"""Private passage search scope, provenance and explicit semantic contracts."""
import copy
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from content_management import test_oasis_indexing as index_tests
from content_management.models import LibraryFolder, LibraryVersion
from content_management.oasis_indexing import job_root, operator_config
from content_management.oasis_search import run_search


class PrivatePassageSearchTests(TestCase):
    add_document = index_tests.PrivateIndexingTests.add_document
    ready_job = index_tests.PrivateIndexingTests.ready_job

    def setUp(self):
        index_tests.PrivateIndexingTests.setUp(self)
        cache.clear()
        self.job = self.ready_job()
        self.job.receipt.update({'snapshot': 'v-synthetic-test', 'vector_reason': 'No installed local embedding model.'})
        for item in self.job.receipt['documents']:
            item.update({'page_count': 1, 'passage_count': 1})
        self.job.save(update_fields=['receipt'])
        self.config = operator_config()
        self.validation = patch('content_management.oasis_search.verified_job', return_value=(self.config, self.job.receipt))
        self.validation.start()
        self.addCleanup(self.validation.stop)

    def search(self, **extra):
        return self.client.get('/api/oasis/index-search/', {'catalogue_version': self.version.id, **extra})

    def passage(self, document):
        source = next(item for item in self.job.receipt['documents'] if item['document_id'] == document.id)
        return {'document_id': document.id, 'title': document.title, 'filename': source['filename'],
                'original_sha256': source['sha256'], 'page': 1, 'text': 'Actual synthetic fixture passage.',
                'publisher': 'Synthetic test publisher', 'authors': 'Synthetic author',
                'source_url': 'https://example.invalid/original', 'licence': 'CC0 (synthetic only)',
                'licence_url': 'https://creativecommons.org/publicdomain/zero/1.0/'}

    def result(self, document, profile='lexical'):
        return {'snapshot': self.job.receipt['snapshot'], 'profile_used': profile, 'results': [self.passage(document)]}

    def test_capabilities_are_private_draft_and_selected_section_is_independent(self):
        outside = self.add_document('unassigned.pdf', 'Unassigned synthetic original')
        section = LibraryFolder.objects.create(folder_name='Synthetic water section', version=self.version, parent=self.water)
        self.water.library_content.remove(self.second)
        section.library_content.add(self.second)
        response = self.search(folder_id=section.id)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()['data']
        self.assertTrue(data['private_draft'])
        self.assertTrue(data['lexical_available'])
        self.assertFalse(data['semantic_available'])
        self.assertIn('embedding model', data['semantic_reason'])
        self.assertEqual((data['indexed_document_count'], data['eligible_document_count']), (1, 1))
        self.assertEqual(data['results'], [])
        self.assertEqual(data['snapshot'], 'v-synthetic-test')
        self.assertNotEqual(outside.id, self.second.id)

    def test_real_passage_contract_is_scoped_and_reader_pinned_to_verified_job(self):
        with patch('content_management.oasis_search.run_search', return_value=self.result(self.second)) as provider:
            response = self.search(folder_id=self.water.id, q='where is the water record?', profile='lexical')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(provider.call_args.args[3], ['synthetic-%s' % self.second.id])
        data = response.json()['data']
        self.assertEqual(data['profile_used'], 'lexical')
        result = data['results'][0]
        self.assertEqual(result['authors'], 'Synthetic author')
        self.assertEqual(result['licence'], 'CC0 (synthetic only)')
        self.assertEqual(result['original_sha256'], self.records[1]['sha256'])
        self.assertEqual(result['original_page_url'], '/api/oasis/index-search/original/%s/%s/#page=1' % (self.job.id, self.second.id))
        with patch('content_management.oasis_search.run_search', return_value=self.result(self.first)):
            self.assertEqual(self.search(folder_id=self.water.id, q='crop').status_code, 409)

    def test_explicit_semantic_mode_never_labels_keyword_fallback_as_ai(self):
        with patch('content_management.oasis_search.run_search') as provider:
            response = self.search(q='water', profile='semantic')
            self.assertEqual(response.status_code, 409)
            self.assertIn('embedding model', response.json()['error']['blocked_reason'])
            provider.assert_not_called()
        self.job.receipt.update({'vector_valid': True, 'vectors_sha256': 'c' * 64, 'vector_reason': None})
        with patch('content_management.oasis_search.run_search', return_value=self.result(self.second, 'semantic')):
            response = self.search(q='where can I find water?', profile='semantic')
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()['data']['profile_used'], 'semantic')
        with patch('content_management.oasis_search.run_search', side_effect=ValueError('Installed model digest changed.')):
            response = self.search(q='water', profile='semantic')
            self.assertEqual(response.status_code, 409)
            self.assertIn('digest changed', response.json()['error']['blocked_reason'])
        with patch('content_management.oasis_search.run_search', return_value=self.result(self.second, 'lexical')):
            self.assertEqual(self.search(q='water', profile='semantic').status_code, 409)

    def test_same_bytes_filename_change_during_query_is_rejected(self):
        result = self.result(self.second)

        def rename_during_search(*args):
            self.second.file_name = 'renamed-during-query.pdf'
            self.second.save(update_fields=['file_name'])
            return result

        with patch('content_management.oasis_search.run_search', side_effect=rename_during_search):
            response = self.search(q='water')
        self.assertEqual(response.status_code, 409)
        self.assertIn('changed during search', response.json()['error']['blocked_reason'])

    def test_replacement_is_excluded_but_old_verified_original_link_keeps_exact_bytes(self):
        original_bytes = Path(self.first.content_file.path).read_bytes()
        draft = job_root(self.job) / 'draft'
        snapshot = draft / self.job.receipt['snapshot']
        (snapshot / 'content').mkdir(parents=True)
        (snapshot / 'content' / self.first.file_name).write_bytes(original_bytes)
        (draft / 'current').symlink_to(snapshot.name, target_is_directory=True)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch('/api/oasis/documents/%s/' % self.first.id, {
                'content_file': ContentFile(index_tests.sample_pdf('Replacement synthetic search original'), name='first.pdf'),
            }, format='multipart')
            self.assertEqual(response.status_code, 200)
        data = self.search(folder_id=self.farming.id).json()['data']
        self.assertFalse(data['lexical_available'])
        self.assertEqual(data['stale_document_count'], 1)
        self.assertEqual(self.search(folder_id=self.farming.id, q='first').status_code, 409)
        original = self.client.get('/api/oasis/index-search/original/%s/%s/' % (self.job.id, self.first.id))
        self.assertEqual(original.status_code, 200)
        self.assertEqual(b''.join(original.streaming_content), original_bytes)
        self.assertEqual(original['Cache-Control'], 'no-store')
        (snapshot / 'content' / 'first.pdf').write_bytes(b'corrupt private original')
        self.assertEqual(self.client.get('/api/oasis/index-search/original/%s/%s/' % (self.job.id, self.first.id)).status_code, 409)

    def test_invalid_queries_corrupt_artifacts_and_remote_origins_are_honest_errors(self):
        for payload in ({'q': 'x' * 161}, {'q': 'line\nfeed'}, {'profile': 'invented'}, {'unknown': 'x'}):
            self.assertEqual(self.search(**payload).status_code, 400)
        other = LibraryVersion.objects.create(library_name='Other synthetic catalogue', version_number='other-search-v1')
        outside = LibraryFolder.objects.create(folder_name='Other library', version=other)
        self.assertEqual(self.search(folder_id=outside.id).status_code, 400)
        with patch('content_management.oasis_search.verified_job', side_effect=ValueError('Corrupt draft index.')):
            data = self.search().json()['data']
            self.assertFalse(data['lexical_available'])
            self.assertIn('Corrupt', data['blocked_reason'])
            self.assertEqual(self.search(q='water').status_code, 409)
        with patch('content_management.oasis_search.run_search') as provider:
            self.assertEqual(self.client.get('/api/oasis/index-search/', {'catalogue_version': self.version.id, 'q': 'water'}, HTTP_SEC_FETCH_SITE='cross-site').status_code, 403)
            provider.assert_not_called()
        for enabled, peer in ((False, '127.0.0.1'), (True, '192.0.2.1')):
            with override_settings(OASIS_CURATOR_ENABLED=enabled, OASIS_LOOPBACK_ONLY=False):
                self.assertEqual(self.client.get('/api/oasis/index-search/', {'catalogue_version': self.version.id}, REMOTE_ADDR=peer).status_code, 403)
                self.assertEqual(self.client.get('/api/oasis/index-search/original/%s/%s/' % (self.job.id, self.first.id), REMOTE_ADDR=peer).status_code, 403)

    def test_reader_rejects_content_directory_symlink_even_for_matching_original_bytes(self):
        draft = job_root(self.job) / 'draft'
        snapshot = draft / self.job.receipt['snapshot']
        snapshot.mkdir(parents=True)
        outside = self.root / 'outside-private-job-originals'
        outside.mkdir()
        (outside / self.first.file_name).write_bytes(Path(self.first.content_file.path).read_bytes())
        (snapshot / 'content').symlink_to(outside, target_is_directory=True)
        (draft / 'current').symlink_to(snapshot.name, target_is_directory=True)
        response = self.client.get('/api/oasis/index-search/original/%s/%s/' % (self.job.id, self.first.id))
        self.assertEqual(response.status_code, 409)
        self.assertIn('unsafe', response.json()['error']['blocked_reason'])

    def test_queries_are_throttled_but_empty_capabilities_do_not_spend_query_budget(self):
        with patch('content_management.oasis_search.run_search', return_value={'snapshot': 'v-synthetic-test', 'profile_used': 'lexical', 'results': []}) as provider:
            for _ in range(10):
                self.assertEqual(self.search(q='water').status_code, 200)
            self.assertEqual(self.search(q='water').status_code, 429)
            self.assertEqual(provider.call_count, 10)
        self.assertEqual(self.search().status_code, 200)

    def test_subprocess_is_bounded_argv_and_timeout_is_not_a_fake_empty_result(self):
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(self.result(self.second)), stderr='')
        with patch('content_management.oasis_search.subprocess.run', return_value=completed) as subprocess_call:
            data = run_search(self.config, self.job, '-water', ['synthetic-%s' % self.second.id], 'lexical')
            self.assertEqual(data['results'][0]['document_id'], self.second.id)
            self.assertIn('--query=-water', subprocess_call.call_args.args[0])
            self.assertEqual(subprocess_call.call_args.kwargs['timeout'], 20)
            self.assertNotIn('shell', subprocess_call.call_args.kwargs)
        with patch('content_management.oasis_search.subprocess.run', side_effect=subprocess.TimeoutExpired('trusted station helper', 20)):
            with self.assertRaisesMessage(ValueError, 'unavailable'):
                run_search(self.config, self.job, 'water', ['synthetic-%s' % self.second.id], 'semantic')
