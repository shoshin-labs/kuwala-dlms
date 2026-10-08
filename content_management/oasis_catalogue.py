"""Read-only, bounded catalogue queries over the existing folder relationships."""
from collections import defaultdict

from django.conf import settings
from django.db.models import Prefetch, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.serializers import SerializerMethodField

from dlms.preview_middleware import is_loopback_request
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata
from content_management.paginators import PageNumberSizePagination
from content_management.serializers import ContentSerializer
from content_management.standardize_format import build_response


def positive_id(value, field):
    try:
        result = int(value)
        if not 1 <= result <= 9223372036854775807:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise ValidationError({field: 'Use a positive integer ID.'})


def selected_catalogue(value, *, required=False):
    if value is None:
        if required:
            raise ValidationError({'catalogue_version': 'Choose a catalogue version.'})
        return None
    version_id = positive_id(value, 'catalogue_version')
    try:
        return LibraryVersion.objects.get(pk=version_id)
    except LibraryVersion.DoesNotExist:
        raise ValidationError({'catalogue_version': 'Catalogue version does not exist.'})


def folder_subtree(version, folder_id):
    """Resolve descendants once, guarding malformed legacy cycles."""
    parents = dict(LibraryFolder.objects.filter(version=version).values_list('id', 'parent_id'))
    if folder_id not in parents:
        raise ValidationError({'folder_id': 'Choose a folder in the selected catalogue.'})
    children = defaultdict(list)
    for item_id, parent_id in parents.items():
        children[parent_id].append(item_id)
    descendants, pending = set(), [folder_id]
    while pending:
        item_id = pending.pop()
        if item_id not in descendants:
            descendants.add(item_id)
            pending.extend(children[item_id])
    return descendants


def queried_documents(queryset, parameters, *, public=False):
    """Apply selected-version/subtree/search filters before SQL pagination."""
    version = selected_catalogue(parameters.get('catalogue_version'), required=public)
    global_value = parameters.get('global', '0')
    if global_value not in ('0', '1') or public and global_value == '1':
        raise ValidationError({'global': 'Global document access is a private curator filter.'})
    global_documents = global_value == '1'
    folder_value = parameters.get('folder_id')
    if folder_value is not None and (version is None or global_documents):
        raise ValidationError({'folder_id': 'Select a catalogue and a scoped document list for this folder.'})
    if public:
        queryset = queryset.filter(active=True)
    if version is not None and not global_documents:
        queryset = queryset.filter(libraryfolder__version=version)
    if folder_value is not None:
        ids = folder_subtree(version, positive_id(folder_value, 'folder_id'))
        queryset = queryset.filter(libraryfolder__id__in=ids)
    if parameters.get('document_id') is not None:
        queryset = queryset.filter(pk=positive_id(parameters['document_id'], 'document_id'))
    search = parameters.get('q', '').strip()
    if len(search) > 200:
        raise ValidationError({'q': 'Search is limited to 200 characters.'})
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(display_title__icontains=search) |
            Q(file_name__icontains=search) | Q(description__icontains=search) |
            Q(metadata__name__icontains=search)
        )
    memberships = LibraryFolder.objects.filter(version=version).only('id', 'version_id') if version else LibraryFolder.objects.none()
    return queryset.distinct().order_by('id').prefetch_related(
        Prefetch('metadata', queryset=Metadata.objects.select_related('type')),
        Prefetch('libraryfolder_set', queryset=memberships, to_attr='oasis_catalogue_folders'),
    )


class CatalogueDocumentSerializer(ContentSerializer):
    catalogue_folder_ids = SerializerMethodField()

    class Meta(ContentSerializer.Meta):
        fields = ContentSerializer.Meta.fields + ('catalogue_folder_ids',)

    def get_catalogue_folder_ids(self, document):
        return sorted(folder.id for folder in getattr(document, 'oasis_catalogue_folders', []))


class CataloguePagination(PageNumberSizePagination):
    page_size = 24
    max_page_size = 100

    def get_paginated_response(self, data):
        return build_response({'results': data, 'count': self.page.paginator.count,
                               'next': self.get_next_link(), 'previous': self.get_previous_link(),
                               'page': self.page.number, 'page_size': self.page.paginator.per_page})


def counted_folders(version, *, curator=False):
    folders = list(LibraryFolder.objects.filter(version=version).order_by('id').values('id', 'folder_name', 'parent', 'version'))
    parents = {folder['id']: folder['parent'] for folder in folders}
    direct, subtree = defaultdict(set), defaultdict(set)
    memberships = LibraryFolder.library_content.through.objects.filter(libraryfolder__version=version)
    if not curator:
        memberships = memberships.filter(content__active=True)
    # Only IDs cross this query; document fields and metadata are fetched for
    # the current page alone. Sets preserve multi-library/section deduplication.
    for folder_id, document_id in memberships.values_list('libraryfolder_id', 'content_id').iterator():
        direct[folder_id].add(document_id)
        pending, seen = folder_id, set()
        while pending in parents and pending not in seen:
            subtree[pending].add(document_id)
            seen.add(pending)
            pending = parents[pending]
    for folder in folders:
        folder['direct_document_count'] = len(direct[folder['id']])
        folder['document_count'] = len(subtree[folder['id']])
    return folders


@api_view(['GET'])
@permission_classes([AllowAny])
def catalogue(request):
    mode = request.query_params.get('mode', 'visitor')
    if mode not in ('visitor', 'curator'):
        raise ValidationError({'mode': 'Choose visitor or curator.'})
    curator = mode == 'curator'
    if curator and not (settings.OASIS_CURATOR_ENABLED and is_loopback_request(request)):
        raise PermissionDenied('Curator catalogue counts require the explicitly enabled loopback preview.')
    versions = list(LibraryVersion.objects.order_by('id').values('id', 'library_name', 'version_number'))
    version = selected_catalogue(request.query_params.get('catalogue_version'))
    if version is None and versions:
        version = LibraryVersion.objects.get(pk=versions[0]['id'])
    documents = Content.objects.all() if curator else Content.objects.filter(active=True)
    payload = {'versions': versions, 'catalogue_version': version.id if version else None,
               'folders': counted_folders(version, curator=curator) if version else [],
               'document_count': documents.filter(libraryfolder__version=version).values('id').distinct().count() if version else 0}
    if curator:
        payload['all_document_count'] = Content.objects.count()
    return build_response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def catalogue_documents(request):
    documents = queried_documents(Content.objects.all(), request.query_params, public=True)
    paginator = CataloguePagination()
    page = paginator.paginate_queryset(documents, request)
    return paginator.get_paginated_response(CatalogueDocumentSerializer(page, many=True, context={'request': request}).data)
