import datetime
import json
import os
import shutil
import time
from pathlib import Path

from django.core.exceptions import ValidationError, MultipleObjectsReturned
from django.core.files import File
from django.utils import timezone
from django.db import transaction
from django.utils.text import get_valid_filename
from rest_framework import status

from content_management.library_db_utils import LibraryDbUtil
from content_management.models import (
    Content,
    Metadata, MetadataType, LibraryFolder, LibraryModule, LibraryVersion)
from content_management.validators import validate_unique_filename, validate_unique_file

import hashlib

from django.conf import settings


class ContentSheetUtil:

    def upload_sheet_contents(self, sheet_contents, placement=None):
        """
        This method adds bulk content data from the Excel sheet uploaded
        :param sheet_contents:
        :return: success status
        """
        unsuccessful_uploads = []
        successful_uploads_count = 0
        try:
            content_data = json.loads(sheet_contents.get("sheet_data"))
            main_path = sheet_contents.get("content_path")
            # if path is provided, add content
            if main_path:
                for each_content in content_data:
                    # if the actual file is not uploaded, don't upload its metadata
                    file_path = os.path.join(main_path, each_content.get("File Name"))
                    if os.path.exists(file_path) is not True:
                        unsuccessful_uploads.append({'file_name': each_content.get("File Name"),
                                                     'error': 'file does not exist'})
                        continue
                    else:
                        try:
                            content = Content()
                            content.title = each_content.get("Title")
                            if each_content.get("Display Title"):
                                content.display_title = each_content.get("Display Title")
                            else:
                                content.display_title = each_content.get("Title")
                            content.description = each_content.get("Description")
                            content.copyright_notes = each_content.get("Copyright Notes")
                            content.reviewed_on = datetime.datetime.now()
                            content.rights_statement = each_content.get("Rights Statement")
                            if each_content.get("Year Published"):
                                try:
                                    content.published_date = datetime.date(each_content.get("Year Published"), 1, 1)
                                except ValueError:
                                    content.published_date = None
                            content.modified_on = timezone.now()
                            content.additional_notes = each_content.get("Additional Notes")
                            
                            active = each_content.get("Active")
                            if active:
                                if type(active) == bool:
                                    content.active = active
                                elif hasattr(active, "lower"):
                                    active = active.lower()
                                    if active == "true" or active == "yes":
                                        content.active = True
                                    else:
                                        content.active = False
                            duplicatable = each_content.get("Duplicatable")
                            if duplicatable:
                                if type(duplicatable) == bool:
                                    content.duplicatable = duplicatable
                                elif hasattr(duplicatable, "lower"):
                                    duplicatable = duplicatable.lower()
                                    if duplicatable == "true" or duplicatable == "yes":
                                        content.duplicatable = True
                                    else:
                                        content.duplicatable = False

                            content.filesize = os.stat(file_path).st_size
                            try:
                                content.save()
                            except Exception as e:
                                raise Exception(str(e))
                            try:
                                self.upload_content_file(file_path, content)
                            except (Exception, ValidationError) as e:
                                content.delete()
                                raise e
                            try:
                                metadata = self.get_associated_meta(each_content)
                                for metadata_item in metadata:
                                    try:
                                        obj, created = Metadata.objects.get_or_create(defaults={'name': metadata_item.name},
                                                                                      name__iexact=metadata_item.name,
                                                                                      type_id=metadata_item.type.id)
                                    except MultipleObjectsReturned:
                                        obj = Metadata.objects.filter(name__iexact=metadata_item.name, type_id=metadata_item.type.id)[0]

                                    content.metadata.add(obj)
                                content.save()
                                if placement is not None:
                                    # A reported successful import must have its exact selected
                                    # memberships. Lock/recheck in case folders were removed
                                    # after the batch preflight. Failure uses the existing
                                    # candidate cleanup below and never reports it imported.
                                    with transaction.atomic():
                                        from content_management.oasis_documents import validate_folder_placement
                                        version = LibraryVersion.objects.select_for_update().get(pk=placement['catalogue_version'].pk)
                                        ids = validate_folder_placement(version, placement['folder_ids'])
                                        folders = list(LibraryFolder.objects.select_for_update().filter(pk__in=ids, version=version))
                                        if len(folders) != len(ids):
                                            raise ValueError('Selected libraries or sections changed; reload before importing.')
                                        for folder in folders:
                                            folder.library_content.add(content)
                                        version.metadata_types.add(*content.metadata.values_list('type_id', flat=True).distinct())
                                successful_uploads_count = successful_uploads_count + 1
                            except Exception as e:
                                content.delete()
                                raise e
                        except (Exception, ValidationError) as e:
                            unsuccessful_uploads.append({'file_name': each_content.get("File Name"), 'error': str(e)})
                            continue
            # if no path is provided, edit the metadata of existing content
            else:
                for each_content in content_data:
                    # if title is not found, don't upload its metadata
                    content = Content.objects.filter(title=each_content.get("Title")).first()
                    print(content)
                    if content is None:
                        unsuccessful_uploads.append({'file_name': each_content.get("Title"),
                                                     'error': 'content does not exist'})
                        continue
                    else:
                        try:
                            content.description = each_content.get("Description")
                            if each_content.get("Display Title"):
                                content.display_title = each_content.get("Display Title")
                            else:
                                content.display_title = each_content.get("Title")
                            content.copyright_notes = each_content.get("Copyright Notes")
                            content.reviewed_on = datetime.datetime.now()
                            content.rights_statement = each_content.get("Rights Statement")
                            if each_content.get("Year Published"):
                                try:
                                    content.published_date = datetime.date(each_content.get("Year Published"), 1, 1)
                                except ValueError:
                                    content.published_date = None
                            content.modified_on = timezone.now()
                            content.additional_notes = each_content.get("Additional Notes")

                            active = each_content.get("Active")
                            if active:
                                if type(active) == bool:
                                    content.active = active
                                elif hasattr(active, "lower"):
                                    active = active.lower()
                                    if active == "true" or active == "yes":
                                        content.active = True
                                    else:
                                        content.active = False
                            duplicatable = each_content.get("Duplicatable")
                            if duplicatable:
                                if type(duplicatable) == bool:
                                    content.duplicatable = duplicatable
                                elif hasattr(duplicatable, "lower"):
                                    duplicatable = duplicatable.lower()
                                    if duplicatable == "true" or duplicatable == "yes":
                                        content.duplicatable = True
                                    else:
                                        content.duplicatable = False

                            try:
                                content.save()
                            except Exception as e:
                                raise Exception(str(e))
                            try:
                                # clear previous metadata association and add new ones
                                content.metadata.clear()
                                metadata = self.get_associated_meta(each_content)
                                for metadata_item in metadata:
                                    try:
                                        obj, created = Metadata.objects.get_or_create(defaults={'name': metadata_item.name},
                                                                                      name__iexact=metadata_item.name,
                                                                                      type_id=metadata_item.type.id)
                                    except MultipleObjectsReturned:
                                        obj = Metadata.objects.filter(name__iexact=metadata_item.name, type_id=metadata_item.type.id)[0]
                                    content.metadata.add(obj)
                                content.save()
                                successful_uploads_count = successful_uploads_count + 1
                            except Exception as e:
                                content.delete()
                                raise e
                        except (Exception, ValidationError) as e:
                            unsuccessful_uploads.append({'file_name': each_content.get("Title"), 'error': str(e)})
                            continue

            data = {
                'success_count': successful_uploads_count,
                'unsuccessful_uploads': unsuccessful_uploads,
            }
            return data

        except Exception as e:
            data = {
                'success': False,
                'error': str(e),
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR
            }
            return data

    @staticmethod
    def get_associated_meta(sheet_row):
        meta_list = []
        for metadata_type in MetadataType.objects.all():
            if sheet_row.get(metadata_type.name) == '' or sheet_row.get(metadata_type.name) is None:
                continue
            meta_values = sheet_row[metadata_type.name].split(' | ')
            for each_value in meta_values:
                metadata = Metadata(name=each_value, type=metadata_type)
                meta_list.append(metadata)
        return meta_list

    @staticmethod
    def upload_content_file(full_path, content: Content):
        content_file = open(full_path, "rb")
        base_name = get_valid_filename(os.path.basename(content_file.name))
        validate_unique_filename(File(content_file, base_name))
        validate_unique_file(File(content_file, base_name))
        content.file_name = base_name
        content.content_file.save(base_name, File(content_file))
        content_file.close()


class LibraryBuildUtil:
    def __init__(self, version_id):
        self.version = LibraryVersion.objects.get(pk=version_id)

    def build_library(self):
        metadata_types = LibraryVersion.metadata_types.through.objects.filter(
            libraryversion__id=self.version.id) \
            .values_list('metadatatype_id', 'metadatatype__name')
        metadata = Metadata.objects.filter(content__libraryfolder__version_id=self.version.id) \
            .filter(type__pk__in=metadata_types.values_list('metadatatype_id')).values_list('id', 'name',
                                                                                            'type__name',
                                                                                            'type_id').distinct()
        folders = LibraryFolder.objects.filter(version_id=self.version.id).values_list('id', 'folder_name',
                                                                                       'logo_img__image_file',
                                                                                       'parent_id')
        modules = self.get_modules_names(LibraryModule.objects.filter(libraryversion__id=self.version.id)
                                         .values('id',
                                                 'module_file',
                                                 'logo_img__image_file'))

        contents = self.add_keywords(
            Content.objects.filter(libraryfolder__version_id=self.version.id).values('id',
                                                                                     'display_title',
                                                                                     'description',
                                                                                     'file_name',
                                                                                     'published_date',
                                                                                     'copyright_notes',
                                                                                     'rights_statement',
                                                                                     'filesize').distinct())
        contents_metadata = Content.metadata.through.objects.filter(content__libraryfolder__version_id=self.version.id) \
            .filter(metadata_id__in=metadata.values_list('id')).values_list('content_id', 'metadata_id').distinct()
        contents_folder = LibraryFolder.library_content.through.objects.filter(
            libraryfolder__version_id=self.version.id) \
            .values_list('content_id', 'libraryfolder_id', 'content__display_title', 'content__file_name',
                         'content__filesize').distinct()
        db_util = LibraryDbUtil(metadata_types, metadata, folders, modules, contents, contents_metadata,
                                contents_folder)
        try:
            build_path = os.path.join(os.path.abspath(settings.BUILDS_ROOT), self.version.version_number)
            if not os.path.isdir(build_path):
                os.makedirs(build_path)
            else:
                build_path = build_path + "_" + str(int(time.time()))
                os.makedirs(build_path)
                print("Directory '% s' successfully created" % build_path)
            self.create_asset_folder(folders.filter(parent_id=None), modules, build_path)
            db_util.create_library_db(build_path)
            self.copy_library_files(contents, build_path)
            print("success creating content folder")
            data = {
                'result': 'success',
            }
            return data

        except Exception as e:
            data = {
                'result': 'error',
                'error': str(e)
            }
            return data

    def add_keywords(self, content):
        """
        This method returns the list of content with its associated list of keywords separated by space. We need this
        for FTS in sqlite to lookup content using its keywords
        :param content:
        :return: a list of content with its associated list of keywords
        """
        content_with_keywords = []
        try:
            for content_item in content:
                keywords_list = Content.metadata.through.objects.filter(content__id=content_item['id']) \
                    .filter(metadata__type__name='Keywords').values_list('metadata__name', flat=True)
                string_keywords = ' '.join([str(i) for i in keywords_list])
                content_item['keywords'] = string_keywords
                content_with_keywords.append(list(content_item.values()))
            return list(content_with_keywords)
        except Exception as e:
            raise e

    def get_modules_names(self, modules):
        """
        This method gets the names of the module files without their extension in order to create its associated url
        later in the app
        :param modules:
        :return: same list of modules with its updated module name (without extension)
        """
        updated_modules_list = []
        try:
            for mod in modules:
                module_name = Path(mod['module_file']).stem
                mod['module_file'] = module_name
                updated_modules_list.append(list(mod.values()))
            return list(updated_modules_list)
        except Exception as e:
            raise e

    def copy_library_files(self, files_list, build_path):
        """
        This method copy the files of the library to be built into a separate folder to be exported
        :param files_list:
        :return: boolean value indicating success/failure of operation
        """
        dir_path = os.path.join(build_path, "content/")
        if not os.path.isdir(dir_path):
            os.makedirs(dir_path)
        print("Directory '% s' successfully created" % dir_path)
        try:
            for content in files_list:
                src_dir = os.path.join(os.path.abspath(settings.CONTENTS_ROOT), content[3])
                shutil.copy(src_dir, dir_path)
            return True
        except FileNotFoundError:
            print("file '% s' doesn't exist in content folder: " % src_dir)
            os.remove(dir_path)

    def create_asset_folder(self, categories, modules, build_path):
        """
        This method creates the asset folder that contains the logos, banner image, and a json file that has information
         about the library version
        """
        logos_path = os.path.join(build_path, "assets/images/logos")
        banners_path = os.path.join(build_path, "assets/images/banners")
        config_path = os.path.join(build_path, "assets/config.json")
        if not os.path.exists(logos_path):
            os.makedirs(logos_path)
        print("Directory '% s' successfully created" % logos_path)
        if not os.path.exists(banners_path):
            os.makedirs(banners_path)
        print("Directory '% s' successfully created" % banners_path)
        try:
            # copy categories icons
            for cat in categories:
                # logo_img__image_file is located at index 2
                if cat[2]:
                    src_dir = os.path.join(os.path.abspath(settings.MEDIA_ROOT), cat[2])
                    shutil.copy(src_dir, logos_path)
            # copy modules icons
            for mod in modules:
                # logo_img__image_file is located at index 2
                if mod[2]:
                    src_dir = os.path.join(os.path.abspath(settings.MEDIA_ROOT), mod[2])
                    shutil.copy(src_dir, logos_path)
            # Branding assets are optional in the data model. A plain library
            # must still export its documents and catalogue successfully.
            if self.version.library_banner and self.version.library_banner.image_file:
                src_dir = self.version.library_banner.image_file.path
                shutil.copy(src_dir, banners_path)
                os.rename(os.path.join(banners_path, os.path.basename(src_dir)),
                          os.path.join(banners_path, "banner.png"))
            # create config.json
            config = {"version": self.version.version_number}
            with open(config_path, 'w') as f:
                json.dump(config, f)
            return True
        except FileExistsError:
            print("file '% exists in asset folder: " % src_dir)


def sha256(bytestream):
    hash_sha256 = hashlib.sha256()
    for chunk in iter(lambda: bytestream.read(4096), b""):
        hash_sha256.update(chunk)
    return hash_sha256.hexdigest()
