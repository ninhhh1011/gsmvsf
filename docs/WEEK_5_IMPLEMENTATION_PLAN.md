# Week 5 — Realtime API + Evaluation: audit and implementation plan

> Execution authorized by the user on 2026-09-21. Use the execution and review
> workflow task by task. Earlier audit findings below describe the frozen baseline.
> Every phase follows Task -> Test -> Diff Review -> Exit Gate.

**Date:** 2026-09-21. **Audited HEAD:** `0983164130fc9f0d399da12e1f1f63058e28c3ef`.
**Goal:** Complete the documented Week 5 API, historical replay evaluation, and
latency evidence milestone by reusing the existing recommendation workflow.
**Architecture proposed:** Keep the FastAPI modular monolith and synchronous
Week 2 -> Week 3 -> Week 4 workflow. Drive existing APIs from a finite historical
replay client. Preserve PostgreSQL snapshot authority and optional Redis KV.
**Stack:** Existing Python, FastAPI/Pydantic, httpx, asyncpg, psycopg2/PostGIS,
Redis, GraphHopper 11, pandas/numpy and pytest. No new dependency proposed.
**Status:** EXECUTABLE. W5-00 PASS: authoritative user decisions recorded below.

## 1. Repository state and audit provenance

- Root: `E:\build6week`; branch: `week4-ranking-recommendation`.
- HEAD and `week4-ranking-recommendation-complete` both resolve to the commit above.
- The bootstrap audit was reused. A short status/HEAD check confirmed no change.
- Working tree was clean before this task. This document is the only intended
  source-tree change; no application, test, configuration or Dataset source changed.
- All requested foundation, architecture, decision, routing, Week 1–4 and migration
  documents were read during bootstrap. This audit traced their actual implementations.
- Evidence directory: `runtime/week5/preimplementation-audit/` (untracked audit
  artifacts; the existing ignore rules do not yet cover runtime/week5).
- Docker Desktop was initially unavailable. Starting the existing Desktop runtime
  and then `docker compose start` restored the existing containers, without rebuild,
  recreation, source import, engine change or volume replacement.
- Real smoke checks append candidate-search evidence and populate the existing
  snapshot cache. They do not ingest operational updates in `--smoke-only` mode.
  Tests use their existing isolated PostgreSQL schemas and Redis prefixes.
- Dataset integrity was checked across all 69 on-disk files, including the six
  preexisting ignored bytecode files. Commands disable bytecode generation.

Authoritative scope: [PROJECT_SCOPE](PROJECT_SCOPE.md),
[ACCEPTANCE_CRITERIA](ACCEPTANCE_CRITERIA.md), [ADR-013](DECISIONS.md),
and [Week 4 handoff](WEEK_4.md#28-known-limitations-and-week-5-handoff).
Earlier engine plans and historical latency measurements do not override these.

## 2. Official Week 5 requirement and boundary

**Title:** Realtime API + Evaluation.

`PROJECT_SCOPE.md` requires building the API, testing performance and evaluating
recommendations. `ACCEPTANCE_CRITERIA.md` requires:

1. Realtime recommendation API responds within latency targets.
2. Historical replay evaluation pipeline is functional.
3. `POST /api/v1/recommend` is operational.

The checked-in six-week acceptance workbook agrees: `Nghiem thu 6 tuan!B11:C11`
specifies recommendation API, performance tests and historical/replay evaluation.
Its A14 explicitly avoids adding KPI thresholds. No numeric latency target,
percentile, concurrency, test duration, quality cutoff or acceptance-rate target
is established by these documents. None is invented here.

The general project output is Best Station plus Top-N alternatives, considering
travel, detour, traffic, queue and capacity. Runtime inputs are GPS/location,
vehicle/trip context, SOC/range/intent, catalogs, road routes and operational
snapshots. Labels and ranking references remain offline evaluation inputs only.

Week 4 already delivers the endpoint, ranking, persistence of snapshots/searches,
baseline evaluation and initial measurements. Week 5 must demonstrate and close
the remaining integration/evaluation contract, not reimplement those components.
Acceptance and ADR-013 mention "Week 5 continuous recommendation" without defining
triggers, cadence, lifecycle or transport. That is an unresolved scope question,
not authorization to add an event broker or autonomous worker.

Week 6 explicitly owns productionization: latency optimization, production
caching/monitoring/logging, deployment and operating documentation. Existing
Week 4 cache/logging remain in use. Week 5 measurement does not certify scale.
`EXTERNAL_GPS_DATA.md` suggests finite GPS/event simulation for Week 5 and
multi-driver external-data load testing for Week 6; external GPS lacks energy,
operational and recommendation ground truth.

## 3. Actual architecture

Production code is a FastAPI modular monolith. `main.create_app()` mounts six
API routers and exception handlers. `core/lifespan.lifespan()` owns one 60-second
httpx client, an asyncpg pool (min 0/max 10), and a Redis client. It constructs
`SnapshotRepository`, `SnapshotCache`, `SnapshotResolver`, `IngestionService`
and `RecommendationWorkflow`. Redis retry is explicitly `Retry(NoBackoff(), 0)`.

`GraphHopperRoutingAdapter` and `GraphHopperMapMatchingAdapter` implement separate
domain protocols. `services/graphhopper.py` maps EV_CAR to car and EV_MOTORBIKE to
motorcycle and rejects missing/conflicting metadata. Routing has a 10-second
per-call default even with the shared client. Matching uses the injected client's
timeout; its adapter-specific timeout is not independently applied in that case.
Neither adapter retries transport calls or switches engines.

GraphHopper uses the immutable patched PBF. Motorcycle weighting shares
`car_access`; independent motorcycle access is not implemented. Matching projects
onto returned geometry, then `SegmentResolver.resolve_matched()` queries PostGIS.
Ambiguity withholds directed segment/direction. Quality is geometric proximity,
not probability. The synchronous segment queries and sequential candidate route
calls remain material latency constraints, not proposed replacements.

Static vehicle/station catalogs load runtime CSVs. Legacy Week 3 endpoints use
`StationCatalog`'s CSV operational lookup. The Week 4 workflow injects
`SnapshotCatalogView` backed by pinned PostgreSQL state. These are distinct paths;
legacy `/candidate-search` does not acquire Week 4 persisted search evidence.

## 4. End-to-end data flow: actual transitions

Paths below are relative to `backend/app/`.

| Transition | Input -> output | Actual function/service | Endpoint | State and dependencies | Errors/short circuits |
|---|---|---|---|---|---|
| GPS -> driver trace | `LocationIngestionRequest` -> realtime `GPSObservation`, `DriverTraceState`, `LocationResponse` | `api/v1/realtime.ingest_location`, `DriverTraceState.add_observation/get_context`, `HybridTrigger.should_trigger` | POST `/api/v1/drivers/{driver_id}/location` | Process-local `DriverStateStore`; no Redis/DB for buffering | 400 future/invalid observation; Pydantic 422; older timestamp returns 200 `STALE_OBSERVATION` without append; warm-up/suppression/no-trigger return without matching |
| Trace -> matched state | realtime observations -> matching `MapMatchRequest` -> `MapMatchResponse` -> `MatchedState` | `realtime._call_map_match`, `MapMatchingService.match_trajectory`, adapter `.match`, `SegmentResolver.resolve_matched` | Same location POST; independent batch POST `/api/v1/map-match` | GraphHopper HTTP and PostGIS identity query when triggered | No-match explicit; location endpoint returns 200 `ENGINE_UNAVAILABLE` on engine/DB errors; batch uses 503/504. No raw point fabricated as matched |
| Driver state -> demand input | `EvaluateDemandApiRequest` plus optional stored state -> `DemandContext` | `api/v1/demand.evaluate_driver_demand_with_realtime_state` | POST `/api/v1/drivers/{driver_id}/demand/evaluate` | In-memory matched state, otherwise latest raw observation; canonical vehicle catalog | No state-age/vehicle/trip binding check here; no service routing; explicit-zero bug described below |
| Telemetry/intent -> energy request | `DemandContext` plus optional `RequestedServiceType` -> `EnergyServiceRequest` | `DemandService.evaluate_auto_demand/process_driver_request`; `AutoDemandDetector`; `DriverRequestProcessor`; `VehicleCapabilityResolver` | POST `/demand/evaluate`, `/demand/request`; also invoked by `/recommend` and `/candidate-search/evaluate` | Canonical catalog; pure policy calculation, no operational DB/cache | Unsupported intent creates `request_valid=false`; insufficient telemetry produces anomaly reason; outer APIs differ in error mapping |
| Energy -> candidate result | `CandidateSearchRequest` -> `CandidateSearchResult` with `EvaluatedCandidate` | `CandidateSearchService.search_candidates`; `expand_candidate_pairs`; `MultiLegRouteCalculator`; `evaluate_candidate_eligibility` | POST `/candidate-search`; telemetry variant `/candidate-search/evaluate` | All static stations, vehicle capabilities, injected operational catalog, real GraphHopper; request-local route reuse | INVALID_REQUEST/NO_SERVICE_NEEDED/ERROR result short circuits; routing failures propagate; actual no-route becomes eligibility evidence |
| Energy -> persisted candidate evidence | Same request -> `CandidateSearchEvidence` | `RecommendationWorkflow.search`, `SnapshotCatalogView`, `SnapshotRepository.save_search` | POST `/ranking/candidates`; internal step of `/recommend` | DB heads pin station/queue; Redis validated payload or DB; existing Week 3 search; DB evidence write | 422 invalid energy/coordinates/max_candidates/anomaly; missing station or DB 503; no-demand skips operational lookup/routing but still persists evidence |
| Evidence -> ranking context | Evidence plus as-of time -> `list[CandidateRankingFeatures]` or conflict | `RankingService.recommend`, `SnapshotResolver.resolve`, `ranking/context.build_features` | POST `/ranking`; internal step of `/recommend` | Eligible station/queue keys and optional origin traffic; DB authoritative versions; catalog digest | Cannot rank before search time; malformed evidence 422; invalidated set 409; missing station 503 |
| Features -> recommendation | Features -> `RankedCandidate[]`, `RecommendationResult` | `rank_features`, `RankingService.recommend` | POST `/ranking` | Pure deterministic cost ordering after context resolution; no GraphHopper call | Zero -> explicit empty result; Top-N only after full ranking; no silent filtering of invalidated candidates |
| Telemetry -> recommendation | `RecommendRequest` containing `RecommendationTelemetry` -> `RecommendationResult` | `api/v1/ranking.recommend` -> demand -> `RecommendationWorkflow.recommend` -> search/ranking | POST `/recommend` | Supplied position/segment/SOC/intent; all Week 4 dependencies above | Strict validation; one whole-search retry only on typed candidate conflict; no automatic driver-store lookup or GPS ingestion |

All unqualified endpoint paths above use `/api/v1`.

There is **no single working Week 1 -> 2 -> 3 -> 4 endpoint**. There is a working
Week 2 -> 3 -> 4 workflow. Clients can already compose location/demand/candidate/
ranking calls, or supply a location in `/recommend`. No additional business
orchestration service is needed merely to connect an HTTP replay client.

## 5. Control flow and bounded retries

| Condition | Actual current behavior |
|---|---|
| No energy service needed | Valid AUTO request enters Week 3 NO_SERVICE_NEEDED short circuit, no routes/snapshot reads. Week 4 saves empty search evidence, returns 200, `has_recommendation=false`, empty ranking and null selection. Result reason is `NO_ELIGIBLE_CANDIDATES`; `energy_context.need_service=false` distinguishes no demand. PostgreSQL is still needed for persistence. |
| Invalid explicit service | `/demand/request` returns 200 with `request_valid=false` and UNSUPPORTED_SERVICE. Direct Week 3 returns INVALID_REQUEST. Week 4 rejects it with 422 INVALID_ENERGY_REQUEST before searching. No silent conversion to charging. |
| Zero eligible | Successful search may contain rejected alternatives; ranking returns false/null/empty, eligible_count=0. This is not a dependency-failure fallback. |
| One eligible | It is best and the sole ranked alternative; station and service retained. |
| Multiple eligible | Only eligible composite identities rank; completion, service start, detour, age, capacity, ID/service define deterministic order. Top-N limits output, not eligibility/ranking inputs. |
| State changes before ranking | Resolver obtains latest versions <= ranking request time. Queue/traffic/service-time changes update ranking features. Newly OFFLINE, zero capacity, exhausted swap inventory, queue >90 min or changed catalog digest invalidate the eligible set. Future snapshots beyond the as-of time do not enter it. |
| CANDIDATE_STATE_CHANGED | Whole request fails 409 with search ID, changed station/service identities, old/new state and RERUN_CANDIDATE_SEARCH. No survivor-only result and no eligibility rerun inside ranking. |
| Workflow retry | `RecommendationWorkflow.recommend` is `for attempt in range(2)`. First ranking conflict runs a new search; second conflict raises. Each attempt saves distinct evidence and uses the same request as-of time. It is not a clock-advancing continuous refresh. |
| Redis down/corrupt/missing | Mandatory DB head selection still runs. Miss/error reads immutable DB payload; cache population is best effort. No route/result-cache substitute. Cache health does not determine freshness. |
| PostgreSQL down | Repository connection/query failures become 503 SNAPSHOT_DATABASE_UNAVAILABLE even with warm Redis. Missing schema is also a repository failure. Standalone historical ranking needs DB search lookup. |
| GraphHopper down | Routes/candidate/recommend fail 503 or 504 for timeout when routing is required. Standalone ranking uses stored routes and need not contact GraphHopper. Valid no-demand needs no route. Triggered realtime matching exposes ENGINE_UNAVAILABLE rather than successful raw matching. |
| Traffic missing | Base route duration retained, BASE_DURATION_MISSING and missing provenance/degraded reason. No invented global delay. |
| Traffic stale | Observed factor remains in use, STALE and age visible; 1,800 seconds inclusive is fresh by default. |
| Queue missing | Observed wait is null; ranking uses labeled 5,400-second PROJECT_POLICY_MISSING_QUEUE default. Week 3's missing-queue operational representation has null wait, not an asserted observed zero. |
| Queue stale | Observed wait remains in use with age/STALE; default threshold 600 seconds inclusive. It can still trigger the existing eligibility queue limit if changed. |
| GPS stale | Timestamp strictly older than stored last observation returns 200 STALE_OBSERVATION and does not append. Equal timestamps are accepted; observation ID is not an ingestion idempotency key. This is ordering, not maximum wall-clock age. |

Retry proof: the workflow's two-attempt loop is the only automatic candidate
retry. `RankingService.recommend` has no retry. GraphHopper adapters perform one
HTTP attempt per route/match. Redis lifespan client has zero retries. Repository
conflict checks do not contain a retry loop. Candidate iteration and per-profile
health iteration are bounded work, not retries. New caller requests are separate
operations. There is no unbounded recommendation retry loop. There is also no
single end-to-end deadline: per-route and DB timeouts do not equal an API SLA.

Refresh distinction: `/ranking` with a later time reuses old position, route
evidence and eligible set. It cannot promote previously ineligible stations.
A repeated `/recommend` with new telemetry/time reruns Week 2/3/4 and can include
newly eligible alternatives. Invalidation guards are read-time checks, not a
persistent invalid-status marker or background sweep.

## 6. What realtime currently means

| Category | Present? | Exact interpretation |
|---|---|---|
| A. Request-time computation | Yes | Location-triggered matching and synchronous demand/search/ranking/recommendation |
| B. Timestamped snapshot lookup | Yes | Latest PostgreSQL versions <= explicit request time; freshness based on that time |
| C. Polling | Client capability only | GET driver state can be polled; debug UI `setInterval(processStep,100)` posts replay samples. Docker periodically checks health. No server recommendation poller. |
| D. Background processing | No recommendation worker | Lifespan manages resources. CLI loaders/evaluators run when invoked. Neither reranks active drivers automatically. |
| E. Streaming | No | Finite CSV/gzip replay exists; no continuous broker/consumer, Kafka or Redis Streams |
| F. Push/WebSocket | No | No WebSocket/SSE/push recommendation endpoint |

The trigger is evaluated on arrival of an HTTP observation. Ten seconds elapsing
without another observation does not schedule a match. Snapshot age does not
turn a historical observation into live traffic.

## 7. Existing orchestration and discovered integration defects

Reuse `services/ranking/orchestration.py::RecommendationWorkflow` and its existing
API. `api/v1/candidate.evaluate_and_search` is an older partial Week 1/2/3 bridge,
not a replacement full recommendation workflow.

Read-only in-process HTTP probes reproduced:

1. **Missing driver-state accessors:** with driver state present and coordinates
   omitted, `candidate.evaluate_and_search` calls `get_latest_observation()` and
   `get_latest_match()`. `DriverTraceState` implements neither; it exposes
   `observations` and `last_matched_state`. The subsequent `resolved_segment_id`
   attribute also differs from actual `MatchedState.road_segment_id`. HTTP 500
   was observed before demand/routing. Existing API test supplies coordinates
   and does not exercise this branch.
2. **Explicit coordinate overwrite:** `demand.evaluate_driver_demand_with_realtime_state`
   uses `lat = lat or ...` and `lon = lon or ...`. A supplied `(0,0)` became
   cached `(21.04,105.86)` with HTTP 200. Missing checks must distinguish `None`
   from zero. Existing integration test covers missing, nonzero Hanoi coordinates.

Probe artifact: `targeted-probes.json`; the third probe confirmed stale GPS
returns STALE_OBSERVATION without incrementing observation count. These are
additional findings, not failures counted in the existing 302-test suite.

Other inspected gaps, without claiming new reproduced failures: driver state
has no persistent trip/vehicle binding, no maximum accepted location age and no
request-as-of historical lookup. Demand bridge can use an older matched state
ahead of newer raw GPS and can mix explicit coordinates with a stored segment.
`_validate_observation` strips timezone rather than converting to UTC for its
future comparison; mixing naive/aware stored observations also lacks an explicit
contract. `EnergyServiceRequest` is described as immutable in historical prose
but its actual Pydantic config is extra-forbid, not frozen. Preserve its current
contract; do not silently turn this audit into broad Week 1/2 rewrites.

## 8. Recommendation-state audit

| Concept | What exists | What is missing |
|---|---|---|
| recommendation_id | No such field | Independent durable recommendation identity |
| driver_id / trip_id | Optional in `energy_context: EnergyServiceRequest`; also inside persisted search evidence | Dedicated indexed recommendation/driver/trip record |
| candidate_search_id | UUID string generated by `CandidateSearchEvidence`; persisted and returned | Nothing needed for existing search/ranking contract |
| recommendation timestamp | `RecommendationResult.request_time` is as-of time | Result generation timestamp; search `created_at` is a different concept |
| selected station/service | `recommended_station_id`, `recommended_service_type` in response | Persisted selection history |
| ranking policy | Full `RankingPolicy` in result, named TOTAL_SERVICE_COMPLETION_V1 | Durable policy attached to a stored final recommendation |
| versions/timestamps | Search `snapshot_ids`, catalog digest; each ranked feature carries station/queue/traffic `ResolvedSnapshot` with ID/source/time/age | Final response history; excluded Top-N alternatives' rank-time provenance is not returned |
| status | `has_recommendation`, `reason`, separate candidate search status; error response on conflict | Lifecycle enum such as active/superseded/accepted/expired; acceptance feedback |
| degraded/freshness | `degraded`, `degraded_reasons`, per-feature freshness/age | Persistent lifecycle freshness tracking or autonomous expiry |

Only snapshots and candidate searches are stored in the Week 4 PostgreSQL schema.
No recommendation repository, result table, latest recommendation Redis key or
GET recommendation/history endpoint exists. Evaluation JSONL is an offline
artifact, not product lifecycle state. Search evidence preserves search-time
routes/eligibility; it is not the final ranked response at a later as-of time.

Durable recommendation history could be useful, but the official milestone does
not explicitly require it. Do not add fields/tables/endpoints speculatively.

## 9. PostgreSQL and Redis contracts

Schema source: `services/snapshots/schema.sql`; repository:
`services/snapshots/repository.py::SnapshotRepository`. Live information_schema,
pg_indexes and pg_constraint queries confirmed the following.

| Table | Columns and constraints | Indexes and responsibility |
|---|---|---|
| state_snapshots | `snapshot_id uuid PK`; `kind text NOT NULL CHECK IN traffic/station/queue`; `entity_id text NOT NULL`; `timestamp timestamptz NOT NULL`; `source text NOT NULL`; `schema_version integer NOT NULL CHECK=1`; `payload jsonb NOT NULL`; `created_at timestamptz NOT NULL DEFAULT now()`; UNIQUE(kind,entity_id,timestamp) | PK index and composite unique B-tree; backwards lookup supports latest-at-or-before. No extra freshness index. |
| candidate_searches | `candidate_search_id text PK`; `payload jsonb NOT NULL`; `created_at timestamptz NOT NULL DEFAULT now()` | PK index only. No driver/trip/status index; no recommendation foreign key. |
| road_segments | `segment_id varchar(50) PK`; `from_node_id/to_node_id varchar(20) NOT NULL`; `travel_direction varchar(10) NOT NULL`; nullable `base_segment_id varchar(50)`; `osm_way_id bigint NOT NULL`; nullable `length_m double precision`, `wkt_geometry text`, `geom geometry(LineString,4326)` | PK; GiST geom; B-tree osm_way_id. Live DB also retains from_node/to_node B-tree indexes not created by the current road loader. Preserve these inherited indexes. |

No SQL trigger prohibits UPDATE/DELETE on snapshots; append-only semantics are
enforced by the ingestion/repository contract, not an asserted database privilege
boundary. There are no cross-table foreign keys for JSON evidence or polymorphic
entities. `IngestionService` validates entities and capacity against catalogs/roads.

Repository methods: `setup`, `ingest/ingest_many`, `heads`, `payloads`,
`existing_segments`, `save_search`, `get_search`, and bounded `connection`.
Ingestion performs transactional `ON CONFLICT DO NOTHING` plus stored-content
verification. Same content/source retry is idempotent; conflicting logical time
returns 409 SNAPSHOT_CONFLICT and rolls back the batch. UUID5 binds ID to validated
content; signed zero is normalized for JSONB. `heads` pins all requested IDs in
one SQL statement/MVCC view; immutable payload fetch follows. Missing search is
404. Search retry with different payload under one ID returns 409.

Live DB contained 701,407 road segments and 883,599 traffic / 3,572 station /
3,594 queue snapshots. These include prior Week 4 demonstrations; they are not
the canonical source-import counts (883,597 / 3,270 / 3,270). A replay must isolate
or fingerprint its consumed source history rather than assume this DB is pristine.

Redis contract (`services/snapshots/resolver.py`):

- Key: `week4:snapshot:{kind}:{entity_id}:latest`; configurable prefix in class.
- Value: JSON `{stamp, payload}`; fixed-width UTC stamp and validated snapshot.
- Default TTL 60 seconds. TTL is retention, not freshness or an invalidation SLA.
- Resolve DB heads first; MGET; accept cache only when content-derived ID equals
  pinned ID and entity key agrees. Miss/corruption/outage -> DB payload.
- Populate from the DB's actual global latest version, even after a historical
  read. Lua compare-and-set prevents an older stamp overwriting a newer stamp.
- DB commit precedes best-effort cache population. No cross-store transaction,
  Redis authority, recommendation cache, Pub/Sub or Streams.
- Defaults: cache connect/read timeout 0.2s; DB timeout 5s; no Redis retry in lifespan.
- PostgreSQL remains source of truth, including on cache hits and cache outages.

## 10. Existing API inventory

All paths have `/api/v1` prefix except aliases explicitly shown. Listed types are
actual Python models; dict responses are identified as such. Pydantic validation
can return 422 throughout. There is no active `/drivers/{id}/history` route despite
the realtime module's stale header comment, and no bare `/demand` route.

| Method/path | Request | Response | Important status/behavior |
|---|---|---|---|
| POST /map-match | `MapMatchRequest` | `MapMatchResponse` | 200; 400 metadata/too few points; 422 no-match; 503 engine/resolver; 504 timeout |
| POST /drivers/{driver_id}/location | `LocationIngestionRequest` | `LocationResponse` | 200 includes WARMING_UP/GPS_ACCEPTED/MATCHED/NO_MATCH/STALE_OBSERVATION/ENGINE_UNAVAILABLE; 400 invalid/future/metadata; 422 shape |
| GET /drivers/{driver_id}/location | Path driver ID | `LocationResponse` | 200 or 404 absent driver; no matching triggered |
| DELETE /drivers/{driver_id}/location | Path driver ID | dict status/removed | 200; resets only process-local driver state |
| GET /drivers | None | dict driver IDs/count | 200; process-local inventory |
| GET /debug/trajectories/{trajectory_id} | Path trajectory ID | list of observation dicts | 200/404; Dataset runtime GPS source |
| POST /demand/evaluate | `EvaluateDemandApiRequest` | `EnergyServiceRequest` | 200 decision; unknown vehicle 404/model 422 |
| POST /demand/request | `DriverIntentApiRequest` | `EnergyServiceRequest` | 200 may be invalid intent; unknown vehicle 404/model 422 |
| POST /drivers/{driver_id}/demand/evaluate | `EvaluateDemandApiRequest` | `EnergyServiceRequest` | 200 decision; state is optional; this bridge lacks the sibling endpoints' explicit unknown-vehicle handler |
| GET /vehicles/{vehicle_id}/capability | Path ID | `VehicleCapability` | 200/404/422 |
| GET /vehicles/models/{model_name}/capability | Path model | `VehicleCapability` | 200/404 |
| POST /route | `RouteRequest` | `RouteResult` | 200; 404 real no-route; 422 unsupported request; 503 engine; 504 timeout |
| POST /candidate-search | `CandidateSearchRequest`, query eligible_only | `CandidateSearchResult` | 200 may contain INVALID_REQUEST/ERROR/NO_SERVICE_NEEDED; routing 422/503/504 |
| POST /candidate-search/evaluate | `EvaluateAndSearchApiRequest` | `CandidateSearchResult` | 200; routing 422/503/504; proven 500 on populated driver-state branch without coordinates |
| POST /ranking/candidates | `CandidateSearchRequest` | `CandidateSearchEvidence` | 200; 422 invalid/partial destination/max_candidates; 503 snapshot/DB/engine; 504 routing |
| POST /ranking | `RankRequest` | `RecommendationResult` | 200; 404 search absent; 409 changed set; 422 invalid evidence/time; 503 DB/snapshot |
| POST /recommend | `RecommendRequest` / `RecommendationTelemetry` | `RecommendationResult` | 200 including no recommendation; 422 validation/energy/ValueError; 409 second conflict; 503/504 dependencies |
| POST /internal/snapshots/traffic | `TrafficSnapshot`, X-Ingestion-Token | dict snapshot_id/created/timestamp/source | 201 new/200 exact retry; 401 missing token/403 wrong token; 409 conflict; 422 validation/entity; 503 disabled/DB |
| POST /internal/snapshots/station | `StationStateSnapshot`, token | Same dict | Same statuses |
| POST /internal/snapshots/queue | `QueueSnapshot`, token | Same dict | Same statuses |
| GET /health; root /health alias | None | dict status | 200 liveness only |
| GET /ready, /readiness; root aliases | None | dependency dict | 200/503; checks actual routes for both profiles and populated roads, not Week 4 snapshot schema/history or Redis |

`StateError` handler returns its structured detail directly; routing handler wraps
string detail in `{"detail": ...}`; FastAPI validation has its own detail array.
Do not claim a unified error envelope already exists. The minimum proposed scope
requires no new public endpoint. A history/lifecycle API needs a separate approved
contract; a new orchestration layer would duplicate existing business logic.

## 11. Shared types and reuse rules

| Module | Reuse |
|---|---|
| `services/realtime/state.py` | `GPSObservation`, `DriverTraceState`, `MatchedState`, `DriverStateStore` |
| `services/map_matching/models.py` | Matching-specific `GPSObservation`, `MapMatchRequest`, `MatchedObservation`, `MapMatchResponse`, `ResolutionStatus`; do not confuse the two GPS classes |
| `services/demand/models.py` | `DemandContext`, `EnergyServiceRequest`, `NeedServiceDecision`, `VehicleCapability`, `ServiceType`, `RequestedServiceType`, `RequestSource`, `ReasonCode`, `VehicleCategory` |
| `services/candidate/models.py` | `CandidateSearchRequest/Result`, `EvaluatedCandidate`, `StationServiceCandidate`, `StationOperationalSnapshot`, `CandidateRouteMetrics`, `CandidateEligibilityReason` |
| `services/routing/models.py` and `engine.py` | `Position`, `VehicleRoutingProfile`, `RouteRequest/Result/Leg/Status`, `RoutingEngine`, typed dependency exceptions |
| `services/snapshots/models.py` | `SnapshotBase`, three snapshot variants, `ResolvedSnapshot`, `StateError`, `aware_utc`, `FrozenModel` |
| `services/ranking/models.py` | `CandidateSearchEvidence`, `CandidateRankingFeatures`, `RankedCandidate`, `RecommendationResult`, `RankingPolicy`, `CandidateStateChanged` |
| `api/v1/ranking.py` | `RankRequest`, `RecommendationTelemetry`, `RecommendRequest` |

Use these types as boundaries. Do not clone request, candidate, eligibility or
ranking models into a Week 5 service. Serialized evidence should retain units,
as-of timestamps, identity and provenance, including null/ambiguous values.

## 12. Observability and evaluation already present

`core/logging.configure_logging` configures standard logging and structlog JSON.
Ranking logs recommendation/search ID, total/ranking milliseconds, eligible and
returned counts, policy, selected identity and degradation. Workflow logs elapsed
time and attempt count plus candidate-search retries. Snapshot resolver logs
lookup time, hits/misses, DB payload fallbacks, stale count and ages, with
process-local Counter metrics. Ingestion logs cache-write failure. Matching
latency and match counters are in driver state. No durable aggregate metric,
global request-correlation middleware, distributed trace or metrics endpoint exists.
The workflow timer starts after demand evaluation and excludes HTTP transport;
the ranking timer and pure-ranking timer are separate scopes.

| Script | Current purpose and reusable parts | Limits |
|---|---|---|
| `evaluate_week4.py` | `reconstruct_contexts`: source-only 1,200 AUTO contexts; causal raw GPS; `predict`: actual demand/workflow; `evaluate_predictions`, `baseline_orders`, `compare_order`: offline comparisons | No Week 1 matching or HTTP end-to-end timing; loops reconstructed trip contexts, not one global event stream; preloaded as-of snapshots; labels open after prediction persistence; no safe resume |
| `verify_week4.py` | `smoke`, `search_rank`, `dynamic_demo`, `failures`, `performance`, `summary`; real APIs and source fixtures | Full mode ingests demonstration snapshots; smoke-only persists searches; 10-sample historical measurements are not capacity proof |
| `replay_realtime.py` | Finite GPS trajectory HTTP replay with vehicle metadata; explicit failure | GPS/matching only, not SOC/demand/recommendation. Waits capped at 100ms, so speed flag is not faithful elapsed-time replay. Stationary counter branch follows broader GPS_ACCEPTED branch; use actual status/reason when extending metrics. |
| `evaluate_graphhopper_matching.py`, `benchmark_realtime_map_matching.py` | Matching quality/trigger-policy evidence | Different population/scope from recommendation quality; retain separate metrics |
| `evaluate_demand_ml.py`, `evaluate_candidate_search.py` | Offline demand/eligibility policy comparisons | Do not substitute frozen/mock route evidence for live GraphHopper measurements |
| `verify_graphhopper.py`, `smoke_test_week3.py`, `benchmark_week3.py` | Real profiles/via legs/candidate routes and call counts | Service/router smoke differs from deployed recommendation HTTP benchmark |
| `load_week4_snapshots.py`, `validate_frozen_dataset.py` | Existing bounded source ingestion and protected validator | Never execute Dataset generators or unwrapped validator |

Week 4 checked-in quality evidence: 848 recommendation label joins and 553
positive ranking groups from 1,200 source predictions; completion composite
top-1 478/553 and common-pool pairwise 10,246/10,885. These are historical baseline
results, not newly rerun full quality evaluation in this audit.

`dataset_v1/realtime/events.csv.gz` has 109,193 rows: 8,231 GPS_UPDATE, 5,722
SOC_UPDATE, 3,270 STATION_STATUS_UPDATE, 3,270 QUEUE_UPDATE, 88,700 TRAFFIC_UPDATE.
Columns: event_id, timestamp, event_type, entity_id, payload_json. Payloads are
abbreviated: traffic lacks free-flow speed/delay factor; queue lacks service times;
GPS/SOC refer to trip IDs. A future event-ingestion replay must enrich from causal
runtime source rows, never labels or fabricated defaults. It cannot directly POST
these abbreviated payloads to the typed snapshot APIs. Full event ingestion is
not necessary merely to evaluate the existing as-of snapshot API.

## 13. Test inventory and coverage gaps

Each file below is under `backend/tests/`. All existing 39 `test_*.py` files are
listed; parametrized test cases account for the 302 executed tests.

| Test file(s) | Behavior protected |
|---|---|
| test_realtime.py | Observation/state buffers, warm-up, gaps, stationary movement, context bounds, reset, store capacity, 10s/50m trigger policy |
| test_map_matching.py | Batch observation/result models, resolution enums, GraphHopper service construction |
| test_matching_integration.py | Actual projected location/way passed to resolver; direction/ambiguity; realtime matched coordinates and explicit outage; duplicate-ID latest selection |
| test_graphhopper_adapter.py | Matching transport/rejection/input failures; no fabricated success |
| test_graphhopper_migration.py | No engine selector; GPX/category/geometry contracts; malformed output; loop ambiguity |
| test_graphhopper_lifecycle.py | Shared client identity and lifespan closure |
| test_config.py | Settings defaults/path validation |
| test_health.py; test_health_migration.py | Root/liveness and required readiness dependencies |
| test_demand_models.py | Enums, capability and normalized request invariants; ANY/unresolved; forbidden ranking fields |
| test_vehicle_capability.py | All 19 models; service support and unknown identity errors |
| test_auto_detector.py | SOC/range/reserve decisions, low-SOC configuration, invalid/missing input |
| test_driver_requester.py | Explicit request/ANY validity across vehicle classes |
| test_demand_service.py | AUTO/intent convergence and no arbitrary service preference |
| test_energy_feasibility.py | Safe/reserve-insufficient/destination-unreachable, same SOC different trips |
| test_scenarios_week2.py | 18 canonical/controlled demand scenarios |
| test_demand_api.py | Demand/capability HTTP and Week 1 raw-state bridge; misses explicit-zero and matched/raw provenance edge cases |
| test_candidate_models.py | Composite identities, immutable candidate metrics, no ranking fields |
| test_candidate_expansion.py | Charging/swap/unresolved ANY expansion |
| test_candidate_compatibility.py | Vehicle/interface/service compatibility |
| test_candidate_eligibility.py | Rejection precedence and eligible outcome |
| test_candidate_energy_feasibility.py | Network distance plus reserve, edge/anomaly cases |
| test_candidate_search_service.py | Invalid/no-demand short circuits, all alternatives, no destination |
| test_candidate_scenarios.py | Fourteen operational/energy/service candidate cases including zero/multiple |
| test_candidate_dataset_replay.py | Frozen-label eligibility replay sample; evaluation-only labels |
| test_station_catalog.py | 30 stations, BOTH services, legacy operational lookup |
| test_candidate_api.py | Candidate endpoints and adapter contract; does not cover absent-coordinate driver-state branch |
| test_routing_models.py | Coordinates/domain contracts free from legacy engine fields |
| test_multi_leg_routing.py | Via/direct/detour arithmetic, no-route, dependency errors, request-local reuse |
| test_mock_routing_adapter.py | Test-only adapter contract, distances and unreachable behavior |
| test_graphhopper_routing_adapter.py | Vehicle profile, real leg schema, invalid constraints, malformed payload, HTTP/transport failure classification |
| test_routing_migration.py | BOTH shares station routes, category conflicts, injected engine, GraphHopper factory, API 422/503/504 |
| test_week4_models.py | Snapshot identity, strict counts/times, freshness boundaries, provenance and recommendation serialization |
| test_week4_database.py | Real DB schema/idempotency, concurrent conflicts, batch rollback, indexed historical pinning, immutable searches, loader retry, outage, signed zero |
| test_week4_snapshots.py | Real Redis hit/miss/corruption/outage; mandatory DB head; concurrent pinning; historical cache cannot regress latest |
| test_week4_ranking.py | Zero/one/BOTH; eligible-only ordering; all invalidation cases; costs/ties/Top-N; missing/stale inputs; no routing or duplicate eligibility |
| test_week4_api.py | Bounded retry via test and real search, second conflict 409, token statuses, telemetry 422, actual resource lifecycle and no-demand result |
| test_week4_evaluation.py | Source schedule/causal GPS reconstruction, composite/common-pool denominators, empty outcomes and mismatch reporting |
| test_week4_verification.py | Timing summaries, source request/traffic probes, dependency failure classification |

Important named proofs: `test_orchestrator_retries_once_only_outside_ranking`,
`test_http_orchestrator_retries_real_search_after_concurrent_state_change[False/True]`,
`test_warm_healthy_cache_does_not_mask_database_failure`,
`test_resolution_pins_all_entities_before_concurrent_ingestion`,
`test_history_future_state_backfill_and_queue_limit_boundary`, and
`test_stale_traffic_and_queue_remain_observed_with_missing_last_detour`.

There is no existing full GPS/SOC -> deployed recommendation chronological replay
test, durable recommendation lifecycle test, or enforceable numeric latency gate.
`test_realtime.py` is principally state/policy unit coverage; the HTTP stale-order
behavior was additionally probed in this audit. Passing existing tests does not
cover the two newly reproduced integration branches.

## 14. Protected behavior

Week 5 must preserve:

1. GraphHopper-only route/match runtime, deterministic category mapping, real
   geometry, explicit failures, shared-client ownership and no engine selector.
2. Week 1 hybrid 10s/50m policy, 3-point warm-up, 30s/50-point context, 3 small
   movements stationary suppression and >60s gap reset; directed ambiguity stays null.
3. Week 2 AUTO/intent/ANY capability and energy-reserve semantics. No labels or
   station/ranking fields in its request. No silent service preference.
4. Week 3 eligibility authority, all-station evaluation before reduction, reason
   precedence, road-distance energy feasibility, request-local route reuse.
5. Composite `(station_id, service_type)` identity through every output/metric.
6. TOTAL_SERVICE_COMPLETION_V1 formula/ties; detour is not charged twice; origin
   traffic proxy is labeled; no learned model or weight changes.
7. Immutable snapshot/search repository semantics, aware UTC/as-of pinning,
   idempotency/conflicts, source provenance, stale/missing distinction.
8. PostgreSQL authority; Redis miss/outage fallback, bounded client retry, CAS
   latest handling, mandatory DB heads even on warm cache.
9. Entire-set CANDIDATE_STATE_CHANGED boundary; ranking never silently filters,
   retries or promotes; only workflow retries once and second conflict propagates.
10. Dataset V1.3.1, both PBFs and all labels unchanged; labels evaluation-only.
11. All existing Week 1–4 and migration freeze tags and their commit identities.
12. Existing API compatibility and explicit zero/no-demand/no-candidate outcomes.
    Correcting proven adapter defects requires focused tests, not policy rewrites.
13. Current runtime graphs/logs/evidence stay inside repository and outside Dataset.
14. No Kafka, Redis Streams, continuous streaming, external live traffic, new
    routing engine, new infrastructure technology or production fallback.

## 15. Executed baseline

All commands ran from the verified root. Environment for Python checks:
`DEBUG=false`, `LOG_LEVEL=INFO`, `PYTHONDONTWRITEBYTECODE=1`; Python invoked with -B.

| Check | PASS | FAIL | ERROR | SKIP | Evidence / scope |
|---|---:|---:|---:|---:|---|
| Full backend suite, final run | 302 | 0 | 0 | 0 | tests-live.xml/log; 12.24s |
| Canonical structural/semantic validator | 152 | 0 | 0 | 0 | validator.log; protected wrapper |
| Canonical scenario assertions | 22 | 0 | 0 | 0 | Same validator output; distinct count |
| Dataset on-disk SHA-256 equality | 69 | 0 | 0 | 0 | dataset-before.json and dataset-integrity.json; includes 63 canonical files |
| API health | 1 | 0 | 0 | 0 | GET /health 200 |
| API readiness | 1 | 0 | 0 | 0 | GET /readiness 200, GraphHopper/PostGIS true |
| PostgreSQL connectivity | 1 | 0 | 0 | 0 | Real loopback SELECT 1 |
| Redis connectivity | 1 | 0 | 0 | 0 | Real PING |
| GraphHopper /info | 1 | 0 | 0 | 0 | 11.0, car/motorcycle |
| GraphHopper smoke command | 1 | 0 | 0 | 0 | Four vehicle/service searches, missing destination, two via routes, route API; command-level count |
| Recommendation smoke scenarios | 4 | 0 | 0 | 0 | Deployed candidate-evidence/ranking/recommend calls; car/fixed/swap/BOTH |
| Deployed Python source equality | 55 | 0 | 0 | 0 | deployed-source.json; container matches checkout |

Final suite command:

```powershell
$env:DEBUG='false'
$env:LOG_LEVEL='INFO'
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest backend/tests -q -p no:cacheprovider --basetemp=runtime/week5/preimplementation-audit/pytest-live --junitxml=runtime/week5/preimplementation-audit/tests-live.xml
python -B scripts/validate_frozen_dataset.py
python -B scripts/verify_graphhopper.py
python -B scripts/verify_week4.py --smoke-only --output runtime/week5/preimplementation-audit/recommendation-live.json
```

Do not reexecute these into existing evidence paths without preserving this run.
The GraphHopper script uses its existing `runtime/migration/graphhopper-routing-smoke.json`
output. Audit-specific stdout is also retained in graphhopper-live.log.

Initial unavailable-runtime attempt is retained: 283 passed, 1 failed, 18 setup
errors, 0 skipped (`tests.xml/log`). Failure was real Redis connection timeout;
18 DB-dependent setups failed. Initial API/engine/connectivity probes also failed.
The configured host-side database default `db` was not resolvable outside Compose;
explicit loopback subsequently verified the real service. No committed settings
were changed. Those initial failures were resolved by starting existing services,
not by replacing them with mocks or changing assertions.

Live recommendation scenario outputs: car 19 eligible, fixed bike 0, explicit
swap 1, BOTH 13; all recommendation HTTP 200. Smoke timings include concurrent
audit activity and are **not** a Week 5 latency benchmark or SLA result. Newly
found bridge defects remain despite the passing existing baseline.

## 16. Gap analysis and recommended scope

| Classification | Work | Rationale |
|---|---|---|
| REQUIRED WEEK 5 | Resolve latency acceptance tuple and request-driven versus continuous-update meaning | Official criterion cannot be judged without a measurable contract |
| REQUIRED WEEK 5 | Reuse/document existing recommendation endpoint, complete tested GPS/telemetry client integration, repair the two proven legacy bridge defects | API integration is the milestone; no second workflow is needed |
| REQUIRED WEEK 5 | Reproducible causal historical replay through actual public APIs with persisted prediction artifacts and offline quality comparison | Extend Week 4's service-level/raw-GPS evaluator to documented integration scope |
| REQUIRED WEEK 5 | End-to-end latency and error measurements under agreed workload; freshness/outage/conflict/refresh evidence | Required performance and API behavior evidence |
| REQUIRED WEEK 5 | Tests, protected regressions, integrity, ADR for approved new approach and final documentation | Required safe milestone completion |
| OPTIONAL WEEK 5 | Durable recommendation_id/history/latest retrieval, lifecycle/acceptance status, refresh parent IDs | Useful product features, not explicit acceptance requirements; do not implement without a concrete use case/contract |
| OPTIONAL WEEK 5 | Full 109,193-event snapshot-ingestion simulation; external GPS robustness replay | Different from historical as-of evaluation; abbreviated events need source enrichment, external GPS has no recommendation labels |
| OPTIONAL WEEK 5 | Thin driver-scoped recommendation API or server-side state adapter | Existing explicit telemetry and client composition may suffice; stale-state rules must be approved first |
| WEEK 6 / PRODUCTIONIZATION | Capacity tuning, cross-request route caching, persistent/shared driver store, retention/cleanup, worker scaling, monitoring stack, deployment hardening | Explicit future milestone; preserve current working cache/logging |
| WEEK 6 / PRODUCTIONIZATION | Multi-driver external-GPS scale exercise, HA/auth/rate limiting/production rollout | Beyond finite Week 5 correctness/performance evidence |
| OUT OF SCOPE | Kafka, Redis Streams, external live traffic, alternate/fallback engines, Dataset regeneration, new ML ranking policy | No supporting requirement; contradicts protected decisions or needs separate authorization |

Three approaches evaluated:

1. **Recommended: request-driven integration + finite replay + measurement.** Reuse
   `/recommend` for full recomputation and `/ranking` for existing-pool reranking;
   store replay outputs as artifacts and reuse DB search evidence. Smallest change
   satisfying the explicit milestone if "continuous" means repeated requests.
2. **Add durable recommendation lifecycle.** Enables history/latest/refresh lineage
   but adds result schema, writes, IDs, retention and API decisions. Defer unless
   the user identifies these as required Week 5 behavior.
3. **Automatic reranking worker/push.** Requires trigger/cadence/delivery/backpressure
   and ownership rules absent from docs. Not selected or authorized.

The proposed required scope adds no recommendation table, Redis recommendation
key, streaming provider, new public endpoint, routing policy or duplicate engine.
Version tracking reuses search IDs and snapshot provenance. Persisted evaluation
responses provide reproducible history for the experiment without pretending to
be product lifecycle state. Adding a production result repository remains a
separate decision, not a hidden dependency of the minimal plan.

## 17. Authoritative contract resolution - W5-00 PASS

The user resolved all contract questions on 2026-09-21 and authorized autonomous
implementation, focused commits, and the Week 5 tag only after all gates pass.
These decisions supersede proposals/ambiguities in the historical audit above.

- Continuous recommendation means client/replay-driven request refresh, using the
  existing Week 2 -> Week 3 -> Week 4 workflow. No daemon, polling loop or push.
- There is no numeric SLA. Measure at least 3 warmups and 20 requests per
  concurrency 1/5/10 where practical. Report median/P90/P95/max, successes/errors,
  workload/cache/environment as INITIAL LOCAL WEEK 5 PERFORMANCE BASELINE.
- No durable recommendation lifecycle/history table. Existing search evidence,
  snapshots, response provenance and report artifacts suffice.
- Location precedence: complete explicit coordinates (None checks, zero valid),
  valid current matched Week 1 position, accepted raw GPS with RAW_GPS_FALLBACK,
  else explicit LOCATION_UNAVAILABLE. No new age threshold or store redesign.
- At replay time T every consumed source/matched/SOC/operational state must be
  <= T. Process chronological source events and populate isolated operational
  history/cache only as time advances; never preload future latest cache entries.
- Finite representative actual Dataset replay targets >=30 trajectories, covering
  car/fixed bike/swap bike, no service, charging/swap/ANY, state changes, stale GPS
  and failures. Additional controlled reliability probes are labeled separately.
- Preserve Week 3 eligibility, Week 4 ranking and exactly-one conflict retry.
- Predict/persist first; read evaluation labels only afterward. Report exact
  coverage, agreement populations, counters, errors and limitations.
- Week 6 owns optimization/SLA, production scaling, shared driver-state redesign,
  lifecycle persistence, retention, monitoring platforms and deployment hardening.

## 18. Executable phases and tasks

Each task follows Inspect -> focused failing check -> minimum change -> focused
and prior-week tests -> git diff review -> fixes/retest -> exit gate. Source labels
and Dataset bytes remain protected. No task may pass on mocks alone when its gate
requires real infrastructure. All expected paths below are relative to root.

### Phase 0 - Contract resolution and baseline

#### W5-00 - Contract resolution and baseline

- **TASK ID:** W5-00
- **OBJECTIVE:** Record the approved scope and preserve the verified baseline.
- **WHY:** Avoid invented SLA, lifecycle or streaming requirements.
- **INPUTS:** User decisions; audit evidence at 0983164.
- **OUTPUTS:** Executable plan, ADR-014, dedicated Week 5 branch.
- **DEPENDENCIES:** Completed audit.
- **FILES EXPECTED TO CHANGE:** docs/WEEK_5_IMPLEMENTATION_PLAN.md; docs/DECISIONS.md; .gitignore
- **IMPLEMENTATION APPROACH:** Record decisions verbatim in meaning; ignore generated runtime/week5 evidence; reuse 302-test/152-check/22-scenario baseline and verify infrastructure before live work.
- **TEST PLAN:** Check contract coverage and existing baseline fingerprints.
- **SELF-REVIEW CHECKLIST:** No fabricated threshold; no Dataset changes; previous freeze tags preserved.
- **EXIT GATE:** PASS when written contracts match user decisions and plan covers every final gate.
- **RISKS:** Historical audit text may look current; label it baseline.
- **FAILURE / FALLBACK BEHAVIOR:** Do not start dependent work if written scope contradicts user instructions.

### Phase 1 - Fix existing state integration defects

#### W5-01 - Fix existing state integration defects

- **TASK ID:** W5-01
- **OBJECTIVE:** Repair missing accessors and explicit-zero handling.
- **WHY:** Existing legacy state branch crashes and truthiness overwrites coordinates.
- **INPUTS:** DriverTraceState observations/last_matched_state; audit reproductions.
- **OUTPUTS:** Working candidate/demand bridges and regression tests.
- **DEPENDENCIES:** W5-00.
- **FILES EXPECTED TO CHANGE:** backend/app/api/v1/candidate.py; backend/app/api/v1/demand.py; backend/app/services/realtime/location.py; backend/tests/test_week5_location.py
- **IMPLEMENTATION APPROACH:** Reuse existing state fields through one small shared location resolver; never add fake compatibility accessors. Validate paired coordinates and use explicit None checks. Search all integration callers.
- **TEST PLAN:** Reproduce missing-accessor and zero bugs; test ordinary explicit/raw/matched/missing branches; run demand/candidate/realtime prior tests.
- **SELF-REVIEW CHECKLIST:** No policy rewrite; no fabricated coordinates; no unrelated store methods.
- **EXIT GATE:** Focused and prior tests pass; relevant git diff reviewed.
- **RISKS:** Matched and raw positions have different observation times.
- **FAILURE / FALLBACK BEHAVIOR:** Explicit location-unavailable or invalid-coordinate error; no accidental 500.

### Phase 2 - Bridge current location into /recommend

#### W5-02 - Bridge current location into /recommend

- **TASK ID:** W5-02
- **OBJECTIVE:** Reuse current state with visible location provenance.
- **WHY:** Existing /recommend only consumes supplied telemetry.
- **INPUTS:** RecommendRequest; shared resolver; Week 1 state; existing workflow.
- **OUTPUTS:** EXPLICIT/MATCHED/RAW_GPS_FALLBACK provenance; unavailable errors; lightweight stage measurements.
- **DEPENDENCIES:** W5-01.
- **FILES EXPECTED TO CHANGE:** backend/app/api/v1/ranking.py; backend/app/services/ranking/models.py; backend/app/services/ranking/orchestration.py; backend/app/config.py; backend/app/core/lifespan.py; backend/tests/test_week5_location.py
- **IMPLEMENTATION APPROACH:** Resolve location before demand; preserve no-service short circuit and invalid-energy rejection; return response provenance and finite timing/count metadata. Keep the existing two-attempt workflow. Add configurable snapshot cache prefix solely for isolated replay. Reject future state at as-of boundary without an age system.
- **TEST PLAN:** Test explicit zero/ordinary coordinates, matched priority, raw fallback, unavailable, future state, no-demand, invalid intent; run Weeks 1-4 protected tests.
- **SELF-REVIEW CHECKLIST:** No extra retry/orchestrator; no hidden matched claim; same ranking costs.
- **EXIT GATE:** Bridge tests and full protected API/regression checks pass; diff reviewed.
- **RISKS:** Current state is not a history store; request timestamps can precede it.
- **FAILURE / FALLBACK BEHAVIOR:** Future/missing current state cannot be invented; request fails explicitly when a location is needed.

#### W5-02A - Classify real degenerate GraphHopper matches

- **TASK ID:** W5-02A
- **OBJECTIVE:** Treat validated empty zero-distance/time GraphHopper paths as no match.
- **WHY:** Replay reproduced 34 real HTTP 200 zero-path responses incorrectly classified as malformed dependency failures; raw response evidence is retained.
- **INPUTS:** runtime/week5/graphhopper-degenerate-probe.json; production adapter; existing MapMatchingNoMatchError contract.
- **OUTPUTS:** Minimal adapter classification fix and focused regression cases.
- **DEPENDENCIES:** W5-02; diagnosis from initial finite replay b.
- **FILES EXPECTED TO CHANGE:** backend/app/services/map_matching/graphhopper_adapter.py; backend/tests/test_graphhopper_adapter.py (or existing matching adapter test file).
- **IMPLEMENTATION APPROACH:** Validate structure and metrics, map only valid empty zero-cost geometry to existing no-match exception. Preserve malformed/nonzero errors and existing Week 1 handling.
- **TEST PLAN:** Reproduce the real zero-path response as a failing adapter test, verify corrected classification and malformed-response protection, rerun prior matching/realtime tests, then fresh complete causal replay.
- **SELF-REVIEW CHECKLIST:** No raw GPS substituted as matched; no trigger/freshness/eligibility/ranking change; no engine fallback; no Dataset writes; preserve real outage errors.
- **EXIT GATE:** Focused/prior tests and diff review pass; actual replay records NO_MATCH with explicit fallback rather than false ENGINE_UNAVAILABLE.
- **RISKS:** Overbroad no-match classification could hide malformed responses; require validated zero metrics and empty geometry.
- **FAILURE / FALLBACK BEHAVIOR:** Unrecognized/malformed responses remain explicit dependency errors; accepted raw GPS retains RAW_GPS_FALLBACK provenance.

### Phase 3 - Finite causal replay

#### W5-03 - Finite causal replay

- **TASK ID:** W5-03
- **OBJECTIVE:** Replay >=30 representative trajectories through real HTTP APIs where practical.
- **WHY:** Need proven W1-to-recommend integration with chronological state.
- **INPUTS:** Actual Dataset GPS/SOC/trips/events and source snapshots; existing reconstruction helpers.
- **OUTPUTS:** Manifest, predictions JSONL, exact trajectory/event/request/provenance/call/error counters.
- **DEPENDENCIES:** W5-02.
- **FILES EXPECTED TO CHANGE:** scripts/replay_week5.py; backend/tests/test_week5_replay.py
- **IMPLEMENTATION APPROACH:** Select source-only representative trips; chronologically ingest causal observations and snapshots into an isolated PostgreSQL schema and unique Redis prefix with real API/GraphHopper. Source snapshot batches advance only <=T. Keep exact timestamp ordering; retain canonical identity mapping; no labels during inference, no safe-resume pretense. Artifacts outside Dataset.
- **TEST PLAN:** Tests for ordering/ties/future exclusion, source-only selection, cache isolation, output collisions and counters. Real pilot then >=30 trajectory run; inspect DB/cache/provenance timestamps.
- **SELF-REVIEW CHECKLIST:** No future preload, no raw-GPS success on engine outage, no frozen writes, no full-dataset claim.
- **EXIT GATE:** Finite run succeeds, temporal audit passes, coverage and errors accurately reported.
- **RISKS:** Full-resolution GPS may be expensive; source-event sampling must be disclosed.
- **FAILURE / FALLBACK BEHAVIOR:** Fail incomplete run on dependency/causality error; preserve partial evidence without PASS.

### Phase 4 - Recommendation evaluation

#### W5-04 - Recommendation evaluation

- **TASK ID:** W5-04
- **OBJECTIVE:** Evaluate completed predictions without label leakage.
- **WHY:** Quality needs correct composite identities and denominators.
- **INPUTS:** Completed replay artifacts; labels only after inference; Week 4 metric helpers.
- **OUTPUTS:** Compact evaluation JSON and mismatch analysis.
- **DEPENDENCIES:** W5-03 predictions completed.
- **FILES EXPECTED TO CHANGE:** scripts/evaluate_week5.py; backend/tests/test_week5_evaluation.py; docs/reports/week5-evaluation.json
- **IMPLEMENTATION APPROACH:** Reuse reference comparison functions. Report presence, station/service top1, service agreement, common-pool pairs, no-service/invalid/refresh behavior. Distinguish AUTO labeled population from explicit intent probes; no expected hardcoded winners.
- **TEST PLAN:** Tests for missing/empty references, composite identity, partial-run rejection, label ordering; execute real replay evaluation.
- **SELF-REVIEW CHECKLIST:** No discarded errors inflating metrics; no acceptance/actual wait invented.
- **EXIT GATE:** Metrics reconcile to saved predictions and reference population; diff reviewed.
- **RISKS:** Matching and objective differences produce valid mismatches.
- **FAILURE / FALLBACK BEHAVIOR:** Report discrepancies; do not tune ranking or alter labels.

### Phase 5 - Refresh invalidation and reliability

#### W5-05 - Refresh invalidation and reliability

- **TASK ID:** W5-05
- **OBJECTIVE:** Prove causal refresh and explicit failures using existing boundaries.
- **WHY:** No-service/empty/conflict/outage must remain distinguishable.
- **INPUTS:** Existing API/workflow, isolated real DB/cache, source fixtures.
- **OUTPUTS:** Reliability report with refresh/conflict/recovery/second-failure counts.
- **DEPENDENCIES:** W5-02; replay patterns available.
- **FILES EXPECTED TO CHANGE:** scripts/verify_week5.py; backend/tests/test_week5_workflow.py; docs/reports/week5-runtime.json
- **IMPLEMENTATION APPROACH:** Exercise GPS/state -> fresh requests; queue/traffic changes; OFFLINE/FULL whole-set conflict; exactly one retry and second 409. Use actual unavailable connections for GH/Redis/DB probes without disrupting production containers. Missing location/traffic/queue, stale GPS, invalid intent, zero candidates all explicit.
- **TEST PLAN:** Run live normal and outage probes plus existing Week 4 retry/cache/ranking regressions; test required report counters.
- **SELF-REVIEW CHECKLIST:** No silent candidate filtering, no second retry loop, no fake route/match.
- **EXIT GATE:** All required actual behavior probes pass and independent diff review finds no ownership regression.
- **RISKS:** Controlled change probes are not canonical trajectory outcomes; label separately.
- **FAILURE / FALLBACK BEHAVIOR:** Retain explicit error result and fail gate for unexpected success.

### Phase 6 - Local performance baseline

#### W5-06 - Local performance baseline

- **TASK ID:** W5-06
- **OBJECTIVE:** Measure real API path without optimization or invented SLA.
- **WHY:** Official Week 5 needs measured performance.
- **INPUTS:** Real services, bridge timings, representative requests.
- **OUTPUTS:** INITIAL LOCAL WEEK 5 PERFORMANCE BASELINE with 3+ warmups and 20+ measured at concurrency 1/5/10.
- **DEPENDENCIES:** W5-02 and correctness gates.
- **FILES EXPECTED TO CHANGE:** scripts/benchmark_week5.py; backend/tests/test_week5_benchmark.py; docs/reports/week5-performance.json
- **IMPLEMENTATION APPROACH:** Measure HTTP full latency and location/demand/candidate/ranking stages where practical. Report median/P90/P95/max, success/error totals, workload/cache/environment. Include failure durations separately. Do not optimize.
- **TEST PLAN:** Check percentiles/counters/concurrency limits and run real workload without concurrent benchmark jobs.
- **SELF-REVIEW CHECKLIST:** No threshold invention; no service timer mislabeled HTTP; cache states honest.
- **EXIT GATE:** Measurements complete and correctness/no-crash checks pass; any bottleneck recorded for Week 6.
- **RISKS:** Laptop measurements cannot establish production capacity.
- **FAILURE / FALLBACK BEHAVIOR:** Dependency/correctness failure fails run; slow valid responses alone do not fail an invented SLA.

### Phase 7 - Regression documentation and freeze

#### W5-07 - Regression documentation and freeze

- **TASK ID:** W5-07
- **OBJECTIVE:** Close only after every user gate passes.
- **WHY:** Need integrity and regression beyond new tests.
- **INPUTS:** All reports, baseline hash/tag manifests, completed task reviews.
- **OUTPUTS:** docs/WEEK_5.md; acceptance report; focused commits; clean tree; week5-realtime-api-evaluation-complete tag.
- **DEPENDENCIES:** W5-00 through W5-06 PASS.
- **FILES EXPECTED TO CHANGE:** docs/WEEK_5.md; docs/reports/week5-acceptance.json; docs/WEEK_5_IMPLEMENTATION_PLAN.md; docs/ARCHITECTURE.md; docs/ACCEPTANCE_CRITERIA.md; AGENTS.md; README.md
- **IMPLEMENTATION APPROACH:** Run all Week 5/full backend tests, protected validator/hashes, real infrastructure and Weeks 1-4 smokes. Audit diff from 0983164, deployed source identity, label leakage and artifact hygiene. Stage explicit files only; preserve prior tags; tag only after clean committed gate.
- **TEST PLAN:** Actual pass/fail/error/skip counts; full SHA-256 Dataset comparison; real API/DB/Redis/GH checks; git diff --check and independent review.
- **SELF-REVIEW CHECKLIST:** No missing gate, stale evidence, blanket staging, Dataset write, Week 6 implementation or production claim.
- **EXIT GATE:** All checklist items PASS, documentation complete, commits clean; only then freeze tag.
- **RISKS:** Self-referential commit IDs in docs; identify final commit through tag.
- **FAILURE / FALLBACK BEHAVIOR:** Any partial/failing gate prohibits tag and CLOSE WEEK 5.

## 19. Execution ledger

| Task | Status | Evidence |
|---|---|---|
| W5-00 | PASS | User contracts, retained 302/152/22 audit baseline, plan reviewed |
| W5-01 | PASS | 5 reproductions failed before fix; 54 focused/prior tests passed; shared accessor/None diff reviewed |
| W5-02 | PASS | 321 full protected tests; independent 19-test review PASS; actual APIs healthy on isolated schemas; location-bridge-tests.xml |
| W5-02A | PASS | 73 protected tests; 34/34 real reproductions; final replay 34 NO_MATCH and zero engine errors |
| W5-03 | PASS | replay-c: 30 trajectories, 1952 events, 308 requests, zero errors; causal provenance/cache audit; 26 focused/prior tests |
| W5-04 | PASS | Predictions persisted and hashed before labels; 184 joined reference events; docs/reports/week5-evaluation.json |
| W5-05 | PENDING | Not yet executed |
| W5-06 | PENDING | Not yet executed |
| W5-07 | PENDING | Not yet executed |
