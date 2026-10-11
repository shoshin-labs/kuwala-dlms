"""Refusal, timing and scope checks for the isolated native benchmark."""
import contextlib
import importlib.util
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('library_search_benchmark', Path(__file__).with_name('benchmark_library_search.py'))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class LibrarySearchBenchmarkTests(unittest.TestCase):
    def test_median_with_an_even_sample_count(self):
        self.assertEqual(benchmark.stats([20, 10])['p50_ms'], 15)

    def test_timeout_in_an_earlier_sample_is_retained(self):
        outcomes = iter(({'returned': None, 'timed_out': True}, {'returned': 10, 'timed_out': False}))
        report = benchmark.measure(lambda: next(outcomes), 2)
        self.assertEqual(report['timeouts'], 1)
        self.assertEqual(len(report['outcomes']), 2)
        self.assertTrue(report['outcomes'][0]['timed_out'])

    def refused(self, output, *args):
        with patch.object(sys, 'argv', ['benchmark', '--output', str(output), *args]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            benchmark.main()
        self.assertEqual(error.exception.code, 2)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve()
            sentinel = output / 'report.json'
            sentinel.write_text('operator data')
            self.refused(output)
            self.assertEqual(sentinel.read_text(), 'operator data')
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_symlink_ancestor_is_refused_without_changing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            destination = root / 'private'; destination.mkdir()
            link = root / 'link'; link.symlink_to(destination, target_is_directory=True)
            self.refused(link / 'new-benchmark')
            self.assertEqual(list(destination.iterdir()), [])

    def test_bad_capacity_arguments_create_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / 'new-benchmark'
            for arguments in (('--documents', '5001'), ('--documents', '1000', '1000'),
                              ('--passages-per-document', '222'), ('--repeats', '11'), ('--query-timeout', '31')):
                with self.subTest(arguments=arguments):
                    self.refused(output, *arguments)
                    self.assertFalse(output.exists())

    def test_fixture_and_lexical_results_obey_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            files = benchmark.build_fixture(Path(temporary), 14, 4, 200, 10)
            fts, vectors, _ = files
            with contextlib.closing(sqlite3.connect(vectors)) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM vectors').fetchone()[0], 56)
            self.assertEqual(benchmark.query_fts(fts, ['synthetic-000000'], '"syntheticneedle"', 1.5),
                             {'returned': 1, 'timed_out': False})
            self.assertEqual(benchmark.query_fts(fts, ['synthetic-000001'], '"syntheticneedle"', 1.5),
                             {'returned': 0, 'timed_out': False})
            self.assertEqual(benchmark.query_fts(fts, ['synthetic-000001'], '"absentcapacityword"', 1.5),
                             {'returned': 0, 'timed_out': False})


if __name__ == '__main__':
    unittest.main()
