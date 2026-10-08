"""Adoption verifies actual copies and preserves the existing source snapshot."""
import copy
import hashlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from content_management.management.commands import adopt_oasis_index as adoption
from content_management.models import LibraryVersion, OasisIndexJob


COMMAND = 'content_management.management.commands.adopt_oasis_index.'


class AdoptOasisIndexTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / 'private-import'
        self.source.mkdir(mode=0o700)
        self.snapshot = self.source / 'v-existing'
        (self.snapshot / 'content').mkdir(parents=True)
        vectors = self.source / 'semantic' / self.snapshot.name / 'vectors.sqlite3'
        vectors.parent.mkdir(parents=True)
        vectors.write_bytes(b'verified existing vector fixture')
        (self.snapshot / 'index.sqlite3').write_bytes(b'verified existing passage fixture')
        (self.source / 'current').symlink_to(self.snapshot.name, target_is_directory=True)
        original = self.snapshot / 'content' / 'original.pdf'
        original.write_bytes(b'%PDF-1.4 original fixture')
        self.version = LibraryVersion.objects.create(library_name='Private authoring fixture', version_number='test-v6',
                                                     created_on=timezone.now())
        self.records = [{'document_id': 4, 'filename': original.name, 'sha256': adoption.file_digest(original)}]
        self.manifest = {'version': 1, 'library_version': self.version.version_number,
                         'usage_scope': 'private-development-testing',
                         'documents': [{'id': 'existing-pdf', 'dlms_id': 4, 'filename': original.name,
                                        'sha256': self.records[0]['sha256'], 'approved': True,
                                        'rights_notes': 'Original attribution and item-level exceptions.',
                                        'testing_only': True, 'rights_review_pending': True}],
                         'libraries': [{'id': 'learning', 'label': 'Learning', 'dlms_folder_id': 18,
                                        'document_ids': ['existing-pdf']}]}
        (self.snapshot / 'manifest.json').write_text(json.dumps(self.manifest))
        self.receipt = {'snapshot': self.snapshot.name,
                        'index_sha256': adoption.file_digest(self.snapshot / 'index.sqlite3'),
                        'vectors_sha256': adoption.file_digest(vectors),
                        'lexical_valid': True, 'vector_valid': True, 'vector_artifact_valid': True,
                        'vector_model_digest': 'a' * 64, 'model_digest': 'a' * 64,
                        'vector_state': 'indexed', 'vector_reason': None,
                        'documents': [{**self.records[0], 'page_count': 2, 'passage_count': 7}]}
        self.config = {'root': self.root / 'station', 'python': self.root / 'python',
                       'manifest': self.root / 'reviewed-manifest.json', 'model': 'existing-model',
                       'base_url': 'http://127.0.0.1:11434', 'dependency_path': ''}
        self.probe = {'manifest': self.manifest, 'model_digest': 'a' * 64, 'vector_available': True}
        settings = override_settings(BASE_DIR=self.root / 'code', MEDIA_ROOT=str(self.root / 'media'),
                                     BUILDS_ROOT=str(self.root / 'builds'),
                                     OASIS_INDEXING_STATE_ROOT=str(self.root / 'indexing'),
                                     OASIS_INDEXING_PROTECTED_ROOTS=(str(self.root / 'live'),))
        settings.enable()
        self.addCleanup(settings.disable)
        preflight = patch(COMMAND + 'preflight', side_effect=self.preflight)
        self.preflight_mock = preflight.start()
        self.addCleanup(preflight.stop)
        probe = patch(COMMAND + 'run_probe', side_effect=self.station_probe)
        self.probe_mock = probe.start()
        self.addCleanup(probe.stop)

    def preflight(self, version, profile):
        self.assertEqual(version.pk, self.version.pk)
        self.assertEqual(profile, 'hybrid')
        return copy.deepcopy((self.config, self.probe, self.records))

    def station_probe(self, config, *, root):
        self.assertEqual(config, self.config)
        return {'receipt': copy.deepcopy(self.receipt)}

    def command(self, *, apply=False, root=None):
        output = StringIO()
        call_command('adopt_oasis_index', root=str(root or self.source),
                     catalogue_version=self.version.pk, apply=apply, stdout=output)
        return output.getvalue()

    def assert_no_partial_job(self):
        self.assertFalse(OasisIndexJob.objects.exists())
        jobs = self.root / 'indexing' / 'jobs'
        self.assertFalse(jobs.exists() and list(jobs.iterdir()))

    def test_dry_run_is_read_only_and_validates_both_indexes(self):
        before = {str(p.relative_to(self.source)): p.read_bytes()
                  for p in self.source.rglob('*') if p.is_file()}
        self.assertIn('Dry run', self.command())
        self.assertFalse((self.root / 'indexing').exists())
        self.assert_no_partial_job()
        after = {str(p.relative_to(self.source)): p.read_bytes()
                 for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.probe_mock.assert_called_once()

    def test_apply_copies_only_required_artifacts_and_records_actual_receipt(self):
        (self.source / '.pdf-import-failed').mkdir()
        (self.source / '.pdf-import-failed' / 'ignored.lock').write_text('failed import')
        (self.snapshot / 'ignored-file').write_text('never adopt arbitrary files')
        self.assertIn('Adopted verified existing snapshot', self.command(apply=True))
        job = OasisIndexJob.objects.get()
        draft = adoption.job_root(job) / 'draft'
        self.assertEqual(job.state, 'succeeded')
        self.assertEqual(job.profile, 'hybrid')
        self.assertEqual(job.documents, self.records)
        self.assertEqual(job.manifest, self.manifest)
        self.assertEqual(job.manifest_sha256, adoption.manifest_digest(self.manifest))
        self.assertEqual(job.receipt, self.receipt)
        self.assertIn('Adopted verified existing snapshot', job.diagnostics)
        self.assertIn('no extraction, embedding or publication commands ran', job.diagnostics)
        self.assertIsNotNone(job.finished_on)
        self.assertEqual((draft / 'current').readlink(), Path(self.snapshot.name))
        for path in ('manifest.json', 'index.sqlite3', 'content/original.pdf'):
            self.assertEqual((draft / self.snapshot.name / path).read_bytes(), (self.snapshot / path).read_bytes())
        self.assertFalse((draft / '.pdf-import-failed').exists())
        self.assertFalse((draft / self.snapshot.name / 'ignored-file').exists())
        copied_vector = draft / 'semantic' / self.snapshot.name / 'vectors.sqlite3'
        self.assertEqual(adoption.file_digest(copied_vector), self.receipt['vectors_sha256'])
        self.assertEqual(copied_vector.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.probe_mock.call_count, 2)

    def test_repeat_verifies_existing_artifacts_without_creating_another_job(self):
        self.command(apply=True)
        job = OasisIndexJob.objects.get()
        created_on = job.created_on
        self.assertIn('Already verified', self.command(apply=True))
        self.assertEqual(OasisIndexJob.objects.count(), 1)
        self.assertEqual(OasisIndexJob.objects.get().created_on, created_on)
        self.assertEqual(len(list((self.root / 'indexing' / 'jobs').iterdir())), 1)
        self.assertEqual(self.probe_mock.call_count, 4)

    def test_full_manifest_rights_and_groups_must_match(self):
        for change in ('rights', 'group'):
            with self.subTest(change=change):
                changed = copy.deepcopy(self.manifest)
                if change == 'rights':
                    changed['documents'][0]['rights_notes'] = 'Changed rights'
                else:
                    changed['libraries'][0]['label'] = 'Changed group'
                (self.snapshot / 'manifest.json').write_text(json.dumps(changed))
                with self.assertRaisesMessage(CommandError, 'full reviewed manifest'):
                    self.command(apply=True)
                self.assert_no_partial_job()

    def test_incomplete_duplicate_or_wrong_receipt_documents_are_rejected(self):
        good = copy.deepcopy(self.receipt)
        cases = [[], [good['documents'][0], good['documents'][0]],
                 [{**good['documents'][0], 'sha256': 'b' * 64}],
                 [{**good['documents'][0], 'page_count': 0}],
                 [{**good['documents'][0], 'passage_count': 0}]]
        for documents in cases:
            with self.subTest(documents=documents):
                self.receipt = {**good, 'documents': documents}
                with self.assertRaises(CommandError):
                    self.command(apply=True)
                self.assert_no_partial_job()

    def test_invalid_vectors_or_installed_model_mismatch_are_rejected(self):
        good = copy.deepcopy(self.receipt)
        for changes in ({'vector_valid': False}, {'vector_artifact_valid': False},
                        {'vectors_sha256': None}, {'vector_model_digest': 'b' * 64},
                        {'model_digest': 'b' * 64}, {'lexical_valid': False}):
            with self.subTest(changes=changes):
                self.receipt = {**good, **changes}
                with self.assertRaises(CommandError):
                    self.command(apply=True)
                self.assert_no_partial_job()

    def test_escaping_current_and_symlinked_originals_are_rejected(self):
        current = self.source / 'current'
        current.unlink()
        current.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(CommandError):
            self.command(apply=True)
        current.unlink()
        current.symlink_to(self.snapshot.name, target_is_directory=True)
        original = self.snapshot / 'content' / 'original.pdf'
        outside = self.root / 'outside.pdf'
        original.replace(outside)
        original.symlink_to(outside)
        with self.assertRaisesMessage(CommandError, 'must not contain symlinks'):
            self.command(apply=True)
        self.assert_no_partial_job()

    def test_current_rejects_absolute_nested_and_unsafe_snapshot_targets(self):
        current = self.source / 'current'
        for target in (str(self.snapshot), 'nested/v-existing', 'nested/../v-existing', 'snapshot', 'v-'):
            with self.subTest(target=target):
                current.unlink()
                current.symlink_to(target, target_is_directory=True)
                with self.assertRaisesMessage(CommandError, 'safe relative v-* snapshot sibling'):
                    self.command(apply=True)
                self.assert_no_partial_job()

    def test_permissive_and_protected_source_roots_are_rejected(self):
        self.source.chmod(0o755)
        with self.assertRaisesMessage(CommandError, 'deny group/other access'):
            self.command(apply=True)
        self.source.chmod(0o700)
        with override_settings(OASIS_INDEXING_PROTECTED_ROOTS=(str(self.source),)):
            with self.assertRaisesMessage(CommandError, 'must not overlap'):
                self.command(apply=True)
        self.assert_no_partial_job()

    def test_copied_validation_failure_removes_partial_files_and_job(self):
        with patch(COMMAND + 'run_probe', side_effect=[{'receipt': copy.deepcopy(self.receipt)},
                                                     ValueError('Copied vectors failed station validation.')]):
            with self.assertRaisesMessage(CommandError, 'Copied vectors failed'):
                self.command(apply=True)
        self.assert_no_partial_job()
        self.assertTrue((self.source / 'current').is_symlink())

    def test_corrupt_copy_or_changed_source_hash_is_rejected_and_cleaned(self):
        original_copy = adoption.shutil.copyfile

        def corrupt_copy(source, target):
            original_copy(source, target)
            if source.name == 'index.sqlite3':
                target.write_bytes(b'corrupted copy')

        with patch(COMMAND + 'shutil.copyfile', side_effect=corrupt_copy):
            with self.assertRaisesMessage(CommandError, 'changed during its private copy'):
                self.command(apply=True)
        self.assert_no_partial_job()
        (self.snapshot / 'index.sqlite3').write_bytes(b'source changed after probe')
        with self.assertRaisesMessage(CommandError, 'source changed after validation'):
            self.command(apply=True)
        self.assert_no_partial_job()

    def test_catalogue_changed_during_adoption_is_rejected_and_cleaned(self):
        changed = copy.deepcopy(self.probe)
        changed['manifest']['documents'][0]['rights_notes'] = 'New review'
        with patch(COMMAND + 'preflight', side_effect=[(self.config, copy.deepcopy(self.probe), self.records),
                                                     (self.config, changed, self.records)]):
            with self.assertRaisesMessage(CommandError, 'changed during adoption'):
                self.command(apply=True)
        self.assert_no_partial_job()

    def test_queued_job_blocks_adoption_without_overwriting_it(self):
        queued = OasisIndexJob.objects.create(catalogue_version=self.version.pk, manifest_sha256='c' * 64)
        with self.assertRaisesMessage(CommandError, 'already queued or running'):
            self.command(apply=True)
        queued.refresh_from_db()
        self.assertEqual(queued.state, 'queued')
        self.assertEqual(OasisIndexJob.objects.count(), 1)
        self.assertFalse((self.root / 'indexing').exists())
