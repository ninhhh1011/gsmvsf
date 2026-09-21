# EV Charging and Battery Swap Station System

Python/FastAPI, PostgreSQL/PostGIS, Redis KV, GraphHopper 11.0 and Docker.

The project matches driver GPS to roads, determines energy-service demand, and
finds eligible station/service alternatives with road-network distance, ETA and
detour. Week 4 adds request-time ranking and recommendation from persisted
traffic, station and queue snapshots, with Redis as a validated payload cache.
Week 5 connects current driver location to the same recommendation endpoint and
adds finite causal replay, evaluation and a measured local latency baseline.
The [Week 5 report](docs/WEEK_5.md) records current acceptance evidence;
the [Week 4 report](docs/WEEK_4.md) preserves its frozen baseline;
the [migration report](docs/GRAPHHOPPER_MIGRATION_REPORT.md) preserves the prior
GraphHopper baseline. Production readiness remains NOT READY.

## Current runtime

GraphHopper is the sole routing and map-matching runtime. There is no engine
selector or fallback runtime. Mock adapters are test-only. Domain interfaces
remain independent of GraphHopper's HTTP schema.
The application lifespan owns one shared asynchronous HTTP client used by the
routing and matching adapters, and closes it on shutdown.

| Domain vehicle category | Routing and matching profile |
|---|---|
| `EV_CAR` | `car` |
| `EV_MOTORBIKE` | `motorcycle` |

OSM is canonical map data. GraphHopper imports the immutable
`dataset_v1/map/raw/hanoi-patched.osm.pbf`; `hanoi-baseline.osm.pbf` is reference
only. Generated graphs are stored under `runtime/graphhopper/gh-cache-11`.
The patched map contains `motorcar=no` on Cầu Thanh Trì way `881947000`.

The motorcycle model excludes motorways, penalizes trunk roads, and caps modeled
speed at 60 km/h. This is a project routing assumption, not a legal-speed claim.
It still uses GraphHopper's `car_access`: `motorcar=no` therefore also excludes
motorcycles, including on the patched bridge. Independent motorcycle access
semantics are not implemented. See [routing strategy](docs/ROUTING_STRATEGY.md).

## Setup and operation

Requirements: Python 3.11+, Docker/Compose, and the existing Python dependencies.
The GraphHopper image builds from the pinned official 11.0 JAR on Java 21;
release 11.0 requires Java 17+, not the development branch's Java 25.

Run from the repository root. Copy `.env.example` to `.env` and retain the host
URLs for host commands. Compose supplies container service URLs automatically.
In PowerShell, set `$env:DEBUG='false'`; in a POSIX shell, `export DEBUG=false`.

```bash
python -m pip install -e "backend[dev]"
python scripts/validate_frozen_dataset.py
docker compose up -d --build db graphhopper redis
# Wait for PostgreSQL and the GraphHopper import to become healthy.
python scripts/load_road_network.py
python -B scripts/load_week4_snapshots.py
# Configure SNAPSHOT_INGESTION_TOKEN in .env for internal state ingestion.
docker compose up -d --build api
```

`load_road_network.py` loads canonical directed road segments into PostGIS for
Dataset segment resolution. A running GraphHopper alone is insufficient for
application readiness. `/health` checks application liveness; `/ready` and
`/readiness` require both routing profiles and populated PostGIS road data.

Equivalent helpers include `make setup`, `make validate-data`, `make prepare-map`,
`make load-roads`, `make up`, `make test`, and `make smoke`. `make prepare-map`
builds/starts GraphHopper; no legacy preprocessing tools are required.

```bash
python -m pytest backend/tests -q --basetemp=runtime/migration/pytest
python scripts/smoke_test.py
python scripts/smoke_test_week3.py
python scripts/benchmark_week3.py --iterations 20
docker compose logs -f
docker compose down
```

Live smoke/benchmark commands fail when GraphHopper is unavailable. They never
substitute synthetic distances or mock matching. Generated verification evidence
is written under `runtime/migration`.

## API boundaries

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/map-match` | Batch GPS matching through GraphHopper and PostGIS resolution |
| `POST /api/v1/drivers/{driver_id}/location` | Realtime GPS ingestion and matching |
| `POST /api/v1/demand` | Week 2 demand evaluation |
| `POST /api/v1/candidate-search` | Evaluate every station/service alternative |
| `POST /api/v1/candidate-search/evaluate` | Demand evaluation followed by candidate search |
| `POST /api/v1/route` | Domain route request, including optional via points |

Routing uses the vehicle category, never a global default profile or an overriding
profile hint. Engine failures return 503, timeouts 504, invalid routing requests
422, and a standalone route with no road path 404. Candidate unreachability is a
business result only when there is actually no road route.

Map matching projects observations onto the actual GraphHopper matched path.
The returned quality score is geometric proximity, not a calibrated probability
or native GraphHopper observation confidence. PostGIS resolves Dataset segment
IDs from matched locations, OSM way details and traversal direction; unresolved
identities remain null. See [architecture](docs/ARCHITECTURE.md).
At ambiguous revisits, crossings or directed-segment ties, the response withholds
`road_segment_id` and `direction` and marks resolution `AMBIGUOUS`; a geometrically
matched location does not by itself establish a directed Dataset identity.

## Measured Week 3 baseline

The 2026-09-21 run used 20 distinct Dataset trip starts: five each for car charging,
fixed-battery motorcycle charging, explicit swap, and ANY/BOTH services. Four
warmup searches were excluded. Every measured search made 61 real GraphHopper
route calls; BOTH retained 60 station/service alternatives.

| Metric | Candidate service latency |
|---|---:|
| Median | 938.140 ms |
| P90 | 1,295.715 ms |
| P95 | 1,505.187 ms |
| Maximum | 1,707.856 ms |

These are `CandidateSearchService.search_candidates` measurements with an injected
shared HTTP client. Initial fixture/catalog loading and HTTP API overhead are
excluded; these are not production endpoint latency or concurrency guarantees.
Evidence: `runtime/migration/graphhopper-week3-benchmark.json` and
`runtime/migration/graphhopper-routing-smoke.json`. Details and historical results
are in [Week 3](docs/WEEK_3.md).

A separate deployed HTTP API run measured 20 candidate-search requests at each
concurrency level, including serialization and station search with the application
lifespan client. This is an initial local baseline, not a production capacity SLA.

| Concurrent requests | Median ms | P90 ms | P95 ms | Maximum ms |
|---|---:|---:|---:|---:|
| 1 | 777.228 | 896.463 | 955.799 | 1,354.926 |
| 5 | 2,384.797 | 2,917.589 | 2,945.508 | 2,974.883 |
| 10 | 6,621.727 | 7,337.150 | 7,358.554 | 7,477.629 |

`runtime/migration/api-smoke.json` records that endpoint benchmark and passing
car/fixed-bike/BOTH route, matching, candidate and realtime checks.
`api-outage.json` records an API configured with an unavailable GraphHopper:
route/matching/candidate calls return 503, realtime returns `ENGINE_UNAVAILABLE`,
liveness stays 200 and readiness returns 503. No mock fallback occurs.

The passing test distribution is Week 1: 37, Week 2: 69, Week 3: 71, migration:
62 (239 total). `runtime/migration/dataset-integrity.json` confirms all 63 Dataset
file hashes are unchanged. The deployed GraphHopper, PostgreSQL and API services
passed their live health/readiness checks.

## Data and scope rules

`dataset_v1/` is read-only. Both PBFs remain untouched. `make validate-data` invokes
`scripts/validate_frozen_dataset.py`, which runs the canonical validator while
redirecting generated reports to `runtime/migration/validation`; it does not
write reports into the frozen Dataset tree. The current canonical validator run (2026-09-21) reports 152 PASS / 0 FAIL
and 22/22 scenario assertions, superseding the older 163/21 count references.
Migration-quality acceptance remains tracked by its own execution gates.

Demand, candidate, recommendation, ranking-reference and map-matching labels
are evaluation-only. Runtime inputs and relationships are documented in
[DATA_CONTRACT](docs/DATA_CONTRACT.md).

The six-week sequence remains map matching, demand, candidates/routing, ranking,
realtime recommendation/evaluation, and productionization. The historical routing
migration preceded the Week 4 ranking and Week 5 integration described below.

The old Milestone 0 README described OSRM and four foundation tests. That is
historical evidence, superseded for current operation by this document and
[ADR-010](docs/DECISIONS.md#adr-010-graphhopper-as-the-sole-routing-and-matching-runtime).
Start further work with [AGENTS.md](AGENTS.md),
[PROJECT_SCOPE](docs/PROJECT_SCOPE.md), [ACCEPTANCE_CRITERIA](docs/ACCEPTANCE_CRITERIA.md),
and the [migration execution plan](docs/GRAPHHOPPER_FULL_MIGRATION_PLAN.md).

## Week 4 snapshot ranking

`POST /api/v1/recommend` synchronously runs Week 2 -> Week 3 -> Week 4.
`POST /api/v1/ranking/candidates` persists a versioned search result;
`POST /api/v1/ranking` ranks that search ID at an explicit request time.
Only eligible station/service alternatives are ranked. An eligibility-changing
snapshot returns structured HTTP 409 `CANDIDATE_STATE_CHANGED`; the full workflow
can repeat Candidate Search once. Ranking never silently drops invalid candidates.

Internal `/api/v1/internal/snapshots/{traffic,station,queue}` endpoints require
`X-Ingestion-Token`. Exact retry is safe; PostgreSQL retains history and Redis
cannot regress to an older latest state. Traffic/queue are project snapshots,
not external production live feeds. See [Week 4](docs/WEEK_4.md) for assumptions,
missing/stale handling, ETA definitions, setup, evaluation and performance.

```bash
python -B scripts/load_week4_snapshots.py
python -B scripts/evaluate_week4.py --output runtime/week4/evaluation.json
python -B scripts/verify_week4.py --smoke-only
# Full verifier ingests labelled September 3 demo state; run after evaluation.
# Provide --token-file pointing to a repository-local file containing your token.
python -B scripts/verify_week4.py --samples 10 --token-file runtime/week4/ingestion-token.txt
```

Use a new output path for each evaluation run; existing prediction artifacts
are never silently overwritten or reused against potentially changed state. Real PostgreSQL and
Redis are required by Week 4 integration tests. Logs, local secrets and large
prediction evidence stay in ignored `runtime/week4/`.

## Week 5 request-driven refresh and evaluation

`POST /api/v1/recommend` now accepts current Week 1 location when explicit paired
coordinates are omitted: valid matched position, then accepted raw GPS fallback,
then explicit location-unavailable failure when service is needed. Zero coordinates
remain explicit. Responses expose location provenance, stage timings and bounded
workflow call/conflict counts. Week 3 eligibility and Week 4 ranking stay unchanged.

The passing finite causal replay covers 30 trajectories and 308 recommendations;
the full backend suite has 347 passing tests. Latency was measured at concurrency
1/5/10 with 20 requests each and no invented SLA. [WEEK_5](docs/WEEK_5.md) contains
exact replay scope, evaluation denominators, failures, latency and reproduction
instructions. Historical replay requires an empty isolated PostgreSQL schema,
fresh driver state and a unique `SNAPSHOT_CACHE_PREFIX`; do not preload full future
snapshot history. Reports are checked in under `docs/reports/week5-*.json`, while
large predictions/logs and local secrets stay in ignored `runtime/week5/`.

Week 5 is request-driven, with no recommendation daemon or push/streaming system.
Production tuning and lifecycle persistence remain Week 6/future work.
