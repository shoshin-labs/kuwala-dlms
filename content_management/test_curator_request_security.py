"""Browser request protections for anonymous, private curator development."""
from types import ModuleType

from django.test import SimpleTestCase, override_settings
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.viewsets import ViewSet

from content_management.views import get_csrf


@api_view(['POST'])
def anonymous_mutation(request):
    return Response({'accepted': True})


@api_view(['GET'])
def export_read(request):
    return Response({'accepted': True})


class LegacyCloneView(ViewSet):
    def clone(self, request):
        return Response({'accepted': True})


URLCONF = ModuleType('curator_request_security_urls')
URLCONF.urlpatterns = [
    path('api/get_csrf/', get_csrf),
    path('api/mutate/', anonymous_mutation),
    path('api/create_build/1/', export_read, name='create-build'),
    path('api/clone/', LegacyCloneView.as_view({'get': 'clone'})),
]


@override_settings(
    ROOT_URLCONF=URLCONF,
    MIDDLEWARE=[
        'dlms.preview_middleware.PrivatePreviewMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
    ],
    ALLOWED_HOSTS=['testserver'],
    OASIS_CURATOR_ENABLED=True,
    OASIS_LOOPBACK_ONLY=True,
)
class CuratorRequestSecurityTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def token(self):
        response = self.client.get('/api/get_csrf/')
        self.assertEqual(response.status_code, 200)
        return response.json()['data']

    def test_anonymous_drf_requires_csrf_cookie_and_token(self):
        self.assertTrue(anonymous_mutation.csrf_exempt)
        self.assertEqual(self.client.post('/api/mutate/', {}).status_code, 403)
        token = self.token()
        self.assertEqual(self.client.post('/api/mutate/', {}).status_code, 403)
        self.assertEqual(self.client.post('/api/mutate/', {}, HTTP_X_CSRFTOKEN='invalid').status_code, 403)
        self.assertEqual(self.client.post('/api/mutate/', {}, HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_same_origin_browser_write_with_valid_token(self):
        response = self.client.post('/api/mutate/', {}, HTTP_X_CSRFTOKEN=self.token(),
                                    HTTP_ORIGIN='http://testserver',
                                    HTTP_REFERER='http://testserver/?tab=manage',
                                    HTTP_SEC_FETCH_SITE='same-origin')
        self.assertEqual(response.status_code, 200)

    def test_cross_origin_browser_writes_rejected_even_with_valid_token(self):
        token = self.token()
        for headers in (
            {'HTTP_ORIGIN': 'https://outside.example'},
            {'HTTP_ORIGIN': 'null'},
            {'HTTP_ORIGIN': 'http://testserver:8791'},
            {'HTTP_REFERER': 'https://outside.example/form'},
            {'HTTP_SEC_FETCH_SITE': 'cross-site'},
            {'HTTP_SEC_FETCH_SITE': 'same-site'},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post('/api/mutate/', {}, HTTP_X_CSRFTOKEN=token, **headers).status_code, 403)

    def test_cross_origin_legacy_mutating_get_and_head_rejected(self):
        for endpoint in ('/api/create_build/1/', '/api/clone/'):
            for method in ('get', 'head'):
                for headers in (
                    {'HTTP_ORIGIN': 'https://outside.example'},
                    {'HTTP_REFERER': 'https://outside.example/link'},
                    {'HTTP_SEC_FETCH_SITE': 'cross-site'},
                ):
                    with self.subTest(endpoint=endpoint, method=method, headers=headers):
                        self.assertEqual(getattr(self.client, method)(endpoint, **headers).status_code, 403)

    def test_legacy_same_origin_and_local_cli_reads_remain_available(self):
        for endpoint in ('/api/create_build/1/', '/api/clone/'):
            self.assertEqual(self.client.get(endpoint).status_code, 200)
            self.assertEqual(self.client.get(endpoint, HTTP_REFERER='http://testserver/?tab=manage',
                                             HTTP_SEC_FETCH_SITE='same-origin').status_code, 200)

    def test_standard_django_test_client_retains_explicit_csrf_bypass(self):
        self.assertEqual(APIClient().post('/api/mutate/', {}).status_code, 200)

    @override_settings(OASIS_CURATOR_ENABLED=False)
    def test_visitor_cannot_mutate_even_with_valid_csrf(self):
        self.assertEqual(self.client.post('/api/mutate/', {}, HTTP_X_CSRFTOKEN=self.token()).status_code, 403)
        self.assertEqual(self.client.get('/api/create_build/1/').status_code, 403)
        self.assertEqual(self.client.head('/api/clone/').status_code, 403)

    def test_forwarded_loopback_never_grants_remote_access(self):
        self.assertEqual(self.client.post('/api/mutate/', {}, REMOTE_ADDR='192.0.2.1',
                                          HTTP_X_FORWARDED_FOR='127.0.0.1').status_code, 403)
