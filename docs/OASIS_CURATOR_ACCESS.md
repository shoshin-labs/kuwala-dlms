# Administrator access to Oasis Library

The device manager uses Django's standard password hashing, staff accounts and
server-side sessions. An account must be authenticated, active and marked as
staff. Authoring `content_management.User` records are attribution records and
do not grant login access. The operator provisions the administrator through
Django's existing `createsuperuser` command under the pinned curator runtime
and validated private device environment. Supply passwords interactively or
through private stdin; never put them in command arguments, source, deployment
logs or Git. No default account or password is shipped. Change a temporary
password using **Change password** after signing in.

This changes device access only. The isolated local development preview keeps
its existing explicitly enabled loopback workflow. The deployed device requires
staff sessions by default; an environment flag cannot turn that requirement off.

## Current private manager

With the existing SSH connection running, open:

`http://127.0.0.1:8796/?workspace=curator&tab=contents`

The browser will open the administrator login. The connection forwards only
local `8796` to Jetson loopback `8790`:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8796:127.0.0.1:8790 brightadmin@jetson001.local
```

Login is at `/accounts/login/`. Logout requires a CSRF-protected POST, available
through **Sign out**. Password changes use Django's current-password check,
password validators and session rotation. Sessions expire after four hours or
when the browser session ends. All manager HTML, catalogue and legacy APIs,
exports, uploaded media and private draft search/original routes require the
staff session. The exceptions are local static files, the login form and
`/healthz`, which returns only readiness and the requirement to authenticate.
Anonymous APIs return an empty error envelope, with no catalogue or job data.

## Optional private phone access

Use a separate private Tailscale Serve listener. The visitor gateway on HTTPS
`443`, its Cloudflare route and its existing published reader remain unchanged.
The curator must not be added to that visitor route allowlist.

Set one exact origin in the private device env before deploying the authenticated
runtime:

```ini
OASIS_DEVICE_ADMIN_ORIGIN=https://kuwala001.tailc01a0e.ts.net:8443
```

Only a canonical HTTPS Tailscale hostname with explicit port `8443` is accepted.
No wildcard, credential, path, query, fragment or alternative public hostname is
accepted. The optional value does not create a proxy or expose a listener.

After the operator has installed and verified the authenticated release, install
the tracked dedicated Pi user service from the exact verified release:

```sh
scp deploy/oasis-library-admin-forward.service brightadmin@kuwala001.local:oasis-library-admin-forward.service
ssh brightadmin@kuwala001.local 'mkdir -p ~/.config/systemd/user && install -m 0600 ~/oasis-library-admin-forward.service ~/.config/systemd/user/oasis-library-admin-forward.service && rm ~/oasis-library-admin-forward.service && systemctl --user daemon-reload && systemctl --user enable --now oasis-library-admin-forward.service'
```

Then configure the Pi's existing Tailscale operator account:

```sh
tailscale serve --bg --https=8443 --yes http://127.0.0.1:8792
tailscale serve status --json
```

Check that HTTPS `443` still targets `4178`, HTTPS `8443` targets `8792`, and
`AllowFunnel` is not enabled for `8443`. Use Serve, never Funnel, for this manager.
The phone must belong to the permitted tailnet and its access policy must allow
the connection. Open
`https://kuwala001.tailc01a0e.ts.net:8443/?workspace=curator&tab=contents`.
Remove only this listener with `tailscale serve --https=8443 off`; do not reset
the Serve configuration or change the existing visitor listener.

Tailscale's HTTP reverse proxy preserves Host and sends the HTTPS protocol
signal. Confirm those headers on the actual installed version during setup.
Django trusts `X-Forwarded-Proto: https` only from a direct loopback peer with
the exact configured Host including `8443`; it never trusts arbitrary forwarded
client addresses or Host headers. Missing or mismatched proxy signals fail
closed. HTTPS session and CSRF cookies are Secure, HttpOnly and SameSite Strict.
The SSH-localhost login remains available over the encrypted SSH connection.

Cookies do not distinguish ports. The manager uses separate cookie names, and
the existing visitor proxy does not forward cookies. The manager's explicit
same-origin and fetch-site checks still reject requests from the visitor's
`443` origin. SameSite cookies alone do not establish this boundary.
Safe top-level browser navigation to the manager shell and password pages is
permitted when following a link from the visitor page. This exception does not
apply to APIs, media, exports, legacy mutating GETs or any write.

## Deployment and verification

Use the [device release process](OASIS_DEVICE_DEPLOYMENT.md) and wait for an
active indexing job to finish its maintenance acknowledgement. Do not restart
or terminate the worker to install login support. Release readiness checks
`/healthz` and the exact locally served assets; rollback to an earlier release
uses that release's earlier readiness contract. Account hashes and sessions
remain in the backed-up persistent catalogue database. A matched state restore
also restores those account/session records; preserve the rescue backup and
follow the documented recovery procedure.

Before allowing phone access, verify anonymous manager/API/export/media/draft
requests fail, staff login works, a nonstaff account fails, missing/cross-origin
CSRF fails, external `next` redirects are rejected, logout invalidates the
session and private original downloads still match their recorded hashes.
Check that the visitor catalogue and its current published collection remain
unchanged. Uploading, indexing or administrator login does not approve technical
advice or publish private-testing documents.
