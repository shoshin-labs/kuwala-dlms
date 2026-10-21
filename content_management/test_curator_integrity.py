"""Regressions for authoring data loss, spreadsheet flags and legacy exports."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata, MetadataType


class CuratorIntegrityTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.originals = self.root / 'media' / 'contents'
        self.originals.mkdir(parents=True)
        override = override_settings(MEDIA_ROOT=str(self.root / 'media'),
            CONTENTS_ROOT=str(self.originals), BUILDS_ROOT=str(self.root / 'builds'),
            OASIS_CURATOR_ENABLED=True, ROOT_URLCONF='dlms.urls')
        override.enable()
        self.addCleanup(override.disable)
        self.client = APIClient()
        self.version = LibraryVersion.objects.create(library_name='Review fixtures', version_number='safe-v1')
        self.folder = LibraryFolder.objects.create(version=self.version, folder_name='Farming')
        self.kind = MetadataType.objects.create(name='Keywords')
        self.tag = Metadata.objects.create(type=self.kind, name='original metadata')
        self.source = sample_pdf('Curator integrity synthetic fixture')
        self.document = Content(title='Existing original', display_title='Original title',
            description='Original description', active=True, duplicatable=True, copyright_notes='Original credit')
        self.document.content_file.save('original.pdf', ContentFile(self.source))
        self.document.metadata.add(self.tag)
        self.folder.library_content.add(self.document)

    def spreadsheet(self, rows, **extra):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/content_bulk_add/',
                {'sheet_data': json.dumps(rows), **extra}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def assert_original_preserved(self):
        self.document.refresh_from_db()
        self.assertEqual(self.document.description, 'Original description')
        self.assertEqual(self.document.display_title, 'Original title')
        self.assertEqual(set(self.document.metadata.values_list('pk', flat=True)), {self.tag.pk})
        self.assertEqual(set(self.document.libraryfolder_set.values_list('pk', flat=True)), {self.folder.pk})
        self.assertEqual(Path(self.document.content_file.path).read_bytes(), self.source)

    def test_invalid_metadata_cell_preserves_existing_record_original_and_memberships(self):
        result = self.spreadsheet([{'Title': self.document.title, 'Keywords': 123,
            'Display Title': 'Must not replace', 'Description': 'Must not save'}])
        self.assertEqual(result['success_count'], 0)
        self.assertEqual(len(result['unsuccessful_uploads']), 1)
        self.assert_original_preserved()

    def test_failure_after_metadata_clear_rolls_back_the_complete_existing_row(self):
        with patch('content_management.utils.Metadata.objects.get_or_create', side_effect=RuntimeError('Fixture database failure')):
            result = self.spreadsheet([{'Title': self.document.title, 'Keywords': 'replacement',
                'Description': 'Must roll back'}])
        self.assertEqual(result['success_count'], 0)
        self.assert_original_preserved()

    def test_failed_row_does_not_prevent_a_later_valid_row(self):
        result = self.spreadsheet([{'Title': self.document.title, 'Keywords': 123},
            {'Title': self.document.title, 'Keywords': 'valid replacement', 'Description': 'Saved second row'}])
        self.assertEqual(result['success_count'], 1)
        self.assertEqual(len(result['unsuccessful_uploads']), 1)
        self.document.refresh_from_db()
        self.assertEqual(self.document.description, 'Saved second row')
        self.assertEqual(list(self.document.metadata.values_list('name', flat=True)), ['valid replacement'])
        self.assertEqual(Path(self.document.content_file.path).read_bytes(), self.source)

    def test_spreadsheet_false_updates_both_flags(self):
        result = self.spreadsheet([{'Title': self.document.title, 'Active': False, 'Duplicatable': False}])
        self.assertEqual(result['success_count'], 1)
        self.document.refresh_from_db()
        self.assertFalse(self.document.active)
        self.assertFalse(self.document.duplicatable)

    def test_blank_flags_leave_existing_values_unchanged(self):
        self.spreadsheet([{'Title': self.document.title, 'Active': '', 'Duplicatable': ''}])
        self.document.refresh_from_db()
        self.assertTrue(self.document.active)
        self.assertTrue(self.document.duplicatable)

    def test_false_flags_on_new_import_override_model_defaults(self):
        source = self.root / 'import'
        source.mkdir()
        (source / 'new.pdf').write_bytes(sample_pdf('Different synthetic import fixture'))
        result = self.spreadsheet([{'Title': 'Inactive import', 'File Name': 'new.pdf',
            'Active': False, 'Duplicatable': False}], content_path=str(source),
            catalogue_version=self.version.pk, folder_ids=[self.folder.pk])
        self.assertEqual(result['success_count'], 1)
        item = Content.objects.get(title='Inactive import')
        self.assertFalse(item.active)
        self.assertFalse(item.duplicatable)
        self.assertEqual(set(item.libraryfolder_set.values_list('pk', flat=True)), {self.folder.pk})

    def test_export_rejects_absolute_traversal_and_unsafe_version_paths_before_writes(self):
        escape = self.root / 'outside'
        for number in (str(escape), '../outside', '.', '..', 'bad/child', 'bad\\child', 'a' * 161):
            with self.subTest(number=number):
                self.version.version_number = number
                self.version.save()
                response = self.client.get('/api/create_build/%s/' % self.version.pk)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertFalse(escape.exists())
                self.assertFalse((self.root / 'builds').exists())

    def test_export_rejects_a_symlink_destination_and_root(self):
        target = self.root / 'outside'
        target.mkdir()
        builds = self.root / 'builds'
        builds.mkdir()
        (builds / self.version.version_number).symlink_to(target, target_is_directory=True)
        self.assertEqual(self.client.get('/api/create_build/%s/' % self.version.pk).status_code, 400)
        (builds / self.version.version_number).unlink()
        builds.rmdir()
        builds.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.client.get('/api/create_build/%s/' % self.version.pk).status_code, 400)
        self.assertEqual(list(target.iterdir()), [])

    def test_copyright_notes_filter_returns_matching_documents_and_an_empty_result(self):
        match = self.client.get('/api/contents/', {'copyright_notes': 'Original credit'})
        self.assertEqual(match.status_code, 200, match.content)
        self.assertEqual([item['id'] for item in match.json()['data']['results']], [self.document.pk])
        missing = self.client.get('/api/contents/', {'copyright_notes': 'unrelated'})
        self.assertEqual(missing.status_code, 200, missing.content)
        self.assertEqual(missing.json()['data']['results'], [])
