# Oasis Library follow-ups

This first rebrand adapts React 16, Material UI 4 and Webpack 4, preserving the
Django schema, folder/content API and export contracts. Larger changes need
separate review and verification.

## Dependency and framework maintenance

The 8 October 2026 `npm audit` reports **100 dependency vulnerabilities** (7 low,
27 moderate, 51 high, 15 critical). This is an inherited dependency inventory,
not an application exploitability assessment. A successful build is not security
remediation.

Upgrade active Axios, Immer, Lodash, Moment and XLSX with workflow tests. Remove
unused direct dependencies after verifying references: this audit found no source
imports for react-pdf, react-codemod, chart.js, react-chartjs-2, font-awesome, csv,
papaparse, downshift, react-image-picker, react-keyed-file-browser,
react-sortable-tree, react-cookie, js-cookie, keycode or react-dnd. Recheck current
advisories during upgrade. Evaluate React, Material UI and bundler migrations
together, preserving keyboard navigation, dates/metadata, multipart upload and
offline chunk loading.

The curator workspace loads separately from visitors. Further bundle reduction
should remove redundant modules. Browserslist’s compatibility dataset remains old.

The isolated preview runs pinned Django 5.2/DRF 3.16. Legacy `requirements.txt`
remains for upstream provenance/configuration. A maintained deployment migration
needs PostgreSQL driver/configuration, runtime checks, static/media serving and
existing operator-data testing. Neither dependency set is a public deployment recipe.

## Publication and access

Follow [the architecture](OASIS_LIBRARY_ARCHITECTURE.md) for immutable
versions/releases. Add authenticated curator/reviewer/publisher roles and
server-enforced approval before remote management. Loopback restriction is a
development boundary. Published readers must expose only approved immutable
versions without staging/private authoring metadata. Upload and active flags
do not establish approval; recorded review does not certify expert advice.

Connect visitor PDF-text and semantic search to an explicitly approved immutable
release. The current search adapter is restricted to private curator drafts and
reuses the existing station providers. Verify semantic retrieval with the intended
installed local model and real reviewed corpus before enabling it. The workstation
preview now verifies Nomic against labelled synthetic fixtures. Preserve original/page attribution and honest
unavailable states rather than exposing testing manifests or labelling keyword
fallback as AI.

Upstream export and bulk filesystem import trust a local curator. Validate
filenames, archive/version paths, rights/source records and release artifacts
before remote access. Export creates a local build; it does not activate or
publish it to Oasis.

## Localisation and scale

Add reviewed Chichewa, Swahili, Zulu and French visitor packs. Move remaining
curator form/validation and backend error copy into resources without translating
document attribution. Test long labels with speakers. Membership/counts load the
selected version's lightweight folder tree and counts; document lists use bounded
server pagination and subtree search. Metadata choices load only when opening an
editor. For larger metadata vocabularies, add paginated autocomplete rather than
fetching every metadata value for that editor.

## Protected central library and downloads

Record this as a future milestone: a protected central archive of authorised
PDF versions, with authenticated per-device downloads when a Kuwala box
reconnects. Hosting under `kuwala.space`, authentication and the sync design
remain open decisions. Preserve offline operation and activate only verified,
complete releases. See [the deferred requirements](OASIS_CENTRAL_LIBRARY_FUTURE.md).
The current local Pi/Jetson setup remains the immediate priority.

## Existing parallel work

Chat streaming, Jetson inference, extraction/vector maintenance, remote trial
exposure and release activation remain in their existing workstreams. The private
index queue delegates to the existing station maintenance commands in new draft
directories. It does not add a second ingestion pipeline or activate a reader release.
The [private device deployment process](OASIS_DEVICE_DEPLOYMENT.md) now supplies
supervised operation, durable queued jobs, maintenance, backups and paired recovery.
Remote management exposure, cancellation and resource scheduling remain follow-ups.
The adapter follows the station importer's shared limit, currently 128 PDFs in a reviewed snapshot.
Larger index packages, scoped/incremental indexing and resource scheduling belong
in that existing pipeline workstream; the paginated catalogue can browse more
records without claiming those records have matching published indexes.
