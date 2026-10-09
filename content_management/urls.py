from django.urls import include, path
from rest_framework import routers
from django.conf.urls.static import static

from django.conf import settings
from .views import (
    ContentViewSet, MetadataViewSet, MetadataTypeViewSet, UserViewSet,
    LibraryFolderViewSet, LibraryVersionViewSet, LibLayoutImageViewSet,
    LibraryBuildView, metadata_sheet, BulkAddView, get_csrf, bulk_edit,
    LibraryModuleViewSet, disk_info, oasis_config
)
from content_management.oasis_documents import OasisDocumentViewSet
from content_management.oasis_indexing import OasisIndexJobViewSet, indexing_status
from content_management.oasis_catalogue import catalogue, catalogue_documents
from content_management.oasis_search import index_search, draft_original
from content_management.oasis_library_transfer import LibraryBundleExportView, LibraryBundleImportView

router = routers.DefaultRouter()
router.register(r'contents', ContentViewSet)
router.register(r'metadata', MetadataViewSet)
router.register(r'metadata_types', MetadataTypeViewSet)
router.register(r'lib_layout_images', LibLayoutImageViewSet)
router.register(r'library_versions', LibraryVersionViewSet)
router.register(r'library_folders', LibraryFolderViewSet)
router.register(r'users', UserViewSet)
router.register(r'library_modules', LibraryModuleViewSet)
router.register(r'oasis/documents', OasisDocumentViewSet, basename='oasis-document')
router.register(r'oasis/index-jobs', OasisIndexJobViewSet, basename='oasis-index-job')


urlpatterns = [
    path('api/oasis/libraries/<int:library_id>/bundle/', LibraryBundleExportView.as_view(), name='oasis-library-bundle'),
    path('api/oasis/libraries/import/', LibraryBundleImportView.as_view(), name='oasis-library-import'),
    path('api/oasis/config/', oasis_config, name='oasis-config'),
    path('api/oasis/catalogue/', catalogue, name='oasis-catalogue'),
    path('api/oasis/catalogue/documents/', catalogue_documents, name='oasis-catalogue-documents'),
    path('api/oasis/indexing/', indexing_status, name='oasis-indexing'),
    path('api/oasis/index-search/', index_search, name='oasis-index-search'),
    path('api/oasis/index-search/original/<uuid:job_id>/<int:document_id>/', draft_original, name='oasis-draft-original'),
    path('api/', include(router.urls)),
    path('api/contents_upload/', BulkAddView.as_view(), name="contents-upload"),
    path('api/content_bulk_add/', BulkAddView.as_view(), name="content_bulk_add"),
    path('api/create_build/<int:version_id>/', LibraryBuildView.as_view(), name="create-build"),
    path('api/spreadsheet/metadata/<str:metadata_type>', metadata_sheet),
    path('api/disk_info/', disk_info),
    path('api/get_csrf/', get_csrf),
    path('api/bulk_edit/', bulk_edit),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
