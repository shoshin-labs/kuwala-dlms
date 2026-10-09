# Bring the main Oasis catalogue into Manage Library

Oasis has one logical collection: its authoritative authoring catalogue and the
immutable snapshot read by visitors and chat. A newly installed empty curator
does not yet contain those authoring records. Transfer the existing catalogue
with its original identities; do not upload its PDFs again under new IDs or seed
a second example collection.

This procedure transfers one selected DLMS version and its referenced records.
It preserves content, folder, version and metadata IDs, every authoring field,
original bytes, layout assets and the complete reviewed manifest. Other versions
and unrelated synthetic documents are excluded. The exported `solarspell.db`
alone is insufficient: it omits authoring notes, flags and dates.

The current collection is version `oasis-schooling-pdfs-v6-20261008` (authoring ID
6), with 85 originals and seven named libraries. Its numeric document IDs are
4–88 and folder IDs 16–22. Retain the manifest's independent public document and
library slug IDs too. Its private development testing scope and pending rights
and subject reviews remain in force. Copying a record or reusing an index does
not grant new publication rights or certify technical advice.

## Prepare and inspect a private transfer

From this checkout, read the authoritative SQLite database without changing it:

```sh
python3 scripts/prepare_oasis_catalogue.py \
  --database /absolute/source/state/evaluation.sqlite3 \
  --version-id 6 \
  --media-root /absolute/source/state/media \
  --manifest /absolute/reviewed/oasis-schooling-pdfs-v6-20261008-manifest.json \
  --output /absolute/private-transfer/catalogue-package.json
```

The output is a private, checksummed JSON package containing the selected Django
fixture, small embedded layout/module assets, original file inventory and the
reviewed manifest's unchanged bytes. It does not contain PDFs, authentication
users or credentials. Preparation checks SQLite integrity, actual source PDF
hashes and exact reviewed membership. It refuses to replace an existing package.
Keep this material out of Git and public web directories.

The device already has the originals and matching text/vector indexes. Stage a
private copy of the selected immutable snapshot under a new directory such as
`/opt/oasis-library/data/imports/<transfer>/published`. Copy only:

- `<snapshot>/manifest.json` and `<snapshot>/index.sqlite3`;
- `<snapshot>/content/<filename>` for every exact manifest original;
- `semantic/<snapshot>/vectors.sqlite3`;
- a relative `current` symlink naming that one direct `<snapshot>` directory.

The snapshot name must have the station's `v-` prefix. Verify each original SHA,
the manifest, index and vector hashes before and after copying, and confirm the
live pointer did not change during staging. Do not copy old failed imports or
locks. Set staged directories to mode 0700, files to 0600 and ownership to
`oasis-library`. Stage the package alongside that private copy. Do not change the
published snapshot, its ownership or the visitor gateway.

## Dry run, back up, then import

Deploy this exact green merged code using the
[existing release process](OASIS_DEVICE_DEPLOYMENT.md). The initial promotion
makes a verified before-image backup. Keep the worker off during transfer and
stop the private curator web unit before applying data changes. Confirm that no
manual process writes the curator database or media and that no indexing job is
running. The transfer must not race curator editing.

The Django command needs the same validated environment and service account as
the web unit. An SSH operator can invoke the existing release runner without
printing or sourcing its private env file:

```sh
cd /opt/oasis-library/current/app
sudo -n python3 -B - <<'PY'
from pathlib import Path
from deploy.target_release import Target

target = Target('/opt/oasis-library')
release = (target.base / 'current').resolve(strict=True)
runtime = (target.base / 'venv').resolve(strict=True)
staged = target.data / 'imports' / 'REPLACE_WITH_TRANSFER'
originals = (staged / 'published' / 'current').resolve(strict=True) / 'content'
target.manage(release, runtime, [
    'import_oasis_catalogue', '--package', str(staged / 'catalogue-package.json'),
    '--originals-dir', str(originals),
])
PY
```

This defaults to a dry run. The output goes to the private deployment log named
by the runner. Inspect its proposed document/library counts and identities.
Keep `-B` on root inspection/maintenance helpers: code releases are immutable,
and writing an import cache there correctly blocks their next verification.
Repeat with `--apply` only after the backup and dry run succeed. Add
`--replace-empty` only to remove an empty initial version/folder scaffold.
Neither flag authorizes replacing a nonempty catalogue. The command preserves
IDs and exact file names, commits records together, removes its new candidate
files on failure and refuses to overwrite existing originals or curator edits.
An exact successful repeat validates existing state and skips.

The unchanged review manifest and import receipt are saved under private
`data/catalogue-import`. Install that manifest into the root-owned operator
directory as mode 0640, group `oasis-library`, after verifying its recorded hash.
Set `OASIS_INDEXING_MANIFEST` in the private env to the root-owned copy. Keep its
existing scope, testing flags, attribution and review limitations intact. The
worker must not be able to change this review file.

## Reuse the verified index

After import, use the same `Target.manage` wrapper with these arguments:

```python
[
    'adopt_oasis_index', '--root', str(staged / 'published'),
    '--catalogue-version', '6',
]
```

The default dry run uses the installed station's validators to check complete
lexical and vector artifacts, every original, all manifest metadata and groups,
and the installed embedding model digest. Repeat with `--apply` to copy those
verified artifacts into a fresh private job directory. A successful adoption
receipt explicitly records that no extraction or embedding ran. Repeating the
command revalidates and skips the existing matching baseline. Partial adoption
fails without leaving a successful job or modifying the active reader.

Now promote the same verified code with `--worker on` through the existing
coordinator. It makes a new complete backup of the imported catalogue and
baseline, checks the adapter and starts the private web and worker units.
Backups preserve the validated internal `draft/current` pointer; other links in
state and all links in code releases remain forbidden.

Check Manage Library's total count, all seven memberships, document metadata,
original downloads and separate PDF-text/semantic statuses. Check the reader's
document identities, rights notes, original and membership fingerprints again.
The 71,375,120-byte Student Success original must remain usable; the curator and
station both permit up to 80 MiB per PDF and 128 PDFs per reviewed snapshot.

## Subsequent changes

Upload, replace, organise or delete documents in this main catalogue. Reindex
document/library actions use the existing durable worker; their confirmation
states that the current implementation builds the full reviewed catalogue.
Changed originals become stale. Newly added, replaced or removed documents and
changed reviewed memberships require an updated explicit manifest before a
build. The worker does not silently approve them.

Visitors continue reading the last verified snapshot while curators edit and
build. Publish the reviewed result using the existing station data-release
process, retaining the previous snapshot for rollback. This is the same logical
Oasis collection at different revisions, not a second independent library.
The transfer adds no public writes. Device management uses the separately
configured [administrator login and private access](OASIS_CURATOR_ACCESS.md).

## Checks

```sh
.venv/bin/python -W ignore::RuntimeWarning manage.py test \
  content_management.test_oasis_catalogue_transfer \
  content_management.test_oasis_index_adoption \
  content_management.test_oasis_indexing \
  content_management.test_oasis_search --settings=dlms.preview_settings
python3 -m unittest discover -s deploy -p 'test_*.py'
```

The preview and both device-runtime CI jobs run the transfer and adoption tests.
