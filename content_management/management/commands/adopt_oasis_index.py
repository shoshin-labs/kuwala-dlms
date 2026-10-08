"""Adopt an already built, verified snapshot into private curator job storage."""
import hashlib
import json
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from content_management.models import LibraryVersion, OasisIndexJob
from content_management.oasis_indexing import job_root, preflight, run_probe, staging_base
from dlms.private_paths import checked_directory, checked_path, require_disjoint


def manifest_digest(manifest):
    rendered = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(rendered.encode('utf-8')).hexdigest()


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path):
    path = checked_path(path, 'Adoption artifact')
    if not path.is_file():
        raise ValueError('Adoption artifacts must be existing regular files: ' + str(path))
    return path


def snapshot_manifest(root):
    """Only current may be a symlink, and it must select a direct child snapshot."""
    root = checked_directory(root, 'Adoption snapshot root')
    if not root.is_dir():
        raise ValueError('Adoption snapshot root must exist.')
    current = root / 'current'
    if not current.is_symlink():
        raise ValueError('Adoption current must be an internal snapshot symlink.')
    target = current.readlink()
    if (target.is_absolute() or len(target.parts) != 1
            or not re.fullmatch(r'v-[A-Za-z0-9][A-Za-z0-9._-]{0,159}', target.name)):
        raise ValueError('Adoption current must name one safe relative v-* snapshot sibling.')
    snapshot = checked_directory(root / target, 'Adoption current target').resolve(strict=True)
    if snapshot.parent != root or snapshot.name == 'current':
        raise ValueError('Adoption current must select a direct child of its private root.')
    snapshot = checked_directory(snapshot, 'Adoption selected snapshot')
    if not snapshot.is_dir():
        raise ValueError('Adoption selected snapshot must be a directory.')
    manifest_path = regular_file(snapshot / 'manifest.json')
    if manifest_path.stat().st_size > 256 * 1024:
        raise ValueError('Adoption manifest exceeds the station manifest limit.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    return snapshot, manifest


def validated_snapshot(config, root, manifest, records, model_digest):
    snapshot, candidate_manifest = snapshot_manifest(root)
    if candidate_manifest != manifest:
        raise ValueError('Adoption manifest differs from the full reviewed manifest, including rights and groups.')
    paths = [(regular_file(snapshot / 'manifest.json'), None),
             (regular_file(snapshot / 'index.sqlite3'), 'index_sha256')]
    for document in manifest['documents']:
        paths.append((regular_file(snapshot / 'content' / document['filename']), document['sha256']))
    vectors = regular_file(root / 'semantic' / snapshot.name / 'vectors.sqlite3')
    paths.append((vectors, 'vectors_sha256'))
    result = run_probe(config, root=root)
    receipt = result.get('receipt')
    if not isinstance(receipt, dict) or receipt.get('snapshot') != snapshot.name:
        raise ValueError('Station validation did not return the selected snapshot receipt.')
    if (receipt.get('lexical_valid') is not True or receipt.get('vector_valid') is not True
            or receipt.get('vector_artifact_valid') is not True):
        raise ValueError('Adoption requires complete, valid lexical and vector artifacts.')
    for field in ('index_sha256', 'vectors_sha256'):
        if not isinstance(receipt.get(field), str) or not re.fullmatch(r'[a-f0-9]{64}', receipt[field]):
            raise ValueError('Station validation returned an invalid artifact hash: ' + field)
    if (not isinstance(model_digest, str) or not model_digest
            or receipt.get('vector_model_digest') != model_digest
            or receipt.get('model_digest') != model_digest):
        raise ValueError('Adoption vectors do not match the installed, preflight-validated model digest.')
    documents = receipt.get('documents')
    expected = {(record['document_id'], record['filename'], record['sha256']) for record in records}
    if not isinstance(documents, list) or len(documents) != len(records):
        raise ValueError('Adoption receipt must contain every exact catalogue original once.')
    found = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError('Adoption receipt has an invalid document record.')
        identity = (document.get('document_id'), document.get('filename'), document.get('sha256'))
        if identity not in expected or identity in found:
            raise ValueError('Adoption receipt differs from the exact catalogue originals.')
        for field in ('page_count', 'passage_count'):
            if type(document.get(field)) is not int or document[field] < 1:
                raise ValueError('Adoption receipt has incomplete page or passage counts.')
        found.add(identity)
    if found != expected:
        raise ValueError('Adoption receipt differs from the exact catalogue originals.')
    # The probe hashes every original. These paths also fence the later copy to
    # exact required artifacts; stale import directories and locks are ignored.
    return snapshot, receipt, paths


def copy_snapshot(source, snapshot, receipt, paths, destination):
    destination.mkdir(mode=0o700)
    for original, expected in paths:
        target = destination / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        original = regular_file(original)
        expected = receipt[expected] if expected in ('index_sha256', 'vectors_sha256') else expected
        before = file_digest(original)
        if expected is not None and before != expected:
            raise ValueError('Adoption source changed after validation: ' + str(original))
        shutil.copyfile(original, target)
        target.chmod(0o600)
        if file_digest(target) != before or file_digest(original) != before:
            raise ValueError('Adoption artifact changed during its private copy: ' + str(original))
    (destination / 'current').symlink_to(snapshot.name, target_is_directory=True)


class Command(BaseCommand):
    help = 'Validate an existing private snapshot; --apply copies it as a verified curator baseline without indexing.'

    def add_arguments(self, parser):
        parser.add_argument('--root', required=True, help='Absolute private staged copy of an existing published root.')
        parser.add_argument('--catalogue-version', required=True, type=int, help='Existing authoring catalogue numeric ID.')
        parser.add_argument('--apply', action='store_true', help='Copy verified artifacts and record a succeeded adoption job.')

    def handle(self, *args, **options):
        created_root = None
        try:
            version = LibraryVersion.objects.get(pk=options['catalogue_version'])
            config, probe, records = preflight(version, 'hybrid')
            source = checked_directory(options['root'], 'Private staged adoption root')
            if not source.is_dir() or source.stat().st_mode & 0o077:
                raise ValueError('Private staged adoption root must exist and deny group/other access.')
            require_disjoint(source, [settings.BASE_DIR, settings.MEDIA_ROOT, settings.BUILDS_ROOT,
                                     config['root'], staging_base(),
                                     *getattr(settings, 'OASIS_INDEXING_PROTECTED_ROOTS', ())],
                             'Private staged adoption root')
            manifest = probe['manifest']
            digest = manifest_digest(manifest)
            snapshot, receipt, paths = validated_snapshot(config, source, manifest, records, probe.get('model_digest'))
            with transaction.atomic():
                LibraryVersion.objects.select_for_update().get(pk=version.pk)
                if OasisIndexJob.objects.filter(catalogue_version=version.pk, state__in=('queued', 'running')).exists():
                    raise ValueError('A catalogue indexing job is already queued or running.')
                for existing in OasisIndexJob.objects.filter(catalogue_version=version.pk, state='succeeded',
                                                            profile='hybrid', manifest_sha256=digest):
                    if existing.manifest != manifest or existing.documents != records or existing.receipt != receipt:
                        continue
                    _, existing_receipt, _ = validated_snapshot(config, job_root(existing) / 'draft',
                                                               manifest, records, probe.get('model_digest'))
                    if existing_receipt != receipt:
                        raise ValueError('Existing matching adoption artifacts changed; verify operator state before retrying.')
                    self.stdout.write('Already verified: %s (%s originals); no changes.' % (existing.pk, len(records)))
                    return
                if not options['apply']:
                    self.stdout.write('Dry run: verified %s originals and existing lexical/vector artifacts; no changes.' % len(records))
                    return
                job = OasisIndexJob(catalogue_version=version.pk, profile='hybrid', state='succeeded',
                                    documents=records, manifest=manifest, manifest_sha256=digest)
                root = job_root(job)
                root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                root.mkdir(mode=0o700)
                created_root = root
                draft = root / 'draft'
                copy_snapshot(source, snapshot, receipt, paths, draft)
                _, copied_receipt, _ = validated_snapshot(config, draft, manifest, records, probe.get('model_digest'))
                if copied_receipt != receipt:
                    raise ValueError('Copied adoption artifacts differ from the verified source receipt.')
                current_config, current_probe, current_records = preflight(version, 'hybrid')
                if current_config != config or current_probe['manifest'] != manifest or current_records != records:
                    raise ValueError('Catalogue or reviewed adapter configuration changed during adoption.')
                if current_probe.get('model_digest') != probe.get('model_digest'):
                    raise ValueError('Installed embedding model changed during adoption.')
                job.receipt = copied_receipt
                job.started_on = job.finished_on = timezone.now()
                job.diagnostics = ('Adopted verified existing snapshot %s into a private curator baseline. '
                                   'Originals, passages and vectors were copied and validated; '
                                   'no extraction, embedding or publication commands ran.') % snapshot.name
                job.save(force_insert=True)
            created_root = None
            self.stdout.write('Adopted verified existing snapshot: %s (%s originals).' % (job.pk, len(records)))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, LibraryVersion.DoesNotExist) as exc:
            if created_root is not None:
                shutil.rmtree(created_root)
            raise CommandError(str(exc)) from exc
        except BaseException:
            if created_root is not None:
                shutil.rmtree(created_root)
            raise
