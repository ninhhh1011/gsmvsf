> Historical baseline: engine-specific instructions and measurements in this document predate the GraphHopper-only migration. Current runtime and verification are documented in [the migration report](GRAPHHOPPER_MIGRATION_REPORT.md).

# WEEK 2 IMPLEMENTATION PLAN
# VinFast EV Charging & Battery Swap Recommendation — Energy Service Need / Demand Detection

**Document Version:** 1.0.0  
**Baseline Commits:**  
- `a3207e7` (chore: clean and freeze Week 1 baseline)  
- `67bff3c` (docs: align routing architecture with mentor direction)  
- `ce3d170` (data: freeze VinFast service intent dataset v1.3.1)  
**Target Milestone:** Week 2 — Demand Detection & Energy Service Request Convergence

---

## 1. Executive Summary & Week 2 Objective

The primary objective of Week 2 is to implement **Energy Service Need / Demand Detection**. The system determines:
1. **Capability:** What energy services (`CHARGING`, `BATTERY_SWAP`) can the current VinFast vehicle use? (Deterministic model-level capability resolution).
2. **Need (AUTO_DETECTED):** Does the driver currently need an energy service based on battery SOC, energy consumption, estimated range, remaining trip distance, and safety reserve?
3. **Intent (DRIVER_REQUEST):** If the request originates explicitly from the driver (`CHARGING`, `BATTERY_SWAP`, `ANY`), is that request supported by the vehicle?
4. **Convergence:** Normalize both `AUTO_DETECTED` and `DRIVER_REQUEST` into a single, canonical `EnergyServiceRequest` contract to serve as the immutable input for Week 3 Candidate Search.

### Strict Boundaries
- **NO Week 3 leakage:** Do NOT implement candidate station search, station filtering, or routing.
- **NO Week 4 leakage:** Do NOT implement station ranking, scoring, or recommendation.
- **Preserve Week 1:** Do NOT redesign or break Week 1 Map Matching or realtime GPS tracking.
- **Dataset V1 is Read-Only:** Do NOT modify `dataset_v1/`. Labels are strictly for evaluation.

---

## 2. Phase & Task Breakdown Overview

| Phase | Description | Key Deliverables |
|---|---|---|
| **Phase 1** | Domain Contracts & Enums | `ServiceType`, `RequestSource`, `ReasonCode`, `VehicleCapability`, `DemandContext`, `EnergyServiceRequest` |
| **Phase 2** | Vehicle Capability Resolution | Model-level catalog mapping, `VehicleCapabilityResolver`, support matrix |
| **Phase 3** | AUTO_DETECTED Demand Baseline | Energy feasibility engine, safety reserve calculation, reason code attribution |
| **Phase 4** | DRIVER_REQUEST Intent Resolution | Explicit driver intent validation against vehicle capabilities, rejection of unsupported requests |
| **Phase 5** | EnergyServiceRequest Convergence | Unified factory / pipeline producing `EnergyServiceRequest`, invariant validation |
| **Phase 6** | Offline Baseline & ML Evaluation | Benchmark rule baseline vs ML (Logistic Regression / Decision Tree) on canonical split |
| **Phase 7** | API & Week 1 Integration | REST endpoints (`/evaluate`, `/request`, state retrieval), integration with `DriverTraceState` |
| **Phase 8** | Scenario Replay & Acceptance | 13+ scenario verifications from Dataset V1.3.1, full regression, audit & final documentation |

---

## 3. Detailed Phase Specifications

### PHASE 1: DOMAIN CONTRACTS

#### TASK 1.1: Core Enums and Value Objects
- **TASK ID:** `W2-T1.1`
- **OBJECTIVE:** Define fundamental domain enums and immutable value objects for service types, request sources, reason codes, and vehicle categories.
- **WHY:** Week 2 requires strict semantic differentiation between requested service, allowed services, and resolved service.
- **INPUTS:** Requirements from `docs/DATA_CONTRACT.md`, `dataset_v1/VERSION.md`, `dataset_v1/DATA_DICTIONARY.md`.
- **OUTPUTS:** `backend/app/services/demand/models.py`.
- **DEPENDENCIES:** Standard library `enum`, `pydantic` v2.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/services/demand/__init__.py` [NEW]
  - `backend/app/services/demand/models.py` [NEW]
- **IMPLEMENTATION APPROACH:**
  - `ServiceType(str, Enum)`: `CHARGING`, `BATTERY_SWAP`.
  - `RequestedServiceType(str, Enum)`: `CHARGING`, `BATTERY_SWAP`, `ANY`.
  - `RequestSource(str, Enum)`: `AUTO_DETECTED`, `DRIVER_REQUEST`.
  - `ReasonCode(str, Enum)`:
    - `SUFFICIENT_SOC_RANGE`
    - `LOW_SOC`
    - `INSUFFICIENT_RANGE`
    - `LOW_SOC_AND_INSUFFICIENT_RANGE`
    - `VALID_REQUEST`
    - `UNSUPPORTED_SERVICE`
    - `MISSING_DATA`
    - `INVALID_STATE`
    - `STALE_STATE`
  - `VehicleCategory(str, Enum)`: `EV_CAR`, `EV_MOTORBIKE`.
  - `VehicleModel(str, Enum)`: 19 models (`VF_3`, `VF_5`, `HERIO_GREEN`, `VF_6`, `VF_7_ECO`, `VF_7_PLUS`, `VF_8`, `VF_9`, `VF_E34`, `NERIO_GREEN`, `EVO200`, `EVO200_LITE`, `FELIZ_S`, `KLARA_S_2022`, `VENTO_S`, `EVO`, `EVO_LITE`, `FELIZ_II`, `VIPER`).
- **TESTS:** `backend/tests/test_demand_models.py` checking enum values, string serialization, and immutability.
- **SELF-REVIEW CHECKLIST:**
  - [ ] `ServiceType` contains only physical services (`CHARGING`, `BATTERY_SWAP`), NOT `NONE` or `ANY`.
  - [ ] `RequestedServiceType` allows `ANY`.
  - [ ] No routing engine or station recommendation dependencies.
- **EXIT GATE:** Enums imported and unit tested without error.
- **RISKS:** Over-complicating enums with UI-specific metadata.

#### TASK 1.2: Vehicle Capability and Telemetry Contracts
- **TASK ID:** `W2-T1.2`
- **OBJECTIVE:** Define data structures for `VehicleCapability`, `DemandContext` (telemetry & trip state), and `NeedServiceDecision`.
- **WHY:** Separate vehicle physical traits from dynamic trip telemetry.
- **INPUTS:** `dataset_v1/vehicles/vehicle_model_catalog.csv` schema, `dataset_v1/vehicles/vehicles.csv` schema.
- **OUTPUTS:** Domain models in `backend/app/services/demand/models.py`.
- **DEPENDENCIES:** Task 1.1.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/demand/models.py`.
- **IMPLEMENTATION APPROACH:**
  - `VehicleCapability`: `vehicle_model`, `vehicle_category`, `battery_architecture`, `battery_capacity_kwh`, `usable_capacity_kwh`, `charging_supported`, `swap_supported`, `public_swap_compatible`, `charging_interface_class`, `swap_battery_family`. Methods: `allowed_service_types -> list[ServiceType]`.
  - `DemandContext`: `vehicle_id`, `driver_id`, `trip_id`, `timestamp`, `current_soc_pct`, `distance_travelled_km`, `planned_trip_distance_km`, `estimated_remaining_range_km`, `consumption_wh_per_km`, `minimum_safe_soc_pct`, `raw_latitude`, `raw_longitude`, `road_segment_id`.
  - `NeedServiceDecision`: `need_service: bool`, `reason_code: ReasonCode`, `safety_reserve_km: float`, `remaining_trip_distance_km: float`.
- **TESTS:** `test_demand_models.py` verifying model instantiation and validators.
- **SELF-REVIEW CHECKLIST:**
  - [ ] Validations reject negative SOC, negative distance, or empty IDs.
- **EXIT GATE:** Unit tests pass.

#### TASK 1.3: Unified EnergyServiceRequest Contract
- **TASK ID:** `W2-T1.3`
- **OBJECTIVE:** Define `EnergyServiceRequest` as the common contract consumed by Week 3.
- **WHY:** Ensures single downstream interface whether demand originated via auto-telemetry or driver button tap.
- **INPUTS:** Requirements from prompt Phase 2 & 6, `dataset_v1/labels/energy_service_requests.csv`.
- **OUTPUTS:** `EnergyServiceRequest` class in `backend/app/services/demand/models.py`.
- **DEPENDENCIES:** Task 1.1, Task 1.2.
- **FILES EXPECTED TO CHANGE:** `backend/app/services/demand/models.py`.
- **IMPLEMENTATION APPROACH:**
  - Fields: `service_request_id`, `driver_id`, `vehicle_id`, `trip_id`, `timestamp`, `request_source`, `need_service`, `requested_service_type`, `allowed_service_types`, `resolved_service_type`, `request_valid`, `reason_code`, `current_soc_pct`, `estimated_remaining_range_km`, `remaining_trip_distance_km`, `safety_reserve_km`, `vehicle_model`, `vehicle_type`, `battery_capacity_kwh`, `usable_capacity_kwh`, `swap_supported`, `charging_supported`, `public_swap_compatible`, location fields.
  - Invariants:
    - If `need_service == False`: `resolved_service_type is None`.
    - If `request_source == AUTO_DETECTED` and `need_service == True` and both allowed: `resolved_service_type is None`.
    - If `requested_service_type == ANY`: `resolved_service_type is None`.
    - If `request_valid == False`: `resolved_service_type is None` and `reason_code == UNSUPPORTED_SERVICE`.
    - NO candidate station, routing, or ranking fields.
- **TESTS:** Invariant validation tests in `test_demand_models.py`.
- **EXIT GATE:** Unit tests pass; Phase 1 Exit Gate satisfied.

---

### PHASE 2: VEHICLE CAPABILITY RESOLUTION

#### TASK 2.1: Vehicle Catalog & Capability Resolver
- **TASK ID:** `W2-T2.1`
- **OBJECTIVE:** Implement deterministic vehicle capability resolution based on model catalog.
- **WHY:** Model-level capability dictates allowed services without category-level assumptions.
- **INPUTS:** `dataset_v1/vehicles/vehicle_model_catalog.csv` and `dataset_v1/vehicles/vehicles.csv`.
- **OUTPUTS:** `backend/app/services/demand/capability.py`.
- **DEPENDENCIES:** Phase 1.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/services/demand/capability.py` [NEW]
- **IMPLEMENTATION APPROACH:**
  - Pre-configure the 19 official VinFast models in code/registry (with optional loader from `vehicle_model_catalog.csv` / fallback).
  - Provide `VehicleCapabilityResolver`:
    - `resolve_by_model(model_name: str) -> VehicleCapability`
    - `resolve_by_vehicle_id(vehicle_id: str) -> VehicleCapability`
  - Strict classification:
    - 10 cars -> `[CHARGING]`
    - 5 charge-only motorbikes (`EVO200`, `EVO200_LITE`, `FELIZ_S`, `KLARA_S_2022`, `VENTO_S`) -> `[CHARGING]`
    - 4 swap-capable motorbikes (`EVO`, `EVO_LITE`, `FELIZ_II`, `VIPER`) -> `[CHARGING, BATTERY_SWAP]`
  - Unknown models raise explicit `UnknownVehicleModelError` / fail safely.
- **TESTS:** `backend/tests/test_vehicle_capability.py` testing every model, fleet vehicle IDs, unknown model, and category checks.
- **SELF-REVIEW CHECKLIST:**
  - [ ] No `vehicle_category == EV_MOTORBIKE` swap shortcut.
  - [ ] HERIO_GREEN (car) is present and resolves to `[CHARGING]`.
  - [ ] Deterministic; 0% ML.
- **EXIT GATE:** Phase 2 Exit Gate satisfied.

---

### PHASE 3: AUTO_DETECTED DEMAND BASELINE

#### TASK 3.1: Energy Feasibility & Need Detection Engine
- **TASK ID:** `W2-T3.1`
- **OBJECTIVE:** Implement deterministic energy feasibility demand detection matching Dataset V1.3.1 logic.
- **WHY:** Drivers only need service when SOC is below safety margin or remaining range cannot complete the trip + reserve.
- **INPUTS:** `DemandContext`, `VehicleCapability`.
- **OUTPUTS:** `backend/app/services/demand/auto_detector.py`.
- **DEPENDENCIES:** Phase 1, Phase 2.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/services/demand/auto_detector.py` [NEW]
- **IMPLEMENTATION APPROACH:**
  - Safety threshold: `below_safe = soc_pct <= float(minimum_safe_soc_pct) + 5.0`
  - Reserve calculation: `safety_reserve_km = max(1.0, remaining_trip_km * 0.15)` (configurable / dynamic context)
  - Feasibility check: `insufficient_range = remaining_range_km < (remaining_trip_km + safety_reserve_km)`
  - Need condition: `need_service = below_safe or insufficient_range`
  - Reason code logic:
    - If not `need_service`: `SUFFICIENT_SOC_RANGE`
    - Else if `below_safe and insufficient_range`: `LOW_SOC_AND_INSUFFICIENT_RANGE`
    - Else if `below_safe`: `LOW_SOC`
    - Else: `INSUFFICIENT_RANGE`
  - Service resolution:
    - If not `need_service`: `resolved_service_type = None`
    - If `need_service`:
      - If `swap_supported == False`: `resolved_service_type = ServiceType.CHARGING`
      - If `swap_supported == True`: `resolved_service_type = None` (UNRESOLVED)
  - Missing/invalid telemetry handling: explicit `MISSING_DATA` or `INVALID_STATE` reason code.
- **TESTS:** `backend/tests/test_auto_detector.py` covering boundary cases: high SOC/short trip, low SOC/short trip, medium SOC/long trip, exact thresholds, missing SOC/distance, swap-capable vs charge-only.
- **SELF-REVIEW CHECKLIST:**
  - [ ] Never auto-selects `BATTERY_SWAP`.
  - [ ] Explains reasons unambiguously.
- **EXIT GATE:** Phase 3 Exit Gate satisfied.

---

### PHASE 4: DRIVER_REQUEST INTENT RESOLUTION

#### TASK 4.1: Explicit Intent Validator
- **TASK ID:** `W2-T4.1`
- **OBJECTIVE:** Validate explicit driver requests against vehicle capabilities and produce valid or rejected requests.
- **WHY:** Drivers can request charging, swap, or any service, but requests must be rejected if the vehicle lacks support.
- **INPUTS:** `driver_id`, `vehicle_id`, `requested_service: RequestedServiceType`, `DemandContext`.
- **OUTPUTS:** `backend/app/services/demand/driver_requester.py`.
- **DEPENDENCIES:** Phase 1, Phase 2.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/services/demand/driver_requester.py` [NEW]
- **IMPLEMENTATION APPROACH:**
  - Matrix validation:
    - Car + `CHARGING` -> `valid=True`, `resolved=CHARGING`, `reason=VALID_REQUEST`
    - Car + `BATTERY_SWAP` -> `valid=False`, `resolved=None`, `reason=UNSUPPORTED_SERVICE`
    - Car + `ANY` -> `valid=True`, `resolved=CHARGING` (or unsupported if strictly multi-service; verify against Dataset rules)
    - Charge-only bike + `CHARGING` -> `valid=True`, `resolved=CHARGING`, `reason=VALID_REQUEST`
    - Charge-only bike + `BATTERY_SWAP` -> `valid=False`, `resolved=None`, `reason=UNSUPPORTED_SERVICE`
    - Swap-capable bike + `CHARGING` -> `valid=True`, `resolved=CHARGING`, `reason=VALID_REQUEST`
    - Swap-capable bike + `BATTERY_SWAP` -> `valid=True`, `resolved=BATTERY_SWAP`, `reason=VALID_REQUEST`
    - Swap-capable bike + `ANY` -> `valid=True`, `allowed=[CHARGING, BATTERY_SWAP]`, `resolved=None`, `reason=VALID_REQUEST`
  - Explicit driver requests always have `need_service = True`.
  - Never silently convert unsupported `BATTERY_SWAP` into `CHARGING`.
  - Never silently resolve `ANY` to `CHARGING` for swap-capable vehicles.
- **TESTS:** `backend/tests/test_driver_requester.py` verifying the complete 3x3 matrix across vehicle types and request types.
- **SELF-REVIEW CHECKLIST:**
  - [ ] Matrix matches Dataset V1.3.1 semantics byte-for-byte.
- **EXIT GATE:** Phase 4 Exit Gate satisfied.

---

### PHASE 5: ENERGY SERVICE REQUEST CONVERGENCE

#### TASK 5.1: Unified Request Factory & Invariant Verifier
- **TASK ID:** `W2-T5.1`
- **OBJECTIVE:** Converge `AUTO_DETECTED` and `DRIVER_REQUEST` workflows into `EnergyServiceRequest`.
- **WHY:** Week 3 consumes a single standard contract regardless of request origin.
- **INPUTS:** Results from AutoDetector or DriverRequester, plus `DemandContext` & `VehicleCapability`.
- **OUTPUTS:** `backend/app/services/demand/service.py`.
- **DEPENDENCIES:** Phases 1–4.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/services/demand/service.py` [NEW]
- **IMPLEMENTATION APPROACH:**
  - `DemandService.evaluate_auto_demand(...) -> EnergyServiceRequest`
  - `DemandService.process_driver_request(...) -> EnergyServiceRequest`
  - Generate unique `service_request_id` (e.g. `REQ-...` or preserve `event_id` in offline replay).
  - Validate all invariant rules before returning.
- **TESTS:** `backend/tests/test_demand_service.py` testing convergence of both flows into identical schema.
- **SELF-REVIEW CHECKLIST:**
  - [ ] No candidate station or route fields attached.
- **EXIT GATE:** Phase 5 Exit Gate satisfied.

---

### PHASE 6: OFFLINE BASELINE / ML EVALUATION

#### TASK 6.1: Offline Benchmark Script & Metric Verification
- **TASK ID:** `W2-T6.1`
- **OBJECTIVE:** Benchmark the rule-based feasibility baseline against canonical `demand_need_service_features.csv` and `demand_need_service_labels.csv` (1200 AUTO_DETECTED samples, 848 pos / 352 neg). Train and compare with Logistic Regression / Decision Tree.
- **WHY:** AGENTS.md and Week 2 instructions require an evidence-based comparison between rule baseline and ML, documenting accuracy, precision, recall, F1, and confusion matrix on the trip-separated test split.
- **INPUTS:** `dataset_v1/training/demand_need_service_features.csv`, `dataset_v1/training/demand_need_service_labels.csv`.
- **OUTPUTS:**
  - `scripts/evaluate_demand_ml.py` [NEW]
  - `docs/reports/demand_evaluation_report.json` / markdown table in docs.
- **DEPENDENCIES:** `scikit-learn`, `pandas`, `numpy`.
- **FILES EXPECTED TO CHANGE:**
  - `scripts/evaluate_demand_ml.py` [NEW]
  - `docs/WEEK_2.md` [NEW/UPDATE]
- **IMPLEMENTATION APPROACH:**
  - Verify train (840) / val (176) / test (184) trip separation (zero leakage).
  - Evaluate Rule Baseline: compute `need_service` using our feasibility logic on test split.
  - Train Logistic Regression & Decision Tree / Random Forest on train split, evaluate on test split.
  - Calculate: Accuracy, Precision, Recall, F1, Confusion Matrix for `need_service=True`.
  - Document runtime decision: Keep rule-based feasibility for runtime execution due to perfect interpretability, zero latency overhead, zero inference drift risk, and direct consistency with physical battery constraints.
- **TESTS:** Run `python scripts/evaluate_demand_ml.py` and verify all splits & metrics output correctly.
- **SELF-REVIEW CHECKLIST:**
  - [ ] No label leakage in feature set.
  - [ ] Clear statement on generator simulation data vs production claims.
- **EXIT GATE:** Phase 6 Exit Gate satisfied.

---

### PHASE 7: API & WEEK 1 INTEGRATION

#### TASK 7.1: REST Endpoints & Route Registration
- **TASK ID:** `W2-T7.1`
- **OBJECTIVE:** Expose Week 2 capability and demand evaluation via FastAPI REST endpoints, integrating with existing Week 1 `DriverTraceState`.
- **WHY:** Allow client applications and simulation harnesses to trigger demand evaluation or submit explicit requests.
- **INPUTS:** `backend/app/services/demand/service.py`, `backend/app/services/realtime/state.py`.
- **OUTPUTS:**
  - `backend/app/api/v1/demand.py` [NEW]
  - Updates to `backend/app/main.py`.
- **DEPENDENCIES:** Phases 1–5.
- **FILES EXPECTED TO CHANGE:**
  - `backend/app/api/v1/demand.py` [NEW]
  - `backend/app/main.py` [MODIFY]
- **IMPLEMENTATION APPROACH:**
  - Endpoints:
    - `POST /api/v1/demand/evaluate`: Evaluate auto demand for a vehicle/trip snapshot.
    - `POST /api/v1/demand/request`: Submit explicit driver request (`CHARGING`, `BATTERY_SWAP`, `ANY`).
    - `GET /api/v1/vehicles/{vehicle_id}/capability`: Query vehicle capabilities.
    - `POST /api/v1/drivers/{driver_id}/demand/evaluate`: Convenience endpoint reading latest Week 1 driver state from `DriverStateStore` when available.
  - Error handling:
    - `400 Bad Request`: malformed input, invalid enum.
    - `404 Not Found`: unknown driver/vehicle.
    - `422 Unprocessable Entity`: validation failure.
- **TESTS:** `backend/tests/test_demand_api.py` testing successful calls, error conditions, and status codes.
- **SELF-REVIEW CHECKLIST:**
  - [ ] Week 1 endpoints (`/map-match`, `/drivers/{id}/location`) continue to function without modification.
  - [ ] 41 baseline tests remain PASS.
- **EXIT GATE:** Phase 7 Exit Gate satisfied.

---

### PHASE 8: SCENARIO REPLAY & ACCEPTANCE

#### TASK 8.1: Dataset Scenario Replay & Acceptance Suite
- **TASK ID:** `W2-T8.1`
- **OBJECTIVE:** Replay canonical scenarios from `scenarios/scenario_coverage.csv` and `labels/demand_labels.csv` through Week 2 implementation.
- **WHY:** Prove correctness on actual Dataset V1.3.1 events without hardcoding outputs.
- **INPUTS:** Real scenario event IDs from Dataset V1.3.1:
  - `CAR_AUTO_NO_SERVICE` (`NORMAL_TRIP`, `NO_SERVICE_NEEDED`)
  - `CAR_AUTO_NEED_CHARGE` (`NEED_CHARGING`, `INSUFFICIENT_RANGE`)
  - `CAR_DRIVER_REQUEST_CHARGE`
  - `CAR_DRIVER_REQUEST_SWAP_INVALID`
  - `FIXED_BIKE_AUTO_NO_SERVICE`
  - `FIXED_BIKE_AUTO_NEED_CHARGE`
  - `FIXED_BIKE_REQUEST_CHARGE`
  - `FIXED_BIKE_REQUEST_SWAP_INVALID`
  - `SWAP_BIKE_AUTO_NO_SERVICE`
  - `SWAP_BIKE_AUTO_NEED_SERVICE_BOTH_ALLOWED` (`NEED_ENERGY_BOTH_ALLOWED`)
  - `SWAP_BIKE_REQUEST_CHARGE`
  - `SWAP_BIKE_REQUEST_SWAP`
  - `SWAP_BIKE_REQUEST_ANY`
- **OUTPUTS:** `backend/tests/test_scenarios_week2.py`.
- **DEPENDENCIES:** Phases 1–7.
- **FILES EXPECTED TO CHANGE:**
  - `backend/tests/test_scenarios_week2.py` [NEW]
  - `docs/WEEK_2.md` [NEW]
- **IMPLEMENTATION APPROACH:**
  - Load scenario event records dynamically from `dataset_v1/labels/demand_labels.csv` and `trips/trips.csv`.
  - Pass context to `DemandService`.
  - Assert exact match on `need_service`, `request_valid`, `reason_code`, `allowed_service_types`, and `resolved_service_type`.
- **TESTS:** `python -m pytest backend/tests/test_scenarios_week2.py`.
- **SELF-REVIEW CHECKLIST:**
  - [ ] No hardcoded responses.
  - [ ] Swap-capable auto need remains unresolved (NULL).
  - [ ] Swap-capable ANY request remains unresolved (NULL).
- **EXIT GATE:** Phase 8 Exit Gate satisfied.

---

## 4. Final Regression, Verification & Close-out Plan

1. **Week 2 Tests:** All new unit, integration, and scenario tests pass.
2. **Dataset Validation:** `python dataset_v1/validation/validate_dataset.py` passes 152/152 checks and 22/22 scenarios.
3. **Week 1 Regression:** All 41 baseline tests in `backend/tests/` continue to pass.
4. **Git Diff Audit:** Compare `git diff ce3d170` to verify:
   - `dataset_v1/` is completely untouched.
   - No dead code, temporary artifacts, or secret keys.
   - Week 3 leakage is strictly absent.
5. **Infrastructure Note:** Document OSRM/Docker environment status clearly (offline during development vs verified).
6. **Documentation:** Produce `docs/WEEK_2.md` with complete architecture, API reference, ML benchmark, and Week 3 handoff contract.
