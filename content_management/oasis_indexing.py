"""Queue existing station maintenance commands into isolated private draft roots."""
import hashlib
import json
import os
import re
import subprocess
import time
import copy
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError

from content_management.models import Content, LibraryFolder, LibraryVersion, OasisIndexJob
from content_management.oasis_documents import PrivateCuratorAccess
from content_management.standardize_format import build_response


def staging_base():
    root = Path(settings.BASE_DIR).resolve() / '.preview' / 'indexing'
    for path in (root.parent, root, root / 'jobs'):
        if path.is_symlink():
            raise ValueError('Private indexing staging directories must not be symlinks.')
    return root


def job_root(job):
    root = staging_base() / 'jobs' / str(job.id)
    if root.is_symlink():
        raise ValueError('Private job root must not be a symlink.')
    return root


def worker_active():
    try:
        heartbeat = json.loads((staging_base() / 'worker.json').read_text())
        return heartbeat.get('active') is True and time.time() - heartbeat['last_seen'] < 20
    except (OSError, ValueError, KeyError, TypeError):
        return False


def heartbeat(active=True):
    base = staging_base()
    base.mkdir(parents=True, exist_ok=True)
    temporary = base / 'worker.tmp'
    temporary.write_text(json.dumps({'active': active, 'last_seen': time.time(), 'pid': os.getpid()}))
    temporary.replace(base / 'worker.json')


def operator_config():
    names = ('OASIS_INDEXING_STATION_ROOT', 'OASIS_INDEXING_PYTHON', 'OASIS_INDEXING_MANIFEST')
    values = {name: os.environ.get(name, '') for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError('Configure the private station adapter: ' + ', '.join(missing) + '. A reviewed manifest is required.')
    root = Path(values[names[0]]).expanduser().resolve()
    # Keep the venv executable path: resolving its symlink would bypass its
    # installed importer dependencies and invoke the system interpreter.
    python = Path(values[names[1]]).expanduser().absolute()
    manifest = Path(values[names[2]]).expanduser().absolute()
    if not (root / 'scripts' / 'import_pdf_library.py').is_file() or not (root / 'scripts' / 'index_pdf_vectors.py').is_file():
        raise ValueError('Configured station root does not contain the existing PDF maintenance commands.')
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('Configured station Python is not executable.')
    if not manifest.is_file() or manifest.stat().st_size > 256 * 1024:
        raise ValueError('Configure a small, explicit reviewed manifest JSON file.')
    staging_base()
    return {'root': root, 'python': python, 'manifest': manifest,
            'model': os.environ.get('OASIS_INDEXING_MODEL', 'nomic-embed-text:latest'),
            'base_url': os.environ.get('OASIS_INDEXING_EMBED_URL', 'http://127.0.0.1:11434')}


def run_probe(config, *, manifest=None, root=None, artifacts_only=False):
    command = [str(config['python']), '-B', str(Path(settings.BASE_DIR) / 'scripts' / 'probe_oasis_index.py'),
               '--station-root', str(config['root']), '--model', config['model'], '--base-url', config['base_url']]
    if manifest is not None:
        command += ['--manifest', str(manifest)]
    if root is not None:
        command += ['--root', str(root)]
    if artifacts_only:
        command += ['--artifacts-only']
    try:
        result = subprocess.run(command, cwd=config['root'], capture_output=True, text=True, timeout=15, check=False)
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError('Configured station validator is unavailable: ' + str(exc))
    if result.returncode or payload.get('error'):
        raise ValueError(payload.get('error') or result.stderr[-2000:] or 'Station validation failed.')
    return payload


@lru_cache(maxsize=64)
def cached_probe(config_key, manifest, root, signatures, time_window):
    config = dict(zip(('root', 'python', 'manifest', 'model', 'base_url'), config_key))
    return run_probe(config, manifest=manifest or None, root=root or None)


def configuration_probe(config):
    key = tuple(str(config[name]) for name in ('root', 'python', 'manifest', 'model', 'base_url'))
    return cached_probe(key, str(config['manifest']), '', (file_signature(config['manifest']),), int(time.time() // 5))


@lru_cache(maxsize=64)
def cached_artifact_receipt(config_key, root, signatures):
    config = dict(zip(('root', 'python', 'manifest', 'model', 'base_url'), config_key))
    return run_probe(config, root=root, artifacts_only=True)['receipt']


def artifact_signature(path):
    """Include symlink/directory changes, not just the target file's stat."""
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return str(path), 'missing'
    return str(path), stat.st_dev, stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


def verified_receipt(config, job):
    draft = job_root(job) / 'draft'
    if draft.is_symlink():
        raise ValueError('Private draft root must not be a symlink.')
    snapshot = (draft / 'current').resolve(strict=True)
    if snapshot.parent != draft.resolve():
        raise ValueError('Private draft pointer escapes its job root.')
    files = [draft, draft / 'current', snapshot, snapshot / 'content', snapshot / 'manifest.json', snapshot / 'index.sqlite3']
    files += [snapshot / 'content' / item['filename'] for item in job.documents]
    vector = draft / 'semantic' / snapshot.name / 'vectors.sqlite3'
    files += [draft / 'semantic', vector.parent, vector]
    signatures = tuple(artifact_signature(path) for path in files)
    key = tuple(str(config[name]) for name in ('root', 'python', 'manifest', 'model', 'base_url'))
    # Immutable originals/indexes need no repeated full-file hashing while all
    # signatures remain unchanged. Installed model state has a separate bounded
    # refresh, and the semantic provider rechecks it at query time as well.
    receipt = copy.deepcopy(cached_artifact_receipt(key, str(draft), signatures))
    if receipt.get('vector_artifact_valid'):
        try:
            model = configuration_probe(config)
            receipt['model_digest'] = model.get('model_digest')
            if not model['vector_available']:
                receipt.update(vector_valid=False, vector_state='unavailable', vector_reason=model['vector_blocked_reason'])
            elif model.get('model_digest') != receipt.get('vector_model_digest'):
                receipt.update(vector_valid=False, vector_state='stale', vector_reason='Installed model digest differs from the verified vectors.')
            else:
                receipt.update(vector_valid=True, vector_state='indexed', vector_reason=None)
        except (ValueError, OSError, KeyError) as exc:
            receipt.update(vector_valid=False, vector_state='unavailable', vector_reason=str(exc))
    return receipt


@lru_cache(maxsize=512)
def _file_hash(path, signature):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    if file_signature(Path(path)) != signature:
        raise ValueError('Original file changed during hash verification. Try again.')
    return digest.hexdigest()


def file_signature(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


def original_record(document):
    path = Path(document.content_file.path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original PDF is missing or is not a regular file.')
    if not 1 <= path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('The existing importer supports PDF originals up to 32 MiB.')
    return {'document_id': document.id, 'filename': document.file_name, 'sha256': _file_hash(str(path), file_signature(path))}


def catalogue_documents(version):
    return list(Content.objects.filter(libraryfolder__version=version, active=True, file_name__iendswith='.pdf').distinct().order_by('id'))


def validate_export_sources(version):
    """Fence the legacy exporter inputs for this private adapter only."""
    contents = Path(settings.CONTENTS_ROOT).resolve()
    for document in Content.objects.filter(libraryfolder__version=version).distinct():
        name = document.file_name or ''
        if not name or name in ('.', '..') or Path(name).name != name or '\\' in name or '\x00' in name:
            raise ValueError('Document %s has an unsafe export filename.' % document.id)
        export_source = contents / name
        try:
            actual = Path(document.content_file.path)
            resolved = export_source.resolve(strict=True)
            if export_source.is_symlink() or not export_source.is_file() or resolved.parent != contents or actual.resolve(strict=True) != resolved:
                raise ValueError('Document %s export original does not match its stored file inside CONTENTS_ROOT.' % document.id)
        except (OSError, ValueError) as exc:
            raise ValueError('Document %s has an unavailable or unsafe export original: %s' % (document.id, exc))
    # Assets are copied with their basename, but their source names must still
    # stay inside configured media storage rather than reading arbitrary files.
    images = [folder.logo_img for folder in version.folders.select_related('logo_img') if folder.logo_img]
    images += [module.logo_img for module in version.library_modules.select_related('logo_img') if module.logo_img]
    if version.library_banner:
        images.append(version.library_banner)
    media = Path(settings.MEDIA_ROOT).resolve()
    for image in images:
        name = str(image.image_file.name or '')
        try:
            relative = Path(name)
            actual = media / relative
            if not name or relative.is_absolute() or '..' in relative.parts or '\\' in name or actual.is_symlink() or not actual.resolve(strict=True).is_relative_to(media):
                raise ValueError('Asset source escapes configured media storage.')
        except (OSError, ValueError) as exc:
            raise ValueError('Unavailable or unsafe catalogue asset: ' + str(exc))


def preflight(version, profile='lexical'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', version.version_number):
        raise ValueError('Use a safe catalogue version identifier (1–160 letters, digits, dots, underscores or hyphens) before private indexing.')
    config = operator_config()
    probe = configuration_probe(config)
    manifest = probe['manifest']
    if manifest['library_version'] != version.version_number:
        raise ValueError('The reviewed manifest belongs to a different catalogue version.')
    documents = catalogue_documents(version)
    if not documents:
        raise ValueError('This catalogue has no enabled PDF documents assigned to a library.')
    reviewed = {item['dlms_id']: item for item in manifest['documents']}
    if set(reviewed) != {document.id for document in documents}:
        raise ValueError('The reviewed manifest must cover exactly every enabled PDF in this catalogue. Review newly added or removed documents first.')
    # Reject incomplete review coverage before reading thousands of unrelated
    # originals. The existing station importer caps reviewed snapshots at 50.
    validate_export_sources(version)
    records = [original_record(document) for document in documents]
    for record in records:
        item = reviewed[record['document_id']]
        if item['filename'] != record['filename'] or item['sha256'] != record['sha256']:
            raise ValueError('Document %s changed filename or bytes since manifest review. Update its explicit review before reindexing.' % record['document_id'])
    if profile == 'hybrid' and not probe['vector_available']:
        raise ValueError(probe['vector_blocked_reason'] or 'The configured local embedding model is unavailable.')
    return config, probe, records


def serialize_job(job, *, detail=False, compact=False):
    result = {'id': str(job.id), 'catalogue_version': job.catalogue_version,
            'requested_document_id': job.requested_document_id, 'requested_folder_id': job.requested_folder_id,
            'profile': job.profile, 'state': job.state, 'created_on': job.created_on.isoformat(),
            'started_on': job.started_on.isoformat() if job.started_on else None,
            'finished_on': job.finished_on.isoformat() if job.finished_on else None,
            'private_draft': True, 'scope': 'catalogue'}
    if not compact:
        ids = [item['document_id'] for item in job.documents]
        result.update({'diagnostics': job.diagnostics, 'affected_document_ids': ids if detail else ids[:100],
                       'affected_document_count': len(ids), 'affected_document_ids_truncated': not detail and len(ids) > 100})
    if detail:
        result['receipt'] = job.receipt
    return result


def subtree_ids(version, folder):
    children = {}
    for identifier, parent in LibraryFolder.objects.filter(version=version).values_list('id', 'parent_id'):
        children.setdefault(parent, []).append(identifier)
    descendants, pending = {folder.id}, [folder.id]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, []):
            if child not in descendants:
                descendants.add(child)
                pending.append(child)
    return descendants


def requested_status_documents(request):
    queryset = Content.objects.only('id', 'file_name', 'content_file', 'active').order_by('id')
    if 'document_ids' not in request.query_params:
        return list(queryset[:100])
    raw = request.query_params['document_ids']
    if raw == '':
        return []
    values = raw.split(',')
    try:
        ids = {int(value) for value in values}
        if len(values) > 100 or any(identifier < 1 for identifier in ids):
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError({'document_ids': 'Use at most 100 comma-separated positive document IDs.'})
    return list(queryset.filter(pk__in=ids))


def selected_version(value):
    try:
        return LibraryVersion.objects.get(pk=int(value))
    except (ValueError, TypeError, LibraryVersion.DoesNotExist):
        raise ValidationError({'catalogue_version': 'Choose an existing catalogue version.'})


@api_view(['GET'])
@permission_classes([PrivateCuratorAccess])
def indexing_status(request):
    version = selected_version(request.query_params.get('catalogue_version'))
    visible = requested_status_documents(request)
    folder = None
    if 'folder_id' in request.query_params:
        try:
            folder = LibraryFolder.objects.get(pk=int(request.query_params['folder_id']), version=version)
        except (ValueError, TypeError, LibraryFolder.DoesNotExist):
            raise ValidationError({'folder_id': 'Choose a library folder in this catalogue.'})
    configuration = {'configured': False, 'blocked_reason': None, 'lexical_available': False,
                     'vector_available': False, 'vector_blocked_reason': None, 'worker_active': worker_active()}
    config = None
    try:
        config, probe, records = preflight(version)
        configuration.update({key: probe[key] for key in ('lexical_available', 'vector_available', 'vector_blocked_reason')})
        configuration['configured'] = True
    except ValueError as exc:
        configuration['blocked_reason'] = str(exc)
    jobs = list(OasisIndexJob.objects.filter(catalogue_version=version.id).defer('receipt', 'manifest')[:10])
    active_job = next((job for job in jobs if job.state in ('queued', 'running')), None)
    ready = OasisIndexJob.objects.filter(catalogue_version=version.id, state='succeeded').first()
    receipt, artifact_error = None, None
    if ready is not None:
        try:
            config = config or operator_config()
            receipt = verified_receipt(config, ready)
            if receipt['index_sha256'] != ready.receipt['index_sha256'] or receipt['vectors_sha256'] != ready.receipt['vectors_sha256']:
                raise ValueError('Private draft artifacts changed after successful verification.')
        except (ValueError, OSError, TypeError, KeyError) as exc:
            artifact_error = str(exc)
    indexed = {record['document_id']: record for record in receipt['documents']} if receipt else {}
    members = set(Content.objects.filter(pk__in=[document.id for document in visible], libraryfolder__version=version).values_list('id', flat=True))
    latest_ids = {item['document_id'] for item in jobs[0].documents} if jobs else set()
    latest = serialize_job(jobs[0], compact=True) if jobs else None
    documents = []
    for document in visible:
        reason = None
        if document.id not in members:
            reason = 'Assign this document to a library in the selected catalogue before indexing.'
        elif not document.active:
            reason = 'This document is disabled.'
        elif not (document.file_name or '').lower().endswith('.pdf'):
            reason = 'The configured station importer indexes PDF originals only.'
        record = {'document_id': document.id, 'filename': document.file_name, 'sha256': None}
        state = 'not_applicable' if reason else 'not_indexed'
        if reason is None:
            try:
                record = original_record(document)
                old = indexed.get(document.id)
                if artifact_error:
                    state, reason = 'unavailable', artifact_error
                elif old:
                    state = 'indexed' if (old['filename'], old['sha256']) == (record['filename'], record['sha256']) else 'stale'
                    if state == 'stale':
                        reason = 'Current original differs from the verified private draft.'
            except (ValueError, OSError) as exc:
                state, reason = 'unavailable', str(exc)
        vector_state, vector_reason = state, reason
        if receipt and state in ('indexed', 'stale') and not receipt.get('vectors_sha256'):
            vector_state, vector_reason = 'not_indexed', 'No vectors have been built for this private draft.'
        elif state == 'indexed' and not receipt['vector_valid']:
            vector_state, vector_reason = receipt.get('vector_state', 'not_indexed'), receipt.get('vector_reason') or 'No verified vectors for this private draft.'
        blocked = reason if state in ('not_applicable', 'unavailable') else configuration['blocked_reason']
        if active_job and not blocked:
            blocked = 'A catalogue indexing job is already queued or running.'
        documents.append({**record, 'lexical': {'state': state, 'reason': reason},
                          'vectors': {'state': vector_state, 'reason': vector_reason},
                          'can_reindex': not bool(blocked), 'blocked_reason': blocked,
                          'latest_job': latest if document.id in latest_ids else None})
    library = None
    if folder:
        eligible_count = Content.objects.filter(libraryfolder__id__in=subtree_ids(version, folder), active=True,
                                                file_name__iendswith='.pdf').distinct().count()
        blocked = configuration['blocked_reason']
        if not eligible_count:
            blocked = 'This library has no enabled PDF originals to index.'
        elif active_job and not blocked:
            blocked = 'A catalogue indexing job is already queued or running.'
        library = {'folder_id': folder.id, 'eligible_document_count': eligible_count,
                   'can_reindex': not bool(blocked), 'blocked_reason': blocked}
    return build_response({'catalogue_version': version.id, 'configuration': configuration,
                           'documents': documents, 'jobs': [serialize_job(job) for job in jobs],
                           'scope': 'catalogue', 'snapshot_document_count': Content.objects.filter(libraryfolder__version=version, active=True, file_name__iendswith='.pdf').distinct().count(),
                           'library': library, 'document_count': Content.objects.count(), 'documents_returned': len(documents)})


class OasisIndexJobViewSet(viewsets.ViewSet):
    permission_classes = (PrivateCuratorAccess,)

    def list(self, request):
        version = selected_version(request.query_params.get('catalogue_version'))
        jobs = OasisIndexJob.objects.filter(catalogue_version=version.id)
        return build_response({'results': [serialize_job(job) for job in jobs[:30]], 'count': jobs.count()})

    def retrieve(self, request, pk=None):
        from rest_framework.generics import get_object_or_404
        return build_response(serialize_job(get_object_or_404(OasisIndexJob, pk=pk), detail=True))

    def create(self, request):
        version = selected_version(request.data.get('catalogue_version'))
        profile = request.data.get('profile', 'lexical')
        if profile not in ('lexical', 'hybrid'):
            raise ValidationError({'profile': 'Choose lexical or hybrid.'})
        document_id, folder_id = request.data.get('document_id'), request.data.get('folder_id')
        if document_id is not None and folder_id is not None:
            raise ValidationError('Request a document or library action, not both.')
        eligible = catalogue_documents(version)
        eligible_ids = {item.id for item in eligible}
        if document_id is not None:
            try:
                document_id = int(document_id)
            except (ValueError, TypeError):
                raise ValidationError({'document_id': 'Use a document ID.'})
            if document_id not in eligible_ids:
                raise ValidationError({'document_id': 'Assign an enabled PDF to this catalogue before indexing.'})
        if folder_id is not None:
            try:
                folder_id = int(folder_id)
                folder = LibraryFolder.objects.get(pk=folder_id, version=version)
            except (ValueError, TypeError, LibraryFolder.DoesNotExist):
                raise ValidationError({'folder_id': 'Choose a library folder in this catalogue.'})
            descendants = subtree_ids(version, folder)
            if not Content.objects.filter(pk__in=eligible_ids, libraryfolder__id__in=descendants).exists():
                raise ValidationError({'folder_id': 'This library has no enabled PDFs to index.'})
        try:
            config, probe, records = preflight(version, profile)
        except ValueError as exc:
            return build_response(status=status.HTTP_409_CONFLICT, success=False, error={'blocked_reason': str(exc)})
        with transaction.atomic():
            LibraryVersion.objects.select_for_update().get(pk=version.id)
            if OasisIndexJob.objects.filter(catalogue_version=version.id, state__in=('queued', 'running')).exists():
                return build_response(status=status.HTTP_409_CONFLICT, success=False, error={'blocked_reason': 'An indexing job is already queued or running for this catalogue.'})
            manifest = probe['manifest']
            digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            job = OasisIndexJob.objects.create(catalogue_version=version.id, requested_document_id=document_id,
                                              requested_folder_id=folder_id, profile=profile, documents=records,
                                              manifest=manifest, manifest_sha256=digest)
        return build_response(serialize_job(job), status=status.HTTP_201_CREATED)
