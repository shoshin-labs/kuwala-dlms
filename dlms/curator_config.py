"""Strict, operator-selected private administrator origin configuration."""
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def admin_origin(value):
    if not value:
        return ''
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ''
        if (not isinstance(value, str) or any(ord(character) <= 32 or ord(character) >= 127 for character in value)
                or parsed.scheme != 'https' or parsed.port != 8443 or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or len(hostname) > 253 or not hostname.endswith('.ts.net') or hostname == 'ts.net'
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                       for label in hostname.split('.'))
                or value != 'https://' + hostname + ':8443'):
            raise ValueError
    except (TypeError, ValueError):
        raise ImproperlyConfigured('OASIS_DEVICE_ADMIN_ORIGIN must be one exact https://<tailnet-name>.ts.net:8443 origin.')
    return value
