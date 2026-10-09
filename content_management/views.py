from rest_framework import viewsets, permissions, views
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, renderer_classes
from content_management.models import (
    Content, Metadata, MetadataType, LibLayoutImage, LibraryVersion,
    LibraryFolder, User,
    LibraryModule)
from content_management.utils import ContentSheetUtil, LibraryBuildUtil

from content_management.serializers import ContentSerializer, MetadataSerializer, MetadataTypeSerializer, \
    LibLayoutImageSerializer, LibraryVersionSerializer, LibraryFolderSerializer, UserSerializer, LibraryModuleSerializer

from content_management.standardize_format import build_response
from content_management.paginators import PageNumberSizePagination

from django.db.models import Q
from django.db import IntegrityError, transaction
from django.utils import timezone

from django.http import HttpResponse
from django.contrib.admin.views.decorators import staff_member_required

import csv
from rest_framework.generics import get_object_or_404
from rest_framework.renderers import JSONRenderer
import xlsxwriter
import io
import datetime

from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.permissions import BasePermission
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from django.middleware.csrf import get_token
from django.conf import settings
from dlms.preview_middleware import is_loopback_request


@api_view(['GET'])
def oasis_config(request):
    """Expose UI capabilities; access is enforced separately by preview middleware."""
    return build_response({
        'curator_enabled': getattr(settings, 'OASIS_CURATOR_ENABLED', False) and is_loopback_request(request),
        'synthetic_fixtures': getattr(settings, 'OASIS_SYNTHETIC_FIXTURES', False),
    })

#Checks if user is Admin
class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

class StandardDataView:
   # permission_classes = (IsAdminUser,)

    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers) 
        except IntegrityError as e:
            return build_response(status=status.HTTP_400_BAD_REQUEST, success=False, error="Already Exists in Database")


    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return build_response(serializer.data)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page != None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return build_response(serializer.data)


# Content ViewSet
class ContentViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = Content.objects.all()
    serializer_class = ContentSerializer
    pagination_class = PageNumberSizePagination

    def get_queryset(self):
        queryset = self.queryset

        title = self.request.GET.get("title", None)
        if title != None:
            queryset = queryset.filter(title__icontains=title)

        display_title = self.request.GET.get("display_title", None)
        if display_title != None:
            queryset = queryset.filter(display_title__icontains=display_title)

        file_name = self.request.GET.get("file_name", None)
        if file_name != None:
            queryset = queryset.filter(file_name__icontains=file_name)
        
        copyright_notes = self.request.GET.get("copyright_notes", None)
        if copyright_notes != None:
            queryset = queryset.filter(copyright__icontains=copyright_notes)
        
        active_raw = self.request.GET.get("active", None)
        if active_raw != None:
            if active_raw.lower() == "true":
                queryset = queryset.filter(active=True)
            if active_raw.lower() == "false":
                queryset = queryset.filter(active=False)

        duplicated_raw = self.request.GET.get("duplicatable", None)
        if duplicated_raw != None:
            if duplicated_raw.lower() == "true":
                queryset = queryset.filter(duplicatable=True)
            if duplicated_raw.lower() == "false":
                queryset = queryset.filter(duplicatable=False)
        
        metadata_raw = self.request.GET.get("metadata", None)
        if metadata_raw != None:
            try:
                metadata = [int(x) for x in metadata_raw.split(",")]
                for meta_id in metadata:
                    print(queryset)
                    queryset = queryset.filter(metadata__in=[meta_id])
                    print(queryset)
            except Exception as e:
                print(e)

        year_from_raw = self.request.GET.get("published_year_from", None)
        if year_from_raw != None:
            try:
                year = int(year_from_raw)
                queryset = queryset.filter(published_date__year__gte=(year))
            except:
                pass

        year_to_raw = self.request.GET.get("published_year_to", None)
        if year_to_raw != None:
            try:
                year = int(year_to_raw)
                queryset = queryset.filter(published_date__year__lte=(year))
            except:
                pass
        
        filesize_from_raw = self.request.GET.get("filesize_from", None)
        if filesize_from_raw != None:
            try:
                filesize = int(filesize_from_raw)
                queryset = queryset.filter(filesize__gte=(filesize * 1000000))
            except:
                pass

        filesize_to_raw = self.request.GET.get("filesize_to", None)
        if filesize_to_raw != None:
            try:
                filesize = int(filesize_to_raw)
                queryset = queryset.filter(filesize__lte=(filesize * 1000000))
            except:
                pass
        
        reviewed_from_raw = self.request.GET.get("reviewed_from", None)
        if reviewed_from_raw != None:
            try:
                queryset = queryset.filter(reviewed_on__gte=(reviewed_from_raw))
            except:
                pass

        reviewed_to_raw = self.request.GET.get("reviewed_to", None)
        if reviewed_to_raw != None:
            try:
                queryset = queryset.filter(reviewed_on__lte=(reviewed_to_raw))
            except:
                pass

        exclude_version = self.request.GET.get("exclude_in_version", None)
        if exclude_version != None:
            try:
                content_in_version = LibraryFolder.objects.filter(version_id=exclude_version).values_list('library_content', flat=True)
                id_list = list(content_in_version)
                filtered = filter(lambda id: id != None, id_list)
                if filtered != []:
                    queryset = queryset.filter(Q(duplicatable=True) | ~Q(id__in=filtered))
            except Exception as e:
                print(e)
        
        order_raw = self.request.GET.get("sort", None)
        if order_raw != None:
            try:
                split = order_raw.split(",")
                if split[0] == "published_year":
                    split[0] = "published_date"
                order_str = ("-" if split[1] == "desc" else "") + split[0]
                queryset = queryset.order_by(order_str)
            except:
                pass

        return queryset
    
    @action(methods=['get'], detail=False)
    def get_spreadsheet(self, request):
        output = io.BytesIO()

        workbook = xlsxwriter.Workbook(output, {'remove_timezone': True})
        worksheet = workbook.add_worksheet()
        
        content_fields = [
            "title", "display_title", "file_name", "description", "modified_on", "copyright_notes",
            "rights_statement", "additional_notes", "published_date", "reviewed_on", "active",
            "duplicatable", "filesize"
        ]

        field_display_names = [
            "Title", "Display Title", "File Name", "Description", "Modified On", "Copyright Notes",
            "Rights Statement", "Additional Notes", "Year Published", "Reviewed On", "Active",
            "Duplicatable", "Filesize"
        ]

        metadata_types = MetadataType.objects.all().order_by("name")
        for col_num, field_name in enumerate(field_display_names):
            worksheet.write(0, col_num, field_name)

        for type_num, metadata in enumerate(metadata_types):
            worksheet.write(0, len(content_fields) + type_num, metadata.name)

        for row_num, content in enumerate(self.get_queryset()):
            for col_num, field_name in enumerate(content_fields):
                attr = getattr(content, field_name, "")
                to_write = str(attr) if not isinstance(attr, datetime.date) else attr.strftime("%m/%d/%Y, %H:%M:%S")
                worksheet.write(row_num + 1, col_num, to_write)

            for type_num, metadata in enumerate(metadata_types):
                worksheet.write(
                    row_num + 1,
                    type_num + len(content_fields),
                    " | ".join([metadata.name for metadata in content.metadata.filter(type=metadata).all()])
                )

        workbook.close()
        output.seek(0)

        filename = 'dlms-content-{}.xlsx'.format(datetime.datetime.now()
            .strftime("%m-%d-%Y"))
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename={}'.format(filename)
        return response

class MetadataViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = Metadata.objects.all()
    serializer_class = MetadataSerializer
    pagination_class = PageNumberSizePagination

    @action(methods=['get'], detail=True)
    def get(self, request, pk=None):
        name = request.GET.get("name", None)
        queryset = self.filter_queryset(Metadata.objects.filter(
            type__name=pk,
            **({"name__icontains":name} if name is not None else dict())
        ))

        page = self.paginate_queryset(queryset)
        if page != None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return build_response(serializer.data)

class MetadataTypeViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = MetadataType.objects.all()
    serializer_class = MetadataTypeSerializer


class LibLayoutImageViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = LibLayoutImage.objects.all()
    serializer_class = LibLayoutImageSerializer

class UserViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class LibraryVersionViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = LibraryVersion.objects.all()
    serializer_class = LibraryVersionSerializer
    folder_serializer = LibraryFolderSerializer
    pagination_class = PageNumberSizePagination

    def get_queryset(self):
            return self.queryset.order_by("id")

    @action(methods=['post'], detail=True)
    def add_metadata_type(self, request, pk=None):
        metadata_type_id = request.data.get('metadata_type_id', None)

        if metadata_type_id is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Metadata Type ID supplied"
            )
        
        version = self.get_queryset().get(id=pk)
        version.metadata_types.add(
            MetadataType.objects.get(id=metadata_type_id)
        )
        print(version.metadata_types )
        return build_response(LibraryVersionSerializer(version).data)

    @action(methods=['post'], detail=True)
    def remove_metadata_type(self, request, pk=None):
        metadata_type_id = request.data.get('metadata_type_id', None)
        
        if metadata_type_id is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Metadata Type ID supplied"
            )
        
        version = self.get_queryset().get(id=pk)
        version.metadata_types.remove(
            MetadataType.objects.get(id=metadata_type_id)
        )
        print(version.metadata_types)
        return build_response(LibraryVersionSerializer(version).data)

    @action(methods=['get'], detail=True)
    def root(self, request, pk=None):
        return build_response(LibraryFolderSerializer(
                LibraryFolder.objects.filter(version=pk, parent=None).order_by("id"),
                many=True
            ).data if pk != None else []
        )
    
    @action(methods=['get'], detail=True)
    def folders(self, request, pk=None):
        return build_response(LibraryFolderSerializer(
            LibraryFolder.objects.filter(version=pk).order_by("id"),
            many=True
        ).data if pk != None else [])

    @action(methods=['get'], detail=True)
    def modules(self, request, pk=None):
        return build_response(LibraryModuleSerializer(
            LibraryVersion.objects.get(id=pk).library_modules.all(),
            many=True
        ).data if pk != None and pk != '0' else []
                              )

    @action(methods=['post'], detail=True)
    def addmodule(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Version ID supplied"
            )
        library_module_id = request.data.get("library_module_id", None)
        if library_module_id is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Module ID supplied"
            )
        version = self.get_queryset().get(id=pk)
        version.library_modules.add(
            LibraryModule.objects.get(id=library_module_id)
        )
        return build_response()

    @action(methods=['post'], detail=True)
    def removemodule(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Version ID supplied"
            )
        library_module_id = request.data.get("library_module_id", None)
        if library_module_id is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Module ID supplied"
            )
        version = self.get_queryset().get(id=pk)
        version.library_modules.remove(
            LibraryModule.objects.get(id=library_module_id)
        )
        return build_response()

    @action(methods=["get"], detail=False)
    def filter_prefix(self, request):
        prefix = request.GET.get("prefix", "")
        return build_response(LibraryVersionSerializer(
            LibraryVersion.objects.all()
                .filter(library_name__icontains=prefix)
                [:10],
            many=True
        ).data)

    @action(methods=['get'], detail=True)
    def clone(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
                )
        
        version_to_clone = get_object_or_404(LibraryVersion, id=pk)
        modules = version_to_clone.library_modules.all()

        #clone version
        version_to_clone.id = None

        i = 0
        new_number = version_to_clone.version_number + str(i)
        while LibraryVersion.objects.filter(version_number=new_number).exists():
            i += 1
            new_number = version_to_clone.version_number + str(i)


        version_to_clone.version_number = new_number
        version_to_clone.save()
        
        version_to_clone.library_modules.set(modules)
        version_to_clone.created_on = datetime.datetime.now()
        version_to_clone.save()


        def clone_recursively(folder_to_clone, new_parent):
            #save relationships of the old folder
            subfolders = folder_to_clone.subfolders.all()
            library_content = folder_to_clone.library_content.all()
            
            #clone subfolder
            folder_to_clone.id = None
            folder_to_clone.save()
            folder_to_clone.parent = new_parent
            folder_to_clone.version = version_to_clone
            folder_to_clone.library_content.set(library_content)
            folder_to_clone.save()
            
            for child in subfolders:
                clone_recursively(child, folder_to_clone)
        
        [
            clone_recursively(top_level_folder, None) for top_level_folder
            in LibraryFolder.objects.filter(parent=None, version_id=pk)
        ]

        return build_response(LibraryVersionSerializer(version_to_clone).data)
    


class LibraryFolderViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = LibraryFolder.objects.all()
    serializer_class = LibraryFolderSerializer

    def _transfer_target(self, request, source):
        """Validate the existing destination parameters before changing a tree."""
        folder_id = request.GET.get("dest_folder")
        version_id = request.GET.get("dest_version")
        if folder_id is None and version_id is None:
            raise ValueError("No Destination Library or Folder supplied")
        try:
            if folder_id is not None:
                destination = LibraryFolder.objects.get(id=int(folder_id))
                seen = set()
                current = destination
                while current is not None:
                    if current.pk == source.pk:
                        raise ValueError("A folder cannot be moved or copied into itself or a descendant.")
                    if current.pk in seen:
                        raise ValueError("The destination folder has an invalid parent path.")
                    seen.add(current.pk)
                    current = current.parent
                return destination, destination.version
            return None, LibraryVersion.objects.get(id=int(version_id))
        except (TypeError, LibraryFolder.DoesNotExist, LibraryVersion.DoesNotExist):
            raise ValueError("Select an existing destination library version or folder.")

    @action(methods=['get'], detail=True)
    def contents(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
                )
        else:
            return build_response(
                {
                    "folders": self.get_serializer(
                        self.get_queryset().filter(parent=pk).order_by("id"),
                        many=True
                    ).data,
                    "files": ContentSerializer(
                        self.get_queryset().get(id=pk).library_content,
                        many=True
                    ).data
                }
            )
    
    @action(methods=['post'], detail=True)
    def addcontent(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
            )
        content_ids = request.data.get("content_ids", None) 
        if content_ids is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Content ID supplied"
            )
        
        folder = self.get_queryset().get(id=pk)
        for content_id in content_ids:
            folder.library_content.add(
                Content.objects.get(id=content_id)
            )

        return build_response()
    
    @action(methods=['post'], detail=True)
    def removecontent(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
            )
        
        content_ids = request.data.get("content_ids", None) 
        if content_ids is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Content ID supplied"
            )
        
        folder = self.get_queryset().get(id=pk)
        for content_id in content_ids:
            folder.library_content.remove(
                Content.objects.get(id=content_id)
            )

        return build_response()

    @action(methods=["post"], detail=True)
    def move_to(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
            )
        
        def update_child_version(folder, version):
            folder.version = version
            folder.save()
            for child in folder.subfolders.all():
                update_child_version(child, version)

        to_move = get_object_or_404(LibraryFolder, id=pk)
        try:
            destination, version = self._transfer_target(request, to_move)
        except ValueError as error:
            return build_response(status=status.HTTP_400_BAD_REQUEST, success=False, error=str(error))
        with transaction.atomic():
            to_move.parent = destination
            to_move.save()
            update_child_version(to_move, version)
        return build_response()

    @action(methods=["post"], detail=True)
    def copy_to(self, request, pk=None):
        if pk is None:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error="No Folder ID supplied"
            )
        
        def copy_children_and_update(folder, version, new_parent):
            old_id = folder.id
            old_files = folder.library_content.all()
            folder.id = None
            folder.version = version
            folder.parent = new_parent
            folder.save()
            folder.library_content.set(old_files)
            for child in LibraryFolder.objects.get(id=old_id).subfolders.all():
                copy_children_and_update(child, version, folder)

        to_copy = get_object_or_404(LibraryFolder, id=pk)
        try:
            destination, version = self._transfer_target(request, to_copy)
        except ValueError as error:
            return build_response(status=status.HTTP_400_BAD_REQUEST, success=False, error=str(error))
        with transaction.atomic():
            copy_children_and_update(to_copy, version, destination)
        return build_response()


class LibraryModuleViewSet(StandardDataView, viewsets.ModelViewSet):
    queryset = LibraryModule.objects.all()
    serializer_class = LibraryModuleSerializer


class BulkAddView(views.APIView):

    def post(self, request):
        sheet_util = ContentSheetUtil()
        content_data = request.data
        placement = None
        if getattr(settings, 'OASIS_CURATOR_ENABLED', False) and str(content_data.get('content_path') or '').strip():
            from content_management.oasis_documents import FolderPlacementSerializer
            selected = FolderPlacementSerializer(data=content_data)
            selected.is_valid(raise_exception=True)
            placement = selected.validated_data
        result = sheet_util.upload_sheet_contents(content_data, placement=placement)
        if result.get('success') is False:
            return build_response(status=status.HTTP_400_BAD_REQUEST, success=False, error=result.get('error'))
        response = build_response(result)
        return response


class LibraryBuildView(views.APIView):

    def get(self, request, *args, **kwargs):
        version_id = int(kwargs['version_id'])
        build_util = LibraryBuildUtil(version_id)
        result = build_util.build_library()
        if result.get("result") == "success":
            return build_response(result)
        else:
            return build_response(
                status=status.HTTP_400_BAD_REQUEST,
                success=False,
                error=result.get("error")
            )

@api_view(('GET',))
# @staff_member_required
def metadata_sheet(request, metadata_type):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="{}.csv"'.format(metadata_type)
    
    writer = csv.writer(response)
    writer.writerow([metadata_type])

    for metadata in Metadata.objects.all().filter(type__name=metadata_type):
        writer.writerow([metadata.name])
    
    return response


@api_view(('GET',))
# @staff_member_required
@renderer_classes((JSONRenderer,))
def disk_info(request):
    import shutil
    total, used, free = shutil.disk_usage('/')
    return build_response({
        "total": total,
        "used": used,
        "free": free
    })

@api_view(('GET',))
# @staff_member_required
@renderer_classes((JSONRenderer,))
def get_csrf(request):
    return build_response(get_token(request))

@api_view(('POST',))
# @staff_member_required
@renderer_classes((JSONRenderer,))
def bulk_edit(request):
    to_remove = request.data.get("to_remove")
    to_add = request.data.get("to_add")
    with transaction.atomic():
        for content in Content.objects.select_for_update().filter(id__in=request.data.get("to_edit")):
            before = set(content.metadata.values_list('id', flat=True))
            content.metadata.remove(*to_remove)
            content.metadata.add(*to_add)
            if before != set(content.metadata.values_list('id', flat=True)):
                content.modified_on = timezone.now()
                content.save(update_fields=['modified_on'])

    return build_response()
