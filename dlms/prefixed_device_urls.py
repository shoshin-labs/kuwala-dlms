"""Explicit manager mount: the trusted proxy preserves the /manage prefix."""
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('manage', RedirectView.as_view(pattern_name='oasis-home', permanent=True,
        query_string=True, http_method_names=['get', 'head']), name='oasis-prefix-root'),
    path('manage/', include('dlms.device_urls')),
]
