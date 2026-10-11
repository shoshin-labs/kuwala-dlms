# Oasis Library: leaving trial

11 October 2026. **Proposed delivery plan, not production qualification.**
Start with a supported 1,000-document library, then qualify 5,000 documents on
the actual Pi and Jetson. Keep one logical Oasis catalogue, grouped into libraries
and sections, with immutable published snapshots behind it. Internal release IDs
remain available for diagnostics and rollback; visitors do not choose versions.

This planning change adds isolated benchmarks and records the work required. It
does not raise installed limits, publish drafts, change authentication, remove the
station's development-only PDF guard, or deploy application code.

## Baseline and measured evidence

Read-only device inspection found 108 authoring records and 85 published PDFs:
11,426 pages and 18,802 passages. The current snapshot is
`v-58d5e0cf61af0153-2ed5069c`. Manager code is merge commit
`e024159abb500f4aae559c4b597cae7384cded2a`; the running station backend is
`397daf1450c53809a9a35332992703f3433f83c0`.

| Installed boundary | Current value | Required work |
|---|---:|---|
| Station documents per snapshot | 128 | Versioned capacity profile and importer/reader agreement |
| Manifest bytes | 256 KiB | Size budget independent of document count; current metadata is already substantial |
| Passages per document | 2,000 | Explicit long-PDF policy; report incomplete extraction |
| Semantic passages / artifact size | 32,000 / 256 MiB | Tested larger format, startup and query budgets |
| Catalogue transfer documents | 512 | Match export/import/reader constraints and compatibility tests |
| Manager document page | 24, maximum 100 | Keep bounded; add equivalent paging to the visitor reader |

The current station rejects its PDF profile outside development mode. Its manifest
reader also accepts private testing and pending rights review records. Removing
the guard requires enforcing publication eligibility first. Upload, `active`, a
successful index, and valid citations do not establish suitability for technical
advice.

See [benchmark evidence and reproduction](benchmarks/library-scale-2026-10-11/README.md)
for measured results. Catalogue measurements use labelled synthetic records on a
laptop; native FTS/vector component measurements use artificial passages and
vectors on the Jetson. Neither proves real-corpus ingestion or model quality.

## Capacity and hardware budget

The current mix averages approximately 221 passages and 7.71 MB of original PDF
per document. These are linear storage projections, not capacity guarantees.
Scanned documents, larger manuals and different metadata can change the totals.

| One published copy, decimal GB | 1,000 PDFs | 5,000 PDFs |
|---|---:|---:|
| Original PDFs | 7.71 | 38.56 |
| Lexical index at today's ratio | 0.47 | 2.35 |
| Vector database at today's ratio | 1.08 | 5.41 |
| Approximate total | 9.26 | 46.31 |
| Estimated passages | 221,200 | 1,106,000 |

768-dimensional float32 vectors alone occupy about 647 MiB at 1,000 documents
and 3.16 GiB at 5,000, before database, text or search-structure overhead. These
values describe stored vectors, not necessarily resident memory.

At inspection the Jetson had about 7.31 GiB RAM, 1.95 GiB available and 35.6 GiB
free on its current disk. One projected 5,000-document snapshot exceeds that free
space before staging, authoring originals, backups or rollback copies. Establish
a storage budget for active + incoming + previous snapshots, authoring revisions,
model files and off-device backups before a large import. Reserve at least 12 GiB
free on the current disk during isolated benchmarks. A storage upgrade remains a
separate decision; no hardware purchase or installation is included here.

The Pi had about 15.84 GiB RAM. Only its root filesystem was inspected (about
6.93 GiB free), not every possible data mount. Do not assume that the Pi has room
for a duplicate library. Keep the current Pi gateway, CPU query embedding service
and Jetson storage/inference responsibilities until measurements justify a change.

## Ordered implementation slices

### 1. Bound browsing and remove repeated verification work

Station PR: paginate `/library` with stable ordering, library and section filters,
bounded metadata responses and honest loading/error states. Keep all-library
navigation useful with thousands of PDFs and preserve multiple membership,
original links, attribution and last-updated dates. A normal page returns at most
24 documents; a request cannot bypass a hard maximum of 100.

Station and manager PRs: verify immutable artifacts at staging/activation and
reader startup, retain a verified snapshot handle, and invalidate caches on
explicit snapshot replacement. Avoid hashing entire index/vector files for each
question. Preserve detection of unexpected file changes and fail closed on an
invalid snapshot; caching must not turn an unverified replacement into a trusted
artifact. Tests must cover replacement, tampering and concurrent reads.

The manager currently starts a search subprocess and verifies scoped originals;
its 512-entry original-hash cache can churn above that scope. Measure this wrapper
separately and replace repeated full checks with bounded, snapshot-aware work.
Keep checksum validation at trust boundaries and validate opened originals.

Exit evidence: bounded first/last/search/section requests, unchanged stable IDs,
small mobile responses, and tests proving correct invalidation and scope isolation.

### 2. Establish a supported package and search capacity profile

Station PR, followed by matching fork adapters: document independent document,
page, passage, manifest, byte, memory and time budgets. Use explicit package schema
and capacity versions; importers and readers must reject unsupported profiles
before partial activation. Existing 128-document packages continue to work.
Do not increase one global constant and claim production capacity.
Stream artifact validation and keep passage/vector reads bounded during startup
and queries. Current semantic startup loads the full passage/vector corpus;
optimising queries alone cannot make a multi-gigabyte snapshot fit safely.

Align station, manager transfer and export constraints, including Unicode and long
filenames, generated slugs and library/section counts. Current transfer filenames
can exceed station limits; preparer and reader slug lengths also differ. Add
round-trip fixtures for these boundaries and preflight storage requirements.

Measure native retrieval, file verification, query embedding, manager wrapper and
HTTP/browser time separately. Keep FTS5 initially, evaluate its query plans and
rank strategy, and add a searchable document scope index where justified. SQLite
documents [FTS5 ranking and query support](https://www.sqlite.org/fts5.html).

Compare optimized exact vector search and a `vec0` KNN table before choosing an
approximate index. Test selected-library and section constraints inside candidate
selection; filtering only after a global top-k query can discard useful matches.
The [sqlite-vec KNN documentation](https://alexgarcia.xyz/sqlite-vec/features/knn.html)
describes both scalar brute-force queries and `vec0` searches. Check compatibility
with installed sqlite-vec 0.1.9; no automatic dependency upgrade is implied.

If exact search misses the latency/memory budget, benchmark compressed IVF/SQ/PQ
and other candidates against an exact oracle. A full-vector HNSW graph requires
additional memory beyond the stored vectors, so it is not the default for this
Jetson. Compare the [Faiss index memory trade-offs](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)
with measured build time, storage, scoped retrieval and recall. Keep model digest,
dimensions, prefixes, passage IDs and original hashes bound to each artifact.

Exit evidence: a pinned real corpus and query set; repeatable results at each
capacity; explicit failure/fallback states; tested compatibility and resource use.

### 3. Preserve document revisions and enforce publishing eligibility

Fork PR: keep a stable logical document ID while a replacement creates an
immutable revision. Retain original bytes, attribution, licence, source URL,
reviewer identity, review date/scope and history. Current authoring replacement
deletes the old authoring original after commit; published snapshots survive, but
this is insufficient as a revision/audit trail.

Separate permission to redistribute, editorial review and any specialist review
of the intended use. Bind decisions to exact file hashes and relevant metadata.
Changing the file or publication-sensitive metadata invalidates the corresponding
review. Do not label an uploaded or indexed manual approved for technical advice.

Station + fork PRs: production preflight, activation and reader startup must all
reject pending, rejected and private-testing-only records. Keep today's test
permissions confined to the protected trial. Use existing Django users/groups
for curator/reviewer/publisher permissions when more operators are added. A sole
operator may review and publish, with explicit actions and an audit record.

Exit evidence: pending/testing documents cannot reach a production release,
replacement requires the appropriate new review, and old revisions remain
recoverable. These checks precede changing the development-only guard.

### 4. Make publishing and maintenance an operator workflow

Fork integration PRs should invoke the existing station maintenance/publisher
commands through a bounded authenticated worker. Keep one ingestion/vector
pipeline. Upload privately, review, build an inactive candidate, verify, then
explicitly publish. “Indexed” and “published” are separate states.

Expose queued/running/failed/stale/current states backed by real receipts. Resume
or retry failed maintenance without changing the active library. Reuse unchanged
extracted pages/vectors only when original hash, extractor settings and model
bindings match. Reindex a document or selected library without a synchronous web
request or an unnecessary rebuild of every unchanged document.

Use atomic activation, a pinned snapshot per request, health checks, an actor and
release receipt, and rollback to a verified prior snapshot. Failed validation,
disk exhaustion, interrupted jobs or a restart cannot leave a partial `current`.
Imports/exports must round-trip libraries, sections, membership, provenance and
rights; an archive import does not confer approval.

Keep ordinary manage actions prominent and advanced diagnostics behind Tools.
Retain the Open Oasis link for testing published changes. Review upload, edit,
replace, move, delete, section/library management, transfer and publish on phone
and desktop; confirm destructive actions in context and explain affected items.

### 5. Prove offline operation, recovery and supported releases

Operations PRs: retain Cloudflare Access for public origins and Django staff
sessions for management. Cloudflare email verification requires internet; provide
the existing documented private LAN/SSH administrator route for offline work,
with no public bypass. Rotate the trial administrator password before production
handover and keep secrets outside bundles/logs. No new authentication scheme.

Validate a cold boot with WAN disconnected and the curator unavailable: browse
libraries/sections, search local text, open passages and original PDFs, and use
local semantic search when its model is present. Distinguish unavailable models,
timeouts, scans needing OCR, extraction failure and genuine empty results.

Exercise restore of authoring DB + originals + review/history + worker state,
then restore a published snapshot and roll back an activation. Store an encrypted
backup on a separate device; record a timed restore drill. Define retention,
minimum free space, alert thresholds and safe cleanup of unreferenced artifacts.

Use the existing exact-commit CI, release bundles, staging, deployment receipts,
health verification and rollback for Pi/Jetson releases. Inventory supported
dependencies and security maintenance separately; keep Django/React for these
slices. A framework rewrite is not a prerequisite for usable library operations.

### 6. Qualify 1,000, then 5,000

Use representative, authorised real PDFs rather than duplicating fixture IDs.
Include large manuals, languages, shared memberships and differing section sizes.
Scanned/encrypted inputs are explicit rejection/error tests unless their extraction
support is delivered separately; they do not count as searchable documents.
Measure ingestion and embeddings in a maintenance
window; do not benchmark a new vector build against live chat without a resource
budget and rollback plan. Record startup and first-request time separately from
warm operation, and test sustained concurrency before increasing advertised use.

The following are **proposed acceptance targets**, to confirm against the first
real-corpus baseline. Missing a target requires a reviewed fix or revised capacity
promise, not an unreported limit change.

| Gate | Proposed acceptance |
|---|---|
| Catalogue | Server p95 ≤500 ms and LAN page p95 ≤1 s; 24 items normally, maximum 100 |
| Lexical search | p95 ≤1.5 s; real cancellation/recovery, timeout distinguishable from zero hits |
| Warm semantic/hybrid search | p95 ≤3 s at 1,000 / ≤5 s at 5,000, including Pi query embedding and wrapper/HTTP work |
| Approximate retrieval, if introduced | Mean recall@10 ≥0.95 within each global/library/section scope class, against nonempty exact-distance results using the same permitted scope and fixed tie handling |
| Correctness | No out-of-scope or unpublished hit; every returned citation opens the matching original/page |
| Resource coexistence | Initial aggregate search-service/cgroup target ≤512 MiB current/peak memory, including helpers, native allocations and charged cache; startup, activation and warm queries measured. Sustained Jetson MemAvailable ≥768 MiB with normal chat running; no OOM/restarts or sustained reclaim pressure |
| Multi-user operation | Measure 1, 2 and 4 simultaneous searches; bound queues, cancellation and overload explicitly |
| Recovery/offline | Successful WAN-off cold boot, curator-off reading, interrupted-build recovery, restore and rollback drills |
| Publishing | Eligibility enforced; actor/receipt and immutable revisions preserved; testing-only records rejected |

“Warm” means models resident and the verified snapshot loaded, with normal OS
caches. Count failures, timeouts and lexical fallback separately; a quick fallback
cannot pass the semantic latency gate. Use enough diverse queries and repetitions
for meaningful percentiles, rather than the three/seven samples in this initial
component check. Approximation recall measures similarity to an exact index, not
whether passages answer a user's question. Evaluate that relevance separately.

Trial exit covers library management, publication and reliable retrieval.
Deployment of technical/health advice requires its own content/use validation;
passing these library gates alone does not establish field readiness of AI answers.

## Scope deliberately deferred

The protected central repository and download/synchronisation of authorised PDFs
remain a later project, as requested. Keep export/import usable locally first.
Do not duplicate Oasis streaming, Jetson inference, translation or vector-job
pipelines, change public exposure policy, or install a new search service merely
because a benchmark is slow. Any new index format or service needs measured
benefit, reproducible deployment and a rollback path.

## Review and rollout

Deliver the ordered slices as small fork/station PRs with contract tests across
both repositories. Complete applicable CI on the exact release, stage privately,
verify backup and rollback, then run a controlled 1,000-document pilot. Publish a
measured capacity report before moving to 5,000. The current protected library
continues working while these candidates are built and reviewed.
