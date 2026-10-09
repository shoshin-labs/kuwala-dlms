"""Private loopback curator runtime with durable state outside release code.

This module deliberately does not import legacy settings or read a source .env.
"""
import os
import re
import stat
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from dlms.private_paths import checked_directory, checked_path, require_disjoint
from dlms.curator_config import admin_origin

BASE_DIR = Path(__file__).resolve().parent.parent


def required(name):
    value = os.environ.get(name, '')
    if not value:
        raise ImproperlyConfigured(name + ' is required for the private device runtime.')
    return value


def read_secret():
    try:
        path = checked_path(required('OASIS_DEVICE_SECRET_KEY_FILE'), 'Device secret file')
        if path.is_relative_to(BASE_DIR):
            raise ValueError('Device secret file must be outside release code.')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or not 50 <= metadata.st_size <= 4096:
                raise ValueError('Device secret file must be a private regular file containing a strong key.')
            value = stream.read(4097).strip()
        if len(value) < 50 or len(set(value)) < 5 or value.startswith('django-insecure-') or any(character.isspace() for character in value):
            raise ValueError('Device secret file must contain a strong key of at least 50 characters.')
        return value
    except (OSError, UnicodeError, ValueError) as exc:
        raise ImproperlyConfigured('Invalid OASIS_DEVICE_SECRET_KEY_FILE: ' + str(exc)) from exc


SECRET_KEY = read_secret()
try:
    DEVICE_DATA_ROOT = checked_directory(required('OASIS_DEVICE_DATA_ROOT'), 'Device data root', create=False)
    if DEVICE_DATA_ROOT.is_relative_to(BASE_DIR) or BASE_DIR.is_relative_to(DEVICE_DATA_ROOT):
        raise ValueError('Device data root must be separate from release code.')
    protected = [Path('/opt/kuwala')]
    if BASE_DIR.parent.parent.name == 'releases':
        protected.append(BASE_DIR.parent.parent)
    require_disjoint(DEVICE_DATA_ROOT, protected, 'Device data root')
    DEVICE_DATA_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if DEVICE_DATA_ROOT.stat().st_mode & 0o077:
        raise ValueError('Device data root must be private to its operator account (mode 0700).')
    for relative in ('media/contents', 'builds', 'indexing/jobs', 'logs'):
        checked_directory(DEVICE_DATA_ROOT / relative, 'Device state directory', create=True)
    for filename in ('catalogue.sqlite3', 'catalogue.sqlite3-wal', 'catalogue.sqlite3-shm', 'catalogue.sqlite3-journal', 'logs/device.log'):
        path = checked_path(DEVICE_DATA_ROOT / filename, 'Device state file')
        if path.exists() and not path.is_file():
            raise ValueError('Device state file must be a regular file.')
except (OSError, ValueError) as exc:
    raise ImproperlyConfigured('Invalid OASIS_DEVICE_DATA_ROOT: ' + str(exc)) from exc

DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '[::1]']
OASIS_DEVICE_ADMIN_ORIGIN = admin_origin(os.environ.get('OASIS_DEVICE_ADMIN_ORIGIN', ''))
if OASIS_DEVICE_ADMIN_ORIGIN:
    from urllib.parse import urlsplit
    ALLOWED_HOSTS.append(urlsplit(OASIS_DEVICE_ADMIN_ORIGIN).hostname)
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework', 'content_management', 'frontend', 'django_extensions',
]
MIDDLEWARE = [
    'dlms.curator_auth.CuratorProxyOriginMiddleware',
    'dlms.preview_middleware.PrivatePreviewMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'dlms.curator_auth.CuratorSessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'dlms.device_urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [str(BASE_DIR / 'templates'), str(BASE_DIR / 'frontend/static')],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug', 'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'dlms.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(DEVICE_DATA_ROOT / 'catalogue.sqlite3')}}
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
# Collect during staging into the individual release so rollback keeps its assets.
STATIC_ROOT = str(BASE_DIR / 'collected-static')
STATICFILES_DIRS = []
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # Webpack already names scripts by their build hash. Compress the collected
    # copies without rewriting the URLs or original bytes in the release receipt.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}


def immutable_static_file(path, url):
    # Webpack 4 emits a 20-character SHA-256 build hash before `.bundle.js`.
    # Logo/favicon paths keep their short cache because their names are stable.
    return re.fullmatch(r'/static/js/[A-Za-z0-9_~.-]+\.[0-9a-f]{20}\.bundle\.js', url) is not None


WHITENOISE_IMMUTABLE_FILE_TEST = immutable_static_file
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False
MEDIA_ROOT = str(DEVICE_DATA_ROOT / 'media')
MEDIA_URL = '/media/'
CONTENTS_ROOT = str(DEVICE_DATA_ROOT / 'media/contents')
CONTENTS_URL = '/media/contents/'
BUILDS_ROOT = str(DEVICE_DATA_ROOT / 'builds')
BUILDS_URL = '/builds/'
OASIS_INDEXING_STATE_ROOT = str(DEVICE_DATA_ROOT / 'indexing')
OASIS_INDEXING_PROTECTED_ROOTS = ('/opt/kuwala',)
OASIS_CURATOR_ENABLED = True
OASIS_SYNTHETIC_FIXTURES = False
OASIS_LOOPBACK_ONLY = True
OASIS_REQUIRE_CURATOR_AUTH = True
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/?workspace=curator&tab=contents'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'EXCEPTION_HANDLER': 'content_management.standardize_format.standard_exception_handler',
}
X_FRAME_OPTIONS = 'SAMEORIGIN'
SESSION_COOKIE_HTTPONLY = True
USE_X_FORWARDED_HOST = False
SECURE_PROXY_SSL_HEADER = None
# The fixed-origin middleware marks cookies Secure on the private HTTPS
# manager, while retaining HTTP localhost access through encrypted SSH.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_NAME = 'oasis_curator_session'
SESSION_COOKIE_AGE = 14400
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_NAME = 'oasis_curator_csrf'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {
        'applogfile': {'class': 'logging.handlers.RotatingFileHandler', 'level': 'INFO',
                       'filename': str(DEVICE_DATA_ROOT / 'logs/device.log'),
                       'maxBytes': 15 * 1024 * 1024, 'backupCount': 10},
        'console': {'class': 'logging.StreamHandler', 'level': 'INFO'},
    },
    'loggers': {'': {'handlers': ['applogfile'], 'level': 'INFO'},
                'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': True}},
}
