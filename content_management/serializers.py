from rest_framework.serializers import ModelSerializer
from content_management.models import (
    Content, Metadata, MetadataType, User,
    LibraryVersion, LibraryFolder, LibLayoutImage, LibraryModule)
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.exceptions import ValidationError
from django.utils import timezone


class ContentSerializer(ModelSerializer):
    class Meta:
        model = Content
        fields = ('id', 'file_name', 'content_file', 'title', 'display_title', 'description', 'modified_on', 'copyright_notes',
                  'rights_statement', 'published_date', 'active', 'metadata', 'additional_notes', 'metadata_info',
                  "published_year", "filesize", "reviewed_on", 'duplicatable')
        read_only_fields = ('modified_on',)

    def create(self, validated_data):
        validated_data['modified_on'] = timezone.now()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['modified_on'] = timezone.now()
        return super().update(instance, validated_data)


class MetadataSerializer(ModelSerializer):
    class Meta:
        validators = [
            UniqueTogetherValidator(
                queryset=Metadata.objects.all(),
                fields=["type", "name"]
            )
        ]
        model = Metadata
        fields = ('id', 'name', 'type', 'type_name')


class MetadataTypeSerializer(ModelSerializer):
    class Meta:
        model = MetadataType
        fields = '__all__'


class LibLayoutImageSerializer(ModelSerializer):
    class Meta:
        model = LibLayoutImage
        fields = ("id", "image_file", "image_group", "file_name")


class LibraryVersionSerializer(ModelSerializer):
    class Meta:
        model = LibraryVersion
        fields = (
            "id", "library_name", "version_number", "created_on",
            "library_banner", "created_by", "user_info", "library_modules", "metadata_types"
        )


class LibraryFolderSerializer(ModelSerializer):
    def validate(self, attrs):
        version = attrs.get('version', self.instance.version if self.instance else None)
        parent = attrs.get('parent', self.instance.parent if self.instance else None)
        seen = {self.instance.pk} if self.instance else set()
        current = parent
        while current is not None:
            if current.pk in seen or current.version_id != version.pk:
                raise ValidationError({'parent': 'Choose a library or section in the same catalogue version, without a parent cycle.'})
            seen.add(current.pk)
            current = current.parent
        if self.instance and version.pk != self.instance.version_id and self.instance.subfolders.exclude(version=version).exists():
            raise ValidationError({'version': 'Move the complete folder tree through the existing move workflow.'})
        return attrs

    class Meta:
        model = LibraryFolder
        fields = (
            "id", "folder_name", "logo_img", "version", "parent", "library_content", "breadcrumb"
        )


class UserSerializer(ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class LibraryModuleSerializer(ModelSerializer):
    class Meta:
        model = LibraryModule
        fields = ("id", "module_name", "module_file", "logo_img", "file_name")
