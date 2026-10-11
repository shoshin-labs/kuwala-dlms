#!/usr/bin/env python3
"""Isolated synthetic FTS/exact-vector capacity measurements; never model quality.

Uses the same FTS5 table/query and sqlite-vec scalar cosine query as Oasis.
Larger cases deliberately exceed the installed trial's acceptance limits. This
is a component benchmark, not proof that its importer/reader supports them.
No model, production index, manifest, original PDF or service is opened.
"""
import argparse
import asyncio
import hashlib
import json
import math
import platform
import resource
import shutil
import sqlite3
import statistics
import struct
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

DIMENSIONS = 768
TOPICS = ('farming', 'water', 'learning', 'repair', 'building', 'health', 'energy')


def stats(values):
    ordered = sorted(values)
    return {'first_ms': round(values[0], 2), 'p50_ms': round(statistics.median(ordered), 2),
            'p95_ms': round(ordered[math.ceil(len(ordered) * .95) - 1], 2),
            'samples_ms': [round(value, 2) for value in values]}


def memory_available():
    file = Path('/proc/meminfo')
    if not file.is_file():
        return None
    for line in file.read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    return None


def connect(path, *, readonly=False):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) if readonly else sqlite3.connect(path)
    connection.execute('PRAGMA cache_size=-8192')
    connection.execute('PRAGMA temp_store=FILE')
    if readonly:
        connection.execute('PRAGMA query_only=ON')
    return connection


def measure(operation, repeats):
    samples, outcomes = [], []
    for _ in range(repeats):
        began = time.perf_counter()
        outcomes.append(operation())
        samples.append((time.perf_counter() - began) * 1000)
    return stats(samples) | {'result': outcomes[-1], 'outcomes': outcomes,
                            'timeouts': sum(isinstance(outcome, dict) and outcome.get('timed_out', False) for outcome in outcomes)}


def hash_files(files):
    for file in files:
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
    return len(files)


def build_fixture(directory, documents, per_document, text_chars, timeout):
    """Stream records: no corpus-sized Python arrays or model invocations."""
    began = time.perf_counter()
    deadline = began + timeout
    fts_path, vector_path = directory / 'index.sqlite3', directory / 'vectors.sqlite3'
    fts, vectors = connect(fts_path), connect(vector_path)
    fts.execute("CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED, document_id UNINDEXED, title, page UNINDEXED, text, tokenize='unicode61 remove_diacritics 2')")
    vectors.execute('CREATE TABLE vectors (id TEXT PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL, vector BLOB NOT NULL, norm REAL NOT NULL)')
    # Repeated deterministic vectors exercise actual distance computation, not
    # semantic relevance. Only 32 vectors are held in Python at a time.
    blobs = [struct.pack('<' + 'f' * DIMENSIONS, *[math.sin((column + 1) * (seed + 1) * .01)
             for column in range(DIMENSIONS)]) for seed in range(32)]
    norms = [math.sqrt(sum(value * value for value in struct.unpack('<' + 'f' * DIMENSIONS, blob))) for blob in blobs]
    for document in range(documents):
        if time.perf_counter() > deadline:
            raise SystemExit('Synthetic build exceeded its deadline; case is incomplete.')
        if document % 100 == 0:
            available = memory_available()
            if available is not None and available < 512 * 1024**2:
                raise SystemExit('Spare host memory fell below 512 MiB; synthetic build stopped.')
        if document % 250 == 0:
            print(json.dumps({'phase': 'fixture_progress', 'documents_written': document,
                              'target_documents': documents}), flush=True)
        identifier, title = f'synthetic-{document:06}', f'Synthetic capacity document {document:06}'
        topic = TOPICS[document % len(TOPICS)]
        fts_rows, vector_rows = [], []
        for passage in range(per_document):
            text = (f'{topic} synthetic capacity fixture record {document:06} page {passage:04}. No technical advice. ' * 30)[:text_chars]
            if document % 997 == 0 and passage == 0:
                text = 'syntheticneedle ' + text[16:]
            passage_id = 'P' + hashlib.sha256(f'{identifier}:{passage}'.encode()).hexdigest()[:24]
            row = (passage_id, identifier, title, passage + 1, text)
            fts_rows.append(row)
            seed = (document + passage) % len(blobs)
            vector_rows.append(row + (blobs[seed], norms[seed]))
        fts.executemany('INSERT INTO passages VALUES (?, ?, ?, ?, ?)', fts_rows)
        vectors.executemany('INSERT INTO vectors VALUES (?, ?, ?, ?, ?, ?, ?)', vector_rows)
        if document % 100 == 99:
            fts.commit()
            vectors.commit()
    fts.commit()
    vectors.commit()
    assert fts.execute('SELECT COUNT(*) FROM passages').fetchone()[0] == documents * per_document
    assert vectors.execute('SELECT COUNT(*) FROM vectors').fetchone()[0] == documents * per_document
    fts.close()
    vectors.close()
    return fts_path, vector_path, round(time.perf_counter() - began, 2)


def query_fts(path, selected, query, seconds):
    connection = connect(path, readonly=True)
    deadline = time.monotonic() + seconds
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        placeholders = ','.join('?' for _ in selected)
        rows = connection.execute("SELECT id, document_id, title, page, snippet(passages,4,'','',' … ',32) AS preview FROM passages WHERE passages MATCH ? AND document_id IN (" + placeholders + ') ORDER BY bm25(passages,0,0,2,0,1), id LIMIT 10', [query, *selected]).fetchall()
        assert len(rows) <= 10 and all(row[1] in selected for row in rows)
        return {'returned': len(rows), 'timed_out': False}
    except sqlite3.OperationalError as exc:
        if 'interrupted' not in str(exc):
            raise
        return {'returned': None, 'timed_out': True, 'deadline_seconds': seconds}
    finally:
        connection.close()


def query_vectors(path, selected, blob, seconds):
    import sqlite_vec
    connection = connect(path, readonly=True)
    connection.enable_load_extension(True)
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)
    deadline = time.monotonic() + seconds
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        placeholders = ','.join('?' for _ in selected)
        rows = connection.execute('SELECT id, document_id, title, page, text, vec_distance_cosine(vector,?) AS distance FROM vectors WHERE document_id IN (' + placeholders + ') ORDER BY distance,id LIMIT 10', [blob, *selected]).fetchall()
        assert len(rows) <= 10 and all(row[1] in selected and math.isfinite(row[5]) for row in rows)
        return {'returned': len(rows), 'timed_out': False}
    except sqlite3.OperationalError as exc:
        if 'interrupted' not in str(exc):
            raise
        return {'returned': None, 'timed_out': True, 'deadline_seconds': seconds}
    finally:
        connection.close()


def browse(station_root, count, repeats):
    """Actual visitor route/template with an explicitly synthetic metadata provider."""
    sys.path.insert(0, str(station_root))
    from app.web.routes import library_index
    from starlette.requests import Request
    records = [{'id': f'synthetic-{index:06}', 'title': f'Synthetic capacity document {index:06}',
                'publisher': 'Kuwala synthetic benchmark', 'filename': f'synthetic-{index:06}.pdf'}
               for index in range(count)]
    groups = [{'id': 'synthetic-all', 'label': 'All synthetic documents',
               'document_ids': [item['id'] for item in records]}]
    groups += [{'id': 'synthetic-' + topic, 'label': topic.title() + ' (synthetic)',
                'document_ids': [item['id'] for index, item in enumerate(records) if index % len(TOPICS) == position]}
               for position, topic in enumerate(TOPICS)]
    library = SimpleNamespace(sources=lambda: records, libraries=lambda: groups, sections=lambda: [])
    state = SimpleNamespace(strings=json.loads((station_root / 'app/web/locales/en.json').read_text()),
                            retriever=None, pdf_library=library,
                            settings=SimpleNamespace(pdf_library_manage_url=''),
                            library_preview_notice='Synthetic capacity fixture. No model or technical advice.')
    results = {}
    for source in ('', 'synthetic-all', 'synthetic-water'):
        request = Request({'type': 'http', 'method': 'GET', 'scheme': 'http',
                           'path': '/library', 'root_path': '', 'query_string': b'', 'headers': [],
                           'server': ('127.0.0.1', 1), 'client': ('127.0.0.1', 1),
                           'app': SimpleNamespace(state=state)})
        def render():
            response = asyncio.run(library_index(request, q='', source=source))
            assert response.status_code == 200 and b'synthetic' in response.body.lower()
            return {'html_bytes': len(response.body), 'document_links': response.body.count(b'class="document-row"')}
        results[source or 'overview'] = measure(render, repeats)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New private directory; refuses existing paths.')
    parser.add_argument('--documents', type=int, nargs='+', default=[1000, 5000])
    parser.add_argument('--passages-per-document', type=int, default=221)
    parser.add_argument('--text-chars', type=int, default=1000)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--query-timeout', type=float, default=15)
    parser.add_argument('--build-timeout', type=float, default=600, help='Maximum fixture-build seconds per case (1..1800).')
    parser.add_argument('--station-root', type=Path, help='Optional read-only source for real visitor template timings.')
    args = parser.parse_args()
    if (not args.documents or len(set(args.documents)) != len(args.documents)
            or any(not 1 <= size <= 5000 for size in args.documents)
            or not 1 <= args.passages_per_document <= 221 or not 1 <= args.repeats <= 10
            or not 200 <= args.text_chars <= 1400 or not 1 <= args.query_timeout <= 30
            or not 1 <= args.build_timeout <= 1800):
        parser.error('Use unique document sizes 1–5000, passages 1–221, repeats 1–10, text 200–1400, query timeout 1–30 and build timeout 1–1800.')
    output = args.output.expanduser().absolute()
    if output.exists() or output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        parser.error('Output must be a fresh directory without symlink ancestors; no existing state is changed.')
    if args.station_root and not (args.station_root / 'app/library/semantic.py').is_file():
        parser.error('Station source directory is unavailable.')
    with closing(sqlite3.connect(':memory:')) as preflight:
        variable_limit = preflight.getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER)
    if variable_limit < max(args.documents) + 1:
        parser.error('SQLite cannot bind the largest document scope; fixture construction has not started.')
    output.mkdir(mode=0o700, parents=True)
    (output / 'synthetic-fixtures.json').write_text(json.dumps({'synthetic': True, 'purpose': __doc__}) + '\n')
    import sqlite_vec
    report = {'synthetic': True, 'method': 'Native FTS5 and exact sqlite-vec queries; deterministic artificial text/vectors; no extraction, embeddings or model answers.',
              'limits': 'Installed trial limits are not changed. Larger results are component projections only.',
              'cache_state': 'OS caches not cleared. First request follows fixture creation; p95 has very few samples.',
              'host': platform.node(), 'machine': platform.machine(), 'python': platform.python_version(),
              'sqlite': sqlite3.sqlite_version, 'sqlite_vec': sqlite_vec.__version__,
              'dimensions': DIMENSIONS, 'repeats': args.repeats, 'text_chars': args.text_chars,
              'sqlite_cache_kib_per_connection': 8192, 'sqlite_variable_limit': variable_limit,
              'station_root': str(args.station_root) if args.station_root else None, 'cases': []}
    query_blob = struct.pack('<' + 'f' * DIMENSIONS, *[math.sin((column + 1) * .013) for column in range(DIMENSIONS)])
    for size in args.documents:
        passages = size * args.passages_per_document
        # Retain at least12GiB plus a conservative peak estimate. Build one
        # fixture at a time; temporary databases are removed after each case.
        required = 12 * 1024**3 + passages * (DIMENSIONS * 4 + args.text_chars * 3 + 1024)
        free = shutil.disk_usage(output).free
        available = memory_available()
        if free < required or available is not None and available < 768 * 1024**2:
            raise SystemExit('Insufficient spare disk or memory for an isolated case; no production changes made.')
        print(json.dumps({'phase': 'building_synthetic_fixture', 'documents': size, 'passages': passages}), flush=True)
        with tempfile.TemporaryDirectory(prefix='synthetic-index-', dir=output) as temporary:
            files = build_fixture(Path(temporary), size, args.passages_per_document, args.text_chars, args.build_timeout)
            fts_path, vector_path, build_seconds = files
            all_ids = [f'synthetic-{index:06}' for index in range(size)]
            scopes = {'all': all_ids, 'one-library': all_ids[1::len(TOPICS)], 'one-document': all_ids[:1]}
            case = {'documents': size, 'passages': passages, 'passages_per_document': args.passages_per_document,
                    'build_seconds': build_seconds, 'lexical_bytes': fts_path.stat().st_size,
                    'vector_bytes': vector_path.stat().st_size, 'metrics': {},
                    'vector_query_timeout_seconds': args.query_timeout, 'fts_query_timeout_seconds': 1.5}
            case['metrics']['hash-both-index-files'] = measure(lambda: hash_files((fts_path, vector_path)), args.repeats)
            for scope, identifiers in scopes.items():
                for query, label in (('"syntheticneedle"', 'rare'), ('"water"', 'common'), ('"absentcapacityword"', 'miss')):
                    case['metrics'][f'fts-{label}-{scope}'] = measure(lambda: query_fts(fts_path, identifiers, query, 1.5), args.repeats)
                case['metrics'][f'exact-vector-{scope}'] = measure(lambda: query_vectors(vector_path, identifiers, query_blob, args.query_timeout), args.repeats)
            if args.station_root:
                case['visitor_render'] = browse(args.station_root, size, args.repeats)
            case['cumulative_process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 if sys.platform == 'darwin' else 1)
            report['cases'].append(case)
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({'phase': 'case_complete', **case}), flush=True)
    print(json.dumps({'phase': 'finished', 'report': str(output / 'report.json')}), flush=True)


if __name__ == '__main__':
    main()
