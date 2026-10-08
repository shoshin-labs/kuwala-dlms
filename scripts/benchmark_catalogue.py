#!/usr/bin/env python3
"""Build an isolated synthetic catalogue and measure bounded read queries."""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / '.preview' / 'scale-check'
if any(path.is_symlink() for path in (ROOT / '.preview', STATE)):
    raise SystemExit('Scale fixture directories must not be symlinks.')
STATE.mkdir(parents=True, exist_ok=True)
marker = STATE / 'synthetic-fixtures.json'
if (STATE / 'catalogue.sqlite3').is_file():
    try:
        known_fixture = json.loads(marker.read_text()).get('synthetic') is True
    except (OSError, ValueError):
        known_fixture = False
    if not known_fixture:
        raise SystemExit('Existing state is not a marked synthetic benchmark; no changes made.')
os.environ['OASIS_PREVIEW_STATE_ROOT'] = str(STATE)
os.environ['DJANGO_SETTINGS_MODULE'] = 'dlms.preview_settings'
os.environ['OASIS_PREVIEW_CURATOR'] = '0'
sys.path.insert(0, str(ROOT))

import django

django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from content_management.models import Content, LibraryFolder, LibraryVersion
from content_management.management.commands.seed_oasis_preview import sample_pdf

call_command('migrate', interactive=False, verbosity=0)
count = 5000
if Content.objects.exists():
    if not marker.is_file() or json.loads(marker.read_text()).get('synthetic') is not True:
        raise SystemExit('Existing state is not a marked synthetic benchmark; no changes made.')
    if Content.objects.count() != count or LibraryVersion.objects.count() != 1:
        raise SystemExit('Benchmark state has changed; use a fresh separate scale-check directory.')
    version = LibraryVersion.objects.get(version_number='synthetic-scale-v1')
    sections = list(LibraryFolder.objects.filter(version=version, parent__isnull=False).order_by('id'))
else:
    if LibraryVersion.objects.exists() or LibraryFolder.objects.exists():
        raise SystemExit('Benchmark needs an empty separate database; no changes made.')
    version = LibraryVersion.objects.create(
        library_name='Synthetic scale check: 5,000 PDFs', version_number='synthetic-scale-v1',
        created_on=timezone.now(),
    )
    roots = [LibraryFolder.objects.create(version=version, folder_name=name) for name in (
        'Farming (synthetic)', 'Water (synthetic)', 'Learning (synthetic)',
    )]
    sections = [LibraryFolder.objects.create(
        version=version, parent=roots[index % 3], folder_name=f'Synthetic section {index + 1:02}',
    ) for index in range(12)]
    pdf = sample_pdf('Synthetic scale check original; no technical advice')
    Path(settings.CONTENTS_ROOT, 'scale-fixture.pdf').write_bytes(pdf)
    Content.objects.bulk_create([Content(
        title=f'Synthetic PDF {index + 1:06}', display_title=f'Synthetic PDF {index + 1:06}',
        description='Synthetic scale fixture. No technical advice.', file_name='scale-fixture.pdf',
        content_file='contents/scale-fixture.pdf', filesize=len(pdf), modified_on=timezone.now(),
        copyright_notes='Synthetic scale fixture by Kuwala contributors.',
        rights_statement='CC0-1.0 applies only to this original synthetic fixture.',
    ) for index in range(count)])
    memberships = LibraryFolder.library_content.through
    memberships.objects.bulk_create([
        memberships(libraryfolder_id=folder.id, content_id=document.id)
        for index, document in enumerate(Content.objects.order_by('id'))
        for folder in (roots[index % 3], sections[index % 12])
    ])
    marker.write_text(json.dumps({'synthetic': True, 'purpose': '5,000-document pagination and section benchmark'}) + '\n')

client = Client()
results = []
for name, url in (
    ('tree', f'/api/oasis/catalogue/?catalogue_version={version.id}'),
    ('first-page', f'/api/oasis/catalogue/documents/?catalogue_version={version.id}'),
    ('section', f'/api/oasis/catalogue/documents/?catalogue_version={version.id}&folder_id={sections[0].id}'),
    ('search', f'/api/oasis/catalogue/documents/?catalogue_version={version.id}&q=004200'),
):
    began = time.perf_counter()
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    if response.status_code != 200:
        raise SystemExit(f'Benchmark {name} failed: HTTP {response.status_code}')
    data = response.json()['data']
    results.append({
        'name': name, 'status': response.status_code, 'queries': len(queries),
        'milliseconds': round((time.perf_counter() - began) * 1000, 1),
        'bytes': len(response.content), 'count': data.get('count', data.get('document_count')),
        'returned': len(data.get('results', data.get('folders', []))),
    })
if not (results[1]['count'] == count and results[1]['returned'] == 24
        and results[2]['count'] == 417 and results[2]['returned'] == 24
        and results[3]['count'] == 1 and results[3]['returned'] == 1):
    raise SystemExit('Unexpected synthetic pagination or section results.')
(STATE / 'benchmark.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
print('Synthetic records share one labelled original PDF; no 5,000-document index is claimed.')
print('Optional visitor preview (loopback only):')
print(f'OASIS_PREVIEW_STATE_ROOT={STATE} .venv/bin/python manage.py runserver 127.0.0.1:8792 --noreload --settings=dlms.preview_settings')
