"""Protect API IDs/export contracts and the isolated preview access boundary."""
import hashlib
import sqlite3
import tempfile
from types import ModuleType
from pathlib import Path

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import include, path
from django.views.static import serve
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibLayoutImage, LibraryFolder, LibraryVersion, Metadata, MetadataType


class CatalogueContractTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'media' / 'contents').mkdir(parents=True)
        urlconf = ModuleType('catalogue_test_urls')
        urlconf.urlpatterns = [
            path('media/<path:path>', serve, {'document_root': str(root / 'media')}),
            path('', include('content_management.urls')),
        ]
        self.settings_override = override_settings(
            MEDIA_ROOT=str(root / 'media'), CONTENTS_ROOT=str(root / 'media' / 'contents'),
            BUILDS_ROOT=str(root / 'builds'), OASIS_CURATOR_ENABLED=True, ROOT_URLCONF=urlconf,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.temp.cleanup)
        self.client = APIClient()
        self.version = LibraryVersion.objects.create(library_name='Synthetic test library', version_number='synthetic-test-v1')
        self.farming = LibraryFolder.objects.create(folder_name='Farming', version=self.version)
        self.water = LibraryFolder.objects.create(folder_name='Water', version=self.version)

    def upload(self):
        source = sample_pdf('Synthetic upload contract fixture')
        response = self.client.post('/api/contents/', {
            'title': 'Synthetic upload contract fixture', 'display_title': 'Synthetic upload contract fixture',
            'description': 'Synthetic contract fixture; no technical advice.',
            'copyright_notes': 'Original synthetic fixture by test contributors',
            'rights_statement': 'CC0-1.0 (synthetic test fixture only)',
            'content_file': ContentFile(source, name='synthetic-contract.pdf'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        return Content.objects.get(pk=response.json()['id']), source

    def test_catalogue_detail_and_multiple_library_membership(self):
        document, _ = self.upload()
        for folder in (self.farming, self.water):
            response = self.client.post('/api/library_folders/%s/addcontent/' % folder.id, {'content_ids': [document.id]}, format='json')
            self.assertEqual(response.status_code, 200)
            payload = self.client.get('/api/library_folders/%s/contents/' % folder.id).json()
            self.assertEqual(payload['data']['files'][0]['id'], document.id)
        child = LibraryFolder.objects.create(folder_name='Water records', version=self.version, parent=self.water)
        roots = self.client.get('/api/library_versions/%s/root/' % self.version.id).json()['data']
        self.assertEqual([item['id'] for item in roots], [self.farming.id, self.water.id])
        folder_contents = self.client.get('/api/library_folders/%s/contents/' % self.water.id).json()['data']
        self.assertEqual(folder_contents['folders'][0]['id'], child.id)
        listing = self.client.get('/api/contents/?title=Synthetic').json()['data']
        self.assertEqual(listing['count'], 1)
        detail = self.client.get('/api/contents/%s/' % document.id).json()['data']
        self.assertEqual(detail['id'], document.id)
        self.assertIsNone(detail['reviewed_on'])
        self.assertEqual(detail['copyright_notes'], 'Original synthetic fixture by test contributors')
        self.assertTrue(detail['content_file'].endswith('/media/contents/synthetic-contract.pdf'))
        original = self.client.get('/media/contents/synthetic-contract.pdf')
        self.assertEqual(original.status_code, 200)
        self.assertTrue(b''.join(original.streaming_content).startswith(b'%PDF-1.4'))

    def test_existing_export_schema_originals_and_local_metadata_fts(self):
        document, source = self.upload()
        keywords = MetadataType.objects.create(name='Keywords')
        tag = Metadata.objects.create(type=keywords, name='synthetic')
        document.metadata.add(tag)
        self.version.metadata_types.add(keywords)
        logo = LibLayoutImage.objects.create(image_group=1)
        logo.image_file.save('synthetic-logo.png', ContentFile(b'synthetic test logo'))
        banner = LibLayoutImage.objects.create(image_group=2)
        banner.image_file.save('synthetic-banner.png', ContentFile(b'synthetic test banner'))
        self.version.library_banner = banner
        self.version.save()
        for folder in (self.farming, self.water):
            folder.logo_img = logo
            folder.save()
            folder.library_content.add(document)
        response = self.client.get('/api/create_build/%s/' % self.version.id)
        self.assertEqual(response.status_code, 200, response.content)
        build = Path(self.temp.name, 'builds', self.version.version_number)
        self.assertEqual(hashlib.sha256((build / 'content' / document.file_name).read_bytes()).digest(), hashlib.sha256(source).digest())
        with sqlite3.connect(build / 'solarspell.db') as database:
            self.assertEqual(database.execute('SELECT id FROM content').fetchall(), [(document.id,)])
            self.assertEqual(database.execute('SELECT id, folder_id FROM content_folder ORDER BY folder_id').fetchall(), [(document.id, self.farming.id), (document.id, self.water.id)])
            self.assertEqual(database.execute('SELECT id FROM metadata').fetchall(), [(tag.id,)])
            self.assertEqual(database.execute('SELECT copyright_notes, rights_statement FROM content').fetchone(), ('Original synthetic fixture by test contributors', 'CC0-1.0 (synthetic test fixture only)'))
            self.assertEqual(database.execute("SELECT rowid FROM content_fts WHERE content_fts MATCH 'synthetic'").fetchall(), [(document.id,)])
        self.assertTrue((build / 'assets' / 'config.json').is_file())


@override_settings(MIDDLEWARE=['dlms.preview_middleware.PrivatePreviewMiddleware'], OASIS_LOOPBACK_ONLY=True)
class PreviewAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @override_settings(OASIS_CURATOR_ENABLED=False, OASIS_SYNTHETIC_FIXTURES=False)
    def test_visitor_mode_config_and_all_mutation_routes(self):
        config = self.client.get('/api/oasis/config/').json()
        self.assertEqual(config, {'success': True, 'data': {'curator_enabled': False, 'synthetic_fixtures': False}, 'error': None})
        for method, path in (
            ('post', '/api/contents/'), ('post', '/api/content_bulk_add/'), ('patch', '/api/contents/1/'),
            ('delete', '/api/library_folders/1/'), ('post', '/api/library_folders/1/addcontent/'),
            ('get', '/api/create_build/1/'), ('head', '/api/create_build/1/'), ('get', '/api/library_versions/1/clone/'),
            ('get', '/api/library_versions/1/clone.json'), ('head', '/api/library_versions/1/clone.json'),
            ('get', '/api/library_versions/1/clone.json/'), ('head', '/api/library_versions/1/clone.api'),
            ('get', '/api/library_versions/+1/clone.json'), ('head', '/api/library_versions/+1/clone/'),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 403)

    @override_settings(OASIS_CURATOR_ENABLED=True, OASIS_SYNTHETIC_FIXTURES=True)
    def test_loopback_peers_only_and_forwarded_headers_do_not_grant_access(self):
        for peer in ('192.0.2.1', '10.0.0.12', '', 'invalid'):
            with self.subTest(peer=peer):
                self.assertEqual(self.client.get('/api/oasis/config/', REMOTE_ADDR=peer, HTTP_X_FORWARDED_FOR='127.0.0.1').status_code, 403)
        for peer in ('127.0.0.1', '::1'):
            response = self.client.get('/api/oasis/config/', REMOTE_ADDR=peer)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['data']['curator_enabled'])

    @override_settings(OASIS_LOOPBACK_ONLY=False, OASIS_CURATOR_ENABLED=True)
    def test_normal_settings_never_enable_remote_curator_mutations(self):
        # A normal reader origin may serve catalogue reads, but an enabled
        # development flag must never authorize a remote write.
        response = self.client.get('/api/oasis/config/', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='127.0.0.1')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['curator_enabled'])
        for method, path in (
            ('post', '/api/contents/'), ('get', '/api/create_build/1/'), ('get', '/api/library_versions/1/clone/'),
            ('get', '/api/library_versions/1/clone.json'), ('head', '/api/library_versions/1/clone.json'),
            ('get', '/api/library_versions/+1/clone.json'), ('head', '/api/library_versions/+1/clone/'),
        ):
            self.assertEqual(getattr(self.client, method)(path, REMOTE_ADDR='192.0.2.1').status_code, 403)
