"""Isolated local preview; never uses the evaluation or operator database."""
import os
from pathlib import Path

PREVIEW_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_STATE_ROOT = Path(os.environ.get('OASIS_PREVIEW_STATE_ROOT', PREVIEW_ROOT / '.preview')).resolve()
for directory in (PREVIEW_STATE_ROOT, PREVIEW_STATE_ROOT / 'media' / 'contents', PREVIEW_STATE_ROOT / 'builds'):
    directory.mkdir(parents=True, exist_ok=True)

# Explicit overrides prevent an operator's DATABASE_URL/.env from leaking into
# this disposable preview. The key is exclusively for local development.
os.environ.update({
    'SECRET_KEY': 'oasis-library-isolated-loopback-preview-only',
    'DEBUG': 'True',
    'ALLOWED_HOSTS': '127.0.0.1,localhost,[::1],testserver',
    'DATABASE_URL': 'sqlite:///' + str(PREVIEW_STATE_ROOT / 'catalogue.sqlite3'),
    'MEDIA_ROOT': str(PREVIEW_STATE_ROOT / 'media'),
    'CONTENTS_ROOT': str(PREVIEW_STATE_ROOT / 'media' / 'contents'),
    'BUILDS_ROOT': str(PREVIEW_STATE_ROOT / 'builds'),
    'STATIC_ROOT': str(PREVIEW_STATE_ROOT / 'collected-static'),
})

from dlms.settings import *  # noqa: E402,F403

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
OASIS_CURATOR_ENABLED = os.environ.get('OASIS_PREVIEW_CURATOR') == '1'
OASIS_SYNTHETIC_FIXTURES = (PREVIEW_STATE_ROOT / 'synthetic-fixtures.json').is_file()
OASIS_LOOPBACK_ONLY = True
LOGGING['handlers']['applogfile']['filename'] = str(PREVIEW_STATE_ROOT / 'preview.log')
TIME_ZONE = 'UTC'
