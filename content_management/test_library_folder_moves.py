"""Tree mutation safety through the existing authenticated/preview API routes."""
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_management.models import Content, LibraryFolder, LibraryVersion


@override_settings(OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=False)
class LibraryFolderMoveTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.version = LibraryVersion.objects.create(library_name='Synthetic source', version_number='synthetic-source', created_on=timezone.now())
        self.target_version = LibraryVersion.objects.create(library_name='Synthetic destination', version_number='synthetic-destination', created_on=timezone.now())
        self.root = LibraryFolder.objects.create(folder_name='Synthetic farming', version=self.version)
        self.child = LibraryFolder.objects.create(folder_name='Synthetic soil', version=self.version, parent=self.root)
        self.deep = LibraryFolder.objects.create(folder_name='Synthetic compost', version=self.version, parent=self.child)
        self.target = LibraryFolder.objects.create(folder_name='Synthetic destination', version=self.target_version)
        self.document = Content.objects.create(title='Synthetic metadata-only move fixture', content_file='', modified_on=timezone.now())
        self.child.library_content.add(self.document)

    def transfer(self, action, source, **destination):
        query = '&'.join('%s=%s' % (name, value) for name, value in destination.items())
        return self.client.post('/api/library_folders/%s/%s/?%s' % (source.pk, action, query), {}, format='json')

    def tree(self):
        return list(LibraryFolder.objects.order_by('pk').values_list('pk', 'parent_id', 'version_id'))

    def test_move_and_copy_reject_self_and_descendants_without_changing_records(self):
        before = self.tree()
        for action in ('move_to', 'copy_to'):
            for target in (self.root, self.child, self.deep):
                with self.subTest(action=action, target=target.pk):
                    response = self.transfer(action, self.root, dest_folder=target.pk)
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json()['success'])
                    self.assertEqual(self.tree(), before)
                    self.assertEqual(list(self.child.library_content.values_list('pk', flat=True)), [self.document.pk])

    def test_missing_unknown_and_malformed_destinations_fail_before_any_mutation(self):
        before = self.tree()
        for action in ('move_to', 'copy_to'):
            for destination in ({}, {'dest_folder': 99999}, {'dest_folder': 'invalid'},
                                {'dest_version': 99999}, {'dest_version': 'invalid'}):
                with self.subTest(action=action, destination=destination):
                    response = self.transfer(action, self.root, **destination)
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json()['success'])
                    self.assertEqual(self.tree(), before)

    def test_valid_move_retains_ids_and_membership_and_updates_every_descendant_version(self):
        response = self.transfer('move_to', self.root, dest_folder=self.target.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.root.refresh_from_db()
        self.assertEqual(self.root.parent_id, self.target.pk)
        self.assertEqual(set(LibraryFolder.objects.filter(pk__in=[self.root.pk, self.child.pk, self.deep.pk]).values_list('version_id', flat=True)), {self.target_version.pk})
        self.assertEqual(list(self.child.library_content.values_list('pk', flat=True)), [self.document.pk])
        self.assertEqual(LibraryFolder.objects.count(), 4)

    def test_valid_copy_creates_new_folder_ids_but_retains_original_document_and_tree(self):
        source_ids = {self.root.pk, self.child.pk, self.deep.pk}
        response = self.transfer('copy_to', self.root, dest_folder=self.target.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.root.refresh_from_db()
        self.assertIsNone(self.root.parent_id)
        copied = LibraryFolder.objects.exclude(pk__in=source_ids | {self.target.pk})
        self.assertEqual(copied.count(), 3)
        self.assertEqual(set(copied.values_list('version_id', flat=True)), {self.target_version.pk})
        copied_child = copied.get(folder_name=self.child.folder_name)
        self.assertEqual(list(copied_child.library_content.values_list('pk', flat=True)), [self.document.pk])
        self.assertEqual(list(self.child.library_content.values_list('pk', flat=True)), [self.document.pk])
        self.assertEqual(Content.objects.count(), 1)

    def test_valid_move_to_catalogue_root_keeps_the_entire_subtree(self):
        response = self.transfer('move_to', self.child, dest_version=self.target_version.pk)
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.deep.refresh_from_db()
        self.assertIsNone(self.child.parent_id)
        self.assertEqual(self.child.version_id, self.target_version.pk)
        self.assertEqual(self.deep.parent_id, self.child.pk)
        self.assertEqual(self.deep.version_id, self.target_version.pk)
