"""Read existing station passage indexes; no extraction, chat or activation."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--station-root', required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--query', required=True)
    parser.add_argument('--sources', required=True)
    parser.add_argument('--profile', choices=('lexical', 'semantic'), required=True)
    parser.add_argument('--model', default='nomic-embed-text:latest')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    args = parser.parse_args()
    sys.path.insert(0, args.station_root)
    from app.library.index import MAX_DOCUMENTS, PdfLibrary, _load_manifest
    from app.library.semantic import SemanticSearch

    library = PdfLibrary(Path(args.root))
    if not library.available:
        raise ValueError('The private draft passage index is unavailable.')
    manifest = _load_manifest(library._snapshot / 'manifest.json')
    records = {item['id']: item for item in manifest['documents']}
    sources = json.loads(args.sources)
    if not isinstance(sources, list) or not sources or len(sources) > MAX_DOCUMENTS or any(not isinstance(source, str) or source not in records for source in sources):
        raise ValueError('Use existing reviewed document identifiers within the selected scope.')
    provider = library
    if args.profile == 'semantic':
        provider = SemanticSearch(library, args.model, args.base_url)
        if not provider.available:
            raise ValueError(provider.error or 'The private draft has no matching semantic vectors.')
    hits = provider.search(args.query, sources=sources, limit=10)
    if args.profile == 'semantic' and provider.last_error:
        # Existing semantic search falls back to keywords. The explicit UI
        # semantic mode must report that failure instead of labelling it AI.
        raise ValueError(provider.last_error)
    results = []
    for hit in hits:
        passage = library.read(hit['id'])
        if passage is None or passage['document_id'] not in sources:
            raise ValueError('A matching passage failed original-document verification.')
        reviewed = records[passage['document_id']]
        results.append({'document_id': reviewed['dlms_id'], 'title': passage['title'],
                        'filename': passage['filename'], 'original_sha256': passage['sha256'],
                        'page': passage['page'], 'text': passage['text'][:1400],
                        **{name: passage[name] for name in ('publisher', 'authors', 'source_url', 'licence', 'licence_url')}})
    print(json.dumps({'snapshot': library._snapshot.name, 'profile_used': args.profile, 'results': results}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        raise SystemExit(2)
