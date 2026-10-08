"""Release safety tests use disposable state; no SSH, systemd or station jobs."""
from contextlib import closing
import hashlib
import io
import shutil
import subprocess
import sys
import json
import os
import sqlite3
import tarfile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deploy import release, target_release as target

SHA = 'a' * 40
OLD = 'b' * 40


def receipt():
    return {'sha': SHA, 'checks': {name: {'id': index + 1, 'status': 'completed',
            'conclusion': 'success', 'head_sha': SHA, 'app': 'github-actions'}
            for index, name in enumerate(sorted(target.REQUIRED_CHECKS))}}


def bundle(root, extra=None, change=None):
    files = {'app/manage.py': b'# test\n', 'app/dlms/device_settings.py': b'# test\n',
             'app/deploy/target_release.py': b'# test\n', 'app/requirements-device.lock.txt': b'demo==1.0\n',
             'app/frontend/static/index.html': b'<link rel="icon" href="/static/favicon.svg"><script src="/static/js/main.js"></script>',
             'app/frontend/static/js/main.js': b'window.test=true;',
             'app/frontend/static/favicon.svg': b'<svg></svg>', 'app/release.json': json.dumps({'sha': SHA}).encode()}
    manifest = {'format': 1, 'sha': SHA, 'repository': 'shoshin-labs/kuwala-dlms', 'ci': receipt(),
                'files': {name: __import__('hashlib').sha256(data).hexdigest() for name, data in files.items()},
                'requirements_sha256': __import__('hashlib').sha256(files['app/requirements-device.lock.txt']).hexdigest()}
    if change:
        change(manifest, files)
    path = Path(root) / 'release.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in {'manifest.json': json.dumps(manifest).encode(), **files}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra:
            info = tarfile.TarInfo(extra)
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
    return path


class BundleChecks(unittest.TestCase):
    def test_valid_bundle_and_exact_checksum(self):
        with tempfile.TemporaryDirectory() as root:
            path = bundle(root)
            self.assertEqual(target.inspect_bundle(path, target.digest(path), SHA)['sha'], SHA)
            with self.assertRaisesRegex(ValueError, 'checksum'):
                target.inspect_bundle(path, '0' * 64, SHA)

    def test_corrupt_file_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as root:
            path = bundle(root, change=lambda manifest, files: files.update({'app/manage.py': b'changed'}))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                target.inspect_bundle(path)

    def test_missing_ci_or_wrong_commit_receipt_rejected(self):
        for alteration in [lambda m, f: m['ci']['checks'].pop('preview'),
                           lambda m, f: m['ci']['checks']['preview'].update(head_sha=OLD)]:
            with self.subTest(alteration=alteration), tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(ValueError, 'CI'):
                    target.inspect_bundle(bundle(root, change=alteration))

    def test_traversal_duplicate_and_unlisted_files_rejected(self):
        for name in ('../escape', 'app/manage.py', 'app/private.sqlite3'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    target.inspect_bundle(bundle(root, extra=name))

    def test_runtime_external_assets_rejected(self):
        with self.assertRaisesRegex(ValueError, 'local'):
            target.validate_html_assets('<script src="https://cdn.invalid/script.js"></script>', {})

    def test_wheels_match_every_pin_and_arm64(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / 'requirements.txt'
            lock.write_text('demo==1.0\n')
            wheels = root / 'wheels'
            wheels.mkdir()
            wheel = wheels / 'demo-1.0-py3-none-any.whl'
            with zipfile.ZipFile(wheel, 'w') as output:
                output.writestr('demo-1.0.dist-info/METADATA', 'Name: demo\nVersion: 1.0\n')
            target.validate_wheels(wheels, lock, '3.12')
            wheel.rename(wheels / 'demo-1.0-cp312-cp312-macosx_14_0_arm64.whl')
            with self.assertRaisesRegex(ValueError, 'architecture'):
                target.validate_wheels(wheels, lock, '3.12')

    def test_latest_failed_ci_overrides_old_green(self):
        checks = [{'id': index + 1, 'name': name, 'status': 'completed', 'conclusion': 'success',
                   'head_sha': SHA, 'app': {'slug': 'github-actions'}}
                  for index, name in enumerate(sorted(target.REQUIRED_CHECKS))]
        response = SimpleNamespace(stdout=json.dumps({'total_count': len(checks), 'check_runs': checks}))
        with patch.object(release, 'run', return_value=response):
            self.assertEqual(set(release.require_ci(SHA)['checks']), target.REQUIRED_CHECKS)
        checks.append({**checks[0], 'id': 99, 'conclusion': 'failure'})
        response.stdout = json.dumps({'total_count': len(checks), 'check_runs': checks})
        with patch.object(release, 'run', return_value=response), self.assertRaisesRegex(ValueError, 'latest'):
            release.require_ci(SHA)

    def test_read_only_remote_check_uses_stdin_without_upload(self):
        with patch.object(release, 'run') as command:
            release.check_remote('operator@known-device.local')
        self.assertEqual(command.call_count, 1)
        argv = command.call_args.args[0]
        self.assertEqual(argv[0], 'ssh')
        self.assertEqual(argv[-1], 'sudo -n python3 - check')
        self.assertIn('input', command.call_args.kwargs)
        self.assertNotIn('scp', argv)


class StateChecks(unittest.TestCase):
    def make_state(self, root):
        data = Path(root) / 'data'
        for name in ('media/contents', 'builds', 'indexing', 'backups', 'logs'):
            (data / name).mkdir(parents=True, exist_ok=True)
        (data / 'backups').chmod(0o700)
        (data / 'media/contents/original.pdf').write_bytes(b'exact-original')
        with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as database, database:
            database.execute('CREATE TABLE content (id INTEGER PRIMARY KEY, title TEXT)')
            database.execute("INSERT INTO content VALUES (1,'real operator source')")
            database.execute('CREATE TABLE content_management_oasisindexjob (state TEXT)')
            database.execute("INSERT INTO content_management_oasisindexjob VALUES ('queued')")
        return data

    def test_coherent_backup_restores_database_media_and_pending_jobs(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            identifier = target.backup_state(data, SHA, '/previous', '/runtime', {'station': 'unchanged'})
            backup, record = target.verify_backup(data, identifier, SHA)
            (data / 'media/contents/original.pdf').write_bytes(b'replacement')
            with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as database, database:
                database.execute("UPDATE content SET title='newer edit'")
            target.restore_state(data, backup)
            self.assertEqual((data / 'media/contents/original.pdf').read_bytes(), b'exact-original')
            with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as database, database:
                self.assertEqual(database.execute('SELECT title FROM content').fetchone()[0], 'real operator source')
                self.assertEqual(database.execute('SELECT state FROM content_management_oasisindexjob').fetchone()[0], 'queued')
            self.assertEqual(record['station'], {'station': 'unchanged'})

    def make_index_draft(self, data):
        draft = data / 'indexing/jobs/11111111-2222-4333-8444-555555555555/draft'
        snapshot = draft / 'v-0123456789abcdef-12345678'
        (snapshot / 'content').mkdir(parents=True)
        (snapshot / 'content/original.pdf').write_bytes(b'labelled indexed test original')
        (snapshot / 'manifest.json').write_text(json.dumps({'library_version': 'labelled-test-snapshot'}))
        with closing(sqlite3.connect(snapshot / 'index.sqlite3')) as connection, connection:
            connection.execute('CREATE TABLE passages (document_id TEXT, page INTEGER, text TEXT)')
            connection.execute("INSERT INTO passages VALUES ('fixture',1,'Labelled test passage')")
        (draft / 'current').symlink_to(snapshot.name, target_is_directory=True)
        return draft, snapshot

    def test_index_draft_pointer_is_verified_backed_up_and_restored_as_a_link(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            draft, snapshot = self.make_index_draft(data)
            identifier = target.backup_state(data, SHA, None, None, {})
            backup, record = target.verify_backup(data, identifier, SHA)
            relative = (draft / 'current').relative_to(data).as_posix()
            binding = record['files'][relative]
            self.assertEqual(binding['type'], 'symlink')
            self.assertEqual(binding['target'], snapshot.name)
            self.assertEqual(binding['sha256'], hashlib.sha256(b'relative-symlink\0' + snapshot.name.encode()).hexdigest())
            saved = backup / 'snapshot' / relative
            self.assertTrue(saved.is_symlink())
            self.assertEqual(os.readlink(saved), snapshot.name)
            self.assertFalse(any(name.startswith(relative + '/') for name in record['files']))
            # Change the live pointer and snapshot after backup; restore the
            # exact original directory bytes and the relative pointer itself.
            (snapshot / 'content/original.pdf').write_bytes(b'replaced after backup')
            (draft / 'current').unlink()
            target.restore_state(data, backup)
            self.assertTrue((draft / 'current').is_symlink())
            self.assertEqual(os.readlink(draft / 'current'), snapshot.name)
            self.assertEqual((draft / 'current/content/original.pdf').read_bytes(), b'labelled indexed test original')
            self.assertEqual(target.digest(snapshot / 'index.sqlite3'), record['files'][(snapshot / 'index.sqlite3').relative_to(data).as_posix()])
            target.verify_backup(data, identifier, SHA)

    def test_pointer_binding_detects_a_different_valid_snapshot_before_restore(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            draft, snapshot = self.make_index_draft(data)
            other = draft / 'v-fedcba9876543210-87654321'
            shutil.copytree(snapshot, other)
            identifier = target.backup_state(data, SHA, None, None, {})
            backup, _ = target.verify_backup(data, identifier, SHA)
            saved = backup / 'snapshot' / (draft / 'current').relative_to(data)
            saved.unlink()
            saved.symlink_to(other.name, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                target.verify_backup(data, identifier, SHA)
            (data / 'media/contents/original.pdf').write_bytes(b'newer live bytes')
            with self.assertRaisesRegex(ValueError, 'changed before restore'):
                target.restore_state(data, backup)
            self.assertEqual((data / 'media/contents/original.pdf').read_bytes(), b'newer live bytes')
            self.assertEqual(os.readlink(draft / 'current'), snapshot.name)

    def test_absolute_escaping_nested_missing_and_aliased_snapshot_pointers_reject(self):
        for kind in ('absolute', 'escape', 'nested', 'missing', 'aliased'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                data = self.make_state(root)
                draft, snapshot = self.make_index_draft(data)
                pointer = draft / 'current'
                pointer.unlink()
                targets = {'absolute': str(snapshot.resolve()), 'escape': '../' + snapshot.name,
                           'nested': snapshot.name + '/content', 'missing': 'v-does-not-exist', 'aliased': 'v-alias'}
                if kind == 'aliased':
                    (draft / 'v-alias').symlink_to(snapshot, target_is_directory=True)
                pointer.symlink_to(targets[kind], target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'pointer'):
                    target.backup_state(data, SHA, None, None, {})
                self.assertEqual(list((data / 'backups').iterdir()), [])

    def test_state_links_under_originals_builds_or_nonjob_paths_reject(self):
        for area in ('media/contents', 'builds', 'indexed-original', 'nonuuid-job', 'other-pointer'):
            with self.subTest(area=area), tempfile.TemporaryDirectory() as root:
                data = self.make_state(root)
                draft, snapshot = self.make_index_draft(data)
                if area == 'indexed-original':
                    path = snapshot / 'content/alias.pdf'
                    target_path = data / 'media/contents/original.pdf'
                elif area == 'nonuuid-job':
                    path = data / 'indexing/jobs/not-a-uuid/draft/current'
                    path.parent.mkdir(parents=True)
                    target_path = snapshot
                elif area == 'other-pointer':
                    path, target_path = draft / 'previous', snapshot.name
                else:
                    path, target_path = data / area / 'alias', snapshot
                path.symlink_to(target_path)
                with self.assertRaisesRegex(ValueError, 'only the importer'):
                    target.backup_state(data, SHA, None, None, {})

    def test_release_tree_remains_strict_even_for_an_allowed_state_pointer_shape(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            self.make_index_draft(data)
            with self.assertRaisesRegex(ValueError, 'link or special'):
                target.tree_hashes(data / 'indexing')

    def test_modified_backup_or_other_transaction_cannot_restore(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            identifier = target.backup_state(data, SHA, None, None, {})
            with self.assertRaisesRegex(ValueError, 'match'):
                target.verify_backup(data, identifier, OLD)
            (data / 'backups' / identifier / 'snapshot/media/contents/original.pdf').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                target.verify_backup(data, identifier, SHA)

    def test_catalogue_import_provenance_and_journal_restore_with_authoring_state(self):
        for prior_import in (False, True):
            with self.subTest(prior_import=prior_import), tempfile.TemporaryDirectory() as root:
                data = self.make_state(root)
                control = data / 'catalogue-import'
                prior = {'reviewed-manifest.json': b'{"catalogue":"labelled prior review"}',
                         'receipt.json': b'{"catalogue":"labelled prior receipt"}',
                         'journal.json': b'{"state":"committed","catalogue":"labelled prior import"}',
                         'import.lock': b''}
                if prior_import:
                    control.mkdir()
                    for name, contents in prior.items():
                        (control / name).write_bytes(contents)
                # Staging is outside paired state, including its unrelated
                # published/current pointer. Do not scan/copy/restore it.
                staging = data / 'imports/labelled-staging/published'
                (staging / 'v-staged').mkdir(parents=True)
                (staging / 'current').symlink_to('v-staged', target_is_directory=True)
                identifier = target.backup_state(data, SHA, None, None, {})
                backup, record = target.verify_backup(data, identifier, SHA)
                self.assertFalse(any(name.startswith('imports/') for name in record['files']))
                control.mkdir(exist_ok=True)
                for name in prior:
                    (control / name).write_bytes(b'labelled newer committed import')
                (control / 'newer-record.json').write_bytes(b'labelled newer receipt')
                with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as connection, connection:
                    connection.execute("UPDATE content SET title='newer imported catalogue'")
                (data / 'media/contents/original.pdf').write_bytes(b'newer imported original')
                target.restore_state(data, backup)
                with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as connection:
                    self.assertEqual(connection.execute('SELECT title FROM content').fetchone()[0], 'real operator source')
                self.assertEqual((data / 'media/contents/original.pdf').read_bytes(), b'exact-original')
                if prior_import:
                    self.assertEqual({path.name: path.read_bytes() for path in control.iterdir()}, prior)
                    self.assertTrue(all('catalogue-import/' + name in record['files'] for name in prior))
                else:
                    self.assertFalse(control.exists(), 'First-import rollback must remove its committed journal so a real retry remains possible.')
                self.assertTrue((staging / 'current').is_symlink())
                self.assertEqual(os.readlink(staging / 'current'), 'v-staged')

    def test_backup_parent_and_snapshot_root_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            identifier = target.backup_state(data, SHA, None, None, {})
            snapshot = data / 'backups' / identifier / 'snapshot'
            moved = data / 'moved-snapshot'
            snapshot.rename(moved)
            snapshot.symlink_to(moved, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'snapshot'):
                target.verify_backup(data, identifier, SHA)
            with self.assertRaisesRegex(ValueError, 'root'):
                target.tree_hashes(snapshot)
            backups = data / 'backups'
            renamed = data / 'moved-backups'
            backups.rename(renamed)
            backups.symlink_to(renamed, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'backup root'):
                target.backup_state(data, SHA, None, None, {})
            with self.assertRaisesRegex(ValueError, 'backup root'):
                target.verify_backup(data, identifier, SHA)

    def test_private_umask_preserves_service_readable_code_and_private_data(self):
        with tempfile.TemporaryDirectory() as root:
            instance = target.Target(Path(root).resolve() / 'new-install')
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            prior = os.umask(0o077)
            try:
                with patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target.os, 'chown'):
                    instance.prepare_directories()
            finally:
                os.umask(prior)
            self.assertEqual(instance.base.stat().st_mode & 0o777, 0o755)
            self.assertEqual(instance.releases.stat().st_mode & 0o777, 0o755)
            self.assertEqual(instance.data.stat().st_mode & 0o777, 0o700)
            self.assertEqual((instance.data / 'backups').stat().st_mode & 0o777, 0o700)

    def test_nondefault_mutation_base_is_rejected_before_any_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            protected = Path(root) / 'station'
            protected.mkdir()
            (protected / 'original').write_bytes(b'unchanged')
            with patch.object(sys, 'argv', ['target_release.py', 'stage', '--base', str(protected), '--sha', SHA]), \
                    patch.object(target.Target, 'stage') as mutation, patch.object(target.os, 'chown') as ownership:
                with self.assertRaises(SystemExit) as result:
                    target.main()
            self.assertEqual(result.exception.code, 1)
            mutation.assert_not_called()
            ownership.assert_not_called()
            self.assertEqual(list(protected.iterdir()), [protected / 'original'])
            self.assertEqual((protected / 'original').read_bytes(), b'unchanged')

    def test_management_timeout_terminates_spawned_writer(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            marker, started = root / 'late-write', root / 'started'
            child = 'import time; from pathlib import Path; time.sleep(0.8); Path(' + repr(str(marker)) + ').write_text("orphan")'
            parent = ('import subprocess,sys,time; from pathlib import Path; '
                      'subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); '
                      'Path(' + repr(str(started)) + ').write_text("started"); time.sleep(30)')
            with (root / 'log').open('wb') as output:
                with self.assertRaises(subprocess.TimeoutExpired):
                    target.run_management([sys.executable, '-c', parent], cwd=root, env=dict(os.environ), output=output, timeout=0.3)
            self.assertTrue(started.exists())
            time.sleep(1)
            self.assertFalse(marker.exists(), 'A migration child must not continue writing during recovery.')

    def test_management_account_switch_works_with_restricted_device_path(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            instance = target.Target(root)
            (instance.data / 'logs').mkdir(parents=True)
            environment = {'PATH': '/usr/local/bin:/usr/bin:/bin'}
            with patch.object(instance, 'operator_environment', return_value=environment), \
                    patch.object(target, 'run_management', return_value=0) as command:
                instance.manage(root / SHA, root / 'runtime', ['check'])
            executable = command.call_args.args[0][0]
            self.assertEqual(executable, '/usr/sbin/runuser')
            self.assertNotIn('/usr/sbin', command.call_args.kwargs['env']['PATH'].split(':'))

    def test_runtime_preparation_uses_readable_directories_and_child_umask(self):
        with tempfile.TemporaryDirectory() as root:
            instance = target.Target(Path(root).resolve())
            release_path = instance.base / 'release'
            release_path.mkdir()
            manifest = {'runtime': {'machine': 'aarch64', 'python': '3.12'}, 'requirements_sha256': 'f' * 64}
            def command(args, **kwargs):
                if args[1:3] == ['-m', 'venv']:
                    Path(args[3]).mkdir(mode=0o755)
                return SimpleNamespace(stdout=json.dumps(['aarch64', '3.12']), returncode=0)
            prior = os.umask(0o077)
            try:
                with patch.object(target, 'validate_wheels'), patch.object(instance, 'verify_runtime'), \
                        patch.object(target.subprocess, 'run', side_effect=command) as commands:
                    instance.prepare_runtime(release_path, manifest, '/existing/python')
            finally:
                os.umask(prior)
            self.assertEqual((instance.base / 'runtimes').stat().st_mode & 0o777, 0o755)
            installer = [call for call in commands.call_args_list if call.args[0][1:3] in (['-m', 'venv'], ['-m', 'pip'])]
            self.assertEqual(len(installer), 2)
            self.assertTrue(all(call.kwargs['umask'] == 0o022 for call in installer))

    def test_operator_paths_hidden_by_protecthome_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            instance = target.Target(Path(root).resolve())
            env = instance.base / 'env'
            original_stat = Path.stat
            def root_owned(path, *args, **kwargs):
                value = original_stat(path, *args, **kwargs)
                return SimpleNamespace(st_mode=value.st_mode, st_uid=0) if path == env else value
            for hidden in ('/home/operator/manifest.json', '/root/manifest.json', '/run/user/1000/manifest.json'):
                with self.subTest(hidden=hidden):
                    env.write_text('OASIS_DEVICE_DATA_ROOT=' + str(instance.data) + '\nOASIS_INDEXING_MANIFEST=' + hidden + '\n')
                    env.chmod(0o600)
                    with patch.object(Path, 'stat', root_owned):
                        with self.assertRaisesRegex(ValueError, 'ProtectHome'):
                            instance.operator_environment()

    def test_running_job_requests_maintenance_without_stopping_process(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as database, database:
                database.execute("UPDATE content_management_oasisindexjob SET state='running'")
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target.subprocess, 'run') as process:
                with self.assertRaisesRegex(ValueError, 'No job was terminated'):
                    target.pause_worker(data)
            self.assertTrue((data / 'indexing/maintenance.json').is_file())
            process.assert_not_called()

    def test_stale_ack_does_not_stop_worker(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            (data / 'indexing/worker.json').write_text(json.dumps({'active': True, 'maintenance': True,
                    'maintenance_nonce': '0' * 32, 'last_seen': time.time(), 'pid': 42}))
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            state = {'ActiveState': 'active', 'MainPID': '42'}
            with patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target, 'service_state', return_value=state), \
                    patch.object(target.time, 'monotonic', side_effect=[0, 0, 2]), patch.object(target.time, 'sleep'), \
                    patch.object(target.subprocess, 'run') as process:
                with self.assertRaisesRegex(ValueError, 'acknowledge'):
                    target.pause_worker(data, timeout=1)
            process.assert_not_called()

    def test_exact_nonce_with_wrong_process_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            data = self.make_state(root)
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            heartbeat = {'active': True, 'maintenance': True, 'maintenance_nonce': '1' * 32,
                         'last_seen': time.time(), 'pid': 99}
            with patch.object(target.uuid, 'uuid4', return_value=SimpleNamespace(hex='1' * 32)), \
                    patch.object(target.pwd, 'getpwnam', return_value=account), \
                    patch.object(target, 'read_json', return_value=heartbeat), \
                    patch.object(target, 'service_state', return_value={'ActiveState': 'active', 'MainPID': '42'}), \
                    patch.object(target.subprocess, 'run') as process:
                with self.assertRaisesRegex(ValueError, 'different process'):
                    target.pause_worker(data)
            process.assert_not_called()

    def test_first_install_skips_absent_unit_but_loaded_stop_failure_propagates(self):
        with patch.object(target, 'service_state', return_value={'LoadState': 'not-found'}), \
                patch.object(target.subprocess, 'run') as process:
            target.stop_web()
            process.assert_not_called()
        with patch.object(target, 'service_state', return_value={'LoadState': 'loaded'}), \
                patch.object(target.subprocess, 'run', side_effect=__import__('subprocess').CalledProcessError(1, ['systemctl'])):
            with self.assertRaises(__import__('subprocess').CalledProcessError):
                target.stop_web()

    def test_station_real_shaped_id_and_provenance_changes_are_detected(self):
        status = {'release_sha': OLD, 'model': 'local', 'pdf_library': {'documents': [{'id': 'source',
                  'filename': 'original.pdf', 'sha256': 'f' * 64, 'library_version': 'v6', 'title': 'Original title',
                  'licence': 'CC-BY-4.0'}], 'libraries': [{'id': 'learning', 'label': 'Learning', 'document_ids': ['source']}],
                  'semantic': {'enabled': True, 'available': True, 'model': 'nomic-embed-text:latest'}}}
        class Response(io.StringIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
        with patch.object(target.urllib.request, 'urlopen', side_effect=lambda *a, **k: Response(json.dumps(status))):
            before = target.station_fingerprint()
            self.assertEqual(before['pdf_trial']['document_count'], 1)
            status['pdf_library']['documents'][0]['licence'] = 'different rights'
            after = target.station_fingerprint()
            self.assertNotEqual(before, after)


class LifecycleChecks(unittest.TestCase):
    def fake_target(self, root, fail_migrate=False):
        owner = StateChecks()
        data = owner.make_state(root)
        root = Path(root).resolve()
        instance = target.Target(root)
        instance.releases.mkdir()
        for sha in (SHA, OLD):
            (instance.releases / sha / 'app').mkdir(parents=True)
        runtime = Path(root) / 'runtime'
        runtime.mkdir()
        (Path(root) / 'venv').symlink_to(runtime, target_is_directory=True)
        instance.verify_release = lambda path: ({}, {'runtime': str(runtime), 'station': {}})
        instance.install_units = lambda path: None
        instance.readiness = lambda *args: None
        instance.operator_environment = lambda: {name: 'explicit' for name in
            ('OASIS_INDEXING_STATION_ROOT', 'OASIS_INDEXING_PYTHON', 'OASIS_INDEXING_MANIFEST')}
        def manage(path, env, arguments):
            if fail_migrate and arguments[0] == 'migrate':
                with closing(sqlite3.connect(data / 'catalogue.sqlite3')) as database, database:
                    database.execute('CREATE TABLE partial_migration (id INTEGER)')
                raise ValueError('migration failed')
        instance.manage = manage
        return instance

    def test_failed_migration_keeps_backup_and_requires_explicit_state_restore(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root, fail_migrate=True)
            (Path(root) / 'current').symlink_to(instance.releases / OLD, target_is_directory=True)
            with patch.object(target, 'pause_worker'), patch.object(target, 'require_idle_worker'), \
                    patch.object(target, 'station_fingerprint', return_value={}), \
                    patch.object(target, 'service_state', return_value={'LoadState': 'loaded', 'UnitFileState': 'disabled'}), \
                    patch.object(target.subprocess, 'run'):
                with self.assertRaisesRegex(ValueError, 'migration failed'):
                    instance.promote(SHA)
            state = target.read_json(instance.state_file)
            self.assertEqual(state['phase'], 'failed')
            backup, _ = target.verify_backup(instance.data, state['backup'], SHA)
            with closing(sqlite3.connect(backup / 'snapshot/catalogue.sqlite3')) as database, database:
                self.assertIsNone(database.execute("SELECT name FROM sqlite_master WHERE name='partial_migration'").fetchone())
            self.assertEqual((Path(root) / 'current').resolve(), (instance.releases / OLD).resolve())
            with self.assertRaisesRegex(ValueError, 'restore-state'):
                instance.rollback(SHA, state['backup'])

    def test_restore_disables_worker_that_was_disabled_before_promotion(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root)
            (Path(root) / 'current').symlink_to(instance.releases / SHA, target_is_directory=True)
            identifier = target.backup_state(instance.data, SHA, str(instance.releases / OLD), str(Path(root) / 'runtime'), {})
            target.atomic_json(instance.state_file, {'sha': SHA, 'phase': 'active', 'backup': identifier, 'worker_enabled': False})
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(target, 'pause_worker'), patch.object(target, 'station_fingerprint', return_value={}), \
                    patch.object(target, 'service_state', return_value={'LoadState': 'loaded'}), \
                    patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target.subprocess, 'run') as commands:
                instance.rollback(SHA, identifier, restore=True)
            commands.assert_any_call(['systemctl', 'disable', target.WORKER], check=True)
            self.assertEqual((Path(root) / 'current').resolve(), (instance.releases / OLD).resolve())
            self.assertEqual(target.read_json(instance.state_file)['phase'], 'rolled_back')

    def test_invalid_worker_probe_blocks_before_stopping_or_migrating(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root)
            def invalid(*args):
                raise ValueError('Reviewed manifest or lexical dependency unavailable')
            instance.manage = invalid
            with patch.object(target, 'station_fingerprint', return_value={}), \
                    patch.object(target, 'service_state', return_value={'UnitFileState': 'disabled'}), \
                    patch.object(target, 'pause_worker') as paused, patch.object(target.subprocess, 'run') as commands:
                with self.assertRaisesRegex(ValueError, 'manifest'):
                    instance.promote(SHA, worker='on')
            paused.assert_not_called()
            commands.assert_not_called()
            self.assertFalse(instance.state_file.exists())

    def test_lexical_probe_does_not_require_vector_availability(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root)
            calls = []
            instance.manage = lambda release, runtime, args: calls.append(args)
            instance.worker_preflight(instance.releases / SHA, instance.base / 'runtime')
            self.assertEqual(calls[0][:2], ['shell', '-c'])
            # Run the actual preflight snippet against a fake read-only adapter.
            from types import ModuleType
            adapter = ModuleType('content_management.oasis_indexing')
            adapter.operator_config = lambda: {'manifest': 'reviewed'}
            adapter.configuration_probe = lambda config: {'lexical_available': True, 'vector_available': False}
            with patch.dict(sys.modules, {'content_management': ModuleType('content_management'),
                                         'content_management.oasis_indexing': adapter}):
                exec(calls[0][2], {})

    def test_external_or_broken_current_is_rejected_before_pause(self):
        for broken in (False, True):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as root:
                instance = self.fake_target(root)
                outside = instance.base / 'legacy-unmanaged'
                if not broken:
                    outside.mkdir()
                (instance.base / 'current').symlink_to(outside, target_is_directory=True)
                with patch.object(target, 'pause_worker') as paused:
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        instance.promote(SHA)
                paused.assert_not_called()

    def test_first_commission_failed_migration_restores_blank_prior_state(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root, fail_migrate=True)
            (instance.data / 'catalogue.sqlite3').unlink()
            (instance.data / 'media/contents/original.pdf').unlink()
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(target, 'station_fingerprint', return_value={}), \
                    patch.object(target, 'service_state', return_value={'LoadState': 'not-found', 'ActiveState': 'inactive'}), \
                    patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target.subprocess, 'run') as commands:
                with self.assertRaisesRegex(ValueError, 'migration failed'):
                    instance.promote(SHA, worker='off')
                state = target.read_json(instance.state_file)
                self.assertIsNone(state['previous'])
                self.assertTrue((instance.data / 'indexing/maintenance.json').is_file())
                self.assertTrue((instance.data / 'catalogue.sqlite3').is_file())
                instance.rollback(SHA, state['backup'], restore=True)
            self.assertFalse((instance.base / 'current').exists())
            self.assertFalse((instance.data / 'catalogue.sqlite3').exists())
            self.assertEqual(list((instance.data / 'media/contents').iterdir()), [])
            self.assertEqual(target.read_json(instance.state_file)['phase'], 'rolled_back')
            commands.assert_any_call(['systemctl', 'disable', target.WEB, target.WORKER], check=True)

    def test_failed_rollback_readiness_stops_web_and_retains_maintenance(self):
        with tempfile.TemporaryDirectory() as root:
            instance = self.fake_target(root)
            (instance.base / 'current').symlink_to(instance.releases / SHA, target_is_directory=True)
            identifier = target.backup_state(instance.data, SHA, str(instance.releases / OLD), str(instance.base / 'runtime'), {})
            target.atomic_json(instance.state_file, {'sha': SHA, 'phase': 'failed', 'backup': identifier, 'worker_enabled': False})
            before = target.tree_hashes(instance.data / 'backups' / identifier)
            instance.readiness = lambda *args: (_ for _ in ()).throw(ValueError('readiness failed'))
            account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
            with patch.object(target, 'pause_worker', side_effect=lambda data: target.request_maintenance(data)), \
                    patch.object(target, 'station_fingerprint', return_value={}), \
                    patch.object(target, 'service_state', return_value={'LoadState': 'loaded'}), \
                    patch.object(target.pwd, 'getpwnam', return_value=account), patch.object(target.subprocess, 'run') as commands:
                with self.assertRaisesRegex(ValueError, 'readiness failed'):
                    instance.rollback(SHA, identifier, restore=True)
            self.assertEqual(target.read_json(instance.state_file)['phase'], 'restoring')
            self.assertTrue((instance.data / 'indexing/maintenance.json').is_file())
            self.assertEqual(before, target.tree_hashes(instance.data / 'backups' / identifier))
            commands.assert_any_call(['systemctl', 'stop', target.WEB], check=True)
            self.assertNotIn(['systemctl', 'enable', '--now', target.WORKER], [call.args[0] for call in commands.call_args_list])


if __name__ == '__main__':
    unittest.main()
