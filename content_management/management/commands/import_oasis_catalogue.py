"""Import one exact authoring catalogue into empty, private operator state."""
import base64
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from content_management.models import LibraryFolder, LibraryVersion, OasisIndexJob
from scripts.prepare_oasis_catalogue import (
    MAX_PACKAGE_BYTES, MODELS, canonical, digest, private_path, validate_package,
)


def state_root():
    value = getattr(settings, 'DEVICE_DATA_ROOT', None) or getattr(settings, 'PREVIEW_STATE_ROOT', None)
    if not value:
        raise ValueError('Import requires explicit device or isolated preview settings.')
    return private_path(value, 'Private state root', directory=True)


def destination(root, relative):
    path = root / relative
    # Validate existing parents and reject links before creating private directories.
    for part in (*reversed(path.parents), path):
        if part.is_symlink() or (part.exists() and part != path and not part.is_dir()):
            raise ValueError('Import destination must not contain symlinks or non-directory parents.')
    if not path.is_relative_to(root):
        raise ValueError('Import destination escapes its private root.')
    return path


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def replace_private(path, value):
    """Only replace importer-owned journal/receipt, using a fsynced private file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.import-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def import_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another authoring import holds the private import lock.') from exc
        yield
    finally:
        os.close(descriptor)


def fixture_objects(package):
    expected_models = {name: apps.get_model('content_management', name) for name in MODELS}
    for row in package['fixture']:
        model = expected_models[row['model'].split('.')[1]]
        expected_fields = {field.name for field in model._meta.concrete_fields if not field.primary_key}
        expected_fields.update(field.name for field in model._meta.many_to_many)
        if set(row['fields']) != expected_fields:
            raise ValueError('Transfer schema does not exactly match the installed authoring model: ' + row['model'])
    objects = list(serializers.deserialize('json', json.dumps(package['fixture']), ignorenonexistent=False))
    # Run field length/date/type validation without probing absent FK/file rows.
    for item in objects:
        for field in item.object._meta.concrete_fields:
            value = field.value_from_object(item.object)
            if field.primary_key or field.is_relation or field.get_internal_type() == 'FileField':
                continue
            if value is None and not field.null:
                raise ValueError('Required authoring field is missing: ' + field.name)
            if value is not None:
                field.run_validators(value)
    return objects


def exact_catalogue(objects):
    """Reject both edits and additional records before treating a rerun as a no-op."""
    by_model = {}
    for item in objects:
        by_model.setdefault(type(item.object), []).append(item)
    for name in MODELS:
        model = apps.get_model('content_management', name)
        expected = by_model.get(model, [])
        if set(model.objects.values_list('pk', flat=True)) != {item.object.pk for item in expected}:
            return False
        for item in expected:
            current = model.objects.get(pk=item.object.pk)
            for field in model._meta.concrete_fields:
                if field.value_from_object(current) != field.value_from_object(item.object):
                    return False
            for field in model._meta.many_to_many:
                if set(getattr(current, field.name).values_list('pk', flat=True)) != set(item.m2m_data.get(field.name, [])):
                    return False
    return True


def require_empty(replace_empty):
    for name in MODELS:
        if name in ('libraryversion', 'libraryfolder'):
            continue
        if apps.get_model('content_management', name).objects.exists():
            raise ValueError('Target authoring catalogue is not empty; import never overwrites curator records.')
    if OasisIndexJob.objects.exists():
        raise ValueError('Target has indexing jobs; reconcile or restore its paired state before importing.')
    if LibraryVersion.objects.exists() or LibraryFolder.objects.exists():
        if not replace_empty:
            raise ValueError('Empty version/folder scaffold exists; use --replace-empty after taking a paired backup.')
        if LibraryFolder.library_content.through.objects.exists():
            raise ValueError('Target folder membership is not empty.')


class Command(BaseCommand):
    help = ('Dry-run an exact selected authoring transfer. --apply requires an empty private catalogue; '
            'stop web/worker and take a paired DB/media backup first. Does not index or publish.')

    def add_arguments(self, parser):
        parser.add_argument('--package', required=True, type=Path)
        parser.add_argument('--originals-dir', required=True, type=Path,
                            help='Resolved, existing published snapshot content directory; never modified.')
        parser.add_argument('--apply', action='store_true', help='Apply the already verified import into empty state.')
        parser.add_argument('--replace-empty', action='store_true', help='Discard only empty version/folder scaffolds.')

    def handle(self, *args, **options):
        try:
            return self.perform(options)
        except (OSError, ValueError, KeyError, TypeError, ValidationError, DatabaseError, serializers.base.DeserializationError) as exc:
            raise CommandError('Authoring import refused: ' + str(exc)) from exc

    def perform(self, options):
        root = state_root()
        media = private_path(Path(settings.MEDIA_ROOT), 'Private media root', directory=True)
        if not media.is_relative_to(root):
            raise ValueError('Import media must be inside the private state root.')
        source = private_path(options['originals_dir'], 'Published original directory', directory=True)
        if source.is_relative_to(media) or media.is_relative_to(source):
            raise ValueError('Published original source must be separate from destination authoring media.')
        package_path = private_path(options['package'], 'Authoring transfer')
        if not 1 <= package_path.stat().st_size <= MAX_PACKAGE_BYTES:
            raise ValueError('Authoring transfer exceeds its byte limit.')
        package = json.loads(package_path.read_bytes())
        manifest, raw_manifest, _ = validate_package(package)
        objects = fixture_objects(package)
        control = destination(root, 'catalogue-import')
        manifest_path = destination(control, 'reviewed-manifest.json')
        receipt_path = destination(control, 'receipt.json')
        journal_path = destination(control, 'journal.json')
        inventory = []
        for row in package['originals']:
            original = private_path(source / Path(row['path']).name, 'Published original')
            if original.stat().st_size != row['size'] or digest(original) != row['sha256']:
                raise ValueError('Published original differs from reviewed bytes: ' + original.name)
            with original.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    raise ValueError('Published original has no PDF header: ' + original.name)
            inventory.append((destination(media, row['path']), original, row))
        for row in package['assets']:
            inventory.append((destination(media, row['path']), None, row))
        if manifest_path.exists() and manifest_path.read_bytes() != raw_manifest:
            raise ValueError('Existing private reviewed manifest differs; never overwrite its review record.')
        exact = exact_catalogue(objects)
        if exact:
            for path, _, row in inventory:
                private_path(path, 'Imported original/asset')
                if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
                    raise ValueError('Imported originals/assets were changed; rerun cannot overwrite edits.')
            if not manifest_path.exists():
                raise ValueError('Existing catalogue has no matching import manifest; restore or reconcile explicitly.')
        else:
            require_empty(options['replace_empty'])
            for path, _, _ in inventory:
                if path.exists():
                    raise ValueError('Target media path already exists; import never overwrites files: ' + str(path))
            if journal_path.exists():
                journal = json.loads(journal_path.read_bytes())
                if journal.get('state') not in ('rolled_back',):
                    raise ValueError('A prior import journal is incomplete; restore its paired backup before retrying.')
        report = {'dry_run': not options['apply'], 'already_imported': exact,
                  'version_id': package['version_id'], 'library_version': manifest['library_version'],
                  'documents': len(package['originals']), 'libraries': len(manifest['libraries']),
                  'original_bytes': sum(row['size'] for row in package['originals']),
                  'package_sha256': package['package_sha256'],
                  'reviewed_manifest_sha256': package['reviewed_manifest_sha256'],
                  'reviewed_manifest': str(manifest_path), 'indexes_changed': False, 'published_changed': False}
        if not options['apply']:
            self.stdout.write(json.dumps(report, sort_keys=True))
            return
        with import_lock(destination(control, 'import.lock')):
            # Recheck after taking the lock; operators must also keep web/worker idle.
            if exact:
                if not exact_catalogue(objects):
                    raise ValueError('Catalogue changed during import validation.')
                replace_private(receipt_path, report)
                replace_private(journal_path, {'state': 'committed', 'package_sha256': package['package_sha256']})
            else:
                require_empty(options['replace_empty'])
                self.apply(objects, inventory, raw_manifest, manifest_path, receipt_path, journal_path, report)
        self.stdout.write(json.dumps(report, sort_keys=True))

    def apply(self, objects, inventory, raw_manifest, manifest_path, receipt_path, journal_path, report):
        installed = []
        committed = False
        journal = {'state': 'installing', 'package_sha256': report['package_sha256'],
                   'planned_media': [str(path.relative_to(Path(settings.MEDIA_ROOT))) for path, _, _ in inventory]}
        replace_private(journal_path, journal)
        try:
            with transaction.atomic():
                # No Content or image deletion signals: only empty scaffolds qualify.
                LibraryFolder.objects.all().delete()
                LibraryVersion.objects.all().delete()
                for path, source, row in inventory:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if source is None:
                        write_new(path, base64.b64decode(row['base64'], validate=True))
                    else:
                        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        installed.append(path)
                        with os.fdopen(descriptor, 'wb') as target, source.open('rb') as original:
                            shutil.copyfileobj(original, target, 1024 * 1024)
                            target.flush(); os.fsync(target.fileno())
                    if path not in installed:
                        installed.append(path)
                    if path.stat().st_size != row['size'] or digest(path) != row['sha256']:
                        raise ValueError('Source original changed while copying: ' + path.name)
                if not manifest_path.exists():
                    write_new(manifest_path, raw_manifest)
                    installed.append(manifest_path)
                for item in objects:
                    # DeserializedObject.save clears m2m_data even when deferred.
                    # Preserve it until every referenced scalar record exists.
                    item.object.save_base(raw=True)
                for item in objects:
                    for name, pks in item.m2m_data.items():
                        getattr(item.object, name).set(pks)
                # Verify complete fields, relation closure and sequence advancement.
                if not exact_catalogue(objects):
                    raise ValueError('Imported authoring records did not round-trip exactly.')
                if connection.vendor == 'sqlite':
                    for name in MODELS:
                        model = apps.get_model('content_management', name)
                        maximum = model.objects.order_by('-pk').values_list('pk', flat=True).first() or 0
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT seq FROM sqlite_sequence WHERE name=%s', [model._meta.db_table])
                            row = cursor.fetchone()
                        if maximum and (not row or row[0] < maximum):
                            raise ValueError('Imported primary-key sequence did not advance.')
                replace_private(receipt_path, report)
                installed.append(receipt_path)
            committed = True
            journal['state'] = 'committed'
            replace_private(journal_path, journal)
        except BaseException:
            # Only files created by this attempt qualify for cleanup. A committed
            # transaction must never have its originals removed by later journaling.
            if not committed:
                for path in reversed(installed):
                    path.unlink(missing_ok=True)
                journal['state'] = 'rolled_back'
                replace_private(journal_path, journal)
            raise
