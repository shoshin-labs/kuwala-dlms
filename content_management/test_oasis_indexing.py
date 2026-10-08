"""Private indexing lifecycle tests independent of a station installation."""
import copy
import hashlib
import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from content_management.management.commands.run_oasis_index_jobs import execute_job
from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibraryFolder, LibraryVersion, OasisIndexJob
from content_management.oasis_indexing import heartbeat, job_root, original_record, operator_config, verified_receipt, cached_artifact_receipt
from content_management import tests as contract_tests


class PrivateIndexingTests(TestCase):
    def setUp(self):
        contract_tests.CatalogueContractTests.setUp(self)
        self.root = Path(self.temp.name).resolve()
        self.private_settings = override_settings(BASE_DIR=self.root)
        self.private_settings.enable()
        self.addCleanup(self.private_settings.disable)
        station = self.root / 'station'
        (station / 'scripts').mkdir(parents=True)
        for filename in ('import_pdf_library.py', 'index_pdf_vectors.py'):
            (station / 'scripts' / filename).write_text('# Mocked existing maintenance entry point\n')
        self.manifest_path = self.root / 'reviewed.json'
        self.environment = patch.dict(os.environ, {
            'OASIS_INDEXING_STATION_ROOT': str(station), 'OASIS_INDEXING_PYTHON': sys.executable,
            'OASIS_INDEXING_MANIFEST': str(self.manifest_path),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.first = self.add_document('first.pdf', 'First synthetic original', self.farming)
        self.second = self.add_document('second.pdf', 'Second synthetic original', self.water)
        self.records = [original_record(document) for document in (self.first, self.second)]
        self.manifest = {'version': 1, 'library_version': self.version.version_number,
                         'documents': [{'dlms_id': record['document_id'], 'id': 'synthetic-%s' % record['document_id'],
                                        'filename': record['filename'], 'sha256': record['sha256']}
                                       for record in self.records]}
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.probe = {'manifest': self.manifest, 'lexical_available': True, 'vector_available': False,
                      'vector_blocked_reason': 'No installed local embedding model.'}
        self.probe_patch = patch('content_management.oasis_indexing.configuration_probe', side_effect=lambda config: copy.deepcopy(self.probe))
        self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)

    def add_document(self, filename, title, folder=None, *, active=True):
        document = Content.objects.create(title=title, display_title=title, active=active,
                                          copyright_notes='Synthetic test fixture only.')
        document.content_file.save(filename, ContentFile(sample_pdf(title)), save=True)
        document.file_name = filename
        document.filesize = document.content_file.size
        document.save(update_fields=['file_name', 'filesize'])
        if folder:
            folder.library_content.add(document)
        return document

    def post_job(self, **extra):
        return self.client.post('/api/oasis/index-jobs/', {'catalogue_version': self.version.id, **extra}, format='json')

    def test_original_limit_matches_station_eighty_mib_and_accepts_larger_existing_pdf(self):
        path = Path(self.first.content_file.path)
        with path.open('r+b') as stream:
            stream.truncate(40 * 1024 * 1024)
        record = original_record(self.first)
        self.assertEqual(record['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        with path.open('r+b') as stream:
            stream.truncate(80 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, '80 MiB'):
            original_record(self.first)

    def test_reviewed_library_names_and_memberships_are_required_without_export(self):
        self.probe['manifest']['libraries'] = [{
            'id': 'farming', 'label': self.farming.folder_name,
            'dlms_folder_id': self.farming.id, 'document_ids': ['synthetic-%s' % self.first.id],
        }]
        self.assertTrue(self.snapshot()['configuration']['configured'])
        self.farming.library_content.add(self.second)
        self.assertIn('memberships changed', self.snapshot()['configuration']['blocked_reason'])
        self.farming.library_content.remove(self.second)
        self.farming.folder_name = 'Renamed synthetic library'
        self.farming.save(update_fields=['folder_name'])
        self.assertIn('names or memberships changed', self.snapshot()['configuration']['blocked_reason'])
        self.assertEqual(self.post_job().status_code, 409)

    def snapshot(self):
        response = self.client.get('/api/oasis/indexing/?catalogue_version=%s' % self.version.id)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['data']

    def ready_job(self):
        receipt = {'documents': copy.deepcopy(self.records), 'index_sha256': 'a' * 64,
                   'vectors_sha256': None, 'lexical_valid': True, 'vector_valid': False,
                   'vector_state': 'not_indexed', 'vector_reason': 'No vectors built.'}
        job = OasisIndexJob.objects.create(catalogue_version=self.version.id, state='succeeded',
                                           documents=self.records, manifest=self.manifest, manifest_sha256='b' * 64,
                                           finished_on=timezone.now(), receipt=receipt)
        return job

    def test_missing_configuration_and_unreviewed_changes_are_blocked_not_queued(self):
        with patch.dict(os.environ, {'OASIS_INDEXING_STATION_ROOT': ''}):
            snapshot = self.snapshot()
            self.assertFalse(snapshot['configuration']['configured'])
            self.assertIn('reviewed manifest', snapshot['configuration']['blocked_reason'])
            response = self.post_job(document_id=self.first.id)
            self.assertEqual(response.status_code, 409)
        self.probe['manifest']['documents'].pop()
        response = self.post_job(document_id=self.first.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn('exactly every enabled PDF', response.json()['error']['blocked_reason'])
        self.assertEqual(OasisIndexJob.objects.count(), 0)

    def test_missing_station_release_is_reported_as_unavailable_without_queueing(self):
        with patch.dict(os.environ, {'OASIS_INDEXING_STATION_ROOT': str(self.root / 'missing-station-release')}):
            snapshot = self.snapshot()
            self.assertFalse(snapshot['configuration']['configured'])
            self.assertIn('station release root is unavailable', snapshot['configuration']['blocked_reason'])
            response = self.post_job(document_id=self.first.id)
            self.assertEqual(response.status_code, 409)
            self.assertIn('station release root is unavailable', response.json()['error']['blocked_reason'])
        self.assertFalse(OasisIndexJob.objects.exists())

    def test_maintenance_sentinel_leaves_queued_jobs_and_skips_commands(self):
        response = self.post_job(document_id=self.first.id)
        self.assertEqual(response.status_code, 201)
        job = OasisIndexJob.objects.get(pk=response.json()['data']['id'])
        base = job_root(job).parent.parent
        base.mkdir(parents=True, exist_ok=True)
        sentinel = base / 'maintenance.json'
        current_nonce = 'b' * 32
        sentinel.write_text(json.dumps({'nonce': current_nonce}))
        heartbeat(maintenance=True, maintenance_nonce='a' * 32)
        with patch('content_management.management.commands.run_oasis_index_jobs.execute_job') as execute, \
             patch('content_management.management.commands.run_oasis_index_jobs.heartbeat', wraps=heartbeat) as reported:
            call_command('run_oasis_index_jobs', once=True, stdout=StringIO())
            execute.assert_not_called()
            self.assertEqual(reported.call_args_list[0].kwargs, {'maintenance': True, 'maintenance_nonce': current_nonce})
        job.refresh_from_db()
        self.assertEqual(job.state, 'queued')
        self.assertFalse(job_root(job).exists())
        response = self.post_job(document_id=self.first.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn('paused', response.json()['error']['blocked_reason'])
        sentinel.unlink()

    def test_maintenance_requested_during_job_is_reported_only_after_it_finishes(self):
        response = self.post_job(document_id=self.first.id)
        self.assertEqual(response.status_code, 201)
        job = OasisIndexJob.objects.get(pk=response.json()['data']['id'])
        base = job_root(job).parent.parent

        def existing_job_finishes(running):
            (base / 'maintenance.json').write_text(json.dumps({'nonce': 'c' * 32}))
            state = json.loads((base / 'worker.json').read_text())
            self.assertFalse(state['maintenance'])
            running.state = 'succeeded'
            running.save(update_fields=['state'])

        # The second sleep follows the paused heartbeat; exit without stopping a job.
        with patch('content_management.management.commands.run_oasis_index_jobs.execute_job', side_effect=existing_job_finishes), \
             patch('content_management.management.commands.run_oasis_index_jobs.time.sleep', side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                call_command('run_oasis_index_jobs', stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.state, 'succeeded')

    def test_document_and_folder_actions_queue_full_catalogue_with_explicit_worker_status(self):
        snapshot = self.snapshot()
        self.assertTrue(snapshot['configuration']['configured'])
        self.assertFalse(snapshot['configuration']['worker_active'])
        self.assertTrue(snapshot['documents'][0]['can_reindex'])
        for target in ({'document_id': self.first.id}, {'folder_id': self.farming.id}):
            response = self.post_job(**target)
            self.assertEqual(response.status_code, 201, response.content)
            data = response.json()['data']
            self.assertEqual(data['affected_document_ids'], [self.first.id, self.second.id])
            self.assertEqual((data['state'], data['scope'], data['private_draft']), ('queued', 'catalogue', True))
            stored = OasisIndexJob.objects.get(pk=data['id'])
            self.assertEqual(stored.documents, self.records)
            self.assertEqual(self.client.get('/api/oasis/index-jobs/%s/' % data['id']).json()['data']['id'], data['id'])
            self.assertEqual(self.post_job().status_code, 409)
            self.assertFalse(self.snapshot()['documents'][0]['can_reindex'])
            stored.delete()
        response = self.post_job(profile='hybrid')
        self.assertEqual(response.status_code, 409)
        self.assertIn('embedding model', response.json()['error']['blocked_reason'])
        self.assertFalse(OasisIndexJob.objects.exists())

    def test_non_pdf_disabled_and_unassigned_documents_report_ineligibility(self):
        outside = self.add_document('outside.pdf', 'Outside synthetic original')
        disabled = self.add_document('disabled.pdf', 'Disabled synthetic original', self.water, active=False)
        nonpdf = self.add_document('notes.txt', 'Non PDF synthetic original', self.water)
        items = {item['document_id']: item for item in self.snapshot()['documents']}
        for document in (outside, disabled, nonpdf):
            self.assertEqual(items[document.id]['lexical']['state'], 'not_applicable')
            self.assertFalse(items[document.id]['can_reindex'])
            self.assertEqual(self.post_job(document_id=document.id).status_code, 400)
        self.assertIn('Assign', items[outside.id]['blocked_reason'])
        self.assertIn('disabled', items[disabled.id]['blocked_reason'])
        self.assertIn('PDF', items[nonpdf.id]['blocked_reason'])

    def test_verified_lexical_draft_becomes_stale_after_same_basename_replacement(self):
        ready = self.ready_job()
        with patch('content_management.oasis_indexing.verified_receipt', return_value=ready.receipt):
            current = self.snapshot()['documents'][0]
            self.assertEqual(current['lexical']['state'], 'indexed')
            self.assertEqual(current['vectors']['state'], 'not_indexed')
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.patch('/api/oasis/documents/%s/' % self.first.id, {
                    'content_file': ContentFile(sample_pdf('Replacement synthetic original'), name='first.pdf'),
                }, format='multipart')
                self.assertEqual(response.status_code, 200, response.content)
            self.first.refresh_from_db()
            self.assertEqual(response.json()['data']['id'], self.first.id)
            current = self.snapshot()['documents'][0]
            self.assertEqual(current['lexical']['state'], 'stale')
            self.assertEqual(current['vectors']['state'], 'not_indexed')
            self.assertNotEqual(current['sha256'], self.records[0]['sha256'])
            self.assertFalse(current['can_reindex'])
            self.assertEqual(self.post_job(document_id=self.first.id).status_code, 409)

    def test_exact_byte_hash_detects_in_place_change_and_corrupt_receipt(self):
        ready = self.ready_job()
        with patch('content_management.oasis_indexing.verified_receipt', return_value=ready.receipt):
            before = self.snapshot()['documents'][0]['sha256']
            path = Path(self.first.content_file.path)
            replacement = sample_pdf('First synthetic original').replace(b'First', b'Other')
            self.assertEqual(len(replacement), path.stat().st_size)
            path.write_bytes(replacement)
            current = self.snapshot()['documents'][0]
            self.assertNotEqual(before, current['sha256'])
            self.assertEqual(current['lexical']['state'], 'stale')
        with patch('content_management.oasis_indexing.verified_receipt', side_effect=ValueError('Synthetic corrupted index')):
            current = self.snapshot()['documents'][0]
            self.assertEqual(current['lexical']['state'], 'unavailable')
            self.assertIn('corrupted', current['blocked_reason'])

    def test_station_subprocess_failure_preserves_prior_ready_root_and_receipt(self):
        ready = self.ready_job()
        prior = job_root(ready)
        prior.mkdir(parents=True)
        (prior / 'sentinel').write_text('previous verified private draft')
        response = self.post_job(document_id=self.first.id)
        self.assertEqual(response.status_code, 201)
        queued = OasisIndexJob.objects.get(pk=response.json()['data']['id'])
        with patch('content_management.management.commands.run_oasis_index_jobs.run_command', side_effect=ValueError('Synthetic extraction subprocess failure')):
            call_command('run_oasis_index_jobs', once=True, stdout=StringIO())
        queued.refresh_from_db()
        ready.refresh_from_db()
        self.assertEqual(queued.state, 'failed')
        self.assertIsNotNone(queued.started_on)
        self.assertIsNotNone(queued.finished_on)
        self.assertIn('subprocess failure', queued.diagnostics)
        self.assertEqual(ready.state, 'succeeded')
        self.assertIsNotNone(ready.receipt)
        self.assertEqual((prior / 'sentinel').read_text(), 'previous verified private draft')
        self.assertNotEqual(prior, job_root(queued))
        self.assertTrue((job_root(queued) / 'bundles' / self.version.version_number / 'solarspell.db').is_file())
        self.assertFalse(self.snapshot()['configuration']['worker_active'])

    def test_incomplete_validated_snapshot_cannot_be_marked_succeeded(self):
        queued = OasisIndexJob.objects.get(pk=self.post_job().json()['data']['id'])
        receipt = self.ready_job().receipt
        receipt['documents'] = receipt['documents'][:1]
        with patch('content_management.management.commands.run_oasis_index_jobs.run_command', return_value='Synthetic process output'), patch('content_management.management.commands.run_oasis_index_jobs.run_probe', return_value={'receipt': receipt}):
            execute_job(queued)
        queued.refresh_from_db()
        self.assertEqual(queued.state, 'failed')
        self.assertIn('exact queued originals', queued.diagnostics)
        self.assertIsNone(queued.receipt)

    def test_unsafe_version_and_legacy_original_paths_fail_before_export(self):
        outside = self.root / 'outside-export'
        for number in (str(outside), '../outside-export', 'bad name', 'v' * 161, 'nested/version', '\\outside'):
            with self.subTest(number=number):
                self.version.version_number = number
                self.version.save(update_fields=['version_number'])
                self.probe['manifest']['library_version'] = number
                self.assertEqual(self.post_job().status_code, 409)
                job = OasisIndexJob.objects.create(catalogue_version=self.version.id, documents=self.records,
                                                    manifest=self.manifest, manifest_sha256='a' * 64)
                with patch('content_management.management.commands.run_oasis_index_jobs.LibraryBuildUtil') as exporter:
                    execute_job(job)
                    exporter.assert_not_called()
                job.refresh_from_db()
                self.assertEqual(job.state, 'failed')
                self.assertFalse(job_root(job).exists())
        self.assertFalse(outside.exists())
        self.version.version_number = 'safe-version'
        self.version.save(update_fields=['version_number'])
        self.probe['manifest']['library_version'] = 'safe-version'
        unsafe = Content.objects.create(title='Malformed legacy original', active=False,
                                        file_name='../outside.txt', content_file='contents/../outside.txt')
        self.water.library_content.add(unsafe)
        self.assertEqual(self.post_job().status_code, 409)
        self.assertIn('unsafe export filename', self.snapshot()['configuration']['blocked_reason'])

    def test_indexing_read_and_write_endpoints_remain_private(self):
        for flags, peer in ((False, '127.0.0.1'), (True, '192.0.2.1')):
            with override_settings(OASIS_CURATOR_ENABLED=flags, OASIS_LOOPBACK_ONLY=False):
                self.assertEqual(self.client.get('/api/oasis/indexing/?catalogue_version=%s' % self.version.id, REMOTE_ADDR=peer).status_code, 403)
                self.assertEqual(self.client.get('/api/oasis/index-jobs/?catalogue_version=%s' % self.version.id, REMOTE_ADDR=peer).status_code, 403)
                self.assertEqual(self.client.post('/api/oasis/index-jobs/', {'catalogue_version': self.version.id}, format='json', REMOTE_ADDR=peer).status_code, 403)

    def test_status_page_ids_and_subtree_eligibility_do_not_depend_on_visible_pdf_cards(self):
        section = LibraryFolder.objects.create(folder_name='Water sections', version=self.version, parent=self.water)
        self.water.library_content.remove(self.second)
        section.library_content.add(self.second)
        nonpdf = self.add_document('visible-notes.txt', 'Visible non PDF', self.water)
        response = self.client.get('/api/oasis/indexing/', {'catalogue_version': self.version.id,
                                   'document_ids': str(nonpdf.id), 'folder_id': self.water.id})
        self.assertEqual(response.status_code, 200, response.content)
        snapshot = response.json()['data']
        self.assertEqual([item['document_id'] for item in snapshot['documents']], [nonpdf.id])
        self.assertEqual(snapshot['document_count'], 3)
        self.assertEqual(snapshot['documents_returned'], 1)
        self.assertEqual(snapshot['library']['eligible_document_count'], 1)
        self.assertTrue(snapshot['library']['can_reindex'])
        empty = self.client.get('/api/oasis/indexing/', {'catalogue_version': self.version.id, 'document_ids': '', 'folder_id': section.id}).json()['data']
        self.assertEqual(empty['documents'], [])
        self.assertTrue(empty['library']['can_reindex'])
        for invalid in ('0', 'abc', ','.join(str(index) for index in range(1, 102))):
            self.assertEqual(self.client.get('/api/oasis/indexing/', {'catalogue_version': self.version.id, 'document_ids': invalid}).status_code, 400)
        unrelated = LibraryVersion.objects.create(library_name='Other synthetic', version_number='other-version')
        wrong_folder = LibraryFolder.objects.create(folder_name='Wrong version', version=unrelated)
        self.assertEqual(self.client.get('/api/oasis/indexing/', {'catalogue_version': self.version.id, 'folder_id': wrong_folder.id}).status_code, 400)

    def test_thousands_of_documents_have_bounded_status_payload_and_compact_jobs(self):
        # These ORM-only labelled records are deliberately unreviewed. Status
        # must reject full-corpus coverage before trying to read their originals.
        additional = Content.objects.bulk_create([Content(title='Synthetic scale fixture %s' % index, display_title='Synthetic scale fixture',
                                                 file_name='scale-%s.pdf' % index, content_file='contents/scale-%s.pdf' % index,
                                                 modified_on=timezone.now())
                                                 for index in range(1200)])
        self.farming.library_content.add(*additional)
        ready = self.ready_job()
        affected = self.records + [{'document_id': document.id, 'filename': document.file_name, 'sha256': 'a' * 64} for document in additional]
        ready.documents = affected
        ready.receipt['documents'] = affected
        ready.save(update_fields=['documents', 'receipt'])
        with patch('content_management.oasis_indexing.verified_receipt', return_value=ready.receipt), patch('content_management.oasis_indexing.original_record', wraps=original_record) as verify:
            response = self.client.get('/api/oasis/indexing/', {'catalogue_version': self.version.id,
                                       'document_ids': '%s,%s' % (self.first.id, self.second.id)})
        self.assertEqual(response.status_code, 200, response.content)
        snapshot = response.json()['data']
        self.assertEqual(snapshot['document_count'], 1202)
        self.assertEqual(snapshot['documents_returned'], 2)
        self.assertFalse(snapshot['configuration']['configured'])
        self.assertEqual(verify.call_count, 2)
        self.assertLess(len(response.content), 12000)
        job = snapshot['jobs'][0]
        self.assertEqual(job['affected_document_count'], 1202)
        self.assertEqual(len(job['affected_document_ids']), 100)
        self.assertTrue(job['affected_document_ids_truncated'])
        self.assertNotIn('receipt', job)
        for document in snapshot['documents']:
            self.assertNotIn('receipt', document['latest_job'])
            self.assertNotIn('affected_document_ids', document['latest_job'])
            self.assertNotIn('diagnostics', document['latest_job'])
        detail = self.client.get('/api/oasis/index-jobs/%s/' % ready.id).json()['data']
        self.assertEqual(len(detail['receipt']['documents']), 1202)
        self.assertEqual(len(detail['affected_document_ids']), 1202)
        self.assertFalse(detail['affected_document_ids_truncated'])

    def cache_fixture(self):
        job = self.ready_job()
        draft = job_root(job) / 'draft'
        snapshot = draft / 'v-synthetic-cache-test'
        (snapshot / 'content').mkdir(parents=True)
        (draft / 'current').symlink_to(snapshot.name, target_is_directory=True)
        (snapshot / 'manifest.json').write_text('{}')
        (snapshot / 'index.sqlite3').write_bytes(b'synthetic immutable index validation fixture')
        for document in (self.first, self.second):
            (snapshot / 'content' / document.file_name).write_bytes(Path(document.content_file.path).read_bytes())
        receipt = copy.deepcopy(job.receipt)
        receipt.update(snapshot=snapshot.name, vector_artifact_valid=False, vector_model_digest=None)
        cached_artifact_receipt.cache_clear()
        return job, draft, snapshot, receipt

    def test_unchanged_artifacts_avoid_full_hash_and_changed_original_invalidates_cache(self):
        job, draft, snapshot, receipt = self.cache_fixture()
        config = operator_config()

        def validate(config, *, root, artifacts_only):
            self.assertTrue(artifacts_only)
            for record in job.documents:
                original = Path(root) / 'current' / 'content' / record['filename']
                if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest() != record['sha256']:
                    raise ValueError('Changed immutable original failed validation.')
            return {'receipt': receipt}

        with patch('content_management.oasis_indexing.run_probe', side_effect=validate) as full_verification:
            first = verified_receipt(config, job)
            with patch('content_management.oasis_indexing.time.time', return_value=10**12):
                second = verified_receipt(config, job)
            self.assertEqual(first, second)
            self.assertEqual(full_verification.call_count, 1)
            (snapshot / 'content' / self.first.file_name).write_bytes(sample_pdf('Changed immutable original'))
            with self.assertRaisesMessage(ValueError, 'Changed immutable original'):
                verified_receipt(config, job)
            self.assertEqual(full_verification.call_count, 2)

    def test_cached_artifact_validation_still_refreshes_installed_model_digest(self):
        job, draft, snapshot, receipt = self.cache_fixture()
        vector = draft / 'semantic' / snapshot.name / 'vectors.sqlite3'
        vector.parent.mkdir(parents=True)
        vector.write_bytes(b'synthetic vector artifact validation fixture')
        receipt.update(vector_artifact_valid=True, vector_valid=True, vector_model_digest='c' * 64,
                       vector_state='indexed', vector_reason=None, vectors_sha256='d' * 64)
        self.probe.update(vector_available=True, model_digest='c' * 64, vector_blocked_reason=None)
        config = operator_config()
        with patch('content_management.oasis_indexing.run_probe', return_value={'receipt': receipt}) as artifact_validation:
            self.assertTrue(verified_receipt(config, job)['vector_valid'])
            self.probe['model_digest'] = 'e' * 64
            stale = verified_receipt(config, job)
            self.assertFalse(stale['vector_valid'])
            self.assertEqual(stale['vector_state'], 'stale')
            self.assertIn('digest differs', stale['vector_reason'])
            self.probe.update(vector_available=False, vector_blocked_reason='Local model was removed.')
            unavailable = verified_receipt(config, job)
            self.assertEqual(unavailable['vector_state'], 'unavailable')
            self.assertTrue(unavailable['lexical_valid'])
            self.assertEqual(artifact_validation.call_count, 1)

    @override_settings(OASIS_SYNTHETIC_FIXTURES=True)
    def test_synthetic_manifest_helper_rejects_replacement_despite_seed_metadata(self):
        version = LibraryVersion.objects.create(library_name='Original synthetic seed', version_number='oasis-synthetic-preview-v1')
        folders = {name: LibraryFolder.objects.create(folder_name=name, version=version) for name in ('Farming', 'Water', 'Learning')}
        originals = []
        for title, filename, library in (('Sample crop record (synthetic)', 'oasis-synthetic-farming.pdf', 'Farming'),
                                         ('Sample water record (synthetic)', 'oasis-synthetic-water.pdf', 'Water'),
                                         ('Sample learning record (synthetic)', 'oasis-synthetic-learning.pdf', 'Learning')):
            document = self.add_document(filename, title, folders[library])
            document.copyright_notes = 'Original synthetic fixture by Kuwala contributors.'
            document.save(update_fields=['copyright_notes'])
            originals.append(document)
        folders['Learning'].library_content.add(originals[1])
        call_command('seed_oasis_index_manifest', stdout=StringIO())
        manifest = self.root / '.preview' / 'indexing' / 'synthetic-reviewed-manifest.json'
        reviewed_before = manifest.read_bytes()
        libraries = {item['label']: item for item in json.loads(reviewed_before)['libraries']}
        self.assertEqual(set(libraries), {'Farming', 'Water', 'Learning'})
        self.assertEqual(set(libraries['Learning']['document_ids']), {'synthetic-document-%s' % item.id for item in originals[1:]})
        self.assertEqual(libraries['Water']['dlms_folder_id'], folders['Water'].id)
        for root_name, section_name, documents in (
            ('Farming', 'Crop records (synthetic)', [originals[0]]),
            ('Water', 'Water records (synthetic)', [originals[1]]),
            ('Learning', 'Learning records (synthetic)', originals[1:]),
        ):
            section = LibraryFolder.objects.create(folder_name=section_name, version=version, parent=folders[root_name])
            section.library_content.add(*documents)
        call_command('seed_oasis_index_manifest', stdout=StringIO())
        # Known sections add no new review authority or top-level sources.
        self.assertEqual(set(item['label'] for item in json.loads(manifest.read_text())['libraries']), set(libraries))
        reviewed_before = manifest.read_bytes()
        unknown = LibraryFolder.objects.create(folder_name='Unreviewed extra section', version=version, parent=folders['Farming'])
        with self.assertRaisesMessage(CommandError, 'original synthetic seed sections'):
            call_command('seed_oasis_index_manifest', stdout=StringIO())
        unknown.delete()
        Path(originals[0].content_file.path).write_bytes(sample_pdf('Arbitrary replacement with copied synthetic metadata'))
        with self.assertRaisesMessage(CommandError, 'cannot authorise replacement bytes'):
            call_command('seed_oasis_index_manifest', stdout=StringIO())
        self.assertEqual(manifest.read_bytes(), reviewed_before)
