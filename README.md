# Oasis Library

Oasis Library is the library catalogue and curator workspace for Kuwala’s offline
community information hub. Visitors choose a library, browse documents and open
an original local file or numbered PDF page. Oasis, the conversational interface,
stands for **Off-grid Autonomous Solar Intelligence System**.

This fork builds on [SolarSPELL’s Digital Library Management System](https://github.com/SolarSPELL-Main/solarspell-dlms)
at Arizona State University. We acknowledge SolarSPELL’s work bringing offline
educational resources to communities. The original [MIT licence and copyright](LICENSE)
are unchanged and readable offline in About. Documents retain their own source,
author, attribution and rights; the software licence does not license them.

## Local preview

Use Node 22 or later and Python 3.12 or 3.13. The preview has a pinned, isolated
Python runtime. Legacy deployment requirements remain in `requirements.txt`.
React 16, Material UI 4 and Webpack 4 remain in this first UI PR.

Run from this checkout (macOS/Linux):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-preview.lock.txt
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build-prod
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py run
```

Open **http://127.0.0.1:8790/?tab=contents**. The preview binds only to loopback and
uses `.preview/catalogue.sqlite3`, `.preview/media` and `.preview/builds`. It does
not use an operator `.env`, the scratch evaluation, or its port **8787**. Build
before starting the server; after rebuilding, restart the preview and reload the
browser so Django discovers the new static output.

The default database is empty. To add labelled example content, stop the preview,
run the explicit seed command, then start it again:

```bash
.venv/bin/python scripts/preview.py seed
.venv/bin/python scripts/preview.py run
```

The seed creates three **synthetic** one-page PDFs in Farming, Water and Learning,
with labelled child sections for testing the folder hierarchy.
The water record also belongs to Learning. The banner and document data identify
these fixtures as examples, without technical-advice approval. Repeating `seed`
reuses the existing records. Do not mix disposable fixture state into a real library.

For library creation, upload, document editing/replacement and deletion,
stop that preview and explicitly start private curator mode:

```bash
.venv/bin/python scripts/preview.py run --curator
```

Choose **Manage Library** or open
**http://127.0.0.1:8790/?workspace=curator&tab=contents**. This is a development
restriction, not a new authentication scheme. Visitor mode denies writes,
including upstream GET export/clone actions and their format-suffixed variants.
Curator writes require explicit enablement and a loopback peer. Do not publish
or proxy the curator origin onto LAN, tailnet or internet: a proxy’s loopback peer
is not end-user authentication. No remote management exposure is provided here.
The workspace saves real database records and original files. **Advanced tools**
retains the existing metadata, catalogue-version and export workflows. See
[private management and indexing guide](docs/OASIS_LIBRARY_MANAGEMENT.md).

Windows: activate `.venv\Scripts\activate` and use `python` in place of
`.venv/bin/python`. Frontend clean/build commands use portable Node/npm scripts;
existing build aliases remain. `build` makes a development bundle and `build-prod`
a minified bundle. No PATH modification or external font service is needed.
After dependencies and local data are present, browsing and original-file access
need no internet connection. This is local server operation, not a browser cache
that remains available after its library host shuts down.

## Libraries and compatibility

- A visitor **library** is a root `LibraryFolder` in a selected `LibraryVersion`.
  Its documents include descendant folders and deduplicate stable content IDs.
- Child folders appear as **sections**. The library overview and persistent navigation
  keep other libraries and sections visible while a selected section filters the
  documents. Curators can create sections under an existing library or section.
- Search and document pagination run on the server, with 24 records per page and
  a maximum API page size of 100. Folder summaries contain counts, not every PDF's
  metadata; editor reference data loads when needed.
- The existing many-to-many relationship supports multiple library membership.
  Metadata categories/tags remain separate; this PR does not rename data.
- Curator **Library versions** manages the original export versions/folder tree.
  With several versions, visitors choose a catalogue version before its libraries.
- Numeric document/folder/version IDs, API paths/envelopes, `solarspell.db`,
  `folder`, `content_folder`, rights fields and original bytes remain compatible.
  The database filename is an upstream/Oasis importer contract.
- Visitor search filters local document metadata. Exported metadata FTS remains
  functional. The private indexing adapter invokes the existing station maintenance
  commands into new draft directories; chat, inference and ingestion implementations
  remain in the station repository. Text and vector freshness are reported separately.
- Manage Library also searches verified private draft passages using those existing
  station readers. PDF-text search returns original page links and attribution;
  AI semantic ranking requires matching local vectors and an installed embedding
  model. Unavailable AI is labelled honestly. Public passage search awaits an
  approved immutable release; private testing drafts remain restricted to curators.
- Library uses Oasis chat's compact header, system typography and dark blue wordmark,
  with a teal action accent. All interface assets are local.

The catalogue is an authoring preview, not an approval-enforced published release.
The upstream active flag and review date do not certify technical advice.
See [the architecture](docs/OASIS_LIBRARY_ARCHITECTURE.md) for publication boundaries.

## Verification and screenshots

```bash
npm --prefix frontend run build-prod
.venv/bin/python scripts/preview.py check
.venv/bin/python scripts/preview.py test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=dlms.preview_settings
```

Tests cover multipart upload, stable detail IDs, multiple library membership,
local original PDF access, exported originals/rights/schema/metadata FTS, and
visitor/remote-peer mutation denials. GitHub Actions repeats build/backend checks.
[Browser verification and desktop/mobile screenshots](docs/OASIS_LIBRARY_REBRAND.md)
cover navigation, metadata search, details, original/PDF links, errors, About and
the curator upload/export/indexing flow.

An optional reproducible synthetic scale check uses its own `.preview/scale-check`
database and leaves the main preview untouched:

```bash
.venv/bin/python scripts/benchmark_catalogue.py
```

It creates 5,000 labelled catalogue records sharing one synthetic PDF original,
checks bounded page/section/search queries and prints a separate loopback preview
command. It does not create or claim a 5,000-document index. The adapter follows
the configured station importer's shared limit (currently 128 PDFs per reviewed
snapshot); larger index packages remain part of separate maintenance work.

English resources are bundled in `frontend/src/js/locales`. See
[translation instructions](frontend/src/js/locales/README.md) for reviewed
Chichewa, Swahili, Zulu and French packs. The modern manager uses a scoped language
resource pack; advanced upstream forms retain legacy English copy.

Original PostgreSQL configuration keys remain in `dlms/env.example`; legacy
dependencies are not a maintained public deployment recipe.
For the private Jetson curator, use the [device deployment runbook](docs/OASIS_DEVICE_DEPLOYMENT.md)
and `requirements-device.lock.txt`: production Gunicorn, persistent private
state, verified release bundles and SSH-only management. The Pi remains the
existing visitor gateway. [Transfer the existing main catalogue](docs/OASIS_CATALOGUE_TRANSFER.md)
into the curator with its original IDs and metadata, rather than starting a
second empty collection. Visitors read an immutable snapshot of that same
catalogue; curator changes become visible after the existing publication process.
Framework/dependency upgrades, full curator translation and enforced
publication/authentication are [separate follow-ups](docs/OASIS_LIBRARY_FOLLOW_UPS.md).
