"""Protect API IDs/export contracts and the isolated preview access boundary."""
import hashlib
import json
import sqlite3
import tempfile
from types import ModuleType
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import include, path
from django.views.static import serve
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibLayoutImage, LibraryFolder, LibraryVersion, Metadata, MetadataType
from content_management.oasis_documents import OasisDocumentSerializer


class CatalogueContractTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
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

    @override_settings(OASIS_LOOPBACK_ONLY=False, OASIS_CURATOR_ENABLED=False)
    def test_modern_document_management_is_private_in_visitor_mode(self):
        for method, path in (
            ('get', '/api/oasis/documents/'), ('get', '/api/oasis/documents/1/'),
            ('post', '/api/oasis/documents/'), ('patch', '/api/oasis/documents/1/'),
            ('delete', '/api/oasis/documents/1/'),
        ):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(path).status_code, 403)

    @override_settings(OASIS_LOOPBACK_ONLY=False, OASIS_CURATOR_ENABLED=True)
    def test_modern_management_reads_and_writes_deny_remote_peers(self):
        for method in ('get', 'post', 'patch', 'delete'):
            response = getattr(self.client, method)('/api/oasis/documents/', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='127.0.0.1')
            self.assertEqual(response.status_code, 403)


class OasisDocumentLifecycleTests(TestCase):
    def setUp(self):
        CatalogueContractTests.setUp(self)
        self.source_bytes = sample_pdf('Original synthetic management fixture')
        self.replacement_bytes = sample_pdf('Replacement synthetic management fixture')
        self.other_version = LibraryVersion.objects.create(library_name='Other synthetic catalogue', version_number='other-synthetic-v1')
        self.other_folder = LibraryFolder.objects.create(folder_name='Learning', version=self.other_version)
        # Created after the version, exercising its existing export whitelist.
        self.creator_type = MetadataType.objects.create(name='Creator')
        self.source_type = MetadataType.objects.create(name='Source')
        self.creator = Metadata.objects.create(type=self.creator_type, name='Synthetic fixture author')
        self.source = Metadata.objects.create(type=self.source_type, name='https://example.invalid/synthetic-original')

    def upload_document(self):
        response = self.client.post('/api/oasis/documents/', {
            'title': 'Synthetic managed document', 'display_title': 'Synthetic managed document',
            'description': 'Synthetic lifecycle fixture; no technical advice.',
            'copyright_notes': 'Original synthetic test document attribution',
            'rights_statement': 'CC0-1.0 (synthetic test fixture only)',
            'content_file': ContentFile(self.source_bytes, name='synthetic-managed.pdf'),
            'catalogue_version': str(self.version.id),
            'folder_ids': '[%s,%s]' % (self.farming.id, self.water.id),
            'metadata': '[%s,%s]' % (self.creator.id, self.source.id),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(sorted(payload['data']['metadata']), [self.creator.id, self.source.id])
        self.assertNotIn('folder_ids', payload['data'])
        self.assertNotIn('catalogue_version', payload['data'])
        return Content.objects.get(pk=payload['data']['id'])

    def test_create_list_detail_replacement_and_delete_preserve_contracts(self):
        document = self.upload_document()
        self.other_folder.library_content.add(document)
        previous_name = document.content_file.name
        previous_path = Path(document.content_file.path)
        previous_modified = document.modified_on
        for path in ('/api/oasis/documents/', '/api/oasis/documents/?catalogue_version=%s' % self.version.id):
            listing = self.client.get(path).json()['data']
            self.assertEqual(listing['count'], 1)
            self.assertEqual(listing['results'][0]['id'], document.id)
            self.assertEqual(sorted(listing['results'][0]['metadata']), [self.creator.id, self.source.id])
        detail = self.client.get('/api/oasis/documents/%s/' % document.id).json()['data']
        self.assertEqual(detail['id'], document.id)
        self.assertEqual(sorted(detail['metadata']), [self.creator.id, self.source.id])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch('/api/oasis/documents/%s/' % document.id, {
                'title': 'Updated synthetic document',
                'content_file': ContentFile(self.replacement_bytes, name='synthetic-managed.pdf'),
                'catalogue_version': str(self.version.id), 'folder_ids': '[%s]' % self.water.id,
                'metadata': '[]',
            }, format='multipart')
            self.assertEqual(response.status_code, 200, response.content)
            # Replacement must never destroy the previous original before commit.
            self.assertTrue(previous_path.exists())
        document.refresh_from_db()
        self.assertEqual(response.json()['data']['id'], document.id)
        self.assertNotEqual(document.content_file.name, previous_name)
        self.assertEqual(document.file_name, Path(document.content_file.name).name)
        self.assertGreater(document.modified_on, previous_modified)
        self.assertEqual(document.filesize, len(self.replacement_bytes))
        self.assertEqual(Path(document.content_file.path).read_bytes(), self.replacement_bytes)
        self.assertFalse(previous_path.exists())
        self.assertEqual(set(document.libraryfolder_set.values_list('id', flat=True)), {self.water.id, self.other_folder.id})
        self.assertEqual(document.metadata.count(), 0)
        self.assertEqual(document.rights_statement, 'CC0-1.0 (synthetic test fixture only)')
        current_path = Path(document.content_file.path)
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete('/api/oasis/documents/%s/' % document.id)
            self.assertEqual(deleted.status_code, 200)
            self.assertTrue(deleted.json()['success'])
            self.assertTrue(current_path.exists())
        self.assertFalse(current_path.exists())
        self.assertFalse(Content.objects.filter(pk=document.id).exists())
        self.assertEqual(self.water.library_content.count(), 0)
        self.assertEqual(self.other_folder.library_content.count(), 0)

    def test_upload_requires_explicit_library_placement(self):
        for extra in ({}, {'catalogue_version': self.version.id, 'folder_ids': []}):
            with self.subTest(extra=extra):
                response = self.client.post('/api/oasis/documents/', {
                    'title': 'Must remain unimported',
                    'content_file': ContentFile(self.source_bytes, name='unplaced.pdf'),
                    **extra,
                }, format='multipart')
                self.assertEqual(response.status_code, 400, response.content)
                self.assertFalse(Content.objects.filter(title='Must remain unimported').exists())

    def test_upload_into_nested_section_preserves_exact_folder_id(self):
        grain = LibraryFolder.objects.create(folder_name='Grain storage', parent=self.farming, version=self.version)
        maize = LibraryFolder.objects.create(folder_name='Maize', parent=grain, version=self.version)
        response = self.client.post('/api/oasis/documents/', {
            'title': 'Nested placement fixture', 'content_file': ContentFile(self.source_bytes, name='nested.pdf'),
            'catalogue_version': self.version.id, 'folder_ids': '[%s,%s]' % (maize.id, self.water.id),
        }, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        document = Content.objects.get(pk=response.json()['data']['id'])
        self.assertEqual(set(document.libraryfolder_set.values_list('id', flat=True)), {maize.id, self.water.id})

    def test_section_creation_rejects_other_version_parent_and_cycle(self):
        payload = {'folder_name': 'Invalid section', 'version': self.version.id, 'parent': self.other_folder.id}
        response = self.client.post('/api/library_folders/', payload, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        child = LibraryFolder.objects.create(folder_name='Child', parent=self.farming, version=self.version)
        response = self.client.patch('/api/library_folders/%s/' % self.farming.id, {'parent': child.id}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.farming.refresh_from_db()
        self.assertIsNone(self.farming.parent_id)

    def test_curator_batch_import_requires_and_saves_section_placement(self):
        section = LibraryFolder.objects.create(folder_name='Seed guidance', parent=self.farming, version=self.version)
        sources = Path(self.temp.name, 'batch-originals')
        sources.mkdir()
        (sources / 'batch.pdf').write_bytes(self.source_bytes)
        body = {
            'content_path': str(sources),
            'sheet_data': json.dumps([{'File Name': 'batch.pdf', 'Title': 'Placed batch fixture'}]),
        }
        missing = self.client.post('/api/content_bulk_add/', body, format='json')
        self.assertEqual(missing.status_code, 400, missing.content)
        self.assertFalse(Content.objects.filter(title='Placed batch fixture').exists())
        placed = self.client.post('/api/content_bulk_add/', {
            **body, 'catalogue_version': self.version.id, 'folder_ids': [section.id, self.water.id],
        }, format='json')
        self.assertEqual(placed.status_code, 200, placed.content)
        self.assertEqual(placed.json()['data']['success_count'], 1)
        document = Content.objects.get(title='Placed batch fixture')
        self.assertEqual(set(document.libraryfolder_set.values_list('id', flat=True)), {section.id, self.water.id})

    def test_empty_library_memberships_clear_only_selected_version(self):
        document = self.upload_document()
        self.other_folder.library_content.add(document)
        original_name = document.content_file.name
        response = self.client.patch('/api/oasis/documents/%s/' % document.id, {
            'catalogue_version': self.version.id, 'folder_ids': [], 'metadata': [],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        document.refresh_from_db()
        self.assertEqual(list(document.libraryfolder_set.values_list('id', flat=True)), [self.other_folder.id])
        self.assertEqual(document.content_file.name, original_name)
        self.assertEqual(document.metadata.count(), 0)
        self.assertEqual(self.client.get('/api/oasis/documents/?catalogue_version=%s' % self.version.id).json()['data']['count'], 0)

    def test_invalid_folder_scope_and_metadata_reject_without_side_effects(self):
        document = self.upload_document()
        original_name = document.content_file.name
        before_files = set(Path(self.temp.name, 'media', 'contents').iterdir())
        for extra in (
            {'catalogue_version': str(self.version.id), 'folder_ids': '[%s]' % self.other_folder.id},
            {'folder_ids': '[%s]' % self.water.id},
            {'metadata': '[999999]'},
            {'folder_ids': '{"invalid":1}', 'catalogue_version': str(self.version.id)},
        ):
            with self.subTest(extra=extra):
                payload = {'content_file': ContentFile(self.replacement_bytes, name='synthetic-managed.pdf'), 'title': 'Must not save'}
                payload.update(extra)
                response = self.client.patch('/api/oasis/documents/%s/' % document.id, payload, format='multipart')
                self.assertEqual(response.status_code, 400, response.content)
        document.refresh_from_db()
        self.assertEqual(document.title, 'Synthetic managed document')
        self.assertEqual(document.content_file.name, original_name)
        self.assertEqual(Path(document.content_file.path).read_bytes(), self.source_bytes)
        self.assertEqual(set(document.libraryfolder_set.values_list('id', flat=True)), {self.farming.id, self.water.id})
        self.assertEqual(set(Path(self.temp.name, 'media', 'contents').iterdir()), before_files)

    def test_membership_database_failure_rolls_back_new_file_and_record(self):
        document = self.upload_document()
        original_name = document.content_file.name
        original_modified = document.modified_on
        before_files = set(Path(self.temp.name, 'media', 'contents').iterdir())
        serializer = OasisDocumentSerializer(document, data={
            'title': 'Must roll back', 'content_file': ContentFile(self.replacement_bytes, name='synthetic-managed.pdf'),
            'catalogue_version': self.version.id, 'folder_ids': [self.water.id], 'metadata': [],
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        with patch.object(type(self.water.library_content), 'add', side_effect=IntegrityError('Synthetic membership failure')):
            with self.assertRaises(IntegrityError):
                serializer.save()
        document.refresh_from_db()
        self.assertEqual(document.title, 'Synthetic managed document')
        self.assertEqual(document.content_file.name, original_name)
        self.assertEqual(document.modified_on, original_modified)
        self.assertEqual(set(document.libraryfolder_set.values_list('id', flat=True)), {self.farming.id, self.water.id})
        self.assertEqual(set(document.metadata.values_list('id', flat=True)), {self.creator.id, self.source.id})
        self.assertEqual(set(Path(self.temp.name, 'media', 'contents').iterdir()), before_files)
        self.assertEqual(Path(document.content_file.path).read_bytes(), self.source_bytes)

    def test_delete_rollback_keeps_original_and_memberships(self):
        document = self.upload_document()
        original_path = Path(document.content_file.path)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                response = self.client.delete('/api/oasis/documents/%s/' % document.id)
                self.assertEqual(response.status_code, 200)
                raise RuntimeError('Synthetic transaction rollback')
        self.assertTrue(Content.objects.filter(pk=document.id).exists())
        self.assertTrue(original_path.exists())
        self.assertEqual(self.farming.library_content.count(), 1)
        self.assertEqual(self.water.library_content.count(), 1)

    def test_cleanup_failure_never_deletes_committed_replacement(self):
        document = self.upload_document()
        previous_path = Path(document.content_file.path)
        storage = document.content_file.storage
        with self.assertLogs('content_management.file_lifecycle', level='ERROR'):
            with patch.object(storage, 'delete', side_effect=OSError('Synthetic cleanup failure')):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.patch('/api/oasis/documents/%s/' % document.id, {
                        'content_file': ContentFile(self.replacement_bytes, name='synthetic-managed.pdf'),
                    }, format='multipart')
                    self.assertEqual(response.status_code, 200, response.content)
        document.refresh_from_db()
        self.assertTrue(previous_path.exists())
        self.assertNotEqual(Path(document.content_file.path), previous_path)
        self.assertEqual(Path(document.content_file.path).read_bytes(), self.replacement_bytes)

    def test_no_asset_export_preserves_new_metadata_and_replacement_original(self):
        self.assertIsNone(self.version.library_banner)
        self.assertIsNone(self.farming.logo_img)
        document = self.upload_document()
        self.assertEqual(set(self.version.metadata_types.values_list('id', flat=True)), {self.creator_type.id, self.source_type.id})
        exported = self.client.get('/api/create_build/%s/' % self.version.id)
        self.assertEqual(exported.status_code, 200, exported.content)
        builds_root = Path(self.temp.name, 'builds')
        original_build = builds_root / self.version.version_number
        self.assertEqual((original_build / 'content' / document.file_name).read_bytes(), self.source_bytes)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch('/api/oasis/documents/%s/' % document.id, {
                'content_file': ContentFile(self.replacement_bytes, name='synthetic-managed.pdf'),
            }, format='multipart')
            self.assertEqual(response.status_code, 200, response.content)
        document.refresh_from_db()
        # A source edit does not silently rewrite an existing exported snapshot.
        self.assertEqual((original_build / 'content' / 'synthetic-managed.pdf').read_bytes(), self.source_bytes)
        rebuilt = self.client.get('/api/create_build/%s/' % self.version.id)
        self.assertEqual(rebuilt.status_code, 200, rebuilt.content)
        new_build = next(path for path in builds_root.iterdir() if path != original_build)
        self.assertEqual((new_build / 'content' / document.file_name).read_bytes(), self.replacement_bytes)
        with sqlite3.connect(new_build / 'solarspell.db') as database:
            self.assertEqual(database.execute('SELECT id, file_name FROM content').fetchall(), [(document.id, document.file_name)])
            self.assertEqual(database.execute('SELECT id, folder_id FROM content_folder ORDER BY folder_id').fetchall(), [(document.id, self.farming.id), (document.id, self.water.id)])
            self.assertEqual(set(database.execute('SELECT meta_name FROM metadata').fetchall()), {('Synthetic fixture author',), ('https://example.invalid/synthetic-original',)})
            self.assertEqual(database.execute('SELECT copyright_notes, rights_statement FROM content').fetchone(), ('Original synthetic test document attribution', 'CC0-1.0 (synthetic test fixture only)'))
