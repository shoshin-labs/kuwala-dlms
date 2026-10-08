"""Library/section grouping and bounded public/private catalogue queries."""
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata, MetadataType


@override_settings(OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=False)
class OasisCatalogueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.version = LibraryVersion.objects.create(library_name='Synthetic catalogue', version_number='synthetic-sections-v1', created_on=timezone.now())
        self.other_version = LibraryVersion.objects.create(library_name='Other synthetic catalogue', version_number='synthetic-sections-v2', created_on=timezone.now())
        self.farming = LibraryFolder.objects.create(folder_name='Farming', version=self.version)
        self.soil = LibraryFolder.objects.create(folder_name='Soil', version=self.version, parent=self.farming)
        self.deep = LibraryFolder.objects.create(folder_name='Soil records', version=self.version, parent=self.soil)
        self.empty = LibraryFolder.objects.create(folder_name='Empty section', version=self.version, parent=self.farming)
        self.water = LibraryFolder.objects.create(folder_name='Water', version=self.version)
        self.other = LibraryFolder.objects.create(folder_name='Other library', version=self.other_version)
        self.shared = self.document('Water harvest manual', 'synthetic-water.pdf')
        self.notes = self.document('Soil notes', 'synthetic-soil.pdf')
        self.inactive = self.document('Disabled synthetic record', 'synthetic-disabled.pdf', active=False)
        self.orphan = self.document('Unassigned synthetic record', 'synthetic-unassigned.pdf')
        self.outside = self.document('Other synthetic record', 'synthetic-other.pdf')
        self.soil.library_content.add(self.shared, self.notes)
        self.deep.library_content.add(self.notes)
        self.farming.library_content.add(self.notes, self.inactive)
        self.water.library_content.add(self.shared)
        self.other.library_content.add(self.outside)
        keywords = MetadataType.objects.create(name='Synthetic keywords')
        first = Metadata.objects.create(type=keywords, name='irrigation')
        second = Metadata.objects.create(type=keywords, name='irrigation fixture author')
        self.shared.metadata.add(first, second)
        self.notes.metadata.add(second)

    def document(self, title, filename, active=True):
        return Content.objects.create(title=title, display_title=title, file_name=filename,
                                      content_file='contents/' + filename, filesize=100, active=active,
                                      description='Synthetic query fixture; no technical advice.', modified_on=timezone.now())

    def overview(self, **parameters):
        return self.client.get('/api/oasis/catalogue/', {'catalogue_version': self.version.id, **parameters})

    def documents(self, **parameters):
        return self.client.get('/api/oasis/catalogue/documents/', {'catalogue_version': self.version.id, **parameters})

    def test_lightweight_tree_counts_descendants_and_deduplicates_memberships(self):
        response = self.overview()
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['catalogue_version'], self.version.id)
        self.assertEqual(data['document_count'], 2)
        self.assertNotIn('all_document_count', data)
        folders = {folder['id']: folder for folder in data['folders']}
        self.assertEqual(set(folders), {self.farming.id, self.soil.id, self.deep.id, self.empty.id, self.water.id})
        self.assertEqual(folders[self.farming.id]['document_count'], 2)
        self.assertEqual(folders[self.farming.id]['direct_document_count'], 1)
        self.assertEqual(folders[self.soil.id]['document_count'], 2)
        self.assertEqual(folders[self.deep.id]['document_count'], 1)
        self.assertEqual(folders[self.water.id]['document_count'], 1)
        self.assertEqual(folders[self.empty.id]['document_count'], 0)
        self.assertEqual(folders[self.soil.id]['parent'], self.farming.id)
        self.assertEqual(folders[self.deep.id]['version'], self.version.id)
        for folder in folders.values():
            self.assertNotIn('library_content', folder)
        self.assertEqual(set(data['versions'][0]), {'id', 'library_name', 'version_number'})

    def test_private_counts_include_disabled_and_global_unassigned_documents(self):
        data = self.overview(mode='curator').json()['data']
        self.assertEqual(data['document_count'], 3)
        self.assertEqual(data['all_document_count'], 5)
        farming = next(folder for folder in data['folders'] if folder['id'] == self.farming.id)
        self.assertEqual(farming['document_count'], 3)
        self.assertEqual(farming['direct_document_count'], 2)
        scoped = self.client.get('/api/oasis/documents/', {'catalogue_version': self.version.id}).json()['data']
        self.assertEqual(scoped['count'], 3)
        global_page = self.client.get('/api/oasis/documents/', {'catalogue_version': self.version.id, 'global': '1'}).json()['data']
        self.assertEqual(global_page['count'], 5)
        orphan = next(document for document in global_page['results'] if document['id'] == self.orphan.id)
        self.assertEqual(orphan['catalogue_folder_ids'], [])
        detail = self.client.get('/api/oasis/documents/%s/' % self.orphan.id,
                                 {'catalogue_version': self.version.id, 'global': '1'})
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()['data']['catalogue_folder_ids'], [])

    def test_subtree_document_pages_keep_ids_deduplicate_and_hide_inactive(self):
        response = self.documents(folder_id=self.farming.id, size=1)
        self.assertEqual(response.status_code, 200)
        first = response.json()['data']
        self.assertEqual(first['count'], 2)
        self.assertEqual(first['page'], 1)
        self.assertEqual(first['page_size'], 1)
        self.assertIsNone(first['previous'])
        self.assertIsNotNone(first['next'])
        self.assertEqual(first['results'][0]['id'], self.shared.id)
        self.assertEqual(first['results'][0]['catalogue_folder_ids'], [self.soil.id, self.water.id])
        second = self.documents(folder_id=self.farming.id, size=1, page=2).json()['data']
        self.assertEqual(second['results'][0]['id'], self.notes.id)
        self.assertIsNone(second['next'])
        self.assertIsNotNone(second['previous'])
        nested = self.documents(folder_id=self.deep.id).json()['data']
        self.assertEqual([item['id'] for item in nested['results']], [self.notes.id])
        self.assertEqual(self.documents(folder_id=self.empty.id).json()['data']['count'], 0)

    def test_search_runs_in_selected_scope_and_deduplicates_metadata_matches(self):
        data = self.documents(folder_id=self.farming.id, q='irrigation').json()['data']
        self.assertEqual(data['count'], 2)
        self.assertEqual([document['id'] for document in data['results']], [self.shared.id, self.notes.id])
        metadata = data['results'][0]['metadata_info']
        self.assertEqual(len(metadata), 2)
        self.assertEqual(metadata[0]['type_name'], 'Synthetic keywords')
        filename = self.documents(q='synthetic-soil.pdf').json()['data']
        self.assertEqual([document['id'] for document in filename['results']], [self.notes.id])
        self.assertEqual(self.documents(folder_id=self.water.id, q='Soil').json()['data']['count'], 0)

    def test_deep_document_filter_enforces_version_and_folder_scope(self):
        self.assertEqual(self.documents(folder_id=self.water.id, document_id=self.notes.id).json()['data']['count'], 0)
        self.assertEqual(self.documents(document_id=self.outside.id).json()['data']['count'], 0)
        self.assertEqual(self.documents(document_id=self.inactive.id).json()['data']['count'], 0)
        self.assertEqual(self.documents(document_id=self.orphan.id).json()['data']['count'], 0)
        self.assertEqual(self.documents(folder_id=self.water.id, document_id=self.shared.id).json()['data']['count'], 1)

    def test_page_size_is_bounded_and_related_data_queries_do_not_grow_per_document(self):
        documents = Content.objects.bulk_create([
            Content(title='Synthetic page fixture %03d' % index, display_title='Synthetic page fixture %03d' % index,
                    file_name='synthetic-page-%03d.pdf' % index, content_file='contents/synthetic-page-%03d.pdf' % index,
                    filesize=100, modified_on=timezone.now())
            for index in range(125)
        ])
        through = LibraryFolder.library_content.through
        through.objects.bulk_create([through(libraryfolder_id=self.farming.id, content_id=document.id) for document in documents])
        with CaptureQueriesContext(connection) as queries:
            response = self.documents(size=10000)
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['count'], 127)
        self.assertEqual(len(data['results']), 100)
        self.assertEqual(data['page_size'], 100)
        self.assertLessEqual(len(queries), 8)
        self.assertTrue(any('LIMIT 100' in query['sql'] for query in queries))
        private = self.client.get('/api/oasis/documents/', {'size': 10000}).json()['data']
        self.assertEqual(len(private['results']), 100)
        self.assertEqual(private['page_size'], 100)

    def test_bad_scope_and_query_values_fail_without_broadening_catalogue(self):
        for parameters in ({'folder_id': self.other.id}, {'folder_id': 'invalid'},
                           {'catalogue_version': 99999}, {'document_id': 0}, {'document_id': '9' * 40},
                           {'global': '1'}, {'q': 'x' * 201}):
            with self.subTest(parameters=parameters):
                self.assertEqual(self.documents(**parameters).status_code, 400)
        self.assertEqual(self.client.get('/api/oasis/catalogue/documents/').status_code, 400)
        self.assertEqual(self.client.get('/api/oasis/documents/', {'folder_id': self.farming.id}).status_code, 400)
        self.assertEqual(self.client.get('/api/oasis/documents/', {'catalogue_version': self.version.id,
                                                                'folder_id': self.farming.id, 'global': 1}).status_code, 400)
        self.assertEqual(self.documents(page=999).status_code, 404)

    @override_settings(OASIS_CURATOR_ENABLED=False)
    def test_public_reads_remain_available_and_private_counts_and_management_stay_denied(self):
        self.assertEqual(self.overview().status_code, 200)
        self.assertEqual(self.documents().status_code, 200)
        self.assertEqual(self.overview(mode='curator').status_code, 403)
        self.assertEqual(self.client.get('/api/oasis/documents/').status_code, 403)
        self.assertEqual(self.client.post('/api/oasis/catalogue/', {}).status_code, 403)

    def test_remote_reader_cannot_request_private_counts(self):
        parameters = {'catalogue_version': self.version.id}
        self.assertEqual(self.client.get('/api/oasis/catalogue/', parameters, REMOTE_ADDR='192.0.2.1').status_code, 200)
        self.assertEqual(self.client.get('/api/oasis/catalogue/', {**parameters, 'mode': 'curator'},
                                         REMOTE_ADDR='192.0.2.1').status_code, 403)

    def test_public_catalogue_endpoints_never_accept_writes_even_in_curator_mode(self):
        self.assertEqual(self.client.post('/api/oasis/catalogue/', {}).status_code, 405)
        self.assertEqual(self.client.post('/api/oasis/catalogue/documents/', {}).status_code, 405)


@override_settings(OASIS_CURATOR_ENABLED=False)
class EmptyOasisCatalogueTests(TestCase):
    def test_empty_database_has_honest_empty_overview(self):
        response = APIClient().get('/api/oasis/catalogue/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'versions': [], 'catalogue_version': None, 'folders': [], 'document_count': 0})
