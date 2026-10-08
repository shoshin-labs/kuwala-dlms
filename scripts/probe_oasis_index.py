"""Read-only adapter probe using the configured station's existing validators."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--station-root', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--root')
    parser.add_argument('--model', default='nomic-embed-text:latest')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--artifacts-only', action='store_true', help='Validate immutable artifacts without contacting an embedding service.')
    args = parser.parse_args()
    sys.path.insert(0, args.station_root)
    from app.library.index import PdfLibrary, _load_manifest, _read_only
    from app.library.semantic import SemanticSearch, _client, _digest, _endpoint, _model_name, _passages
    import pypdf  # noqa: F401; the configured importer must actually be installed.
    result = {'lexical_available': True, 'vector_available': False, 'vector_blocked_reason': None}
    if not args.artifacts_only:
        try:
            endpoint = _endpoint(args.base_url)
            model = _model_name(args.model)
            with _client(endpoint, timeout=2) as client:
                result['model_digest'] = _digest(client, model)
            import sqlite_vec  # noqa: F401
            result['vector_available'] = True
        except Exception as exc:
            result['vector_blocked_reason'] = str(exc)
    if args.manifest:
        result['manifest'] = _load_manifest(Path(args.manifest))
    if args.root:
        library = PdfLibrary(Path(args.root))
        if not library.available:
            raise ValueError('Private draft passage index is missing or invalid.')
        snapshot = library._snapshot
        manifest = _load_manifest(snapshot / 'manifest.json')
        with _read_only(snapshot / 'index.sqlite3') as connection:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Private draft passage database integrity failed.')
            if dict(connection.execute('SELECT key,value FROM metadata')).get('library_version') != manifest['library_version']:
                raise ValueError('Private draft index version binding failed.')
        _passages(library, snapshot / 'index.sqlite3')
        documents = []
        for item in manifest['documents']:
            record = library.document(item['id'])
            if record is None:
                raise ValueError('Private draft original failed exact-hash validation: ' + item['id'])
            documents.append({'document_id': item['dlms_id'], 'filename': item['filename'], 'sha256': item['sha256'], 'page_count': record['page_count'], 'passage_count': record['passage_count']})
        semantic = SemanticSearch(library, args.model, args.base_url)
        vectors = Path(args.root) / 'semantic' / snapshot.name / 'vectors.sqlite3'
        vector_state, vector_reason = 'indexed', None
        if not vectors.is_file():
            vector_state, vector_reason = 'not_indexed', 'No vectors built for this private draft.'
        elif not semantic.available:
            vector_state, vector_reason = 'stale', semantic.error
        elif not args.artifacts_only and not result['vector_available']:
            vector_state, vector_reason = 'unavailable', result['vector_blocked_reason']
        elif not args.artifacts_only and semantic._digest != result.get('model_digest'):
            vector_state, vector_reason = 'stale', 'Installed model digest differs from the verified vectors.'
        result['receipt'] = {
            'snapshot': snapshot.name, 'index_sha256': sha(snapshot / 'index.sqlite3'),
            'vectors_sha256': sha(vectors) if vectors.is_file() else None,
            'lexical_valid': True, 'vector_valid': vector_state == 'indexed',
            'vector_artifact_valid': semantic.available,
            'vector_model_digest': semantic._digest if semantic.available else None,
            'vector_state': vector_state, 'vector_reason': vector_reason,
            'model_digest': result.get('model_digest'), 'documents': documents,
        }
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        raise SystemExit(2)
