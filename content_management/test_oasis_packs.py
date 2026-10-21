"""Only normal staff sessions and CSRF may reach the fixed pack controller."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content_management.test_curator_auth import MIDDLEWARE, TEMPLATES


@override_settings(ROOT_URLCONF='dlms.device_urls', MIDDLEWARE=MIDDLEWARE, TEMPLATES=TEMPLATES,
    ALLOWED_HOSTS=['testserver'], OASIS_CURATOR_ENABLED=True, OASIS_LOOPBACK_ONLY=True,
    OASIS_REQUIRE_CURATOR_AUTH=True, OASIS_DEVICE_ADMIN_ORIGIN='', OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN='',
    LOGIN_URL='/accounts/login/', SESSION_COOKIE_NAME='oasis_curator_session', CSRF_COOKIE_NAME='oasis_curator_csrf')
class PackControlTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        get_user_model().objects.create_user(username='pack-test-staff', password='Synthetic-test-only!29', is_staff=True)

    def sign_in(self):
        token = self.client.get('/accounts/login/').cookies['oasis_curator_csrf'].value
        response = self.client.post('/accounts/login/', {'username': 'pack-test-staff', 'password': 'Synthetic-test-only!29'}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 302)
        return self.client.get('/api/get_csrf/').json()['data']

    @patch('content_management.oasis_packs.control')
    def test_anonymous_cannot_read_or_install(self, control):
        self.assertEqual(self.client.get('/api/oasis/packs/').status_code, 401)
        self.assertIn(self.client.post('/api/oasis/packs/', {'action': 'refresh'}, format='json').status_code, (401, 403))
        control.assert_not_called()

    @patch('content_management.oasis_packs.control', return_value={'configured': True, 'packs': []})
    def test_staff_read_is_bounded_and_valid_install_uses_fixed_command(self, control):
        token = self.sign_in()
        self.assertEqual(self.client.get('/api/oasis/packs/?page=2').status_code, 200)
        control.assert_called_with({'action': 'catalogue', 'page': 2})
        body = {'action': 'install', 'pack_ids': ['malawi-farming'], 'publication_sha256': 'a' * 64, 'request_id': 'install-fixture'}
        response = self.client.post('/api/oasis/packs/', body, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)
        control.assert_called_with(body)

    @patch('content_management.oasis_packs.control')
    def test_csrf_and_cross_origin_write_rejected_before_socket(self, control):
        token = self.sign_in()
        control.reset_mock()
        self.assertEqual(self.client.post('/api/oasis/packs/', {'action': 'refresh'}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/oasis/packs/', {'action': 'refresh'}, format='json',
            HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://outside.example').status_code, 403)
        control.assert_not_called()

    @patch('content_management.oasis_packs.control')
    def test_arbitrary_paths_urls_shells_and_unbounded_catalogue_pages_are_refused(self, control):
        token = self.sign_in()
        control.reset_mock()
        for body in ({'action': 'refresh', 'url': 'https://outside.example'}, {'action': 'install', 'path': '/tmp'}, {'action': 'exec', 'command': 'id'}):
            self.assertEqual(self.client.post('/api/oasis/packs/', body, format='json', HTTP_X_CSRFTOKEN=token).status_code, 400)
        self.assertEqual(self.client.get('/api/oasis/packs/?page=99').status_code, 400)
        self.assertEqual(self.client.get('/api/oasis/packs/?path=/tmp').status_code, 400)
        control.assert_not_called()

    @patch('content_management.oasis_packs.control', side_effect=ValueError('Fixed local service unavailable'))
    def test_unavailable_installer_is_explicit_and_does_not_report_an_install(self, control):
        token = self.sign_in()
        response = self.client.get('/api/oasis/packs/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['data']['configured'])
        response = self.client.post('/api/oasis/packs/', {'action': 'refresh'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['success'])
