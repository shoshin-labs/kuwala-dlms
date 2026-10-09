"""Additive private library bundles; independent of publication and indexing."""
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
import zlib
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import DatabaseError, transaction
from django.http import FileResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import get_valid_filename
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from dlms.preview_middleware import PrivatePreviewMiddleware
from dlms.private_paths import checked_directory, checked_path
from content_management.models import Content, LibraryFolder, LibraryVersion, Metadata, MetadataType
from content_management.oasis_documents import PrivateCuratorAccess
from content_management.standardize_format import build_response

logger = logging.getLogger(__name__)
FORMAT = 'oasis-library-bundle'
SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_PDF_BYTES = 80 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_DOCUMENTS = 512
MAX_FOLDERS = 512
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_METADATA_VALUES = 8192
MAX_DEPTH = 64
CHUNK = 65536
MANIFEST = 'manifest.json'
TEXT_FIELDS = ('title', 'display_title', 'description', 'copyright_notes', 'rights_statement', 'additional_notes')
DATE_FIELDS = ('published_date', 'reviewed_on')
CONTENT_FIELDS = frozenset((*TEXT_FIELDS, *DATE_FIELDS, 'modified_on', 'active', 'duplicatable'))


def invalid(message):
    raise serializers.ValidationError({'bundle': message})


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        invalid(label + ' has missing or unsupported fields.')


def identifier(value, label):
    if type(value) is not int or not 1 <= value <= 9223372036854775807:
        invalid(label + ' must be a positive integer.')
    return value


def text(value, limit, label, *, nullable=False, empty=False):
    if value is None and nullable:
        return value
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (not empty and not value.strip()):
        invalid(label + ' must be readable text of at most ' + str(limit) + ' characters.')
    return value


def filename(value):
    text(value, 255, 'Original filename')
    if '/' in value or '\\' in value or any(ord(char) < 32 for char in value) or not value.lower().endswith('.pdf'):
        invalid('Every original must have a plain PDF filename.')
    try:
        get_valid_filename(value)
    except Exception:
        invalid('Original filename is invalid.')
    return value


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            invalid('The manifest contains duplicate JSON fields.')
        result[key] = value
    return result


def validate_manifest(manifest):
    exact_keys(manifest, ('format', 'version', 'library', 'folders', 'documents'), 'Manifest')
    if manifest['format'] != FORMAT or type(manifest['version']) is not int or manifest['version'] != SCHEMA_VERSION:
        invalid('This is not a supported Oasis library bundle.')
    library = manifest['library']
    exact_keys(library, ('source_id', 'name'), 'Library')
    root_id = identifier(library['source_id'], 'Library source ID')
    text(library['name'], 300, 'Library name')
    folders, documents = manifest['folders'], manifest['documents']
    if not isinstance(folders, list) or not 1 <= len(folders) <= MAX_FOLDERS:
        invalid('A bundle must contain one library and at most 512 library/section folders.')
    if not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS:
        invalid('A bundle may contain at most 512 PDF documents.')
    folder_map, children, referenced = {}, defaultdict(list), set()
    for folder in folders:
        exact_keys(folder, ('source_id', 'name', 'parent_source_id', 'document_source_ids'), 'Folder')
        source_id = identifier(folder['source_id'], 'Folder source ID')
        if source_id in folder_map:
            invalid('Folder source IDs must be unique.')
        text(folder['name'], 300, 'Folder name')
        parent = folder['parent_source_id']
        if parent is not None:
            identifier(parent, 'Parent source ID')
        memberships = folder['document_source_ids']
        if not isinstance(memberships, list) or len(memberships) > MAX_DOCUMENTS:
            invalid('Folder document references are invalid.')
        for value in memberships:
            identifier(value, 'Document membership source ID')
        if len(set(memberships)) != len(memberships):
            invalid('A folder repeats a document membership.')
        referenced.update(memberships)
        folder_map[source_id] = folder
        children[parent].append(source_id)
    if children[None] != [root_id] or folder_map.get(root_id, {}).get('name') != library['name']:
        invalid('The bundle must contain exactly its named root library.')
    ordered, pending = [], deque([(root_id, 0)])
    while pending:
        current, depth = pending.popleft()
        if depth > MAX_DEPTH or current in ordered:
            invalid('Library sections contain a cycle or exceed 64 levels.')
        ordered.append(current)
        pending.extend((child, depth + 1) for child in children[current])
    if len(ordered) != len(folder_map):
        invalid('Every section must belong to the root library with valid, acyclic parents.')
    document_map, members, total_bytes, total_metadata = {}, set(), 0, 0
    for document in documents:
        exact_keys(document, ('source_id', 'filename', 'member', 'sha256', 'size', 'fields', 'metadata'), 'Document')
        source_id = identifier(document['source_id'], 'Document source ID')
        if source_id in document_map:
            invalid('Document source IDs must be unique.')
        filename(document['filename'])
        if document['member'] != 'documents/' + str(source_id) + '.pdf':
            invalid('Document members must use their declared canonical PDF path.')
        if not isinstance(document['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', document['sha256']):
            invalid('Every PDF needs a valid SHA-256 checksum.')
        size = document['size']
        if type(size) is not int or not 1 <= size <= MAX_PDF_BYTES:
            invalid('Every PDF must be nonempty and at most 80 MiB.')
        total_bytes += size
        if total_bytes > MAX_EXPANDED_BYTES:
            invalid('Expanded original PDFs exceed the 512 MiB library limit.')
        fields = document['fields']
        exact_keys(fields, CONTENT_FIELDS, 'Document metadata')
        text(fields['title'], 300, 'Document title')
        text(fields['display_title'], 300, 'Display title', empty=True)
        for name in ('description', 'copyright_notes', 'rights_statement', 'additional_notes'):
            text(fields[name], 65536, name, nullable=True, empty=True)
        for name in ('active', 'duplicatable'):
            if type(fields[name]) is not bool:
                invalid(name + ' must be a boolean.')
        for name in DATE_FIELDS:
            value = fields[name]
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    invalid(name + ' must be an ISO date or null.')
                try:
                    parsed = parse_date(value)
                except ValueError:
                    parsed = None
                if parsed is None:
                    invalid(name + ' is not a valid date.')
        modified = fields['modified_on']
        try:
            parsed = parse_datetime(modified) if isinstance(modified, str) and len(modified) <= 64 else None
        except (ValueError, TypeError):
            parsed = None
        if parsed is None:
            invalid('modified_on must be an ISO date and time.')
        metadata = document['metadata']
        if not isinstance(metadata, list) or len(metadata) > 128:
            invalid('A document may contain at most 128 metadata values.')
        reserve_filename = not any(isinstance(value, dict) and value.get('type') == 'Transfer original filename' for value in metadata)
        if len(metadata) + int(reserve_filename) > 128:
            invalid('A document may contain at most 128 metadata values including original-filename provenance.')
        total_metadata += len(metadata) + int(reserve_filename)
        if total_metadata > MAX_METADATA_VALUES:
            invalid('The bundle contains too many metadata values.')
        seen_metadata = set()
        for value in metadata:
            exact_keys(value, ('type', 'name'), 'Metadata value')
            text(value['type'], 100, 'Metadata type')
            text(value['name'], 500, 'Metadata value')
            pair = value['type'], value['name']
            if pair in seen_metadata:
                invalid('A document repeats a metadata value.')
            seen_metadata.add(pair)
        document_map[source_id] = document
        members.add(document['member'])
    if referenced != set(document_map):
        invalid('Document references must match the PDFs exactly; every document must belong to a library or section.')
    return ordered, document_map, members, total_bytes


def copy_pdf(source, target, limit, *, expected_size=None, expected_hash=None):
    digest, total, header, tail = hashlib.sha256(), 0, b'', b''
    while True:
        chunk = source.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            invalid('An original PDF exceeds its declared or allowed size.')
        header = (header + chunk)[:8]
        tail = (tail + chunk)[-1024:]
        digest.update(chunk)
        target.write(chunk)
    if not header.startswith(b'%PDF-') or b'%%EOF' not in tail:
        invalid('An original does not have a PDF header and end marker.')
    value = digest.hexdigest()
    if expected_size is not None and total != expected_size:
        invalid('An original PDF does not match its declared size.')
    if expected_hash is not None and value != expected_hash:
        invalid('An original PDF does not match its SHA-256 checksum.')
    return total, value


def library_name_conflict(version, library_name):
    candidate = library_name.strip().casefold()
    names = LibraryFolder.objects.filter(version=version, parent__isnull=True).values_list('folder_name', flat=True)
    return any(name.strip().casefold() == candidate for name in names)


class InspectedBundle:
    def __init__(self, upload):
        self.temporary = tempfile.TemporaryDirectory(prefix='oasis-library-inspect-')
        self.paths = {}
        try:
            if not 0 < upload.size <= MAX_ARCHIVE_BYTES:
                invalid('Choose a library ZIP of at most 80 MiB.')
            upload.seek(0)
            if upload.read(4) != b'PK\x03\x04':
                invalid('Choose an ordinary ZIP library bundle.')
            upload.seek(0)
            digest, uploaded_bytes = hashlib.sha256(), 0
            for chunk in iter(lambda: upload.read(CHUNK), b''):
                uploaded_bytes += len(chunk)
                if uploaded_bytes > MAX_ARCHIVE_BYTES:
                    invalid('Choose a library ZIP of at most 80 MiB.')
                digest.update(chunk)
            self.sha256 = digest.hexdigest()
            upload.seek(0)
            with zipfile.ZipFile(upload) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_DOCUMENTS + 1:
                    invalid('The ZIP contains too many entries.')
                names = set()
                for entry in entries:
                    name, mode = entry.filename, entry.external_attr >> 16
                    parts = PurePosixPath(name).parts
                    if not name or entry.orig_filename != name or '\\' in name or '\x00' in name or name.startswith('/') or '..' in parts or name != str(PurePosixPath(name)):
                        invalid('ZIP paths must be plain relative paths without traversal.')
                    if name in names:
                        invalid('The ZIP contains duplicate members.')
                    names.add(name)
                    if entry.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                        invalid('ZIP entries must be regular, unencrypted files, without links or directories.')
                    if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        invalid('Use a ZIP with stored or deflated entries.')
                if MANIFEST not in names:
                    invalid('The ZIP needs an Oasis manifest.json file.')
                info = archive.getinfo(MANIFEST)
                if info.file_size > MAX_MANIFEST_BYTES:
                    invalid('The library manifest exceeds 4 MiB.')
                with archive.open(info) as stream:
                    raw = stream.read(MAX_MANIFEST_BYTES + 1)
                if len(raw) > MAX_MANIFEST_BYTES:
                    invalid('The library manifest exceeds 4 MiB.')
                try:
                    self.manifest = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_json)
                except (ValueError, UnicodeError, RecursionError):
                    invalid('The library manifest must be valid UTF-8 JSON.')
                self.ordered, self.documents, members, self.original_bytes = validate_manifest(self.manifest)
                if names != members | {MANIFEST}:
                    invalid('The ZIP entries must exactly match the declared original PDFs.')
                for source_id, document in self.documents.items():
                    info = archive.getinfo(document['member'])
                    if info.file_size != document['size'] or info.file_size > MAX_PDF_BYTES:
                        invalid('ZIP sizes do not match the declared PDFs.')
                    path = Path(self.temporary.name) / (uuid.uuid4().hex + '.pdf')
                    with archive.open(info) as source, path.open('xb') as target:
                        os.chmod(path, 0o600)
                        copy_pdf(source, target, document['size'], expected_size=document['size'], expected_hash=document['sha256'])
                    self.paths[source_id] = path
        except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, OSError, zlib.error):
            self.close()
            invalid('The ZIP or its original PDFs are unreadable or corrupt.')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.temporary.cleanup()

    def plan(self, version, library_name):
        conflict = library_name_conflict(version, library_name)
        warnings = ['Import creates a new private library and documents. It does not publish, approve technical advice, or index documents.']
        warnings.append('Imported originals receive unique filenames; the source filenames are retained in document metadata.')
        if conflict:
            warnings.append('A library with this name already exists. Choose a different library name before importing.')
        return {'dry_run': True, 'bundle_sha256': self.sha256, 'library_name': library_name,
                'source_library_name': self.manifest['library']['name'], 'section_count': len(self.ordered) - 1,
                'document_count': len(self.documents), 'original_bytes': self.original_bytes,
                'name_conflict': conflict, 'can_import': not conflict, 'warnings': warnings}


def apply_bundle(bundle, version, library_name):
    root = checked_directory(settings.MEDIA_ROOT, 'Library originals root')
    directory = checked_directory(root / 'contents', 'Library originals directory')
    created, committed = [], False
    try:
        with transaction.atomic():
            version = LibraryVersion.objects.select_for_update().get(pk=version.pk)
            if library_name_conflict(version, library_name):
                invalid('A library with this name already exists. Choose a different name before importing.')
            folder_map, document_map, metadata_types = {}, {}, set()
            for source_id in bundle.ordered:
                source = next(folder for folder in bundle.manifest['folders'] if folder['source_id'] == source_id)
                parent_id = source['parent_source_id']
                folder_map[source_id] = LibraryFolder.objects.create(
                    version=version, folder_name=library_name if parent_id is None else source['name'],
                    parent=folder_map[parent_id] if parent_id is not None else None)
            if bundle.documents:
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            for source_id, source in bundle.documents.items():
                stem = get_valid_filename(source['filename'])[:-4].encode('utf-8')[:218].decode('utf-8', errors='ignore') or 'original'
                candidate = directory / (uuid.uuid4().hex + '-' + stem + '.pdf')
                created.append(candidate)
                descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, 'wb') as target, bundle.paths[source_id].open('rb') as original:
                    shutil.copyfileobj(original, target, CHUNK)
                fields = dict(source['fields'])
                for name in DATE_FIELDS:
                    fields[name] = parse_date(fields[name]) if fields[name] else None
                fields['modified_on'] = parse_datetime(fields['modified_on'])
                document = Content.objects.create(content_file=str(candidate.relative_to(root)),
                    file_name=candidate.name, filesize=source['size'], **fields)
                values = []
                transferred_metadata = list(source['metadata'])
                if not any(value['type'] == 'Transfer original filename' for value in transferred_metadata):
                    transferred_metadata.append({'type': 'Transfer original filename', 'name': source['filename']})
                for value in transferred_metadata:
                    kind, _ = MetadataType.objects.get_or_create(name=value['type'])
                    metadata_types.add(kind.pk)
                    item = Metadata.objects.filter(type=kind, name=value['name']).order_by('pk').first()
                    if item is None:
                        item = Metadata.objects.create(type=kind, name=value['name'])
                    values.append(item)
                document.metadata.set(values)
                document_map[source_id] = document
            for source in bundle.manifest['folders']:
                folder_map[source['source_id']].library_content.add(*(document_map[key] for key in source['document_source_ids']))
            version.metadata_types.add(*metadata_types)
        committed = True
        library = folder_map[bundle.manifest['library']['source_id']]
        return {'dry_run': False, 'library': {'id': library.pk, 'name': library.folder_name},
                'section_count': len(folder_map) - 1, 'document_count': len(document_map),
                'document_ids': [item.pk for item in document_map.values()], 'bundle_sha256': bundle.sha256}
    except BaseException:
        if not committed:
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.exception('Unable to remove a rolled-back library original.')
        raise


def export_library(library):
    folders = list(LibraryFolder.objects.filter(version_id=library.version_id).only('pk', 'folder_name', 'parent', 'version').order_by('pk'))
    by_parent = defaultdict(list)
    for folder in folders:
        by_parent[folder.parent_id].append(folder)
    selected, pending, seen = [], deque([library]), set()
    while pending:
        folder = pending.popleft()
        if folder.pk in seen or len(seen) >= MAX_FOLDERS:
            invalid('This library has an invalid or oversized section hierarchy.')
        selected.append(folder)
        seen.add(folder.pk)
        pending.extend(by_parent[folder.pk])
    documents = Content.objects.filter(libraryfolder__pk__in=seen).distinct().prefetch_related('metadata__type').order_by('pk')
    if documents.count() > MAX_DOCUMENTS:
        invalid('A portable library bundle supports at most 512 PDF documents.')
    manifest = {'format': FORMAT, 'version': SCHEMA_VERSION, 'library': {'source_id': library.pk, 'name': library.folder_name},
                'folders': [{'source_id': folder.pk, 'name': folder.folder_name, 'parent_source_id': folder.parent_id,
                             'document_source_ids': sorted(folder.library_content.values_list('pk', flat=True))} for folder in selected],
                'documents': []}
    output = tempfile.TemporaryFile(mode='w+b', prefix='oasis-library-export-', suffix='.zip')
    os.fchmod(output.fileno(), 0o600)
    try:
        root = checked_directory(settings.MEDIA_ROOT, 'Library originals root')
        total = 0
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for document in documents:
                relative = document.content_file.name
                if not relative or PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts or '\\' in relative:
                    invalid('A library original is unavailable. Repair it before exporting.')
                path = checked_path(root / relative, 'Library original')
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, 'rb') as original:
                    info = os.fstat(original.fileno())
                    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PDF_BYTES:
                        invalid('Every library original must be a regular PDF of at most 80 MiB.')
                    if total + info.st_size > MAX_EXPANDED_BYTES:
                        invalid('Expanded original PDFs exceed the 512 MiB library limit.')
                    member = 'documents/' + str(document.pk) + '.pdf'
                    with archive.open(member, 'w') as target:
                        size, digest = copy_pdf(original, target, min(MAX_PDF_BYTES, MAX_EXPANDED_BYTES - total))
                    total += size
                    fields = {name: getattr(document, name) for name in CONTENT_FIELDS}
                    for name in (*DATE_FIELDS, 'modified_on'):
                        fields[name] = fields[name].isoformat() if fields[name] is not None else None
                    manifest['documents'].append({'source_id': document.pk,
                        'filename': filename(document.file_name or path.name), 'member': member, 'sha256': digest, 'size': size,
                        'fields': fields, 'metadata': [{'type': item.type.name, 'name': item.name} for item in document.metadata.all()]})
            validate_manifest(manifest)
            raw = json.dumps(manifest, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
            if len(raw) > MAX_MANIFEST_BYTES:
                invalid('The library manifest exceeds 4 MiB; this library cannot be bundled.')
            archive.writestr(MANIFEST, raw)
        if output.tell() > MAX_ARCHIVE_BYTES:
            invalid('The resulting ZIP exceeds 80 MiB. Export a smaller library so the bundle can be imported.')
        output.seek(0)
        try:
            download_name = get_valid_filename(library.folder_name)
        except SuspiciousFileOperation:
            download_name = 'oasis'
        response = FileResponse(output, content_type='application/zip', as_attachment=True,
                                filename=download_name + '-library.zip')
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'same-origin'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'"
        return response
    except (OSError, ValueError) as error:
        output.close()
        invalid('A library original is unavailable or unsafe. Repair it before exporting.')
    except BaseException:
        output.close()
        raise


class LibraryTransferStaff(BasePermission):
    message = 'Library transfers require an active administrator session on the private curator origin.'

    def has_permission(self, request, view):
        if not PrivatePreviewMiddleware.browser_origin_allowed(request):
            return False
        # Respect the existing explicitly enabled loopback preview profile;
        # production device settings always require a fresh active staff user.
        if not getattr(settings, 'OASIS_REQUIRE_CURATOR_AUTH', False):
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff)


class LibraryBundleExportView(APIView):
    permission_classes = (PrivateCuratorAccess, LibraryTransferStaff)

    def get(self, request, library_id):
        try:
            library = LibraryFolder.objects.get(pk=library_id, parent__isnull=True)
        except LibraryFolder.DoesNotExist:
            raise serializers.ValidationError({'library': 'Choose an existing root library to export.'})
        return export_library(library)


class LibraryBundleImportView(APIView):
    permission_classes = (PrivateCuratorAccess, LibraryTransferStaff)
    parser_classes = (MultiPartParser,)

    def post(self, request):
        length = request.META.get('CONTENT_LENGTH', '')
        if length.isdigit() and int(length) > MAX_ARCHIVE_BYTES + 65536:
            invalid('Choose a library ZIP of at most 80 MiB.')
        allowed = {'bundle', 'catalogue_version', 'expected_sha256', 'confirmed', 'library_name'}
        if set(request.data) - allowed:
            invalid('Unsupported library import fields.')
        if any(len(request.data.getlist(key)) != 1 for key in request.data) or set(request.query_params) - {'dry_run'}:
            invalid('Library import controls must appear exactly once.')
        if len(request.query_params.getlist('dry_run')) > 1 or request.query_params.get('dry_run', '0') not in ('0', '1'):
            invalid('Use dry_run=1 to inspect a library bundle.')
        inputs = LibraryBundleImportSerializer(data=request.data)
        inputs.is_valid(raise_exception=True)
        values = inputs.validated_data
        bundle = InspectedBundle(values['bundle'])
        try:
            library_name = values.get('library_name', bundle.manifest['library']['name'])
            if request.query_params.get('dry_run') == '1':
                return build_response(bundle.plan(values['catalogue_version'], library_name))
            if not values['confirmed'] or values.get('expected_sha256') != bundle.sha256:
                invalid('Inspect this exact bundle first, then confirm its returned SHA-256 before importing.')
            try:
                result = apply_bundle(bundle, values['catalogue_version'], library_name)
            except LibraryVersion.DoesNotExist:
                raise serializers.ValidationError({'catalogue_version': 'The selected catalogue changed. Reload and try again.'})
            except (OSError, ValueError, DatabaseError):
                invalid('The library could not be stored. No new library or documents were saved; try again.')
            return build_response(result, status=201)
        finally:
            bundle.close()


class LibraryBundleImportSerializer(serializers.Serializer):
    bundle = serializers.FileField()
    catalogue_version = serializers.PrimaryKeyRelatedField(queryset=LibraryVersion.objects.all())
    library_name = serializers.CharField(max_length=300, required=False, allow_blank=False)
    expected_sha256 = serializers.RegexField(r'^[0-9a-f]{64}$', required=False)
    confirmed = serializers.BooleanField(required=False, default=False)
