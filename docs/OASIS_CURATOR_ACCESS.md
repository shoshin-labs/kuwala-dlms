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

After the operator has installed and verified the authenticated release, use
the dedicated Pi SSH key at `~/.ssh/oasis-library-admin-forward` (mode `0600`).
For a first installation, create it on the Pi; retain an existing key:

```sh
ssh-keygen -t ed25519 -N '' -C oasis-library-admin-forward -f ~/.ssh/oasis-library-admin-forward
```

Use a separate Jetson service account, `oasis-curator-forward`, with a locked
password, no sudo membership and `/usr/sbin/nologin`. The account's public key
is root-owned at `/etc/ssh/authorized_keys/oasis-curator-forward`; its home is
not writable by the account. Its scoped SSH policy permits only TCP forwards
to `127.0.0.1:8790`, disables remote and Unix socket forwarding, and denies
shell, command and subsystem sessions. The Pi unit still uses the same private
key, `-F /dev/null` and `IdentitiesOnly=yes`. Never copy or log the private key.
Keep the existing verified Jetson host key in the Pi operator's `known_hosts`.

From this checkout on the operator's laptop, transfer only the public key and
the tracked policy to the Jetson:

```sh
scp brightadmin@kuwala001.local:.ssh/oasis-library-admin-forward.pub /tmp/oasis-library-admin-forward.pub
scp /tmp/oasis-library-admin-forward.pub brightadmin@jetson001.local:oasis-library-admin-forward.pub
scp deploy/sshd/90-oasis-library-admin-forward.conf brightadmin@jetson001.local:90-oasis-library-admin-forward.conf
```

For the first installation on the Jetson, keep an existing operator SSH session
open throughout. Stop if the account or either destination file already exists;
inspect the existing setup rather than overwriting it. Do not change the
operator account, its other keys, or the existing visitor forward:

```sh
sudo useradd --system --user-group --create-home --home-dir /var/lib/oasis-curator-forward --shell /usr/sbin/nologin oasis-curator-forward
sudo passwd --lock oasis-curator-forward
sudo chown root:root /var/lib/oasis-curator-forward
sudo chmod 0755 /var/lib/oasis-curator-forward
id oasis-curator-forward
sudo passwd --status oasis-curator-forward
ssh-keygen -lf ~/oasis-library-admin-forward.pub
sudo install -d -o root -g root -m 0755 /etc/ssh/authorized_keys
sudo install -o root -g root -m 0644 ~/oasis-library-admin-forward.pub /etc/ssh/authorized_keys/oasis-curator-forward
sudo install -o root -g root -m 0644 ~/90-oasis-library-admin-forward.conf /etc/ssh/sshd_config.d/90-oasis-library-admin-forward.conf
sudo /usr/sbin/sshd -t
```

The unique `90-` filename and trailing `Match all` make the intended scope
explicit, but the installed include ordering must still be checked. Confirm
`/etc/ssh/sshd_config` includes that directory, inspect earlier matching blocks,
and verify the effective settings before reloading. OpenSSH uses the first value
from matching blocks, so a successful syntax check alone is insufficient.
Substitute the Pi's actual source address as seen by the Jetson:

```sh
PI_ADDRESS='<Pi source address>'
sudo /usr/sbin/sshd -T -C "user=oasis-curator-forward,addr=${PI_ADDRESS},host=kuwala001.local"
sudo /usr/sbin/sshd -T -C "user=brightadmin,addr=${PI_ADDRESS},host=kuwala001.local"
```

For `oasis-curator-forward`, require `authenticationmethods publickey`,
`passwordauthentication no`, `kbdinteractiveauthentication no`,
`authorizedkeysfile /etc/ssh/authorized_keys/%u`, `forcecommand /usr/bin/false`,
`maxsessions 0`, `allowtcpforwarding local`, `permitopen 127.0.0.1:8790`,
`permitlisten none`, `allowstreamlocalforwarding no`, and `no` for TTY, user RC,
agent, X11 and tunnel permissions. Compare `brightadmin` against its captured
beforeimage, including the existing visitor key's effective connection settings.
Reload only after both checks pass:

```sh
sudo systemctl reload ssh
```

`MaxSessions 0` permits `ssh -N` forwarding while blocking shell and subsystem
sessions. A forced `/usr/bin/false` command supplies another session restriction.
`PermitListen none` is an **sshd configuration** setting; OpenSSH 9.6 does not
accept `permitlisten="none"` in `authorized_keys`. Key-only
`restrict,port-forwarding,permitopen=...` also does not constrain Unix socket
forwarding or disable command execution. See the official
[SSH server settings](https://man.openbsd.org/sshd_config#MaxSessions),
[key options](https://man.openbsd.org/sshd#AUTHORIZED_KEYS_FILE_FORMAT), and
[OpenSSH 9.6 key parser](https://github.com/openssh/openssh-portable/blob/V_9_6_P1/auth-options.c).

Then install the tracked dedicated Pi user service:

```sh
scp deploy/oasis-library-admin-forward.service brightadmin@kuwala001.local:oasis-library-admin-forward.service
ssh brightadmin@kuwala001.local 'mkdir -p ~/.config/systemd/user && install -m 0600 ~/oasis-library-admin-forward.service ~/.config/systemd/user/oasis-library-admin-forward.service && rm ~/oasis-library-admin-forward.service && systemctl --user daemon-reload && systemctl --user enable --now oasis-library-admin-forward.service'
```

On the Pi, confirm the unit connects as `oasis-curator-forward`, its loopback
`8792` forward returns the minimal Jetson `/healthz`, and an anonymous manager
API request returns `401`. Using this exact key with `IdentitiesOnly=yes`, verify
shell/command/SFTP, remote TCP, Unix socket and other TCP destination requests
are denied. Keep the operator session open until these checks pass. When moving
an existing installation, remove only this same public key from the Jetson
`brightadmin` account's `authorized_keys` after the new forward works; otherwise
the key retains its previous operator-account access. Do not remove the visitor
or operator keys. Store a private configuration/key beforeimage for recovery.

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
