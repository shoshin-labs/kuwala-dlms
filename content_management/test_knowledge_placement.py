"""Folder-backed library/section review contract; no originals or live state."""
import copy
from django.test import SimpleTestCase
from scripts.prepare_oasis_catalogue import validate_manifest_placement, validate_manifest_sections


class KnowledgePlacementManifestTests(SimpleTestCase):
    def setUp(self):
        self.manifest = {
            'documents': [{'id': 'doc-one'}, {'id': 'doc-two'}],
            'libraries': [{'id': 'farming', 'label': 'Farming', 'dlms_folder_id': 1, 'document_ids': ['doc-one', 'doc-two']}],
            'sections': [
                {'id': 'grain', 'label': 'Grain', 'library_id': 'farming', 'dlms_folder_id': 2, 'parent_id': None, 'document_ids': ['doc-one']},
                {'id': 'maize', 'label': 'Maize', 'library_id': 'farming', 'dlms_folder_id': 3, 'parent_id': 'grain', 'document_ids': ['doc-one']},
                {'id': 'empty', 'label': 'Empty', 'library_id': 'farming', 'dlms_folder_id': 4, 'parent_id': None, 'document_ids': []},
            ],
        }
        self.folders = {
            1: {'folder_name': 'Farming', 'parent': None, 'library_content': [12]},
            2: {'folder_name': 'Grain', 'parent': 1, 'library_content': []},
            3: {'folder_name': 'Maize', 'parent': 2, 'library_content': [11]},
            4: {'folder_name': 'Empty', 'parent': 1, 'library_content': []},
        }
        self.slugs = {'doc-one': 11, 'doc-two': 12}

    def test_nested_section_subtrees_and_empty_sections(self):
        validate_manifest_placement(self.manifest, self.folders, self.slugs)
        # Direct + nested duplicate membership must not double-count a document.
        self.folders[2]['library_content'] = [11]
        validate_manifest_placement(self.manifest, self.folders, self.slugs)

    def test_parent_label_membership_and_tree_changes_are_rejected(self):
        for key, value in (('parent', 1), ('folder_name', 'Renamed'), ('library_content', [12])):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.folders)
                changed[3][key] = value
                with self.assertRaises(ValueError):
                    validate_manifest_placement(self.manifest, changed, self.slugs)
        validate_manifest_placement(self.manifest, {**self.folders, 5: {'folder_name': 'Empty holding', 'parent': 1, 'library_content': []}}, self.slugs)
        validate_manifest_placement(self.manifest, {**self.folders, 5: {'folder_name': 'Private holding', 'parent': None, 'library_content': [999]}}, self.slugs)
        with self.assertRaises(ValueError):
            validate_manifest_placement(self.manifest, {**self.folders, 5: {'folder_name': 'Unreviewed descendant', 'parent': 1, 'library_content': [999]}}, self.slugs)

    def test_parent_cycle_and_invalid_library_are_rejected(self):
        for changes in ({'parent_id': 'maize'}, {'library_id': 'missing'}):
            manifest = copy.deepcopy(self.manifest)
            manifest['sections'][0].update(changes)
            with self.assertRaises(ValueError):
                validate_manifest_placement(manifest, self.folders, self.slugs)

    def test_section_and_document_provider_id_collisions_are_rejected(self):
        for identifier in ('general-knowledge', 'fao-grain', 'fao-mycotoxin-part-1', 'fao-mycotoxin-part-2', 'oasis', 'datasource'):
            manifest = copy.deepcopy(self.manifest)
            manifest['sections'][0]['id'] = identifier
            with self.assertRaises(ValueError):
                validate_manifest_placement(manifest, self.folders, self.slugs)
        manifest = copy.deepcopy(self.manifest)
        manifest['documents'][0]['id'] = 'fao-mycotoxin-part-1'
        with self.assertRaises(ValueError):
            validate_manifest_placement(manifest, self.folders, self.slugs)

    def test_depth_boundary_is_sixteen_section_levels(self):
        manifest = copy.deepcopy(self.manifest)
        manifest['sections'] = [
            {'id': 'level-%s' % index, 'label': 'Level %s' % index, 'library_id': 'farming',
             'dlms_folder_id': index + 2, 'parent_id': ('level-%s' % (index - 1)) if index else None,
             'document_ids': []}
            for index in range(16)
        ]
        validate_manifest_sections(manifest)
        manifest['sections'].append({'id': 'level-16', 'label': 'Too deep', 'library_id': 'farming',
                                     'dlms_folder_id': 18, 'parent_id': 'level-15', 'document_ids': []})
        with self.assertRaises(ValueError):
            validate_manifest_sections(manifest)

    def test_malformed_or_out_of_scope_sections_fail_cleanly(self):
        cases = [None, [], {'library_id': []}, {'parent_id': []}, {'label': 'Bad\x00label'},
                 {'document_ids': [None]}, {'document_ids': ['missing']}]
        for changes in cases:
            manifest = copy.deepcopy(self.manifest)
            if isinstance(changes, dict):
                manifest['sections'][0].update(changes)
            else:
                manifest['sections'][0] = changes
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_manifest_sections(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest['sections'][0]['document_ids'] = []
        with self.assertRaises(ValueError):
            validate_manifest_sections(manifest)  # Maize must be contained in Grain's scope.

    def test_legacy_flat_direct_membership_contract_is_preserved(self):
        self.manifest.pop('sections')
        with self.assertRaises(ValueError):
            validate_manifest_placement(self.manifest, self.folders, self.slugs)
        self.folders[1]['library_content'] = [11, 12]
        validate_manifest_placement(self.manifest, self.folders, self.slugs)
