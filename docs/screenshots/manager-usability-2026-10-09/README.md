# Manager usability review — 9 October 2026

These screenshots show the isolated, loopback-only Django/React preview with
**labelled synthetic fixtures**. They contain no community guidance, private
documents or production data. Browser viewport overrides were restored after
capture.

- [Desktop catalogue](desktop-catalogue.jpg): sections, grouped library actions,
  document search, upload and document actions.
- [Phone section](mobile-section.jpg): readable navigation labels and compact
  library/section selectors; document details and actions remain available.
- [Shared Tools menu](tools-menu.jpg): catalogue-wide Advanced tools and Refresh.
- [Optional Search maintenance](search-maintenance.jpg): closed by default below
  the list; its expanded view explains search rebuilding and publication.

## Checked workflows

- Default All documents view; library and section filtering; metadata search.
- Reload and browser Back/Forward preserve library, section and query. Back also
  dismisses Advanced tools and reloads the manager's catalogue references.
- A stale page bookmark has a working Return to the first page action.
- Create a synthetic library and section, rename a section, and edit a document
  while preserving its author, rights, original file and placements.
- Upload a unique synthetic PDF into a section. A duplicate original is rejected
  with an inline error while preserving the entered form.
- Inspect the document deletion confirmation and cancel it; no real document was
  deleted. Mutation/security coverage runs in the existing backend CI suite.
- Open Advanced tools and create a local export of the synthetic catalogue;
  the UI confirms Local export created. Closing the dialog restores the manager
  URL after legacy tabs change it.
- Phone and desktop layouts fit the document viewport without horizontal page
  overflow. Single-page lists omit disabled Previous/Next controls.

## Reproduce

Follow the environment/build preparation in
[the project README](../../../README.md), then use a separate state directory
and free loopback port to avoid an existing evaluation:

```sh
export OASIS_PREVIEW_STATE_ROOT="$PWD/.preview/search-maintenance"
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py seed
npm --prefix frontend run build-prod
.venv/bin/python scripts/preview.py check
OASIS_PREVIEW_CURATOR=1 .venv/bin/python manage.py runserver 127.0.0.1:8801 --noreload --settings=dlms.preview_settings
```

Open `http://127.0.0.1:8801/?workspace=curator&tab=contents`.
The seed has three unique PDFs; the upload check adds a fourth synthetic PDF.
The screenshots show this explicitly labelled state.

## Limits

This preview does not configure a station indexing adapter: PDF text and AI
search accurately show unavailable/not indexed, and reindex actions are disabled.
This review does not rebuild production indexes, publish a library release, change
authentication or replace the legacy export/metadata framework. Existing Webpack
asset-size and outdated Browserslist warnings remain; the advanced and import
tools continue to load on demand.
