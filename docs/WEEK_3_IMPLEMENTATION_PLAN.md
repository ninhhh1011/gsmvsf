> Historical baseline: engine-specific instructions and measurements in this document predate the GraphHopper-only migration. Current runtime and verification are documented in [the migration report](GRAPHHOPPER_MIGRATION_REPORT.md).

# WEEK 3 IMPLEMENTATION PLAN: CANDIDATE SEARCH + ROUTING

**Project:** VinFast EV Charging & Battery-Swap Recommendation System  
**Milestone:** Week 3 — Candidate Search & Routing Engine  
**Baseline Frozen:** `week2-demand-detection-complete` (commit `3d5fe9c`), Dataset V1.3.1  
**Architecture Direction:** Mentor Directive — Engine-independent dynamic routing abstraction, domain-level routing contracts, OSRM adapter, no OSRM leakage into business logic, strict separation between candidate search and ranking.

---

## 1. Executive Summary & Objective

Week 3 consumes the canonical `EnergyServiceRequest` produced in Week 2 and produces an evaluated candidate set of reachable, operational, compatible station/service alternatives with complete routing metrics (driver→station, station→destination, direct route, detour distance, detour duration, base ETA) ready for Week 4 ranking.

### Critical Boundaries
1. **Candidate Identity**: `(station_id, service_type)` — a single physical station offering both charging and swap yields TWO candidate alternatives for a swap-capable vehicle.
2. **Strict Ordering**: ALL STATIONS → EXPAND SERVICE ALTERNATIVES → FULL ELIGIBILITY (Compatibility → Status → Battery → Capacity → Queue → Route Reachability → Energy Feasibility) → ELIGIBLE CANDIDATES → (optional deterministic reduction). Never filter top-N by Euclidean distance before eligibility.
3. **No Ranking Leakage**: Week 3 does NOT calculate recommendation scores, does NOT rank candidates, does NOT pick a "best" station.
4. **Engine Independence**: Candidate search logic depends only on `RoutingEngine` protocol, `RouteRequest`, and `RouteResult`. OSRM is strictly an adapter.
5. **No Label Leakage**: `dataset_v1/labels/candidate_labels.csv` is evaluation data only. Runtime derives candidate eligibility dynamically from vehicle specs, station status, and live routing.

---

## 2. Phase Breakdown

### Phase 1: Domain Contracts & Interfaces
- **Task 1.1**: Candidate Domain Models
- **Task 1.2**: Engine-Independent Routing Domain Models

### Phase 2: Station & Service Capability Model
- **Task 2.1**: Station Catalog Loader & State Provider
- **Task 2.2**: Service Compatibility Engine
- **Task 2.3**: Unresolved & Multi-Service Request Expansion

### Phase 3: Routing Engine Interface & OSRM Adapter
- **Task 3.1**: `RoutingEngine` Abstract Contract / Protocol
- **Task 3.2**: `OSRMRoutingAdapter` Implementation
- **Task 3.3**: Mock / In-Memory Routing Adapter for Isolated Testing

### Phase 4: Multi-Leg Route & Detour Computation
- **Task 4.1**: Driver → Station Routing & Station → Destination Routing
- **Task 4.2**: Direct Route & Detour Metric Derivation
- **Task 4.3**: Missing Destination & Fallback Path Handling

### Phase 5: Energy Feasibility to Station
- **Task 5.1**: Network-Distance Energy Feasibility Evaluator (with 0.5 km buffer)
- **Task 5.2**: Edge Cases & Telemetry Invariant Verification

### Phase 6: Candidate Eligibility Engine & Orchestration
- **Task 6.1**: Candidate Eligibility Evaluator & Deterministic Reason Precedence
- **Task 6.2**: Candidate Search Orchestrator (`CandidateSearchService`)

### Phase 7: API & Subsystem Integration
- **Task 7.1**: REST API Endpoint `POST /api/v1/candidate-search`
- **Task 7.2**: Week 2 `EnergyServiceRequest` & Week 1 State Store Integration

### Phase 8: Dataset V1.3.1 Replay & Evaluation
- **Task 8.1**: Offline Replay Pipeline against `candidate_labels.csv`
- **Task 8.2**: Scenario Assertions & Mismatch Diagnostic Audit

### Phase 9: Real Infrastructure & OSRM Runtime Verification
- **Task 9.1**: OSRM Service Activation with Canonical Patched Hanoi Map
- **Task 9.2**: Live Runtime Route & Detour Smoke Verification

### Phase 10: Performance Profiling & Acceptance Audit
- **Task 10.1**: Latency & Route Call Rate Measurement
- **Task 10.2**: Full Regression (Week 1, Week 2, Dataset V1.3.1, Week 3)
- **Task 10.3**: Week 4 Handoff Contract & Final Freeze Tag

---

## 3. Detailed Task Specifications

### Phase 1: Domain Contracts & Interfaces

#### TASK 1.1: Candidate Domain Models
- **TASK ID**: `TASK-W3-01`
- **OBJECTIVE**: Define core Pydantic models for station candidates, evaluation status, eligibility reasons, and candidate search requests/responses.
- **WHY**: Provides strongly-typed, immutable domain representations preventing primitive obsession and enforcing architectural boundaries.
- **INPUTS**: Architecture docs, Dataset V1.3.1 reason codes, `EnergyServiceRequest`.
- **OUTPUTS**: `backend/app/services/candidate/models.py`.
- **DEPENDENCIES**: `backend/app/services/demand/models.py`.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/models.py` [NEW], `backend/app/services/candidate/__init__.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - `CandidateEligibilityReason` enum: `ELIGIBLE`, `INCOMPATIBLE`, `OFFLINE`, `NO_SWAP_BATTERY`, `FULL`, `EXCESSIVE_QUEUE`, `UNREACHABLE`, `INSUFFICIENT_SOC_TO_REACH`.
  - `StationServiceCandidate`: contains `station_id`, `service_type` (`CHARGING` or `BATTERY_SWAP`), `eligible: bool`, `reason: CandidateEligibilityReason`.
  - `CandidateRouteMetrics`: `distance_to_station_m`, `duration_to_station_s`, `distance_station_to_dest_m`, `duration_station_to_dest_s`, `via_total_distance_m`, `via_total_duration_s`, `direct_distance_m`, `direct_duration_s`, `detour_distance_m`, `detour_duration_s`, `eta_to_station_timestamp`.
  - `StationOperationalSnapshot`: `operating_status`, `available_service_slots`, `available_swap_batteries`, `available_capacity`, `queue_length`, `estimated_wait_min`, `service_time_min`.
  - `EvaluatedCandidate`: joins `StationServiceCandidate`, `CandidateRouteMetrics`, `StationOperationalSnapshot`, and `soc_feasible: bool`.
  - `CandidateSearchRequest`: wraps `EnergyServiceRequest` and optional `destination_latitude`, `destination_longitude`.
  - `CandidateSearchResult`: list of `EvaluatedCandidate`, `total_evaluated`, `eligible_count`, `search_timestamp`.
- **TEST PLAN**: `backend/tests/test_candidate_models.py` validating validation rules, immutability, serialization.
- **SELF-REVIEW CHECKLIST**: No ranking score fields, no recommended flag, preserves station + service pair.
- **EXIT GATE**: Unit tests PASS.
- **RISKS**: Accidental inclusion of ranking score.
- **FAILURE / FALLBACK**: Pydantic validation rejects extra fields (`extra='forbid'`).

#### TASK 1.2: Engine-Independent Routing Domain Models
- **TASK ID**: `TASK-W3-02`
- **OBJECTIVE**: Implement domain routing models independent of OSRM.
- **WHY**: Satisfies mentor directive ("custom route nhiều nhất, dynamic nhất có thể, không gò bó vào việc dễ triển khai").
- **INPUTS**: `docs/ROUTING_STRATEGY.md`.
- **OUTPUTS**: `backend/app/services/routing/models.py`.
- **DEPENDENCIES**: None.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/models.py` [NEW], `backend/app/services/routing/__init__.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - `Position`: `latitude: float`, `longitude: float`, `node_id: Optional[str] = None`.
  - `RouteStatus`: `SUCCESS`, `NO_ROUTE`, `UNREACHABLE`, `ENGINE_ERROR`, `TIMEOUT`.
  - `RouteLeg`: `from_pos: Position`, `to_pos: Position`, `distance_m: float`, `duration_s: float`, `geometry: Optional[str] = None`.
  - `RouteRequest`: `origin: Position`, `destination: Position`, `via: list[Position] = []`, `vehicle_profile: Optional[VehicleRoutingProfile] = None`, `constraints: Optional[RouteConstraints] = None`, `optimization_objective: OptimizationObjective = MIN_TRAVEL_TIME`, `dynamic_context: Optional[DynamicRoutingContext] = None`.
  - `RouteResult`: `status: RouteStatus`, `distance_m: float`, `duration_s: float`, `legs: list[RouteLeg]`, `geometry: Optional[str]`, `engine_name: str`, `error_message: Optional[str] = None`.
- **TEST PLAN**: `backend/tests/test_routing_models.py`.
- **SELF-REVIEW CHECKLIST**: No OSRM-specific query params or URL strings in domain models.
- **EXIT GATE**: Tests PASS.
- **RISKS**: OSRM concepts creeping into domain.
- **FAILURE / FALLBACK**: Keep models strictly domain-level.

---

### Phase 2: Station & Service Capability Model

#### TASK 2.1: Station Catalog Loader & State Provider
- **TASK ID**: `TASK-W3-03`
- **OBJECTIVE**: Load stations from `dataset_v1/stations/stations.csv` and status snapshots from `station_status.csv.gz`.
- **WHY**: Candidate search needs authoritative physical station definitions and dynamic slot/battery status.
- **INPUTS**: `dataset_v1/stations/stations.csv`, `dataset_v1/stations/station_status.csv.gz`.
- **OUTPUTS**: `backend/app/services/candidate/station_catalog.py`.
- **DEPENDENCIES**: Task 1.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/station_catalog.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Load all 30 stations into indexed dictionary of `StationRecord`.
  - Parse multi-valued fields (`supported_vehicle_type`, `connector_type`, `battery_type`).
  - Provide point-in-time station status lookup matching state timestamp.
- **TEST PLAN**: `backend/tests/test_station_catalog.py`.
- **SELF-REVIEW CHECKLIST**: Correctly parses 30 stations, 4 dual-service stations (S005, S010, S020, S025).
- **EXIT GATE**: Catalog load test PASS.
- **RISKS**: Missing or malformed CSV headers.
- **FAILURE / FALLBACK**: Raise explicit configuration error if catalog fails to load.

#### TASK 2.2: Service Compatibility Engine
- **TASK ID**: `TASK-W3-04`
- **OBJECTIVE**: Determine whether a vehicle can physically receive a service at a station.
- **WHY**: Prevents directing cars to motorcycle-only stations or charge-only bikes to swap stations.
- **INPUTS**: `VehicleCapability`, `StationRecord`, `ServiceType`.
- **OUTPUTS**: `backend/app/services/candidate/compatibility.py`.
- **DEPENDENCIES**: Task 2.1, Week 2 `VehicleCapability`.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/compatibility.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Replicate Dataset V1.3.1 compatibility rules:
    - If service is `CHARGING`: vehicle charging supported, station `charging_slots > 0`, vehicle type in station `supported_vehicle_type`, connector matches.
    - If service is `BATTERY_SWAP`: vehicle swap supported, station `swap_slots > 0`, vehicle type matches, connector matches, and `swap_battery_family` matches station `battery_type`.
- **TEST PLAN**: `backend/tests/test_candidate_compatibility.py` testing EV cars, charge-only bikes, swap bikes against various station types.
- **SELF-REVIEW CHECKLIST**: Exact match with Dataset V1.3.1 `service_compatible()`.
- **EXIT GATE**: All compatibility unit tests PASS.
- **RISKS**: Subtle mismatch with dataset tokenization (semicolon vs comma).
- **FAILURE / FALLBACK**: Standardize token parsing helper `tokens(value)`.

#### TASK 2.3: Unresolved & Multi-Service Request Expansion
- **TASK ID**: `TASK-W3-05`
- **OBJECTIVE**: Given an `EnergyServiceRequest`, generate all applicable candidate service alternatives.
- **WHY**: Swap-capable vehicles with `need_service=True` or requests with `ANY` must evaluate both `CHARGING` and `BATTERY_SWAP`.
- **INPUTS**: `EnergyServiceRequest`.
- **OUTPUTS**: Generator of `(station_id, service_type)` candidate pairs across all 30 stations.
- **DEPENDENCIES**: Task 2.2.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/expansion.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Determine `services_to_evaluate`:
    - If `resolved_service_type` is present: `[resolved_service_type]`.
    - If `resolved_service_type` is None: filter vehicle's `allowed_service_types` (or `[CHARGING, BATTERY_SWAP]` if swap supported).
  - For each station in catalog (30 stations):
    - For each service in `services_to_evaluate`: yield candidate `(station, service)`.
- **TEST PLAN**: `backend/tests/test_candidate_expansion.py`.
- **SELF-REVIEW CHECKLIST**: Car yields 30 candidates (charging only). Swap bike with unresolved yields 60 candidates (30 charging + 30 swap).
- **EXIT GATE**: Expansion tests PASS.
- **RISKS**: Collapsing candidates prematurely.
- **FAILURE / FALLBACK**: Keep candidates distinct by `(station_id, service_type)`.

---

### Phase 3: Routing Engine Interface & OSRM Adapter

#### TASK 3.1: Routing Engine Protocol / Abstract Base Class
- **TASK ID**: `TASK-W3-06`
- **OBJECTIVE**: Define the Python `Protocol` / ABC for routing engines.
- **WHY**: Enables plugging in OSRM, Valhalla, GraphHopper, or mock adapters without modifying business logic.
- **INPUTS**: Task 1.2 routing domain models.
- **OUTPUTS**: `backend/app/services/routing/engine.py`.
- **DEPENDENCIES**: Task 1.2.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/engine.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - `class RoutingEngine(Protocol)`:
    - `async def route(self, request: RouteRequest) -> RouteResult:`
    - `async def route_via(self, origin: Position, waypoints: list[Position], destination: Position, ...) -> RouteResult:`
    - `async def is_healthy(self) -> bool:`
- **TEST PLAN**: `backend/tests/test_routing_engine.py`.
- **SELF-REVIEW CHECKLIST**: Pure interface, zero OSRM dependencies.
- **EXIT GATE**: Protocol verification test PASS.

#### TASK 3.2: OSRM Routing Adapter Implementation
- **TASK ID**: `TASK-W3-07`
- **OBJECTIVE**: Implement `OSRMRoutingAdapter` behind `RoutingEngine`.
- **WHY**: Connects to the canonical local OSRM instance using `hanoi-patched.osrm`.
- **INPUTS**: `RouteRequest`, OSRM HTTP API specification.
- **OUTPUTS**: `backend/app/services/routing/osrm_routing_adapter.py`.
- **DEPENDENCIES**: Task 3.1, `httpx`.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/osrm_routing_adapter.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Formulate `/route/v1/driving/{lon1},{lat1};{lon2},{lat2}` (and multi-waypoint coordinates).
  - Parse OSRM JSON: extract legs, summary distance, duration, polyline geometry.
  - Map OSRM errors:
    - `NoRoute` -> `RouteStatus.NO_ROUTE`
    - Connection failure -> `RouteStatus.ENGINE_ERROR` (or raise `RoutingEngineUnavailableError`)
    - Timeout -> `RouteStatus.TIMEOUT`
- **TEST PLAN**: `backend/tests/test_osrm_routing_adapter.py` using `respx` / `httpx_mock`.
- **SELF-REVIEW CHECKLIST**: Handle non-200 responses, never return 0 distance on failure.
- **EXIT GATE**: Unit tests with mocked HTTP responses PASS.
- **RISKS**: Coordinate ordering (OSRM expects lon,lat while domain uses lat,lon).
- **FAILURE / FALLBACK**: Explicit coordinate transformation helper.

#### TASK 3.3: Mock / In-Memory Routing Adapter
- **TASK ID**: `TASK-W3-08`
- **OBJECTIVE**: Implement `MockRoutingAdapter` / `NetworkGraphRoutingAdapter` for offline and fast unit testing.
- **WHY**: Unit tests must run reliably without requiring a live Docker/OSRM daemon.
- **INPUTS**: Task 3.1.
- **OUTPUTS**: `backend/app/services/routing/mock_adapter.py`.
- **DEPENDENCIES**: Task 3.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/mock_adapter.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Haversine-based distance calculation with configurable winding factor (1.3x) and average speed (30 km/h), or pre-loaded node graph.
  - Enables full test coverage in isolated CI environments.
- **TEST PLAN**: `backend/tests/test_mock_routing_adapter.py`.
- **SELF-REVIEW CHECKLIST**: Returns valid `RouteResult` with realistic distance/duration.
- **EXIT GATE**: Mock tests PASS.

---

### Phase 4: Multi-Leg Route & Detour Computation

#### TASK 4.1: Driver → Station & Station → Destination Routing
- **TASK ID**: `TASK-W3-09`
- **OBJECTIVE**: Calculate routes: Leg 1 (driver → station) and Leg 2 (station → destination).
- **WHY**: Core candidate search metrics required for reachability, detour, and ranking.
- **INPUTS**: Driver position, station position, destination position, `RoutingEngine`.
- **OUTPUTS**: `backend/app/services/routing/multi_leg.py`.
- **DEPENDENCIES**: Tasks 1.2, 3.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/multi_leg.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Compute `leg1 = await engine.route(driver_pos, station_pos)`.
  - If destination is provided:
    - Compute `leg2 = await engine.route(station_pos, dest_pos)`.
    - Compute `direct = await engine.route(driver_pos, dest_pos)`.
- **TEST PLAN**: `backend/tests/test_multi_leg_routing.py`.
- **SELF-REVIEW CHECKLIST**: Clean separation of legs, proper error propagation.
- **EXIT GATE**: Tests PASS.

#### TASK 4.2: Detour Metric Derivation
- **TASK ID**: `TASK-W3-10`
- **OBJECTIVE**: Compute via-distance, via-duration, detour distance, and detour duration.
- **WHY**: Detour is a primary feature for driver convenience in EV charging.
- **INPUTS**: `leg1`, `leg2`, `direct`.
- **OUTPUTS**: `CandidateRouteMetrics`.
- **DEPENDENCIES**: Task 4.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/multi_leg.py`.
- **IMPLEMENTATION APPROACH**:
  - `via_distance_m = leg1.distance_m + leg2.distance_m`
  - `via_duration_s = leg1.duration_s + leg2.duration_s`
  - `detour_distance_m = max(0.0, via_distance_m - direct.distance_m)` (handle minor floating point rounding)
  - `detour_duration_s = max(0.0, via_duration_s - direct.duration_s)`
- **TEST PLAN**: `backend/tests/test_detour_metrics.py`.
- **SELF-REVIEW CHECKLIST**: Detour is never negative; base ETA equals `duration_to_station_s`.
- **EXIT GATE**: Tests PASS.

#### TASK 4.3: Missing Destination Handling
- **TASK ID**: `TASK-W3-11`
- **OBJECTIVE**: Support requests without destination (e.g. wandering driver or destination not specified).
- **WHY**: Real-world drivers sometimes request charging without entering a destination.
- **INPUTS**: `CandidateSearchRequest` with `destination=None`.
- **OUTPUTS**: Valid `CandidateRouteMetrics` with `distance_to_station_m` populated, destination/detour fields set to `None`.
- **DEPENDENCIES**: Task 4.2.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/routing/multi_leg.py`.
- **IMPLEMENTATION APPROACH**:
  - Detect `destination is None`.
  - Skip Leg 2 and direct route.
  - Return `CandidateRouteMetrics` with station leg metrics only; detour is `None`.
- **TEST PLAN**: `backend/tests/test_missing_destination.py`.
- **SELF-REVIEW CHECKLIST**: Does not throw `AttributeError` or `ValueError`.
- **EXIT GATE**: Tests PASS.

---

### Phase 5: Energy Feasibility to Station

#### TASK 5.1: Network-Distance Energy Feasibility Evaluator
- **TASK ID**: `TASK-W3-12`
- **OBJECTIVE**: Determine if vehicle has sufficient energy to physically reach the candidate station.
- **WHY**: Prevents recommending a station that the driver will run out of battery trying to reach.
- **INPUTS**: `route_distance_to_station_m`, `estimated_remaining_range_km`, `SOC_REACH_BUFFER_KM` (0.5 km).
- **OUTPUTS**: `soc_feasible: bool`, reason `INSUFFICIENT_SOC_TO_REACH` if false.
- **DEPENDENCIES**: Task 1.1, Dataset V1.3.1 semantics.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/energy_feasibility.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Match Dataset V1.3.1 exact formula:
    `feasible = (route_dist_m / 1000.0 + 0.5 <= estimated_remaining_range_km)`
  - Use network routing distance (from `RoutingEngine`), never straight-line Euclidean distance as final check.
- **TEST PLAN**: `backend/tests/test_candidate_energy_feasibility.py`.
- **SELF-REVIEW CHECKLIST**: Exact replication of `07_correct_service_intent_semantics.py` line 686.
- **EXIT GATE**: Tests PASS.

#### TASK 5.2: Edge Cases & Telemetry Invariant Verification
- **TASK ID**: `TASK-W3-13`
- **OBJECTIVE**: Robust handling of zero range, missing range, unreachable routes.
- **WHY**: Production resilience against telemetry dropouts or corrupt inputs.
- **INPUTS**: Edge-case inputs (None range, negative range, infinite distance).
- **OUTPUTS**: Safe boolean output and explicit reason code.
- **DEPENDENCIES**: Task 5.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/energy_feasibility.py`.
- **IMPLEMENTATION APPROACH**:
  - If `route_dist_m` is None or infinite -> `feasible = False`.
  - If `estimated_remaining_range_km` is None or <= 0 -> `feasible = False`.
- **TEST PLAN**: `backend/tests/test_candidate_energy_feasibility.py`.
- **SELF-REVIEW CHECKLIST**: No uncaught exceptions.
- **EXIT GATE**: Edge-case tests PASS.

---

### Phase 6: Candidate Eligibility Engine & Orchestration

#### TASK 6.1: Candidate Eligibility Evaluator & Deterministic Precedence
- **TASK ID**: `TASK-W3-14`
- **OBJECTIVE**: Evaluate full eligibility of a station/service candidate with deterministic reason precedence.
- **WHY**: Dataset V1.3.1 defines an exact, deterministic evaluation chain for reason codes.
- **INPUTS**: StationRecord, ServiceType, VehicleCapability, StationStatus, QueueStatus, RouteResult, RangeKm.
- **OUTPUTS**: `(eligible: bool, reason: CandidateEligibilityReason)`.
- **DEPENDENCIES**: Tasks 2.2, 5.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/eligibility.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Evaluate in exact order:
    1. `not route_reach` -> `(False, UNREACHABLE)`
    2. `not compatible` -> `(False, INCOMPATIBLE)`
    3. `operating_status != 'OPEN'` -> `(False, OFFLINE)`
    4. `service == BATTERY_SWAP and slots_avail > 0 and swap_batt <= 0` -> `(False, NO_SWAP_BATTERY)`
    5. `capacity <= 0` -> `(False, FULL)`
    6. `wait > CANDIDATE_MAX_WAIT_MIN` (90.0 min) -> `(False, EXCESSIVE_QUEUE)`
    7. `not soc_feasible` -> `(False, INSUFFICIENT_SOC_TO_REACH)`
    8. else -> `(True, ELIGIBLE)`
- **TEST PLAN**: `backend/tests/test_candidate_eligibility.py` testing each precedence condition when multiple failures coincide.
- **SELF-REVIEW CHECKLIST**: Matches Dataset V1.3.1 lines 689-704 byte-for-byte in semantics.
- **EXIT GATE**: Precedence tests PASS.

#### TASK 6.2: Candidate Search Orchestrator (`CandidateSearchService`)
- **TASK ID**: `TASK-W3-15`
- **OBJECTIVE**: Coordinate the full Week 3 candidate search pipeline.
- **WHY**: Single entry point combining request validation, service expansion, routing, eligibility, and metrics.
- **INPUTS**: `CandidateSearchRequest` (or `EnergyServiceRequest`), `RoutingEngine`.
- **OUTPUTS**: `CandidateSearchResult`.
- **DEPENDENCIES**: Tasks 1.1, 2.1, 2.3, 3.1, 4.1, 6.1.
- **FILES EXPECTED TO CHANGE**: `backend/app/services/candidate/service.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Short-circuit checks:
    - If `request.request_valid == False` -> return empty candidates with `reason="INVALID_REQUEST"`.
    - If `request.request_source == AUTO_DETECTED and request.need_service == False` -> return empty candidates with `reason="NO_SERVICE_NEEDED"`.
  - Expand candidates: generate `(station, service)` pairs for allowed/unresolved services.
  - Perform routing and evaluate eligibility across all candidates.
  - Assemble `EvaluatedCandidate` objects with route metrics.
  - Filter `eligible_candidates = [c for c in candidates if c.eligible]`.
  - Return `CandidateSearchResult`.
- **TEST PLAN**: `backend/tests/test_candidate_search_service.py`.
- **SELF-REVIEW CHECKLIST**: No top-N before eligibility, all 30 stations evaluated, clean candidate results.
- **EXIT GATE**: Service tests PASS.

---

### Phase 7: API & Subsystem Integration

#### TASK 7.1: REST API Endpoint `POST /api/v1/candidate-search`
- **TASK ID**: `TASK-W3-16`
- **OBJECTIVE**: Expose candidate search as a clean REST API.
- **WHY**: Satisfies system architecture deliverables for Week 3.
- **INPUTS**: HTTP POST body matching `CandidateSearchRequest` or `EnergyServiceRequest`.
- **OUTPUTS**: HTTP JSON response matching `CandidateSearchResult`.
- **DEPENDENCIES**: Task 6.2, FastAPI router.
- **FILES EXPECTED TO CHANGE**: `backend/app/api/v1/candidate.py` [NEW], `backend/app/main.py` [MODIFY].
- **IMPLEMENTATION APPROACH**:
  - Define FastAPI router with dependency injection for `CandidateSearchService` and `RoutingEngine`.
  - Register router in `backend/app/main.py` under prefix `/api/v1`.
  - Handle exceptions gracefully with standard HTTP error codes (400, 422, 500, 503).
- **TEST PLAN**: `backend/tests/test_candidate_api.py` using `httpx.AsyncClient`.
- **SELF-REVIEW CHECKLIST**: Status codes, input validation, no ranking fields in response.
- **EXIT GATE**: API tests PASS.

#### TASK 7.2: Integration with Week 2 Demand Detection & Week 1 State
- **TASK ID**: `TASK-W3-17`
- **OBJECTIVE**: Seamless integration between Week 1 Realtime Driver State, Week 2 Demand Detection, and Week 3 Candidate Search.
- **WHY**: Allows end-to-end pipeline: telemetry -> map match -> demand detection -> candidate search.
- **INPUTS**: `driver_id` or `DemandContext`.
- **OUTPUTS**: Chained pipeline producing `CandidateSearchResult`.
- **DEPENDENCIES**: Week 1 `DriverStateStore`, Week 2 `DemandDetectionService`, Task 6.2.
- **FILES EXPECTED TO CHANGE**: `backend/app/api/v1/candidate.py`.
- **IMPLEMENTATION APPROACH**:
  - Add optional endpoint or utility `POST /api/v1/candidate-search/evaluate` accepting `DemandContext` or `driver_id`, generating `EnergyServiceRequest` via Week 2 service, then feeding it directly to Candidate Search.
- **TEST PLAN**: `backend/tests/test_end_to_end_integration.py`.
- **SELF-REVIEW CHECKLIST**: Preserves Week 1 and Week 2 without modifying their internal contracts.
- **EXIT GATE**: Integration tests PASS.

---

### Phase 8: Dataset V1.3.1 Replay & Evaluation

#### TASK 8.1: Offline Replay Pipeline against `candidate_labels.csv`
- **TASK ID**: `TASK-W3-18`
- **OBJECTIVE**: Replay Dataset V1.3.1 candidate evaluation events and compare runtime output against `candidate_labels.csv`.
- **WHY**: Proves semantic adherence to canonical ground truth without leaking labels into runtime.
- **INPUTS**: `dataset_v1/labels/candidate_labels.csv`, `dataset_v1/labels/energy_service_requests.csv`.
- **OUTPUTS**: Replay evaluation report and confusion matrix.
- **DEPENDENCIES**: Task 6.2.
- **FILES EXPECTED TO CHANGE**: `backend/tests/test_candidate_dataset_replay.py` [NEW], `scripts/evaluate_candidate_search.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Sample representative events across cars, charge-only bikes, and swap bikes.
  - Run runtime CandidateSearchService (using mock/network matrix matching dataset road network).
  - Compare `eligible` boolean and `reason` string against labels.
- **TEST PLAN**: Pytest suite checking agreement rate >= 99%.
- **SELF-REVIEW CHECKLIST**: Labels strictly used for comparison in assertions, never passed into service.
- **EXIT GATE**: Replay suite passes.

#### TASK 8.2: Canonical Scenario Verification
- **TASK ID**: `TASK-W3-19`
- **OBJECTIVE**: Explicitly verify the 14+ required scenarios:
  - `CAR_CHARGING_ELIGIBLE`
  - `CAR_INCOMPATIBLE_MOTORCYCLE_STATION`
  - `CHARGE_ONLY_BIKE_CHARGING`
  - `CHARGE_ONLY_BIKE_SWAP_NOT_ALLOWED`
  - `SWAP_BIKE_CHARGING`
  - `SWAP_BIKE_SWAP`
  - `SWAP_BIKE_BOTH_ALLOWED`
  - `STATION_OFFLINE`
  - `STATION_FULL`
  - `STATION_UNREACHABLE`
  - `INSUFFICIENT_SOC_TO_REACH`
  - `NO_ELIGIBLE_CANDIDATES`
  - `MULTIPLE_ELIGIBLE_CANDIDATES`
  - `FARTHER_BUT_FASTER`
- **WHY**: Validates business edge cases mandated by project scope and acceptance criteria.
- **INPUTS**: Dataset V1.3.1 scenario definitions in `dataset_v1/scenarios/scenario_coverage.csv`.
- **OUTPUTS**: `backend/tests/test_candidate_scenarios.py`.
- **DEPENDENCIES**: Task 8.1.
- **FILES EXPECTED TO CHANGE**: `backend/tests/test_candidate_scenarios.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Replay specific scenario event IDs and assert expected eligibility and candidate set structure.
- **TEST PLAN**: Run pytest on `test_candidate_scenarios.py`.
- **SELF-REVIEW CHECKLIST**: All 14 scenarios covered with explicit assertions.
- **EXIT GATE**: 100% scenario tests PASS.

---

### Phase 9: Real Infrastructure & OSRM Runtime Verification

#### TASK 9.1: OSRM Service Activation with Canonical Patched Hanoi Map
- **TASK ID**: `TASK-W3-20`
- **OBJECTIVE**: Verify or launch the OSRM backend container with `hanoi-patched.osrm` on port 5000.
- **WHY**: Week 3 core deliverable requires real road network routing.
- **INPUTS**: `runtime/osrm/hanoi-patched.osrm`, Docker Desktop / compose.
- **OUTPUTS**: Verified HTTP response from `http://localhost:5000/route/v1/driving/...`.
- **DEPENDENCIES**: Docker daemon.
- **FILES EXPECTED TO CHANGE**: None (configuration already in `docker-compose.yml`).
- **IMPLEMENTATION APPROACH**:
  - Start Docker / OSRM container `ev_osrm`.
  - Validate health endpoint and route query between known Hanoi coordinates.
- **TEST PLAN**: Live curl / httpx test script.
- **SELF-REVIEW CHECKLIST**: Uses `hanoi-patched.osrm` (not baseline).
- **EXIT GATE**: Live route query returns code `Ok` and valid distance.

#### TASK 9.2: Live Runtime Route & Detour Smoke Verification
- **TASK ID**: `TASK-W3-21`
- **OBJECTIVE**: Execute end-to-end Candidate Search API against the live OSRM instance.
- **WHY**: Confirms integration between FastAPI, OSRM adapter, and candidate search pipeline.
- **INPUTS**: Live FastAPI instance, live OSRM instance.
- **OUTPUTS**: Live JSON response with real road distances and detours.
- **DEPENDENCIES**: Tasks 7.1, 9.1.
- **FILES EXPECTED TO CHANGE**: `scripts/smoke_test_week3.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Query `/api/v1/candidate-search` with sample requests.
  - Verify Leg 1, Leg 2, direct route, and detour metrics with non-zero road distances.
- **TEST PLAN**: Run `scripts/smoke_test_week3.py`.
- **SELF-REVIEW CHECKLIST**: Distances reflect real road network topology.
- **EXIT GATE**: Smoke test PASS.

---

### Phase 10: Performance Profiling & Acceptance Audit

#### TASK 10.1: Latency & Route Call Rate Measurement
- **TASK ID**: `TASK-W3-22`
- **OBJECTIVE**: Profile candidate search latency, OSRM route calls per request, candidate counts.
- **WHY**: Establish empirical baseline for Week 6 optimization without premature optimization in Week 3.
- **INPUTS**: Sample requests from dataset.
- **OUTPUTS**: Performance benchmark statistics (median, P90, P95).
- **DEPENDENCIES**: Task 9.2.
- **FILES EXPECTED TO CHANGE**: `scripts/benchmark_week3.py` [NEW].
- **IMPLEMENTATION APPROACH**:
  - Measure 100 candidate search executions.
  - Report latency distribution and route calls per search.
- **TEST PLAN**: Run benchmark script.
- **SELF-REVIEW CHECKLIST**: No caching or Redis added (maintain architectural cleanliness).
- **EXIT GATE**: Benchmark documented.

#### TASK 10.2: Full Regression Suite
- **TASK ID**: `TASK-W3-23`
- **OBJECTIVE**: Execute full regression across all project layers.
- **WHY**: Ensure zero regressions in Week 1, Week 2, or Dataset V1.3.1.
- **INPUTS**: All pytest files, `validate_dataset.py`.
- **OUTPUTS**: Clean test run across all suites.
- **DEPENDENCIES**: All prior tasks.
- **FILES EXPECTED TO CHANGE**: None.
- **IMPLEMENTATION APPROACH**:
  - Run `python dataset_v1/validation/validate_dataset.py` (152 checks, 22 scenarios).
  - Run `pytest backend/tests/test_map_matching.py backend/tests/test_realtime.py backend/tests/test_health.py` (Week 1).
  - Run `pytest backend/tests/test_demand_*.py backend/tests/test_auto_detector.py backend/tests/test_energy_feasibility.py backend/tests/test_scenarios_week2.py` (Week 2).
  - Run all Week 3 tests.
- **TEST PLAN**: 100% tests PASS, 0 failures.
- **SELF-REVIEW CHECKLIST**: No existing tests modified or weakened.
- **EXIT GATE**: All suites PASS.

#### TASK 10.3: Documentation & Week 4 Handoff
- **TASK ID**: `TASK-W3-24`
- **OBJECTIVE**: Document Week 3 architecture, candidate search pipeline, and handoff contract in `docs/WEEK_3.md`.
- **WHY**: Source of truth for Week 4 ranking model development.
- **INPUTS**: Completed Week 3 implementation.
- **OUTPUTS**: `docs/WEEK_3.md` [NEW].
- **DEPENDENCIES**: Task 10.2.
- **FILES EXPECTED TO CHANGE**: `docs/WEEK_3.md` [NEW], `docs/DECISIONS.md` [MODIFY].
- **IMPLEMENTATION APPROACH**:
  - Document candidate data contract, routing abstraction, OSRM adapter, evaluation results, handoff schema for Week 4.
  - Create tag `week3-candidate-routing-complete`.
- **TEST PLAN**: Review documentation against acceptance criteria.
- **SELF-REVIEW CHECKLIST**: Traceability matrix complete, limitations documented.
- **EXIT GATE**: Documentation approved.

---

## 4. Acceptance Traceability Matrix

| Requirement | Implementation Component | Test File | Runtime Verification | Status |
|---|---|---|---|---|
| Candidate identity = (station, service) | `StationServiceCandidate` | `test_candidate_models.py` | `smoke_test_week3.py` | Planned |
| Vehicle-station compatibility | `check_station_service_compatibility` | `test_candidate_compatibility.py` | `evaluate_candidate_search.py` | Planned |
| Unresolved service expansion | `CandidateExpansionEngine` | `test_candidate_expansion.py` | `test_candidate_scenarios.py` | Planned |
| Operational & capacity filtering | `CandidateEligibilityEvaluator` | `test_candidate_eligibility.py` | `test_candidate_scenarios.py` | Planned |
| Engine-independent routing contract | `RoutingEngine`, `RouteRequest`, `RouteResult` | `test_routing_engine.py` | N/A (Architecture boundary) | Planned |
| OSRM routing adapter | `OSRMRoutingAdapter` | `test_osrm_routing_adapter.py` | Live OSRM query | Planned |
| Multi-leg routing (leg1, leg2, direct) | `MultiLegRouteCalculator` | `test_multi_leg_routing.py` | `smoke_test_week3.py` | Planned |
| Detour metrics (distance, duration) | `CandidateRouteMetrics` | `test_detour_metrics.py` | `smoke_test_week3.py` | Planned |
| Energy feasibility to station | `check_energy_feasibility_to_station` | `test_candidate_energy_feasibility.py` | `test_candidate_scenarios.py` | Planned |
| Full Candidate Search Pipeline | `CandidateSearchService` | `test_candidate_search_service.py` | `smoke_test_week3.py` | Planned |
| REST API `/api/v1/candidate-search` | FastAPI router `api/v1/candidate.py` | `test_candidate_api.py` | Live HTTP request | Planned |
| Dataset V1.3.1 Replay | Replay harness | `test_candidate_dataset_replay.py` | `evaluate_candidate_search.py` | Planned |
| Zero regression Week 1 & 2 | All existing test suites | Pytest runner | CI test suite | Planned |
| Dataset integrity preserved | `validate_dataset.py` | 152 checks + 22 scenarios | Script execution | Planned |
