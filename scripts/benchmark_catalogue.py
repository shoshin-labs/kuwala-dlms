#!/usr/bin/env python3
"""Measure bounded catalogue reads in marked, isolated synthetic preview state."""
import argparse
import hashlib
import json
import math
import os
import shlex
import sqlite3
import stat
import sys
import time
from contextlib import closing
from datetime import datetime, timezone as utc_timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = 'oasis-catalogue-scale-v1'
VERSION = 'synthetic-scale-v1'
ORIGINAL = 'media/contents/scale-fixture.pdf'
PURPOSE = 'Synthetic catalogue pagination, section and metadata-search benchmark'
DESCRIPTION = 'Synthetic scale fixture. No technical advice.'
COPYRIGHT = 'Synthetic scale fixture by Kuwala contributors.'
RIGHTS = 'CC0-1.0 applies only to this original synthetic fixture.'
LIBRARIES = ('Farming (synthetic)', 'Water (synthetic)', 'Learning (synthetic)')


class UnsafeState(ValueError):
    pass


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--documents', type=int, choices=(1000, 5000), default=5000)
    parser.add_argument('--repeats', type=int, default=7, help='Samples per connection-cold and steady phase (1..100).')
    parser.add_argument('--output-root', type=Path, help='A scale-* directory beneath this checkout\'s .preview; relative paths use the checkout root.')
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 100:
        parser.error('--repeats must be between 1 and 100.')
    return args


def safe_state_path(output_root, documents, *, root=ROOT):
    root = root.resolve()
    preview = root / '.preview'
    output_root = output_root or preview / ('scale-check' if documents == 5000 else 'scale-check-1000')
    state = Path(os.path.abspath(root / output_root if not output_root.is_absolute() else output_root))
    try:
        relative = state.relative_to(preview)
    except ValueError as error:
        raise UnsafeState('Output must be inside this checkout\'s .preview/scale-* directory.') from error
    if not relative.parts or not relative.parts[0].startswith('scale-'):
        raise UnsafeState('Use a separate .preview/scale-* directory, never the main preview state.')
    # Check unresolved ancestors: resolve() alone would hide a directory link.
    for path in (preview, *(preview.joinpath(*relative.parts[:index + 1]) for index in range(len(relative.parts)))):
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise UnsafeState('Scale fixture directories must be real directories, never symlinks.')
    return state


def check_entries(state):
    for path in state.rglob('*'):
        mode = path.lstat()
        if stat.S_ISLNK(mode.st_mode) or not (stat.S_ISDIR(mode.st_mode) or stat.S_ISREG(mode.st_mode)):
            raise UnsafeState('Scale state must not contain symlinks or special files.')
        if stat.S_ISREG(mode.st_mode) and mode.st_nlink != 1:
            raise UnsafeState('Scale files must not be hard-linked to another state.')


def validate_fixture_database(state, documents):
    """Read-only preflight before Django can migrate or write existing state."""
    database = state / 'catalogue.sqlite3'
    if not database.is_file() or not (state / ORIGINAL).is_file():
        raise UnsafeState('Marked fixture state is incomplete; use a fresh scale-* directory.')
    if database.stat().st_size > 4 * 1024 * 1024 + documents * 4096:
        raise UnsafeState('The database exceeds the bounded synthetic fixture size.')
    original = state / ORIGINAL
    if original.stat().st_size > 4096:
        raise UnsafeState('The shared original is not the small synthetic fixture.')
    payload = original.read_bytes()
    if not (payload.startswith(b'%PDF-') and payload.rstrip().endswith(b'%%EOF')
            and b'Synthetic scale check original; no technical advice' in payload):
        raise UnsafeState('The shared original is not the labelled synthetic fixture.')
    try:
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            versions = db.execute('SELECT id, substr(library_name,1,301), substr(version_number,1,301) FROM content_management_libraryversion LIMIT 2').fetchall()
            if len(versions) != 1 or versions[0][2] != VERSION or versions[0][1] != f'Synthetic scale check: {documents:,} PDFs':
                raise UnsafeState('Existing database is not this synthetic scale fixture.')
            original_bytes = len(payload)
            rows = db.execute('''SELECT id,
                title = printf('Synthetic PDF %06d', id) AND display_title = title
                AND description = ? AND file_name = 'scale-fixture.pdf'
                AND content_file = 'contents/scale-fixture.pdf' AND copyright_notes = ?
                AND rights_statement = ? AND active = 1 AND filesize = ?
                FROM content_management_content ORDER BY id LIMIT ?''',
                (DESCRIPTION, COPYRIGHT, RIGHTS, original_bytes, documents + 1)).fetchall()
            if len(rows) != documents:
                raise UnsafeState('Benchmark document count changed; use a fresh separate scale-* directory.')
            for index, row in enumerate(rows, 1):
                if row != (index, 1):
                    raise UnsafeState('Benchmark records changed; no existing records will be overwritten.')
            folders = db.execute('SELECT id,substr(folder_name,1,301),parent_id,version_id FROM content_management_libraryfolder ORDER BY id LIMIT 16').fetchall()
            if len(folders) != 15 or [row[1] for row in folders[:3]] != list(LIBRARIES) or any(row[2] is not None for row in folders[:3]):
                raise UnsafeState('Benchmark library structure changed; use a fresh separate scale-* directory.')
            for index, row in enumerate(folders[3:]):
                if row[1:] != (f'Synthetic section {index + 1:02}', folders[index % 3][0], versions[0][0]):
                    raise UnsafeState('Benchmark section structure changed.')
            if any(row[3] != versions[0][0] for row in folders):
                raise UnsafeState('Benchmark folder catalogue changed.')
            memberships = db.execute('SELECT libraryfolder_id,content_id FROM content_management_libraryfolder_library_content LIMIT ?', (2 * documents + 1,)).fetchall()
            actual = set(memberships)
            expected = {(folder, row[0]) for index, row in enumerate(rows)
                        for folder in (folders[index % 3][0], folders[3 + index % 12][0])}
            if len(memberships) != 2 * documents or actual != expected or db.execute('SELECT id FROM content_management_metadata LIMIT 1').fetchone():
                raise UnsafeState('Benchmark memberships or metadata changed.')
    except (sqlite3.Error, OSError) as error:
        raise UnsafeState('Existing fixture database cannot be verified read-only; no changes made.') from error


def marker_data(documents, *, ready=False, original_sha256=None):
    return {'synthetic': True, 'fixture': FIXTURE, 'documents': documents, 'purpose': PURPOSE,
            'status': 'ready' if ready else 'preparing', 'shared_original': ORIGINAL,
            'original_sha256': original_sha256}


def prepare_state(state, documents):
    """Claim only empty state; refuse foreign/incomplete state before any write."""
    marker = state / 'synthetic-fixtures.json'
    if state.exists() and any(state.iterdir()):
        check_entries(state)
        try:
            if not marker.is_file() or marker.stat().st_size > 4096:
                raise UnsafeState('Existing state is not a marked synthetic benchmark; no changes made.')
            known = json.loads(marker.read_text())
        except (OSError, ValueError) as error:
            raise UnsafeState('Existing state has no valid synthetic benchmark marker; no changes made.') from error
        legacy = known == {'synthetic': True, 'purpose': '5,000-document pagination and section benchmark'} and documents == 5000
        if not legacy and (not isinstance(known, dict) or known.get('synthetic') is not True
                or known.get('fixture') != FIXTURE or type(known.get('documents')) is not int
                or known['documents'] != documents or known.get('purpose') != PURPOSE
                or known.get('status') != 'ready' or known.get('shared_original') != ORIGINAL):
            raise UnsafeState('Existing state is not this completed synthetic benchmark; use a fresh scale-* directory.')
        validate_fixture_database(state, documents)
        if not legacy and known.get('original_sha256') != hashlib.sha256((state / ORIGINAL).read_bytes()).hexdigest():
            raise UnsafeState('The synthetic original changed; no existing files will be overwritten.')
        return True
    state.mkdir(parents=True, exist_ok=True)
    with marker.open('x') as stream:
        json.dump(marker_data(documents), stream)
        stream.write('\n')
    return False


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    return ordered[lower] + (ordered[math.ceil(position)] - ordered[lower]) * (position - lower)


def phase_summary(samples):
    times = [sample['milliseconds'] for sample in samples]
    return {'samples': samples, 'p50_ms': round(percentile(times, .5), 3), 'p95_ms': round(percentile(times, .95), 3),
            'min_ms': round(min(times), 3), 'max_ms': round(max(times), 3),
            'queries_min': min(sample['queries'] for sample in samples), 'queries_max': max(sample['queries'] for sample in samples),
            'response_bytes_min': min(sample['bytes'] for sample in samples), 'response_bytes_max': max(sample['bytes'] for sample in samples)}


def benchmark(state, documents, repeats, reused):
    os.environ.update({'OASIS_PREVIEW_STATE_ROOT': str(state), 'DJANGO_SETTINGS_MODULE': 'dlms.preview_settings', 'OASIS_PREVIEW_CURATOR': '0'})
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection, transaction
    from django.test import Client
    from django.test.utils import CaptureQueriesContext
    from django.utils import timezone
    from content_management.models import Content, LibraryFolder, LibraryVersion
    from content_management.management.commands.seed_oasis_preview import sample_pdf

    if Path(settings.DATABASES['default']['NAME']).resolve() != state / 'catalogue.sqlite3' or Path(settings.CONTENTS_ROOT).resolve() != state / 'media' / 'contents':
        raise UnsafeState('Django did not select the isolated benchmark database and originals.')
    pdf = sample_pdf('Synthetic scale check original; no technical advice')
    if reused and (state / ORIGINAL).read_bytes() != pdf:
        raise UnsafeState('The original is not the expected synthetic PDF.')
    call_command('migrate', interactive=False, verbosity=0)
    if reused:
        version = LibraryVersion.objects.get(version_number=VERSION)
        sections = list(LibraryFolder.objects.filter(version=version, parent__isnull=False).order_by('id'))
    else:
        with (state / ORIGINAL).open('xb') as stream:
            stream.write(pdf)
        with transaction.atomic():
            version = LibraryVersion.objects.create(library_name=f'Synthetic scale check: {documents:,} PDFs', version_number=VERSION, created_on=timezone.now())
            roots = [LibraryFolder.objects.create(version=version, folder_name=name) for name in LIBRARIES]
            sections = [LibraryFolder.objects.create(version=version, parent=roots[index % 3], folder_name=f'Synthetic section {index + 1:02}') for index in range(12)]
            now = timezone.now()
            Content.objects.bulk_create([Content(title=f'Synthetic PDF {index + 1:06}', display_title=f'Synthetic PDF {index + 1:06}',
                description=DESCRIPTION, file_name='scale-fixture.pdf', content_file='contents/scale-fixture.pdf', filesize=len(pdf), modified_on=now,
                copyright_notes=COPYRIGHT, rights_statement=RIGHTS) for index in range(documents)])
            memberships = LibraryFolder.library_content.through
            memberships.objects.bulk_create([memberships(libraryfolder_id=folder.id, content_id=document.id)
                for index, document in enumerate(Content.objects.order_by('id')) for folder in (roots[index % 3], sections[index % 12])])
        (state / 'synthetic-fixtures.json').write_text(json.dumps(marker_data(documents, ready=True, original_sha256=hashlib.sha256(pdf).hexdigest())) + '\n')

    # These fixtures measure catalogue metadata, not extracted pages or vectors.
    ids = list(Content.objects.order_by('id').values_list('id', flat=True))
    folder_ids = set(LibraryFolder.objects.values_list('id', flat=True))
    scope = f'catalogue_version={version.id}'
    base = '/api/oasis/catalogue/documents/?' + scope
    search_serial = min(4200, documents)
    last_page = math.ceil(documents / 24)
    cases = [
        ('tree', '/api/oasis/catalogue/?' + scope, None, None),
        ('first-page', base, ids[:24], documents),
        ('second-page', base + '&page=2', ids[24:48], documents),
        ('last-page', base + f'&page={last_page}', ids[(last_page - 1) * 24:], documents),
        ('max-page-size', base + '&size=10000', ids[:100], documents),
        ('section', base + f'&folder_id={sections[0].id}', ids[::12][:24], len(ids[::12])),
        ('search', base + f'&q={search_serial:06}', [ids[search_serial - 1]], 1),
        ('section-search-miss', base + f'&folder_id={sections[0].id}&q=000002', [], 0),
    ]
    client = Client()

    def request_case(name, url, expected_ids, expected_count):
        started = time.perf_counter()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise UnsafeState(f'Benchmark {name} failed: HTTP {response.status_code}')
        data = response.json()['data']
        returned = data.get('results', data.get('folders', []))
        if len(queries) > 8:
            raise UnsafeState(f'Benchmark {name} used unbounded related-data queries: {len(queries)}.')
        if name == 'tree':
            if data['document_count'] != documents or {folder['id'] for folder in returned} != folder_ids or any('library_content' in folder for folder in returned):
                raise UnsafeState('Unexpected synthetic tree counts or unbounded folder payload.')
            section = next(folder for folder in returned if folder['id'] == sections[0].id)
            if section['document_count'] != len(ids[::12]):
                raise UnsafeState('Synthetic section overview count is incorrect.')
        else:
            expected_size = 100 if name == 'max-page-size' else 24
            if data['count'] != expected_count or data['page_size'] != expected_size or [item['id'] for item in returned] != expected_ids:
                raise UnsafeState(f'Unexpected synthetic {name} pagination, section or search results.')
            if returned and not any(' LIMIT ' in query['sql'].upper() for query in queries):
                raise UnsafeState('Document pagination did not issue a bounded SQL query.')
            if name == 'first-page' and (data['previous'] is not None or data['next'] is None) or name == 'last-page' and data['next'] is not None:
                raise UnsafeState('Pagination boundary links are incorrect.')
        if len(response.content) > 8192 + (100 if name == 'max-page-size' else 24) * 2048:
            raise UnsafeState('Synthetic response exceeds its bounded fixture payload.')
        return {'milliseconds': round(elapsed, 3), 'queries': len(queries), 'bytes': len(response.content),
                'count': data.get('count', data.get('document_count')), 'returned': len(returned)}

    results = []
    for name, url, expected_ids, expected_count in cases:
        phases = {}
        for phase in ('connection_cold', 'steady'):
            samples = []
            for _ in range(repeats):
                if phase == 'connection_cold':
                    connection.close()
                samples.append(request_case(name, url, expected_ids, expected_count))
            phases[phase] = phase_summary(samples)
        results.append({'name': name, 'url': url, 'validated': True, **phases})
    connection.close()
    return {'schema_version': 1, 'synthetic': True, 'fixture': FIXTURE, 'documents': documents, 'libraries': 3, 'sections': 12,
            'shared_originals': 1, 'reused_state': reused, 'repeats_per_phase': repeats,
            'generated_at_utc': datetime.now(utc_timezone.utc).isoformat(), 'state_root': str(state),
            'measurement': 'In-process Django test client; query capture and preview DEBUG enabled; no network or browser rendering.',
            'cold_definition': 'SQLite connection closed before each connection_cold sample; OS/page caches are not evicted. First request may include URL/module initialization.',
            'percentile_method': 'Linear interpolation over the requested samples; small local samples are not a production latency guarantee.',
            'limitations': ['One labelled synthetic PDF original is shared by all catalogue records.', 'No PDF extraction, OCR, full-text/vector index, model inference, concurrent-user or device performance is measured.'],
            'results': results}


def main(argv=None):
    args = arguments(argv)
    try:
        state = safe_state_path(args.output_root, args.documents, root=ROOT)
        reused = prepare_state(state, args.documents)
        report = benchmark(state, args.documents, args.repeats, reused)
        (state / 'benchmark.json').write_text(json.dumps(report, indent=2) + '\n')
    except (UnsafeState, OSError) as error:
        print(f'Catalogue benchmark refused: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    print('Synthetic records share one labelled original PDF; extraction, vector and model performance are not measured.')
    print('Optional visitor preview (loopback only):')
    print(f'OASIS_PREVIEW_STATE_ROOT={shlex.quote(str(state))} {shlex.quote(sys.executable)} manage.py runserver 127.0.0.1:8792 --noreload --settings=dlms.preview_settings')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
