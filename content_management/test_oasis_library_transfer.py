"""Portable library bundles: attribution, additive import and unsafe archive denial."""
import copy
import hashlib
import io
import json
import os
import stat
import struct
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata, MetadataType, OasisIndexJob
from content_management.oasis_indexing import validate_export_sources
from content_management.oasis_library_transfer import InspectedBundle, apply_bundle, export_library
from content_management.utils import LibraryBuildUtil


MIDDLEWARE = [
    'dlms.preview_middleware.PrivatePreviewMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]


def zipped(manifest, originals, *, extra=None, raw_manifest=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', raw_manifest if raw_manifest is not None else json.dumps(manifest).encode())
        for name, value in originals.items():
            archive.writestr(name, value)
        for name, value in extra or []:
            archive.writestr(name, value)
    return output.getvalue()


@override_settings(ROOT_URLCONF='content_management.urls', MIDDLEWARE=MIDDLEWARE,
                   ALLOWED_HOSTS=['testserver'], OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=True,
                   OASIS_REQUIRE_CURATOR_AUTH=False)
class OasisLibraryTransferTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.media = Path(self.temp.name).resolve() / 'media'
        self.contents = self.media / 'contents'
        self.contents.mkdir(parents=True)
        self.settings = override_settings(MEDIA_ROOT=str(self.media), CONTENTS_ROOT=str(self.contents))
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.staff = get_user_model().objects.create_user('synthetic-transfer-admin', is_staff=True)
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.staff)
        self.version = LibraryVersion.objects.create(library_name='Synthetic source', version_number='synthetic-source', created_on=timezone.now())
        self.target = LibraryVersion.objects.create(library_name='Synthetic main catalogue', version_number='synthetic-target', created_on=timezone.now())
        self.library = LibraryFolder.objects.create(folder_name='Synthetic Farming', version=self.version)
        self.section = LibraryFolder.objects.create(folder_name='Synthetic crops', version=self.version, parent=self.library)
        self.first = self.document('first-fixture.pdf', 'Synthetic crops document')
        self.second = self.document('second-fixture.pdf', 'Synthetic soil document')
        self.library.library_content.add(self.first)
        self.section.library_content.add(self.first, self.second)
        for kind, value in [('Author', 'Synthetic fixture author'), ('Source', 'https://example.invalid/synthetic-original'),
                            ('Licence', 'CC0 synthetic fixture only')]:
            category = MetadataType.objects.create(name=kind)
            item = Metadata.objects.create(type=category, name=value)
            self.first.metadata.add(item)
        self.other = LibraryFolder.objects.create(folder_name='Synthetic Water', version=self.target)
        self.sentinel = self.document('sentinel-fixture.pdf', 'Existing target document')
        self.other.library_content.add(self.sentinel)
        self.url = '/api/oasis/libraries/import/'
        self.export_url = '/api/oasis/libraries/' + str(self.library.pk) + '/bundle/'
        response = self.client.get(self.export_url)
        self.assertEqual(response.status_code, 200)
        self.bundle_bytes = b''.join(response.streaming_content)
        response.close()
        with zipfile.ZipFile(io.BytesIO(self.bundle_bytes)) as archive:
            self.manifest = json.loads(archive.read('manifest.json'))
            self.originals = {name: archive.read(name) for name in archive.namelist() if name != 'manifest.json'}
        self.original_rows = list(Content.objects.values())
        self.original_files = {path.name: path.read_bytes() for path in self.contents.iterdir()}

    def document(self, filename, title):
        document = Content.objects.create(title=title, display_title=title + ' display', description='Synthetic description',
            copyright_notes='Synthetic original attribution', rights_statement='CC0 synthetic fixture only',
            additional_notes='Testing only; no technical-advice approval.', published_date='2020-05-06', reviewed_on='2026-10-08',
            modified_on=timezone.now().replace(microsecond=0), active=True, duplicatable=False)
        document.content_file.save(filename, ContentFile(sample_pdf(title)), save=True)
        document.file_name = filename
        document.filesize = document.content_file.size
        document.save(update_fields=['file_name', 'filesize'])
        return document

    def token(self):
        return self.client.get('/api/get_csrf/').json()['data']

    def request_import(self, value=None, *, dry_run=False, **fields):
        data = {'bundle': SimpleUploadedFile('synthetic-library.zip', self.bundle_bytes if value is None else value, content_type='application/zip'),
                'catalogue_version': str(self.target.pk), **fields}
        return self.client.post(self.url + ('?dry_run=1' if dry_run else ''), data, format='multipart', HTTP_X_CSRFTOKEN=self.token())

    def commit(self, value=None, **fields):
        raw = self.bundle_bytes if value is None else value
        return self.request_import(raw, confirmed='true', expected_sha256=hashlib.sha256(raw).hexdigest(), **fields)

    def assert_existing_unchanged(self):
        for row in self.original_rows:
            self.assertEqual(Content.objects.values().get(pk=row['id']), row)
        for name, value in self.original_files.items():
            self.assertEqual((self.contents / name).read_bytes(), value)
        self.assertEqual(set(self.other.library_content.values_list('pk', flat=True)), {self.sentinel.pk})
        self.assertEqual(OasisIndexJob.objects.count(), 0)

    def test_export_has_exact_library_closure_attribution_and_stream_cleanup(self):
        self.assertEqual({folder['source_id'] for folder in self.manifest['folders']}, {self.library.pk, self.section.pk})
        self.assertEqual({document['source_id'] for document in self.manifest['documents']}, {self.first.pk, self.second.pk})
        first = next(document for document in self.manifest['documents'] if document['source_id'] == self.first.pk)
        self.assertEqual(first['fields']['rights_statement'], self.first.rights_statement)
        self.assertEqual(first['fields']['reviewed_on'], '2026-10-08')
        self.assertEqual({(value['type'], value['name']) for value in first['metadata']},
            {('Author', 'Synthetic fixture author'), ('Source', 'https://example.invalid/synthetic-original'), ('Licence', 'CC0 synthetic fixture only')})
        self.assertNotIn('approved', first)
        response = self.client.get(self.export_url)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['Referrer-Policy'], 'same-origin')
        response.close()
        response = export_library(self.library)
        stream = response.file_to_stream
        self.assertFalse(stream.closed)
        self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
        response.close()
        self.assertTrue(stream.closed)

    def test_inspection_is_read_only_and_reports_name_conflict(self):
        count = (Content.objects.count(), LibraryFolder.objects.count(), Metadata.objects.count())
        response = self.request_import(dry_run=True, library_name=self.other.folder_name)
        self.assertEqual(response.status_code, 200)
        plan = response.json()['data']
        self.assertEqual((plan['document_count'], plan['section_count']), (2, 1))
        self.assertTrue(plan['dry_run'] and plan['name_conflict'])
        self.assertFalse(plan['can_import'])
        self.assertEqual(plan['source_library_name'], self.library.folder_name)
        self.assertEqual(plan['bundle_sha256'], hashlib.sha256(self.bundle_bytes).hexdigest())
        self.assertEqual((Content.objects.count(), LibraryFolder.objects.count(), Metadata.objects.count()), count)
        self.assertEqual({path.name: path.read_bytes() for path in self.contents.iterdir()}, self.original_files)

    def test_apply_creates_fresh_ids_memberships_and_preserves_source_values(self):
        response = self.commit(library_name='Synthetic imported farming')
        self.assertEqual(response.status_code, 201, response.content)
        result = response.json()['data']
        imported = LibraryFolder.objects.get(pk=result['library']['id'])
        self.assertEqual(imported.version_id, self.target.pk)
        self.assertIsNone(imported.parent_id)
        self.assertEqual(imported.folder_name, 'Synthetic imported farming')
        child = imported.subfolders.get()
        self.assertEqual(child.folder_name, self.section.folder_name)
        documents = Content.objects.filter(pk__in=result['document_ids'])
        self.assertEqual(documents.count(), 2)
        self.assertFalse(set(result['document_ids']) & {self.first.pk, self.second.pk, self.sentinel.pk})
        first = documents.get(title=self.first.title)
        second = documents.get(title=self.second.title)
        self.assertEqual(set(imported.library_content.values_list('pk', flat=True)), {first.pk})
        self.assertEqual(set(child.library_content.values_list('pk', flat=True)), {first.pk, second.pk})
        self.first.refresh_from_db()
        for name in ['title', 'display_title', 'description', 'copyright_notes', 'rights_statement', 'additional_notes',
                     'published_date', 'reviewed_on', 'modified_on', 'active', 'duplicatable']:
            self.assertEqual(getattr(first, name), getattr(self.first, name), name)
        original_values = {(item.type.name, item.name) for item in self.first.metadata.select_related('type')}
        new_values = {(item.type.name, item.name) for item in first.metadata.select_related('type')}
        self.assertTrue(original_values <= new_values)
        self.assertIn(('Transfer original filename', self.first.file_name), new_values)
        self.assertEqual(Path(first.content_file.path), self.contents / first.file_name)
        self.assertEqual(Path(first.content_file.path).read_bytes(), Path(self.first.content_file.path).read_bytes())
        self.assertNotEqual(first.file_name, self.first.file_name)
        validate_export_sources(self.target)
        with override_settings(ROOT_URLCONF='dlms.device_urls'):
            response = self.client.get('/media/contents/' + first.file_name)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), Path(self.first.content_file.path).read_bytes())
            response.close()
        builds = Path(self.temp.name).resolve() / 'synthetic-legacy-builds'
        with override_settings(BUILDS_ROOT=str(builds)):
            result = LibraryBuildUtil(self.target.pk).build_library()
        self.assertEqual(result['result'], 'success', result)
        self.assertEqual((builds / self.target.version_number / 'content' / first.file_name).read_bytes(), Path(first.content_file.path).read_bytes())
        self.assert_existing_unchanged()
        # The resulting library itself is portable, with exactly the new IDs.
        roundtrip = self.client.get('/api/oasis/libraries/' + str(imported.pk) + '/bundle/')
        self.assertEqual(roundtrip.status_code, 200)
        raw = b''.join(roundtrip.streaming_content); roundtrip.close()
        response = self.request_import(raw, dry_run=True, library_name='Another synthetic copy')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['data']['document_count'], 2)

    def test_confirmation_hash_name_and_version_guards_prevent_writes(self):
        # Existing catalogue names can include whitespace; both inspection and
        # application must reject equivalent display names consistently.
        self.other.folder_name = '  Synthetic WaTER  '
        self.other.save(update_fields=['folder_name'])
        for name in ('Synthetic Water', '  sYnThEtIc water  '):
            with self.subTest(library_name=name):
                response = self.request_import(dry_run=True, library_name=name)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()['data']['name_conflict'])
                self.assertFalse(response.json()['data']['can_import'])
                self.assertEqual(self.commit(library_name=name).status_code, 400)
        attempts = [({}, self.target.pk), ({'confirmed': 'true', 'expected_sha256': '0' * 64}, self.target.pk),
                    ({'confirmed': 'true', 'expected_sha256': hashlib.sha256(self.bundle_bytes).hexdigest(), 'library_name': self.other.folder_name}, self.target.pk),
                    ({'confirmed': 'true', 'expected_sha256': hashlib.sha256(self.bundle_bytes).hexdigest(), 'library_name': ' '}, self.target.pk)]
        for fields, _ in attempts:
            with self.subTest(fields=fields):
                self.assertEqual(self.request_import(**fields).status_code, 400)
        self.assertEqual(self.request_import(catalogue_version='999999', dry_run=True).status_code, 400)
        self.assertEqual(Content.objects.count(), len(self.original_rows))
        self.assertEqual({path.name: path.read_bytes() for path in self.contents.iterdir()}, self.original_files)
        self.assert_existing_unchanged()

    def test_invalid_archive_and_manifest_shapes_are_rejected_before_writes(self):
        mutations = [lambda m: m.update(version=True), lambda m: m.update(format='other'),
            lambda m: m['library'].update(source_id=True), lambda m: m['folders'][1].update(parent_source_id=999999),
            lambda m: m['folders'][0].update(parent_source_id=m['folders'][1]['source_id']),
            lambda m: m['folders'][0].update(document_source_ids=[999999]),
            lambda m: m['documents'][0].update(source_id=True), lambda m: m['documents'][0].update(filename='../escape.pdf'),
            lambda m: m['documents'][0].update(member='other.pdf'), lambda m: m['documents'][0].update(size=True),
            lambda m: m['documents'][0].update(sha256='0' * 64), lambda m: m['documents'][0]['fields'].update(reviewed_on='2026-99-99'),
            lambda m: m['documents'][0]['fields'].update(active=1), lambda m: m['documents'][0]['fields'].update(unknown='unsafe')]
        for mutate in mutations:
            manifest = copy.deepcopy(self.manifest); mutate(manifest)
            with self.subTest(manifest=manifest):
                response = self.request_import(zipped(manifest, self.originals), dry_run=True)
                self.assertEqual(response.status_code, 400, response.content)
        for value in [b'not a zip', zipped(self.manifest, self.originals, extra=[('../escape.pdf', b'bad')]),
                      zipped(self.manifest, self.originals, extra=[('documents/unlisted.pdf', b'bad')]),
                      zipped(self.manifest, self.originals, raw_manifest=b'{"format":"first","format":"duplicate"}')]:
            self.assertEqual(self.request_import(value, dry_run=True).status_code, 400)
        self.assertEqual(Content.objects.count(), len(self.original_rows))
        self.assertEqual({path.name: path.read_bytes() for path in self.contents.iterdir()}, self.original_files)

    def test_duplicate_symlink_directory_and_corrupt_deflate_entries_rejected(self):
        link = zipfile.ZipInfo('documents/link.pdf'); link.external_attr = (stat.S_IFLNK | 0o777) << 16
        directory = zipfile.ZipInfo('documents/'); directory.external_attr = (stat.S_IFDIR | 0o700) << 16
        for extras in [[('manifest.json', b'duplicate')], [(link, b'target')], [(directory, b'')]]:
            self.assertEqual(self.request_import(zipped(self.manifest, self.originals, extra=extras), dry_run=True).status_code, 400)
        corrupt = bytearray(self.bundle_bytes)
        filename_length, extra_length = struct.unpack_from('<HH', corrupt, 26)
        corrupt[30 + filename_length + extra_length] = 0x07  # invalid DEFLATE block type
        self.assertEqual(self.request_import(bytes(corrupt), dry_run=True).status_code, 400)
        # NUL names are preserved in orig_filename but truncated in filename.
        malformed = self.bundle_bytes.replace(b'manifest.json', b'manifest\x00json')
        self.assertEqual(self.request_import(malformed, dry_run=True).status_code, 400)
        encrypted = bytearray(self.bundle_bytes)
        central = encrypted.find(b'PK\x01\x02')
        struct.pack_into('<H', encrypted, 6, struct.unpack_from('<H', encrypted, 6)[0] | 1)
        struct.pack_into('<H', encrypted, central + 8, struct.unpack_from('<H', encrypted, central + 8)[0] | 1)
        self.assertEqual(self.request_import(bytes(encrypted), dry_run=True).status_code, 400)
        self.assert_existing_unchanged()

    def test_metadata_budget_reserves_provenance_and_stays_roundtrippable(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['documents'][0]['metadata'] = [{'type': 'Synthetic keywords', 'name': 'Value ' + str(index)} for index in range(128)]
        self.assertEqual(self.request_import(zipped(manifest, self.originals), dry_run=True).status_code, 400)
        manifest['documents'][0]['metadata'].pop()
        response = self.commit(zipped(manifest, self.originals), library_name='Synthetic maximum metadata')
        self.assertEqual(response.status_code, 201, response.content)
        library_id = response.json()['data']['library']['id']
        exported = self.client.get('/api/oasis/libraries/' + str(library_id) + '/bundle/')
        self.assertEqual(exported.status_code, 200)
        raw = b''.join(exported.streaming_content); exported.close()
        self.assertEqual(self.request_import(raw, dry_run=True).status_code, 200)
        with patch('content_management.oasis_library_transfer.MAX_METADATA_VALUES', 5):
            response = self.commit(library_name='Synthetic aggregate metadata boundary')
            self.assertEqual(response.status_code, 201, response.content)
            exported = self.client.get('/api/oasis/libraries/' + str(response.json()['data']['library']['id']) + '/bundle/')
            self.assertEqual(exported.status_code, 200)
            raw = b''.join(exported.streaming_content); exported.close()
            self.assertEqual(self.request_import(raw, dry_run=True).status_code, 200)
        self.assert_existing_unchanged()

    def test_hash_pdf_signature_and_size_limits(self):
        originals = dict(self.originals)
        member = self.manifest['documents'][0]['member']
        originals[member] = b'not a PDF but ends %%EOF'
        manifest = copy.deepcopy(self.manifest)
        manifest['documents'][0]['size'] = len(originals[member])
        manifest['documents'][0]['sha256'] = hashlib.sha256(originals[member]).hexdigest()
        self.assertEqual(self.request_import(zipped(manifest, originals), dry_run=True).status_code, 400)
        for setting, value in [('MAX_ARCHIVE_BYTES', 10), ('MAX_PDF_BYTES', 10), ('MAX_EXPANDED_BYTES', 10),
                               ('MAX_MANIFEST_BYTES', 10), ('MAX_DOCUMENTS', 1), ('MAX_FOLDERS', 1)]:
            with self.subTest(setting=setting), patch('content_management.oasis_library_transfer.' + setting, value):
                self.assertEqual(self.request_import(dry_run=True).status_code, 400)
        with patch('content_management.oasis_library_transfer.MAX_ARCHIVE_BYTES', 10):
            self.assertEqual(self.client.get(self.export_url).status_code, 400)
        self.assert_existing_unchanged()

    @override_settings(OASIS_REQUIRE_CURATOR_AUTH=True)
    def test_staff_private_origin_and_csrf_controls(self):
        self.assertEqual(self.client.post(self.url, {}, format='multipart').status_code, 403)
        for headers in [{'HTTP_ORIGIN': 'https://outside.example'}, {'HTTP_SEC_FETCH_SITE': 'same-site'},
                        {'REMOTE_ADDR': '192.0.2.1', 'HTTP_X_FORWARDED_FOR': '127.0.0.1'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get(self.export_url, **headers).status_code, 403)
                self.assertEqual(self.client.post(self.url, {}, format='multipart', HTTP_X_CSRFTOKEN=self.token(), **headers).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.export_url).status_code, 403)
        self.assertEqual(self.request_import(dry_run=True).status_code, 403)
        for staff, active in [(False, True), (True, False)]:
            self.staff.is_staff = staff; self.staff.is_active = active; self.staff.save()
            self.client.force_login(self.staff)
            self.assertEqual(self.client.get(self.export_url).status_code, 403)
        self.assert_existing_unchanged()

    def test_anonymous_enabled_loopback_preview_can_transfer_with_csrf(self):
        self.client.logout()
        response = self.client.get(self.export_url)
        self.assertEqual(response.status_code, 200)
        downloaded = b''.join(response.streaming_content)
        response.close()
        with zipfile.ZipFile(io.BytesIO(downloaded)) as archive:
            self.assertEqual(archive.read('documents/' + str(self.first.pk) + '.pdf'), Path(self.first.content_file.path).read_bytes())
        upload = SimpleUploadedFile('synthetic-library.zip', self.bundle_bytes, content_type='application/zip')
        self.assertEqual(self.client.post(self.url + '?dry_run=1', {'bundle': upload, 'catalogue_version': str(self.target.pk)}, format='multipart').status_code, 403)
        response = self.request_import(dry_run=True)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Content.objects.count(), len(self.original_rows))
        response = self.commit(library_name='Synthetic anonymous preview import')
        self.assertEqual(response.status_code, 201, response.content)
        imported = LibraryFolder.objects.get(pk=response.json()['data']['library']['id'])
        self.assertEqual(imported.version_id, self.target.pk)
        self.assertEqual(Content.objects.count(), len(self.original_rows) + 2)
        self.assert_existing_unchanged()
        for headers in [{'HTTP_ORIGIN': 'https://outside.example'}, {'HTTP_SEC_FETCH_SITE': 'same-site'},
                        {'REMOTE_ADDR': '192.0.2.1', 'HTTP_X_FORWARDED_FOR': '127.0.0.1'}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get(self.export_url, **headers).status_code, 403)
                self.assertEqual(self.client.post(self.url, {}, format='multipart', HTTP_X_CSRFTOKEN=self.token(), **headers).status_code, 403)
        with override_settings(OASIS_CURATOR_ENABLED=False):
            self.assertEqual(self.client.get(self.export_url).status_code, 403)
            self.assertEqual(self.request_import(dry_run=True).status_code, 403)

    def test_unexpected_multipart_duplicates_and_json_are_honest_errors(self):
        self.assertEqual(self.client.post(self.url, {}, format='json', HTTP_X_CSRFTOKEN=self.token()).status_code, 415)
        self.assertEqual(self.request_import(dry_run=True, unsupported='value').status_code, 400)
        self.assertEqual(self.request_import(dry_run=True, catalogue_version=[str(self.target.pk), str(self.target.pk)]).status_code, 400)
        self.assertEqual(self.client.post(self.url + '?dry_run=1&dry_run=1', {}, format='multipart', HTTP_X_CSRFTOKEN=self.token()).status_code, 400)
        self.assert_existing_unchanged()

    def test_rollback_removes_partial_new_files_and_preserves_every_existing_record(self):
        bundle = InspectedBundle(SimpleUploadedFile('fixture.zip', self.bundle_bytes))
        try:
            def interrupted(original, target, length):
                target.write(original.read(10))
                raise KeyboardInterrupt()
            with patch('content_management.oasis_library_transfer.shutil.copyfileobj', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                apply_bundle(bundle, self.target, 'Synthetic interrupted import')
            self.assertFalse(LibraryFolder.objects.filter(folder_name='Synthetic interrupted import').exists())
            self.assertEqual({path.name: path.read_bytes() for path in self.contents.iterdir()}, self.original_files)
            with patch('content_management.oasis_library_transfer.Content.objects.create', side_effect=ValueError('Synthetic database failure')):
                with self.assertRaisesMessage(ValueError, 'Synthetic database failure'):
                    apply_bundle(bundle, self.target, 'Synthetic database failure')
            self.assertEqual({path.name: path.read_bytes() for path in self.contents.iterdir()}, self.original_files)
            self.assertEqual(Content.objects.count(), len(self.original_rows))
            self.assert_existing_unchanged()
        finally:
            bundle.close()

    def test_unicode_filename_fits_flat_filesystem_and_source_filename_is_retained(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['documents'][0]['filename'] = '水' * 80 + '.pdf'
        response = self.commit(zipped(manifest, self.originals), library_name='Synthetic unicode originals')
        self.assertEqual(response.status_code, 201, response.content)
        imported = Content.objects.get(pk=response.json()['data']['document_ids'][0])
        self.assertLessEqual(len(imported.file_name.encode('utf-8')), 255)
        self.assertTrue(imported.metadata.filter(type__name='Transfer original filename', name='水' * 80 + '.pdf').exists())
        validate_export_sources(self.target)

    def test_export_refuses_section_missing_original_symlink_and_uses_safe_download_name(self):
        self.assertEqual(self.client.get('/api/oasis/libraries/' + str(self.section.pk) + '/bundle/').status_code, 400)
        empty = LibraryFolder.objects.create(folder_name='!!!', version=self.target)
        response = self.client.get('/api/oasis/libraries/' + str(empty.pk) + '/bundle/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('oasis-library.zip', response['Content-Disposition'])
        response.close()
        original = Path(self.first.content_file.path); original.unlink()
        self.assertEqual(self.client.get(self.export_url).status_code, 400)
        original.symlink_to(self.sentinel.content_file.path)
        self.assertEqual(self.client.get(self.export_url).status_code, 400)
