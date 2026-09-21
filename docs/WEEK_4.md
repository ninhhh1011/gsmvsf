# Week 4 — Snapshot-aware ranking and recommendation

Date: 2026-09-21. **Week 4 acceptance PASS.** Implementation is request-driven.
Final verification: 302 tests passed, frozen Dataset validation passed, real
PostgreSQL/Redis/GraphHopper/API checks passed. Production readiness remains NOT READY.
The [implementation plan](WEEK_4_IMPLEMENTATION_PLAN.md) and
[ADR-013](DECISIONS.md#adr-013-week-4-snapshot-persistence-and-eligibility-ownership)
record the scope and approved eligibility boundary.

## 1. Repository audit

Root `E:\build6week`; starting branch `graphhopper-full-migration-20260921`;
starting commit `d8574c0f19126984df7f965796b2c3355e0d3a2c`; initially clean.
Tags `graphhopper-full-migration-complete` and `week3-candidate-routing-complete`
identify that baseline. Work branch: `week4-ranking-recommendation`.
Required scope, acceptance, contract, architecture, decision, routing, historical
Week 1–3, GraphHopper and Dataset documents were inspected alongside actual code,
CSV headers, generators and validator. Baseline verification: 239 tests, canonical
validator 152 PASS / 0 FAIL and 22/22 scenarios, real GraphHopper smoke.

Week 3 produces `CandidateSearchResult` containing `EvaluatedCandidate` entries,
eligibility/reason, composite station/service identity, operational snapshots and
route metrics. Its implementation remains the eligibility authority. The new
workflow injects a pinned PostgreSQL operational view into that existing service.
No duplicate Candidate Search or alternative routing runtime was introduced.

## 2. Implementation plan and gates

The plan groups the requested areas into seven implementation phases to avoid
duplicated contracts and premature API work. Each task includes objective, why,
inputs, outputs, dependencies, files, approach, tests, review, exit gate, risks
and failure behavior. The execution ledger records actual gate evidence.

| Phase | Tasks | Responsibility |
|---|---|---|
| 0 / plan | Audit / detailed plan | Verify repository and resolve ownership conflict |
| 1 | W4-01 | Immutable snapshots, search evidence, explainable result contracts |
| 2 | W4-02, W4-03 | PostgreSQL, validation, immutable ingestion, source import |
| 3 | W4-04 | Redis KV, time-aware resolver, freshness, database fallback |
| 4 | W4-05, W4-06 | Context, invalidation, completion-time ranking and ties |
| 5 | W4-07 | Internal ingestion, public ranking, bounded synchronous workflow |
| 6 | W4-08, W4-09 | Dataset evaluation, dynamic demonstration and measurements |
| 7 | W4-10 | Regressions, independent review, documentation and conditional freeze |

## 3. Week 4 architecture

```text
Dataset/project timestamped snapshots
  -> authenticated ingestion API -> PostgreSQL immutable history
                                  -> best-effort Redis latest payload update

Request -> Week 2 EnergyServiceRequest
        -> resolver pins DB snapshot versions -> injected Week 3 Candidate Search
        -> persisted CandidateSearchEvidence
        -> resolver: DB heads -> validated Redis payload / DB payload fallback
        -> ranking context + eligibility-change guard
        -> deterministic RankingService -> RecommendationResult
```

Static master data remains the existing canonical station and vehicle catalogs.
Operational state is timestamped persisted data. Position, SOC, energy margin,
destination, route metrics and request time are request context. GraphHopper
remains the sole routing/matching adapter. Redis is optional for availability,
while PostgreSQL is authoritative. Provider responsibilities are isolated in the
resolver/ingestion boundary; a future feed can ingest the same contracts without
changing the ranking formula. There are no streaming providers or consumers.

## 4. Persistence

`backend/app/services/snapshots/schema.sql` defines two tables:

- `state_snapshots`: UUID primary key, kind, entity ID, timestamptz observation
  time, source, schema version, JSONB payload and database `created_at`.
- `candidate_searches`: server-issued search ID, immutable JSONB evidence and
  database `created_at`.

Unique `(kind, entity_id, timestamp)` provides deterministic logical identity
across sources. Its B-tree supports latest-at-or-before lookups using a backward
index scan; a real EXPLAIN test verifies this. No redundant timestamp index.
UUID5 binds snapshot identity to validated content; signed zero is normalized
before hashing because JSONB normalizes `-0.0`. Conflicting content cannot reuse
a logical timestamp. There is no existing ORM/repository to duplicate; the
repository uses the project's existing asyncpg dependency and lifespan pool.

The explicit loader installs schema idempotently and imports source snapshots
in bounded transactions. Initial import: 890,137 rows (883,597 traffic, 3,270
station, 3,270 queue). Exact repeated import created zero rows. PostGIS retains
canonical directed road segments for traffic identifier validation and matching.

## 5. Ingestion

Separate token-protected internal endpoints accept typed traffic/station/queue
snapshots. Validation rejects unknown entities, naive timestamps, nonfinite or
negative numbers, invalid status/traffic enums, fractional counts, excessive
capacity, unsupported service values and inconsistent speed/delay factors.
Supported services require positive service time. Times normalize to UTC.

Database commit precedes cache maintenance. Exact retry returns 200 and the same
ID; initial insert returns 201; same logical key with different content/source
returns 409 `SNAPSHOT_CONFLICT`. Concurrent writers use database uniqueness and
transactional conflict verification; any conflicting batch rolls back. Older
observations remain in history. Cache population queries the actual global head,
so an older ingestion cannot become latest even after cache expiration.

## 6. Redis cache

Keys are centralized as `week4:snapshot:{kind}:{entity_id}:latest`. Values contain
a fixed-width UTC stamp and validated snapshot payload. Lua compare-and-set
atomically prevents older writers from replacing newer entries. Configurable
60-second TTL bounds retention; it does not establish freshness or correctness.

Every resolution first pins authoritative DB IDs in one SQL statement. A Redis
payload is a hit only if its calculated content ID matches the pinned ID. Miss,
corruption or Redis failure reads the immutable DB payload. Population is best
effort and uses the global newest version, not an arbitrary historical result.
This intentionally keeps a small DB metadata lookup on cache hits: missed cache
writes cannot hide operational changes. Warm Redis never masks a DB outage.

## 7. Snapshot resolution and freshness

Each key resolves its latest timestamp `<= request_time`; future rows cannot
enter that request. One MVCC query pins all selected versions before any cache
read. A concurrent write changes a later resolution, not half of the current
context. Different entities can legitimately have different observation times.

Every feature exposes source, content ID, timestamp, age in seconds and
`FRESH`, `STALE` or `MISSING`. Default freshness: station/queue 600 seconds,
traffic 1,800 seconds, inclusive at the threshold. These are configurable
project choices aligned to Dataset cadence, not official VinFast policies.
Stale observed values remain usable with visible degradation. Missing station
state fails explicitly because operational eligibility cannot be established.

## 8. Traffic semantics

Source: `dataset_v1/traffic/traffic_snapshots.csv.gz`; fields are segment ID,
timestamp, traffic level, free-flow/current speed and `delay_factor`.
The factor represents free-flow speed divided by current speed, with Dataset
rounding tolerance validated at ingestion.

```text
base_travel_duration = existing Week 3 GraphHopper station-leg duration
adjusted_travel_duration = base_travel_duration * origin_snapshot.delay_factor
traffic_adjustment = adjusted_travel_duration - base_travel_duration
```

This is explicitly `ORIGIN_SEGMENT_PROXY` when a directed origin segment is
available. Week 3 provides no complete route-to-Dataset-segment traversal, so
the system does not claim segment-weighted route traffic. No known origin
segment or no snapshot means unchanged base duration and
`BASE_DURATION_MISSING`; no global factor or invented live traffic. Ranking
does not call GraphHopper again. Dataset evaluation uses causal raw GPS without
map matching and therefore truthfully reports traffic MISSING for that replay.

## 9. Queue and station state

`stations/station_status.csv.gz` supplies OPEN/OFFLINE, available/occupied
charging and swap slots, available swap batteries, and service times.
`queue/queue_status.csv.gz` supplies per-service queue length, active service
count, service-time fields and estimated wait. Wait is taken directly from
`*_estimated_wait_min` once; queue length is not multiplied by service time
again. Canonical operational station service time is used (Dataset charging
18 minutes, swap 6 minutes); there is no charging-curve simulation.

Charging capacity is available charging slots. Swap capacity is the minimum
of available swap slots and available batteries. Missing queue has null observed
wait and a visibly labelled `PROJECT_POLICY_MISSING_QUEUE` effective wait of
5,400 seconds, configurable. This assumption never asserts an observed zero wait.

## 10. Ranking context

Each feature contains station ID and service type; base/adjusted travel and
adjustment seconds; traffic method; observed/effective queue wait and assumption;
service duration; detour duration/distance; route distance; available capacity;
and complete resolved station/queue/traffic provenance. The result also retains
the Week 2 energy request: SOC, remaining range/energy, margin, need reason,
intent and capabilities. Urgency is available but does not silently alter weights.

Search evidence includes request time, server creation time, complete original
Week 3 result, snapshot IDs and canonical catalog digest. `/ranking` loads this
server record; the client cannot replace its eligible candidates in that call.
Ranking time cannot precede search context time. Nested legacy UTC search clocks
are normalized at the Week 4 boundary without changing the Week 3 implementation.

## 11. Ranking policy and explanation

`TOTAL_SERVICE_COMPLETION_V1` minimizes adjusted station travel + queue + service,
in seconds. Final cost equals service-completion duration. No learned score,
arbitrary weighted mixture, urgency multiplier or generalized penalty is used.
The explicit penalty-components map is empty for this baseline. Detour is only
a tie-breaker, so it is not counted twice with travel time.

Ordering: completion rounded to milliseconds; service start rounded to
milliseconds; lower detour seconds, then meters (missing last); younger station
state; higher available capacity; station ID; service-type string. Reported
durations retain precision. This defines deterministic near-ties without a
nontransitive approximate-equality comparator.

## 12. ETA definitions

```text
ETA_TO_STATION         = adjusted travel
ETA_TO_SERVICE_START   = adjusted travel + effective queue wait
ETA_TO_SERVICE_COMPLETE= adjusted travel + effective queue wait + service
```

All three are durations from request context in seconds, not wall-clock arrival
timestamps. Onward travel and detour remain visible context, not completion cost.

## 13. Recommendation and eligibility ownership

Zero eligible alternatives returns `has_recommendation=false`, null identity and
an empty ordered list. One returns that alternative. Multiple rank the complete
eligible set. `top_n` truncates only after ranking; Week 4 search rejects the
legacy `max_candidates` option. S001/CHARGING and S001/BATTERY_SWAP are distinct.

If a changed version makes an originally eligible candidate OFFLINE, FULL or
without usable swap inventory, the entire set fails HTTP 409. Catalog change
also invalidates evidence. Queue changes normally rank with the newer wait;
crossing Week 3's existing 90-minute eligibility ceiling is an eligibility
change. No route-reachability update stream exists, so no such state is invented.
No rejected candidate is rescued and no invalidated candidate is silently dropped.

Source-based deployed API examples (all returned 200):

| Request | Evaluated alternatives | Eligible | Recommendation |
|---|---:|---:|---|
| Car T0001, charging | 30 | 19 | S029 / CHARGING |
| Fixed bike T0024, charging | 30 | 0 | none |
| Swap bike T0003, swap | 30 | 1 | S021 / BATTERY_SWAP |
| Swap-capable T0015, ANY | 60 | 13 | S009 / BATTERY_SWAP |

The ANY case evaluates charging and swap as separate alternatives. Both service
identities at one station are also explicitly covered by composite-identity tests.


```json
{"error_code":"CANDIDATE_STATE_CHANGED",
 "message":"Candidate eligibility state changed after candidate search.",
 "candidate_search_id":"server-issued-id",
 "changed_candidates":[{"station_id":"S010","service_type":"CHARGING",
 "previous_state":"ELIGIBLE","current_state":"OFFLINE"}],
 "action":"RERUN_CANDIDATE_SEARCH"}
```

The higher-level workflow retries Week 3 once on this typed conflict. A second
conflict propagates. RankingService has no retry or competing eligibility engine.
Both attempts retain the explicit request's as-of time. Late-arriving observations
at or before that time can invalidate a pinned set; observations after it belong
to a later request. To assess a stored search against later state, supply a later
`request_time` to `/ranking`. Wall-clock passage does not silently change a
historical scenario's time boundary.

## 14. API and operation

| Endpoint | Behavior / status |
|---|---|
| POST `/api/v1/ranking/candidates` | Existing Week 3 search with pinned state, persists evidence; 200 |
| POST `/api/v1/ranking` | Search ID, optional later request time/top_n; 200 or structured 409 |
| POST `/api/v1/recommend` | Telemetry and optional driver intent; synchronous Week 2→3→4; 200 |
| POST `/api/v1/internal/snapshots/traffic` | Token-protected typed ingestion; 201/200/409/422 |
| POST `/api/v1/internal/snapshots/station` | Same, operational state |
| POST `/api/v1/internal/snapshots/queue` | Same, queue state |

Missing search ID returns 404. Malformed/invalid request returns 422. Internal
ingestion is disabled with 503 until `SNAPSHOT_INGESTION_TOKEN` is configured;
missing token returns 401, wrong token 403. Send it in `X-Ingestion-Token`.
Dependency failures return explicit 503 or routing timeout 504. Public telemetry
bounds include inherited SOC threshold, consumption, distance and energy fields;
missing/invalid Week 2 decisions cannot masquerade as successful no-service.

Host setup uses `.env.example` with IPv4 PostgreSQL; Compose injects service-host
URLs. Start db/GraphHopper/Redis, load roads, then run
`python -B scripts/load_week4_snapshots.py` before using snapshot endpoints.
The API lifespan owns HTTP, PostgreSQL pool and Redis client shutdown. Existing
readiness checks routing/PostGIS roads; run the snapshot loader and Week4 smoke
to verify snapshot schema/source readiness as well.

## 15. Reliability

Redis down/corrupt/missing: DB payload fallback. DB down: explicit failure even
with warm cache. Missing traffic: base route with missing provenance. Missing
queue: labelled configurable conservative assumption. Missing station: failure.
Stale data: observed values plus age/degraded flags. GraphHopper unavailable:
existing adapter failure, no mock fallback. Duplicate/out-of-order ingestion:
immutable retry semantics and atomic latest-cache handling. A valid historical
request deliberately does not see snapshots after its request time.

## 16. Dynamic snapshot demonstration

**PASS**, [real backend evidence](reports/week4-runtime.json). On September 3 at
00:10 UTC, 20 eligible charging alternatives recommend S029 with zero queue wait.
A newer S029 queue snapshot at 00:11 raises its wait to 90 minutes while remaining
serviceable. Ranking the same stored search at that later time recommends S007;
all 20 alternatives remain ranked. An older arrival at 00:10:30 cannot overwrite
Redis's00:11 head. Ranking historically at 00:10 again selects S029.

A subsequent S029 OFFLINE update returns 409 `CANDIDATE_STATE_CHANGED`, identifying
S029/CHARGING and requiring new Candidate Search. Exact ingestion retry returned 200;
conflicting retry 409. Additional real state changes produce exactly one eligible
candidate and then zero. Newer snapshots restore OPEN serviceability at 00:19.
Traffic POST/readback/history and401/403/422 validation probes also pass. All
mutations are labelled project demonstration source, outside Dataset scenario dates.

Network failure checks use actual unavailable local ports with real repositories,
adapters and in-process HTTP routes; deployed services remain running. Results:
Redis-down search/ranking 200 with 20 eligible and S029/CHARGING; PostgreSQL-down 503
`SNAPSHOT_DATABASE_UNAVAILABLE` even with warm cache; GraphHopper timeout 504 and
`RoutingTimeoutError`. Windows can time out rather than immediately refuse a
connection; the verifier records the actual failure and never substitutes routes.

## 17. Dataset evaluation

Completed all **1,200 source events**, joining all **848 recommendation rows** and
**553 positive ranking groups**. `scripts/evaluate_week4.py` independently reconstructs 1,200
AUTO event contexts from source SOC/trips/vehicles and latest causal raw GPS.
Labels open only after persisted predictions are complete. Source reconstruction
is separately checked against labels as an evaluation assertion, never as input.

| Classification | Inputs |
|---|---|
| SOURCE DATA | trips, vehicle/station catalogs, SOC, raw GPS, destination nodes, persisted source snapshots |
| RUNTIME-DERIVED | Week 2 request, GraphHopper routes, eligible candidates, context, ordered costs |
| GROUND-TRUTH LABEL | ranking_reference, recommendation_labels; demand labels only in reconstruction test |

Baselines: nearest eligible, minimum station ETA, total completion. Report full
runtime-pool top-1 and common-composite-pool pairwise agreement separately. Frozen
reference ranks at most eight nearest eligible alternatives and includes onward
travel, detour penalties and capacity credit, with different route/traffic inputs.
Agreement is not expected to be 100%; mismatches must retain actual evidence.

| Baseline | Positive top-1 station/service | Overall recommendation (including empty) | Pairwise common pool |
|---|---:|---:|---:|
| Nearest eligible | 473/553 (85.53%) | 743/848 (87.62%) | 10,096/10,885 (92.75%) |
| Minimum station ETA | 465/553 (84.09%) | 735/848 (86.67%) | 10,188/10,885 (93.60%) |
| Total service completion | **478/553 (86.44%)** | **748/848 (88.21%)** | **10,246/10,885 (94.13%)** |

Completion's common-pool top-1 is 482/540 (89.26%). Service-type-only agreement
is 540/553 (97.65%); this is weaker than composite identity agreement. Presence
agreement is 810/848 (95.52%): 25 runtime-only and 13 reference-only recommendations.
Runtime groups across all 1,200: 635 zero, 67 single, 498 multiple. The reference
848 service-needed events contain 295 zero, 75 single and 478 multiple; the extra
352 no-demand events are retained in runtime totals rather than silently removed.

Examples investigated against actual route/eligibility evidence:

- DE000049: reference S012/BATTERY_SWAP route 6,691.2m becomes 8,486.7m with
  GraphHopper. Available range 8.27km plus required 0.5km reserve makes it
  `INSUFFICIENT_SOC_TO_REACH`. Runtime S021 needs 7.7692+0.5=8.2692km and remains
  eligible. This is a route/eligibility-pool difference, not a ranking rescue.
- DE000169: reference marks S016/CHARGING unreachable. GraphHopper returns a
  valid 1,945m/140.8s route; station OPEN, capacity 3, wait 0, range 54.95km. Runtime
  correctly returns an eligible recommendation where the reference has none.
- DE000273: runtime S008/CHARGING completes in 1,710.9s (630.9 travel + 0 queue
  + 1,080 service), versus 1,726.3s for S022. Frozen reference instead prefers
  S022: generalized cost 82.8032 versus 89.4261, including two-leg travel,
  detour and capacity credit. Frozen traffic factors are 2.132/1.997; runtime
  has no matched segment and exposes base duration. Queue/service are equal
  and do not explain this mismatch. Route, traffic and objective effects are
  confounded rather than isolated by this comparison.

Mismatch categories overlap: 17 reference-best alternatives absent from runtime
eligibility, 38 recommendation-presence differences, 25 runtime winners outside
the reference pool, and 58 ordering differences within the common pool. The
report preserves example metrics; differing objective, route geometry/profile,
origin and traffic cannot be assigned isolated causal percentages by this replay.
No reference outputs were changed. Completion is selected because its interpretable
objective fits Week4 and its measured top-1/pairwise agreement exceeds both tested
alternatives. No generalized-cost or ML runtime was needed.

Eligible-count distribution: all 1,200 events min/median/max = 0/0/20;
the joined 848 service-needed events = 0/4/20, with 283 zero, 67 single and
498 multiple eligible groups. The report includes the complete count histogram;
the prediction artifact retains each group's eligible identities and features.

Prediction provenance records code/source/configuration fingerprints. The completed
run was uninterrupted with stable source DB history and GraphHopper map. Resume
was deliberately removed because a file fingerprint alone cannot guarantee an
unchanged mutable backend. New runs require a new output path. Compact evidence:
[Dataset evaluation](reports/week4-evaluation.json); full predictions remain in
`runtime/week4/evaluation.predictions.jsonl`.


## 18. Observability

Structured logs expose workflow and recommendation latency, attempts, evaluated
and eligible counts, ranking-only time, selected policy/station/service, degraded
status, snapshot lookup latency/ages, hit/miss, DB payload fallbacks, stale/missing
counts, cache corruption and unavailability. Resolver counters provide lightweight
in-process measurements. No monitoring stack, driver payload logging or token
logging is introduced. Counters are process-local, not durable aggregate metrics.

## 19. Initial local performance baseline

**PASS**, measured with running Docker API/PostgreSQL/Redis/GraphHopper.
Ten samples per row; durations in milliseconds, percentiles linearly interpolated.

| Operation | Median | P90 | P95 | Max |
|---|---:|---:|---:|---:|
| New snapshot ingestion HTTP | 8.789 | 10.27 | 10.588 | 10.905 |
| Pure ranking (20 candidates) | 0.105 | 0.112 | 0.125 | 0.138 |
| Snapshot lookup: Redis hit | 8.67 | 10.187 | 10.302 | 10.417 |
| Snapshot lookup: miss + DB + population | 78.684 | 87.624 | 96.504 | 105.383 |
| Ranking HTTP: cache hit | 14.347 | 17.596 | 18.578 | 19.559 |
| Ranking HTTP: cache miss | 30.308 | 39.164 | 55.103 | 71.042 |
| Week 2-3-4 HTTP: cache hit | 337.738 | 447.276 | 462.771 | 478.266 |
| Week 2-3-4 HTTP: cache miss | 396.739 | 528.034 | 535.486 | 542.938 |
| Week 2-3-4 HTTP concurrency 1 | 332.141 | 379.297 | 387.427 | 395.558 |
| Week 2-3-4 HTTP concurrency 5 | 1135.717 | 1285.422 | 1305.435 | 1325.448 |
| Week 2-3-4 HTTP concurrency 10 | 2252.427 | 2479.249 | 2488.713 | 2498.177 |

The timed fixture has 20 eligible candidates; source smoke covers 0, 1, 13, 19.
Snapshot measurements resolve 60 station/queue entities. Redis hit avoids DB payload
fetch/population but retains the authoritative head query. Ranking HTTP median
improved from 30.308 to 14.347ms; full workflow from 396.739 to 337.738ms in this run.
Pure ranking is small relative to route orchestration. Concurrency 10 P95 is about
2.489s: these ten-request samples are an initial laptop baseline, not a capacity
or tail-latency guarantee. Cache population and payload validation are included;
cache clearing/warming setup is outside timed requests. HTTP end-to-end includes
routing and serialization; pure ranking measurements do not.

This is an INITIAL LOCAL WEEK 4 BACKEND PERFORMANCE BASELINE, not production
capacity. A required DB metadata read remains on cache hits; measured benefit
must be reported honestly even when negative or dominated by GraphHopper time.

## 20. Week 4 tests

**63 passed / 0 failed / 0 skipped** in the explicit Week4 suite.

| File | Passed | Failed | Skipped |
|---|---:|---:|---:|
| `test_week4_api.py` | 7 | 0 | 0 |
| `test_week4_database.py` | 8 | 0 | 0 |
| `test_week4_evaluation.py` | 4 | 0 | 0 |
| `test_week4_models.py` | 9 | 0 | 0 |
| `test_week4_ranking.py` | 25 | 0 | 0 |
| `test_week4_snapshots.py` | 7 | 0 | 0 |
| `test_week4_verification.py` | 3 | 0 | 0 |

Tests cover contracts, real PostgreSQL and Redis,
concurrent conflicts, pinned reads, empty-cache historical population, signed-zero
identity, stale/missing states, every approved conflict boundary, ties, zero/one/
multiple alternatives, no silent filtering, bounded retry, API validation/auth,
and real lifespan resource cleanup. Integration tests require actual services.
Two additional HTTP tests use real PostgreSQL and actual Week3 search/ranking
with a test routing adapter: concurrent state change triggers one fresh search
and returns S002; invalidating that second set returns 409 after exactly two
searches. This complements the deployed-service smoke and failure probes.

## 21. Dataset regression

**PASS: 152 checks / 0 failures; 22/22 scenario assertions.**
Use `python -B scripts/validate_frozen_dataset.py`:
it executes the frozen canonical validator but redirects generated reports outside
Dataset. Direct execution of the Dataset validator writes its own frozen files
and would violate the read-only rule. All 63 tracked canonical files and all 69
initial on-disk files (including six preexisting ignored bytecode files) are hashed.

## 22. Week 3 regression

**71 passed / 0 failed / 0 skipped** in 13 files: Candidate Search, compatibility, eligibility,
energy feasibility, route abstraction, multi-leg metrics and API. No ranking
logic was added to Week 3 source; only the injected operational catalog changes
the new workflow's source of state. Existing candidate API remains compatible.

## 23. Week 2 regression

**69 passed / 0 failed / 0 skipped** in 8 files: AUTO, DRIVER_REQUEST, ANY, capabilities,
EnergyServiceRequest, energy feasibility and API. Week 2 source remains unchanged.

## 24. Week 1 regression

**37 passed / 0 failed / 0 skipped** in matching/realtime/config/health files,
plus **62 passed** in the dedicated GraphHopper/migration regression group.
Coverage includes current GraphHopper matching, realtime state,
projection/segment resolution and shared client lifecycle. Historical engine
counts are not substituted for current test execution.

## 25. Code and diff audit

**PASS.** Final audit compares against `d8574c0`. Runtime changes are new snapshot/ranking
modules and API plus config/main/lifespan integration, Redis dependency/Compose.
Review specifically checks label leakage, Dataset writes, duplicate eligibility,
hardcoded global traffic/queue, non-deterministic ties, cache authority/fallback,
out-of-order races and unintended generated artifacts. Runtime logs/tokens/large
predictions remain ignored under `runtime/week4`, never in Dataset or commits.

## 26. Documentation

This report, implementation plan, ADR-013, current architecture, acceptance,
README and environment/setup helpers document the delivered milestone. Traffic
and queue are timestamped Dataset/project snapshots, not external production
live feeds. TTL, freshness, fallback wait and traffic proxy are project policy.

## 27. Git and freeze

Work is retained on `week4-ranking-recommendation`. Focused implementation commits:
`307f3d6` plan/ADR; `d586316` contracts; `3e59705` persistence/ingestion;
`7ee0dbb` cache/resolution; `710ba75` latest-cache correction; `4080ac2` ranking;
`5979c75` APIs/workflow; `93fd195` JSONB identity fix; `9ba2769` telemetry validation;
`5f188cb` evaluation/runtime evidence. The final documentation/regression commit
is identified by `week4-ranking-recommendation-complete` to avoid a self-referential
commit hash in this file. The tag is created only after that commit and a clean
working-tree check. Existing historical tags remain untouched. No destructive
Git operations, blanket staging, merge, push or Week5 work are part of this freeze.

## 28. Known limitations and Week 5 handoff

Origin-segment traffic is a coarse proxy; replay without matching uses base
duration. Snapshot freshness does not make observations live. DB heads are always
required for correctness; Redis is a best-effort optimization. Snapshot/search
history has no automatic retention policy. Internal token auth is a local project
boundary, not a complete multi-user authorization system. Current static catalog
digest invalidates conservatively on any catalog change. No dynamic reachability
state is represented. GraphHopper motorcycle routing retains documented car_access
limitations. Local benchmarks do not establish production SLAs.

Week 5 may consume these synchronous contracts after separate authorization.
Continuous monitoring, background reranking, push/WebSocket updates, Kafka,
Redis Streams and external live feeds are not implemented. Production readiness:
**NOT READY**.

## 29. Bugs and remaining gates

No known unresolved Week4 acceptance bug or required gate remains. Independent
reviews covered runtime consistency, eligibility ownership, input validation,
label leakage, evaluation denominators and final requirement coverage. Findings
fixed and retested: empty-cache historical population, signed-zero JSONB identity,
naive legacy search clock, inherited telemetry bounds and invalid no-service
input. Verification harness issues (Windows timeout classification and temporary
LOG_LEVEL override) were corrected without changing frozen subsystem behavior.
Earlier failed evidence is retained under ignored runtime/week4 for traceability.

[Acceptance evidence](reports/week4-acceptance.json) lists exact commands, files,
per-file test totals, return codes and integrity checks. Final combined suite:
**302 passed / 0 failed / 0 skipped**. Explicit groups: Week4 63, Week3 71,
Week2 69, Week1 37, additional GraphHopper/migration 62. Live final checks passed:
`verify_graphhopper.py`, `smoke_test.py`, and `verify_week4.py --smoke-only`.
Docker API, PostgreSQL/PostGIS, Redis and GraphHopper were all healthy at final audit.

| Acceptance area | Status | Evidence |
|---|---|---|
| Domain, eligible-only composite identity and explainable ranking | PASS | 9 models + 25 ranking tests |
| Persistence, schema, idempotency and concurrent writers | PASS | 8 real DB tests; full source import/retry |
| Cache hit/miss/failure, time lookup, stale/missing, concurrent pinning | PASS | 7 real Redis/resolver tests and runtime probes |
| 409 ownership boundary and bounded workflow retry | PASS | 7 API tests, actual-search race tests, live OFFLINE409 |
| Dataset evaluation and no label leakage | PASS | 1,200 real predictions; 4 evaluator tests; independent review |
| Dynamic state, history, traffic ingestion and failures | PASS | live runtime report and 3 verifier tests |
| Observability and initial performance | PASS | structured operations and concurrency1/5/10 measurements |
| Weeks1-3, GraphHopper and Dataset preservation | PASS | grouped regressions, real APIs,63 tracked/69 disk hashes unchanged |
| Documentation, diff review and freeze | PASS | plan, ADR, this report, acceptance artifact; clean commit before tag |

WEEK 4 SNAPSHOT BACKEND STATUS: PASS  
WEEK 4 CACHE / RELIABILITY STATUS: PASS  
WEEK 4 RANKING STATUS: PASS  
WEEK 4 RECOMMENDATION STATUS: PASS  
WEEK 4 DATASET EVALUATION: PASS  
WEEK 4 REGRESSION: PASS  
REAL BACKEND RUNTIME: VERIFIED  
WEEK 4 QUALITY: PASS  
PRODUCTION READINESS: NOT READY  
FINAL DECISION: CLOSE WEEK 4

