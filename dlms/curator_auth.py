"""Standard Django staff sessions for the private device curator."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView, PasswordChangeDoneView, redirect_to_login
from django.http import JsonResponse
from django.views.decorators.http import require_safe
from django.views.generic import TemplateView

from dlms.preview_middleware import PrivatePreviewMiddleware, is_loopback_request


@lru_cache(maxsize=1)
def curator_ui():
    # Separate server resources keep the login usable without JavaScript and
    # permit later translations without introducing a second frontend bundle.
    return json.loads((Path(__file__).parent / 'locales/curator.en.json').read_text(encoding='utf-8'))


class CuratorProxyOriginMiddleware:
    """Trust the fixed HTTPS signal only from the already-private loopback tunnel."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = getattr(settings, 'OASIS_DEVICE_ADMIN_ORIGIN', '')
        protocol = request.META.get('HTTP_X_FORWARDED_PROTO')
        trusted = False
        if protocol is not None:
            if (not origin or not is_loopback_request(request) or protocol != 'https'
                    or request.get_host() != urlsplit(origin).netloc):
                return PrivatePreviewMiddleware.denied(curator_ui()['invalid_proxy_origin'])
            request.META['wsgi.url_scheme'] = 'https'
            trusted = True
        elif origin and request.get_host() == urlsplit(origin).netloc:
            return PrivatePreviewMiddleware.denied(curator_ui()['invalid_proxy_origin'])
        response = self.get_response(request)
        if trusted:
            # The SSH-forwarded localhost origin remains usable over local
            # HTTP; every cookie emitted on the configured HTTPS origin is Secure.
            for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
                if name in response.cookies:
                    response.cookies[name]['secure'] = True
        return response


class CuratorSessionMiddleware:
    """Guard the complete device application, including upstream legacy read endpoints."""
    PUBLIC_VIEWS = frozenset(('oasis-login', 'oasis-health'))
    NAVIGATION_VIEWS = frozenset(('oasis-home', 'oasis-password-change', 'oasis-password-change-done'))

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(settings, 'OASIS_REQUIRE_CURATOR_AUTH', False):
            response['Cache-Control'] = 'no-store'
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not getattr(settings, 'OASIS_REQUIRE_CURATOR_AUTH', False):
            return None
        if request.resolver_match.url_name in self.PUBLIC_VIEWS:
            return None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_active and user.is_staff:
            navigation = (request.method == 'GET' and request.resolver_match.url_name in self.NAVIGATION_VIEWS
                          and request.META.get('HTTP_SEC_FETCH_MODE') == 'navigate'
                          and request.META.get('HTTP_SEC_FETCH_DEST') == 'document')
            if not navigation and not PrivatePreviewMiddleware.browser_origin_allowed(request):
                return PrivatePreviewMiddleware.denied(curator_ui()['invalid_browser_origin'])
            return None
        if request.path.startswith('/api/') or request.path.startswith(('/media/', '/builds/')):
            return JsonResponse({'success': False, 'data': None, 'error': curator_ui()['session_required']},
                                status=403 if user is not None and user.is_authenticated else 401,
                                headers={'Cache-Control': 'no-store'})
        if user is not None and user.is_authenticated:
            return PrivatePreviewMiddleware.denied(curator_ui()['staff_required'])
        return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)


class CuratorContext:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['curator_ui'] = curator_ui()
        return context


class CuratorLoginView(CuratorContext, LoginView):
    template_name = 'curator/login.html'
    authentication_form = AdminAuthenticationForm


class CuratorLogoutView(LogoutView):
    next_page = 'oasis-login'


class CuratorPasswordChangeView(CuratorContext, PasswordChangeView):
    template_name = 'curator/password_change.html'
    success_url = '/accounts/password-change/done/'


class CuratorPasswordChangeDoneView(CuratorContext, PasswordChangeDoneView):
    template_name = 'curator/password_change_done.html'


class CuratorShellView(CuratorContext, TemplateView):
    template_name = 'index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['curator_session'] = bool(user.is_authenticated and user.is_active and user.is_staff)
        return context


@require_safe
def health(request):
    """Minimal loopback readiness, with no catalogue, operator or job information."""
    return JsonResponse({'success': True, 'data': {'ready': True, 'authentication_required': True}, 'error': None},
                        headers={'Cache-Control': 'no-store'})
