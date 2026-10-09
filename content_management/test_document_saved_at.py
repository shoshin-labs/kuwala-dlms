"""Retained document APIs report the server time of an actual record save."""
import tempfile
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata, MetadataType


UTC = datetime_timezone.utc
OLD = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
SAVED = datetime(2026, 10, 9, 9, 10, 11, tzinfo=UTC)


@override_settings(OASIS_CURATOR_ENABLED=True)
class DocumentSavedAtTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        (root / 'media/contents').mkdir(parents=True)
        self.settings_override = override_settings(MEDIA_ROOT=str(root / 'media'), CONTENTS_ROOT=str(root / 'media/contents'))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.client = APIClient()
        self.document = Content.objects.create(title='Synthetic saved-at fixture', modified_on=OLD)
        self.version = LibraryVersion.objects.create(library_name='Synthetic timestamp library', version_number='synthetic-date-v1')
        self.folder = LibraryFolder.objects.create(folder_name='Synthetic records', version=self.version)
        self.folder.library_content.add(self.document)
        metadata_type = MetadataType.objects.create(name='Synthetic date tags')
        self.before = Metadata.objects.create(type=metadata_type, name='Before')
        self.after = Metadata.objects.create(type=metadata_type, name='After')
        self.document.metadata.add(self.before)

    def test_legacy_patch_ignores_spoofed_timestamp_and_uses_server_utc(self):
        with patch('content_management.serializers.timezone.now', return_value=SAVED):
            response = self.client.patch('/api/contents/%s/' % self.document.id,
                                         {'title': 'Saved synthetic fixture', 'modified_on': '2099-01-01T00:00:00Z'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.modified_on, SAVED)
        self.assertEqual(response.json()['modified_on'], '2026-10-09T09:10:11Z')
        self.assertEqual(self.document.libraryfolder_set.get().pk, self.folder.pk)

    def test_legacy_creation_timestamp_is_aware_utc_and_client_value_is_ignored(self):
        with patch('content_management.serializers.timezone.now', return_value=SAVED):
            response = self.client.post('/api/contents/', {'title': 'Synthetic created-at fixture',
                                         'modified_on': '2000-01-01T00:00:00Z',
                                         'content_file': ContentFile(sample_pdf('Synthetic created-at fixture'), name='synthetic-created-at.pdf')},
                                        format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        document = Content.objects.get(pk=response.json()['id'])
        self.assertEqual(document.modified_on, SAVED)
        self.assertEqual(document.modified_on.utcoffset().total_seconds(), 0)
        self.assertEqual(response.json()['modified_on'], '2026-10-09T09:10:11Z')

    def test_legacy_file_replacement_advances_timestamp_without_changing_id_or_memberships(self):
        self.document.content_file.save('synthetic-original-date.pdf', ContentFile(sample_pdf('Synthetic original date')))
        replacement = sample_pdf('Synthetic replacement date')
        with patch('content_management.serializers.timezone.now', return_value=SAVED):
            response = self.client.patch('/api/contents/%s/' % self.document.id, {
                'modified_on': '2099-01-01T00:00:00Z',
                'content_file': ContentFile(replacement, name='synthetic-replacement-date.pdf'),
            }, format='multipart')
        self.assertEqual(response.status_code, 200, response.content)
        self.document.refresh_from_db()
        self.assertEqual(response.json()['id'], self.document.pk)
        self.assertEqual(self.document.modified_on, SAVED)
        self.assertEqual(Path(self.document.content_file.path).read_bytes(), replacement)
        self.assertEqual(list(self.document.libraryfolder_set.values_list('id', flat=True)), [self.folder.pk])

    def test_legacy_metadata_patch_and_bulk_remove_add_advance_record_timestamp(self):
        with patch('content_management.serializers.timezone.now', return_value=SAVED):
            response = self.client.patch('/api/contents/%s/' % self.document.id, {'metadata': [self.after.pk]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.modified_on, SAVED)
        self.assertEqual(list(self.document.metadata.values_list('id', flat=True)), [self.after.pk])
        later = datetime(2026, 10, 9, 9, 20, 11, tzinfo=UTC)
        with patch('content_management.views.timezone.now', return_value=later):
            response = self.client.post('/api/bulk_edit/', {'to_edit': [self.document.pk], 'to_remove': [self.after.pk],
                                                          'to_add': [self.before.pk], 'modified_on': '2099-01-01T00:00:00Z'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.modified_on, later)
        self.assertEqual(list(self.document.metadata.values_list('id', flat=True)), [self.before.pk])

    def test_noop_bulk_metadata_edit_does_not_claim_a_later_record_save(self):
        response = self.client.post('/api/bulk_edit/', {'to_edit': [self.document.pk], 'to_remove': [],
                                                      'to_add': [self.before.pk]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.modified_on, OLD)

    def test_rejected_legacy_patch_preserves_original_timestamp(self):
        with patch('content_management.serializers.timezone.now', return_value=SAVED):
            response = self.client.patch('/api/contents/%s/' % self.document.id, {'metadata': [999999],
                                         'modified_on': '2099-01-01T00:00:00Z'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.document.refresh_from_db()
        self.assertEqual(self.document.modified_on, OLD)
