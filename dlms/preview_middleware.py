"""Development access restrictions, not a replacement for curator authentication."""
import ipaddress
from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware


def is_loopback_request(request):
    """Use the direct peer address; forwarded headers never grant access."""
    try:
        return ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')).is_loopback
    except ValueError:
        return False


class PrivatePreviewMiddleware:
    # Upstream performs writes through these GET views. Resolve the view/action
    # rather than matching paths: DRF supports format suffixes and noncanonical
    # integer primary keys such as +1, which must use the same access policy.
    MUTATING_READ_NAMES = frozenset(('create-build', 'libraryversion-clone'))
    MUTATING_READ_ACTIONS = frozenset(('clone',))

    def __init__(self, get_response):
        self.get_response = get_response
        self.csrf = CsrfViewMiddleware(get_response)

    def __call__(self, request):
        loopback = is_loopback_request(request)
        if settings.OASIS_LOOPBACK_ONLY and not loopback:
            return self.denied('This development preview is available only on loopback.')
        writes = request.method not in ('GET', 'HEAD', 'OPTIONS')
        if writes and (not loopback or not settings.OASIS_CURATOR_ENABLED):
            return self.denied('Curator operations require the explicitly enabled loopback development preview.')
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        name = request.resolver_match.url_name
        action = getattr(view_func, 'actions', {}).get('get')
        writes = request.method not in ('GET', 'HEAD', 'OPTIONS')
        mutating_read = request.method in ('GET', 'HEAD') and (
            name in self.MUTATING_READ_NAMES or action in self.MUTATING_READ_ACTIONS
        )
        if writes or mutating_read:
            if not is_loopback_request(request) or not settings.OASIS_CURATOR_ENABLED:
                return self.denied('Curator operations require the explicitly enabled loopback development preview.')
            if not self.browser_origin_allowed(request):
                return self.denied('Curator operations must come from the same preview origin.')
            if writes:
                # DRF exempts its views and only checks CSRF for authenticated
                # sessions. This local curator has no authentication scheme, so
                # use Django's validator with a non-exempt callback explicitly.
                # Django's intentional test-client bypass remains supported.
                return self.csrf.process_view(request, self.csrf_callback, view_args, view_kwargs)
        return None

    @staticmethod
    def csrf_callback(request, *args, **kwargs):
        """Non-exempt callback used only for Django's CSRF validation."""

    @classmethod
    def browser_origin_allowed(cls, request):
        # Browsers emit these headers; local CLI callers may omit them. Reject
        # same-site too: a different port or host is a different curator origin.
        fetch_site = request.META.get('HTTP_SEC_FETCH_SITE', '').strip().lower()
        if fetch_site not in ('', 'same-origin', 'none'):
            return False
        for header in ('HTTP_ORIGIN', 'HTTP_REFERER'):
            if header in request.META and not cls.same_origin(request, request.META[header]):
                return False
        return True

    @staticmethod
    def same_origin(request, value):
        try:
            supplied = urlsplit(value)
            expected = urlsplit('%s://%s' % (request.scheme, request.get_host()))
            if supplied.scheme not in ('http', 'https') or not supplied.hostname or supplied.username is not None or supplied.password is not None:
                return False
            supplied_port = supplied.port or (443 if supplied.scheme == 'https' else 80)
            expected_port = expected.port or (443 if expected.scheme == 'https' else 80)
            return (supplied.scheme, supplied.hostname.lower(), supplied_port) == (
                expected.scheme, expected.hostname.lower(), expected_port
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def denied(message):
        return JsonResponse({'success': False, 'data': None, 'error': message}, status=403)
