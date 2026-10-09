"""Device configuration, durable indexing and private file boundaries."""
import json
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from unittest import skipUnless
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from content_management.oasis_indexing import maintenance_request, operator_config, run_probe, staging_base, job_root, station_environment
from content_management.oasis_search import run_search
from content_management.management.commands.run_oasis_index_jobs import run_command


REPOSITORY = Path(__file__).resolve().parent.parent


class DeviceConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.secret = self.root / 'secret-key'
        self.secret.write_text('aB7.' * 20 + 'C8dEfGhIjKlMnOpQrStUvWxYz')
        self.secret.chmod(0o600)
        self.data = self.root / 'data'
        self.env = {'OASIS_DEVICE_SECRET_KEY_FILE': str(self.secret), 'OASIS_DEVICE_DATA_ROOT': str(self.data)}

    def load(self, env=None, source=None, action=''):
        script = (
            'import json, runpy; '
            's = runpy.run_path(%r); ' % str(source or REPOSITORY / 'dlms/device_settings.py')
            + action
            + 'print(json.dumps({"debug":s["DEBUG"],"database":s["DATABASES"]["default"]["NAME"],'
              '"media":s["MEDIA_ROOT"],"builds":s["BUILDS_ROOT"],"indexing":s["OASIS_INDEXING_STATE_ROOT"],'
              '"static":s["STATIC_ROOT"],"curator":s["OASIS_CURATOR_ENABLED"],"loopback":s["OASIS_LOOPBACK_ONLY"],'
              '"authentication_required":s["OASIS_REQUIRE_CURATOR_AUTH"],"admin_origin":s["OASIS_DEVICE_ADMIN_ORIGIN"]}))'
        )
        return subprocess.run([sys.executable, '-B', '-c', script], cwd=REPOSITORY,
                              env={**os.environ, **(self.env if env is None else env)}, capture_output=True, text=True, timeout=15)

    def test_device_ignores_legacy_environment_and_uses_durable_paths(self):
        result = self.load({**self.env, 'DEBUG': 'True', 'SECRET_KEY': 'untrusted',
                            'DATABASE_URL': 'sqlite:////untrusted.sqlite3', 'MEDIA_ROOT': '/untrusted',
                            'ALLOWED_HOSTS': '*', 'BUILDS_ROOT': '/untrusted', 'OASIS_REQUIRE_CURATOR_AUTH': 'False'})
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertFalse(config['debug'])
        self.assertTrue(config['curator'] and config['loopback'])
        self.assertTrue(config['authentication_required'])
        self.assertEqual(config['admin_origin'], '')
        self.assertEqual(config['database'], str(self.data / 'catalogue.sqlite3'))
        for key, relative in (('media', 'media'), ('builds', 'builds'), ('indexing', 'indexing')):
            self.assertEqual(config[key], str(self.data / relative))
        self.assertEqual(config['static'], str(REPOSITORY / 'collected-static'))

    def test_missing_weak_permissive_and_symlink_secrets_fail_without_key_disclosure(self):
        bad = self.root / 'bad-key'
        cases = [{**self.env, 'OASIS_DEVICE_SECRET_KEY_FILE': ''}]
        for value, mode in (('short', 0o600), ('z' * 80, 0o600), ('django-insecure-' + 'abcd1234' * 10, 0o600),
                            ('Abcd1234' * 10, 0o644)):
            bad.write_text(value)
            bad.chmod(mode)
            result = self.load({**self.env, 'OASIS_DEVICE_SECRET_KEY_FILE': str(bad)})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(value, result.stdout + result.stderr)
        link = self.root / 'linked-key'
        link.symlink_to(self.secret)
        cases.append({**self.env, 'OASIS_DEVICE_SECRET_KEY_FILE': str(link)})
        for env in cases:
            result = self.load(env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('OASIS_DEVICE_SECRET_KEY_FILE', result.stderr)
        self.assertFalse(self.data.exists())

    def test_missing_relative_code_owned_and_symlink_state_fail_closed(self):
        link = self.root / 'linked-state'
        link.symlink_to(self.root, target_is_directory=True)
        for value in ('', 'relative/data', str(REPOSITORY / 'data'), str(link / 'data')):
            result = self.load({**self.env, 'OASIS_DEVICE_DATA_ROOT': value})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('OASIS_DEVICE_DATA_ROOT', result.stderr)
        self.data.mkdir(mode=0o700)
        (self.data / 'media').symlink_to(self.root, target_is_directory=True)
        self.assertNotEqual(self.load().returncode, 0)

    def test_device_settings_pass_django_system_checks_without_source_env(self):
        result = self.load(action=(
            'from django.conf import settings; settings.configure(**{k:v for k,v in s.items() if k.isupper()}); '
            'import django, io; django.setup(); from django.core.management import call_command; '
            'call_command("check",stdout=io.StringIO()); '
        ))
        self.assertEqual(result.returncode, 0, result.stderr)

    @skipUnless(importlib.util.find_spec('whitenoise'), 'Requires the isolated device runtime lock.')
    def test_compressed_device_assets_preserve_bytes_and_scope_immutable_caching(self):
        source = self.root / 'asset-source'
        source.mkdir()
        script_bytes = b'window.syntheticCompressionFixture="local offline asset";\n' * 100
        files = {
            'js/main.0123456789abcdef0123.bundle.js': script_bytes,
            'js/vendors~curator.0123456789abcdef0123.bundle.js': script_bytes,
            'js/main.01234567.bundle.js': script_bytes,
            'js/current.js': script_bytes,
            'other/main.0123456789abcdef0123.bundle.js': script_bytes,
            'images/kuwala-oasis.svg': b'<svg xmlns="http://www.w3.org/2000/svg"><title>synthetic test asset</title></svg>',
        }
        for name, contents in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        action = (
            'import gzip,io; from django.conf import settings; '
            'config={k:v for k,v in s.items() if k.isupper()}; '
            'config.update(STATIC_ROOT=%r,STATICFILES_DIRS=[%r],'
            'STATICFILES_FINDERS=["django.contrib.staticfiles.finders.FileSystemFinder"]); '
            % (str(self.root / 'collected-static'), str(source))
            + 'settings.configure(**config); import django; django.setup(); '
            'from django.core.management import call_command; '
            'call_command("collectstatic",interactive=False,verbosity=0,stdout=io.StringIO()); '
            'from django.test import Client; client=Client(); '
            'expected=%r; ' % files
            + '\nfor name,contents in expected.items():\n'
              ' response=client.get("/static/"+name); assert response.status_code==200; '
              'assert b"".join(response.streaming_content)==contents; response.close();\n'
              ' cache=response["Cache-Control"]; '
              'immutable=name in ("js/main.0123456789abcdef0123.bundle.js","js/vendors~curator.0123456789abcdef0123.bundle.js"); '
              'assert ("immutable" in cache)==immutable,(name,cache);\n'
              ' if name.startswith("js/"):\n'
              '  response=client.get("/static/"+name,HTTP_ACCEPT_ENCODING="gzip"); '
              'assert response.status_code==200; assert response["Content-Encoding"]=="gzip"; '
              'assert "Accept-Encoding" in response["Vary"]; '
              'assert gzip.decompress(b"".join(response.streaming_content))==contents; response.close();\n'
        )
        result = self.load(action=action)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_catalogue_ids_originals_jobs_survive_code_release_switch(self):
        sources = []
        for name in ('release-a', 'release-b'):
            module = self.root / name / 'dlms/device_settings.py'
            module.parent.mkdir(parents=True)
            shutil.copyfile(REPOSITORY / 'dlms/device_settings.py', module)
            (module.parent.parent / '.env').write_text('DEBUG=True\nSECRET_KEY=untrusted\nDATABASE_URL=sqlite:////bad.sqlite3\n')
            sources.append(module)
        action = (
            'from django.conf import settings; settings.configure(**{k:v for k,v in s.items() if k.isupper()}); '
            'import django; django.setup(); from django.core.management import call_command; '
            'call_command("migrate",verbosity=0); from content_management.models import Content; '
            'document=Content.objects.create(title="Persistent device original"); '
            'from django.core.files.base import ContentFile; document.content_file.save("persistent.pdf",ContentFile(b"%PDF-1.4 fixture")); '
        )
        first = self.load(source=sources[0], action=action)
        self.assertEqual(first.returncode, 0, first.stderr)
        job = self.data / 'indexing/jobs' / str(uuid.uuid4())
        job.mkdir()
        (job / 'receipt.json').write_text('{"private_draft":true}')
        second_action = (
            'from django.conf import settings; settings.configure(**{k:v for k,v in s.items() if k.isupper()}); '
            'import django; django.setup(); from content_management.models import Content; '
            'document=Content.objects.get(title="Persistent device original"); '
            'assert document.pk==1; assert document.content_file.read()==b"%PDF-1.4 fixture"; '
        )
        second = self.load(source=sources[1], action=second_action)
        self.assertEqual(second.returncode, 0, second.stderr)
        before, after = json.loads(first.stdout), json.loads(second.stdout)
        self.assertEqual(before['database'], after['database'])
        self.assertEqual(before['media'], after['media'])
        self.assertNotEqual(before['static'], after['static'])
        self.assertTrue((job / 'receipt.json').is_file())

    @skipUnless(importlib.util.find_spec('gunicorn') and importlib.util.find_spec('whitenoise'), 'Requires the isolated device runtime lock.')
    def test_real_gunicorn_device_wsgi_keeps_catalogue_private_and_enforces_auth(self):
        environment = {**os.environ, **self.env, 'DJANGO_SETTINGS_MODULE': 'dlms.device_settings'}
        for name in ('PYTHONHOME', 'PYTHONPATH'):
            environment.pop(name, None)
        prepared = subprocess.run([sys.executable, '-B', 'manage.py', 'migrate', '--noinput', '--verbosity=0'],
                                  env=environment, cwd=REPOSITORY, capture_output=True, text=True, timeout=20)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        log_path = self.root / 'gunicorn-test.log'
        with log_path.open('wb') as log:
            process = subprocess.Popen([sys.executable, '-B', '-m', 'gunicorn', 'dlms.wsgi:application',
                                        '--bind', '127.0.0.1:%s' % port, '--workers', '1', '--timeout', '10'],
                                       env=environment, cwd=REPOSITORY, stdout=log, stderr=subprocess.STDOUT)
            try:
                base = 'http://127.0.0.1:%s' % port
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with urlopen(base + '/healthz', timeout=1) as response:
                            config = json.load(response)['data']
                        break
                    except (URLError, OSError):
                        if process.poll() is not None or time.monotonic() >= deadline:
                            self.fail('Device WSGI did not become ready: ' + log_path.read_text())
                        time.sleep(0.05)
                self.assertEqual(config, {'ready': True, 'authentication_required': True})
                for endpoint in ('/api/oasis/config/', '/api/contents/', '/media/contents/missing.pdf'):
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(base + endpoint, timeout=2)
                    self.assertEqual(denied.exception.code, 401)
                    denied.exception.close()
                request = Request(base + '/api/oasis/index-jobs/', data=b'{}', method='POST',
                                  headers={'Content-Type': 'application/json', 'Origin': base})
                with self.assertRaises(HTTPError) as denied:
                    urlopen(request, timeout=2)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@skipUnless(importlib.util.find_spec('whitenoise'), 'Requires the isolated device runtime lock.')
class DevicePrivateMediaTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.media = self.root / 'media'
        (self.media / 'contents').mkdir(parents=True)
        self.original = self.media / 'contents/original.pdf'
        self.original.write_bytes(b'%PDF-1.4 private original')
        static = self.root / 'collected-static'
        static.mkdir()
        (static / 'fixture.js').write_text('window.fixture=true;')
        self.override = override_settings(
            DEBUG=False, ROOT_URLCONF='dlms.device_urls', MEDIA_ROOT=str(self.media),
            STATIC_ROOT=str(static), WHITENOISE_USE_FINDERS=False, WHITENOISE_AUTOREFRESH=False,
            MIDDLEWARE=['dlms.preview_middleware.PrivatePreviewMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware'],
            OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=True,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client = APIClient()

    def test_collected_assets_and_originals_work_without_debug(self):
        for endpoint, contents in (('/static/fixture.js', b'window.fixture=true;'),
                                   ('/media/contents/original.pdf', self.original.read_bytes())):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b''.join(response.streaming_content), contents)
        response = self.client.get('/media/contents/original.pdf')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertTrue(response['Content-Disposition'].startswith('inline;'))
        self.assertEqual(response['Content-Security-Policy'], "sandbox; default-src 'none'")

    def test_uploaded_active_formats_download_in_a_scriptless_sandbox(self):
        for filename, contents in (('uploaded.html', '<script>window.attack=true</script>'),
                                   ('uploaded.svg', '<svg onload="window.attack=true"></svg>')):
            (self.media / 'contents' / filename).write_text(contents)
            response = self.client.get('/media/contents/' + filename)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(response['Content-Security-Policy'], "sandbox; default-src 'none'")
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            response.close()

    def test_remote_forwarded_and_cross_origin_requests_cannot_read_originals(self):
        for headers in ({'REMOTE_ADDR': '192.0.2.20', 'HTTP_X_FORWARDED_FOR': '127.0.0.1'},
                        {'HTTP_ORIGIN': 'https://outside.example'}, {'HTTP_SEC_FETCH_SITE': 'same-site'}):
            self.assertEqual(self.client.get('/media/contents/original.pdf', **headers).status_code, 403)
        self.assertEqual(self.client.get('/static/fixture.js', REMOTE_ADDR='192.0.2.20').status_code, 403)
        with override_settings(OASIS_CURATOR_ENABLED=False):
            self.assertEqual(self.client.get('/media/contents/original.pdf').status_code, 403)

    def test_paths_directories_and_symlink_files_do_not_expose_private_state(self):
        secret = self.root / 'private-secret'
        secret.write_text('must remain outside served media')
        (self.media / 'contents/linked.pdf').symlink_to(secret)
        (self.media / 'linked-directory').symlink_to(self.root, target_is_directory=True)
        for endpoint in ('/media/../private-secret', '/media/contents/linked.pdf',
                         '/media/linked-directory/private-secret', '/media/contents/',
                         '/media/contents/missing.pdf', '/builds/private-export.zip'):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 404, endpoint)


class DeviceIndexingEnvironmentTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.station = self.root / 'station-release'
        (self.station / 'scripts').mkdir(parents=True)
        for name in ('import_pdf_library.py', 'index_pdf_vectors.py'):
            (self.station / 'scripts' / name).write_text('# reviewed maintenance command\n')
        self.current = self.root / 'station-current'
        self.current.symlink_to(self.station, target_is_directory=True)
        self.deps = self.root / 'reviewed-deps'
        self.deps.mkdir()
        self.manifest = self.root / 'reviewed.json'
        self.manifest.write_text('{}')
        self.state = self.root / 'data/indexing'
        override = override_settings(OASIS_INDEXING_STATE_ROOT=str(self.state))
        override.enable()
        self.addCleanup(override.disable)
        environment = patch.dict(os.environ, {
            'OASIS_INDEXING_STATION_ROOT': str(self.current), 'OASIS_INDEXING_PYTHON': sys.executable,
            'OASIS_INDEXING_MANIFEST': str(self.manifest), 'OASIS_INDEXING_DEPENDENCY_PATH': str(self.deps),
            'PYTHONPATH': '/unreviewed/injected', 'PYTHONHOME': '/unreviewed/home',
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_explicit_dependencies_reach_probe_search_and_worker_without_injected_paths(self):
        config = operator_config()
        self.assertEqual(config['root'], self.station)
        expected = os.pathsep.join((str(self.station), str(self.deps)))
        environment = station_environment(config)
        self.assertEqual(environment['PYTHONPATH'], expected)
        self.assertNotIn('PYTHONHOME', environment)
        self.assertEqual(environment['PYTHONNOUSERSITE'], '1')
        job = SimpleNamespace(id=uuid.uuid4())
        with patch('content_management.oasis_indexing.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='{}')) as probe:
            run_probe(config, artifacts_only=True)
            self.assertEqual(probe.call_args.kwargs['env']['PYTHONPATH'], expected)
        with patch('content_management.oasis_search.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='{}')) as search:
            run_search(config, job, 'fixture', ['fixture'], 'lexical')
            self.assertEqual(search.call_args.kwargs['env']['PYTHONPATH'], expected)
        root = job_root(job)
        root.mkdir(parents=True)
        result = run_command([sys.executable, '-B', '-c', 'import os; print(os.environ["PYTHONPATH"])'], config, job, 'probe')
        self.assertEqual(result.strip(), expected)

    def test_indexing_jobs_stay_at_the_same_path_across_release_changes(self):
        job = SimpleNamespace(id=uuid.uuid4())
        before = job_root(job)
        before.mkdir(parents=True)
        (before / 'receipt.json').write_text('private draft receipt')
        with override_settings(BASE_DIR=self.root / 'new-code-release'):
            after = job_root(job)
        self.assertEqual(before, after)
        self.assertTrue((after / 'receipt.json').is_file())

    def test_untrusted_dependency_and_staging_paths_fail_before_subprocess(self):
        link = self.root / 'untrusted-deps'
        link.symlink_to(self.deps, target_is_directory=True)
        for value in ('relative/deps', str(link), str(self.root / 'missing')):
            with patch.dict(os.environ, {'OASIS_INDEXING_DEPENDENCY_PATH': value}):
                with self.assertRaises(ValueError):
                    operator_config()
        self.assertFalse((self.root / 'missing').exists())
        config = operator_config()
        config['dependency_path'] = str(self.root / 'missing-child-dependencies')
        with self.assertRaises(ValueError):
            station_environment(config)
        self.assertFalse((self.root / 'missing-child-dependencies').exists())
        self.state.mkdir(parents=True)
        (self.state / 'worker.lock').symlink_to(self.manifest)
        with self.assertRaisesMessage(ValueError, 'symlinks'):
            staging_base()

    def test_missing_station_release_is_unavailable_before_subprocess(self):
        self.current.unlink()
        self.current.symlink_to(self.root / 'missing-release', target_is_directory=True)
        with self.assertRaisesMessage(ValueError, 'station release root is unavailable'):
            operator_config()

    def test_invalid_maintenance_request_is_never_acknowledged(self):
        self.state.mkdir(parents=True)
        request = self.state / 'maintenance.json'
        for payload in ('not JSON', '{}', '{"nonce":"old"}', '["not a request"]'):
            request.write_text(payload)
            with self.assertRaises(ValueError):
                maintenance_request()

    def test_staging_destinations_cannot_overlap_station_originals_exports_or_evaluation(self):
        originals, exports, evaluation = (self.root / name for name in ('originals', 'exports', 'evaluation'))
        for destination in (self.station / 'drafts', originals / 'drafts', exports, evaluation / 'drafts', self.root):
            existed = destination.exists()
            with self.subTest(destination=destination), override_settings(
                OASIS_INDEXING_STATE_ROOT=str(destination), MEDIA_ROOT=str(originals), BUILDS_ROOT=str(exports),
                OASIS_INDEXING_PROTECTED_ROOTS=(str(evaluation),),
            ):
                with self.assertRaisesMessage(ValueError, 'must not overlap'):
                    staging_base()
            self.assertEqual(destination.exists(), existed)

    def test_passage_search_uses_configured_station_shared_source_limit(self):
        # Exercise the real adapter CLI with a bounded, offline station reader.
        library = self.station / 'app/library'
        library.mkdir(parents=True)
        (self.station / 'app/__init__.py').write_text('')
        (library / '__init__.py').write_text('')
        (library / 'index.py').write_text(
            'from pathlib import Path\nMAX_DOCUMENTS=128\n'
            'class PdfLibrary:\n'
            ' def __init__(self, root): self.available=True; self._snapshot=Path(root)\n'
            ' def search(self, query, sources, limit): return []\n'
            'def _load_manifest(path): return {"documents":[{"id":"source-"+str(i)} for i in range(129)]}\n'
        )
        (library / 'semantic.py').write_text('class SemanticSearch: pass\n')
        command = [sys.executable, '-B', str(REPOSITORY / 'scripts/search_oasis_index.py'),
                   '--station-root', str(self.station), '--root', str(self.root / 'draft'),
                   '--query', 'offline fixture', '--profile', 'lexical', '--sources']
        environment = station_environment(operator_config())
        for count, expected in ((51, 0), (128, 0), (129, 2)):
            with self.subTest(count=count):
                result = subprocess.run(command + [json.dumps(['source-' + str(i) for i in range(count)])],
                                        env=environment, cwd=REPOSITORY, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
