"""Mounted manager sessions and URLs, with disposable synthetic content only."""
import json
import importlib.util
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.http import HttpResponseNotFound
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from content_management.management.commands.seed_oasis_preview import sample_pdf
from content_management.models import Content, LibraryFolder, LibraryVersion
from content_management.test_curator_auth import MIDDLEWARE, TEMPLATES
from dlms.curator_config import manager_base_path, public_admin_origin


class ManagePrefixConfigurationTests(SimpleTestCase):
    def test_only_the_explicit_mount_and_box_origin_are_supported(self):
        self.assertEqual(manager_base_path(''), '')
        self.assertEqual(manager_base_path('/manage'), '/manage')
        self.assertEqual(public_admin_origin('https://box001.kuwala.space'), 'https://box001.kuwala.space')
        for value in (None, 'manage', '/manage/', '//manage', '/other', '/manage/../', '/manage?x=1'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                manager_base_path(value)
        for value in ('https://box001.kuwala.space/', 'http://box001.kuwala.space',
                      'https://box001.kuwala.space:443', 'https://box001.kuwala.space/manage',
                      'https://box001.kuwala.space.attacker.example', 'https://user@box001.kuwala.space'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                public_admin_origin(value)

    @skipUnless(importlib.util.find_spec('whitenoise'), 'WhiteNoise belongs to the separate pinned device runtime')
    def test_whitenoise_serves_only_the_configured_static_mount(self):
        from whitenoise.middleware import WhiteNoiseMiddleware
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / 'synthetic.js').write_bytes(b'window.syntheticPrefixFixture = true;')
            with override_settings(STATIC_ROOT=str(root), STATIC_URL='/manage/static/',
                                   WHITENOISE_USE_FINDERS=False, WHITENOISE_AUTOREFRESH=False,
                                   FORCE_SCRIPT_NAME=None):
                serve = WhiteNoiseMiddleware(lambda request: HttpResponseNotFound())
                response = serve(RequestFactory().get('/manage/static/synthetic.js'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'window.syntheticPrefixFixture = true;')
                response.close()
                self.assertEqual(serve(RequestFactory().get('/static/synthetic.js')).status_code, 404)


@override_settings(ROOT_URLCONF='dlms.prefixed_device_urls', MIDDLEWARE=MIDDLEWARE, TEMPLATES=TEMPLATES,
                   ALLOWED_HOSTS=['testserver', '127.0.0.1', 'box001.kuwala.space'],
                   OASIS_DEVICE_BASE_PATH='/manage', OASIS_CURATOR_ENABLED=True,
                   OASIS_LOOPBACK_ONLY=True, OASIS_REQUIRE_CURATOR_AUTH=True,
                   OASIS_DEVICE_ADMIN_ORIGIN='', OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='https://box001.kuwala.space',
                   LOGIN_URL='oasis-login', LOGIN_REDIRECT_URL='/manage/?workspace=curator&tab=contents',
                   STATIC_URL='/manage/static/', MEDIA_URL='/manage/media/', CONTENTS_URL='/manage/media/contents/',
                   SESSION_COOKIE_NAME='oasis_curator_session', CSRF_COOKIE_NAME='oasis_curator_csrf',
                   SESSION_COOKIE_PATH='/manage/', CSRF_COOKIE_PATH='/manage/',
                   SESSION_COOKIE_HTTPONLY=True, CSRF_COOKIE_HTTPONLY=True,
                   SESSION_COOKIE_SAMESITE='Strict', CSRF_COOKIE_SAMESITE='Strict')
class MountedManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username='synthetic-prefix-admin', password='Test-prefix-session!729', is_staff=True)
        cls.visitor = get_user_model().objects.create_user(
            username='synthetic-prefix-visitor', password='Test-prefix-session!729')
        cls.version = LibraryVersion.objects.create(library_name='Synthetic prefix catalogue', version_number='prefix-fixture-v1')
        cls.library = LibraryFolder.objects.create(folder_name='Synthetic prefix library', version=cls.version)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'media/contents').mkdir(parents=True)
        self.state = override_settings(MEDIA_ROOT=str(self.root / 'media'),
            CONTENTS_ROOT=str(self.root / 'media/contents'), BUILDS_ROOT=str(self.root / 'builds'))
        self.state.enable()
        self.addCleanup(self.state.disable)
        self.client = APIClient(enforce_csrf_checks=True)
        self.host = {'HTTP_HOST': 'box001.kuwala.space', 'HTTP_X_FORWARDED_PROTO': 'https'}

    def sign_in(self, next_path=None):
        response = self.client.get('/manage/accounts/login/', **self.host)
        self.assertEqual(response.status_code, 200, response.content)
        token = response.cookies[settings.CSRF_COOKIE_NAME].value
        payload = {'username': self.staff.username, 'password': 'Test-prefix-session!729'}
        if next_path is not None:
            payload['next'] = next_path
        return self.client.post('/manage/accounts/login/', payload,
            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://box001.kuwala.space', **self.host)

    def csrf(self):
        return self.client.get('/manage/api/get_csrf/', **self.host).json()['data']

    def test_bare_mount_redirect_preserves_query_and_refuses_write_redirects(self):
        for method in ('get', 'head'):
            response = getattr(self.client, method)('/manage?library=18&tab=contents', **self.host)
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response['Location'], '/manage/?library=18&tab=contents')
        self.assertIn(self.client.post('/manage', {}, **self.host).status_code, (403, 405))

    def test_login_forms_icons_and_anonymous_routes_stay_mounted(self):
        response = self.client.get('/manage/?workspace=curator&tab=contents', **self.host)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/manage/accounts/login/?next='))
        login = self.client.get('/manage/accounts/login/', **self.host)
        self.assertContains(login, 'action="/manage/accounts/login/"')
        self.assertContains(login, 'src="/manage/static/images/kuwala-oasis.svg"')
        self.assertContains(login, 'href="/manage/static/images/favicon.svg"')
        for path in ('/manage/api/oasis/config/', '/manage/api/contents/', '/manage/api/library_versions/',
                     '/manage/api/get_csrf/', '/manage/media/contents/original.pdf',
                     '/manage/api/oasis/libraries/import/', '/manage/api/create_build/6/'):
            for method in ('get', 'head'):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, **self.host)
                    self.assertEqual(response.status_code, 401)
                    if method == 'get':
                        self.assertIsNone(response.json()['data'])
                    else:
                        self.assertEqual(response.content, b'')
        for path in ('/', '/accounts/login/', '/api/oasis/config/', '/media/contents/original.pdf'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **self.host).status_code, 404)

    def test_login_and_logout_scope_secure_cookies_to_manage(self):
        response = self.sign_in()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/manage/?workspace=curator&tab=contents')
        for name in (settings.CSRF_COOKIE_NAME, settings.SESSION_COOKIE_NAME):
            cookie = self.client.cookies[name]
            self.assertEqual(cookie['path'], '/manage/')
            self.assertEqual(cookie['domain'], '')
            self.assertTrue(cookie['secure'] and cookie['httponly'])
            self.assertEqual(cookie['samesite'], 'Strict')
        self.assertEqual(self.client.get('/manage/api/oasis/config/', **self.host).status_code, 200)
        self.assertEqual(self.client.get('/manage/accounts/logout/', **self.host).status_code, 405)
        self.assertEqual(self.client.post('/manage/accounts/logout/', {}, **self.host).status_code, 403)
        response = self.client.post('/manage/accounts/logout/', {}, HTTP_X_CSRFTOKEN=self.csrf(),
            HTTP_ORIGIN='https://box001.kuwala.space', **self.host)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/manage/accounts/login/')
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['path'], '/manage/')
        self.assertEqual(self.client.get('/manage/api/oasis/config/', **self.host).status_code, 401)

    def test_login_next_cannot_escape_manager_and_preserves_selected_document(self):
        for next_path in ('/', '/api/oasis/config/', '//attacker.example/manage/', 'https://attacker.example/',
                          '/manage/../api/', '/manage/%2e%2e/api/'):
            with self.subTest(next_path=next_path):
                self.client = APIClient(enforce_csrf_checks=True)
                response = self.sign_in(next_path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], '/manage/?workspace=curator&tab=contents')
        self.client = APIClient(enforce_csrf_checks=True)
        response = self.sign_in('/manage/?version=6&library=18&document=92')
        self.assertEqual(response['Location'], '/manage/?version=6&library=18&document=92')

    def test_prefixed_upload_edit_original_export_and_delete_keep_stable_ids(self):
        self.assertEqual(self.sign_in().status_code, 302)
        headers = {'HTTP_X_CSRFTOKEN': self.csrf(), 'HTTP_ORIGIN': 'https://box001.kuwala.space', **self.host}
        original = sample_pdf('Synthetic prefix upload; no technical advice')
        response = self.client.post('/manage/api/oasis/documents/', {
            'title': 'Synthetic prefix original', 'rights_statement': 'Synthetic test only',
            'content_file': ContentFile(original, name='synthetic-prefix.pdf'),
            'catalogue_version': str(self.version.pk), 'folder_ids': json.dumps([self.library.pk]),
        }, format='multipart', **headers)
        self.assertEqual(response.status_code, 201, response.content)
        item = response.json()['data']
        document_id = item['id']
        self.assertIn('/manage/media/contents/synthetic-prefix.pdf', item['content_file'])
        self.assertEqual(self.client.get('/manage/api/oasis/documents/%s/' % document_id, **self.host).json()['data']['id'], document_id)
        media = self.client.get('/manage/media/contents/synthetic-prefix.pdf', **self.host)
        self.assertEqual(media.status_code, 200)
        self.assertEqual(b''.join(media.streaming_content), original)
        response = self.client.patch('/manage/api/oasis/documents/%s/' % document_id,
            {'display_title': 'Renamed synthetic prefix record'}, format='json', **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['data']['id'], document_id)
        export = self.client.get('/manage/api/oasis/libraries/%s/bundle/' % self.library.pk, **self.host)
        self.assertEqual(export.status_code, 200, export.content if not export.streaming else '')
        self.assertEqual(export['Content-Type'], 'application/zip')
        export.close()
        response = self.client.delete('/manage/api/oasis/documents/%s/' % document_id, **headers)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Content.objects.filter(pk=document_id).exists())

    def test_password_change_and_return_links_are_prefixed(self):
        self.assertEqual(self.sign_in().status_code, 302)
        page = self.client.get('/manage/accounts/password-change/', **self.host)
        self.assertContains(page, 'href="/manage/?workspace=curator&amp;tab=contents"')
        response = self.client.post('/manage/accounts/password-change/', {
            'old_password': 'Test-prefix-session!729', 'new_password1': 'New-prefix-session!891',
            'new_password2': 'New-prefix-session!891'}, HTTP_X_CSRFTOKEN=self.csrf(),
            HTTP_ORIGIN='https://box001.kuwala.space', **self.host)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/manage/accounts/password-change/done/')
        self.assertEqual(self.client.get('/manage/api/oasis/config/', **self.host).status_code, 200)

    def test_csrf_remote_peer_and_wrong_origin_denials_survive_mounting(self):
        self.assertEqual(self.sign_in().status_code, 302)
        token = self.csrf()
        for origin in ('https://outside.example', 'http://box001.kuwala.space', 'https://manage.kuwala.space'):
            self.assertEqual(self.client.post('/manage/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                HTTP_ORIGIN=origin, **self.host).status_code, 403)
        self.assertEqual(self.client.post('/manage/api/oasis/documents/', {}, **self.host).status_code, 403)
        self.assertEqual(self.client.get('/manage/api/oasis/config/', REMOTE_ADDR='192.0.2.1',
            HTTP_X_FORWARDED_FOR='127.0.0.1', **self.host).status_code, 403)
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.get('/manage/api/oasis/config/', **self.host).status_code, 403)

    def test_minimal_health_and_reversed_original_page_route_use_mount(self):
        response = self.client.get('/manage/healthz', **self.host)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'ready': True, 'authentication_required': True})
        self.assertEqual(reverse('oasis-draft-original', args=('00000000-0000-0000-0000-000000000001', 2)),
            '/manage/api/oasis/index-search/original/00000000-0000-0000-0000-000000000001/2/')
