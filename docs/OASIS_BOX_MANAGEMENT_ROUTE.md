# Management on the box

The physical box's curator address is `https://box001.kuwala.space/manage/`.
The existing Django staff username/password stays in place behind the separate
Cloudflare management gate. This is the same catalogue and original files; URL
changes do not create another library or migrate document identities.

The application supports two explicit device profiles:

| Setting | Root profile | Box profile |
| --- | --- | --- |
| `OASIS_DEVICE_BASE_PATH` | empty | `/manage` |
| Home | `/` | `/manage/` |
| Login | `/accounts/login/` | `/manage/accounts/login/` |
| API | `/api/…` | `/manage/api/…` |
| Originals | `/media/…` | `/manage/media/…` |
| Static assets | `/static/…` | `/manage/static/…` |
| Session and CSRF cookie path | `/` | `/manage/` |

Configure the private device environment with:

```ini
OASIS_DEVICE_ADMIN_PUBLIC_ORIGIN=https://box001.kuwala.space
OASIS_DEVICE_BASE_PATH=/manage
```

The public-origin setting is an origin only; the path has its own strict setting.
The proxy must route `/manage` and `/manage/…` to the existing private curator
forward, preserving the complete path. `/manage` redirects to `/manage/` before
rendering, retaining its query string. The hostname root continues to the
visitor interface. Root `/api/`, `/media/` and `/accounts/` routes must not be
forwarded to management as compatibility aliases.

Django mounts the existing URLconf beneath `/manage`. It does not trust
`X-Script-Name`, `X-Forwarded-Prefix` or arbitrary `SCRIPT_NAME` values, and the
proxy does not rewrite HTML. Named login/logout/password and original-page links
retain the mount. The same frontend build uses local relative startup assets and
a server-declared application base for API requests, originals and lazy assets.
Query-based navigation keeps the selected library, section and document.

Session and CSRF cookies remain host-only, HttpOnly and SameSite Strict, with
Secure applied on the explicitly trusted HTTPS proxy origin. Their path is scoped
to `/manage/`. Login return URLs cannot leave the manager mount. Existing
loopback-only peer checks, staff-session enforcement, CSRF validation and private
original-file restrictions remain enabled. The Cloudflare application/connector
must protect the complete manager path with its own management audience before
that path is routed; visitor authorization must not grant curator access.

Local development uses the unchanged root preview. A device configured with the
mount also uses `/manage/` through its private SSH forward. The explicit empty
mount profile remains available for older root installations. A rollback to code
that predates prefix support must restore its compatible root/origin settings as
well as the earlier verified release; changing the code pointer alone cannot make
an older release understand `/manage` or the new box hostname.

The release validator accepts strictly local `static/…` startup assets and the
earlier `/static/…` form, verifies each file against the staged manifest, and
requests the configured mounted health and static paths during readiness. No
database migration, user/password reset, catalogue transfer or index rebuild is
needed for this URL change. Follow the existing staged-release and rollback
transaction; these code changes alone do not configure DNS, Access or a proxy.

## Central library navigation and future packs

The manager header's **Central library** link opens
`https://library.kuwala.space/` in a new tab. It leads to source discovery and pack
draft preparation and requires internet access plus the central curator sign-in.
The mounted manager's **Open Oasis** link returns to the same box's `/` visitor
interface; the root-hosted manager keeps its existing cloud Oasis destination.

Pack downloading and installation still require the separate reviewed publication
and signed-pack workflow. Private central drafts are not distributable releases.
Connecting the box manager to that delivery API, authenticating box entitlements,
showing real available releases and applying approved packs locally is follow-up
work. This navigation change creates no download status, publication claim or new
ingestion/indexing pipeline.

## Verification

The prefix tests exercise real Django staff login, scoped cookies, logout and
password redirects; anonymous/API/media denials; multipart upload, stable-ID edit,
original retrieval, library export and deletion with synthetic originals; mounted
passage-page links; WhiteNoise paths; and the unchanged root profile. Frontend
tests exercise the actual URL helpers, modern/legacy request boundaries, startup
and runtime asset bases, and the two curator navigation links.

Before commissioning, run the normal production frontend build, frontend Node
tests, backend preview/device suites and release checks. Then verify the actual
Cloudflare gate, Django login, phone/desktop navigation and original-file access
at the box URL, and confirm the published visitor catalogue remains unchanged.
