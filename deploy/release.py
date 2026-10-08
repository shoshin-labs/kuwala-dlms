#!/usr/bin/env python3
"""Build and explicitly deploy the private Oasis curator; never publish station data."""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from deploy.target_release import inspect_bundle, validate_wheels, REQUIRED_CHECKS  # noqa: E402

REPOSITORY = 'shoshin-labs/kuwala-dlms'
SHA = re.compile(r'[0-9a-f]{40}\Z')
HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@:-]*\Z')


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, **kwargs)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def merged_commit(value):
    sha = run(['git', 'rev-parse', '--verify', value + '^{commit}'], cwd=ROOT,
              capture_output=True).stdout.strip()
    if not SHA.fullmatch(sha):
        raise ValueError('Use a full Git commit SHA.')
    run(['git', 'merge-base', '--is-ancestor', sha, 'origin/master'], cwd=ROOT,
        capture_output=True)
    return sha


def require_ci(sha):
    response = json.loads(run(['gh', 'api', 'repos/' + REPOSITORY + '/commits/' + sha
                              + '/check-runs?filter=all&per_page=100'],
                             capture_output=True).stdout)
    checks = response.get('check_runs', [])
    if response.get('total_count', 0) > len(checks):
        raise ValueError('Too many checks to determine the latest exact-commit CI result.')
    latest = {}
    for item in checks:
        name = item.get('name')
        if name in REQUIRED_CHECKS and item.get('app', {}).get('slug') == 'github-actions':
            if name not in latest or item['id'] > latest[name]['id']:
                latest[name] = item
    if set(latest) != REQUIRED_CHECKS or any(item.get('status') != 'completed'
            or item.get('conclusion') != 'success' or item.get('head_sha') != sha for item in latest.values()):
        raise ValueError('All latest applicable GitHub Actions checks must succeed on this exact merged SHA: '
                         + ', '.join(sorted(REQUIRED_CHECKS)))
    return {'sha': sha, 'checks': {name: {key: item.get(key) for key in
            ('id', 'status', 'conclusion', 'head_sha')} | {'app': 'github-actions'}
            for name, item in latest.items()}}


def archive_source(sha, destination):
    with tempfile.TemporaryFile() as stream:
        run(['git', 'archive', sha], cwd=ROOT, stdout=stream)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            # git archive contains only the chosen tracked tree. Reject tracked
            # symlinks too: deployment has no need for them.
            for member in archive.getmembers():
                parts = Path(member.name).parts
                if member.issym() or member.islnk() or member.name.startswith('/') or '..' in parts:
                    raise ValueError('Release source has an unsafe archive member.')
                if not member.isdir() and not member.isfile():
                    raise ValueError('Release source must contain regular files and directories.')
            archive.extractall(destination)


def source_hashes(root):
    return {path.relative_to(root).as_posix(): digest(path)
            for path in sorted(root.rglob('*')) if path.is_file()}


def build(sha, output, wheelhouse=None, target_python=None, offline_npm=False, ci=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ('oasis-library-' + sha + '.tar.gz')
    if destination.exists():
        raise ValueError('A bundle already exists for this SHA; inspect it or choose another output directory.')
    with tempfile.TemporaryDirectory(prefix='oasis-device-build-') as workspace:
        workspace = Path(workspace)
        app = workspace / 'app'
        app.mkdir()
        archive_source(sha, app)
        originals = source_hashes(app)
        required = ['requirements-device.lock.txt', 'dlms/device_settings.py',
                    'deploy/target_release.py', 'deploy/oasis-library.service',
                    'deploy/oasis-library-index-worker.service']
        if any(not (app / name).is_file() for name in required):
            raise ValueError('The merged commit does not include the complete device deployment implementation.')
        npm = ['npm', 'ci', '--ignore-scripts'] + (['--offline'] if offline_npm else [])
        run(npm, cwd=app / 'frontend')
        run(['npm', 'run', 'build-prod'], cwd=app / 'frontend')
        shutil.rmtree(app / 'frontend/node_modules')
        for name, expected in originals.items():
            if not (app / name).is_file() or digest(app / name) != expected:
                raise ValueError('The source build changed a tracked release input: ' + name)
        (app / 'release.json').write_text(json.dumps({'sha': sha}) + '\n')
        runtime = None
        if wheelhouse:
            if not target_python or not re.fullmatch(r'3\.(?:1[0-9])', target_python):
                raise ValueError('A wheelhouse needs an explicit target Python, for example --target-python 3.12.')
            source = Path(wheelhouse).resolve()
            validate_wheels(source, app / 'requirements-device.lock.txt', target_python)
            shutil.copytree(source, workspace / 'wheels')
            runtime = {'machine': 'aarch64', 'python': target_python}
        files = {path.relative_to(workspace).as_posix(): digest(path)
                 for path in sorted(workspace.rglob('*')) if path.is_file()}
        manifest = {'format': 1, 'sha': sha, 'repository': REPOSITORY,
                    'requirements_sha256': digest(app / 'requirements-device.lock.txt'),
                    'source_files': originals, 'files': files, 'runtime': runtime, 'ci': ci}
        (workspace / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
        temporary = destination.with_suffix('.tmp')
        try:
            with tarfile.open(temporary, 'w:gz') as archive:
                archive.add(workspace / 'manifest.json', arcname='manifest.json')
                archive.add(app, arcname='app')
                if runtime:
                    archive.add(workspace / 'wheels', arcname='wheels')
            inspect_bundle(temporary, digest(temporary), sha)
            os.replace(temporary, destination)
            destination.with_suffix(destination.suffix + '.sha256').write_text(
                digest(destination) + '  ' + destination.name + '\n')
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def verify_source(manifest):
    with tempfile.TemporaryDirectory(prefix='oasis-device-source-') as workspace:
        archive_source(manifest['sha'], Path(workspace))
        if source_hashes(Path(workspace)) != manifest.get('source_files'):
            raise ValueError('Bundle source does not match the exact merged Git tree.')
    for name, expected in manifest['source_files'].items():
        if manifest['files'].get('app/' + name) != expected:
            raise ValueError('A bundled source file differs from its merged Git tree.')


def ssh(host, argv, *, input_text=None, tty=False):
    if not HOST.fullmatch(host):
        raise ValueError('Use an existing SSH user@hostname; SSH options are not accepted as a host.')
    command = ['ssh', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10']
    command += ['-tt'] if tty else ['-o', 'BatchMode=yes']
    return run(command + [host, shlex.join(argv)], input=input_text)


def check_remote(host):
    # Supply the read-only checker through stdin, without uploading a file or
    # creating a remote staging directory. It does not load Django settings.
    source = (ROOT / 'deploy/target_release.py').read_text()
    ssh(host, ['python3', '-', 'check'], input_text=source)


def deploy(args):
    if args.mode == 'rollback':
        if not args.restore_state or not args.backup or not SHA.fullmatch(args.sha or ''):
            raise ValueError('Rollback requires --sha, --backup and explicit --restore-state. Read the data-loss warning.')
        # A rollback uses the target's already staged, verified runner; no new
        # application or runtime is transferred.
        runner = '/opt/oasis-library/releases/' + args.sha + '/app/deploy/target_release.py'
        ssh(args.jetson, ['sudo', 'python3', runner, 'rollback', '--sha', args.sha,
                         '--backup', args.backup, '--restore-state'], tty=True)
        return
    if not args.bundle:
        raise ValueError('Stage/promote requires --bundle.')
    path = Path(args.bundle).resolve()
    checksum = path.with_suffix(path.suffix + '.sha256')
    expected = checksum.read_text().split()[0]
    manifest = inspect_bundle(path, expected)
    sha = merged_commit(manifest['sha'])
    if not args.offline:
        require_ci(sha)
    verify_source(manifest)
    remote = '.cache/oasis-library-release/' + sha
    ssh(args.jetson, ['mkdir', '-p', remote])
    run(['scp', '-o', 'StrictHostKeyChecking=yes', str(path), args.jetson + ':' + remote + '/bundle.tar.gz'])
    with tarfile.open(path) as archive, tempfile.TemporaryDirectory() as temporary:
        runner = Path(temporary) / 'target_release.py'
        runner.write_bytes(archive.extractfile('app/deploy/target_release.py').read())
        run(['scp', '-o', 'StrictHostKeyChecking=yes', str(runner), args.jetson + ':' + remote + '/target_release.py'])
    command = ['sudo', 'python3', remote + '/target_release.py', 'stage', '--sha', sha,
               '--bundle', remote + '/bundle.tar.gz', '--digest', expected]
    if args.prepare_runtime:
        command += ['--prepare-runtime', '--python', args.python]
    ssh(args.jetson, command, tty=True)
    if args.mode == 'promote':
        ssh(args.jetson, ['sudo', 'python3', remote + '/target_release.py', 'promote',
                         '--sha', sha, '--worker', args.worker], tty=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    build_parser = sub.add_parser('build', help='Build locally from an exact green merged origin/master commit.')
    build_parser.add_argument('--commit', required=True)
    build_parser.add_argument('--output', type=Path, default=Path('dist'))
    build_parser.add_argument('--wheelhouse', type=Path)
    build_parser.add_argument('--target-python')
    build_parser.add_argument('--offline-npm', action='store_true')
    check = sub.add_parser('check', help='Read-only device inventory; no uploads, migrations or restarts.')
    check.add_argument('--jetson', required=True)
    release = sub.add_parser('deploy', help='Explicitly stage, promote or restore the private curator only.')
    release.add_argument('--mode', required=True, choices=('stage', 'promote', 'rollback'))
    release.add_argument('--jetson', required=True)
    release.add_argument('--bundle', type=Path)
    release.add_argument('--prepare-runtime', action='store_true')
    release.add_argument('--python', default='/usr/bin/python3')
    release.add_argument('--worker', choices=('preserve', 'on', 'off'), default='preserve')
    release.add_argument('--sha')
    release.add_argument('--backup')
    release.add_argument('--restore-state', action='store_true')
    release.add_argument('--offline', action='store_true', help='Trust the bundle CI receipt and cached merged source; no GitHub request.')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            sha = merged_commit(args.commit)
            receipt = require_ci(sha)
            print(build(sha, args.output, args.wheelhouse, args.target_python, args.offline_npm, receipt))
        elif args.command == 'check':
            check_remote(args.jetson)
        elif args.command == 'deploy':
            deploy(args)
        else:
            parser.print_help()
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        parser.exit(1, 'Release stopped: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
