# DECISIONS

## ADR-013: Week 4 snapshot persistence and eligibility ownership

**Date:** 2026-09-21. **Status:** Approved by the user for Week 4.

Week 3 owns eligibility. Week 4 ranks an already-valid eligible candidate set.
An eligibility-affecting change after search returns HTTP 409 with
`error_code=CANDIDATE_STATE_CHANGED`, the candidate search ID, changed
station/service identities, previous/current state and
`action=RERUN_CANDIDATE_SEARCH`. Ranking must neither rerun eligibility nor drop
invalidated candidates and proceed. The synchronous orchestrator may retry the
whole candidate search exactly once; a second conflict is returned to the caller.
Queue changes below the existing eligibility limit, traffic, service estimates
and freshness changes are ranking context. OFFLINE, zero usable capacity, absent
swap inventory, compatibility changes and represented reachability invalidation
are candidate-set conflicts. No new dynamic routing state is implied.

PostgreSQL stores immutable timestamped traffic, station and queue snapshots and
server-issued candidate-search evidence. Redis is an optional KV payload cache,
never a source of truth. An authoritative, single-statement database head lookup
pins the snapshot IDs used by each context, including historical requests. Cache
entries must match these IDs; a failed cache write cannot conceal a committed
operational change. Redis failure falls back to PostgreSQL; database failure is
explicit even when payloads are cached. No Kafka, Streams or background reranking.

Use the existing asyncpg dependency for this first application repository (there
is no existing ORM/repository implementation to duplicate). Unique
`(kind, entity_id, timestamp)` identifies a snapshot: identical payload/source
retries return the same ID; conflicting retries return 409. An atomic Redis
compare-and-set prevents older snapshots from replacing newer cache values.

Traffic uses the Dataset `delay_factor` for the driver's known directed segment
as a labelled **origin-segment proxy** for the station leg, matching the reference
generator's coarse approach. It is not route-segment traffic integration. Missing
segment/state retains base GraphHopper duration with explicit missing provenance.
Week 3 exposes no route-to-Dataset-segment traversal mapping; no routes are
recomputed solely for ranking. Canonical estimated queue wait is used once.

The initial runtime policy minimizes station service completion time: adjusted
station travel + queue wait + service time. Detour, freshness and capacity break
ties; no arbitrary generalized weights or urgency weights. The Dataset reference
also includes onward travel and detour/capacity terms, so agreement is a measured
comparison rather than an expected 100%. Unknown queue wait uses a configurable
conservative project assumption of 90 minutes, visibly marked MISSING; it is not
an observed wait or official VinFast policy. Snapshot freshness defaults follow
Dataset cadence (traffic 30 minutes, operational/queue 10 minutes); Redis TTL is
configurable at 60 seconds for memory retention, not validity.

**Trade-off:** The metadata check retains a small database dependency on cache
hits in exchange for deterministic invalidation and request-consistent evidence.
This request-driven Week 4 extension explicitly authorizes persistence, Redis KV,
lightweight observability and local performance measurements without starting
Week 5 continuous recommendation or Week 6 productionization.

Current runtime decisions are ADR-010 through ADR-012 below. ADR-002's initial
OSRM engine choice is historical and superseded. ADR-006's patched-map selection
remains active with GraphHopper. ADR-008's domain independence remains active;
its initial engine and conceptual future interfaces are not current runtime
requirements. ADR-009's candidate policy remains active; its historical latency
and agreement statements do not certify the new runtime.


## ADR-001: Modular Monolith Initially

**Decision**: Use Modular Monolith architecture for the initial implementation.

**Reason**: The six-week scope requires rapid iteration across multiple modules. A modular monolith allows sharing code and data structures between Map Matching, Demand Detection, Candidate Search, and Ranking without distributed system overhead. Each module is a clearly separated Python package within the FastAPI application.

**Trade-off**: If the system scales beyond Week 6 to multi-team or multi-region deployment, extraction will require refactoring. Microservice patterns should not be introduced preemptively.

**Revisit condition**: When deployment requires independent scaling of individual modules or when team size exceeds 10.

---

## ADR-002: OSRM as Initial Map Matching / Routing Engine

**Status: HISTORICAL; superseded by ADR-010.**

**Decision**: Use OSRM (Open Source Routing Machine) as the routing and map-matching engine.

**Reason**: OSRM is production-proven, provides a clean HTTP API, supports MLD (Multi-Level Dijkstra) for fast queries, and has a map-matching endpoint. Dataset V1 provides OSM-derived road data that aligns with OSRM's requirements. No custom routing algorithm is needed for the initial implementation.

**Trade-off**: OSRM requires preprocessing the OSM PBF into OSRM artifacts (extract → partition → customize). The MLD profile is optimized for car routing.

**Revisit condition**: When custom turn-by-turn routing, real-time traffic-reactive routing, or multi-modal routing is required.

---

## ADR-003: PostgreSQL + PostGIS as Geospatial Application DB

**Decision**: Use PostgreSQL 16 with PostGIS 3 as the application database.

**Reason**: PostGIS provides robust geospatial indexing (GiST), spatial queries, and routing graph storage. FastAPI backend can store runtime state, evaluation results, and processed trajectories. PostgreSQL's JSONB support handles semi-structured data from OSRM responses and replay events.

**Trade-off**: PostgreSQL/PostGIS is not purpose-built for real-time routing. For high-volume production routing, a dedicated routing engine like OSRM alone may suffice.

**Revisit condition**: When read-heavy geospatial queries exceed PostgreSQL performance targets.

---

## ADR-004: Dataset V1 as Canonical Project Development Data

**Decision**: Use Dataset V1 (./dataset_v1/) as the authoritative, immutable development dataset for the full six-week project.

**Reason**: Dataset V1 provides a complete, validated, and self-consistent operational dataset covering all six weeks of requirements. It includes ground truth, labels, training data, evaluation data, and replay events. The 163 validation checks and 21 scenario assertions provide confidence in its integrity.

**Trade-off**: Dataset V1 is a synthetic dataset with fixed capacity and station configurations. Real-world deployment will require live station APIs, real GPS streams, and dynamic traffic data.

**Revisit condition**: When a production deployment requires integration with live data sources.

---

## ADR-005: Dataset V1 is Immutable During Normal Development

**Decision**: Dataset V1 is treated as READ-ONLY during the six-week implementation.

**Reason**: Modifying Dataset V1 invalidates the evaluation framework and breaks the validation contract (163 checks, 21 scenarios). Any data derived for application use is placed outside dataset_v1/.

**Trade-off**: If a bug is found in Dataset V1, it cannot be fixed inline. Issues must be reported and resolved through a formal patch process.

**Revisit condition**: When Dataset V1 maintainers provide an official patch mechanism.

---

## ADR-006: hanoi-patched.osm.pbf is Primary Routing Map (Supersedes v1)

**Status: map selection ACTIVE; engine wording superseded by ADR-010.**

**Decision**: Use `hanoi-patched.osm.pbf` as the primary OSRM routing map.

**Reason**: The patched PBF has been approved for production use. It contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì bridge), which is the intended project behavior.

**Trade-off**: The baseline PBF remains available as a reference for historical comparison.

**Revisit condition**: When a new approved PBF patch is provided.

---

## ADR-007: hanoi-baseline.osm.pbf is Reference Map (Supersedes v1)

**Decision**: `hanoi-baseline.osm.pbf` is kept as a reference map only.

**Reason**: The baseline PBF served as the initial OSRM map. With the approval of hanoi-patched.osm.pbf, the baseline is retained for historical reference and comparison purposes.

**Trade-off**: The baseline should not be used for production routing. Both PBFs remain byte-for-byte intact.

**Revisit condition**: When comparing routing behavior between baseline and patched maps is needed.

---

## ADR-008: Engine-Independent Dynamic Routing Domain

**Status: domain boundary ACTIVE; initial engine and future-interface proposal superseded/refined by ADR-010.**

**Decision**: Represent route requests, constraints, objectives, vehicle capabilities, and dynamic context at the project/domain level. Routing engines are adapters behind these contracts.

**Reason**: The six-week project requires increasingly dynamic routing decisions (vehicle-specific access, energy-aware routing, traffic-adjusted ETA, avoid constraints, multi-objective optimization). Hardcoding OSRM's current capabilities into business logic will make future extensions brittle and engine-switching expensive. OSRM remains the initial engine implementation.

**Trade-off**: Slightly more abstraction now, but avoids engine lock-in as dynamic requirements grow. The domain model must be maintained as requirements evolve — it is not a one-time design.

**Domain model scope:**
- `RouteRequest` with origin/destination/via, vehicle profile, constraints, optimization objective, dynamic context
- `RouteResult` with geometry, distance, duration, legs, detour metrics, engine metadata
- `RoutingEngine` interface (route, route_via, matrix, map_match)
- Separation of routing (path computation) from recommendation (station scoring)

**Week 3 decision gate:** Reassess when concrete use cases (vehicle-specific routing, energy-aware paths, dynamic cost propagation) demonstrate an OSRM limitation. Evidence-based benchmarking takes priority over feature checklists.

**Revisit condition**: When Week 3/4 benchmarks show OSRM cannot express a required constraint, or when custom costing is required and OSRM profile rebuild is too slow for production.

---

## ADR-009: Candidate Search Ordering, Composite Identity, and Evaluation Precedence

**Status: policy ACTIVE. The old ~86 ms benchmark used a mock adapter; it is historical, not current GraphHopper latency. Agreement claims below describe the earlier eligibility replay, not current engine accuracy.**

**Decision**:
1. Represent candidate identity as the composite tuple `(station_id, service_type)`.
2. Enforce strict pipeline ordering: All Stations → Service Alternatives Expansion → Full Eligibility Evaluation → Eligible Candidates → Optional Deterministic Top-N Reduction.
3. Enforce deterministic candidate rejection reason precedence: `UNREACHABLE` → `INCOMPATIBLE` → `OFFLINE` → `NO_SWAP_BATTERY` → `FULL` → `EXCESSIVE_QUEUE` → `INSUFFICIENT_SOC_TO_REACH` → `ELIGIBLE`.
4. Decouple Candidate Search from Week 4 Ranking: Candidate Search computes physical multi-leg routing metrics (distance, duration, detour, base ETA) and operational availability; it does NOT assign ranking scores, weights, or recommendations.

**Reason**:
Early iterations of the platform (pre-Dataset V1.3) suffered from two major architectural defects:
- Collapsing candidates to physical `station_id` caused multi-service stations (offering both charging and swap) to arbitrarily drop one service alternative for swap-capable vehicles.
- Performing nearest-N prefiltering by Euclidean distance prior to checking compatibility or operational status excluded viable stations along the route and recommended unreachable/incompatible ones.
The deterministic precedence guarantees 100% semantic alignment with canonical Dataset V1.3.1 ground truth.

**Trade-off**: Evaluating all 30 physical stations and up to 60 service alternatives generates 61 route calls per request. Benchmark profiling shows median latency is ~86 ms, well within real-time budgets, and avoids premature optimization.

**Revisit condition**: If the station network expands from 30 stations to >1,000 stations in production, introduce spatial grid/quadtree bounding-box prefiltering with safety reachability buffers.


---

## ADR-010: GraphHopper as the Sole Routing and Matching Runtime

**Date:** 2026-09-21. **Decision:** GraphHopper 11.0 replaces the prior production
engine for both routing and map matching. No engine selectors, alternate-engine
services or mock runtime fallback remain authorized. Mock adapters remain only
for tests. The existing domain protocols and request/result types stay separate
from GraphHopper's HTTP schema. This supersedes ADR-002's runtime choice and the
old dual-engine root plan; it does not change Week 2 policies or add Week 4 work.

Use the pinned official 11.0 JAR on the pinned Java 21 runtime. Release 11.0
requires Java 17+, not Java 25. Import only the read-only approved
`hanoi-patched.osm.pbf`; OSM is canonical. The baseline PBF is reference-only.
Generated graph data belongs in `runtime/graphhopper/gh-cache-11`.

Map vehicle categories deterministically: `EV_CAR -> car`,
`EV_MOTORBIKE -> motorcycle`, identically for routing and matching. Missing or
conflicting category metadata is an explicit request error. Global profile
defaults and overriding profile hints are unsupported. Routing requests use real
per-leg details, encoded geometry strings and explicit dependency errors.
Unsupported constraints, alternate objectives and dynamic context are rejected
rather than silently ignored.

**Reason:** The user selected a complete sole-engine migration with consistent
vehicle-aware behavior. The existing adapter contracts support that replacement
while keeping candidate, demand and future ranking logic engine-independent.

**Trade-offs:** The maintained motorcycle model uses `car_access`; therefore
`motorcar=no` conservatively excludes motorcycles, including patched Cầu Thanh
Trì way 881947000. The project model excludes motorways, penalizes trunk roads,
and caps modeled speed at 60 km/h, which is an assumption rather than a legal
speed claim. Full independent motorcycle access requires a validated separate
parser and reimport; the frozen PBF must not be altered to bypass this limit.

**Connection ownership:** Routing and matching use one asynchronous HTTP client
owned and closed by the application lifespan. This pools connections while
retaining request-local route-result caching and explicit dependency failures.

**Evidence and gate:** See `GRAPHHOPPER_MIGRATION_RESEARCH.md`, live smoke evidence,
and the measured Week 3 benchmark documented in `WEEK_3.md`. Benchmarks diagnose
behavior and regressions, not a fallback engine choice. Functional verification
passed with 239 tests, live API/outage checks and all 63 Dataset hashes unchanged.
Final reporting and formal freeze still require the migration execution gate;
this ADR alone does not declare a freeze.

---

## ADR-011: Honest Matching Reconstruction and Dataset Identity

**Date:** 2026-09-21. **Decision:** Submit GPX to GraphHopper matching and request
actual unsimplified path geometry with OSM way details. Reconstruct observation
locations by projecting each onto that geometry, with a 100 m residual cutoff.
Use PostGIS to resolve canonical directed Dataset segments from the projected
location, actual OSM way when available, and path traversal bearing. Unresolved
identities stay null with resolution provenance; never relabel GraphHopper
internal edge/node IDs as Dataset or OSM identities.

When projected traversal is ambiguous at revisited geometry, or PostGIS directed
segments remain tied, return resolution `AMBIGUOUS` and withhold
`road_segment_id` and `direction`. A matched geometric location can remain
available without inventing a directed identity. Regression checks cover this
distinction.

Per-observation quality is `max(0, 1 - residual_m / 100)` for matched observations;
overall quality averages proximity scores across all observations. This is
project geometric quality, not calibrated probability, native GraphHopper
posterior or historical engine confidence. The matching request uses GPS
accuracy 20 m. No raw-GPS success fallback is permitted on dependency failure.

**Reason:** The maintained matching JSON does not provide a reliable one-to-one
observation result array or the earlier engine's confidence semantics. Explicit
reconstruction and identity provenance preserve truthful domain outputs.

**Trade-offs and gate:** Projection can be ambiguous at loops, crossings and
parallel roads, and unresolved identity coverage can differ from geometric
matching coverage. Ground-truth direction/identity tests and live matching
quality evaluation must report these separately. Existing freeze/quality reports
are historical and cannot certify this implementation automatically.

---

## ADR-012: Frozen Validation and Live Migration Evidence

**Date:** 2026-09-21. **Decision:** Run the canonical Dataset validator through
`scripts/validate_frozen_dataset.py`, redirecting generated report writes into
`runtime/migration/validation`. Preserve every Dataset file, including its
validator source and PBFs. The current run has 152 PASS / 0 FAIL and 22/22 scenario
assertions; older 163/21 references are retained only as superseded history.

Live smoke/benchmark scripts must forward requests to the actual GraphHopper
adapter and fail on outage. Request-local caching shares station route results
between service alternatives and caches direct NO_ROUTE; no cross-request
runtime cache is introduced. Benchmark fixtures use runtime Dataset inputs,
while labels stay offline-evaluation-only. Reports record request counts,
measurement scope and engine/profile evidence under `runtime/migration`.

**Reason:** A canonical validator can generate reports without requiring writes
to frozen source data. Real-engine evidence must remain distinguishable from
unit-test mocks and historical business-policy replay.

**Trade-off:** The documented Week 3 benchmark measures the candidate service
with a shared injected HTTP client, excluding initial fixture/catalog loading
and HTTP API overhead. It is not a production endpoint or concurrency benchmark.
A separate deployed HTTP run (`runtime/migration/api-smoke.json`) measures 20
requests each at concurrency 1, 5 and 10, including serialization and station
search. Its median/P95 values are 777.228/955.799 ms, 2,384.797/2,945.508 ms and
6,621.727/7,358.554 ms respectively. These are an initial local baseline, not a
production SLA. `api-outage.json` confirms explicit failures without a fallback.
The final passing test distribution is Week 1: 37, Week 2: 69, Week 3: 71 and
migration: 62. The integrity manifest records 63 unchanged files. Larger
performance work remains subject to the project's week boundaries.


## ADR-014: Week 5 request-driven refresh and causal evaluation

**Date:** 2026-09-21. **Status:** Approved by the user.

Continuous recommendation means repeated client/replay requests through the existing
Week 2?4 RecommendationWorkflow. A shared small location bridge uses explicit
coordinates (including zero), then current valid matched Week 1 state, then accepted
raw GPS with RAW_GPS_FALLBACK provenance; no location is an explicit error when needed.
No driver-store rewrite, new lifecycle table, background worker, push or streaming.

Finite historical replay uses isolated operational history/cache and advances only
state available at event time. Future state and evaluation labels must not enter
inference. Predictions are persisted before labels are opened for comparison.
Existing immutable candidate evidence and snapshot provenance remain sufficient.

Week 3 retains eligibility and Week 4 ranking. Its one whole-search conflict retry
is unchanged. There is no official numeric latency SLA: measure at least three
warmups and twenty requests per concurrency 1/5/10 where practical, reporting
median/P90/P95/max, successes/errors and workload/cache/environment as an INITIAL
LOCAL WEEK 5 PERFORMANCE BASELINE. Slow correct responses do not fail an invented SLA.
Production optimization, lifecycle/retention, scale, monitoring and deployment
hardening remain Week 6/future scope.
