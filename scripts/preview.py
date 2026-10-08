#!/usr/bin/env python3
"""Reproducible, isolated Oasis Library development commands."""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'seed', 'check', 'test'):
        sub.add_parser(command)
    run = sub.add_parser('run', help='Serve only 127.0.0.1:8790, read-only by default.')
    run.add_argument('--curator', action='store_true', help='Enable private local development writes.')
    worker = sub.add_parser('index-worker', help='Process private draft indexing jobs with existing station commands.')
    worker.add_argument('--once', action='store_true', help='Process one queued job then stop.')
    sub.add_parser('index-fixtures', help='Write an explicit private-testing manifest for labelled synthetic seed PDFs.')
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    os.environ['DJANGO_SETTINGS_MODULE'] = 'dlms.preview_settings'
    os.environ['OASIS_PREVIEW_CURATOR'] = '1' if getattr(args, 'curator', False) else '0'
    from django.core.management import execute_from_command_line

    commands = {
        'prepare': ['migrate', '--noinput'],
        'seed': ['seed_oasis_preview'],
        'check': ['check'],
        'test': ['test', 'content_management', '--noinput'],
        'run': ['runserver', '127.0.0.1:8790', '--noreload'],
        'index-worker': ['run_oasis_index_jobs'] + (['--once'] if getattr(args, 'once', False) else []),
        'index-fixtures': ['seed_oasis_index_manifest'],
    }
    execute_from_command_line([str(root / 'manage.py')] + commands[args.command])


if __name__ == '__main__':
    main()
