# Signed Box library packs

The Manage Library page includes a lazily loaded Library packs panel. It uses
the existing staff session, private-curator permissions and CSRF boundary, and
proxies only bounded commands to `/run/oasis-pack-installer/control.sock`.
There are no user-controlled paths, origins, shell commands or credentials.
The socket must have the reviewed kuwala:oasis-library identity and root-owned
parent; kernel peer identity is checked before sending an operation.

The companion kuwala-station pack maintenance release commissions the service,
publisher key and per-box entitlement privately. Until commissioned, the panel
reports unavailable and existing library functions continue normally. Deploy
this curator release only after exact-head and merged-commit preview and device
runtime CI pass, using the existing paired backup and preserved staff key.

Refresh, review rights and subject notes, select packs, acknowledge the reader
restart, then install. Lists replace bounded pages, selections persist across
pages, and obsolete responses are ignored. Polling is limited to active jobs.
Unknown POST outcomes are followed by a status read before offering another
action. The service owns resumable transfer, inactive indexing, verified atomic
activation, readiness checks, durable recovery and baseline rollback. The
curator cannot select an arbitrary rollback generation or replace station code.

The new controls require live signed-in acceptance on the Box. Unit tests use
synthetic sources and service responses; they do not prove model quality,
rights clearance, physical phone behaviour or real power-loss recovery.
