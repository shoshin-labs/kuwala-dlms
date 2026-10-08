"""Exact selected-catalogue transfer, with no device or active reader mutation."""
import copy
import hashlib
import json
import shutil
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.core import serializers
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibLayoutImage, LibraryFolder, LibraryVersion, Metadata, MetadataType, User
from scripts.prepare_oasis_catalogue import M2M, MODELS, canonical, prepare, validate_package


class AuthoringTransferTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / 'target'
        self.media = self.target / 'media'
        (self.media / 'contents').mkdir(parents=True)
        self.source_media = self.root / 'source-media'
        self.originals = self.target / 'imports' / 'published-snapshot' / 'content'
        self.originals.mkdir(parents=True)
        self.settings = override_settings(PREVIEW_STATE_ROOT=self.target, DEVICE_DATA_ROOT=None,
                                          MEDIA_ROOT=str(self.media), CONTENTS_ROOT=str(self.media / 'contents'))
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        language = MetadataType.objects.create(pk=1, name='Language')
        creator = MetadataType.objects.create(pk=2, name='Creator')
        unused = MetadataType.objects.create(pk=4, name='Keywords')
        english = Metadata.objects.create(pk=1, type=language, name='English')
        author = Metadata.objects.create(pk=9, type=creator, name='Synthetic fixture author')
        user = User.objects.create(pk=1, name='Synthetic original authoring curator')
        banner = LibLayoutImage.objects.create(pk=1, image_group=2)
        banner.image_file.save('source-banner.png', ContentFile(b'fixture banner'))
        logo = LibLayoutImage.objects.create(pk=2, image_group=1)
        logo.image_file.save('source-logo.png', ContentFile(b'fixture logo'))
        version = LibraryVersion.objects.create(pk=6, library_name='Synthetic main Oasis collection',
                                                version_number='synthetic-main-v6', created_by=user, library_banner=banner)
        version.metadata_types.set([language, creator, unused])
        farming = LibraryFolder.objects.create(pk=16, folder_name='Farming', version=version, logo_img=logo)
        water = LibraryFolder.objects.create(pk=17, folder_name='Water', version=version, logo_img=logo)
        section = LibraryFolder.objects.create(pk=18, folder_name='Crop section', version=version, parent=farming)
        first = self.document(4, 'first.pdf', 'First synthetic original')
        second = self.document(5, 'second.pdf', 'Second synthetic original')
        for document in (first, second):
            document.metadata.add(english, author)
        farming.library_content.add(first)
        water.library_content.add(first, second)
        section.library_content.add(first)
        other = LibraryVersion.objects.create(pk=7, library_name='Unselected synthetic catalogue', version_number='other-v7')
        outside = self.document(99, 'outside.pdf', 'Outside synthetic original')
        LibraryFolder.objects.create(pk=30, folder_name='Outside', version=other).library_content.add(outside)
        Metadata.objects.create(pk=50, type=creator, name='Unreferenced metadata excluded')
        self.manifest = {
            'version': 1, 'library_version': version.version_number, 'usage_scope': 'private-development-testing',
            'documents': [
                {'id': 'first-synthetic', 'dlms_id': first.pk, 'filename': first.file_name, 'title': first.title,
                 'sha256': hashlib.sha256(Path(first.content_file.path).read_bytes()).hexdigest(),
                 'approved': True, 'testing_only': True, 'rights_review_pending': True,
                 'source_url': 'https://example.invalid/first', 'rights_notes': 'Synthetic review only'},
                {'id': 'second-synthetic', 'dlms_id': second.pk, 'filename': second.file_name, 'title': second.title,
                 'sha256': hashlib.sha256(Path(second.content_file.path).read_bytes()).hexdigest(),
                 'approved': True, 'testing_only': True, 'rights_review_pending': True,
                 'source_url': 'https://example.invalid/second', 'rights_notes': 'Synthetic review only'},
            ],
            'libraries': [
                {'id': 'farming', 'dlms_folder_id': 16, 'label': 'Farming', 'document_ids': ['first-synthetic']},
                {'id': 'water', 'dlms_folder_id': 17, 'label': 'Water', 'document_ids': ['first-synthetic', 'second-synthetic']},
            ],
        }
        self.manifest_path = self.root / 'reviewed.json'
        self.manifest_bytes = (json.dumps(self.manifest, ensure_ascii=False, indent=2) + '\n').encode()
        self.manifest_path.write_bytes(self.manifest_bytes)
        shutil.copytree(self.media, self.source_media)
        for document in (first, second):
            shutil.copyfile(Path(document.content_file.path), self.originals / document.file_name)
        self.database = self.root / 'authoring.sqlite3'
        self.write_source_database()
        self.package = prepare(self.database, 6, self.source_media, self.manifest_path)
        self.package_path = self.root / 'catalogue-package.json'
        self.save_package()
        # Target is independently empty: source DB/media remain intact.
        LibraryFolder.objects.all().delete()
        LibraryVersion.objects.all().delete()
        Content.objects.all().delete()
        Metadata.objects.all().delete()
        MetadataType.objects.all().delete()
        User.objects.all().delete()
        LibLayoutImage.objects.all().delete()
        shutil.rmtree(self.media)
        (self.media / 'contents').mkdir(parents=True)

    def document(self, pk, filename, title):
        document = Content.objects.create(pk=pk, title=title, display_title=title,
                                          description='Exact synthetic authoring description',
                                          copyright_notes='Original fixture attribution', rights_statement='CC0 synthetic fixture only',
                                          additional_notes='Existing private-testing context', reviewed_on='2026-10-08', published_date='2020-01-01')
        document.content_file.save(filename, ContentFile(sample_pdf(title)), save=True)
        document.file_name = filename
        document.filesize = document.content_file.size
        document.save(update_fields=['file_name', 'filesize'])
        return document

    def write_source_database(self):
        with sqlite3.connect(self.database) as database:
            for name in MODELS:
                model = apps.get_model('content_management', name)
                fields = [field for field in model._meta.concrete_fields if not field.primary_key]
                columns = [field.column for field in fields]
                def sqlite_type(field):
                    if field.get_internal_type() == 'FloatField':
                        return 'REAL'
                    if field.is_relation or field.get_internal_type() in ('BooleanField', 'IntegerField', 'PositiveSmallIntegerField'):
                        return 'INTEGER'
                    return 'TEXT'
                database.execute('CREATE TABLE ' + model._meta.db_table + ' (id INTEGER PRIMARY KEY,'
                                 + ','.join(field.column + ' ' + sqlite_type(field) for field in fields) + ')')
                # Preserve numeric SQLite types just as the real authoring schema.
                rows = json.loads(serializers.serialize('json', model.objects.all()))
                for row in rows:
                    values = [row['fields'][field.name] for field in fields]
                    for index, field in enumerate(fields):
                        if field.get_internal_type() in ('BooleanField', 'IntegerField', 'PositiveSmallIntegerField', 'FloatField') or field.is_relation:
                            values[index] = None if values[index] is None else str(int(values[index])) if field.get_internal_type() != 'FloatField' else str(values[index])
                    database.execute('INSERT INTO ' + model._meta.db_table + ' VALUES (' + ','.join('?' for _ in range(len(values) + 1)) + ')', [row['pk'], *values])
                for field, (table, left, right) in M2M.get(name, {}).items():
                    database.execute('CREATE TABLE ' + table + ' (' + left + ' INTEGER,' + right + ' INTEGER)')
                    for row in rows:
                        database.executemany('INSERT INTO ' + table + ' VALUES (?,?)', [(row['pk'], pk) for pk in row['fields'][field]])

    def save_package(self):
        self.package['package_sha256'] = hashlib.sha256(canonical({key: value for key, value in self.package.items() if key != 'package_sha256'})).hexdigest()
        self.package_path.write_bytes(canonical(self.package))

    def run_import(self, **options):
        output = StringIO()
        call_command('import_oasis_catalogue', package=self.package_path, originals_dir=self.originals,
                     stdout=output, **options)
        return json.loads(output.getvalue())

    def test_preparation_selects_only_exact_version_closure_and_is_read_only(self):
        manifest, raw, fixture = validate_package(self.package)
        self.assertEqual((manifest, raw), (self.manifest, self.manifest_bytes))
        self.assertEqual(set(fixture['content']), {4, 5})
        self.assertEqual(set(fixture['libraryfolder']), {16, 17, 18})
        self.assertEqual(set(fixture['libraryversion']), {6})
        self.assertEqual(set(fixture['metadata']), {1, 9})
        self.assertEqual(set(fixture['metadatatype']), {1, 2, 4})
        self.assertEqual(set(fixture['user']), {1})
        self.assertEqual(set(fixture['liblayoutimage']), {1, 2})
        before = self.database.read_bytes()
        repeated = prepare(self.database, 6, self.source_media, self.manifest_path)
        self.assertEqual(repeated, self.package)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse((self.database.parent / (self.database.name + '-journal')).exists())

    def test_default_dry_run_changes_neither_rows_nor_media(self):
        report = self.run_import()
        self.assertTrue(report['dry_run'])
        self.assertEqual((report['documents'], report['libraries']), (2, 2))
        self.assertFalse(Content.objects.exists())
        self.assertFalse(LibraryVersion.objects.exists())
        self.assertFalse((self.target / 'catalogue-import').exists())
        self.assertEqual(list((self.media / 'contents').iterdir()), [])

    def test_apply_preserves_all_fields_ids_memberships_assets_and_reviewed_bytes(self):
        report = self.run_import(apply=True)
        self.assertFalse(report['dry_run'])
        self.assertFalse(report['indexes_changed'])
        self.assertEqual(set(Content.objects.values_list('pk', flat=True)), {4, 5})
        self.assertEqual(LibraryVersion.objects.get().pk, 6)
        self.assertEqual(set(LibraryVersion.objects.get().metadata_types.values_list('pk', flat=True)), {1, 2, 4})
        self.assertEqual(set(LibraryFolder.objects.get(pk=17).library_content.values_list('pk', flat=True)), {4, 5})
        self.assertEqual(LibraryFolder.objects.get(pk=18).parent_id, 16)
        original = Content.objects.get(pk=4)
        self.assertEqual(original.additional_notes, 'Existing private-testing context')
        self.assertEqual(original.copyright_notes, 'Original fixture attribution')
        self.assertEqual(str(original.content_file), 'contents/first.pdf')
        self.assertEqual(Path(original.content_file.path).read_bytes(), (self.originals / 'first.pdf').read_bytes())
        self.assertEqual((self.media / 'images/banners/source-banner.png').read_bytes(), b'fixture banner')
        self.assertEqual((self.target / 'catalogue-import/reviewed-manifest.json').read_bytes(), self.manifest_bytes)
        self.assertTrue(json.loads((self.target / 'catalogue-import/reviewed-manifest.json').read_text())['documents'][0]['rights_review_pending'])
        self.assertGreater(Content.objects.create(title='Next synthetic record').pk, 5)

    def test_exact_rerun_is_noop_and_edits_are_never_overwritten(self):
        self.run_import(apply=True)
        modified = Content.objects.get(pk=4).modified_on
        report = self.run_import(apply=True)
        self.assertTrue(report['already_imported'])
        self.assertEqual(Content.objects.get(pk=4).modified_on, modified)
        Content.objects.filter(pk=4).update(title='Curator edited title')
        with self.assertRaisesMessage(CommandError, 'not empty'):
            self.run_import(apply=True)
        self.assertEqual(Content.objects.get(pk=4).title, 'Curator edited title')

    def test_only_explicitly_replaceable_empty_scaffold_can_be_discarded(self):
        empty = LibraryVersion.objects.create(library_name='Empty initial collection', version_number='empty-initial')
        LibraryFolder.objects.create(folder_name='Empty library', version=empty)
        with self.assertRaisesMessage(CommandError, '--replace-empty'):
            self.run_import(apply=True)
        self.run_import(apply=True, replace_empty=True)
        self.assertEqual(list(LibraryVersion.objects.values_list('pk', flat=True)), [6])
        Content.objects.create(pk=99, title='Existing curator record')
        with self.assertRaisesMessage(CommandError, 'not empty'):
            self.run_import(apply=True, replace_empty=True)

    def test_source_hash_mismatch_and_symlink_are_refused_before_writes(self):
        (self.originals / 'first.pdf').write_bytes(sample_pdf('Changed synthetic bytes'))
        with self.assertRaisesMessage(CommandError, 'differs from reviewed bytes'):
            self.run_import(apply=True)
        self.assertFalse(Content.objects.exists())
        (self.originals / 'first.pdf').unlink()
        (self.originals / 'first.pdf').symlink_to(self.source_media / 'contents/first.pdf')
        with self.assertRaisesMessage(CommandError, 'symlinks'):
            self.run_import(apply=True)
        self.assertFalse((self.target / 'catalogue-import').exists())

    def test_transaction_failure_restores_empty_scaffold_and_cleans_only_new_files(self):
        empty = LibraryVersion.objects.create(library_name='Empty initial collection', version_number='empty-initial')
        folder = LibraryFolder.objects.create(folder_name='Empty library', version=empty)
        sentinel = self.media / 'unrelated-private-file'
        sentinel.write_bytes(b'preserve unrelated private file')
        with patch('django.db.models.Model.save_base', side_effect=ValueError('Synthetic fixture database failure')):
            with self.assertRaisesMessage(CommandError, 'Synthetic fixture database failure'):
                self.run_import(apply=True, replace_empty=True)
        self.assertEqual(LibraryVersion.objects.get().pk, empty.pk)
        self.assertEqual(LibraryFolder.objects.get().pk, folder.pk)
        self.assertFalse(Content.objects.exists())
        self.assertEqual(list((self.media / 'contents').iterdir()), [])
        self.assertFalse((self.target / 'catalogue-import/reviewed-manifest.json').exists())
        self.assertEqual(sentinel.read_bytes(), b'preserve unrelated private file')
        self.assertEqual(json.loads((self.target / 'catalogue-import/journal.json').read_text())['state'], 'rolled_back')
        self.run_import(apply=True, replace_empty=True)

    def test_reviewed_membership_tampering_and_media_collisions_are_refused(self):
        original = copy.deepcopy(self.package)
        folder = next(row for row in self.package['fixture'] if row['model'].endswith('.libraryfolder') and row['pk'] == 17)
        folder['fields']['library_content'] = [5]
        self.save_package()
        with self.assertRaisesMessage(CommandError, 'direct memberships'):
            self.run_import(apply=True)
        self.package = original; self.save_package()
        (self.media / 'contents/first.pdf').write_bytes(b'existing private file')
        with self.assertRaisesMessage(CommandError, 'never overwrites files'):
            self.run_import(apply=True)
        self.assertEqual((self.media / 'contents/first.pdf').read_bytes(), b'existing private file')

    def test_edited_imported_original_blocks_idempotent_rerun(self):
        self.run_import(apply=True)
        (self.media / 'contents/first.pdf').write_bytes(sample_pdf('Curator replaced original'))
        with self.assertRaisesMessage(CommandError, 'were changed'):
            self.run_import(apply=True)

    def test_postcommit_journal_failure_never_deletes_committed_originals(self):
        from content_management.management.commands.import_oasis_catalogue import replace_private
        calls = []

        def fail_final_journal(path, value):
            calls.append(value.get('state'))
            if value.get('state') == 'committed':
                raise OSError('Synthetic postcommit journal failure')
            return replace_private(path, value)

        with patch('content_management.management.commands.import_oasis_catalogue.replace_private', side_effect=fail_final_journal):
            with self.assertRaisesMessage(CommandError, 'postcommit journal failure'):
                self.run_import(apply=True)
        self.assertEqual(Content.objects.count(), 2)
        self.assertTrue((self.media / 'contents/first.pdf').is_file())
        self.assertTrue((self.target / 'catalogue-import/reviewed-manifest.json').is_file())
        self.assertTrue(self.run_import(apply=True)['already_imported'])

    def test_incomplete_or_extra_relation_closure_is_refused_before_writes(self):
        original = copy.deepcopy(self.package)
        self.package['fixture'] = [row for row in self.package['fixture'] if not (row['model'].endswith('.metadata') and row['pk'] == 9)]
        self.save_package()
        with self.assertRaisesMessage(CommandError, 'metadata must exactly match'):
            self.run_import(apply=True)
        self.assertFalse(Content.objects.exists())
        self.package = original
        self.package['fixture'].append({'model': 'content_management.user', 'pk': 99, 'fields': {'name': 'Unselected person'}})
        self.save_package()
        with self.assertRaisesMessage(CommandError, 'exact selected relation closure'):
            self.run_import(apply=True)
        self.assertFalse((self.target / 'catalogue-import').exists())

    def test_interrupted_file_copy_cleans_partial_destination_and_keeps_source(self):
        source_bytes = (self.originals / 'first.pdf').read_bytes()

        def interrupted(source, target, length):
            target.write(source.read(10))
            raise KeyboardInterrupt()

        with patch('content_management.management.commands.import_oasis_catalogue.shutil.copyfileobj', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.run_import(apply=True)
        self.assertFalse(Content.objects.exists())
        self.assertEqual(list((self.media / 'contents').iterdir()), [])
        self.assertEqual((self.originals / 'first.pdf').read_bytes(), source_bytes)
        self.assertEqual(json.loads((self.target / 'catalogue-import/journal.json').read_text())['state'], 'rolled_back')

    def test_interrupted_new_asset_write_removes_only_its_partial_file(self):
        from content_management.management.commands.import_oasis_catalogue import write_new
        path = self.media / 'images/logos/interrupted.png'
        with patch('content_management.management.commands.import_oasis_catalogue.os.fsync', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                write_new(path, b'partial synthetic asset')
        self.assertFalse(path.exists())

    def test_interrupted_journal_write_removes_its_temporary_file(self):
        from content_management.management.commands.import_oasis_catalogue import replace_private
        control = self.target / 'catalogue-import'
        with patch('content_management.management.commands.import_oasis_catalogue.os.fsync', side_effect=OSError('Synthetic disk-full write failure')):
            with self.assertRaisesMessage(OSError, 'disk-full'):
                replace_private(control / 'journal.json', {'state': 'installing'})
        self.assertEqual(list(control.iterdir()), [])
