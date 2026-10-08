# Oasis Library rebrand verification

Verified locally on 8 October 2026 using Node 26, npm 11, Python 3.13 and Chromium.
This PR retains React 16 / Material UI 4 / Webpack 4 and the existing Django data
model. The independently runnable preview uses the pinned runtime described in
[README](../README.md). It has its own database/media/build directories and port
8790. The evaluation on port 8787 continued returning HTTP 200 and was not changed.

## Changes

- Oasis wordmark, white/blue palette matching the active Oasis app, system fonts,
  responsive layouts, 48 px actions, keyboard focus, and restrained motion with a
  reduced-motion alternative. Old logo/icon navigation and blue table typography
  are removed. The visitor bundle is about 453 KiB; curator modules load separately.
- Visitors choose a root-folder library, browse deduplicated descendant documents,
  search their metadata, inspect source/author/rights and open local originals or
  numbered PDF pages. Multiple library membership and stable IDs are preserved.
- Separate private curator navigation reuses upload, metadata, folder/version and
  export screens. Default visitor requests cannot mutate data, including legacy
  GET clone/export URL variants. Explicit curator mode is loopback development only.
- About includes Oasis’s name expansion, SolarSPELL acknowledgement and the full
  upstream MIT text offline. LICENSE is unchanged. New strings live in resources;
  only English is offered until additional language packs are reviewed.

## Checks

| Check | Result |
|---|---|
| Production frontend build | Pass on Node 26, without legacy OpenSSL flags |
| Django system check | Pass, zero issues |
| Backend contract/access tests | 5 tests pass; upload, detail, M2M folders, originals, export and access cases |
| Migration drift | No changes detected |
| Diff whitespace / upstream licence | Clean; LICENSE unchanged, bundled MIT text matches |
| Library navigation | Farming / Water / Learning from API; Water record also appears in Learning |
| Metadata search | Matching results, no-match state and Clear search checked |
| Detail / original links | Local PDF opens; PDF-page action opens the original with `#page=1` |
| History / root navigation | Catalogue returns from detail to library choice; stable query IDs retained |
| Error / retry | Mocked folder HTTP 503 gives localised error; removing mock and Try again restores catalogue |
| Empty catalogue | Mocked empty API gives honest “No catalogue versions yet” state |
| Offline assets | External requests blocked during reload; zero external resources and no curator chunks requested by visitor |
| Responsive browsing | 1440 px desktop, 768 px tablet, 390 px phone; detail and About also fit 320 px without horizontal overflow |
| Touch targets | Visitor controls measured at least 48 px high |
| Keyboard / motion | Skip-to-content receives a visible focus outline; reduced-motion view animation is none |
| About | Expansion and offline upstream MIT text verified |
| Curator browser upload/export | Upload saved, assigned to Farming, then exported successfully; local/exported original SHA-256 and rights/ID matched |

The upload/export API test checks the exported `solarspell.db` schema, shared
`content_folder` IDs, original-byte SHA-256, attribution/rights and local metadata
FTS. The browser check uploaded a labelled synthetic PDF, assigned it to Farming,
created a build, and verified the exported file’s bytes, document ID and rights.
The temporary browser-upload record was then deleted through the UI; the three
original seed documents remain. Curator row actions are labelled native buttons.

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
| Private curator documents | [Desktop curator](../output/playwright/desktop-curator.png) |
| Private curator on a phone | [Mobile curator](../output/playwright/mobile-curator.png) |
| Private curator document | [Desktop curator detail](../output/playwright/desktop-curator-document.png) |
| Private curator phone document | [Mobile curator detail](../output/playwright/mobile-curator-document.png) |

## Limits

The dependency audit still reports 100 inherited npm vulnerabilities, and builds
warn about bundle size and old Browserslist data. Backend tests report inherited
naive timestamp warnings. The retained Material UI dialog also emits an inherited
focus-transfer warning, despite passing keyboard open/close and responsive checks.
Curator metadata tables scroll horizontally within their view on phones; the
page and document dialog do not overflow. These checks do not establish production readiness.
Existing curator form text remains English. The catalogue searches metadata, not
document bodies; no indexing-state data, expert approval, publication activation
or remote management authentication has been added. PDF page count is not recorded.
See [separate follow-ups](OASIS_LIBRARY_FOLLOW_UPS.md) and
[the architecture](OASIS_LIBRARY_ARCHITECTURE.md).
