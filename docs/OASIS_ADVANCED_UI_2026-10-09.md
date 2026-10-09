# Advanced tools usability review — 9 October 2026

The previous manager cleanup left the upstream Advanced pages largely intact.
This pass reviews Workspace, Metadata, Library assets, Modules, Library versions,
Export builds and System information with the current Kuwala brand. The normal
manager now exposes library import/export, with version selectors hidden.

## Workflow and scope

The main manager has **Import library** and **Export library**. Export carries
one named library, its sections, original PDFs, authoring metadata and rights
records as a portable ZIP. Import first inspects the package without writes,
then requires an explicit review confirmation and a unique library name. It adds
records to the existing main catalogue, assigns fresh target IDs, and never
replaces existing originals or documents. Original source IDs remain in the
package; existing local IDs and Oasis API/export contracts are unchanged.

Normal curator and visitor screens hide catalogue version selectors. Advanced
navigation initially contains metadata, images, modules and host information.
**Show catalogue internals** reveals legacy Library versions and Export builds
only when requested. Empty catalogue setup creates the compatibility record
without asking the user to invent a version number. Existing bookmarked IDs
remain usable.

The internal Library versions page has readable full names, identifiers, creators
and dates, with **Open** and labelled **Actions**. Library/section controls appear
after opening a version. These compatibility tools do not publish to Oasis.

Inside a version, button breadcrumbs and named libraries/sections lead to
original documents. Unused folder selection is removed. Document row actions
operate on that row; an explicit toolbar handles selected documents. Removing
a document here removes its membership, retaining its original file. The
existing export picker rule remains: already-used documents appear when their
record permits duplicate placement (`duplicatable`).

Document moves establish the destination before removing source membership. If
the destination write fails, the source remains; if source removal fails, both
memberships remain and the form reports the error. Folder move/copy refuses
self/descendant destinations in the UI and server. Valid moves/copies retain the
existing response contracts, with transactional mutations and no schema change.

Forms validate required values, prevent duplicate submissions and retain input
on failed requests. Catalogue deletion clears the selected version's stale
frontend state. Shared Actions controls support keyboard navigation and visible
labels. Dialog actions update with their current state (including Move/Copy).
Phone navigation uses a labelled tool selector; fields and menus remain usable
at phone widths. Initial data failures show an error instead of empty catalogues.

Metadata uses accessible expand/collapse groups, labelled value actions and
readable forms. Assets and optional ZIP modules show clear empty states and file
controls. ZIP replacements and module upload references are corrected. Export
builds explains its local-only result. Disk information shows real reported
values, or an unavailable/error state with Refresh.

Authentication, published visitor collections, ingestion, model installation,
vector jobs and release activation are outside this UI change. A successful
upload, export or index does not approve technical advice or publication.

## Portable library packages

`GET /api/oasis/libraries/<root-library-id>/bundle/` downloads one library ZIP.
It contains `manifest.json` and `documents/<source-document-id>.pdf` originals.
The manifest format is `oasis-library-bundle`, schema version `1`. Its library,
folder parent IDs and document memberships describe a single complete tree;
document entries include byte sizes, SHA-256 checksums, source filenames,
catalogue fields and metadata type/value pairs. Rights, author/source metadata,
review/publication dates and the recorded last-update date are retained.

`POST /api/oasis/libraries/import/?dry_run=1` accepts multipart `bundle` and
`catalogue_version`, with an optional `library_name`. Inspection returns the
library/section/document counts and `bundle_sha256`, without database or media
writes. Confirmation posts the same file and target to `/api/oasis/libraries/import/`
with `confirmed=true`, the returned `expected_sha256` and a unique `library_name`.
The browser binds the review to its original target and requires a new review if
that target changes. Import creates a new library inside the current catalogue;
it does not create another catalogue version or merge over existing libraries.

Files receive collision-safe flat basenames compatible with existing original
links, exports and indexing source checks. `Transfer original filename` metadata
retains their previous names. Bundle source IDs are references for transfer, not
IDs to overwrite on the target. Partial SQL/filesystem writes are rolled back.
Transfers never create users, credentials, index jobs or published collections.

Current bounds are **80 MiB per ZIP and PDF**, **512 MiB expanded PDFs**,
**512 documents and folders**, 64 section levels, a 4 MiB manifest, 128 metadata
values per document and 8,192 values per bundle (including filename provenance).
Both export and import enforce the same bounds. This first format contains PDFs
and their catalogue records; logos, modules and search indexes are separate.
Very large libraries need a later streaming/chunked transfer design. The existing
Material UI/React framework remains; a dependency migration is a separate follow-up.

## Reproduce locally

Use the existing preview environment described in the README. Choose a dedicated
state directory, never the commissioned device data root:

```sh
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build-prod
export OASIS_PREVIEW_STATE_ROOT="$PWD/.preview/advanced-tools"
python scripts/preview.py prepare
python scripts/preview.py seed
OASIS_PREVIEW_CURATOR=1 python manage.py runserver 127.0.0.1:8801 --noreload --settings=dlms.preview_settings
```

Open `http://127.0.0.1:8801/?workspace=curator&tab=contents`, then Tools → Advanced
tools. The seed banner and example files are visibly synthetic and are not
community guidance. The preview binds loopback and does not replace evaluation
ports 8787/8790.

```sh
node --test frontend/scripts/test-document-updated.js frontend/scripts/test-brand.js frontend/scripts/test-version-move-safety.js frontend/scripts/test-advanced-state.js frontend/scripts/test-advanced-dialogs.js frontend/scripts/test-library-transfer-ui.js
python scripts/preview.py check
python scripts/preview.py test
python -m unittest discover -s deploy -p 'test_*.py'
```

The safety checks cover failed/partial transfers, folder cycles, invalid
endpoints, stable valid moves/copies, startup errors, copying an unopened version,
ZIP replacement, reviewed additive imports and package validation. Screenshots and
the PR record list the actual manual checks.

## Verification

The production frontend build and Django system check pass. Local verification
passed 163 Django tests, 31 frontend behavior tests and 36 release/rollback tests.
Webpack retains its existing large-bundle warnings; Advanced code is loaded on
demand. CI also checks the device runtime on Python 3.10 and 3.12.

In the isolated synthetic preview, the browser checked every retained Advanced
tab, required-name feedback, accessible field labels, section rename prefilling,
document membership moves, image upload, ZIP module upload/replacement, disk
refresh and a local legacy export build. Farming was downloaded through the
browser and imported after review into the same single catalogue. Its section
memberships, licence/author metadata and exact original PDF bytes survived; the
existing library remained intact and no indexing job was created. Original media
serving and compatibility with the existing export source validator/build were
also covered by integration tests. No production documents were imported or
edited during verification.
