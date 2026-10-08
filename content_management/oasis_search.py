"""Private curator search over a verified draft using the station's providers."""
import hashlib
import json
import subprocess
from pathlib import Path

from django.conf import settings
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.throttling import SimpleRateThrottle

from content_management.models import Content, LibraryFolder, OasisIndexJob
from content_management.oasis_documents import PrivateCuratorAccess
from content_management.oasis_indexing import job_root, operator_config, original_record, selected_version, subtree_ids, verified_receipt
from content_management.standardize_format import build_response
from dlms.preview_middleware import PrivatePreviewMiddleware


class PrivateSearchThrottle(SimpleRateThrottle):
    rate = '10/min'

    def get_cache_key(self, request, view):
        return 'oasis-private-index-search:' + request.META.get('REMOTE_ADDR', '')


def verified_job(job):
    config = operator_config()
    receipt = verified_receipt(config, job)
    if not job.receipt or receipt['index_sha256'] != job.receipt['index_sha256'] or receipt['vectors_sha256'] != job.receipt['vectors_sha256']:
        raise ValueError('Private draft artifacts changed after successful validation.')
    return config, receipt


def run_search(config, job, query, sources, profile):
    command = [str(config['python']), '-B', str(Path(settings.BASE_DIR) / 'scripts' / 'search_oasis_index.py'),
               '--station-root', str(config['root']), '--root', str(job_root(job) / 'draft'),
               '--query=' + query, '--sources', json.dumps(sources), '--profile', profile,
               '--model', config['model'], '--base-url', config['base_url']]
    try:
        result = subprocess.run(command, cwd=config['root'], capture_output=True, text=True, timeout=20, check=False)
        if len(result.stdout) > 256 * 1024:
            raise ValueError('Private search exceeded its bounded response size.')
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError('The existing station search returned an invalid response.')
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError('Private passage search is unavailable: ' + str(exc))
    if result.returncode or payload.get('error'):
        raise ValueError(payload.get('error') or result.stderr[-2000:] or 'Existing station passage search failed.')
    return payload


@api_view(['GET'])
@permission_classes([PrivateCuratorAccess])
def index_search(request):
    if not PrivatePreviewMiddleware.browser_origin_allowed(request):
        return build_response(success=False, status=403, error={'blocked_reason': 'Private search must come from the same curator preview origin.'})
    allowed = {'catalogue_version', 'folder_id', 'q', 'profile'}
    if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
        raise ValidationError('Use one value for each private search parameter.')
    version = selected_version(request.query_params.get('catalogue_version'))
    profile = request.query_params.get('profile', 'lexical')
    query = request.query_params.get('q', '')
    if profile not in ('lexical', 'semantic'):
        raise ValidationError({'profile': 'Choose lexical or semantic.'})
    if len(query) > 160 or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in query):
        raise ValidationError({'q': 'Use a search query of at most 160 characters without control characters.'})
    query = query.strip()
    if query:
        throttle = PrivateSearchThrottle()
        if not throttle.allow_request(request, None):
            raise Throttled(wait=throttle.wait())
    folder = None
    scope = Content.objects.filter(libraryfolder__version=version, active=True, file_name__iendswith='.pdf').distinct()
    if 'folder_id' in request.query_params:
        try:
            folder = LibraryFolder.objects.get(pk=int(request.query_params['folder_id']), version=version)
        except (ValueError, TypeError, LibraryFolder.DoesNotExist):
            raise ValidationError({'folder_id': 'Choose a library folder in the selected catalogue.'})
        scope = scope.filter(libraryfolder__id__in=subtree_ids(version, folder)).distinct()
    eligible_count = scope.count()
    data = {'private_draft': True, 'catalogue_version': version.id, 'folder_id': folder.id if folder else None,
            'snapshot': None, 'profile_used': profile, 'lexical_available': False, 'semantic_available': False,
            'semantic_reason': 'No verified semantic vectors are available.', 'blocked_reason': None,
            'indexed_document_count': 0, 'eligible_document_count': eligible_count,
            'stale_document_count': 0, 'unindexed_document_count': eligible_count, 'results': []}
    job = OasisIndexJob.objects.filter(catalogue_version=version.id, state='succeeded').first()
    if not job:
        data['blocked_reason'] = 'Finish a private draft indexing job before searching document text.'
    else:
        try:
            config, receipt = verified_job(job)
            indexed = {item['document_id']: item for item in receipt['documents']}
            fresh = []
            for document in scope.filter(pk__in=indexed):
                current = original_record(document)
                old = indexed[document.id]
                if (current['filename'], current['sha256']) == (old['filename'], old['sha256']):
                    fresh.append(document.id)
                else:
                    data['stale_document_count'] += 1
            data.update({'snapshot': receipt['snapshot'], 'indexed_document_count': len(fresh),
                         'unindexed_document_count': data['eligible_document_count'] - len(fresh) - data['stale_document_count'],
                         'lexical_available': bool(fresh), 'semantic_available': bool(fresh) and receipt['vector_valid'],
                         'semantic_reason': receipt.get('vector_reason') or ('No current indexed documents in this selected scope.' if not fresh else None)})
            if not fresh:
                data['blocked_reason'] = 'The selected scope has no indexed PDFs matching its current original bytes.'
            if query and data['lexical_available'] and (profile == 'lexical' or data['semantic_available']):
                sources = [item['id'] for item in job.manifest['documents'] if item['dlms_id'] in fresh]
                result = run_search(config, job, query, sources, profile)
                if result.get('snapshot') != data['snapshot'] or result.get('profile_used') != profile:
                    raise ValueError('Private search returned a different draft or ranking profile.')
                if not isinstance(result.get('results'), list) or len(result['results']) > 10:
                    raise ValueError('Private search returned an invalid result count.')
                for item in result['results']:
                    original = indexed.get(item.get('document_id'))
                    if not original or item['document_id'] not in fresh or item.get('filename') != original['filename'] or item.get('original_sha256') != original['sha256'] or type(item.get('page')) is not int or not 1 <= item['page'] <= original['page_count'] or not isinstance(item.get('text'), str) or len(item['text']) > 1400:
                        raise ValueError('Private search result failed document, page or original-hash validation.')
                    current_document = scope.filter(pk=item['document_id']).first()
                    current = original_record(current_document) if current_document else None
                    if current is None or (current['filename'], current['sha256']) != (item['filename'], item['original_sha256']):
                        raise ValueError('A matching original or library membership changed during search. Try again.')
                    item['original_page_url'] = '/api/oasis/index-search/original/%s/%s/#page=%s' % (job.id, item['document_id'], item['page'])
                data['results'] = result['results']
        except (ValueError, OSError, KeyError, TypeError) as exc:
            data['lexical_available'], data['semantic_available'] = False, False
            data['blocked_reason'] = str(exc)
    if query and (data['blocked_reason'] or profile == 'semantic' and not data['semantic_available']):
        return build_response(success=False, status=409, error={'blocked_reason': data['blocked_reason'] or data['semantic_reason']})
    return build_response(data)


@api_view(['GET'])
@permission_classes([PrivateCuratorAccess])
def draft_original(request, job_id, document_id):
    """Pin reader links to the indexed original, even after authoring replacement."""
    if not PrivatePreviewMiddleware.browser_origin_allowed(request):
        return build_response(success=False, status=403, error='Use the same curator preview origin.')
    job = get_object_or_404(OasisIndexJob, pk=job_id, state='succeeded')
    try:
        config, receipt = verified_job(job)
        original = next((item for item in receipt['documents'] if item['document_id'] == document_id), None)
        if original is None:
            return build_response(success=False, status=404, error='Original is not in this verified private draft.')
        draft = job_root(job) / 'draft'
        snapshot = (draft / 'current').resolve(strict=True)
        content = snapshot / 'content'
        path = content / original['filename']
        if snapshot.parent != draft.resolve() or content.is_symlink() or content.resolve(strict=True).parent != snapshot or path.is_symlink() or path.resolve(strict=True).parent != content.resolve() or not 1 <= path.stat().st_size <= 32 * 1024 * 1024:
            raise ValueError('Private draft original path is unavailable or unsafe.')
        stream = path.open('rb')
        try:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(65536), b''):
                digest.update(block)
            if digest.hexdigest() != original['sha256']:
                raise ValueError('Private original changed after draft validation.')
            stream.seek(0)
        except BaseException:
            stream.close()
            raise
        response = FileResponse(stream, content_type='application/pdf', filename=original['filename'], as_attachment=False)
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'same-origin'
        return response
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return build_response(success=False, status=409, error={'blocked_reason': str(exc)})
