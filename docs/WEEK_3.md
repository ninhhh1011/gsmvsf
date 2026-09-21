# Week 3: Candidate Search and Routing

Updated 2026-09-21. Candidate search and routing are implemented with GraphHopper
as the sole runtime. Historical Week 3 completion and evaluation records are
retained below as superseded evidence. Functional migration verification passed:
239 tests including 71 Week 3 tests, live API/outage checks, and unchanged hashes
for all 63 Dataset files. Final reporting and the formal freeze gate remain
governed by [GRAPHHOPPER_FULL_MIGRATION_PLAN](GRAPHHOPPER_FULL_MIGRATION_PLAN.md).

## Scope and interfaces

Week 3 consumes Week 2's normalized `EnergyServiceRequest`, evaluates every
station/service alternative, and supplies eligibility plus physical routing
metrics for later ranking. It adds no scores, ranking weights, selected best
station, or Week 4 recommendation behavior.

- `POST /api/v1/candidate-search`: evaluate an energy request and optional destination.
- `POST /api/v1/candidate-search/evaluate`: telemetry through existing Week 2 demand evaluation, then search.
- `POST /api/v1/route`: domain `RouteRequest` to a road-network `RouteResult`, with optional via points.

`CandidateSearchService` requires an injected `RoutingEngine`; production wiring
uses GraphHopper only. `EV_CAR -> car` and `EV_MOTORBIKE -> motorcycle` apply to
routing and matching. Missing category is resolved from vehicle capability where
available, while conflicts and unsupported categories are rejected. Profile
hints cannot override category. Nonempty constraints, dynamic context and
objectives other than `MIN_TRAVEL_TIME` are explicitly unsupported.
Production routing and matching share one asynchronous HTTP client created and
closed by the application lifespan.

GraphHopper 11 route geometry is the encoded `paths[0].points` string. Distance
is meters; time is converted from milliseconds to seconds. The adapter requests
real `leg_distance` and `leg_time` details; via-leg totals are never split equally
as an estimate. Success payloads and metrics are validated.

## Candidate expansion and eligibility

The required sequence remains:

```text
ALL STATIONS -> SERVICE ALTERNATIVES -> FULL ELIGIBILITY
             -> ELIGIBLE CANDIDATES -> OPTIONAL DETERMINISTIC REDUCTION
```

Candidate identity is `(station_id, service_type)`. All 30 stations are evaluated
for CHARGING-only requests or explicit BATTERY_SWAP requests. Swap-capable
unresolved AUTO or explicit ANY requests expand both services, yielding 60
alternatives. A BOTH station remains two candidate identities. No nearest-N
straight-line prefilter may exclude candidates before eligibility.

Reason precedence remains:

```text
UNREACHABLE -> INCOMPATIBLE -> OFFLINE -> NO_SWAP_BATTERY -> FULL
            -> EXCESSIVE_QUEUE -> INSUFFICIENT_SOC_TO_REACH -> ELIGIBLE
```

The existing operational, compatibility and demand policies are unchanged:
closed station state, service-specific slot/battery availability, queue waiting
over 90 minutes, and energy feasibility retain their established rules.
Charging service time is 18 minutes; swap is 6 minutes. Energy feasibility is
`network_distance_m / 1000 + 0.5 <= estimated_remaining_range_km`.
Labels remain evaluation-only and are never loaded by the runtime search.

## Multi-leg metrics and failures

For each physical station:

- Leg 1: driver to station, `D1`, `T1`; station ETA is `T1`.
- Leg 2: station to destination, `D2`, `T2`.
- Direct route: driver to destination, `Ddirect`, `Tdirect`.
- Via totals: `D1 + D2`, `T1 + T2`.
- Detour: `max(0, Dvia - Ddirect)`, `max(0, Tvia - Tdirect)`.

Direct and station-route results are cached only within one request. Charging
and swap alternatives share the same physical station routes. With a destination
and 30 reachable stations this makes 61 route calls for either 30 or 60
alternatives. Without a destination, only 30 station calls are made and onward,
direct and detour fields remain null.

A genuine failed direct route is cached so it is not retried per station. If
both station legs succeed, their actual via totals are returned even when the
direct route is NO_ROUTE; direct/detour metrics remain null. An onward NO_ROUTE
retains station-only metrics. A no-route station leg yields UNREACHABLE.

Infrastructure failures from direct, station or onward calls propagate as 503;
timeouts as 504; invalid routing requests as 422. They never become a successful
search full of unreachable stations. Standalone `/route` returns 404 for a
genuine no-path result. There is no alternate engine, fake distance or mock
fallback.

## Live GraphHopper verification and benchmark

Run from the repository root with `DEBUG=false`:

```bash
python scripts/smoke_test_week3.py
python scripts/verify_graphhopper.py
python scripts/benchmark_week3.py --iterations 20
```

Smoke verifies both profiles, actual via legs, car/fixed-bike/swap/BOTH requests,
missing destination and the `/route` API. It fails when GraphHopper is unavailable.
The benchmark uses 20 distinct canonical trip starts, five per case, after four
warmup searches. Its forwarding counter preserves every real adapter result.
Inputs are vehicles, trips, road nodes and earliest SOC telemetry; explicit
driver requests exercise the service alternatives without changing the data.

Measured 2026-09-21:

| Case | Searches | Median ms | P90 ms | P95 ms | Maximum ms |
|---|---:|---:|---:|---:|---:|
| Car charging | 5 | 819.065 | 1,172.857 | 1,205.560 | 1,238.263 |
| Fixed-battery bike charging | 5 | 1,201.373 | 1,259.034 | 1,266.330 | 1,273.626 |
| Explicit swap | 5 | 1,005.768 | 1,622.522 | 1,665.189 | 1,707.856 |
| ANY/BOTH | 5 | 764.405 | 787.806 | 791.276 | 794.746 |
| All cases | 20 | 938.140 | 1,295.715 | 1,505.187 | 1,707.856 |

All 1,220 measured route calls succeeded. Every search made exactly 61 calls;
BOTH retained 60 alternatives. Percentiles use linear interpolation. These are
`CandidateSearchService.search_candidates` measurements using an injected shared
HTTP client; initial catalog/fixture loading and HTTP API overhead are excluded.
They are not production endpoint latency, concurrency capacity, or an acceptance
claim against an unmeasured production target.

Evidence lives in `runtime/migration/graphhopper-routing-smoke.json` and
`runtime/migration/graphhopper-week3-benchmark.json`, including full requests,
trip identities, candidate metrics, per-search times and route counts.

A separate deployed HTTP API benchmark includes serialization and station search
using the shared application client. Each concurrency level used 20 requests;
the evidence labels it an initial local GraphHopper performance baseline.

| Concurrency | Requests | Median ms | P90 ms | P95 ms | Maximum ms | Throughput/s |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 777.228 | 896.463 | 955.799 | 1,354.926 | 1.230 |
| 5 | 20 | 2,384.797 | 2,917.589 | 2,945.508 | 2,974.883 | 2.059 |
| 10 | 20 | 6,621.727 | 7,337.150 | 7,358.554 | 7,477.629 | 1.457 |

These are actual endpoint measurements, distinct from the earlier service-only
benchmark above. They show increased per-request latency under concurrency and
do not establish a production SLA. `runtime/migration/api-smoke.json` preserves
the exact numbers and normal route/matching/candidate/realtime checks.
`api-outage.json` confirms route/matching/candidate 503, realtime
`ENGINE_UNAVAILABLE`, liveness 200 and readiness 503 when GraphHopper is unavailable.

The motorcycle model shares `car_access`; `motorcar=no` excludes motorcycles too,
including the patched bridge. No complete independent motorcycle-access claim
is made. [ROUTING_STRATEGY](ROUTING_STRATEGY.md) describes this limitation and the
current matching projection/PostGIS quality semantics.
Ambiguous projected traversal or PostGIS directed-segment ties return
`AMBIGUOUS` with road segment and direction withheld, even when the geometric
location matched. Matching coverage must not be substituted for resolved-identity
or direction accuracy.

## Historical evidence: superseded for current runtime

The earlier Week 3 report recorded 100 searches with minimum 61.19 ms, median
86.38 ms, mean 157.43 ms, P90 156.14 ms and P95 285.43 ms; it reported 61 calls and
11.6 searches/second. The inherited benchmark used a mock routing adapter, so
those figures do not measure the current live GraphHopper deployment and must
not be presented as its realtime latency.

The earlier eligibility replay reported 31,440/31,440 eligible/ineligible and
reason-code agreement (TP 7,474; TN 23,966; FP/FN 0), split as 25,440 CHARGING and
6,000 BATTERY_SWAP rows. This is historical eligibility-policy evidence. It does
not establish current GraphHopper route agreement, map-matching quality, or new
freeze acceptance. Any migration evaluation must identify its actual runtime,
fixture scope and evaluation-only label use.

## Week 4 handoff remains unchanged

`CandidateSearchResult` carries search status, evaluated count, eligible count,
and `EvaluatedCandidate` records. Each record includes station/service identity,
eligibility/reason, location/access node, network distance, energy feasibility,
operational snapshot and `CandidateRouteMetrics`. Operational snapshots include
status, capacity, queue, wait, service time and timestamp. Route metrics include
station and onward legs, via/direct/detour distance and duration, and station ETA.
Future ranking consumes eligible candidates and these domain fields; it must
not depend on GraphHopper HTTP fields or invent missing traffic adjustments.
