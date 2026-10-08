# Private library management

Oasis Library is a working Django catalogue with a React interface. The optional
preview seed adds clearly labelled synthetic documents; it does not replace the
database with a mock API. Curator changes persist in the preview's own SQLite
database and media directory.

Start the independently runnable development preview with writes explicitly
enabled, then choose **Manage Library**:

```bash
npm --prefix frontend run build-prod
.venv/bin/python scripts/preview.py prepare
.venv/bin/python scripts/preview.py run --curator
```

Open `http://127.0.0.1:8790/?workspace=curator`. Default `run` is read-only;
`--curator` enables local development writes only. Management belongs on a private
operator origin. Loopback restrictions are not authentication for a proxy, LAN,
tailnet or public deployment. Visitor gateways must not forward management routes.

## Authoring model

A catalogue version contains named libraries. Each library is an existing root
`LibraryFolder`; descendant folders remain compatible with upstream organisation.
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
deletion. **Advanced tools** retains upstream metadata, version and export screens.

## Export and reindexing

An export creates local originals and `solarspell.db` with the existing IDs,
folder membership, rights and metadata FTS contract. Logos and banners are optional.
It does not activate a release or update Oasis chat's passage/vector indexes.

The existing Kuwala station maintenance commands remain the indexing route:

```bash
# Run from the station checkout, with an explicitly reviewed manifest and
# a NEW staging destination; these commands are not run by this fork's UI.
python -m scripts.import_pdf_library \
  --bundle /path/to/export \
  --manifest /path/to/reviewed-manifest.json \
  --destination /path/to/new-staging-library

# Run where the already installed local embedding model is available.
python -m scripts.index_pdf_vectors --root /path/to/new-staging-library
```

The importer validates original hashes and the review manifest, extracts pages
and builds the local passage/lexical index. The existing vector builder creates
the matching local semantic index. Station providers pin their snapshot at
startup; switching packages also requires restarting the reader runtime through
its existing release process. A replacement requires updated exact-file
hashes in that manifest; a deletion requires a new complete release without the
deleted document. Validate the complete new package before switching readers to
it, retaining the previous published package for rollback.

The current station manifest binds library membership to exact exported folder
IDs, while this fork's visitor catalogue also includes descendant folders. An
adapter must account for nested folders explicitly rather than claiming a
recursive visitor group is already an importer-compatible release manifest.

Job submission, persisted diagnostics, index freshness and publication/rollback
controls are a separate adapter to those existing commands. This fork does not
show a successful index status or a reindex button without that connection.
Uploading, an active flag or a recorded review date does not establish permission
for all uses or expert approval of technical advice. See the
[architecture](OASIS_LIBRARY_ARCHITECTURE.md) for that publication boundary.
