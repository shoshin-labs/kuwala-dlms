"""Development access restrictions, not a replacement for curator authentication."""
import ipaddress

from django.conf import settings
from django.http import JsonResponse


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

    def __call__(self, request):
        loopback = is_loopback_request(request)
        if settings.OASIS_LOOPBACK_ONLY and not loopback:
            return self.denied('This development preview is available only on loopback.')
        writes = request.method not in ('GET', 'HEAD', 'OPTIONS')
        if writes and (not loopback or not settings.OASIS_CURATOR_ENABLED):
            return self.denied('Curator operations require the explicitly enabled loopback development preview.')
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method not in ('GET', 'HEAD'):
            return None
        name = request.resolver_match.url_name
        action = getattr(view_func, 'actions', {}).get('get')
        if name in self.MUTATING_READ_NAMES or action in self.MUTATING_READ_ACTIONS:
            if not is_loopback_request(request) or not settings.OASIS_CURATOR_ENABLED:
                return self.denied('Curator operations require the explicitly enabled loopback development preview.')
        return None

    @staticmethod
    def denied(message):
        return JsonResponse({'success': False, 'data': None, 'error': message}, status=403)
