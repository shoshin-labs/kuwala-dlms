# Manager and account interface verification

The private manager, login and password screens now follow the station's approved
Oasis Knowledge brand. They share Graphite text and sun tile, Dark Khaki actions,
Olive links/focus, restrained Amber Glow selections, system typography and white
surfaces. Form controls retain 48px touch targets; phone search/select controls
use 16px text. The account/session protection and original-file policies are
unchanged.

## Loading

The live catalogue/database was already fast: 8–10ms for catalogue metadata and
27–33ms for the first 23-document page. A cold draft-status check took 20.269s,
mostly artifact verification. That validation remains mandatory. The manager
now waits for the correct document page before requesting status, and waits for
status before checking passage-search capabilities. Browsing, metadata search
and upload controls remain available during verification. Explicit status/error
text and retries remain available.

The spreadsheet importer and parser load when requested. Initial production
manager JavaScript decreased from 1,673,433 to 739,327 bytes (55.8%). The new
assets total approximately 216,525 bytes when gzipped. This is a transfer-size
comparison, not a claim about every phone's network latency. The existing
WhiteNoise runtime now compresses collected assets and caches only explicitly
hashed Webpack bundles as immutable. Stable icon paths keep their short cache.
The index overview is a native disclosure; active/failed jobs and status errors
open it automatically.

## Reproduce

Use the existing isolated preview and locked dependencies described in
[README](../README.md). To test independently of a preview already on 8790:

```sh
export OASIS_PREVIEW_STATE_ROOT="$(mktemp -d)"
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py seed
npm --prefix frontend run build-prod
OASIS_PREVIEW_CURATOR=1 .venv/bin/python manage.py runserver 127.0.0.1:8806 --noreload --settings=dlms.preview_settings
```

Fixtures are visibly synthetic. The loopback development preview remains
separate from the password-protected device manager. Restart its server after
rebuilding assets. Device releases still use the
[verified deployment procedure](OASIS_DEVICE_DEPLOYMENT.md), with successful CI
for the exact merged commit and a paired state backup.

Verification included the existing catalogue, section filter, document editor,
bulk-import dialog, authentication/CSRF/origin tests, deployment tests, production
build and local-brand/date checks. A new DEBUGFalse regression confirms gzip
decodes to the exact asset bytes and immutable caching applies only to the
correct static filenames. No migrations or framework changes are required.
Browser checks confirmed no horizontal overflow at 320px and 390px CSS widths,
readable 16px search controls and working library/section placement dialogs.

## Screenshots

These screenshots use labelled synthetic documents in a separate loopback
preview. Indexing honestly reports unavailable because that preview has no
station adapter. They do not represent new published documents or a new library.

| Surface | Desktop | Phone |
|---|---|---|
| Manager | [Screenshot](screenshots/manager-brand-2026-10-09/manager-desktop.png) | [Screenshot](screenshots/manager-brand-2026-10-09/manager-mobile.png) |
| Login | [Screenshot](screenshots/manager-brand-2026-10-09/login-desktop.png) | [Screenshot](screenshots/manager-brand-2026-10-09/login-mobile.png) |

The Libraries → Sections → Documents UI remains intact. Populating subject
sections in the real catalogue is a separate, reversible data operation using
the existing catalogue IDs and memberships. It does not approve additional
documents for publication or technical advice.
