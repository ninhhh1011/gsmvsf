# Routing strategy

Current implementation, 2026-09-21. The previous multi-engine proposal is
superseded by ADR-010; domain independence from ADR-008 remains required.
GraphHopper 11.0 is the sole production routing and matching engine. Benchmarks
measure this migration's behavior and regressions; they do not reopen engine
selection or authorize an automatic fallback.

## Domain boundary

Business logic consumes `RouteRequest` and `RouteResult`, not GraphHopper URLs or
JSON. `CandidateSearchService` requires an injected `RoutingEngine`; the production
factory injects `GraphHopperRoutingAdapter`. Mock engines are test-only.
`MapMatchingService` uses a separate engine contract shared by batch and realtime
flows. No additional runtime engine, matrix service or ranking implementation is
needed for Weeks 1–3.

The implemented `RouteRequest` contains origin, destination, optional via points,
vehicle profile, optional constraints, objective and optional dynamic context.
`Position` validates finite coordinates and geographic bounds. `RouteResult`
contains status, meters, seconds, optional encoded geometry, actual legs and
engine metadata. Candidate multi-leg metrics contain station distance/ETA,
onward distance/time, direct metrics, via totals and detour.

Only `MIN_TRAVEL_TIME` is implemented. Nonempty `RouteConstraints`, nonempty
`DynamicRoutingContext`, alternate objectives and nonempty profile hints produce
explicit invalid-request results. They are domain extension points, not claims
that dynamic traffic, energy-aware path search or arbitrary avoid rules already
work. A future requirement must add measured support behind the existing domain
contract rather than silently ignoring inputs.

## Vehicle-aware runtime

Production routing and matching share one asynchronous HTTP client owned by the
application lifespan and closed on shutdown. Connection pooling does not reuse
candidate route results between searches.

| Domain category | GraphHopper profile |
|---|---|
| `EV_CAR` | `car` |
| `EV_MOTORBIKE` | `motorcycle` |

Both routing and matching use the same mapping. Candidate search derives an
omitted category from actual resolved capability and rejects conflicts. Missing
or unknown categories cannot silently become car or motorcycle routes.
The deployment has no routing-engine selector or single default profile.

The approved immutable patched OSM PBF supplies the graph. The baseline PBF is
reference-only. The project motorcycle custom model excludes MOTORWAY, penalizes
TRUNK, uses 90% of car speed with a 60 km/h modeling cap, and preserves
rough-surface restrictions. The cap is not a Vietnamese legal-speed assertion.

The maintained motorcycle model still depends on `car_access`. Consequently,
`motorcar=no` excludes motorcycles too, including Cầu Thanh Trì way `881947000`.
This is a conservative known limitation, not complete motorcycle-specific OSM
access support. An independent access parser requires separately validated
rules and graph reimport; modifying Dataset V1 to bypass it is prohibited.

## HTTP adapter semantics

Routing uses GET `/route` with repeated `point=lat,lon`, deterministic profile,
encoded points and `leg_distance`/`leg_time` details. GraphHopper's encoded
`paths[0].points` is a string. Time and leg time are milliseconds converted to
seconds. Each leg uses the returned detail values; dividing totals evenly would
fabricate metrics. Missing/malformed success payloads and invalid/nonfinite
metrics are engine failures. Known no-path HTTP 400 errors remain NO_ROUTE;
other invalid requests are separate from dependency failures.

Matching uses POST `/match` with GPX, unsimplified path geometry and OSM way
details. The project projects each observation onto that returned geometry and
uses a 100 m residual cutoff. PostGIS resolves Dataset directed segments using
matched OSM way identity and path traversal direction; unresolved IDs stay null.
GraphHopper internal edge IDs are not Dataset or OSM IDs.

Matching quality is geometric proximity: `max(0, 1 - residual_m / 100)` per
matched observation, averaged across all observations for overall quality. It
is not a probability or native GraphHopper posterior. Path projection can be
ambiguous at loops, crossings and parallel roads; matching-quality acceptance
requires measured direction/identity/coverage evidence. Historical engine
confidence thresholds and old freeze reports do not establish equivalence.

## Candidate search remains Week 3

Ambiguous projected traversal or PostGIS directed-segment ties return
`AMBIGUOUS` with `road_segment_id` and `direction` withheld. A geometric matched
location can remain available without proving the directed Dataset identity.

The sequence is all stations, service expansion, road routing and complete
eligibility, eligible candidates, then optional deterministic reduction. It
never prefilters nearest-N by straight-line distance. Candidate identity remains
`(station_id, service_type)`; station service alternatives remain separate even
when they share a request-local route calculation.

For a destination and 30 reachable stations: one direct call, 30 station calls,
30 onward calls. BOTH therefore has 60 alternatives with 61 route calls. This
cache is request-local and does not reuse dynamic results across drivers or
searches. Without a destination only the 30 station calls are needed. Direct
NO_ROUTE is cached and leaves detour undefined while retaining real via totals.
Onward NO_ROUTE preserves station-only metrics.

Engine failures/timeouts from any leg fail the request with 503/504; invalid
routing requests return 422. A standalone no-route result returns 404. Only real
no-route results make candidates unreachable. No outage substitutes Euclidean
distances, raw-GPS matching or a mock adapter.

Energy feasibility remains road distance in km plus the existing 0.5 km reserve
against remaining range. Queue, station capacity and service duration remain
operational inputs to eligibility and future ranking; they do not modify the
road path in this implementation. Week 4 ranking remains outside this migration.

## Verification and historical evidence

Functional verification passed with 239 tests (Week 1: 37; Week 2: 69; Week 3: 71;
migration: 62), live API and explicit outage checks, and identical hashes for all
63 Dataset files. Formal reporting/freeze remains a separate final gate.
`runtime/migration/api-smoke.json` also records deployed HTTP request latency at
concurrency 1/5/10: median 777.228/2,384.797/6,621.727 ms and P95
955.799/2,945.508/7,358.554 ms for 20 requests per level. These local endpoint
measurements include serialization/search and are distinct from the service-only
benchmark; they do not establish a production SLA. `api-outage.json` confirms
route/matching/candidate 503, realtime `ENGINE_UNAVAILABLE`, health 200 and
readiness 503 with GraphHopper unavailable.

`scripts/verify_graphhopper.py` and `scripts/smoke_test_week3.py` verify both
profiles, actual via legs, Dataset candidate searches, BOTH call sharing, missing
destination behavior and `/api/v1/route` against live GraphHopper. They fail on
outage. `scripts/benchmark_week3.py --iterations 20` records 20 distinct Dataset
trip starts and exact forwarded HTTP route counts. See [WEEK_3](WEEK_3.md) for
measured distributions and their shared-client/service measurement scope.

The old strategy contained conceptual future types, additional engine choices,
unimplemented matrix calls and speculative performance targets. Those are not
current contracts or acceptance results. Final migration quality/freeze is
tracked in [GRAPHHOPPER_FULL_MIGRATION_PLAN](GRAPHHOPPER_FULL_MIGRATION_PLAN.md).
