# Week 5 - Realtime API + Evaluation

## Scope and contract

The official milestone is **Realtime API + Evaluation**: build the API, test
performance, and evaluate recommendations. The project owner's 2026-09-21
contract decisions are recorded in ADR-014 and the implementation plan.

Continuous recommendation means **request-driven refresh**. A replay or client
ingests a new observation/state and issues a new recommendation request. There
is no recommendation daemon, polling loop, event broker, push transport or
external live traffic feed.

```text
GPS/event -> Week 1 accepted driver state
         -> POST /api/v1/recommend (resolve current location)
         -> Week 2 EnergyServiceRequest
         -> Week 3 eligible station/service pairs
         -> Week 4 snapshot-aware ranking
         -> RecommendationResult
```

The existing /recommend endpoint evaluates demand, then RecommendationWorkflow
owns candidate search and ranking.
Week 5 adds a location bridge and evidence around that workflow. PostgreSQL
remains snapshot authority; Redis is an optional latest-state cache. Search
evidence and snapshot history remain the persistence contract. Week 5 does not
add a durable recommendation lifecycle or recommendation history table.

## Location and freshness

The shared location bridge uses supplied coordinates first, testing for `None`
so latitude or longitude `0.0` stays explicit. A partial coordinate pair is
invalid. Explicit coordinates do not inherit an unrelated cached road segment.

With no explicit position, the bridge uses the current Week 1 matched position,
then the latest accepted raw observation. Provenance distinguishes `EXPLICIT`,
`MATCHED`, `RAW_GPS_FALLBACK` and `LOCATION_UNAVAILABLE`. A raw fallback never
claims a map match. Location event time must be at or before request time.
Week 1 owns match validity and gap resets; no additional age threshold is added.

A service request that requires location fails explicitly when none is
available. A valid no-service decision keeps its existing short circuit.
Invalid explicit service requests retain Week 2 capability validation.

## Integration defects corrected

The candidate evaluate endpoint previously called nonexistent driver-state accessor
methods; it now reads the existing contract through the shared resolver. The
driver-demand bridge previously replaced explicit zero coordinates via truthiness;
all location bridge branches now distinguish `None`.

Real replay also exposed valid empty, zero-cost GraphHopper matching paths. These
now use the existing `MapMatchingNoMatchError`/`NO_MATCH` path; malformed geometry
and nonzero empty paths remain engine errors. The Week 1 trigger policy is unchanged.

## Historical replay

Replay is finite and ordered by event timestamps. It uses actual Dataset V1.3.1
trajectories, GPS, SOC/trip context and operational source snapshots. An isolated
PostgreSQL schema, a separate Redis prefix and fresh in-process driver state
prevent preloaded future latest state from entering historical inference.

At time T, only source events and snapshots at or before T are ingested. Match
state derives from accepted observations already processed. Search evidence and
recommendation provenance are checked against the same cutoff. Predictions are
written outside the frozen Dataset before evaluation opens reference labels.
One canonical source heading of `360.0` is normalized to the equivalent `0.0`
at the replay client wire boundary, with original/transmitted evidence recorded.
The Dataset and Week 1 `[0, 360)` validation contract remain unchanged.

## Refresh and invalidation

Each request recomputes from its current causal inputs. A refreshed result may
select the same station/service pair or a different pair. Neither outcome alone
proves or disproves refresh; request evidence and consumed state establish it.

Week 3 continues to own eligibility. Week 4 rejects an invalidated candidate set
with HTTP 409 `CANDIDATE_STATE_CHANGED`; it does not silently drop candidates.
Only RecommendationWorkflow may rerun search once and ranking once. A second
conflict propagates 409. Week 5 adds no retry loop.

## Evaluation and performance

Evaluation reports explicit denominators for recommendation presence, composite
station/service top-1, service type and meaningful pairwise comparisons. AUTO
reference comparisons and explicit service-intent checks are reported separately.
Labels are evaluation-only; runtime inputs and source selection exclude them.

Performance is an **INITIAL LOCAL WEEK 5 PERFORMANCE BASELINE**, not a production
SLA. Warmup, sample count, concurrency, cache conditions, runtime environment,
median/P90/P95/max and success/error counts accompany the measurements. Stage
timers identify location, demand, candidate search and ranking costs. No numeric
latency pass threshold is invented and no optimization is part of Week 5.

## Failure behavior and limits

Redis failure uses PostgreSQL fallback. PostgreSQL failure remains explicit even
with warm cache; GraphHopper failure is never hidden behind a mock or alternate
routing engine. Missing traffic and queue use the existing Week 4 degraded-state
policy. Stale GPS is rejected by the existing Week 1 acceptance policy.

Driver state is process-local and bounded. A historical request cannot reconstruct
arbitrary discarded driver history; the replay client must maintain causal order.
GraphHopper motorcycle routing shares `car_access`; independent motorcycle access
coverage is not claimed. Matching quality remains geometric proximity, not a
calibrated confidence score.

## Verification evidence

Verified on 2026-09-21 against real FastAPI, PostgreSQL 16.4/PostGIS 3.4,
Redis 7.4 and GraphHopper 11.0. Host replay/performance used Python 3.14.4 on
Windows 11 with eight logical CPUs; the deployed Docker API was also rebuilt
and its 56 Python source files matched the checkout by SHA-256.

| Gate | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| Full backend tests | 347 | 0 | 0 |
| New Week 5 test files, included above | 39 | 0 | 0 |
| Additional adapter regressions, included above | 6 | 0 | 0 |
| Canonical validator | 152 | 0 | 0 |
| Scenario assertions | 22 | 0 | 0 |
| Dataset file hash comparisons | 69 | 0 | 0 |
| Replay recommendation requests | 308 | 0 | 0 |
| Measured performance requests | 60 | 0 | 0 |

The hash inventory includes 63 canonical files and six pre-existing bytecode
files. Neither canonical PBF changed. No tests wrote Dataset reports; the
protected validator redirected them under `runtime/migration/validation`.

### Replay coverage and counters

[Replay evidence](reports/week5-replay.json) records 30 source-selected trajectories:
13 cars, nine charge-only motorcycles and eight swap-capable motorcycles. All
21 source scenario IDs are represented. This is a finite representative replay,
not a full-Dataset replay or every raw GPS point in each trajectory.

The schedule contains 1,712 actual GPS observations from source realtime events
plus decision-origin observations, and 240 SOC decisions (eight per trajectory).
It also makes 68 explicit intent requests: 30 CHARGING, 30 ANY and eight BATTERY_SWAP.
Thirty deliberately stale repeats are separate reliability probes.

| Counter | Observed |
|---|---:|
| Scheduled GPS/SOC events processed | 1,952 |
| Recommendation requests / candidate-search calls / ranking calls | 308 / 308 / 308 |
| Matched positions / explicit raw fallbacks | 284 / 24 |
| No-service short circuits | 56 |
| Zero-candidate results, including no-service | 148 |
| Zero candidates among service-needed requests | 92 |
| Changed / unchanged comparable refreshes | 14 / 196 |
| Stale observations correctly rejected | 30 |
| Valid no-match observations | 34 |
| North-heading wire normalizations | 1 |
| Natural conflicts / retry recoveries / second conflicts | 0 / 0 / 0 |
| GraphHopper dependency failures / total errors | 0 / 0 |
| Station / queue / traffic snapshots ingested causally | 930 / 930 / 262,691 |

Search/ranking counters count workflow calls, including existing no-service
short circuits. Controlled conflicts and outages are reported separately below.
At every decision the client checked database maximum timestamp, dedicated-cache
payload timestamps, returned snapshot/location provenance and persisted search
evidence against event time. Prediction SHA-256 is stored in the replay manifest.

Diagnostic runs remain outside Dataset: run `a` exposed pandas timestamp-unit
precision; run `b` completed with 35 reported errors (34 degenerate matching
misclassifications and one heading-boundary rejection). The corrected fresh run
`c` is the passing evidence. No failed results were overwritten or relabeled.

### Evaluation results

[Evaluation evidence](reports/week5-evaluation.json) compares the 240 AUTO
predictions with 184 matching reference events; 68 explicit-intent probes are
excluded from AUTO reference metrics. Labels were opened only after inference
completed and persisted prediction hashes were verified.

| Metric | Matches / denominator | Agreement |
|---|---:|---:|
| Recommendation presence | 167 / 184 | 90.76% |
| Overall station/service identity, including empty | 158 / 184 | 85.87% |
| Station/service top-1, reference-positive events | 85 / 95 | 89.47% |
| Service type, reference-positive events | 94 / 95 | 98.95% |
| Pairwise order on common pools | 1,102 / 1,224 | 90.03% |
| No-service requests returning no recommendation | 56 / 56 | 100% |

Pairwise comparison covers 70 comparable events. Mismatch causes overlap:
17 presence differences, two reference winners outside runtime eligibility,
16 runtime winners outside reference pools and eight common-pool order differences.
The existing Week 4 evaluator retains concrete mismatch examples and policy
differences. These descriptive agreements are not a new accuracy gate. The
runtime completion-time objective differs from the frozen reference objective;
matched origins, routing/profile and traffic inputs also differ.

### Refresh, invalidation and dependency verification

[Runtime evidence](reports/week5-runtime.json) records real isolated state writes,
actual routing, and HTTP API calls. A queue change moves the recommendation from
S029 to S007. An unchanged refresh produces new search evidence. A controlled
traffic snapshot is consumed with its exact version; its supplied canonical
segment is explicitly synthetic context, not a claim of matched segment identity.

OFFLINE and FULL changes each invalidate an earlier search with HTTP 409.
The full workflow recovers from one conflict with exactly two searches and two
ranking calls; two successive conflicts return 409 with the same bounded counts.
This controlled set contains five observed conflicts: two standalone invalidations,
one recovered conflict and two conflicts in the final-failure case.

Redis unavailability returns HTTP 200 using PostgreSQL fallback. PostgreSQL
unavailability returns 503 despite a warm cache. GraphHopper unavailability
returns 504 in the measured recommendation probe; Week 1 ingestion explicitly
returns `ENGINE_UNAVAILABLE`, with no false matched position. These outage probes
use actual refused/timed-out socket connections through in-process FastAPI and
production adapters. They do not stop shared containers or substitute mock results.

Missing location and invalid explicit swap intent return 422. Raw fallback,
stale rejection, no-service, zero candidates and missing traffic/queue policies
all pass. The deployed Week 1 smoke covers three vehicle/profile groups, Week 2
smoke passes 12 HTTP checks, and Week 3/GraphHopper and Week 4 smokes each cover
four service/vehicle groups plus their existing routing-contract checks.

### Initial local performance baseline

[Performance evidence](reports/week5-performance.json) measures a source-derived
car workload (T0020), current matched location and 20 eligible alternatives.
Each concurrency batch has three sequential warmups and 20 measured requests:
nine successful warmups and 60 successful measurements, with zero errors.
Cache state is natural after warmup; TTL remains 60 seconds and no guaranteed
cache-hit claim is made. HTTP latency excludes client semaphore waiting.

| Concurrency | Median ms | P90 ms | P95 ms | Max ms |
|---|---:|---:|---:|---:|
| 1 | 302.814 | 352.801 | 370.677 | 442.097 |
| 5 | 1,003.411 | 1,138.937 | 1,189.425 | 1,242.757 |
| 10 | 2,011.372 | 2,436.568 | 2,536.864 | 2,815.297 |

| Server stage median ms | C1 | C5 | C10 |
|---|---:|---:|---:|
| Location resolution | 0.023 | 0.035 | 0.032 |
| Demand | 0.077 | 0.123 | 0.110 |
| Candidate search, including routing | 291.967 | 965.247 | 1,974.153 |
| Ranking | 7.129 | 25.150 | 30.911 |
| Full server recommendation | 299.996 | 991.615 | 1,992.454 |

Independent stage medians do not necessarily sum to median total. Candidate
search/routing dominates this workload; optimization is deferred. This single
local workload establishes neither production throughput nor a latency SLA.

### Reproduction and artifact locations

Use a fresh `week5_*` PostgreSQL schema containing the existing snapshot schema,
with `search_path=<schema>,public`, a unique `week5:*:` Redis prefix, and a fresh
API process. Set `DATABASE_URL` to that schema's DSN, `SNAPSHOT_CACHE_PREFIX` to
the unique prefix, and host URLs for GraphHopper, Redis and the PostGIS road
database. Never use the shared full-history snapshot schema for causal replay.
`replay_week5.py` refuses absent local tables, nonempty history/cache or existing
namespaced driver state. The verification API needs its own separate empty schema
and configured ingestion token.

```powershell
python -B scripts/replay_week5.py --api-url http://127.0.0.1:8008 --schema week5_replay_NEW --cache-prefix week5:replay:NEW: --output runtime/week5/replay-NEW --trajectories 30
python -B scripts/evaluate_week5.py --replay runtime/week5/replay-NEW --output runtime/week5/evaluation-NEW.json
python -B scripts/verify_week5.py --api-url http://127.0.0.1:8006 --database-url "<isolated verification DSN>" --cache-prefix week5:verify:NEW: --token-file "<local token file>" --output runtime/week5/verification-NEW.json
python -B scripts/benchmark_week5.py --api-url http://127.0.0.1:8008 --request-file "<verified current workload JSON>" --warmup 3 --samples 20 --output runtime/week5/performance-NEW.json
python -B -m pytest backend/tests -q -p no:cacheprovider --basetemp=runtime/week5/pytest-new
python -B scripts/validate_frozen_dataset.py
python -B scripts/smoke_test.py
python -B scripts/smoke_test_week3.py
python -B scripts/verify_week4.py --smoke-only --output runtime/week5/week4-smoke-new.json
```

Replace NEW with a unique lowercase run identifier and start the matching API
configuration first. Detailed local predictions, logs and hash manifests live
under `runtime/week5/`; compact checked-in evidence lives under `docs/reports/`.
The protected Week 1-4 freeze tags remain unchanged. Week 5 freezes only after
the final regression/diff checks and clean commit gate, using
`week5-realtime-api-evaluation-complete`.

## Week 6 handoff

Production capacity/SLA tuning, broader load testing, cross-process driver state,
durable recommendation lifecycle, retention, monitoring and deployment hardening
remain Week 6/future work. Kafka, Redis Streams, WebSocket push and external live
feeds are not introduced. Local measurements and observed bottlenecks guide
future work; they do not establish production readiness.
