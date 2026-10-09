# Private library management

Oasis Knowledge is a working Django catalogue with a React interface. The optional
preview seed adds clearly labelled synthetic documents; it does not replace the
database with a mock API. Curator changes persist in the preview's own SQLite
database and media directory.

Start the independently runnable development preview with writes explicitly
enabled, then choose **Manage libraries**:

```bash
npm --prefix frontend run build-prod
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py run --curator
```

Open `http://127.0.0.1:8790/?workspace=curator`. Default `run` is read-only;
`--curator` enables local development writes only. Management belongs on a private
operator origin. Loopback restrictions are not authentication for a proxy, LAN,
tailnet or public deployment. Visitor gateways must not forward management routes.
The device runtime adds [standard administrator login](OASIS_CURATOR_ACCESS.md)
for its complete manager and private APIs. Development preview access is unchanged.

## Authoring model

A catalogue version contains named libraries. Each library is an existing root
`LibraryFolder`; descendant folders appear as sections. Create a library from the
overview or a section within the selected library/section. Both can be renamed or
removed. Their underlying folder IDs and parent relationships remain compatible
with upstream organisation.
`Content` records hold originals and metadata and can belong to several folders
and catalogue versions. Choosing a library in the visitor catalogue aggregates
its descendant documents and deduplicates stable numeric IDs.

The modern workspace uses existing version/folder/metadata APIs and an additive
`/api/oasis/documents/` endpoint for document writes. Original `/api/contents/`
contracts remain available to existing clients. Multipart document saves accept
`catalogue_version` and `folder_ids` (a JSON array string); JSON saves also accept
an array. Folder IDs must belong to that version. Document and membership changes
commit together; changing one version's membership preserves other versions.

Replacing an original keeps the logical `Content.id` and its memberships. This
is an authoring replacement, not an immutable published document version. Existing
export bundles are independent copies. Before publication, the separate release
workflow must bind the exact replacement hash, metadata and matching indexes.

Deleting a document removes that authoring record and its original from every
library. Removing a library removes its folders and memberships while retaining
the document records and originals. Previously exported bundles are unaffected
by either action. The interface confirms these different consequences before
deletion. The manager's **Tools → Advanced tools** menu opens the catalogue-wide
metadata, version and export screens in a separate dialog. They are loaded only
when requested and are no longer repeated below each library or section. Closing
the dialog refreshes the document workspace while retaining its selected location.
Library/section rename, delete and rebuild actions are grouped under the labelled
**Library actions** or **Section actions** menu. **New section**, **Upload document**,
document editing and original-file access remain visible. On phones, labelled
Library and Section selectors replace the long sidebar; nested section paths and
document counts remain available. The workspace opens at **All documents** by
default, and its catalogue version, library/section, metadata query and page are
retained in the URL for reloads and browser Back/Forward. Advanced tools restore
that manager URL when closed.

## Export and private draft indexing

The collapsed **Search maintenance** control below the document list contains
background rebuild status and job diagnostics. It stays closed until opened,
including while jobs run or fail; a short status remains visible when attention
is needed. A completed rebuild is shown inside the control and does not certify
that every current document is indexed. Each document keeps its own text/vector
freshness status and reindex action. Rebuilding prepares private manager search;
it does not publish changes to the visitor library.

## Choosing placement when importing

**Upload document** and **Import files** use the same Library → Section picker.
Choose the library first, then a child section. Section choices are limited to
that library and retain their nested path. **Library documents (no section)** is
valid when a document belongs directly to the library. **Add another library or
section** retains multiple memberships. Removing one placement does not remove
other placements or memberships in other catalogue versions.

**New section** in the document form creates a real child folder under the chosen
library or section and selects it for the document. The section remains in the
catalogue if the document form is cancelled. The standalone section dialog also
lets a curator select a library and parent section. Existing numeric folder IDs
and `LibraryFolder.parent` relationships are the source of truth.

New modern uploads require nonempty `folder_ids` and a matching
`catalogue_version`; omitted, empty, cross-version or invalid parent paths fail
before saving an original. Document edits retain their exact selected-version
folder IDs. A deliberate edit with an empty list clears that version's membership
while preserving originals and other versions, as in the existing API contract.

The batch spreadsheet importer applies its selected placements to every new
file. Use separate batches when documents need different placements. Its curator
API validates selection before any file is imported and rechecks/locks folders
before reporting each record successful. A blank original-file folder updates
existing metadata only and preserves existing membership. Legacy single-file
forms are retained in source/API for compatibility, while the modern workspace
provides the single and batch import UI. Advanced tools keeps metadata, versions,
assets, modules and export tools.

An export creates local originals and `solarspell.db` with the existing IDs,
folder membership, rights and metadata FTS contract. Logos and banners are optional.
Export alone does not update Oasis chat's passage/vector indexes.

Manage libraries shows **PDF text** and **Semantic vectors** separately. An indexed
status requires a successful build or explicit adoption of an existing index,
validation by the existing station reader and an
exact match with the current document ID, filename and original SHA-256. Replacing
an original makes the previous draft stale. Changed/corrupt artifacts are unavailable;
a failed rebuild retains the previous successful draft. These are private draft
states. An adopted baseline can be the same exact snapshot currently served by
Oasis chat. Subsequent curator edits remain drafts until publication.

For an existing Oasis collection, [transfer its authoritative authoring records](OASIS_CATALOGUE_TRANSFER.md)
and adopt the matching verified snapshot. This retains one main catalogue with
the same documents, named libraries, original IDs and rights notes in Manage
Library and the reader. Historical synthetic catalogue versions are excluded.

**Reindex document** and **Reindex library** queue durable jobs through
`/api/oasis/index-jobs/`. This initial worker rebuilds the complete selected
catalogue's enabled PDFs, including when requested for one document or library;
the confirmation states the scope and document count. Library actions include
PDFs in descendant folders. Each job exports to a fresh UUID directory under
the configured private indexing state directory (`.preview/indexing/jobs/` for
the preview, `/opt/oasis-library/data/indexing/jobs/` on the device), invokes the station's existing `import_pdf_library`
command and, for the optional hybrid profile, `index_pdf_vectors`. Existing
published/evaluation roots are never selected as destinations. Logs, timestamps,
queued/running/succeeded/failed states and worker heartbeat are real persisted data.

The adapter follows the station importer's shared limit, currently 128 PDFs per
reviewed snapshot. The catalogue
can browse thousands of records through server pagination; this worker does not
claim to index thousands in one build. Larger packages and incremental jobs remain
in the existing ingestion workstream.

For the supervised private device runtime, durable state, backups and recovery,
see [device deployment](OASIS_DEVICE_DEPLOYMENT.md).

The adapter requires an explicit reviewed manifest that covers exactly the
catalogue's enabled PDFs, with matching filenames and hashes. Uploading, an active
flag or a recorded review date does not automatically approve a manifest. A new,
replaced or removed PDF requires an updated manifest before another build.
Unassigned documents and non-PDF originals are not eligible for this importer.
The station manifest also binds library membership to exact exported folder IDs;
when including its optional library definitions, review nested membership explicitly.
For a hierarchical release, the additive manifest `sections` array declares each
section's stable slug, label, `library_id`, `dlms_folder_id`, `parent_id` (null for
a direct library child) and deduplicated descendant `document_ids`. Root library
`document_ids` also describes its full subtree. Empty sections are supported;
root library scopes must include at least one reviewed PDF. Declared folder labels, parents
and exact subtree memberships must match authoring/export before
indexing or transfer. Operational holding folders may remain undeclared, but all
descendants contribute to their declared ancestors’ exact scope. An undeclared
empty folder does not force a public section; an extra unpublished document in a
declared subtree rejects the reviewed scope. A legacy manifest without `sections` retains its prior
flat direct-folder validation.

## Configure the local worker

Use an existing station checkout and its already installed PDF maintenance runtime.
The paths below are this workstation's examples; configure your own explicit
reviewed manifest for real documents. Set the same values in both server and worker
terminals, then restart the preview:

```bash
export OASIS_INDEXING_STATION_ROOT=/Users/tom/Dev/kuwala-station
export OASIS_INDEXING_PYTHON=/Users/tom/Dev/kuwala-station/.venv/bin/python
export OASIS_INDEXING_MANIFEST=/absolute/path/to/reviewed-manifest.json
.venv/bin/python scripts/preview.py run --curator
```

In the worker terminal:

```bash
# Set the same three environment variables above first.
.venv/bin/python scripts/preview.py index-worker
# Alternatively, process one queued request and stop:
.venv/bin/python scripts/preview.py index-worker --once
```

Jobs can be queued while the worker is stopped; the interface explains that they
wait. One worker holds the private queue lock. A restarted worker marks interrupted
running jobs as failed rather than pretending they completed. The worker is a local
macOS/Linux development command, not a production process supervisor.

Text indexing requires the existing local PDF extractor. Semantic indexing also
requires an already installed embedding model and its local service. Optional
`OASIS_INDEXING_MODEL` defaults to `nomic-embed-text:latest` and
`OASIS_INDEXING_EMBED_URL` to `http://127.0.0.1:11434`. The adapter does not download
models. A missing model disables the hybrid profile with the actual reason.
Vector freshness also checks the model digest, so replacing a model under the
same tag does not preserve an indexed status incorrectly.

An operator can install the configured model explicitly before building vectors:

```bash
ollama pull nomic-embed-text:latest
```

This one-time download requires internet access. Keep the installed model and
local Ollama service available for subsequent offline semantic indexing/search.

For the disposable seeded preview only:

```bash
.venv/bin/python scripts/preview.py seed
.venv/bin/python scripts/preview.py index-fixtures
export OASIS_INDEXING_MANIFEST="$PWD/.preview/indexing/synthetic-reviewed-manifest.json"
```

`index-fixtures` accepts the generated synthetic seed corpus only. Its manifest
explicitly uses `private-development-testing`, `testing_only` and
`rights_review_pending`; it is not permission to publish or expert review of advice.
Do not use it to approve uploaded community documents.

## Search a private indexed draft

Manage libraries offers **Metadata**, **PDF text** and **AI semantic** search modes.
Metadata searches the current catalogue's document records. PDF text searches
passages in the latest successfully verified private draft through the existing
station `PdfLibrary` reader. AI semantic uses the existing `SemanticSearch` provider
and local embedding service, when matching vectors and the model are available.
It ranks passages; it does not generate answers or certify technical advice.

Text/AI searches run when submitted, with a 160-character query limit, at most ten
passages, a 20-second subprocess timeout and ten submitted searches per minute.
Library/section scope follows current folder memberships. Only documents whose
current original hash matches the indexed bytes are searched. Results retain
source, author, licence and page information; local PDF links are pinned to the
verified draft original so replacement cannot silently change an existing result.
A missing model, stale document, unavailable index or semantic provider failure is
reported explicitly. Keyword fallback is never labelled as AI semantic search.

These routes and draft originals are private curator endpoints. Visitor browsing
continues to search metadata. Public document-text/AI search needs a separately
configured approved immutable release; private testing manifests must not become
public search sources. Nomic was installed explicitly on the workstation, and both
PDF-text and semantic search were verified against the labelled synthetic draft.

## Activating a release

The importer validates hashes and review scope, extracts pages and builds local
passage/lexical search. The existing vector builder creates a matching semantic
index. Station providers pin their snapshot at startup; switching packages also
requires restarting the reader through its existing release process. Validate a
complete reviewed package before switching readers, retaining the previous
published package for rollback. A deletion requires a release without the deleted
document. This private worker does not switch the active reader, change Jetson
inference or duplicate those release/ingestion pipelines.

See the [architecture](OASIS_LIBRARY_ARCHITECTURE.md) for publication boundaries.
Uploading a document does not establish permission for every use or approval for
technical advice.
