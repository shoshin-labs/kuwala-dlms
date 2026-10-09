"""Private curator adapter over the existing document and folder contracts."""
import hashlib
import json
import logging
import os

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import BasePermission

from dlms.preview_middleware import is_loopback_request

from content_management.file_lifecycle import delete_file_after_commit
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata
from content_management.oasis_catalogue import CatalogueDocumentSerializer, CataloguePagination, queried_documents
from content_management.standardize_format import build_response

logger = logging.getLogger(__name__)


class MultipartListField(serializers.ListField):
    """Accept JSON arrays as multipart fields, including an explicit empty list."""
    def get_value(self, dictionary):
        value = super().get_value(dictionary)
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str) and value[0].lstrip().startswith('['):
            return value[0]
        return value

    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                raise serializers.ValidationError('Use a JSON array of IDs.')
        return super().to_internal_value(data)

    def to_representation(self, data):
        if hasattr(data, 'all'):
            data = data.all()
        return super().to_representation(data)


def file_digest(file_object):
    digest = hashlib.sha256()
    file_object.seek(0)
    for chunk in iter(lambda: file_object.read(65536), b''):
        digest.update(chunk)
    file_object.seek(0)
    return digest.digest()


def validate_folder_placement(version, folder_ids):
    """Every selected section must resolve to a root library in this version."""
    ids = set(folder_ids)
    folders = {folder.pk: folder for folder in LibraryFolder.objects.filter(version=version)}
    for identifier in ids:
        seen = set()
        current = identifier
        while current is not None:
            if current in seen or current not in folders:
                raise serializers.ValidationError({'folder_ids': 'Every selected library or section must have a valid parent path in this catalogue version.'})
            seen.add(current)
            current = folders[current].parent_id
    return sorted(ids)


class FolderPlacementSerializer(serializers.Serializer):
    catalogue_version = serializers.PrimaryKeyRelatedField(queryset=LibraryVersion.objects.all())
    folder_ids = MultipartListField(child=serializers.IntegerField(min_value=1), allow_empty=False)

    def validate(self, attrs):
        attrs['folder_ids'] = validate_folder_placement(attrs['catalogue_version'], attrs['folder_ids'])
        return attrs


class OasisDocumentSerializer(CatalogueDocumentSerializer):
    # Validate originals here so replacement may reuse the current basename;
    # the legacy field validators reject it even when it belongs to this item.
    content_file = serializers.FileField(required=False, max_length=500)
    catalogue_version = serializers.PrimaryKeyRelatedField(queryset=LibraryVersion.objects.all(), required=False, write_only=True)
    folder_ids = MultipartListField(child=serializers.IntegerField(min_value=1), required=False, write_only=True)
    metadata = MultipartListField(child=serializers.PrimaryKeyRelatedField(queryset=Metadata.objects.all()), required=False)

    class Meta(CatalogueDocumentSerializer.Meta):
        fields = CatalogueDocumentSerializer.Meta.fields + ('catalogue_version', 'folder_ids')
        read_only_fields = ('id', 'file_name', 'filesize', 'modified_on')

    def validate_content_file(self, upload):
        basename = get_valid_filename(os.path.basename(upload.name))
        upload.name = basename
        storage = Content._meta.get_field('content_file').storage
        current_name = self.instance.content_file.name if self.instance and self.instance.content_file else None
        requested_name = os.path.join('contents', basename)
        if requested_name != current_name and storage.exists(requested_name):
            raise serializers.ValidationError('Filename already exists.')
        digest = file_digest(upload)
        # Check records rather than scanning every local artifact. Preserve the
        # duplicate-original rule, excluding the document being replaced.
        others = Content.objects.exclude(pk=self.instance.pk) if self.instance else Content.objects.all()
        for document in others.exclude(content_file=''):
            original = document.content_file
            if not original.storage.exists(original.name) or original.size != upload.size:
                continue
            with original.storage.open(original.name, 'rb') as existing:
                if file_digest(existing) == digest:
                    raise serializers.ValidationError('This original file already belongs to another document.')
        return upload

    def validate(self, attrs):
        if not self.instance and 'content_file' not in attrs:
            raise serializers.ValidationError({'content_file': 'Choose an original file.'})
        if not self.instance and not attrs.get('folder_ids'):
            raise serializers.ValidationError({'folder_ids': 'Choose a library and, where applicable, a section before importing a document.'})
        if 'folder_ids' in attrs:
            version = attrs.get('catalogue_version')
            if version is None:
                raise serializers.ValidationError({'catalogue_version': 'Select the catalogue version for library membership.'})
            attrs['folder_ids'] = validate_folder_placement(version, attrs['folder_ids'])
        return attrs

    def create(self, validated_data):
        return self.persist(None, validated_data)

    def update(self, instance, validated_data):
        return self.persist(instance, validated_data)

    def persist(self, instance, validated_data):
        version = validated_data.pop('catalogue_version', None)
        folder_ids = validated_data.pop('folder_ids', None)
        metadata = validated_data.pop('metadata', None)
        upload = validated_data.pop('content_file', None)
        stored_name = None
        storage = Content._meta.get_field('content_file').storage
        try:
            with transaction.atomic():
                document = Content.objects.select_for_update().get(pk=instance.pk) if instance else Content()
                old_name = document.content_file.name if document.content_file else None
                folders = None
                if folder_ids is not None:
                    try:
                        version = LibraryVersion.objects.select_for_update().get(pk=version.pk)
                    except LibraryVersion.DoesNotExist:
                        raise serializers.ValidationError({'catalogue_version': 'The selected catalogue version changed. Reload and try again.'})
                    folders = list(LibraryFolder.objects.select_for_update().filter(pk__in=folder_ids, version_id=version.pk))
                    if len(folders) != len(folder_ids):
                        raise serializers.ValidationError({'folder_ids': 'The selected library folders changed. Reload and try again.'})
                for name, value in validated_data.items():
                    setattr(document, name, value)
                document.modified_on = timezone.now()
                if upload is not None:
                    document.content_file = upload
                    filename = document._meta.get_field('content_file').generate_filename(document, upload.name)
                    # Default storage allocates a distinct path when a basename
                    # already exists, leaving the previous original intact.
                    stored_name = storage.save(filename, upload)
                    document.content_file = stored_name
                    document.file_name = os.path.basename(stored_name)
                    document.filesize = upload.size
                document.save()
                if metadata is not None:
                    document.metadata.set(metadata)
                if folders is not None:
                    through = LibraryFolder.library_content.through
                    through.objects.filter(content_id=document.pk, libraryfolder__version_id=version.pk).exclude(libraryfolder_id__in=folder_ids).delete()
                    for folder in folders:
                        folder.library_content.add(document)
                    # Types created after an export version must be included in
                    # its existing whitelist so attribution survives export.
                    version.metadata_types.add(*document.metadata.values_list('type_id', flat=True).distinct())
                if upload is not None and old_name and old_name != stored_name:
                    delete_file_after_commit(storage, old_name)
                return document
        except Exception:
            # Files are outside SQL transactions. Remove only the new candidate
            # on failure; the old original and its memberships remain intact.
            if stored_name:
                try:
                    storage.delete(stored_name)
                except Exception:
                    logger.exception('Unable to remove failed document upload %s', stored_name)
            raise


class PrivateCuratorAccess(BasePermission):
    message = 'Document management requires the explicitly enabled loopback curator preview.'

    def has_permission(self, request, view):
        return settings.OASIS_CURATOR_ENABLED and is_loopback_request(request)


class OasisDocumentViewSet(viewsets.ModelViewSet):
    queryset = Content.objects.all()
    serializer_class = OasisDocumentSerializer
    pagination_class = CataloguePagination
    permission_classes = (PrivateCuratorAccess,)

    def get_queryset(self):
        return queried_documents(super().get_queryset(), self.request.query_params)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return build_response({'results': self.get_serializer(queryset, many=True).data, 'count': queryset.count()})

    def retrieve(self, request, *args, **kwargs):
        return build_response(self.get_serializer(self.get_object()).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return build_response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return build_response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        with transaction.atomic():
            self.get_object().delete()
        return build_response()
