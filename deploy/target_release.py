#!/usr/bin/env python3
"""Private curator target operations. With no command, only inspect the device."""
import argparse
from contextlib import closing
import email
import hashlib
import html.parser
import json
import os
import platform
import pwd
import re
import shlex
import shutil
import signal
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

SHA = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
BACKUP = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-[0-9a-f]{8}\Z')
DEFAULT_BASE = Path('/opt/oasis-library')
SERVICE_USER = 'oasis-library'
WEB = 'oasis-library.service'
WORKER = 'oasis-library-index-worker.service'
STATE_FILES = ('catalogue.sqlite3', 'media', 'builds', 'indexing', 'catalogue-import')
REQUIRED_CHECKS = {'preview', 'device-runtime (3.10)', 'device-runtime (3.12)'}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def safe_relative(name):
    path = PurePosixPath(name)
    return bool(name and not path.is_absolute() and '..' not in path.parts
                and '.' not in path.parts and '\\' not in name and str(path) == name)


def inspect_bundle(path, expected_digest=None, expected_sha=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError('Use a regular release bundle smaller than 512 MiB.')
    if expected_digest is not None and (not DIGEST.fullmatch(expected_digest) or digest(path) != expected_digest):
        raise ValueError('Release bundle checksum mismatch.')
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        names = [member.name.rstrip('/') for member in members]
        if len(names) != len(set(names)) or len(names) > 50000:
            raise ValueError('Release archive contains duplicate or excessive members.')
        if any(not safe_relative(name) for name in names):
            raise ValueError('Release archive contains an unsafe path.')
        if any(not member.isfile() and not member.isdir() for member in members):
            raise ValueError('Release archive contains a link or special file.')
        manifest_member = archive.getmember('manifest.json')
        if manifest_member.size > 2 * 1024 * 1024:
            raise ValueError('Release manifest is too large.')
        manifest = json.load(archive.extractfile(manifest_member))
        if manifest.get('format') != 1 or not SHA.fullmatch(manifest.get('sha', '')):
            raise ValueError('Release manifest has an invalid format or SHA.')
        if expected_sha and manifest['sha'] != expected_sha:
            raise ValueError('Release SHA does not match the requested commit.')
        if manifest.get('repository') != 'shoshin-labs/kuwala-dlms':
            raise ValueError('Release belongs to another repository.')
        receipt = manifest.get('ci', {})
        checks = receipt.get('checks', {})
        if receipt.get('sha') != manifest['sha'] or set(checks) != REQUIRED_CHECKS or any(
                item.get('status') != 'completed' or item.get('conclusion') != 'success'
                or item.get('head_sha') != manifest['sha'] or item.get('app') != 'github-actions'
                for item in checks.values()):
            raise ValueError('Bundle lacks successful applicable CI build receipts for its exact commit.')
        files = manifest.get('files')
        if not isinstance(files, dict) or not files:
            raise ValueError('Release manifest has no file hashes.')
        actual_files = {member.name for member in members if member.isfile()} - {'manifest.json'}
        if actual_files != set(files):
            raise ValueError('Release archive has missing or unlisted files.')
        if sum(member.size for member in members) > 1024 * 1024 * 1024:
            raise ValueError('Expanded release is too large.')
        for name, expected in files.items():
            if not name.startswith(('app/', 'wheels/')) or not DIGEST.fullmatch(expected):
                raise ValueError('Invalid release file hash or location.')
            if any(part in {'.preview', '.git', 'node_modules', '.env'} for part in PurePosixPath(name).parts):
                raise ValueError('A release must not contain private state, credentials or node_modules.')
            result = hashlib.sha256()
            with archive.extractfile(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    result.update(block)
            if result.hexdigest() != expected:
                raise ValueError('Release file checksum mismatch: ' + name)
        required = {'app/manage.py', 'app/dlms/device_settings.py', 'app/deploy/target_release.py',
                    'app/requirements-device.lock.txt', 'app/frontend/static/index.html', 'app/release.json'}
        if not required <= set(files):
            raise ValueError('Release is missing device code, locked requirements or frontend assets.')
        if files['app/requirements-device.lock.txt'] != manifest.get('requirements_sha256'):
            raise ValueError('Release requirements hash is inconsistent.')
        if json.load(archive.extractfile('app/release.json')) != {'sha': manifest['sha']}:
            raise ValueError('Application release marker does not match its bundle.')
        html = archive.extractfile('app/frontend/static/index.html').read().decode('utf-8')
        validate_html_assets(html, files)
    return manifest


class AssetParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == 'script' and attributes.get('src'):
            self.paths.append(attributes['src'])
        elif tag == 'link' and attributes.get('rel') in {'stylesheet', 'icon'}:
            self.paths.append(attributes.get('href', ''))


def validate_html_assets(html, files):
    parser = AssetParser()
    parser.feed(html)
    if not any(name.endswith('.js') for name in parser.paths):
        raise ValueError('Frontend HTML has no local JavaScript bundle.')
    for asset in parser.paths:
        if not asset.startswith('/static/') or not safe_relative(asset[8:]):
            raise ValueError('Frontend runtime assets must use local /static/ URLs.')
        if 'app/frontend/static/' + asset[8:] not in files:
            raise ValueError('Frontend HTML references an absent local asset.')
    return parser.paths


def requirements(path):
    pins = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line)
        if not match:
            raise ValueError('Device requirements must consist of exact package==version pins.')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in pins:
            raise ValueError('Duplicate device requirement.')
        pins[name] = match[2]
    if not pins:
        raise ValueError('Device requirements are empty.')
    return pins


def validate_wheels(root, lock, target_python):
    pins, found = requirements(lock), {}
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Wheelhouse must be a regular directory.')
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != '.whl':
            raise ValueError('Wheelhouse must contain regular wheel files only.')
        tags = path.stem.rsplit('-', 3)
        if len(tags) != 4 or not (tags[-1] == 'any' or 'aarch64' in tags[-1]):
            raise ValueError('Wheelhouse contains a wheel for another architecture.')
        if tags[-1] != 'any' and tags[-2] != 'abi3' and 'cp' + target_python.replace('.', '') not in tags[-3].split('.'):
            raise ValueError('Native wheel Python tag does not match the requested device runtime.')
        with zipfile.ZipFile(path) as wheel:
            metadata = [item for item in wheel.infolist() if item.filename.endswith('.dist-info/METADATA')]
            if len(metadata) != 1 or metadata[0].file_size > 1024 * 1024:
                raise ValueError('Wheel metadata is missing or oversized.')
            info = email.message_from_bytes(wheel.read(metadata[0]))
            name = re.sub(r'[-_.]+', '-', info.get('Name', '')).lower()
            if name not in pins or info.get('Version') != pins[name] or name in found:
                raise ValueError('Wheelhouse must cover each exact locked package once, without extras.')
            found[name] = info['Version']
    if found != pins:
        raise ValueError('Wheelhouse does not contain every exact locked dependency.')


def tree_hashes(root):
    root = Path(root)
    hashes = {}
    if root.is_symlink() or root.exists() and not root.is_dir():
        raise ValueError('Private state/release root must be a regular directory.')
    if not root.exists():
        return hashes
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file() and not path.is_dir():
            raise ValueError('Private state/release contains a link or special file.')
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = digest(path)
    return hashes


def state_tree_hashes(root, prefix=''):
    """Hash private state without following the importer's one allowed pointer.

    Release assets continue to use strict tree_hashes. Only a job's direct
    draft/current relative link may select a regular v-* snapshot sibling.
    The receipt binds the link type, literal target and its digest, while the
    snapshot's original/index files are independently hashed in the same tree.
    """
    root = Path(root)
    if root.is_symlink() or root.exists() and not root.is_dir():
        raise ValueError('Private state root must be a regular directory.')
    hashes = {}
    if not root.exists():
        return hashes
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        scoped = PurePosixPath(prefix) / relative if prefix else PurePosixPath(relative)
        if path.is_symlink():
            parts = scoped.parts
            if (len(parts) != 5 or parts[:2] != ('indexing', 'jobs')
                    or parts[3:] != ('draft', 'current')
                    or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', parts[2])):
                raise ValueError('Private state permits only the importer draft/current pointer.')
            target = os.readlink(path)
            if not re.fullmatch(r'v-[A-Za-z0-9][A-Za-z0-9._-]{0,159}', target):
                raise ValueError('Private draft pointer must name a direct relative v-* snapshot sibling.')
            snapshot = path.parent / target
            if snapshot.is_symlink() or not snapshot.is_dir():
                raise ValueError('Private draft pointer must select a regular snapshot directory.')
            hashes[relative] = {'type': 'symlink', 'target': target,
                               'sha256': hashlib.sha256(b'relative-symlink\0' + target.encode('ascii')).hexdigest()}
        elif path.is_file():
            hashes[relative] = digest(path)
        elif not path.is_dir():
            raise ValueError('Private state contains a special file.')
    return hashes


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    with temporary.open('w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_link(path, target):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(temporary, path)


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).is_file() else default


def run_management(command, *, cwd, env, output, timeout=600):
    """Reap the complete runuser/Django process group before recovery."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        # A runuser parent may exit before its child. Terminate any remaining
        # members too; only management checks/migrations use this helper.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


def service_state(unit):
    result = subprocess.run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,UnitFileState,MainPID', '--no-pager'],
                            capture_output=True, text=True, timeout=10, check=True)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def stop_web():
    if service_state(WEB).get('LoadState') != 'not-found':
        subprocess.run(['systemctl', 'stop', WEB], check=True)


def station_fingerprint():
    result = {}
    for name, port in [('station', 3000), ('pdf_trial', 4176)]:
        with urllib.request.urlopen('http://127.0.0.1:' + str(port) + '/api/status', timeout=10) as response:
            status = json.load(response)
        library = status.get('pdf_library', {})
        documents = library.get('documents', [])
        provenance = ('filename', 'sha256', 'library_version', 'title', 'publisher', 'authors',
                      'source_url', 'licence', 'licence_url', 'rights_notes', 'reviewed_on',
                      'reviewer', 'page_count', 'passage_count', 'empty_pages')
        entries = sorted((item.get('document_id') or item['id'],
                          {key: item.get(key) for key in provenance}) for item in documents)
        groups = sorted((item['id'], item.get('label'), sorted(item.get('document_ids', [])))
                        for item in library.get('libraries', []))
        result[name] = {'release_sha': status.get('release_sha'), 'model': status.get('model'),
                        'library_version': entries[0][1]['library_version'] if entries else None, 'document_count': len(entries),
                        'originals_fingerprint': hashlib.sha256(json.dumps(entries).encode()).hexdigest(),
                        'libraries_fingerprint': hashlib.sha256(json.dumps(groups).encode()).hexdigest(),
                        'semantic': {key: library.get('semantic', {}).get(key)
                                     for key in ('enabled', 'available', 'model', 'error')},
                        'network': {key: status.get('network', {}).get(key)
                                    for key in ('enabled', 'allow_web_fallback')},
                        'privacy': status.get('privacy'), 'deployment_mode': status.get('deployment_mode')}
    return result


def running_jobs(data):
    database = Path(data) / 'catalogue.sqlite3'
    if not database.is_file():
        return 0
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_management_oasisindexjob'").fetchone()
        return connection.execute("SELECT COUNT(*) FROM content_management_oasisindexjob WHERE state='running'").fetchone()[0] if exists else 0


def require_idle_worker(data):
    if service_state(WORKER).get('ActiveState') in {'active', 'activating', 'deactivating'}:
        raise ValueError('The indexing worker must be stopped while idle before promotion/restore; do not kill an in-flight job.')
    heartbeat = read_json(Path(data) / 'indexing/worker.json', {})
    if heartbeat.get('active') and time.time() - heartbeat.get('last_seen', 0) < 20:
        raise ValueError('A manually started indexing worker is still active. Stop it while idle before deployment.')
    if running_jobs(data):
        raise ValueError('Running index jobs prevent deployment. Resolve/drain them through the existing worker first.')


def request_maintenance(data):
    root = Path(data) / 'indexing'
    sentinel = root / 'maintenance.json'
    if sentinel.is_symlink():
        raise ValueError('Worker maintenance sentinel must not be a symlink.')
    nonce = uuid.uuid4().hex
    atomic_json(sentinel, {'nonce': nonce, 'requested_on': time.time(), 'purpose': 'private curator deployment'})
    account = pwd.getpwnam(SERVICE_USER)
    os.chown(sentinel, account.pw_uid, account.pw_gid)
    return nonce


def pause_worker(data, timeout=30):
    """Ask the existing worker to stop claims; never signal an in-flight job."""
    root = Path(data) / 'indexing'
    nonce = request_maintenance(data)
    # An active command finishes under the existing worker; the operator can
    # retry when it has drained. Keep the sentinel until recovery/promotion.
    if running_jobs(data):
        raise ValueError('An index job is running. Maintenance is requested; let it finish, then retry. No job was terminated.')
    state = service_state(WORKER)
    heartbeat = read_json(root / 'worker.json', {})
    active = state.get('ActiveState') in {'active', 'activating', 'deactivating'} or (
        heartbeat.get('active') and time.time() - heartbeat.get('last_seen', 0) < 20)
    if active:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            heartbeat = read_json(root / 'worker.json', {})
            current_state = service_state(WORKER)
            if heartbeat.get('active') and heartbeat.get('maintenance') and heartbeat.get('maintenance_nonce') == nonce and time.time() - heartbeat.get('last_seen', 0) < 10 and not running_jobs(data):
                if current_state.get('ActiveState') != 'active':
                    raise ValueError('A manual worker is paused. Stop it cleanly before retrying; deployment will not signal it.')
                if str(heartbeat.get('pid')) != current_state.get('MainPID'):
                    raise ValueError('Worker acknowledgement belongs to a different process; deployment will not stop it.')
                subprocess.run(['systemctl', 'stop', WORKER], check=True)
                # Wait for the real final heartbeat, or let an old idle
                # heartbeat expire after supervisor SIGTERM. Never forge it.
                stopped_deadline = time.monotonic() + 25
                while True:
                    try:
                        require_idle_worker(data)
                        break
                    except ValueError:
                        if time.monotonic() >= stopped_deadline:
                            raise ValueError('The stopped worker still reports activity; no backup or migration was started.')
                        time.sleep(0.25)
                return
            time.sleep(0.25)
        raise ValueError('Worker did not acknowledge idle maintenance. It was not stopped; inspect it and retry.')
    require_idle_worker(data)


def clear_maintenance(data):
    sentinel = Path(data) / 'indexing/maintenance.json'
    if sentinel.is_symlink():
        raise ValueError('Worker maintenance sentinel must not be a symlink.')
    sentinel.unlink(missing_ok=True)


def backup_state(data, sha, previous, runtime, fingerprint):
    data = Path(data)
    backups = data / 'backups'
    if data.is_symlink() or backups.is_symlink() or not backups.is_dir() or backups.stat().st_uid != os.geteuid() or backups.stat().st_mode & 0o077:
        raise ValueError('Private backup root must be a private directory owned by the deployment operator.')
    size = sum(path.stat().st_size for name in STATE_FILES for path in
               ([data / name] if (data / name).is_file() else (data / name).rglob('*')) if path.is_file())
    if shutil.disk_usage(data).free < size + 64 * 1024 * 1024:
        raise ValueError('Insufficient free space for a complete private state backup; nothing was migrated.')
    identifier = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + sha[:12] + '-' + uuid.uuid4().hex[:8]
    destination = data / 'backups' / identifier
    destination.mkdir(parents=True, mode=0o700)
    snapshot = destination / 'snapshot'
    snapshot.mkdir(mode=0o700)
    try:
        for name in STATE_FILES:
            source = data / name
            if source.is_symlink():
                raise ValueError('Private state must not contain symlinks.')
            if not source.exists():
                continue
            if source.is_dir():
                state_tree_hashes(source, prefix=name)
                shutil.copytree(source, snapshot / name, symlinks=True)
            elif name == 'catalogue.sqlite3':
                with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as original:
                    with closing(sqlite3.connect(snapshot / name)) as copied:
                        original.backup(copied)
                        if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise ValueError('Catalogue backup failed SQLite integrity verification.')
            else:
                raise ValueError('Unexpected persistent state file.')
        record = {'format': 1, 'sha': sha, 'previous': previous, 'previous_runtime': runtime,
                  'station': fingerprint, 'files': state_tree_hashes(snapshot), 'created_on': time.time()}
        atomic_json(destination / 'backup.json', record)
        return identifier
    except BaseException:
        shutil.rmtree(destination)
        raise


def verify_backup(data, identifier, sha):
    if not BACKUP.fullmatch(identifier):
        raise ValueError('Use a backup identifier printed by this deployment transaction.')
    root = Path(data) / 'backups'
    if Path(data).is_symlink() or root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
        raise ValueError('Private backup root must be a private directory owned by the deployment operator.')
    backup = root / identifier
    if backup.is_symlink() or not backup.is_dir():
        raise ValueError('Matching private state backup is absent.')
    record = read_json(backup / 'backup.json', {})
    if (backup / 'snapshot').is_symlink() or not (backup / 'snapshot').is_dir():
        raise ValueError('Private backup snapshot must be a regular directory.')
    if record.get('format') != 1 or record.get('sha') != sha or state_tree_hashes(backup / 'snapshot') != record.get('files'):
        raise ValueError('Backup does not match this release, or its state files are corrupt.')
    return backup, record


def restore_state(data, backup):
    data, snapshot = Path(data), Path(backup) / 'snapshot'
    if data.is_symlink() or Path(backup).is_symlink():
        raise ValueError('Private restore roots must not be symlinks.')
    if not snapshot.is_dir() or state_tree_hashes(snapshot) != read_json(Path(backup) / 'backup.json', {}).get('files'):
        raise ValueError('Private backup state changed before restore.')
    # Services are stopped throughout. Each replacement is atomic; a power
    # failure leaves the transaction marked restoring and can be retried from
    # the same verified, unchanged backup.
    for name in STATE_FILES:
        destination, source = data / name, snapshot / name
        temporary = data / ('.restore-' + name + '-' + uuid.uuid4().hex)
        if source.is_dir():
            shutil.copytree(source, temporary, symlinks=True)
        elif source.is_file():
            shutil.copy2(source, temporary)
        if destination.is_symlink():
            raise ValueError('Refusing to restore through a symlink.')
        if destination.is_dir():
            old = data / ('.old-' + name + '-' + uuid.uuid4().hex)
            os.replace(destination, old)
            if temporary.exists():
                os.replace(temporary, destination)
            shutil.rmtree(old)
        elif temporary.exists():
            os.replace(temporary, destination)
        else:
            destination.unlink(missing_ok=True)
    for suffix in ('-wal', '-shm', '-journal'):
        (data / ('catalogue.sqlite3' + suffix)).unlink(missing_ok=True)


class Target:
    def __init__(self, base):
        self.base = Path(base).absolute()
        self.data = self.base / 'data'
        self.releases = self.base / 'releases'
        self.state_file = self.base / 'release-state.json'

    def operator_environment(self):
        path = self.base / 'env'
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != 0:
            raise ValueError('Prepare the private root-owned mode0600 device env file using the runbook.')
        values = {}
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise ValueError('Device env must use literal KEY=value entries.')
            key, raw = line.split('=', 1)
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
                raise ValueError('Invalid device env key.')
            parsed = shlex.split(raw, comments=False)
            if len(parsed) > 1:
                raise ValueError('Quote env values containing spaces.')
            values[key] = parsed[0] if parsed else ''
        if values.get('OASIS_DEVICE_DATA_ROOT') != str(self.data):
            raise ValueError('OASIS_DEVICE_DATA_ROOT must point to persistent /opt/oasis-library/data.')
        if values.get('DJANGO_SETTINGS_MODULE', 'dlms.device_settings') != 'dlms.device_settings':
            raise ValueError('Device deployments must use dlms.device_settings.')
        for name in ('OASIS_DEVICE_SECRET_KEY_FILE', 'OASIS_INDEXING_STATION_ROOT',
                     'OASIS_INDEXING_PYTHON', 'OASIS_INDEXING_MANIFEST', 'OASIS_INDEXING_DEPENDENCY_PATH'):
            if values.get(name):
                supplied = Path(values[name])
                resolved = supplied.resolve()
                if any(path.is_relative_to(Path(root)) for path in (supplied, resolved)
                       for root in ('/home', '/root', '/run/user')):
                    raise ValueError('Configured ' + name + ' is hidden by the service ProtectHome sandbox; use a reviewed /opt path.')
        environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
                       'DJANGO_SETTINGS_MODULE': 'dlms.device_settings'}
        environment.update(values)
        return environment

    def prepare_directories(self):
        if any(path.is_symlink() for path in [self.base, *self.base.parents, self.data, self.releases]):
            raise ValueError('Deployment roots must be regular directories, not symlinks.')
        account = pwd.getpwnam(SERVICE_USER)
        self.base.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.base.chmod(0o755)
        self.releases.mkdir(parents=True, exist_ok=True, mode=0o755)
        self.releases.chmod(0o755)
        self.data.mkdir(exist_ok=True, mode=0o700)
        self.data.chmod(0o700)
        os.chown(self.data, account.pw_uid, account.pw_gid)
        for name in ('media', 'media/contents', 'builds', 'indexing', 'logs'):
            path = self.data / name
            if path.is_symlink():
                raise ValueError('Persistent state directories must not be symlinks.')
            path.mkdir(parents=True, exist_ok=True, mode=0o750)
            os.chown(path, account.pw_uid, account.pw_gid)
        backups = self.data / 'backups'
        if backups.is_symlink() or backups.exists() and not backups.is_dir():
            raise ValueError('Private backup root must be a regular directory.')
        backups.mkdir(exist_ok=True, mode=0o700)
        backups.chmod(0o700)
        os.chown(backups, 0, 0)

    def verify_runtime(self, runtime, lock):
        script = ('import importlib.metadata,json,platform,sys; '
                  'print(json.dumps({"python":list(sys.version_info[:2]),"machine":platform.machine(),'
                  '"versions":{name:importlib.metadata.version(name) for name in ' + repr(list(requirements(lock))) + '}}))')
        result = subprocess.run([str(Path(runtime) / 'bin/python'), '-B', '-c', script],
                                capture_output=True, text=True, timeout=30, check=True)
        info = json.loads(result.stdout)
        if info['machine'] != 'aarch64' or info['python'][0] != 3 or info['python'][1] < 10:
            raise ValueError('Use a supported existing ARM64 Python>=3.10; do not copy a workstation venv.')
        if info['versions'] != requirements(lock):
            raise ValueError('Prepared device venv package versions differ from the exact device lock.')
        subprocess.run([str(Path(runtime) / 'bin/python'), '-m', 'pip', 'check'], check=True,
                       capture_output=True, text=True, timeout=30)
        return info

    def prepare_runtime(self, release, manifest, python):
        metadata = manifest.get('runtime')
        if not metadata or metadata.get('machine') != 'aarch64':
            raise ValueError('Runtime preparation needs a verified ARM64 wheelhouse included in the bundle.')
        info = json.loads(subprocess.run([python, '-c', 'import json,platform,sys;print(json.dumps([platform.machine(),"%d.%d"%sys.version_info[:2]]))'],
                                        capture_output=True, text=True, check=True).stdout)
        if info != ['aarch64', metadata['python']]:
            raise ValueError('Existing target Python does not match this wheelhouse. No system Python upgrade is performed.')
        wheels, lock = release / 'wheels', release / 'app/requirements-device.lock.txt'
        validate_wheels(wheels, lock, metadata['python'])
        destination = self.base / 'runtimes' / (manifest['requirements_sha256'][:16] + '-py' + metadata['python'] + '-aarch64')
        if destination.parent.is_symlink() or destination.is_symlink():
            raise ValueError('Versioned runtime paths must not be symlinks.')
        if destination.exists():
            self.verify_runtime(destination, lock)
            return destination
        destination.parent.mkdir(exist_ok=True, mode=0o755)
        destination.parent.chmod(0o755)
        try:
            subprocess.run([python, '-m', 'venv', str(destination)], check=True, capture_output=True, umask=0o022)
            subprocess.run([str(destination / 'bin/python'), '-m', 'pip', 'install', '--no-index', '--no-deps',
                            '--disable-pip-version-check', '--no-cache-dir', '--find-links', str(wheels), '-r', str(lock)],
                           check=True, capture_output=True, timeout=600, umask=0o022)
            self.verify_runtime(destination, lock)
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return destination

    def manage(self, release, runtime, arguments):
        env = self.operator_environment()
        log = self.data / 'logs' / ('deploy-' + release.name + '.log')
        with log.open('ab') as output:
            # Ubuntu keeps this privileged tool outside the restricted app PATH.
            result = run_management(['/usr/sbin/runuser', '-u', SERVICE_USER, '--', str(runtime / 'bin/python'), '-B',
                                     str(release / 'app/manage.py'), *arguments], cwd=release / 'app', env=env,
                                    output=output)
        if result:
            raise ValueError('Django management check failed; inspect the private deployment log at ' + str(log))

    def worker_preflight(self, release, runtime):
        # Invoke only the existing validator under the actual service account.
        # It reads the manifest/runtime and local model availability; it never
        # creates a job, extracts PDFs, embeds text or downloads a model.
        code = ('from content_management.oasis_indexing import operator_config, configuration_probe; '
                'result = configuration_probe(operator_config()); '
                'assert result.get("lexical_available") is True, "Existing lexical maintenance runtime unavailable"; '
                'print("Reviewed manifest and lexical maintenance runtime verified; vector availability:", '
                'bool(result.get("vector_available")))')
        self.manage(release, runtime, ['shell', '-c', code])

    def verify_release(self, release):
        manifest = read_json(release / 'manifest.json', {})
        if release.is_symlink() or not SHA.fullmatch(release.name) or manifest.get('sha') != release.name:
            raise ValueError('Staged release identity is invalid.')
        for name, expected in manifest.get('files', {}).items():
            path = release / name
            if path.is_symlink() or not path.is_file() or digest(path) != expected:
                raise ValueError('Staged release contains a missing or changed file.')
        stage = read_json(release / 'staged.json', {})
        if stage.get('sha') != release.name or tree_hashes(release / 'app/collected-static') != stage.get('static_files'):
            raise ValueError('Staged collected static assets are missing or changed.')
        expected = set(manifest.get('files', {})) | {'manifest.json', 'staged.json'}
        expected |= {'app/collected-static/' + name for name in stage['static_files']}
        if set(tree_hashes(release)) != expected:
            raise ValueError('Staged release contains unlisted files.')
        self.verify_runtime(Path(stage['runtime']), release / 'app/requirements-device.lock.txt')
        return manifest, stage

    def stage(self, sha, bundle, checksum, prepare_runtime=False, python='/usr/bin/python3'):
        manifest = inspect_bundle(bundle, checksum, sha)
        self.operator_environment()
        self.prepare_directories()
        release = self.releases / sha
        if release.exists():
            existing, stage = self.verify_release(release)
            if existing['files'] != manifest['files']:
                raise ValueError('This SHA was already staged with different bundle bytes.')
            stage['station'] = station_fingerprint()
            atomic_json(release / 'staged.json', stage)
            print(json.dumps({'phase': 'staged', 'sha': sha, 'already_staged': True}))
            return
        temporary = Path(tempfile.mkdtemp(prefix='.' + sha + '-', dir=self.releases))
        try:
            with tarfile.open(bundle, 'r:gz') as archive:
                archive.extractall(temporary)
            temporary.chmod(0o755)
            for path in temporary.rglob('*'):
                if path.is_dir():
                    path.chmod(0o755)
                elif path.is_file():
                    path.chmod(0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644)
            os.replace(temporary, release)
            runtime = self.prepare_runtime(release, manifest, python) if prepare_runtime else self.base / 'venv'
            self.verify_runtime(runtime, release / 'app/requirements-device.lock.txt')
            static_root = release / 'app/collected-static'
            static_root.mkdir(mode=0o755)
            account = pwd.getpwnam(SERVICE_USER)
            os.chown(static_root, account.pw_uid, account.pw_gid)
            self.manage(release, runtime, ['check'])
            self.manage(release, runtime, ['collectstatic', '--noinput', '--clear'])
            static_files = tree_hashes(static_root)
            for path in [static_root, *static_root.rglob('*')]:
                os.chown(path, 0, 0)
                path.chmod(0o755 if path.is_dir() else 0o644)
            atomic_json(release / 'staged.json', {'sha': sha, 'runtime': str(runtime.resolve()),
                        'static_files': static_files, 'station': station_fingerprint()})
            self.verify_release(release)
            print(json.dumps({'phase': 'staged', 'sha': sha, 'station': station_fingerprint()}))
        except BaseException:
            if release.exists() and not (self.base / 'current').exists():
                shutil.rmtree(release)
            elif release.exists() and (self.base / 'current').resolve() != release:
                shutil.rmtree(release)
            if temporary.exists():
                shutil.rmtree(temporary)
            raise

    def select_runtime(self, target):
        link = self.base / 'venv'
        if link.exists() and not link.is_symlink():
            if link.resolve() != target.resolve():
                raise ValueError('Existing venv is not a symlink; preserve it as a versioned runtime before changing it.')
            return
        atomic_link(link, target)

    def install_units(self, release):
        for unit in (WEB, WORKER):
            shutil.copy2(release / 'app/deploy' / unit, Path('/etc/systemd/system') / unit)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)

    def readiness(self, release, fingerprint):
        deadline = time.monotonic() + 45
        last = None
        while time.monotonic() < deadline:
            try:
                if service_state(WEB).get('ActiveState') != 'active':
                    raise ValueError('Curator service is not active.')
                authenticated_runtime = (release / 'app/dlms/curator_auth.py').is_file()
                endpoint = '/healthz' if authenticated_runtime else '/api/oasis/config/'
                with urllib.request.urlopen('http://127.0.0.1:8790' + endpoint, timeout=5) as response:
                    config = json.load(response)
                data = config.get('data', config)
                if authenticated_runtime:
                    if data != {'ready': True, 'authentication_required': True} or config.get('success') is not True:
                        raise ValueError('The private device endpoint does not report authenticated curator readiness.')
                elif not data.get('curator_enabled') or data.get('synthetic_fixtures') or config.get('success') is False:
                    raise ValueError('The earlier private device runtime is not ready for rollback.')
                process = service_state(WEB).get('MainPID', '')
                if not process.isdigit() or not Path('/proc/' + process + '/cwd').exists() or Path('/proc/' + process + '/cwd').resolve() != release / 'app':
                    raise ValueError('The running curator process does not use this exact staged release.')
                html = (release / 'app/frontend/static/index.html').read_text()
                manifest = read_json(release / 'manifest.json')
                for asset in validate_html_assets(html, manifest['files']):
                    with urllib.request.urlopen('http://127.0.0.1:8790' + asset, timeout=5) as response:
                        result = response.read(64 * 1024 * 1024)
                    if hashlib.sha256(result).hexdigest() != manifest['files']['app/frontend/static/' + asset[8:]]:
                        raise ValueError('Served frontend asset differs from the staged release.')
                if station_fingerprint() != fingerprint:
                    raise ValueError('Station code/model/published PDF fingerprint changed during private curator promotion.')
                return
            except (OSError, ValueError) as exc:
                last = exc
                time.sleep(1)
        raise ValueError('Curator readiness failed: ' + str(last))

    def promote(self, sha, worker='preserve'):
        release = self.releases / sha
        _, stage = self.verify_release(release)
        old = read_json(self.state_file, {})
        if old.get('phase') in {'migrating', 'promoting', 'failed', 'restoring'}:
            raise ValueError('An incomplete transaction requires explicit matching backup restore before another promotion.')
        current = self.base / 'current'
        if current.exists() and not current.is_symlink():
            raise ValueError('Current must be a versioned release symlink.')
        previous = None
        if current.is_symlink():
            prior_release = current.resolve(strict=True)
            if prior_release.parent != self.releases or not SHA.fullmatch(prior_release.name):
                raise ValueError('Current must point to a verified managed release.')
            _, prior_stage = self.verify_release(prior_release)
            if not (self.base / 'venv').exists() or (self.base / 'venv').resolve(strict=True) != Path(prior_stage['runtime']).resolve(strict=True):
                raise ValueError('Current runtime does not match the verified previous release.')
            previous = str(prior_release)
        previous_runtime = str((self.base / 'venv').resolve()) if (self.base / 'venv').exists() else None
        fingerprint = station_fingerprint()
        if fingerprint != stage.get('station'):
            raise ValueError('Station/published collection changed since staging; inspect and re-stage before promotion.')
        previous_worker = service_state(WORKER).get('UnitFileState') == 'enabled'
        enable_worker = previous_worker if worker == 'preserve' else worker == 'on'
        if enable_worker:
            self.worker_preflight(release, Path(stage['runtime']))
        pause_worker(self.data)
        stop_web()
        require_idle_worker(self.data)
        backup = backup_state(self.data, sha, previous, previous_runtime, fingerprint)
        state = {'sha': sha, 'phase': 'migrating', 'previous': previous, 'backup': backup,
                 'previous_runtime': previous_runtime, 'worker_enabled': previous_worker, 'station': fingerprint}
        atomic_json(self.state_file, state)
        try:
            self.manage(release, Path(stage['runtime']), ['migrate', '--noinput'])
            state['phase'] = 'promoting'
            atomic_json(self.state_file, state)
            self.select_runtime(Path(stage['runtime']))
            atomic_link(current, release)
            self.install_units(release)
            subprocess.run(['systemctl', 'enable', '--now', WEB], check=True)
            self.readiness(release, fingerprint)
            clear_maintenance(self.data)
            if enable_worker:
                subprocess.run(['systemctl', 'enable', '--now', WORKER], check=True)
            else:
                subprocess.run(['systemctl', 'disable', WORKER], check=True)
            state['phase'] = 'active'
            atomic_json(self.state_file, state)
            print(json.dumps({'phase': 'active', 'sha': sha, 'backup': backup, 'worker_enabled': enable_worker,
                              'station': fingerprint, 'initial_catalogue': 'blank unless explicit operator data was previously installed'}))
        except BaseException:
            try:
                stop_web()
            except Exception as stop_error:
                state['curator_stop_error'] = str(stop_error)
            try:
                request_maintenance(self.data)
            except Exception as pause_error:
                state['maintenance_error'] = str(pause_error)
            # No automatic code-only rollback: migrations and media must stay
            # paired. Do not stop a worker that may have started a real job.
            state['phase'] = 'failed'
            atomic_json(self.state_file, state)
            print(json.dumps({'phase': 'failed', 'sha': sha, 'backup': backup,
                              'recovery': 'explicit rollback --restore-state required'}), file=__import__('sys').stderr)
            raise

    def rollback(self, sha, identifier, restore=False):
        if not restore:
            raise ValueError('Rollback requires explicit --restore-state; edits after the backup will be replaced.')
        state = read_json(self.state_file, {})
        if state.get('sha') != sha or state.get('backup') != identifier:
            raise ValueError('Rollback must use the matching transaction SHA and backup.')
        backup, record = verify_backup(self.data, identifier, sha)
        previous = record.get('previous')
        if previous:
            previous = Path(previous)
            if previous.parent != self.releases or not SHA.fullmatch(previous.name):
                raise ValueError('Previous code release escapes the managed release directory.')
            self.verify_release(previous)
        pause_worker(self.data)
        stop_web()
        fingerprint = station_fingerprint()
        current = self.base / 'current'
        rescue = backup_state(self.data, sha, str(current.resolve()) if current.exists() else None,
                              str((self.base / 'venv').resolve()), fingerprint)
        state.update(phase='restoring', rescue_backup=rescue)
        atomic_json(self.state_file, state)
        try:
            restore_state(self.data, backup)
            # Restoring the snapshot may restore an older maintenance request.
            # Install a new request before a service can restart/claim work.
            pause_worker(self.data)
            account = pwd.getpwnam(SERVICE_USER)
            for name in STATE_FILES:
                root = self.data / name
                if root.exists():
                    for path in [root, *(root.rglob('*') if root.is_dir() else [])]:
                        os.chown(path, account.pw_uid, account.pw_gid)
            if previous:
                self.select_runtime(Path(record['previous_runtime']))
                atomic_link(self.base / 'current', previous)
                self.install_units(previous)
                subprocess.run(['systemctl', 'start', WEB], check=True)
                self.readiness(previous, fingerprint)
                if state.get('worker_enabled'):
                    self.worker_preflight(previous, Path(record['previous_runtime']))
                clear_maintenance(self.data)
                if state.get('worker_enabled'):
                    subprocess.run(['systemctl', 'enable', '--now', WORKER], check=True)
                else:
                    subprocess.run(['systemctl', 'disable', WORKER], check=True)
            else:
                (self.base / 'current').unlink(missing_ok=True)
                subprocess.run(['systemctl', 'disable', WEB, WORKER], check=True)
                clear_maintenance(self.data)
        except BaseException:
            try:
                stop_web()
            except Exception as stop_error:
                state['curator_stop_error'] = str(stop_error)
            try:
                request_maintenance(self.data)
            except Exception as pause_error:
                state['maintenance_error'] = str(pause_error)
            state['phase'] = 'restoring'
            atomic_json(self.state_file, state)
            raise
        state['phase'] = 'rolled_back'
        state['station'] = fingerprint
        atomic_json(self.state_file, state)
        print(json.dumps({'phase': 'rolled_back', 'sha': sha, 'rescue_backup': rescue,
                          'previous': str(previous) if previous else None}))

    def check(self):
        current = self.base / 'current'
        result = {'base': str(self.base), 'current': str(current.resolve()) if current.exists() else None,
                  'transaction': read_json(self.state_file, {}), 'curator': service_state(WEB),
                  'worker': service_state(WORKER), 'running_jobs': running_jobs(self.data),
                  'station': station_fingerprint(), 'bind': '127.0.0.1:8790', 'remote_management': False}
        print(json.dumps(result, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='check', choices=('check', 'stage', 'promote', 'rollback'))
    parser.add_argument('--base', type=Path, default=DEFAULT_BASE)
    parser.add_argument('--sha')
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--digest')
    parser.add_argument('--prepare-runtime', action='store_true')
    parser.add_argument('--python', default='/usr/bin/python3')
    parser.add_argument('--worker', choices=('preserve', 'on', 'off'), default='preserve')
    parser.add_argument('--backup')
    parser.add_argument('--restore-state', action='store_true')
    args = parser.parse_args()
    try:
        target = Target(args.base)
        if args.command == 'check':
            target.check()
            return
        if args.base != DEFAULT_BASE:
            raise ValueError('Mutating operations support only /opt/oasis-library; station and arbitrary roots are forbidden.')
        if os.geteuid() != 0 or not SHA.fullmatch(args.sha or ''):
            raise ValueError('Mutating target operations require sudo and a full release SHA.')
        os.umask(0o077)
        if args.command == 'stage':
            if not args.bundle or not args.digest:
                raise ValueError('Stage requires the bundle and its independently supplied checksum.')
            target.stage(args.sha, args.bundle, args.digest, args.prepare_runtime, args.python)
        elif args.command == 'promote':
            target.promote(args.sha, args.worker)
        else:
            if not args.backup:
                raise ValueError('Rollback requires a matching backup identifier.')
            target.rollback(args.sha, args.backup, args.restore_state)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError, sqlite3.Error) as exc:
        parser.exit(1, 'Target operation stopped: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
