"""Private device staff-session access and fixed HTTPS proxy boundaries."""
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, SimpleTestCase, override_settings
from rest_framework.test import APIClient

from dlms.curator_config import admin_origin, public_admin_origin


MIDDLEWARE = [
    'dlms.curator_auth.CuratorProxyOriginMiddleware',
    'dlms.preview_middleware.PrivatePreviewMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'dlms.curator_auth.CuratorSessionMiddleware',
]
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [str(Path(__file__).resolve().parent.parent / 'templates')],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                                      'django.contrib.auth.context_processors.auth']},
}]


@override_settings(ROOT_URLCONF='dlms.device_urls', MIDDLEWARE=MIDDLEWARE, TEMPLATES=TEMPLATES,
                   ALLOWED_HOSTS=['testserver', '127.0.0.1', 'kuwala001.tailc01a0e.ts.net', 'manage.kuwala.space'],
                   OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=True,
                   OASIS_REQUIRE_CURATOR_AUTH=True, OASIS_DEVICE_ADMIN_ORIGIN='', OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='',
                   LOGIN_URL='/accounts/login/', LOGIN_REDIRECT_URL='/?workspace=curator&tab=contents',
                   SESSION_COOKIE_NAME='oasis_curator_session', CSRF_COOKIE_NAME='oasis_curator_csrf',
                   SESSION_COOKIE_HTTPONLY=True, CSRF_COOKIE_HTTPONLY=True,
                   SESSION_COOKIE_SAMESITE='Strict', CSRF_COOKIE_SAMESITE='Strict')
class CuratorSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username='fixture-admin', password='Test-private-login!712', is_staff=True)
        cls.nonstaff = get_user_model().objects.create_user(username='fixture-visitor', password='Test-private-login!712')

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def token(self, **headers):
        response = self.client.get('/accounts/login/', **headers)
        self.assertEqual(response.status_code, 200)
        return response.cookies[settings.CSRF_COOKIE_NAME].value

    def sign_in(self, username='fixture-admin', **headers):
        token = self.token(**headers)
        return self.client.post('/accounts/login/', {'username': username, 'password': 'Test-private-login!712'},
                                HTTP_X_CSRFTOKEN=token, **headers)

    def test_anonymous_shell_redirect_and_all_management_reads_denied(self):
        response = self.client.get('/?workspace=curator&tab=contents')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/accounts/login/?next='))
        for path in ['/api/oasis/config/', '/api/contents/', '/api/library_versions/', '/api/metadata/',
                     '/api/oasis/catalogue/', '/api/oasis/catalogue/documents/', '/api/oasis/documents/',
                     '/api/oasis/indexing/', '/api/oasis/index-search/', '/api/oasis/index-jobs/',
                     '/api/oasis/index-search/original/00000000-0000-0000-0000-000000000001/1/',
                     '/api/contents.json', '/api/spreadsheet/metadata/fixture',
                     '/api/get_csrf/', '/api/create_build/6/', '/api/library_versions/6/clone/',
                     '/media/contents/fixture.pdf']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertIsNone(response.json()['data'])
                self.assertEqual(self.client.head(path).status_code, 401)

    def test_anonymous_mutations_denied_even_with_valid_csrf(self):
        token = self.token()
        for method, path in [('post', '/api/oasis/documents/'), ('patch', '/api/contents/1/'),
                             ('delete', '/api/library_folders/16/'), ('post', '/api/oasis/index-jobs/'),
                             ('post', '/api/contents_upload/')]:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, {}, HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 401)

    def test_staff_session_can_read_catalogue_and_private_original(self):
        self.assertEqual(self.sign_in().status_code, 302)
        self.assertEqual(self.client.get('/api/oasis/config/').json()['data']['curator_enabled'], True)
        self.assertEqual(self.client.get('/api/oasis/documents/').status_code, 200)
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            root = Path(directory).resolve()
            path = root / 'contents'; path.mkdir(); (path / 'fixture.pdf').write_bytes(b'%PDF-1.4 fixture')
            with override_settings(MEDIA_ROOT=str(root)):
                response = self.client.get('/media/contents/fixture.pdf')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4 fixture')
        self.assertEqual(self.client.get('/api/oasis/documents/', HTTP_ORIGIN='https://outside.example').status_code, 403)

    def test_nonstaff_and_inactive_accounts_cannot_sign_in_or_manage(self):
        self.assertEqual(self.sign_in('fixture-visitor').status_code, 200)
        self.assertEqual(self.client.get('/api/oasis/documents/').status_code, 401)
        self.client.force_login(self.nonstaff)
        self.assertEqual(self.client.get('/api/oasis/config/').status_code, 403)
        self.staff.is_active = False; self.staff.save(update_fields=['is_active'])
        self.client.logout()
        self.assertEqual(self.sign_in().status_code, 200)
        self.assertEqual(self.client.get('/api/oasis/config/').status_code, 401)

    def test_csrf_required_for_login_logout_and_authenticated_mutations(self):
        self.assertEqual(self.client.post('/accounts/login/', {'username': 'fixture-admin', 'password': 'Test-private-login!712'}).status_code, 403)
        self.assertEqual(self.sign_in().status_code, 302)
        self.assertEqual(self.client.post('/api/oasis/documents/', {}).status_code, 403)
        self.assertEqual(self.client.post('/accounts/logout/', {}).status_code, 403)
        token = self.client.get('/api/get_csrf/').json()['data']
        self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token).status_code, 400)

    def test_external_next_does_not_redirect_and_logout_is_post_only(self):
        token = self.token()
        response = self.client.post('/accounts/login/', {'username': 'fixture-admin', 'password': 'Test-private-login!712',
                                                        'next': 'https://outside.example/'}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/?workspace=curator&tab=contents')
        self.assertEqual(self.client.get('/accounts/logout/').status_code, 405)
        token = self.client.get('/api/get_csrf/').json()['data']
        self.assertEqual(self.client.post('/accounts/logout/', {}, HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertEqual(self.client.get('/api/oasis/config/').status_code, 401)

    def test_password_change_uses_standard_validation_and_keeps_current_session(self):
        self.assertEqual(self.sign_in().status_code, 302)
        token = self.client.get('/api/get_csrf/').json()['data']
        response = self.client.post('/accounts/password-change/', {'old_password': 'Test-private-login!712',
                                    'new_password1': 'A-new-private-password!893', 'new_password2': 'A-new-private-password!893'},
                                    HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('A-new-private-password!893'))
        self.assertEqual(self.client.get('/api/oasis/config/').status_code, 200)

    def test_health_is_minimal_and_remote_headers_never_grant_loopback(self):
        response = self.client.get('/healthz')
        self.assertEqual(response.json(), {'success': True, 'data': {'ready': True, 'authentication_required': True}, 'error': None})
        self.assertEqual(self.client.get('/healthz', REMOTE_ADDR='192.0.2.1', HTTP_X_FORWARDED_FOR='127.0.0.1').status_code, 403)
        self.assertEqual(self.client.get('/accounts/login/', REMOTE_ADDR='192.0.2.1').status_code, 403)

    def test_private_account_screens_share_decorative_logo_and_local_icons(self):
        login = self.client.get('/accounts/login/')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.sign_in().status_code, 302)
        for response in [login, self.client.get('/accounts/password-change/'),
                         self.client.get('/accounts/password-change/done/')]:
            with self.subTest(path=response.wsgi_request.path):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<img src="/static/images/kuwala-oasis.svg" alt="" aria-hidden="true" width="40" height="40">')
                self.assertContains(response, '<strong>Oasis Knowledge</strong>')
                for name in ['favicon.ico', 'favicon-32.png', 'favicon.svg', 'apple-touch-icon.png']:
                    self.assertContains(response, 'href="/static/images/' + name + '"')
                self.assertNotContains(response, '/static/images/oasis-library.svg')

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443')
    def test_exact_trusted_https_origin_cookie_security_and_csrf(self):
        host = {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https'}
        token = self.token(**host)
        self.assertTrue(self.client.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        self.assertTrue(self.client.cookies[settings.CSRF_COOKIE_NAME]['httponly'])
        response = self.client.post('/accounts/login/', {'username': 'fixture-admin', 'password': 'Test-private-login!712'},
                                    HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443', **host)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['httponly'])
        token = self.client.get('/api/get_csrf/', **host).json()['data']
        self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                                        HTTP_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443', **host).status_code, 400)
        self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                                        HTTP_ORIGIN='https://kuwala001.tailc01a0e.ts.net', **host).status_code, 403)
        self.assertEqual(self.client.get('/api/oasis/config/', HTTP_SEC_FETCH_SITE='same-site', **host).status_code, 403)

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443')
    def test_untrusted_protocol_host_and_forwarded_addresses_rejected(self):
        for headers in [
            {'HTTP_X_FORWARDED_PROTO': 'https'},
            {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443'},
            {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'http'},
            {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https,http'},
            {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https', 'REMOTE_ADDR': '192.0.2.1',
             'HTTP_X_FORWARDED_FOR': '127.0.0.1'},
            {'HTTP_X_FORWARDED_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https'},
        ]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get('/accounts/login/', **headers).status_code, 403)

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443',
                       OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='https://manage.kuwala.space')
    def test_both_https_origins_keep_staff_login_secure_cookies_and_csrf(self):
        origins = ('https://kuwala001.tailc01a0e.ts.net:8443', 'https://manage.kuwala.space')
        for origin in origins:
            with self.subTest(origin=origin):
                self.client = APIClient(enforce_csrf_checks=True)
                host = {'HTTP_HOST': origin.removeprefix('https://'), 'HTTP_X_FORWARDED_PROTO': 'https'}
                token = self.token(**host)
                csrf_cookie = self.client.cookies[settings.CSRF_COOKIE_NAME]
                self.assertTrue(csrf_cookie['secure'])
                self.assertTrue(csrf_cookie['httponly'])
                self.assertEqual(csrf_cookie['samesite'], 'Strict')
                self.assertEqual(csrf_cookie['domain'], '')
                response = self.client.post('/accounts/login/',
                                            {'username': 'fixture-admin', 'password': 'Test-private-login!712'},
                                            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN=origin, **host)
                self.assertEqual(response.status_code, 302)
                session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
                self.assertTrue(session_cookie['secure'])
                self.assertTrue(session_cookie['httponly'])
                self.assertEqual(session_cookie['samesite'], 'Strict')
                self.assertEqual(session_cookie['domain'], '')
                self.assertEqual(self.client.get('/api/oasis/documents/', **host).status_code, 200)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    (root / 'contents').mkdir()
                    original = b'%PDF-1.4 unchanged private fixture'
                    (root / 'contents/fixture.pdf').write_bytes(original)
                    with override_settings(MEDIA_ROOT=str(root)):
                        response = self.client.get('/media/contents/fixture.pdf', **host)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(b''.join(response.streaming_content), original)
                        self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertEqual(self.client.post('/api/oasis/documents/', {}, **host).status_code, 403)
                token = self.client.get('/api/get_csrf/', **host).json()['data']
                self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                                                 HTTP_ORIGIN=origin, **host).status_code, 400)
                other_origin = next(value for value in origins if value != origin)
                self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                                                 HTTP_ORIGIN=other_origin, **host).status_code, 403)
                for endpoint in ('/api/oasis/documents/', '/api/create_build/6/', '/media/contents/fixture.pdf'):
                    self.assertEqual(self.client.get(endpoint, HTTP_ORIGIN=other_origin, **host).status_code, 403)
                self.assertEqual(self.client.get('/api/oasis/config/', HTTP_SEC_FETCH_SITE='same-site', **host).status_code, 403)
                self.assertEqual(self.client.post('/accounts/logout/', {}, HTTP_X_CSRFTOKEN=token,
                                                 HTTP_ORIGIN=origin, **host).status_code, 302)
                self.assertEqual(self.client.get('/api/oasis/documents/', **host).status_code, 401)

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443')
    def test_public_proxy_origin_is_rejected_until_explicitly_enabled(self):
        self.assertEqual(self.client.get('/accounts/login/', HTTP_HOST='manage.kuwala.space',
                                        HTTP_X_FORWARDED_PROTO='https').status_code, 403)
        private = {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https'}
        self.assertEqual(self.sign_in(HTTP_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443', **private).status_code, 302)
        self.assertEqual(self.client.get('/api/oasis/documents/', **private).status_code, 200)

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443',
                       OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='https://manage.kuwala.space')
    def test_public_proxy_rejects_missing_wrong_and_forwarded_signals(self):
        host = {'HTTP_HOST': 'manage.kuwala.space', 'HTTP_X_FORWARDED_PROTO': 'https'}
        for headers in [
            {'HTTP_HOST': 'manage.kuwala.space'},
            {**host, 'HTTP_X_FORWARDED_PROTO': 'http'},
            {**host, 'HTTP_X_FORWARDED_PROTO': 'https,http'},
            {**host, 'HTTP_HOST': 'manage.kuwala.space:443'},
            {**host, 'HTTP_HOST': 'manage.kuwala.space:8443'},
            {**host, 'REMOTE_ADDR': '192.0.2.1', 'HTTP_X_FORWARDED_FOR': '127.0.0.1'},
            {'HTTP_X_FORWARDED_HOST': 'manage.kuwala.space', 'HTTP_X_FORWARDED_PROTO': 'https'},
        ]:
            with self.subTest(headers=headers):
                self.assertEqual(self.client.get('/accounts/login/', **headers).status_code, 403)

    @override_settings(OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='https://manage.kuwala.space')
    def test_public_https_proxy_does_not_grant_anonymous_or_nonstaff_access(self):
        host = {'HTTP_HOST': 'manage.kuwala.space', 'HTTP_X_FORWARDED_PROTO': 'https'}
        endpoints = ('/api/oasis/documents/', '/api/create_build/6/', '/api/library_versions/6/clone/',
                     '/media/contents/fixture.pdf', '/api/spreadsheet/metadata/fixture')
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, **host)
                self.assertEqual(response.status_code, 401)
                self.assertIsNone(response.json()['data'])
        token = self.token(**host)
        self.assertEqual(self.client.post('/api/oasis/documents/', {}, HTTP_X_CSRFTOKEN=token,
                                         HTTP_ORIGIN='https://manage.kuwala.space', **host).status_code, 401)
        self.assertEqual(self.sign_in('fixture-visitor', HTTP_ORIGIN='https://manage.kuwala.space', **host).status_code, 200)
        self.client.force_login(self.nonstaff)
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint, **host).status_code, 403)

    @override_settings(OASIS_DEVICE_ADMIN_ORIGIN='https://kuwala001.tailc01a0e.ts.net:8443', TEMPLATES=[{
        **TEMPLATES[0], 'APP_DIRS': False, 'OPTIONS': {**TEMPLATES[0]['OPTIONS'], 'loaders': [
            ('django.template.loaders.locmem.Loader', {'index.html': '<title>Oasis Library</title>{% include "curator/session_controls.html" %}'}),
            'django.template.loaders.filesystem.Loader',
        ]},
    }])
    def test_cross_port_top_level_navigation_allowed_but_private_reads_remain_same_origin(self):
        self.client.force_login(self.staff)
        headers = {'HTTP_HOST': 'kuwala001.tailc01a0e.ts.net:8443', 'HTTP_X_FORWARDED_PROTO': 'https',
                   'HTTP_REFERER': 'https://kuwala001.tailc01a0e.ts.net/library',
                   'HTTP_SEC_FETCH_SITE': 'same-site', 'HTTP_SEC_FETCH_MODE': 'navigate', 'HTTP_SEC_FETCH_DEST': 'document'}
        for endpoint in ['/?workspace=curator&tab=contents', '/accounts/password-change/', '/accounts/password-change/done/']:
            self.assertEqual(self.client.get(endpoint, **headers).status_code, 200)
        for endpoint in ['/api/oasis/config/', '/api/contents/', '/api/create_build/6/',
                         '/api/library_versions/6/clone/', '/media/contents/fixture.pdf']:
            self.assertEqual(self.client.get(endpoint, **headers).status_code, 403)
        self.assertEqual(self.client.get('/', **{**headers, 'HTTP_SEC_FETCH_MODE': 'cors'}).status_code, 403)

    @override_settings(OASIS_REQUIRE_CURATOR_AUTH=False)
    def test_development_preview_retains_existing_anonymous_behavior(self):
        self.assertEqual(self.client.get('/api/oasis/config/').status_code, 200)
        self.assertEqual(self.client.get('/api/oasis/documents/').status_code, 200)


class CuratorOriginConfigurationTests(SimpleTestCase):
    def test_public_origin_requires_the_single_exact_protected_hostname(self):
        self.assertEqual(public_admin_origin(''), '')
        self.assertEqual(public_admin_origin('https://manage.kuwala.space'), 'https://manage.kuwala.space')
        for value in (None, False, 0, b'https://manage.kuwala.space', '*', 'https://*.kuwala.space',
                      'http://manage.kuwala.space', 'https://manage.kuwala.space:443',
                      'https://manage.kuwala.space:8443', 'https://manage.kuwala.space/',
                      'https://manage.kuwala.space.evil.example', 'https://oasis.kuwala.space',
                      'https://user@manage.kuwala.space', 'https://manage.kuwala.space?q=a',
                      'https://manage.kuwala.space#x', 'https://MANAGE.kuwala.space',
                      ' https://manage.kuwala.space', 'https://manage.kuwala.space\n'):
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                public_admin_origin(value)

    def test_only_one_canonical_private_tailnet_origin_is_accepted(self):
        self.assertEqual(admin_origin(''), '')
        self.assertEqual(admin_origin('https://kuwala001.tailc01a0e.ts.net:8443'), 'https://kuwala001.tailc01a0e.ts.net:8443')
        for value in ['*', 'https://*.ts.net:8443', 'http://kuwala001.tailc01a0e.ts.net:8443',
                      'https://kuwala001.tailc01a0e.ts.net', 'https://kuwala001.tailc01a0e.ts.net:443',
                      'https://oasis.kuwala.space:8443', 'https://kuwala001.tailc01a0e.ts.net:8443/',
                      'https://user@kuwala001.tailc01a0e.ts.net:8443', 'https://kuwala001.tailc01a0e.ts.net:8443?q=a',
                      'https://kuwala001.tailc01a0e.ts.net:8443#x', 'https://KUWALA001.tailc01a0e.ts.net:8443',
                      ' https://kuwala001.tailc01a0e.ts.net:8443', 'https://kuwala001.\ntailc01a0e.ts.net:8443']:
            with self.subTest(value=value), self.assertRaises(ImproperlyConfigured):
                admin_origin(value)
