"""Safety checks for the disposable catalogue benchmark, without Django setup."""
import contextlib
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('benchmark_catalogue.py')
spec = importlib.util.spec_from_file_location('oasis_catalogue_benchmark', SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class CatalogueBenchmarkSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / '.preview' / 'scale-safety'

    def run_refused(self, state=None, *, documents=1000):
        with patch.object(benchmark, 'ROOT', self.root), patch.object(benchmark, 'benchmark') as execute, contextlib.redirect_stderr(io.StringIO()):
            # main explicitly supplies ROOT so tests can use a disposable checkout.
            result = benchmark.main(['--documents', str(documents), '--output-root', str(state or self.state)])
        self.assertEqual(result, 1)
        execute.assert_not_called()

    def test_import_and_bad_arguments_never_initialize_django(self):
        self.assertNotIn('django', sys.modules)
        for args in (['--documents', '84'], ['--repeats', '0'], ['--repeats', '101']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                benchmark.arguments(args)
        self.assertFalse(self.state.exists())

    def test_output_paths_cannot_select_main_preview_outside_or_linked_state(self):
        for path in (self.root, self.root / '.preview', self.root / '.preview' / 'media',
                     self.root / '.preview' / 'scale-safety' / '..' / '..' / 'operator-state',
                     self.root / 'outside' / 'scale-safety'):
            with self.subTest(path=path), self.assertRaises(benchmark.UnsafeState):
                benchmark.safe_state_path(path, 1000, root=self.root)
        outside = self.root / 'outside'; outside.mkdir()
        preview = self.root / '.preview'; preview.mkdir()
        (preview / 'scale-link').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(benchmark.UnsafeState):
            benchmark.safe_state_path(preview / 'scale-link' / 'nested', 1000, root=self.root)
        self.assertFalse(any(outside.iterdir()))
        self.assertEqual(benchmark.safe_state_path(None, 5000, root=self.root), preview / 'scale-check')
        self.assertEqual(benchmark.safe_state_path(None, 1000, root=self.root), preview / 'scale-check-1000')

    def test_unmarked_database_or_preexisting_original_is_not_migrated_or_overwritten(self):
        self.state.mkdir(parents=True)
        database = self.state / 'catalogue.sqlite3'
        with contextlib.closing(sqlite3.connect(database)) as connection, connection:
            connection.execute('CREATE TABLE operator_sentinel (value TEXT)')
            connection.execute("INSERT INTO operator_sentinel VALUES ('private catalogue')")
        original = self.state / 'media' / 'contents' / 'scale-fixture.pdf'
        original.parent.mkdir(parents=True)
        original.write_bytes(b'operator original must survive')
        before = {path.relative_to(self.state): path.read_bytes() for path in self.state.rglob('*') if path.is_file()}
        self.run_refused()
        self.assertEqual(before, {path.relative_to(self.state): path.read_bytes() for path in self.state.rglob('*') if path.is_file()})
        self.assertFalse((self.state / 'synthetic-fixtures.json').exists())

    def test_foreign_malformed_or_wrong_count_marker_never_reaches_writes(self):
        self.state.mkdir(parents=True)
        marker = self.state / 'synthetic-fixtures.json'
        valid = benchmark.marker_data(1000, ready=True, original_sha256='0' * 64)
        cases = ('malformed', '[]', json.dumps({'synthetic': True}),
                 json.dumps({**valid, 'documents': 5000}), json.dumps({**valid, 'documents': True}),
                 json.dumps({**valid, 'fixture': 'some-other-synthetic-preview'}),
                 json.dumps({**valid, 'status': 'preparing'}))
        for value in cases:
            with self.subTest(value=value):
                marker.write_text(value)
                self.run_refused()
                self.assertEqual(marker.read_text(), value)
                self.assertEqual(list(self.state.iterdir()), [marker])
        # An exact marker alone cannot turn a foreign/live DB into benchmark state.
        marker.write_text(json.dumps(valid))
        database = self.state / 'catalogue.sqlite3'; database.write_bytes(b'not a synthetic database')
        original = self.state / benchmark.ORIGINAL; original.parent.mkdir(parents=True); original.write_bytes(b'not a fixture')
        self.run_refused()
        self.assertEqual(database.read_bytes(), b'not a synthetic database')
        self.assertEqual(original.read_bytes(), b'not a fixture')

    def test_database_marker_original_report_and_nested_links_are_rejected(self):
        outside = self.root / 'operator-file'; outside.write_bytes(b'outside sentinel')
        for name in ('catalogue.sqlite3', 'synthetic-fixtures.json', benchmark.ORIGINAL, 'benchmark.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as directory:
                state = Path(directory); target = state / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(outside)
                with self.assertRaises(benchmark.UnsafeState):
                    benchmark.prepare_state(state, 1000)
                self.assertTrue(target.is_symlink())
                self.assertEqual(outside.read_bytes(), b'outside sentinel')
        self.state.mkdir(parents=True)
        (self.state / 'media').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(benchmark.UnsafeState):
            benchmark.prepare_state(self.state, 1000)

    def test_fresh_empty_state_is_marked_before_django_can_run(self):
        self.assertFalse(benchmark.prepare_state(self.state, 1000))
        self.assertEqual(json.loads((self.state / 'synthetic-fixtures.json').read_text()), benchmark.marker_data(1000))
        self.assertFalse((self.state / 'catalogue.sqlite3').exists())
        with self.assertRaises(benchmark.UnsafeState):
            benchmark.prepare_state(self.state, 1000)

    def test_oversized_marked_original_is_rejected_before_reading_or_opening_database(self):
        self.state.mkdir(parents=True)
        marker = self.state / 'synthetic-fixtures.json'
        marker.write_text(json.dumps(benchmark.marker_data(1000, ready=True, original_sha256='0' * 64)))
        database = self.state / 'catalogue.sqlite3'; database.write_bytes(b'unchanged database sentinel')
        original = self.state / benchmark.ORIGINAL; original.parent.mkdir(parents=True)
        original.write_bytes(b'x' * 4097)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Oversized original must not be read')):
            with patch.object(benchmark.sqlite3, 'connect', side_effect=AssertionError('Database must not be opened')):
                self.run_refused()
        self.assertEqual(database.read_bytes(), b'unchanged database sentinel')
        self.assertEqual(original.read_bytes(), b'x' * 4097)


if __name__ == '__main__':
    unittest.main()
