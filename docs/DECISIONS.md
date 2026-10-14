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
Week 2 API and Week 3-4 RecommendationWorkflow. A shared small location bridge uses explicit
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


## ADR-015: Domain-Driven Vehicle Energy Model and Dynamic Consumption

**Date:** 2026-09-28. **Status:** Approved.

**Context:** The existing demo statically assigned vehicle models to trips without an interactive driver selector. All cars were evaluated with a flat 150 Wh/km consumption rate, and vehicle battery SOC did not decrease as vehicles traveled, leading to static recommendation inputs.

**Decision:**
1. Maintain the canonical VinFast vehicle model catalog in domain backend (`CANONICAL_MODEL_CATALOG`), mapping all 19 official models with exact battery and usable capacities from `dataset_v1/vehicles/vehicle_model_catalog.csv`.
2. Introduce model-specific `PROJECT_ESTIMATE` energy consumption rates based on official range and battery specifications (e.g. VF 3: 95 Wh/km, VF 5: 125 Wh/km, VF 6: 145 Wh/km, VF 7: 165 Wh/km, VF 8: 195 Wh/km, VF 9: 235 Wh/km, motorbikes: 45 Wh/km), maintaining transparent non-official provenance.
3. Expose the vehicle catalog and specifications via an API endpoint (`/api/v1/vehicles`).
4. As vehicles travel distance $\Delta d$, calculate energy depletion in the domain model:
   $\Delta E = \Delta d \times C / 1000$ kWh, $\Delta \text{SOC}\% = (\Delta E / \text{usable\_kwh}) \times 100\%$, and update remaining range accordingly. Subsequent recommendation requests evaluate on the updated dynamic SOC state.


## ADR-016: 3-Tier Container Separation (Nginx Presentation Tier)

**Date:** 2026-09-28. **Status:** Approved.

**Context:** The existing FastAPI container directly hosted and served static HTML/JS demo files under `/demo`. A failure or restart of the API container completely disconnected the frontend.

**Decision:**
1. Separate the presentation tier into an independent Nginx container (`ev_frontend`).
2. Nginx serves all static frontend assets and reverse-proxies `/api/` traffic to the backend FastAPI container (`ev_api:8000`).
3. If the backend is restarted or unavailable, Nginx remains operational and the frontend UI gracefully displays an "API Offline - Reconnecting..." state rather than dropping the connection.
4. Stopping or restarting the frontend has zero impact on the backend API or data tier.


## ADR-017: Core vs Realtime Schema Separation

**Date:** 2026-09-28. **Status:** Approved.

**Context:** Static reference data (`road_segments`, `road_nodes`) and volatile operational time-series data (`state_snapshots`, `candidate_searches`) resided in the same `public` schema in PostgreSQL.

**Decision:**
1. Establish a logical schema separation within PostgreSQL:
   - `core` schema (or `public`): immutable spatial road network and station master records.
   - `realtime` schema: dynamic operational state snapshots and candidate search evidence.
2. Abstract database connectivity such that `REALTIME_DATABASE_URL` defaults to the main database with the `realtime` schema, but can point to an independent physical PostgreSQL instance in production with zero business logic refactoring.


## ADR-018: Lightweight Realtime Operational State Simulator

**Date:** 2026-09-28. **Status:** Approved.

**Context:** Operational state snapshots were static. Demo evaluations did not reflect changing queue wait times, slot availability, or traffic congestion over time.

**Decision:**
1. Build an internal `RealtimeSimulator` executing bounded random-walk Markov transitions for key Hanoi stations and connecting road segments every 30 seconds.
2. Enforce all snapshot validation rules through the existing `IngestionService` (available slots + occupied slots $\le$ canonical capacity, positive service times, speed-delay factor consistency).
3. Demonstrate dynamic recommendation cost variance where station rankings evolve between timestamps $T_0$ and $T_1$ based on live operational changes.


## ADR-019: Multi-Replica API & Nginx Upstream Load Balancing (Superseded)

**Date:** 2026-09-29. **Status:** Historical proposal; deployment claims are not verified.

The deployed Compose topology runs two API containers on one host. The data plane remains single-node. This ADR does not establish host-level failover, zero-downtime resilience, or a production SLA.

**Context:** A single API container was a single point of failure (SPOF) for the application tier. High concurrency could exhaust process worker threads, and an API restart interrupted incoming client traffic.

**Decision:**
1. Deploy dual stateless backend replicas (`ev_api_1` and `ev_api_2`) sharing database, Redis, and GraphHopper dependencies.
2. Configure Nginx upstream `backend_cluster` with `least_conn` load distribution and automated failover (`proxy_next_upstream error timeout http_502 http_503 http_504; proxy_next_upstream_tries 2`).
3. Ensure background singleton tasks (such as the `RealtimeSimulator`) execute on designated replica `api_1` while `api_2` operates purely on request serving to avoid duplicate snapshot generation.
4. Verify zero-downtime resilience: terminating one API replica results in seamless request forwarding to the healthy replica without dropped client requests.


## ADR-020: Production Readiness Overhaul — Dead Code Elimination, Async DB Unification & Frontend Modularization

**Date:** 2026-10-07. **Status:** Approved.

**Context:** External architectural evaluation identified several critical maintainability, testing, and production weaknesses:
1. Over 1,500 lines of dead code in an unused `route_history` service.
2. Inconsistent sync/async database execution mixing `psycopg2` and `asyncpg` within async FastAPI handlers.
3. Abuse of global singletons for state and dependencies.
4. Hardcoded assumptions for Hanoi and VinFast vehicles, preventing multi-city and multi-brand deployment.
5. Monolithic `driver_mode.js` (~2,529 lines) with zero automated frontend test coverage.
6. Undefined variable bugs (`DriverTraceState`, `origin=origin`, `window` in Node.js).

**Decision:**
1. **Dead Code Elimination:** Completely delete `route_history` service, models, repositories, API endpoints, and associated scripts (>5,600 lines eliminated). Remove all references across configuration, docker-compose, and test suites.
2. **Unified Database Execution Model:** Standardize all FastAPI async routes on `asyncpg` connection pooling registered via application lifespan (`core/lifespan.py`). Eliminate synchronous blocking `psycopg2` calls in `health.py`. Wrap low-level database errors in domain exceptions (`SegmentResolverUnavailableError`, `SegmentResolverError`) so controllers remain decoupled from the driver.
3. **Explicit Dependency Injection:** Eliminate hidden global singletons. Wire services and adapters into `request.app.state` during application lifespan. Inject services into routes via explicit FastAPI `Depends()`, supporting clean mocking in unit tests while retaining isolated testing fallbacks.
4. **Environment-Driven Configuration & Multi-Brand Catalog:** Parameterize city center, bounding box coordinates, and default zoom levels in `config.py` and `.env.example`. Expose `GET /api/v1/config` for frontend bootstrapping. Support dynamic multi-brand EV registration (`register_model`, `register_vehicle`) supporting non-VinFast brands (Tesla, BYD, Hyundai, Dat Bike) and multiple Vietnamese cities (Hanoi, HCMC, Da Nang).
5. **Modular Frontend Decomposition:** Decompose monolithic `driver_mode.js` into cohesive single-responsibility domain modules:
   - `domain/vehicle_model.js`: Battery physics, consumption, range calculation, multi-brand specs.
   - `domain/driver_state.js`: Driver state machine and transition validation.
   - `domain/navigation_tracker.js`: Route progress tracking, off-route detection, reroute throttling.
   - `domain/station_evaluator.js`: Station compatibility and candidate filtering.
   - `ui/cockpit_renderer.js`: Pure HTML card template generation (Available, Offline, Complete).
   - `ui/drawer_renderer.js`: Station drawer card markup for en-route vs at-destination intents.
   - `ui/map_picker.js`: Interactive origin/destination coordinate selection state machine.
6. **Automated Frontend Testing:** Establish 54 pure Node.js automated unit and scenario tests (`node --test tests/frontend/*.mjs`), executable via `npm test` and `make test-frontend`, testing all domain logic without browser DOM overhead.


## ADR-021: Route Familiarity v2 as an Opt-in Explanation and Ranking Tie-breaker

**Date:** 2026-10-07. **Status:** Approved for Phase 4 implementation.

**Context:** Route history and familiarity were removed in ADR-020 because the previous code mixed synchronous database access into async requests, used hidden globals, and did not apply its placeholder similarity to ranking. The product requirement for personal and community route familiarity remains.

**Decision:** Rebuild the capability with ordered, distance-weighted H3 Resolution 11 signatures, asyncpg persistence, protected trusted-producer ingestion, and an opt-in `ENABLE_ROUTE_FAMILIARITY=false` default. Personal familiarity may add only a configurable nonnegative penalty capped at 30 seconds after eligibility and physical service-completion costs are established. Community evidence is explanatory only. No familiarity input changes eligibility, physical ETA, queue/service semantics, or the existing 409 retry. No personal-history read API or raw route logging is added. A local H3 v4 browser bundle may render resolution-11 explanation cells.

The current `/recommend` boundary does not authenticate end users. When enabled, V2 therefore requires a configured identity HMAC secret and a trusted gateway signature over the request's exact driver ID; requests without a valid signature are rejected before history access. Ingestion remains restricted to a trusted producer token. Event-time queries must exclude route records completed after the evaluated request time. History lookup and route-signature sizes are bounded and truncation is explicit. This ADR authorizes Phase 4 only and does not authorize Week 6 infrastructure or unrelated work.

Operations remain limited to the current single-host topology: API replicas on one host share one single-node data plane. Route familiarity schema changes are explicit; `make migrate-route-familiarity` applies the additive table/index DDL and `make rollback-route-familiarity` drops that table and its history. The opt-in local benchmark measures production signature/similarity/evaluation code at bounded logical data sizes. For PostgreSQL evidence it creates and drops a UUID-named disposable database, seeds only synthetic rows there, and records the actual asyncpg repository query plans; the configured application database is never written by the benchmark.

## ADR-022: Offline geometric comparison and causal familiarity weighting

**Date:** 2026-10-10. **Status:** Authorized by the user for implementation following review; runtime activation remains opt-in.

**Decision:** Whole-trip offline evaluation freezes the initial GraphHopper proposal and uses the whole observed GPS trajectory. Replay progress does not change the comparison extent. Raw observed geometry is labelled explicitly and is not asserted to be a successful map match or ground truth. Comparison defaults to H3 resolution 9, with 8/9/10 available for evaluation; the existing resolution-11 signature remains a persistence/search index, not the similarity metric. Directed geometric projection, ordered one-use distance accounting and neighboring-cell lookup replace exact-cell overlap in familiarity ranking. A 10 m global sampling grid reduces vertex-density dependence; the result is a corridor approximation with project assumptions of 45 m lateral tolerance and 60 degree heading tolerance. It is not proof that adjacent streets are the same road.

Bound vertices/distance, resampled geometry, query-cell expansion and comparison-pair work; return unavailable/reject work exhaustion explicitly. One assessment can prepare at most 50,000 pieces across its unique routes; this budget is consumed before resampling allocation. CPU comparison runs outside the request event loop. Reuse prepared geometry and comparison results only within one assessment batch. No new infrastructure or cross-user cache.

Add optional geometry and started_at to completed history using additive, idempotent migration. Preserve existing rows. Trusted retries can fill previously null evidence if the immutable trip signature agrees, but cannot replace known evidence. Missing geometry/start is unavailable evidence; no cell-center reconstruction or destructive backfill. Only records completed strictly before the request time are usable. The 7-day default and 30-day option group comparable history by trip start in Vietnam time. Community remains suppressed below five supporting drivers and never changes ranking.

The existing personal penalty remains nonnegative and capped at 30 seconds; it changes final ranking cost only, not eligibility, physical ETA or HTTP 409 retry. Protected driver history still requires the exact-driver HMAC identity boundary and trusted ingestion token. Anonymous route comparisons do not access history. Feature-off remains the default, and this change does not authorize exposing signing/ingestion secrets to the browser.

**Energy:** Backend power-step owns observed-interval energy estimation and SOC updates; frontend displays those results. Catalog boot preserves nullable physical metadata and per-field provenance. VF3 maximum motor power 30 kW has a brochure citation; the remaining physics coefficients are project assumptions, not officially verified or hardware-calibrated. Unsupported models return an explicit unavailable estimate instead of being mapped to VF3. Interval integration assumes linear speed change, uses midpoint power, and supports auxiliary load at rest and bounded regenerative braking. Capability exceedance is explicit rather than silent clipping. Range remains the labelled catalog Wh/km estimate pending independent energy calibration.

**Evidence:** See `docs/reports/offline-route-weighting-fixes-2026-10-10.md`. Historical ADR-021 acceptance records describe their earlier baseline and are not overwritten. No Dataset V1 edits, new production SLA, new routing engine or streaming worker are introduced.



## ADR-023: One station chooser and compact Driver cockpit

**Date:** 2026-10-10. **Status:** Authorized by the user.

**Decision:** Reuse the station drawer as the sole station chooser. Show up to five unique stations in backend-ranked order, followed by the remaining catalog in a native disclosure. Recommendation refresh does not open another panel or select a station. Keep the drawer disclosure, scroll and focused station action across updates. The cockpit recommendation is a compact summary with a cost-detail action.

Mobile starts with a compact cockpit containing destination, remaining distance, estimated driving ETA, SOC and primary actions. A semantic button expands it; opening the station bottom sheet hides the cockpit so its controls cannot obstruct the chooser. Native details contains coordinates, road identity, replay speed, simulation SOC and H3 analysis. Preserve its state and controls across replay updates; update model/power values incrementally. No new dependencies or historical trip picker.

Remaining road distance comes from the untraveled route geometry; straight-line fallback is explicitly labelled. ETA scales the active engine route duration by remaining distance and is labelled an estimate; it excludes station queue/service and is never taken from an unselected station recommendation. Combined selected legs include driving to the station and onward to B. Unknown timing remains unavailable. This is not a live traffic or segment-speed forecast. Backend ranking, eligibility, offline comparison and Dataset V1 are unchanged.

**Evidence:** [Driver UI verification](reports/driver-ui-panels-2026-10-10.md).

## ADR-024: Separate station intent from physical energy warnings

**Date:** 2026-10-12. **Status:** User-authorized bug fix and project review.

**Decision:** Preserve the canonical `need_service`, `request_valid` and `reason_code` service-intent contract. An explicit valid station request remains `VALID_REQUEST` even with ample battery. Add optional `energy_assessment` carrying the existing backend demand detector's physical decision and warning level. The backend owns thresholds; the UI maps warning level/reason to presentation. Missing/invalid/unsupported evidence must not default to a safe battery or a low-reserve warning. Legacy manual-request evidence without a physical assessment is unavailable; no database migration is needed.

Propagate detector-derived range to candidate search when range is absent. Explicit requests retain valid supplied range/trip/reserve even when physical assessment is unavailable due to missing SOC. Reject nonfinite telemetry at demand/candidate HTTP boundaries. During locked station navigation, reuse `/demand/evaluate` to refresh energy without reranking or changing the selected station. Manual SOC/model changes, accepted power steps and newer drawer requests invalidate outstanding assessment results. Failed stale requests must not clear newer evidence. No second threshold policy, new dependency, background server process or Week 6 infrastructure.

**Evidence and limits:** [Energy warning fix and project review](reports/energy-warning-and-project-review-2026-10-12.md). The warning patch is verified separately from eight still-open runtime/UI findings. Physical thresholds and the uncalibrated catalog/physics estimate remain unchanged; no claim of exhaustive project correctness.

## ADR-025: Complete journey scoring, optional destination and isolated synthetic history

**Date:** 2026-10-12. **Status:** Implemented, verified and merged into local main (2026-10-13).

**Decision:** Supersede ADR-021/022's personal-only 30-second ranking preference. Use 80% normalized complete journey time, 10% confidence-adjusted personal mismatch and 10% confidence-adjusted community mismatch. The time reference is the fastest eligible complete journey, floored at one second only for division. Physical ETA excludes preference cost. Personal history uses mean comparable corridor coverage; community includes non-supporting comparable drivers and withholds public support below five drivers. Preserve bounded, causal history and expose truncation.

With B, include A→station→B travel, queue and service. Without B, include A→station, queue and service. After-B includes A→B→station once. Backend confirms the station/service pair, current operational eligibility and constrained geometry; waypoint indices preserve navigation progress when rerouting. Passing a waypoint does not prove that charging or swapping occurred. No durable charger workflow is added.

The current service-time snapshot cannot prove replenished energy. Until such evidence exists, onward feasibility conservatively requires current range to cover the represented legs and reserve. This can exclude feasible charging journeys; it must remain explicit rather than inventing a full battery.

Use only validated `realtime` or `synthetic` history schemas. Production defaults remain `realtime`, feature disabled and no public profile. The opt-in public sample requires enabled synthetic history and exposes only the existing fixed-ID HMAC read signature, never signing or ingestion secrets. Generated manifests and separate behavioral evaluation truth remain inside the repository, outside Dataset V1. Synthetic observations explain simulated usage; they do not establish real driver motivations. No fake/demo badge is added to the UI at the customer's request.

Measure finite virtual-driver GPS at 30 real seconds separately from demand-triggered recommendations. Keep the existing per-IP limit of 100 requests/minute by default; the local measurement explicitly configures 6,000 to measure application capacity rather than the single load client's protective rate limit. No new infrastructure, numeric production SLA or Week 6 productionization is introduced.


ADR-025 implementation pins standalone candidate endpoints to PostgreSQL snapshots, filters stale traffic using existing freshness and an additive fresh-window index, and preserves bounded geometric matching through spatial candidate lookup. GPS/reset uses payload-version-generation compare-and-set and shared location resolution. Nonfinite HTTP numeric input returns serializable 422 errors without committing state. Manual vehicle changes invalidate incompatible navigation; automatic historical assignment preserves original identity and causal time. Shared origin/destination picker entry points close the station drawer before map selection so mobile overlays cannot intercept the intended map click.

**Current evidence:** [Journey ranking and scale-up report](reports/journey-ranking-scale-up-2026-10-13.md). Live API eight checks and desktop/mobile browser 32 checks passed; finite load results are recorded. The measured 500/1,000-driver stages include dependency failures and are not reliable capacity passes.

## ADR-026: Model replenishment and resolve measured capacity failures

**Date:** 2026-10-13. **Status:** Customer-authorized implementation in progress.

**Decision:** Complete the unfinished ADR-025 journey model. Before B, charge only enough for onward network travel plus safety reserve. Without B, and after B when the station is the final goal, target 80% without reducing existing charge. Battery swap predicts receiving 90% of effective usable installed capacity. The customer explicitly selected these defaults; expose them as validated configuration. Current station arrival must remain physically feasible.

Canonical catalogs do not include charging power or charging curves. Use explicit application assumptions for station/vehicle charging limits, efficiency and taper; never reuse motor power. Return arrival, departure and destination energy/SOC, added kWh, computed service duration and provenance. Charging duration replaces the old flat whole-service estimate; it is not added on top of that estimate. Swap duration still comes from the operational snapshot. Candidate search, ranking refresh and selected-plan confirmation use one shared energy model. Deduct after-B prefix energy exactly once. Missing evidence and infeasible replenishment remain explicit.

This predicts a plan, not proof of service: reaching a station waypoint must not manufacture accepted SOC. Keep physical battery warnings separate from predicted post-service energy. Ranking retains 80/10/10 and queue remains counted once. Do not edit canonical data or consume evaluation labels. Old flat-duration ranking baselines remain historical evidence rather than ground truth for the new service model.

Resolve the measured 500/1,000-driver dependency failures by first recording sanitized exception type and duration and measuring the actual bottleneck. A successful measurement with errors is not a capacity pass. Do not use arbitrary timeout increases or new infrastructure to conceal failures. Repeat real 30-second GPS workloads and independently sampled recommendations, including a longer observation of backlog and memory. Work plan: [completion plan](superpowers/plans/2026-10-13-replenishment-scale-completion.md).

**Measured capacity ruling:** Two single-worker API replicas passed the finite workload but failed the sustained stress workload of 1,000 GPS sources and 25 recommendations every 30 seconds. CPU profiles and locally equivalent matcher caching reduced wasted work, yet the sustained queue still grew. Scale the existing modular-monolith API tier to four single-worker replicas behind the existing Nginx `least_conn` gateway, using available local CPU and shared Redis/PostgreSQL. This avoids multiple simulator producers and changing per-process Prometheus semantics. Only `api_1` is the simulator producer. Set each adapter's configurable route budget to four so the aggregate remains sixteen. Redis's 0.2-second budget and GraphHopper's 10-second network timeout remain unchanged. No new service technology, engine fallback, cloud resource or distributed database is introduced.

The existing per-IP rate limiter remains 100/minute **per API replica**, not a cluster-wide quota; this was already local to each of the previous two replicas. Capacity tests explicitly use the existing local 6,000/minute setting. Repeat the sustained measurement after this deployment; do not infer success from the replica count or turn the stress rate into an unapproved production SLA.

**GPS cadence correction:** The measured 30-second cadence exposed a 30-second default matching-context window: slight scheduling jitter removed the preceding point and returned WARMING_UP despite an established valid session. Set the default context window to the existing 60-second session-gap boundary; retain the 50-point cap, explicit caller-selected windows, three-observation warmup and reset on a gap greater than 60 seconds. This restores matching at the approved cadence rather than lowering the workload. Earlier measurements must disclose their high warmup counts and cannot establish full matching capacity. New boundary regressions cover 30.001/59.999/60 seconds and a session break above 60 seconds; rerun real measurements after this change.

Remove unused signature-array fields from history read projections and decode identical serialized geometry once per assessment. This reuses the existing request-local memoization pattern; it does not change causal SQL selection, community denominator, caps, per-trip point accounting, ingestion schema or ranking results. Keep the current history-cell work guard even though the community query now uses cells only as a nonempty gate. Independent review and full-assessment regressions verify equivalence before new load measurements.

**Matching acceleration experiment:** The final full-matching finite stages passed, but recurring 1,000-driver GPS plus 25 recommendations/30 seconds still overloaded the eight-logical-CPU host. GraphHopper 11's [matching implementation](https://raw.githubusercontent.com/graphhopper/graphhopper/11.0/map-matching/src/main/java/com/graphhopper/matching/MapMatching.java) uses edge-based Dijkstra without prepared landmarks; CH preparations do not accelerate this matching path. Prepare separate car/motorcycle landmarks in a new generated graph directory, retaining the closed baseline graph and unchanged canonical PBF, profiles, weights and turn restrictions. Matching then uses GraphHopper's supported edge-based A* with landmark lower bounds. This is the same production engine, not a fallback or a new service technology. Ordinary routing remains CH; explicitly disable LM in the existing congestion POST to preserve its flexible solver and custom-model behavior. Compare real geometry, costs, OSM details, directed resolution/ambiguity and timings before adopting the preparation and rerunning sustained load. Preparation alone is not a capacity pass; nearby observations can be faster with Dijkstra.

**Experiment outcome — rejected:** Same-server alternating controls retained matching/route/directed-resolution results, including 390 ambiguous observations with IDs/direction withheld. LM was slower: original matching samples mean 54.62 ms versus Dijkstra 12.37 ms; sampled actual-load traces mean 23.07 versus 17.28 ms. Restore the prior graph configuration and congestion request; retain the isolated generated graph and evidence. A long environment/tool pause invalidated one route's wall-time sample and overall probe duration, not the completed paired matching comparison. This experiment is not an adopted runtime change or a capacity pass.

**Complete CPU admission:** Signature preparation previously used the general thread pool outside the evaluator's admission, allowing GIL-heavy signature and comparison jobs to overlap on one API. The recommendation workflow now passes the persistent evaluator's existing runner to its snapshot-scoped candidate service. Signature, query and comparison work share the same slot/cancellation drain; no new per-request semaphore, global thread-pool policy, timeout or workload reduction is introduced. Standalone/feature-off behavior and invalid-geometry semantics are unchanged. Existing timing logs now record signature CPU separately, and the load runner records actual selected personal-history/community-cohort counts rather than treating AVAILABLE alone as proof of both evidence sources.

## ADR-027: Seven-day departure origins instead of visit weights

**Date:** 2026-10-14. **Status:** Owner-authorized on
`feat/h3-departure-statistics-7d`; separate permission required to merge.

**Problem:** The Hanoi-wide overlay selects 425 resolution-9 cells from static
visit weights. These are not spatial coverage or evidence of leaving an instructed
route. Existing completed histories do not record corresponding active guidance.

**Decision:** Preserve legacy history and add separately protected paired guidance
versions/observations using existing PostgreSQL/H3. Count every confirmed exit,
rearming after confirmed return. Guidance changes do not manufacture exits.
Aggregate all comparable completed guided trips in seven days ending at event time.
Color by distinct departing trips / distinct reached guided trips per cell and
show total confirmed events separately. Missing evidence is gray; never infer
departure or motivation from visits or today's reconstructed routing result.

Reuse the 45 m lateral / 60 degree heading corridor assumptions. Three samples and
30 m confirm exits/returns. Gaps above 60 s, jumps above 200 m, implausible movement
and ambiguous projections break continuity. The last unambiguous guided position
approximates the exit origin; it is not a verified junction. Exclude uncertain
no-event cell contributions from denominators. Preserve production cohort privacy
and explicitly describe synthetic data. Coarsen grid detail to cover the viewport
within 500 cells, aggregate at that resolution, never sum child percentages. Keep
whole-trip comparison separate and 80/10/10 ranking intact.

**Evidence:** Independent fake maneuver truth, real GraphHopper identity control,
isolated PostgreSQL/API and desktop/mobile browser checks. Synthetic data establishes
algorithm behavior only. See the [plan](superpowers/plans/2026-10-14-h3-departure-statistics.md)
and [branch report](reports/h3-departure-statistics-2026-10-14.md).

**Owner screenshot correction:** "Coverage" means footprints originating from driver
journeys, not covering empty geographic space. Supersede the viewport-grid/coarsening
portion above: do not generate empty background cells, retain the selected H3
resolution, and render only journey evidence. The 500-visible-cell cap remains
explicit. Do not expand the behavioral coverage of 30 small synthetic test trips by
painting the city. Unpaired legacy history remains unavailable for departure weights;
adding its gray footprints is a separate source-selection question.

**Approved history/source extension:** Render gray footprints for all legacy completed
journeys in the same seven-day window. Resolution-11 signature centres approximate
footprints; no saved point timestamps or original guidance are invented. Legacy
visits never enter the guided denominator. Exclude a duplicate legacy identity only
after its paired completion is available at query time. Gray paired observation
cells likewise do not prove adherence. Existing cohort privacy remains in force.

Reuse GraphHopper to create a separate seeded synthetic paired batch on 12 road
corridors: 360 trips, 108 distinct observed geometries. Declared maneuvers stay
offline; this is simulator evidence, not real drivers or perfect detector accuracy.
All-region data is fetched at explicit resolution/time and clipped locally on pan.
Bound legacy work to 100,000 trips, 2,000 signature groups and 100,000 group cells.
Deduplicate footprint driver IDs in Python to avoid sorting toasted SQL arrays;
materialize per-cell time predicates once before counting. Keep the five-second
statement timeout and explicit failures. No cache service or new dependency.
