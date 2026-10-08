# Oasis Library rebrand and management verification

Verified locally on 8 October 2026 using Node 26, npm 11, Python 3.13 and Chromium.
This PR retains React 16 / Material UI 4 / Webpack 4 and the existing Django data
model. The independently runnable preview uses the pinned runtime described in
[README](../README.md). It has its own database/media/build directories and port
8790. The evaluation on port 8787 continued returning HTTP 200 and was not changed.

## Changes

- Oasis wordmark, white and dark blue base matching the active Oasis app, a teal
  action accent, the same compact header metrics and system typography,
  responsive layouts, 48 px actions, keyboard focus, and restrained motion with a
  reduced-motion alternative. Old logo/icon navigation and blue table typography
  are removed. Curator modules and advanced upstream tools load separately.
- Visitors choose a root-folder library, browse deduplicated descendant documents,
  search their metadata, inspect source/author/rights and open local originals or
  numbered PDF pages. Named child sections remain visible in the overview and
  persistent navigation. Lists use server pagination (24 records, maximum 100)
  and subtree filtering. Multiple library membership and stable IDs are preserved.
- **Manage Library** provides real library creation/renaming/deletion, document
  upload/edit/replacement/deletion, multiple folder membership, original links and
  author/source/licence metadata creation. Uploads and memberships commit together;
  replacements preserve the document ID. Retained version/export screens live in
  lazy **Advanced tools**. Default visitor requests cannot mutate data, including legacy
  GET clone/export URL variants. Explicit curator mode is loopback development only.
- Private draft indexing delegates to the existing station importer/vector commands
  in new UUID directories. Exact original/artifact hashes back PDF-text and semantic
  status. Reindex actions, durable job states, worker heartbeat and errors are real.
  A changed original becomes stale; a failed rebuild retains the successful draft.
- Private PDF passage search reuses the station readers, retains source/author/licence
  and opens pinned original pages. Semantic mode is explicit and never labels a
  keyword fallback as AI. Public browsing searches metadata until an approved
  immutable reader release is configured.
- About includes Oasis’s name expansion, SolarSPELL acknowledgement and the full
  upstream MIT text offline. LICENSE is unchanged. New strings live in resources;
  only English is offered until additional language packs are reviewed.

## Checks

| Check | Result |
|---|---|
| Production frontend build | Pass on Node 26, without legacy OpenSSL flags |
| Django system check | Pass, zero issues |
| Backend contract/access tests | 56 tests pass; legacy contracts, private CRUD, CSRF/origin enforcement, replacement/deletion, transaction rollback, cleanup failure, metadata/export, scoped pagination, draft indexing and private passage-search contracts |
| Migration drift | No changes detected |
| Diff whitespace / upstream licence | Clean; LICENSE unchanged, bundled MIT text matches |
| Library navigation | Farming / Water / Learning from API; Water record also appears in Learning |
| Metadata search | Matching results, no-match state and Clear search checked |
| Detail / original links | Local PDF opens; PDF-page action opens the original with `#page=1` |
| History / root navigation | Section, metadata query and page remain stable through document detail/back; brand and workspace navigation clear stale selection parameters |
| Error / retry | Simulated catalogue HTTP 503 gives a localised error; removing the failure and Try again restores the catalogue |
| Empty catalogue | Mocked empty API gives honest “No catalogue versions yet” state |
| Offline assets | External requests blocked during reload; zero external resources and no curator chunks requested by visitor |
| Responsive browsing | 1440 px desktop, 768 px tablet, 390 px phone; detail and About also fit 320 px without horizontal overflow |
| Touch targets | Visitor controls measured at least 48 px high |
| Keyboard / motion | Skip-to-content receives a visible focus outline; reduced-motion view animation is none |
| About | Expansion and offline upstream MIT text verified |
| Curator browser upload/export | Upload saved, assigned to Farming, then exported successfully; local/exported original SHA-256 and rights/ID matched |
| Modern manager lifecycle | Create/rename a library; upload into two libraries; add author/source metadata; replace same-basename PDF while retaining ID 5; add third membership; export; delete library while retaining document; delete document globally |
| Save failure recovery | A simulated HTTP 503 retained the filled upload form; removing the mock and retrying saved the real file and memberships |
| Real empty database | Created a catalogue version, library and uploaded a labelled PDF through the UI; reload and export retained the record and exact bytes in a separate empty SQLite preview |
| Section management | Created, renamed and deleted an empty labelled section from Farming through the real private workspace |
| Real CSRF recovery | Expired browser CSRF cookies blocked a rename; the form survived, retry fetched a new token and saved successfully |
| Private text indexing | Existing station importer built and validated three labelled PDFs/pages/passages in a new private draft; original hashes and named memberships matched |
| Stale / failed rebuild | Changed one labelled fixture; only that document became stale, the reviewed-manifest check blocked rebuilding, and the previous index SHA stayed unchanged; restored the original bytes |
| Private passage search | Existing station provider returned the Water PDF's actual page-one passage and original-byte hash within the selected scope |
| Real semantic indexing/search | Installed local Nomic, built three matching semantic vectors, queried through the existing provider and verified the returned original PDF's hash |
| Synthetic scale | 5,000 records, three libraries, 12 sections; bounded tree/page/section/search queries and browser navigation without loading the full document catalogue |

The [synthetic scale benchmark](../output/playwright/catalogue-scale-benchmark.json)
records 5–6 SQL queries per bounded request; the document page returned 24 records
in about 15 KiB. Timings are workstation observations, not production guarantees.
The [local indexed-search evidence](../output/playwright/indexed-search-check.json)
records the actual text/semantic provider responses, pinned original hashes and
installed Nomic digest.

The upload/export API test checks the exported `solarspell.db` schema, shared
`content_folder` IDs, original-byte SHA-256, attribution/rights and local metadata
FTS. The browser check uploaded a labelled synthetic PDF, assigned it to Farming,
created a build, and verified the exported file’s bytes, document ID and rights.
The temporary browser-upload record was then deleted through the UI; the three
original seed documents remain. Curator row actions are labelled native buttons.

The modern manager browser test used a second clearly labelled synthetic fixture.
The replacement's SHA-256 was
`4edcb8adde903860a6031505c48ce6c280bf6dc40720201c85b08106dc7f2b09`;
served and exported bytes matched. The export retained document ID 5, rights,
Creator metadata and a newly created source metadata type. Removing its library
preserved the document in Water and Learning; global deletion removed the record
and original. Its temporary library, source field and document were then cleaned
up. The seed records 1, 2 and 3 remain.

## Screenshots

All screenshot content is **synthetic preview data**, explicitly labelled in the
interface and documents. It is not technical guidance or a published release.

| View | Screenshot |
|---|---|
| Desktop catalogue, 1440 px | [Desktop catalogue](../output/playwright/desktop-catalogue.png) |
| Phone catalogue, 390 px | [Mobile catalogue](../output/playwright/mobile-catalogue.png) |
| Tablet catalogue, 768 px | [Tablet catalogue](../output/playwright/tablet-catalogue.png) |
| Desktop document detail | [Desktop document](../output/playwright/desktop-document.png) |
| Phone document detail | [Mobile document](../output/playwright/mobile-document.png) |
| About and MIT licence | [Desktop About](../output/playwright/desktop-about.png) |
| Modern private manager | [Desktop manager](../output/playwright/desktop-manager.png) |
| Modern private manager on a phone | [Mobile manager](../output/playwright/mobile-manager.png) |
| Modern document editor | [Desktop editor](../output/playwright/desktop-manager-document.png) |
| Modern document editor on a phone | [Mobile editor](../output/playwright/mobile-manager-document.png) |
| Library section and documents | [Desktop section](../output/playwright/desktop-section.png) |
| Working local AI passage search | [Desktop AI search](../output/playwright/desktop-ai-search.png) |
| Working local AI passage search on a phone | [Mobile AI search](../output/playwright/mobile-ai-search.png) |
| 5,000-record catalogue overview | [Desktop scale catalogue](../output/playwright/desktop-scale-catalogue.png) |
| 5,000-record catalogue on a phone | [Mobile scale catalogue](../output/playwright/mobile-scale-catalogue.png) |
| Private draft rebuild confirmation | [Reindex scope](../output/playwright/desktop-reindex-dialog.png) |
| Changed original and blocked draft rebuild | [Stale document](../output/playwright/desktop-index-stale.png) |

## Limits

The dependency audit still reports 100 inherited npm vulnerabilities, and builds
warn about bundle size and old Browserslist data. Backend tests report inherited
naive timestamp warnings. The retained Material UI dialog also emits an inherited
focus-transfer warning, despite passing keyboard open/close and responsive checks.
Curator metadata tables scroll horizontally within their view on phones; the
page and document dialog do not overflow. These checks do not establish production readiness.
The modern manager uses scoped English language resources and the selected shell
locale; advanced legacy form text remains English. Visitors search metadata; private
curators can search indexed document passages. The existing importer limits a
reviewed snapshot to 128 PDFs in the current station runtime; the adapter follows
that shared limit. The 5,000-record fixture is a catalogue scalability
check, not a 5,000-document index. Private draft indexing does not establish expert approval or
activate the Oasis chat reader. Remote management authentication remains a separate
follow-up. PDF page count is reported only when backed by a verified draft index.
See [separate follow-ups](OASIS_LIBRARY_FOLLOW_UPS.md) and
[the architecture](OASIS_LIBRARY_ARCHITECTURE.md). The
[management guide](OASIS_LIBRARY_MANAGEMENT.md) explains real authoring persistence,
global document edits, version-scoped memberships and the private indexing adapter.
