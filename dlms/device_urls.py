"""Serve private originals explicitly when DEBUG is disabled."""
import mimetypes
import os
import stat
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.urls import include, path

from dlms.private_paths import checked_directory, checked_path
from dlms.preview_middleware import PrivatePreviewMiddleware, is_loopback_request
from dlms.curator_auth import (CuratorShellView, CuratorLoginView, CuratorLogoutView,
                               CuratorPasswordChangeView, CuratorPasswordChangeDoneView, health)


def private_media(request, path):
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    if not settings.OASIS_CURATOR_ENABLED or not is_loopback_request(request) or not PrivatePreviewMiddleware.browser_origin_allowed(request):
        return PrivatePreviewMiddleware.denied('Original files require the private curator origin.')
    try:
        relative = Path(path)
        if not path or relative.is_absolute() or '..' in relative.parts or '\\' in path or '\x00' in path:
            raise ValueError('Unsafe media path.')
        root = checked_directory(settings.MEDIA_ROOT, 'Private media root')
        candidate = checked_path(root / relative, 'Private media file')
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        stream = os.fdopen(descriptor, 'rb')
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            stream.close()
            raise ValueError('Private media must be a regular file.')
    except (OSError, ValueError):
        raise Http404('Private original is unavailable.')
    content_type = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
    active_formats = {'text/html', 'image/svg+xml', 'application/xhtml+xml', 'application/xml', 'text/xml',
                      'application/javascript', 'text/javascript'}
    response = FileResponse(stream, content_type=content_type, filename=candidate.name,
                            as_attachment=content_type in active_formats)
    response['Cache-Control'] = 'no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Referrer-Policy'] = 'same-origin'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    return response


urlpatterns = [
    path('', CuratorShellView.as_view(), name='oasis-home'),
    path('healthz', health, name='oasis-health'),
    path('accounts/login/', CuratorLoginView.as_view(), name='oasis-login'),
    path('accounts/logout/', CuratorLogoutView.as_view(), name='oasis-logout'),
    path('accounts/password-change/', CuratorPasswordChangeView.as_view(), name='oasis-password-change'),
    path('accounts/password-change/done/', CuratorPasswordChangeDoneView.as_view(), name='oasis-password-change-done'),
    path('media/<path:path>', private_media, name='oasis-private-media'),
    path('', include('content_management.urls')),
]
