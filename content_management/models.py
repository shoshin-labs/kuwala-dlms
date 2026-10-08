import os
from _datetime import datetime

from django.db import models
from django.dispatch import receiver
from django.utils.text import get_valid_filename

from content_management.validators import validate_unique_filename, validate_unique_file
from content_management.file_lifecycle import delete_file_after_commit

import logging

logger = logging.getLogger(__name__)

class MetadataType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Metadata(models.Model):
    # TODO: Make sure there are no metadata with the same type and the
    # same name when creating a new one
    name = models.CharField(max_length=500)
    type = models.ForeignKey(MetadataType, on_delete=models.CASCADE)

    def type_name(self):
        return self.type.name

    def __str__(self):
        return f'[{self.type}]{self.name}'


class Content(models.Model):
    def set_file_name(self, file_name):
        path = os.path.join("contents", file_name)
        # get file size if this content was saved individually
        if(self.content_file):
            self.filesize = self.content_file.size
            self.file_name = get_valid_filename(file_name)
        return path

    content_file = models.FileField(
        "File",
        upload_to=set_file_name,
        max_length=500,
        validators=[
            validate_unique_filename,
            validate_unique_file
            ])
    filesize = models.FloatField(null=True, editable=True)
    file_name = models.CharField(max_length=500, null=True)
    title = models.CharField(max_length=300)
    display_title = models.CharField(max_length=300, default="")
    description = models.TextField(null=True)
    modified_on = models.DateTimeField(default=datetime.now)
    metadata = models.ManyToManyField(Metadata, blank=True)
    copyright_notes = models.TextField(null=True)
    rights_statement = models.TextField(null=True)
    additional_notes = models.TextField(null=True)
    published_date = models.DateField(null=True)
    reviewed_on = models.DateField(null=True)
    active = models.BooleanField(default=1)
    duplicatable = models.BooleanField(default=0)

    def published_year(self):
        return None if self.published_date == None else str(self.published_date.year)

    def metadata_info(self):
        return [{
            "id": metadata.id,
            "name": metadata.name,
            "type_name": metadata.type.name,
            "type": metadata.type.id
        } for metadata in self.metadata.all()]

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.title}'

@receiver(models.signals.post_delete, sender=Content)
def on_content_delete(sender, instance, **kwargs):
    logger.info("Delete request received for " + instance.title)
    if instance.content_file:
        delete_file_after_commit(instance.content_file.storage, instance.content_file.name)

class LibLayoutImage(models.Model):

    def get_folder_name(self, file_name):
        if self.image_group == 1:
            return os.path.join("images", "logos", file_name)
        elif self.image_group == 2:
            return os.path.join("images", "banners", file_name)

    GROUPS = (
        (1, 'Logo'),
        (2, 'Banner'),
    )
    image_file = models.FileField(upload_to=get_folder_name)
    image_group = models.PositiveSmallIntegerField(choices=GROUPS, default=1)

    def file_name(self):
        return os.path.basename(self.image_file.name)

    def __str__(self):
        return f'{self.image_file.name}'

@receiver(models.signals.post_delete, sender=LibLayoutImage)
def on_image_delete(sender, instance, **kwargs):
    if instance.image_file:
        if os.path.isfile(instance.image_file.path):
            os.remove(instance.image_file.path)

class User(models.Model):
    name = models.CharField(max_length=300)

    def __str__(self):
        return f'User<{self.name}>'


class LibraryModule(models.Model):
    module_name = models.CharField(max_length=300)
    module_file = models.FileField(upload_to="modules/")
    logo_img = models.ForeignKey(LibLayoutImage, related_name="module_logos", on_delete=models.SET_NULL, null=True)

    def file_name(self):
        return os.path.basename(self.module_file.name)

@receiver(models.signals.post_delete, sender=LibraryModule)
def on_module_delete(sender, instance, **kwargs):
    if instance.module_file:
        if os.path.isfile(instance.module_file.path):
            os.remove(instance.module_file.path)

class LibraryVersion(models.Model):
    library_name = models.CharField(max_length=300)
    version_number = models.CharField(max_length=300, unique=True)
    library_banner = models.ForeignKey(
        LibLayoutImage, related_name="versions", on_delete=models.SET_NULL, null=True
    )
    created_on = models.DateTimeField(default=datetime.now)
    created_by = models.ForeignKey(User, related_name="versions", on_delete=models.SET_NULL, null=True)
    library_modules = models.ManyToManyField(LibraryModule, blank=True)
    metadata_types = models.ManyToManyField(MetadataType, blank=True)

    def user_info(self):
        if self.created_by is None:
            return None
        return {
            "id": self.created_by.id,
            "name": self.created_by.name
        }

    def __str__(self):
        return f'[{self.library_name}]{self.version_number}'


@receiver(models.signals.post_save, sender=LibraryVersion)
def on_version_save(sender, instance, created, **kwargs):
    # adds initial metadata_types
    if created:
        for metadata_type in MetadataType.objects.all():
            instance.metadata_types.add(metadata_type)


class LibraryFolder(models.Model):
    folder_name = models.CharField(max_length=300)
    logo_img = models.ForeignKey(LibLayoutImage, related_name="logos", on_delete=models.SET_NULL, null=True)
    version = models.ForeignKey(LibraryVersion, related_name='folders', on_delete=models.CASCADE)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name="subfolders", null=True)
    library_content = models.ManyToManyField(Content, blank=True)

    def breadcrumb(self):
        parent = self.parent
        arr = [{
            "id": self.id,
            "folder_name": self.folder_name,
            "version": self.version.id,
        }]
        while parent != None:
            arr.insert(0, {
                "id": parent.id,
                "folder_name": parent.folder_name,
                "version": self.version.id,
            })
            parent = parent.parent
        return arr

    def __str__(self):
        return f'{self.folder_name}'

@receiver(models.signals.post_save, sender=LibraryVersion)
def on_folder_save(sender, instance, *args, **kwargs):
    if LibraryVersion.objects.filter(
            library_name=instance.library_name,
            version_number=instance.version_number
    ).exists():
        return
