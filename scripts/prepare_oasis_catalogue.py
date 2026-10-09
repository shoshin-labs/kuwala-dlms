#!/usr/bin/env python3
"""Prepare one exact authoring catalogue from read-only SQLite, without PDFs.

The transfer contains selected Django fixture records, local layout/module
assets and the unchanged reviewed manifest. Originals are verified here and
read separately from an explicitly selected published snapshot during import.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_ASSET_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_PDF_BYTES = 80 * 1024 * 1024
MODELS = ('metadatatype', 'metadata', 'user', 'liblayoutimage', 'librarymodule',
          'content', 'libraryversion', 'libraryfolder')
M2M = {
    'content': {'metadata': ('content_management_content_metadata', 'content_id', 'metadata_id')},
    'libraryversion': {
        'metadata_types': ('content_management_libraryversion_metadata_types', 'libraryversion_id', 'metadatatype_id'),
        'library_modules': ('content_management_libraryversion_library_modules', 'libraryversion_id', 'librarymodule_id'),
    },
    'libraryfolder': {'library_content': ('content_management_libraryfolder_library_content', 'libraryfolder_id', 'content_id')},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def private_path(value, label, *, directory=False):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise ValueError(label + ' must be an absolute path without parent traversal.')
    for parent in (*reversed(path.parents), path):
        if parent.is_symlink():
            raise ValueError(label + ' must not contain symlinks; select a resolved snapshot path.')
        if parent.exists() and parent != path and not parent.is_dir():
            raise ValueError(label + ' has a non-directory parent.')
    if directory and not path.is_dir():
        raise ValueError(label + ' must be an existing directory.')
    if not directory and not path.is_file():
        raise ValueError(label + ' must be an existing regular file.')
    return path


def media_relative(value, kind):
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Invalid stored media filename.')
    path = Path(value)
    prefixes = {'content': [('contents',)], 'liblayoutimage': [('images', 'logos'), ('images', 'banners')],
                'librarymodule': [('modules',)]}
    if path.is_absolute() or '..' in path.parts or path.name in ('.', '..'):
        raise ValueError('Stored media paths must be safe relative paths.')
    if tuple(path.parts[:-1]) not in prefixes[kind] or path.as_posix() != value:
        raise ValueError('Stored media path does not match its model.')
    return value


def positive(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + ' must be a positive integer.')
    return value


def reviewed_manifest(raw):
    if not 1 <= len(raw) <= MAX_MANIFEST_BYTES:
        raise ValueError('Reviewed manifest exceeds its byte limit.')
    manifest = json.loads(raw)
    if manifest.get('version') != 1 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}', manifest.get('library_version', '')):
        raise ValueError('Reviewed manifest needs a safe library version and schema version 1.')
    documents = manifest.get('documents')
    libraries = manifest.get('libraries')
    if not isinstance(documents, list) or not 1 <= len(documents) <= 128:
        raise ValueError('Reviewed manifest needs 1–128 documents.')
    if not isinstance(libraries, list) or not 1 <= len(libraries) <= 128:
        raise ValueError('Reviewed manifest needs explicit library memberships.')
    ids, slugs, filenames = set(), set(), set()
    for record in documents:
        pk = positive(record.get('dlms_id'), 'Document DLMS ID')
        slug, filename = record.get('id'), record.get('filename')
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', slug):
            raise ValueError('Invalid reviewed document slug.')
        if not isinstance(filename, str) or media_relative('contents/' + filename, 'content') != 'contents/' + filename:
            raise ValueError('Invalid reviewed original filename.')
        if not filename.lower().endswith('.pdf') or record.get('approved') is not True:
            raise ValueError('Every imported PDF needs its existing explicit review record.')
        if (('testing_only' in record or 'rights_review_pending' in record)
                and not (manifest.get('usage_scope') == 'private-development-testing'
                         and record.get('testing_only') is True and record.get('rights_review_pending') is True)):
            raise ValueError('Existing private-testing review scope must remain explicit and unchanged.')
        if not isinstance(record.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', record['sha256']):
            raise ValueError('Invalid reviewed original SHA-256.')
        if pk in ids or slug in slugs or filename.casefold() in filenames:
            raise ValueError('Reviewed document identities must be unique.')
        ids.add(pk); slugs.add(slug); filenames.add(filename.casefold())
    folder_ids, group_ids, covered = set(), set(), set()
    for library in libraries:
        pk = positive(library.get('dlms_folder_id'), 'Library DLMS folder ID')
        slug = library.get('id')
        members = library.get('document_ids')
        if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,95}', slug):
            raise ValueError('Invalid reviewed library slug.')
        if (pk in folder_ids or slug in group_ids or slug in slugs or not isinstance(members, list) or not members
                or len(set(members)) != len(members) or not set(members).issubset(slugs)):
            raise ValueError('Reviewed library identities/memberships must be complete and unique.')
        folder_ids.add(pk); group_ids.add(slug); covered.update(members)
    if covered != slugs:
        raise ValueError('Every reviewed PDF must belong to a reviewed library.')
    validate_manifest_sections(manifest)
    return manifest


def validate_manifest_sections(manifest):
    """Validate optional root-library/section definitions, without Django."""
    if 'sections' not in manifest:
        return None
    sections = manifest['sections']
    if not isinstance(sections, list) or len(sections) > 128:
        raise ValueError('Reviewed sections must be a bounded list.')
    libraries = {item['id']: item for item in manifest['libraries']}
    documents = {item['id'] for item in manifest['documents']}
    provider_ids = {'general-knowledge', 'fao-grain', 'fao-mycotoxin-part-1', 'fao-mycotoxin-part-2'}
    if documents & provider_ids or (set(libraries) & (provider_ids - {'general-knowledge'})):
        raise ValueError('Document/library IDs conflict with built-in knowledge providers.')
    identifiers = set(libraries) | documents | provider_ids
    folder_ids = {item['dlms_folder_id'] for item in manifest['libraries']}
    by_id = {}
    for section in sections:
        identifier = section.get('id')
        label = section.get('label')
        members = section.get('document_ids')
        folder_id = positive(section.get('dlms_folder_id'), 'Section DLMS folder ID')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', identifier) or len(identifier) > 64
                or identifier in identifiers or identifier in by_id or folder_id in folder_ids
                or not isinstance(label, str) or not label.strip() or len(label) > 200
                or section.get('library_id') not in libraries
                or not isinstance(members, list) or len(set(members)) != len(members)
                or not set(members).issubset(documents)):
            raise ValueError('Reviewed section identities, library and document scope must be complete and unique.')
        by_id[identifier] = section
        folder_ids.add(folder_id)
    for identifier, section in by_id.items():
        parent = section.get('parent_id')
        seen = {identifier}
        while parent is not None:
            if (parent not in by_id or parent in seen or len(seen) > 16
                    or by_id[parent]['library_id'] != section['library_id']):
                raise ValueError('Section parents must belong to the same library without cycles.')
            seen.add(parent)
            parent = by_id[parent].get('parent_id')
    return by_id


def validate_manifest_placement(manifest, folders, by_slug):
    """Bind exact numeric parents and deduplicated subtree scopes to review."""
    sections = validate_manifest_sections(manifest)
    if sections is None:
        for library in manifest.get('libraries', []):
            folder = folders.get(library['dlms_folder_id'])
            expected = {by_slug[slug] for slug in library['document_ids']}
            if (folder is None or folder.get('folder_name') != library['label']
                    or set(folder.get('library_content', [])) != expected):
                raise ValueError('Reviewed library label/direct memberships differ from authoring.')
        return
    libraries = {item['id']: item for item in manifest['libraries']}
    definitions = [*libraries.values(), *sections.values()]
    declared = {item['dlms_folder_id'] for item in definitions}
    # The hierarchical manifest describes the complete tree, including empty
    # sections, so an undeclared child cannot silently change a reviewed scope.
    if set(folders) != declared:
        raise ValueError('Reviewed libraries and sections must describe every authoring folder in this catalogue.')
    children = {}
    for identifier, folder in folders.items():
        parent = folder.get('parent')
        children.setdefault(parent, []).append(identifier)
    def scope(identifier):
        seen, pending, members = set(), [identifier], set()
        while pending:
            current = pending.pop()
            if current in seen or current not in folders:
                raise ValueError('Authoring section tree has a cycle or missing folder.')
            seen.add(current)
            members.update(folders[current].get('library_content', []))
            pending.extend(children.get(current, []))
        return members
    for definition in definitions:
        folder = folders.get(definition['dlms_folder_id'])
        parent = None
        if definition['id'] in sections:
            ancestor = sections.get(definition.get('parent_id')) or libraries[definition['library_id']]
            parent = ancestor['dlms_folder_id']
        expected = {by_slug[slug] for slug in definition['document_ids']}
        if (folder is None or folder.get('folder_name') != definition['label']
                or folder.get('parent') != parent or scope(definition['dlms_folder_id']) != expected):
            raise ValueError('Reviewed library/section label, parent or descendant document scope differs from authoring.')


def validate_package(package):
    if not isinstance(package, dict) or package.get('format') != 'oasis-authoring-transfer-v1':
        raise ValueError('Unsupported authoring transfer format.')
    payload = {key: value for key, value in package.items() if key != 'package_sha256'}
    if hashlib.sha256(canonical(payload)).hexdigest() != package.get('package_sha256'):
        raise ValueError('Authoring transfer checksum mismatch.')
    raw = base64.b64decode(package.get('reviewed_manifest_base64', ''), validate=True)
    if hashlib.sha256(raw).hexdigest() != package.get('reviewed_manifest_sha256'):
        raise ValueError('Reviewed manifest checksum mismatch.')
    manifest = reviewed_manifest(raw)
    rows = package.get('fixture')
    if not isinstance(rows, list) or not rows or len(rows) > 10_000:
        raise ValueError('Invalid selected authoring fixture.')
    by_model = {name: {} for name in MODELS}
    for row in rows:
        name = row.get('model', '').removeprefix('content_management.')
        if row.get('model') != 'content_management.' + name or name not in by_model:
            raise ValueError('Only selected authoring models may be transferred.')
        pk = positive(row.get('pk'), 'Fixture primary key')
        if pk in by_model[name] or not isinstance(row.get('fields'), dict):
            raise ValueError('Fixture identities must be unique.')
        by_model[name][pk] = row['fields']
    versions = by_model['libraryversion']
    if len(versions) != 1 or package.get('version_id') not in versions:
        raise ValueError('Transfer must contain exactly the selected authoring version.')
    version_id = package['version_id']
    if versions[version_id].get('version_number') != manifest['library_version']:
        raise ValueError('Authoring version differs from reviewed manifest.')
    documents = {record['dlms_id']: record for record in manifest['documents']}
    if set(documents) != set(by_model['content']):
        raise ValueError('Selected authoring records must exactly match reviewed documents.')
    linked = set()
    for pk, folder in by_model['libraryfolder'].items():
        if folder.get('version') != version_id or not set(folder.get('library_content', [])).issubset(documents):
            raise ValueError('Transferred folders must belong to this version and reference selected documents.')
        parent = folder.get('parent')
        seen = {pk}
        while parent is not None:
            positive(parent, 'Parent folder ID')
            if parent not in by_model['libraryfolder'] or parent in seen:
                raise ValueError('Folder parent must be in the same selected version without cycles.')
            seen.add(parent)
            parent = by_model['libraryfolder'][parent].get('parent')
        linked.update(folder.get('library_content', []))
    if linked != set(documents):
        raise ValueError('Selected authoring membership differs from reviewed documents.')
    slug_to_pk = {record['id']: record['dlms_id'] for record in manifest['documents']}
    validate_manifest_placement(manifest, by_model['libraryfolder'], slug_to_pk)
    def relation_ids(fields, name):
        values = fields.get(name)
        if not isinstance(values, list) or len(set(values)) != len(values):
            raise ValueError('Fixture many-to-many memberships must be unique lists.')
        return {positive(value, 'Related fixture ID') for value in values}

    metadata_ids = set()
    for fields in by_model['content'].values():
        metadata_ids.update(relation_ids(fields, 'metadata'))
    if metadata_ids != set(by_model['metadata']):
        raise ValueError('Fixture metadata must exactly match selected document references.')
    type_ids = {positive(fields.get('type'), 'Metadata type ID') for fields in by_model['metadata'].values()}
    user_ids, module_ids, image_ids = set(), set(), set()
    for fields in versions.values():
        type_ids.update(relation_ids(fields, 'metadata_types'))
        module_ids.update(relation_ids(fields, 'library_modules'))
        if fields.get('created_by') is not None:
            user_ids.add(positive(fields['created_by'], 'Authoring user ID'))
        if fields.get('library_banner') is not None:
            image_ids.add(positive(fields['library_banner'], 'Banner image ID'))
    for fields in (*by_model['libraryfolder'].values(), *by_model['librarymodule'].values()):
        if fields.get('logo_img') is not None:
            image_ids.add(positive(fields['logo_img'], 'Logo image ID'))
    for name, expected in (('metadatatype', type_ids), ('user', user_ids), ('librarymodule', module_ids), ('liblayoutimage', image_ids)):
        if set(by_model[name]) != expected:
            raise ValueError('Fixture must contain the exact selected relation closure: ' + name)
    originals = package.get('originals', [])
    if len(originals) != len(documents) or {row.get('content_id') for row in originals} != set(documents):
        raise ValueError('Original file inventory differs from selected authoring records.')
    for original in originals:
        record = documents[original['content_id']]
        content = by_model['content'][original['content_id']]
        expected_path = 'contents/' + record['filename']
        if (original.get('path') != expected_path or original.get('sha256') != record['sha256']
                or content.get('content_file') != expected_path or content.get('file_name') != record['filename']
                or content.get('title') != record.get('title') or content.get('active') is not True
                or type(original.get('size')) is not int or not 1 <= original['size'] <= MAX_PDF_BYTES
                or content.get('filesize') != original['size']):
            raise ValueError('Original filename/hash/size/title differs from reviewed authoring record.')
    assets = package.get('assets', [])
    expected_assets = {}
    for name, field in (('liblayoutimage', 'image_file'), ('librarymodule', 'module_file')):
        for fields in by_model[name].values():
            relative = media_relative(fields.get(field), name)
            expected_assets[relative] = name
    if len(assets) != len(expected_assets) or {row.get('path') for row in assets} != set(expected_assets):
        raise ValueError('Selected layout/module asset inventory is incomplete.')
    for asset in assets:
        data = base64.b64decode(asset.get('base64', ''), validate=True)
        if (not 1 <= len(data) <= MAX_ASSET_BYTES or len(data) != asset.get('size')
                or hashlib.sha256(data).hexdigest() != asset.get('sha256')):
            raise ValueError('Transferred asset checksum/size mismatch.')
    return manifest, raw, by_model


def prepare(database, version_id, media_root, manifest_path):
    database = private_path(database, 'Source database')
    media_root = private_path(media_root, 'Source media root', directory=True)
    raw = private_path(manifest_path, 'Reviewed manifest').read_bytes()
    manifest = reviewed_manifest(raw)
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN')
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source SQLite integrity check failed.')

        def rows(name, ids=None, where=None, args=()):
            query = 'SELECT * FROM content_management_' + name
            if ids is not None:
                if not ids:
                    return []
                query += ' WHERE id IN (' + ','.join('?' for _ in ids) + ')'
                args = tuple(sorted(ids))
            elif where:
                query += ' WHERE ' + where
            return list(connection.execute(query + ' ORDER BY id', args))

        def links(name, field, pk):
            table, left, right = M2M[name][field]
            return [row[0] for row in connection.execute('SELECT ' + right + ' FROM ' + table + ' WHERE ' + left + '=? ORDER BY ' + right, (pk,))]

        version_rows = rows('libraryversion', {positive(version_id, 'Selected version ID')})
        if len(version_rows) != 1 or version_rows[0]['version_number'] != manifest['library_version']:
            raise ValueError('Selected source version does not match the reviewed manifest.')
        folder_rows = rows('libraryfolder', where='version_id=?', args=(version_id,))
        document_ids = {pk for folder in folder_rows for pk in links('libraryfolder', 'library_content', folder['id'])}
        if document_ids != {record['dlms_id'] for record in manifest['documents']}:
            raise ValueError('Selected version must contain exactly the reviewed documents.')
        content_rows = rows('content', document_ids)
        metadata_ids = {pk for row in content_rows for pk in links('content', 'metadata', row['id'])}
        metadata_rows = rows('metadata', metadata_ids)
        type_ids = {row['type_id'] for row in metadata_rows} | set(links('libraryversion', 'metadata_types', version_id))
        module_rows = rows('librarymodule', set(links('libraryversion', 'library_modules', version_id)))
        image_ids = {row['logo_img_id'] for row in folder_rows + module_rows if row['logo_img_id'] is not None}
        if version_rows[0]['library_banner_id'] is not None:
            image_ids.add(version_rows[0]['library_banner_id'])
        author_id = version_rows[0]['created_by_id']
        selected = {
            'metadatatype': rows('metadatatype', type_ids), 'metadata': metadata_rows,
            'user': rows('user', {author_id} if author_id else set()),
            'liblayoutimage': rows('liblayoutimage', image_ids), 'librarymodule': module_rows,
            'content': content_rows, 'libraryversion': version_rows, 'libraryfolder': folder_rows,
        }
        fixture = []
        for name in MODELS:
            for row in selected[name]:
                fields = {key.removesuffix('_id') if key.endswith('_id') else key: row[key]
                          for key in row.keys() if key != 'id'}
                if name == 'content':
                    fields['active'] = bool(fields['active']); fields['duplicatable'] = bool(fields['duplicatable'])
                for field in ('modified_on', 'created_on'):
                    if field in fields and fields[field]:
                        # Python 3.10 does not accept Django's UTC "Z" suffix.
                        rendered = fields[field]
                        if rendered.endswith('Z'):
                            rendered = rendered[:-1] + '+00:00'
                        value = datetime.fromisoformat(rendered)
                        # Django's USE_TZ SQLite storage is UTC without an offset.
                        if value.tzinfo is None:
                            value = value.replace(tzinfo=timezone.utc)
                        fields[field] = value.isoformat()
                for field in M2M.get(name, {}):
                    fields[field] = links(name, field, row['id'])
                fixture.append({'model': 'content_management.' + name, 'pk': row['id'], 'fields': fields})
        originals, assets = [], []
        manifest_docs = {record['dlms_id']: record for record in manifest['documents']}
        for row in content_rows:
            relative = media_relative(row['content_file'], 'content')
            source = private_path(media_root / relative, 'Source original')
            size = source.stat().st_size
            sha = digest(source)
            if not 1 <= size <= MAX_PDF_BYTES or sha != manifest_docs[row['id']]['sha256']:
                raise ValueError('Source original does not match reviewed hash/size: ' + relative)
            originals.append({'content_id': row['id'], 'path': relative, 'sha256': sha, 'size': size})
        asset_paths = set()
        for name, field in (('liblayoutimage', 'image_file'), ('librarymodule', 'module_file')):
            for row in selected[name]:
                relative = media_relative(row[field], name)
                if relative in asset_paths:
                    continue
                source = private_path(media_root / relative, 'Source asset')
                if not 1 <= source.stat().st_size <= MAX_ASSET_BYTES:
                    raise ValueError('Source asset exceeds transfer bounds.')
                data = source.read_bytes()
                assets.append({'path': relative, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
                               'base64': base64.b64encode(data).decode('ascii')})
                asset_paths.add(relative)
        package = {'format': 'oasis-authoring-transfer-v1', 'version_id': version_id, 'fixture': fixture,
                   'originals': originals, 'assets': assets, 'reviewed_manifest_base64': base64.b64encode(raw).decode('ascii'),
                   'reviewed_manifest_sha256': hashlib.sha256(raw).hexdigest()}
        package['package_sha256'] = hashlib.sha256(canonical(package)).hexdigest()
        validate_package(package)
        return package
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--version-id', required=True, type=int)
    parser.add_argument('--media-root', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New private JSON transfer file; never overwrite.')
    args = parser.parse_args()
    try:
        package = prepare(args.database, args.version_id, args.media_root, args.manifest)
        data = canonical(package) + b'\n'
        if len(data) > MAX_PACKAGE_BYTES:
            raise ValueError('Authoring transfer exceeds its byte limit.')
        output = args.output
        if not output.is_absolute() or '..' in output.parts or output.is_symlink():
            raise ValueError('Output must be an absolute new file without traversal.')
        private_path(output.parent, 'Transfer directory', directory=True)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({'package': str(output), 'package_sha256': package['package_sha256'],
                          'version_id': args.version_id, 'documents': len(package['originals']),
                          'assets': len(package['assets']), 'reviewed_manifest_sha256': package['reviewed_manifest_sha256']}))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.exit(1, 'Transfer preparation failed: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
