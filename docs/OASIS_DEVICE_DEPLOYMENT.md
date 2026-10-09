# Private Oasis Library device deployment

This procedure installs the curator on the Jetson through existing SSH access.
It does not deploy a public manager or replace the running visitor collection.
Application, authoring data, reviewed library releases and models have separate
lifecycles.

| Process | Host and existing route | Responsibility |
|---|---|---|
| Oasis station | Jetson loopback `3000`, existing Pi gateway `4175` | Normal chat and local sources |
| PDF library profile | Jetson loopback `4176` | Published catalogue, chat, passages and original PDFs |
| PDF visitor gateway | Pi forward `4177`, visitor gateway `4178`, existing tailnet listener `4179` | Existing visitor access only |
| Oasis Library curator | Jetson loopback `8790`, SSH local forward or private Tailscale `8443` | Staff-session files, metadata, libraries and draft search |
| Draft index worker | Jetson supervised process | Existing station import/vector commands into new private roots |

The commissioned PDF profile has been observed with **85 documents in seven
libraries, version v6**. Deployment records the actual running collection,
provenance, memberships and semantic configuration and requires them to remain
unchanged. The curator starts with a **blank catalogue** unless an operator has
explicitly installed authoring data. It does not import those 85 documents or
approve their reuse automatically.

The proposed `oasis.kuwala.space` address is not configured here. DNS, Funnel,
visitor credentials and public routing remain separate commissioning work.
The manager uses [standard Django staff login](OASIS_CURATOR_ACCESS.md) over
SSH forwarding or a separately configured private Tailscale HTTPS origin. Do
not forward its origin through either visitor gateway. Loopback, same-origin
and CSRF checks remain in force alongside authentication. No public curator
listener is installed by the release process.

Station code deployment is covered by [station release PR #166](https://github.com/shoshin-labs/kuwala-station/pull/166)
and its `docs/ALPHA_RELEASES.md`. Reader styling is covered by
[reader PR #164](https://github.com/shoshin-labs/kuwala-station/pull/164).
Use each repository's exact merged, green commit; curator deployment never
promotes station code, published library data or models.

## Persistent layout and runtime

| Path | Contents |
|---|---|
| `/opt/oasis-library/releases/<SHA>/app` | Immutable curator source, built frontend and collected local static assets |
| `/opt/oasis-library/current` | Selected curator release symlink |
| `/opt/oasis-library/runtimes/…`, `/opt/oasis-library/venv` | Pinned curator environment and selected runtime |
| `/opt/oasis-library/env` | Root-owned mode `0600` literal environment file |
| `/opt/oasis-library/operator/secret.key` | Stable mode `0600` secret, readable by `oasis-library` |
| `/opt/oasis-library/data/catalogue.sqlite3` | Authoring records and durable queued jobs |
| `/opt/oasis-library/data/media/contents` | Private originals |
| `/opt/oasis-library/data/builds` | Authoring exports |
| `/opt/oasis-library/data/indexing/jobs/<UUID>` | Independent private draft originals, indexes and receipts |
| `/opt/oasis-library/data/backups/<ID>` | Verified paired database/media/builds/indexing backup |
| `/opt/oasis-library/data/logs` | Private runtime and deployment diagnostics |

The dedicated service account owns the mode `0700` data root. State paths reject
symlinks, traversal and overlap with release code or `/opt/kuwala`. Device
settings require explicit paths and the stable secret file, ignore a source
`.env`, and set `DEBUG=False`. Gunicorn binds `127.0.0.1:8790`; WhiteNoise serves
collected local assets. Original-file routes remain loopback-only, reject unsafe
paths and serve active uploaded formats as downloads in a scriptless sandbox.

The curator uses `requirements-device.lock.txt` in its own ARM64 Python
environment. Python 3.10 and 3.12 are CI targets. The example below prepares
Python 3.12 wheels; first confirm that a matching Python already exists on the
Jetson. Do not copy a macOS venv or change the station environment to satisfy
curator dependencies. If no matching Python exists, stop and prepare a separately
reviewed runtime; this release tool does not upgrade system Python.

## First commission

Perform these commands once on the Jetson, using an existing operator SSH login.
Confirm the paths are unused by another application. If the account or secret
already exists, preserve it and inspect its ownership rather than recreating it.

```sh
uname -m
python3 -c 'import platform,sys; print(platform.machine(), sys.version.split()[0])'
getent passwd oasis-library
```

For a new account/layout:

```sh
sudo useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin oasis-library
sudo install -d -o root -g root -m 0755 /opt/oasis-library
sudo install -d -o root -g root -m 0711 /opt/oasis-library/operator
sudo install -d -o oasis-library -g oasis-library -m 0700 /opt/oasis-library/data
sudo python3 - <<'PY'
import os, pwd, secrets
account = pwd.getpwnam('oasis-library')
fd = os.open('/opt/oasis-library/operator/secret.key', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    os.fchown(output.fileno(), account.pw_uid, account.pw_gid)
    output.write(secrets.token_urlsafe(64) + '\n')
PY
```

The secret command refuses to overwrite a key and prints no secret. Keep a
private recovery copy of this stable file separately from code bundles and data
backups. Do not rotate it during an ordinary code release.

From the prep checkout, transfer the committed environment example, then install
and edit it on the Jetson:

```sh
scp deploy/device.env.example brightadmin@jetson001.local:oasis-device.env
```

```sh
sudo install -o root -g root -m 0600 oasis-device.env /opt/oasis-library/env
rm oasis-device.env
sudoedit /opt/oasis-library/env
```

Keep `DJANGO_SETTINGS_MODULE=dlms.device_settings`,
`OASIS_DEVICE_DATA_ROOT=/opt/oasis-library/data` and the secret-file path above.
Leave `OASIS_INDEXING_MANIFEST` empty initially and commission with the worker
off. Do not copy a preview database or run synthetic seed commands on the device.

## Build, inspect and stage

The prep computer needs Git, Python/pip, Node 22/npm, `gh`, SSH and `scp`, with
existing GitHub and SSH access. Build while GitHub/npm/package downloads are
available, then carry the verified bundle to offline targets.

On the prep computer, fetch the fork's `master` after merge. All applicable
GitHub Actions checks must succeed on the **same full merged SHA**: `preview`,
`device-runtime (3.10)` and `device-runtime (3.12)`. A green PR check does not
substitute for the merged commit's checks. The build tool enforces ancestry and
the latest exact-commit results.

```sh
git fetch origin master
OASIS_RELEASE_SHA=$(git rev-parse origin/master)
OASIS_DEVICE=brightadmin@jetson001.local
mkdir -p dist
git show "$OASIS_RELEASE_SHA:requirements-device.lock.txt" > "dist/requirements-device-$OASIS_RELEASE_SHA.lock.txt"
python3 -m pip download --only-binary=:all: --platform manylinux2014_aarch64 --implementation cp --python-version 312 --abi cp312 -r "dist/requirements-device-$OASIS_RELEASE_SHA.lock.txt" --dest "dist/wheels-aarch64-py312-$OASIS_RELEASE_SHA"
python3 deploy/release.py build --commit "$OASIS_RELEASE_SHA" --output dist --wheelhouse "dist/wheels-aarch64-py312-$OASIS_RELEASE_SHA" --target-python 3.12
python3 deploy/release.py check --jetson "$OASIS_DEVICE"
```

The read-only check runs through SSH stdin with the existing operator's
noninteractive sudo access, which is needed to inspect the private installed
database and transaction record. It does not upload files, migrate, restart
services or load Django. It inspects both existing Jetson status paths
on `3000` and `4176`, so those commissioned station profiles must be available.
The bundle includes exact source/asset hashes, a CI receipt and ARM64 wheels;
its `.tar.gz.sha256` sidecar protects transferred bytes. Keep both files.

Stage without selecting code or running migrations. Replace `/usr/bin/python3`
with the absolute path of the **verified existing Python 3.12** if necessary:

```sh
python3 deploy/release.py deploy --mode stage --jetson "$OASIS_DEVICE" --bundle "dist/oasis-library-$OASIS_RELEASE_SHA.tar.gz" --prepare-runtime --python /usr/bin/python3
```

Staging verifies the bundle and wheelhouse, prepares a separate pinned runtime,
runs Django checks, collects static assets and records the station fingerprint.
It does not seed content, run migrations, queue jobs or touch published library
roots. An already prepared matching curator runtime can omit `--prepare-runtime`.

For offline targets, carry the bundle **and** checksum from the connected prep
computer. Add `--offline` to stage/promote: it uses the bundled CI receipt and
cached merged Git tree without contacting GitHub. Installation uses the bundled
wheelhouse with `--no-index`; targets require neither npm nor internet access.
The prep machine still needs its cached source/ref and SSH access.

## Promote and private access

Start the first curator with its queue worker off:

```sh
python3 deploy/release.py deploy --mode promote --jetson "$OASIS_DEVICE" --bundle "dist/oasis-library-$OASIS_RELEASE_SHA.tar.gz" --prepare-runtime --python /usr/bin/python3 --worker off
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8796:127.0.0.1:8790 "$OASIS_DEVICE"
```

Open `http://127.0.0.1:8796/?workspace=curator&tab=contents` on the prep computer.
Sign in with the operator-provisioned active staff account; no default password
is included. The [administrator access guide](OASIS_CURATOR_ACCESS.md) covers
password changes and optional private phone access.
Local `8796` keeps the existing preview on `8790` separate. The production service
uses local assets and persistent originals, not Django `runserver`.

Promotion requests a unique maintenance nonce. An active worker must finish its
current job and acknowledge idle maintenance with a fresh heartbeat and its
actual systemd MainPID before it is stopped. Running jobs, unacknowledged/manual
workers and changed station fingerprints block the transaction. Queued requests
remain queued. Other processes must not write this curator database/media during
deployment.
If a job is running, leave the requested maintenance in place, let it finish and
retry; the deployment does not terminate that job.

With web and worker idle, promotion verifies a complete backup of SQLite,
media, builds and indexing state, then migrates, selects the exact code/runtime
and starts the web unit. Readiness checks the actual process release directory,
served asset bytes, private config and unchanged station collection. The printed
backup ID and `/opt/oasis-library/release-state.json` identify the transaction.
`--worker preserve` is the default for later releases; explicit `on`/`off` are
operator choices.

## Configure the existing index adapter

Set these literal values in the private device env only after reviewing the
real catalogue and manifest:

```ini
OASIS_INDEXING_STATION_ROOT=/opt/kuwala/current/app
OASIS_INDEXING_PYTHON=/opt/kuwala/venv/bin/python
OASIS_INDEXING_MANIFEST=/opt/oasis-library/operator/reviewed-manifest.json
OASIS_INDEXING_MODEL=nomic-embed-text:latest
OASIS_INDEXING_EMBED_URL=http://127.0.0.1:11434
OASIS_INDEXING_DEPENDENCY_PATH=/opt/REPLACE_WITH_REVIEWED_EXISTING_PDF_DEPENDENCIES
```

The dependency path is optional when the existing station venv already contains
its PDF packages. Use the real on-device directory, not the placeholder. It
must be readable/traversable by `oasis-library` and usable with systemd
`ProtectHome=true`: keep the station runtime, dependency directory, manifest and
secret under `/opt`, outside `/home`, `/root` and `/run/user`. A private directory
belonging to another service account
may not be accessible; resolve that with a reviewed runtime/permission change,
without broadening access to station data or silently installing packages.

Install an operator-reviewed manifest for this authoring catalogue as a root-owned
file readable by the service account, then set its exact path in the private env:

```sh
sudo install -o root -g oasis-library -m 0640 reviewed-manifest.json /opt/oasis-library/operator/reviewed-manifest.json
sudoedit /opt/oasis-library/env
```

Use that catalogue's actual stable IDs, version, filenames and hashes. When
transferring the existing main Oasis catalogue, preserve its authoring records
and explicit reviewed manifest together; the transfer verifies their exact
identity and membership. A published collection with different records does not
approve new authoring files. The worker must not be able to rewrite the review file.

Worker enablement runs the existing adapter's read-only configuration/manifest
probe under the curator account before service changes. It pins the configured
station release, validates the explicit review manifest, imports existing PDF
dependencies and checks only loopback model availability. It does not extract,
embed, download models or activate an index. Vector unavailability permits
lexical operation and is shown explicitly. Commission the worker using the same
promote command with `--worker on` once this preflight succeeds. Repeating
promotion for the same SHA is supported: it re-verifies the staged release and
records a new current before-image and backup before changing worker state.

Jobs still validate exact IDs, filenames, original hashes and complete manifest
coverage before invoking the existing station commands. They use new UUID roots
under `/opt/oasis-library/data/indexing`; failed jobs preserve previously ready
drafts and every published root. The current station bound is **128 PDFs per
reviewed snapshot** and **80 MiB per original**, including curator draft access.
Metadata pagination can contain thousands of records without claiming an index
of that size. Use the [main catalogue transfer](OASIS_CATALOGUE_TRANSFER.md) to
bring existing documents and a verified index into management. Schedule embedding
work around visitor chat load.

Publication remains an explicit separate station operation using reviewed
immutable exports and the existing station importer/vector/profile procedure;
see [the station PDF library guide](https://github.com/shoshin-labs/kuwala-station/blob/main/docs/PDF_LIBRARY_ALPHA.md).
Code release alone does not publish a library. Upload,
the upstream active flag, a review date or a successful draft job does not grant
rights or approve technical advice. Preserve source, author, licence, original
bytes and page links. This deployment never changes the station's published
pointer or turns a private draft into a visitor source.

## Failure recovery and checks

A failed migration/readiness leaves the curator stopped and the transaction
marked failed. Do not restart it against mismatched code/schema or retry another
promotion. Use the exact failed transaction SHA and printed backup ID:

```sh
OASIS_BACKUP_ID=REPLACE_WITH_PRINTED_BACKUP_ID
python3 deploy/release.py deploy --mode rollback --jetson "$OASIS_DEVICE" --sha "$OASIS_RELEASE_SHA" --backup "$OASIS_BACKUP_ID" --restore-state
```

`--restore-state` explicitly replaces database, media, exports and draft artifacts
with the verified before-image. **Edits and jobs made after that backup are
removed from the restored state.** The tool first saves a separate rescue backup
of the current state and prints its ID. It restores paired code/runtime/data and
the prior worker enabled state; first-install recovery returns to no active
curator. Preserve both backups and the secret for operator recovery. An
interrupted restore remains marked restoring and can be retried against the same
verified transaction; never edit backup files to bypass verification.

After promotion/recovery, use the read-only inventory command and SSH-forwarded
manager to verify libraries, one original PDF and metadata. Through the existing
password visitor gateway, an operator should also browse a published library,
open a passage/original page, check original GET/HEAD and ask a bounded chat
question using existing access. A 401 challenge proves the gate, not an
authenticated end-to-end session. Preserve the existing public/tailnet routes
and credentials; this procedure does not commission a new subdomain.

## Local validation for this change

The device backend passed 76 tests, production Webpack build, `pip check` and
migration-drift checks; 28 stdlib release tests passed. A disposable `DEBUG=False`
Gunicorn HTTP smoke created
two libraries, uploaded a labelled test original, verified multiple memberships,
original bytes and export, replaced it with the same stable document ID and
deleted it. Those fixtures were isolated from device data.

Station release validation passed 831 tests; reader styling passed 823 tests
and has desktop/mobile screenshots in its linked PR. These are local checks,
not a device promotion, physical reboot test or hardware capacity benchmark.
The new read-only inventory command also ran on the Jetson through SSH stdin:
curator/worker units were absent, `current` was unset and there were no curator
jobs; the existing PDF profile reported 85 documents in v6 with Nomic available.
No curator device code was installed. The live station SHA is read afresh for
each transaction rather than hardcoded in this runbook.
Applicable CI must complete successfully on the exact merged commits before
any release. See the release-tool tests for first commission, paired backup,
failed-migration recovery and worker maintenance/rollback cases.
