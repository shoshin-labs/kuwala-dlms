# Future: protected central library and device downloads

Deferred requirement, recorded 8 October 2026. The immediate priority remains
getting the current local Pi/Jetson system working. This proposal does not add
hosting, authentication, DNS, downloads or another ingestion pipeline.

## Intended outcome

Maintain a protected central repository of all original document versions we are
authorised to retain, with their metadata and review history. When a Kuwala box
can connect to the internet, it should authenticate and download the authorised
PDFs/releases for its permitted libraries from our repository. A subdomain of
**kuwala.space** is a candidate; its address and implementation remain undecided.
The box must continue using its installed library without internet access.

## Requirements for the later planning pass

- Preserve original PDFs, stable document/version IDs, library memberships,
  source, author, licence, hashes and review records in a private historical
  archive. Distribution manifests include only explicitly authorised versions;
  boxes cannot retrieve drafts or rejected versions.
- Keep permission to retain/distribute separate from editorial publication and
  expert review of technical advice. Uploading, indexing or downloading does
  not establish approval.
- Authenticate enrolled devices and enforce their permitted libraries on the
  server. Plan human publishing roles, credential rotation, lost-device
  revocation and appropriate audit records before remote access.
- Download into bounded staging storage, with resumable transfers. Verify
  authenticity, hashes, versions and application/index/model compatibility.
  Activate a complete release atomically and retain a usable previous release.
- Preserve the current local library through network/authentication failures,
  incomplete or corrupt transfers, power loss, low storage and failed activation.
  Browsing, original PDFs, search and chat retrieval remain local.
- Define withdrawals, rights expiry and revocation on reconnection, including
  removal from visitor access. Instant revocation of an already downloaded copy
  cannot be guaranteed while its box is offline.
- Update library data, application code and models as separate transactions.
  Reuse the existing maintenance/publishing commands and immutable release
  contract rather than creating another extraction or vector pipeline.

## Decisions left open

Choose storage/hosting and the subdomain; human and device authentication/trust;
per-device library permissions and selection; whether compatible indexes are
downloaded or built locally; archive retention, device storage quotas and the
offline expiry/withdrawal policy. The central archive can grow independently
from the bounded releases installed on individual boxes.

Plan and test this as a separate milestone after the local system works. The
existing [library architecture](OASIS_LIBRARY_ARCHITECTURE.md) supplies the
immutable version, provenance and publication principles. The current
[device deployment process](OASIS_DEVICE_DEPLOYMENT.md) remains the immediate
operational path; central distribution is not a prerequisite for it.
