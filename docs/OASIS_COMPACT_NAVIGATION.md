# Compact library and section navigation

The phone document view previously placed every library and section above the
original-document link. With more libraries, this displaced the reading task
by several screens. The catalogue landing page also repeated the same libraries
in its navigation and overview.

The design keeps the current location visible and makes changing it deliberate:

- One location disclosure replaces the long sidebar and mobile selection grids.
  Browsing a selected library, reading a document and managing documents begin
  with the disclosure closed.
- Opening it exposes searchable library and section lists with bounded heights.
  The initial visitor catalogue opens the library list for discovery, once.
- Choosing a library with sections previews its sections in the same control.
  Choosing a section or all documents commits the existing folder selection.
- Closing the control cancels an uncommitted selection. Keyboard users can open
  it, search, choose a location and dismiss it with Escape.
- Manage Library keeps **New library** available beside the location control.
  Document search, uploads and library/section actions keep their existing scope.

The visual direction is a quiet white reading surface, the existing Kuwala
palette, system typography, clear selection and generous touch targets. The
interaction removes repeated navigation from the task without hiding where a
document belongs. React, Material UI and the backend/export contracts remain
unchanged; this introduces no frontend dependency or external asset.

## Verification

Use the isolated preview described in the README. Build the frontend before
starting it, and restart the preview after a rebuild so static assets are found.
The developer verification uses a separate `.preview/navigation-check` database
on loopback port **8798**; it leaves the existing 8787 evaluation and 8790 preview
alone. All test records and originals are visibly synthetic.

For a fresh, separate three-document preview after installing the README's local
dependencies, run from the repository root:

```bash
npm --prefix frontend run build-prod
export OASIS_PREVIEW_STATE_ROOT="$PWD/.preview/compact-review"
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py seed
OASIS_PREVIEW_CURATOR=1 .venv/bin/python manage.py runserver 127.0.0.1:8798 --settings=dlms.preview_settings --noreload
```

Open `http://127.0.0.1:8798/?tab=contents` or
`http://127.0.0.1:8798/?workspace=curator&tab=contents`. Keep this development
preview on loopback. The larger synthetic fixture described below was added
only to the isolated verification database; ordinary seeding creates three PDFs.

The isolated fixture has **50 libraries** and **51 sections** in one library,
including nested sections and documents with multiple memberships. Browser
checks at 390 × 844 and 1280 × 900 CSS pixels covered selection, independent
library/section searches, no-match states, bounded lists, keyboard Escape and
focus, browser history, returning to the overview and document back navigation.
Upload still preselects the current library; editing retains all memberships.
The new-library, upload and edit dialogs were opened and cancelled in the browser;
the existing backend suite checks saved mutations and export behavior.

The collapsed location control measured **105 CSS pixels** at phone widths. At
the same 433-pixel width, the previous synthetic library/section grids occupied
3,491 pixels. No horizontal page overflow was observed. Search input bounds were
checked after fixing an overflowing content-box width in the expanded desktop
control.

- Production frontend build: passed; existing bundle-size/Browserslist warnings.
- Frontend checks: **39 passed**, including eight navigation behavior checks.
- Django preview suite: **163 run: 157 passed and six existing environment-dependent skips**.
- Deployment regression checks: **36 passed**.
- Django system check and migration-drift check: passed; no new migrations.

See the [desktop and phone screenshots](screenshots/compact-navigation-2026-10-11/README.md).
They are visibly synthetic. This is a UI check, not evidence of a 5,000-PDF search
index or production capacity.
