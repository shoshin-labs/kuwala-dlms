# Library capacity evidence — 11 October 2026

These are **synthetic component benchmarks**, supporting the
[trial exit plan](../../OASIS_LIBRARY_SCALE_PLAN.md). They do not certify 1,000 or
5,000 real PDFs, extraction/OCR, semantic relevance, AI answers, concurrency,
cold-start performance or production eligibility. No production limits changed.

## Catalogue requests on the development Mac

The Django preview used 1,000 and 5,000 explicitly labelled metadata records,
three libraries, twelve sections and one shared synthetic original PDF. Seven
connection-cold and seven steady samples covered eight cases at each size:
overview, first/second/last page, maximum page size, section, title search and a
scoped miss. All 224 total requests passed content, membership, pagination,
query-count and response-size checks.

| Steady median / p95, milliseconds | 1,000 records | 5,000 records |
|---|---:|---:|
| Overview | 1.94 / 2.09 | 7.07 / 7.14 |
| First 24 documents | 4.46 / 4.75 | 12.28 / 13.47 |
| Maximum 100 documents | 9.21 / 9.45 | 16.66 / 17.08 |
| One section | 3.00 / 3.43 | 3.70 / 4.34 |
| Metadata search | 2.61 / 2.66 | 7.44 / 7.60 |

Requests used three to six SQL queries. First-page JSON was 15,383 bytes; the
100-item response was 63,540 bytes at either size. These are in-process test-client
times with preview DEBUG/query capture, not browser or network latency.
“Connection-cold” reopens SQLite connections; it does not evict OS caches. Tiny
sample sets do not establish production tail latency. Raw validated samples:
[1,000 records](catalogue-1000.json) and [5,000 records](catalogue-5000.json).

## Native search and visitor rendering on the actual Jetson

The isolated harness streamed 221 artificial passages per document: 221,000 and
1,105,000 passages. Text is repetitive, vectors are 32 deterministic artificial
patterns at 768 dimensions, and no embedding/inference request was made. Queries
use the existing FTS5 schema/ranking and regular-table scalar cosine pattern.
The fixture does not run through the production importer or semantic startup
validator, which currently reject this capacity.

Runtime: aarch64, Python 3.12.3, SQLite 3.45.1, sqlite-vec 0.1.9, 8 MiB SQLite cache
per connection. Transient service limits were one CPU core, nice 19, 384 MiB
maximum/256 MiB high memory, idle I/O and 20 minutes maximum runtime. This reserved
resources for live services but can make storage/cache timings worse than an
unrestricted run. It measures a bounded capacity scenario, not an isolated-device
production latency promise. OS caches were not cleared.

| Component median, seconds, three samples | 1,000 PDFs | 5,000 PDFs |
|---|---:|---:|
| Hash both complete index files | 3.26 | 16.36 |
| Exact vector search, entire corpus | 2.41 | 12.25 |
| Exact vector search, one of seven libraries | 2.71 | 13.27 |
| Exact vector search, one document | 0.13 | 11.97 |
| Rare-word FTS, entire corpus | 0.003 | 0.012 |
| Common-word FTS, entire corpus | 0.255 | **3/3 timed out** |

At 5,000, common-word FTS timed out in all nine samples across whole-corpus,
one-library and one-document scopes. The 1.5-second interrupted durations are
**not successful response times**. Rare-word and no-hit FTS completed at both
sizes. Every completed query respected its permitted document IDs and ten-result
limit. Vector tests had a separate 15-second benchmark deadline, not a production
execution guarantee. Ties and artificial vectors cannot establish useful search.

The regular vector table lacks a document-scope index, so choosing one document
still requires a large scan. Narrowing the UI library alone will not resolve this
cost. File verification must move out of the repeated query path without weakening
validation; FTS ranking/scoping and vector access need their own measurements and
fixes. Query embeddings, subprocess/receipt verification and HTTP time add costs
not included above.

The actual deployed visitor route/template was also called with synthetic metadata
and no model or HTTP server. Choosing the all-documents synthetic library rendered
every document: 232,448 bytes at 1,000 and **1,084,448 bytes at 5,000**. Median server
render time was 15.23 / 156.41 ms. The overview rendered library cards only. These
HTML sizes justify pagination even when server render time looks small; browser
rendering and phone-network latency were not measured.

Fixtures occupied 352 MB lexical + 1.03 GB vectors at 1,000 and 1.75 GB lexical +
5.14 GB vectors at 5,000 (decimal units). They were built without PDF extraction
or model work. Total run time was 319.528 seconds, CPU time 235.951 seconds,
observed cgroup memory peak 269,217,792 bytes (256.75 MiB), swap peak zero.
Per-case Python RSS high-water marks are cumulative and exclude some charged
filesystem cache; they are not production semantic-startup memory measurements.

[Native raw results](jetson-native-search.json) retain every sample outcome,
including timeouts. The executed script's SHA-256 is recorded there. The final
script adds explicit closing of its preflight SQLite connection and the standard
median for even sample counts. The measured three-sample medians and fixture/query
logic are unchanged.

Before/after deployment inspections were identical: manager release, published
snapshot/model fingerprints, worker state and zero running index jobs. All five
checked live services retained their PIDs and zero restart counts. Synthetic
databases were removed after the run; only the private harness and small reports
remain. No app deployment, production index job or activation occurred.

## Reproduce safely

From a fork checkout with its documented preview dependencies installed:

```bash
.venv/bin/python scripts/benchmark_catalogue.py --documents 1000 --repeats 7
.venv/bin/python scripts/benchmark_catalogue.py --documents 5000 --repeats 7
.venv/bin/python -B -m unittest scripts/test_benchmark_catalogue.py scripts/test_benchmark_library_search.py
```

Catalogue fixtures stay under `.preview/scale-*`. Foreign, unmarked, incomplete
or linked state is refused before migration/writes. Use `--output-root
.preview/scale-another-run` for a fresh case. An existing verified synthetic
fixture may be reused; it cannot be reused with a different document count.

Native component measurements need Python 3.12 and sqlite-vec 0.1.9. Install these
only in an isolated benchmark environment, or reuse the station's existing
compatible environment. No Django or station dependency is needed unless the
optional visitor template measurement is requested.

```bash
python3.12 -m venv .preview/native-benchmark-venv
.preview/native-benchmark-venv/bin/python -m pip install sqlite-vec==0.1.9
.preview/native-benchmark-venv/bin/python scripts/benchmark_library_search.py \
  --output "$HOME/oasis-synthetic-scale-run-1" \
  --documents 1000 5000 --passages-per-document 221 --repeats 3
```

The output directory must be new, with no symlink ancestors. The harness checks
SQL parameter capacity, spare disk and Linux available memory, streams fixtures
one case at a time, checks build progress/deadlines and removes temporary databases
on ordinary completion/exceptions. It keeps a JSON report after each complete
case; an interrupted run with only one case is not a completed two-size test.
An external kill can leave labelled temporary fixtures to inspect and remove
manually. Never point the output at an existing catalogue or published snapshot.

For the Jetson measurement, the harness was copied into a fresh private directory
beneath `~/.local/share/kuwala-benchmarks`. This is the bounded execution recipe;
replace the fresh directory, unique unit suffix and inspected station release
path deliberately. The station source path is read only. Do not restart a service
or edit its environment to run this benchmark.

```bash
systemd-run --user --unit=oasis-library-scale-UNIQUE --collect --wait --pipe \
  -p MemoryMax=384M -p MemoryHigh=256M -p CPUQuota=100% -p Nice=19 \
  -p IOWeight=10 -p IOSchedulingClass=idle -p TasksMax=8 -p RuntimeMaxSec=1200 \
  /usr/bin/env PYTHONPATH=/opt/kuwala/data/trials/pdf-library-20261008/deps \
  /opt/kuwala/venv/bin/python \
  /home/brightadmin/.local/share/kuwala-benchmarks/FRESH/benchmark_library_search.py \
  --output /home/brightadmin/.local/share/kuwala-benchmarks/FRESH/results \
  --documents 1000 5000 --passages-per-document 221 --repeats 3 \
  --station-root /opt/kuwala/releases/397daf1450c53809a9a35332992703f3433f83c0/app
```

Run the small `--documents 14 --passages-per-document 4 --text-chars 200` case in
a separate fresh output directory before a large run on a different runtime.
Retain before/after live-state checks and resource readings. Do not clear global
caches, call models or build a production index as part of this component check.
