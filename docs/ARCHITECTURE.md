# Current architecture

Updated 2026-09-21 for the sole-GraphHopper migration. Weeks 1–3 behavior is
implemented; functional verification passed with 239 tests, live API/outage
checks and all 63 Dataset file hashes unchanged. Final reporting and formal freeze
remain tracked in [GRAPHHOPPER_FULL_MIGRATION_PLAN](GRAPHHOPPER_FULL_MIGRATION_PLAN.md)
and the [migration report](GRAPHHOPPER_MIGRATION_REPORT.md).
Historical Week 1 freeze reports describe the earlier engine and do not certify
this replacement runtime.

## Components and data flow

```text
Immutable Dataset OSM PBF --> GraphHopper 11 graph import --> car / motorcycle
Immutable directed road CSVs --> PostGIS road_segments and spatial index

Batch GPS / realtime GPS --> shared MapMatchingService
    --> GraphHopperMapMatchingAdapter --> POST /match (GPX)
    --> project observation projection onto actual matched geometry
    --> PostGIS Dataset segment resolution
    --> observation results / realtime state

Telemetry / explicit driver intent --> Week 2 DemandService
    --> EnergyServiceRequest --> CandidateSearchService
    --> all stations --> station/service alternatives
    --> injected RoutingEngine --> GraphHopperRoutingAdapter --> GET /route
    --> multi-leg metrics + operational snapshots + eligibility
    --> eligible candidate set for future Week 4 ranking
```

The modular monolith uses FastAPI and PostgreSQL 16/PostGIS. GraphHopper 11.0 is
the sole production routing/matching service, built from its pinned official JAR
on the pinned Java 21 image. Release 11.0 requires Java 17+. Compose runs `db`,
`graphhopper` and `api`. No engine selectors, legacy engine services, or mock
runtime fallback are part of the current architecture.

The application lifespan creates one shared `httpx.AsyncClient` for both routing
and matching, and closes it at shutdown. Request-local candidate result reuse
is separate from this connection pooling; it does not cache routes between
searches.

OSM is the canonical map source. `hanoi-patched.osm.pbf` is mounted read-only;
`hanoi-baseline.osm.pbf` remains a reference. The graph cache is generated under
`runtime/graphhopper/gh-cache-11`, outside Dataset V1. PostGIS data is loaded by
`scripts/load_road_network.py` from canonical road CSVs.

## Domain contracts and vehicle profiles

`RoutingEngine.route(RouteRequest) -> RouteResult` and `MapMatchingEngine` keep
business logic separate from engine HTTP formats. Via points are part of the
route request. Separate matrix or alternate-engine implementations are not
required for the current scope.

`EV_CAR` maps to `car`; `EV_MOTORBIKE` maps to `motorcycle` for both matching and
routing. Candidate search uses resolved vehicle capability when its energy
request omits category and rejects a conflicting explicit category. Matching
can resolve canonical vehicle/trip/driver metadata; missing or conflicting
metadata is rejected. No global motorcycle/car default overrides vehicle type.

The GraphHopper adapter uses repeated `point=latitude,longitude` parameters,
encoded `paths[0].points` strings, meters, and milliseconds converted to seconds.
`leg_distance` and `leg_time` path details provide actual per-leg metrics.
Malformed successful responses are engine errors, not fabricated zero metrics.
Nonempty constraints, dynamic routing inputs, profile hints, and objectives
other than `MIN_TRAVEL_TIME` are rejected explicitly by this implementation.

## Matching identity and quality

The adapter submits GPX to GraphHopper `/match` and requests unsimplified matched
geometry and `osm_way_id` path details. GraphHopper's JSON does not guarantee one
returned tracepoint per input observation. The project reconstructs observation
locations by nearest projection onto the actual matched geometry, with a 100 m
residual cutoff. This projection is not an alternate routing engine and does not
turn the raw GPS point into a successful matched position on failure.

The per-observation score is `max(0, 1 - distance_to_matched_path_m / 100)` for a
matched observation. Overall quality is the mean of this proximity score across
all observations. It is a project-defined geometric quality measure, not a
calibrated probability, native GraphHopper posterior, or interchangeable with
historical engine confidence. The GraphHopper matching request uses GPS accuracy
20 m; quality calibration and ground-truth accuracy remain measured separately.

PostGIS resolves the projected position to frozen Dataset directed segments,
using actual OSM way identity when available and the matched path's traversal
bearing. Unresolved IDs stay null with an explicit resolution status. Internal
GraphHopper edge/node IDs are never renamed Dataset segment IDs or OSM IDs.
Nearest-path projection can be ambiguous at loops, crossings and parallel roads;
resolver provenance and coverage must accompany any accuracy claim.
When revisited geometry leaves traversal ambiguous, or PostGIS cannot distinguish
a directed-segment identity, resolution is `AMBIGUOUS`: `road_segment_id` and
`direction` are withheld. The geometric matched location may still be returned.
This preserves the distinction between path proximity and a proven directed
Dataset identity instead of choosing an arbitrary direction at a loop.

## Motorcycle model limitations

The project model uses the maintained motorcycle model's `car_access` and 90%
of car average speed, excludes MOTORWAY, penalizes TRUNK, retains rough-surface
restrictions, and caps modeled speed at 60 km/h. The cap is a local modeling
assumption, not a legal-speed guarantee. Turn-cost configuration uses motorcycle
and motor-vehicle turn restrictions.

`car_access` is still shared: `motorcar=no` excludes motorcycles as well as cars.
This conservatively excludes the patched Cầu Thanh Trì way `881947000` even if
motorcycles could otherwise use it. Complete independent motorcycle-tag access
semantics would require a separately validated parser and graph reimport. The
frozen OSM files are not patched to bypass the limitation.

## Failure and candidate semantics

Routing dependency failure produces HTTP 503, timeout 504, invalid request 422.
Standalone `/api/v1/route` returns 404 for a genuine no-route result. Batch and
realtime matching likewise expose dependency/no-match states rather than fake
success. `/health` is liveness; `/ready` and `/readiness` require routes from both
profiles and populated PostGIS road data.

The deployed outage check (`runtime/migration/api-outage.json`) confirms 503 for
route, matching and candidate endpoints with an unavailable GraphHopper;
realtime exposes `ENGINE_UNAVAILABLE`, liveness stays 200, and readiness becomes
503. Normal deployed checks and the local HTTP concurrency baseline are in
`api-smoke.json`. Twenty requests at concurrency 1/5/10 measured median
777.228/2,384.797/6,621.727 ms and P95 955.799/2,945.508/7,358.554 ms, including HTTP
serialization and station search. These local measurements are not capacity SLAs.

Candidate identity remains `(station_id, service_type)`. Eligibility is evaluated
before any optional reduction. Routing results are cached only within the current
search: one direct route and one pair of routes per station, shared by CHARGING
and BATTERY_SWAP alternatives. With 30 reachable stations and a destination this
is 61 calls, including BOTH's 60 alternatives. Without a destination it is 30
calls. Direct NO_ROUTE is cached; successful via totals are retained without
inventing direct/detour values. An onward NO_ROUTE leaves station-only metrics.
Infrastructure failures from any leg abort the search as dependency errors.

Week 2 demand rules, service expansion, eligibility precedence and station
operations remain unchanged. No ranking scores or Week 4 implementation are
introduced. Labels remain evaluation-only.

## Historical architecture

The earlier foundation diagram used OSRM preprocessing and planned multiple
engine adapters. ADR-010 supersedes that runtime choice and any active engine
selection path. ADR-008's domain independence remains in force. Old benchmark
or freeze documents remain historical evidence; they are not proof of current
GraphHopper quality or production readiness.
