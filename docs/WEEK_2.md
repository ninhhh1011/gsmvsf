# Week 2: Energy Service Need / Demand Detection

**Status:** Week 2 Complete  
**Date:** 2026-09-18  
**Baseline Commit:** `ce3d170` (data: freeze VinFast service intent dataset v1.3.1)  
**Milestone:** Week 2 — Demand Detection & EnergyServiceRequest Convergence  

---

## 1. Executive Summary & Objective

Week 2 delivers the **Energy Service Need / Demand Detection** subsystem for the VinFast EV recommendation platform. The subsystem answers four foundational operational questions:

1. **Vehicle Capability:** What energy services (`CHARGING`, `BATTERY_SWAP`) can the current vehicle model physically use? (Deterministic model-level capability resolution; zero ML).
2. **Need Determination (AUTO_DETECTED):** Does the vehicle currently require an energy service based on battery state of charge (SOC), usable capacity, consumption rate, remaining trip distance, and dynamic safety reserve?
3. **Intent Validation (DRIVER_REQUEST):** If the driver explicitly requests a service (`CHARGING`, `BATTERY_SWAP`, `ANY`), is that request supported by the vehicle?
4. **Contract Convergence:** Normalize both `AUTO_DETECTED` and `DRIVER_REQUEST` workflows into one unified `EnergyServiceRequest` contract to serve as the single, immutable input for Week 3 Candidate Search.

### Scope Enforcements & Week Boundaries
- **Zero Week 3 Leakage:** No candidate station lookup, no station eligibility filtering, no routing engine invocation, no ETA calculation.
- **Zero Week 4 Leakage:** No station ranking, no queue calculation, no final recommendation.
- **Preserved Week 1:** All 41 baseline tests for Map Matching and Realtime GPS tracking pass without regression. Week 1 realtime driver location state is consumed seamlessly.
- **Read-Only Dataset V1.3.1:** Canonical dataset files remain byte-for-byte immutable.

---

## 2. Architecture & Data Flow

```
                      ┌─────────────────────────────────┐
                      │    Driver State & Telemetry     │
                      │  (SOC, Range, Trip Distance)    │
                      └────────────────┬────────────────┘
                                       │
           ┌───────────────────────────┴───────────────────────────┐
           │                                                       │
           ▼                                                       ▼
  [AUTO_DETECTED Flow]                                   [DRIVER_REQUEST Flow]
           │                                                       │
           ▼                                                       ▼
┌─────────────────────────┐                             ┌─────────────────────────┐
│   AutoDemandDetector    │                             │  DriverRequestProcessor │
│ (Feasibility Baseline)  │                             │   (Intent Validation)   │
└──────────┬──────────────┘                             └──────────┬──────────────┘
           │                                                       │
           │        ┌──────────────────────────────────┐           │
           └───────►│    VehicleCapabilityResolver     │◄──────────┘
                    │    (19 Model Deterministic Map)  │
                    └─────────────────┬────────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │          DemandService           │
                    │      (Request Convergence)       │
                    └─────────────────┬────────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │       EnergyServiceRequest       │
                    │   (Canonical Contract for W3)    │
                    └──────────────────────────────────┘
```

---

## 3. Vehicle Capability Resolution

Vehicle capability resolution is 100% deterministic and model-based (`VehicleCapabilityResolver`). Category-level shortcuts (such as assuming all motorcycles support swapping) are strictly forbidden.

### Fleet Capability Matrix (19 Models)

| Category | Model Count | Models | Charging Supported | Swap Supported | Interface Class | Allowed Services |
|---|---|---|---|---|---|---|
| **EV_CAR** | 10 | `VF_3`, `VF_5`, `HERIO_GREEN`, `VF_6`, `VF_7_ECO`, `VF_7_PLUS`, `VF_8`, `VF_9`, `VF_E34`, `NERIO_GREEN` | Yes | No | `CCS2_TYPE2` | `[CHARGING]` |
| **EV_MOTORBIKE** (Charge-only) | 5 | `EVO200`, `EVO200_LITE`, `FELIZ_S`, `KLARA_S_2022`, `VENTO_S` | Yes | No | `VINFAST_MOTORCYCLE_CHARGING` | `[CHARGING]` |
| **EV_MOTORBIKE** (Swap-capable) | 4 | `EVO`, `EVO_LITE`, `FELIZ_II`, `VIPER` | Yes | Yes | `VINFAST_MOTORCYCLE_CHARGING`, `VINFAST_SWAP_LFP_1_5_KWH` | `[CHARGING, BATTERY_SWAP]` |

- Unknown models raise `UnknownVehicleModelError`.
- Unknown vehicle IDs raise `UnknownVehicleError`.

---

## 4. AUTO_DETECTED Demand Baseline

The `AutoDemandDetector` implements the physical energy feasibility equation matching Dataset V1.3.1 canonical semantics:

### Formulation
1. **Safety Threshold Check:**
   $$\text{below\_safe} = \text{soc\_pct} \le \text{minimum\_safe\_soc\_pct} + 5.0\%$$
2. **Safety Reserve Calculation:**
   $$\text{safety\_reserve\_km} = \max(1.0\text{ km}, \text{remaining\_trip\_distance\_km} \times 0.15)$$
3. **Range Feasibility Check:**
   $$\text{insufficient\_range} = \text{estimated\_remaining\_range\_km} < (\text{remaining\_trip\_distance\_km} + \text{safety\_reserve\_km})$$
4. **Decision:**
   $$\text{need\_service} = \text{below\_safe} \lor \text{insufficient\_range}$$

### Resolution Rules & Reason Codes
- If $\text{need\_service} = \text{False}$:
  - `resolved_service_type = None`
  - `reason_code = ReasonCode.SUFFICIENT_SOC_RANGE`
- If $\text{need\_service} = \text{True}$:
  - If `below_safe` and `insufficient_range`: `reason_code = ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE`
  - Else if `below_safe`: `reason_code = ReasonCode.LOW_SOC`
  - Else: `reason_code = ReasonCode.INSUFFICIENT_RANGE`
  - **Single-service vehicle (Cars, Charge-only bikes):** `resolved_service_type = ServiceType.CHARGING`
  - **Swap-capable vehicle (EVO, EVO_LITE, FELIZ_II, VIPER):** `resolved_service_type = None` (**UNRESOLVED**). The system does NOT auto-prefer battery swap over charging. Candidate search and ranking in Weeks 3–4 evaluate both services.

---

## 5. DRIVER_REQUEST Intent Resolution

The `DriverRequestProcessor` validates explicit driver requests (`CHARGING`, `BATTERY_SWAP`, `ANY`) against vehicle capabilities:

### Decision Matrix

| Vehicle Category / Model Type | Requested Service | `request_valid` | `allowed_service_types` | `resolved_service_type` | `reason_code` |
|---|---|---|---|---|---|
| **EV_CAR** (All 10 models) | `CHARGING` | True | `[CHARGING]` | `CHARGING` | `VALID_REQUEST` |
| **EV_CAR** (All 10 models) | `BATTERY_SWAP` | False | `[CHARGING]` | `None` | `UNSUPPORTED_SERVICE` |
| **EV_CAR** (All 10 models) | `ANY` | False | `[CHARGING]` | `None` | `UNSUPPORTED_SERVICE` |
| **EV_MOTORBIKE** (Charge-only) | `CHARGING` | True | `[CHARGING]` | `CHARGING` | `VALID_REQUEST` |
| **EV_MOTORBIKE** (Charge-only) | `BATTERY_SWAP` | False | `[CHARGING]` | `None` | `UNSUPPORTED_SERVICE` |
| **EV_MOTORBIKE** (Charge-only) | `ANY` | False | `[CHARGING]` | `None` | `UNSUPPORTED_SERVICE` |
| **EV_MOTORBIKE** (Swap-capable) | `CHARGING` | True | `[CHARGING, BATTERY_SWAP]` | `CHARGING` | `VALID_REQUEST` |
| **EV_MOTORBIKE** (Swap-capable) | `BATTERY_SWAP` | True | `[CHARGING, BATTERY_SWAP]` | `BATTERY_SWAP` | `VALID_REQUEST` |
| **EV_MOTORBIKE** (Swap-capable) | `ANY` | True | `[CHARGING, BATTERY_SWAP]` | `None` (UNRESOLVED) | `VALID_REQUEST` |

- Explicit driver requests always have `need_service = True`.
- Unsupported requests are NOT silently converted.
- Requests with `ANY` on swap-capable vehicles are NOT silently resolved to `CHARGING`.

---

## 6. EnergyServiceRequest Convergence Contract

All requests emit an immutable `EnergyServiceRequest` object:

```python
class EnergyServiceRequest(BaseModel):
    service_request_id: str
    driver_id: Optional[str]
    vehicle_id: str
    trip_id: Optional[str]
    timestamp: datetime
    request_source: RequestSource        # AUTO_DETECTED | DRIVER_REQUEST
    need_service: bool
    requested_service_type: Optional[RequestedServiceType]  # CHARGING | BATTERY_SWAP | ANY | None
    allowed_service_types: list[ServiceType]                # [CHARGING] or [CHARGING, BATTERY_SWAP]
    resolved_service_type: Optional[ServiceType]            # CHARGING | BATTERY_SWAP | None
    request_valid: bool
    reason_code: ReasonCode
    current_soc_pct: Optional[float]
    estimated_remaining_range_km: Optional[float]
    remaining_trip_distance_km: Optional[float]
    safety_reserve_km: Optional[float]
    vehicle_model: Optional[str]
    vehicle_type: Optional[str]
    battery_capacity_kwh: Optional[float]
    usable_capacity_kwh: Optional[float]
    installed_battery_modules: Optional[int]
    swap_supported: bool
    charging_supported: bool
    public_swap_compatible: bool
    latitude: Optional[float]
    longitude: Optional[float]
    road_segment_id: Optional[str]
```

---

## 7. Offline Evaluation & ML Benchmark

Evaluated using `scripts/evaluate_demand_ml.py` on the canonical Dataset V1.3.1 training files:
- Features: `dataset_v1/training/demand_need_service_features.csv` (1,200 rows, strictly AUTO_DETECTED)
- Labels: `dataset_v1/training/demand_need_service_labels.csv` (1,200 rows, 848 positive / 352 negative)
- Split: Trip-level train (840) / validation (176) / test (184) with **zero trip overlap** and **zero target leakage**.

### Performance Results

| Model / Split | Split Samples | Accuracy | Precision (pos) | Recall (pos) | F1 Score (pos) | Confusion Matrix (TP / FP / FN / TN) |
|---|---|---|---|---|---|---|
| **Rule Baseline** (Train) | 840 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 608 / 0 / 0 / 232 |
| **Rule Baseline** (Validation) | 176 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 120 / 0 / 0 / 56 |
| **Rule Baseline** (Test) | 184 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 120 / 0 / 0 / 64 |
| **Logistic Regression** (Train) | 840 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 608 / 0 / 0 / 232 |
| **Logistic Regression** (Validation) | 176 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 120 / 0 / 0 / 56 |
| **Logistic Regression** (Test) | 184 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 120 / 0 / 0 / 64 |

### Runtime Decision: RULE BASELINE SELECTED
1. **Perfect Fidelity:** The deterministic physical feasibility rule achieves 100% precision, recall, and F1 across all splits.
2. **Interpretability & Safety:** Energy decisions are governed directly by battery limits and range reachability, emitting auditable `ReasonCode` values.
3. **Zero Overhead:** Rule evaluation executes in <1 microsecond with zero tensor allocations, zero model inference latency, and zero model drift risk.
4. **Data Generator Nature:** Dataset labels are derived from simulation physics. An ML model would merely approximate the known algebraic equation while introducing edge-case error probability.

---

## 8. REST API Endpoints

Integrated into FastAPI backend under `/api/v1`:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/demand/evaluate` | Evaluates vehicle telemetry for auto-detected demand |
| `POST` | `/api/v1/demand/request` | Processes explicit driver intent (`CHARGING`, `BATTERY_SWAP`, `ANY`) |
| `GET` | `/api/v1/vehicles/{vehicle_id}/capability` | Queries model capability for a fleet vehicle ID |
| `GET` | `/api/v1/vehicles/models/{model_name}/capability` | Queries model capability by model name |
| `POST` | `/api/v1/drivers/{driver_id}/demand/evaluate` | Evaluates demand integrating Week 1 realtime GPS tracking state |

---

## 9. Dataset V1.3.1 Scenario Replay Verification

Replayed 13 canonical scenarios directly against `dataset_v1/labels/demand_labels.csv`:

| Scenario Name | Canonical Event ID | Vehicle / Model | Request Source | Ground Truth Need | Allowed Services | Ground Truth Resolved | Replay Status |
|---|---|---|---|---|---|---|---|
| `CAR_AUTO_NO_SERVICE` | `DE000001` | `V0001` (VF_3) | AUTO_DETECTED | False | `[CHARGING]` | `None` | **PASS** |
| `CAR_AUTO_NEED_CHARGE` | `DE000081` | `V0004` (VF_6) | AUTO_DETECTED | True | `[CHARGING]` | `CHARGING` | **PASS** |
| `CAR_DRIVER_REQUEST_CHARGE` | `DE000002` | `V0001` (VF_3) | DRIVER_REQUEST | True | `[CHARGING]` | `CHARGING` | **PASS** |
| `CAR_DRIVER_REQUEST_SWAP_INVALID` | `DE000003` | `V0001` (VF_3) | DRIVER_REQUEST | True | `[CHARGING]` | `None` (Invalid) | **PASS** |
| `FIXED_BIKE_AUTO_NO_SERVICE` | `DE000913` | `V0036` (VENTO_S) | AUTO_DETECTED | False | `[CHARGING]` | `None` | **PASS** |
| `FIXED_BIKE_AUTO_NEED_CHARGE` | `DE000617` | `V0024` (EVO200) | AUTO_DETECTED | True | `[CHARGING]` | `CHARGING` | **PASS** |
| `FIXED_BIKE_REQUEST_CHARGE` | `DE000618` | `V0024` (EVO200) | DRIVER_REQUEST | True | `[CHARGING]` | `CHARGING` | **PASS** |
| `FIXED_BIKE_REQUEST_SWAP_INVALID` | `DE000619` | `V0024` (EVO200) | DRIVER_REQUEST | True | `[CHARGING]` | `None` (Invalid) | **PASS** |
| `SWAP_BIKE_AUTO_NO_SERVICE` | `DE000377` | `V0015` (EVO) | AUTO_DETECTED | False | `[CHARGING, BATTERY_SWAP]` | `None` | **PASS** |
| `SWAP_BIKE_AUTO_NEED_SERVICE_BOTH_ALLOWED` | `DE000049` | `V0003` (EVO) | AUTO_DETECTED | True | `[CHARGING, BATTERY_SWAP]` | `None` (UNRESOLVED) | **PASS** |
| `SWAP_BIKE_REQUEST_CHARGE` | `DE000050` | `V0003` (EVO) | DRIVER_REQUEST | True | `[CHARGING, BATTERY_SWAP]` | `CHARGING` | **PASS** |
| `SWAP_BIKE_REQUEST_SWAP` | `DE000051` | `V0003` (EVO) | DRIVER_REQUEST | True | `[CHARGING, BATTERY_SWAP]` | `BATTERY_SWAP` | **PASS** |
| `SWAP_BIKE_REQUEST_ANY` | `DE000052` | `V0003` (EVO) | DRIVER_REQUEST | True | `[CHARGING, BATTERY_SWAP]` | `None` (UNRESOLVED) | **PASS** |

---

## 10. Traceability & Acceptance Matrix

| Requirement | Implementation | Evidence | Test | Status | Limitation / Note |
|---|---|---|---|---|---|
| Model-level vehicle capability | `capability.py` | 19 VinFast models, 40 cars, 13 charge bikes, 7 swap bikes | `test_vehicle_capability.py` | **PASS** | Strict model catalog; no category shortcuts |
| AUTO demand feasibility | `auto_detector.py` | Safe SOC + reserve range feasibility equation | `test_auto_detector.py` | **PASS** | Deterministic baseline; handles missing/invalid state |
| Swap bike AUTO leaves unresolved | `auto_detector.py`, `service.py` | `resolved_service_type=None` for swap-capable AUTO | `test_auto_detector.py`, `test_scenarios_week2.py` | **PASS** | Prevents pre-ranking service bias |
| Explicit DRIVER_REQUEST validation | `driver_requester.py` | Matrix validation for CHARGING, BATTERY_SWAP, ANY | `test_driver_requester.py` | **PASS** | Unsupported requests rejected with UNSUPPORTED_SERVICE |
| DRIVER_REQUEST ANY unconstrained | `driver_requester.py` | `resolved_service_type=None` for ANY on swap bike | `test_driver_requester.py`, `test_scenarios_week2.py` | **PASS** | Never collapsed to CHARGING |
| Common EnergyServiceRequest contract | `models.py`, `service.py` | Single schema for AUTO and DRIVER requests | `test_demand_models.py`, `test_demand_service.py` | **PASS** | Extra station/ranking fields strictly forbidden |
| Offline ML evaluation & comparison | `scripts/evaluate_demand_ml.py` | Canonical split, zero leakage, 100% metrics | Benchmark script run | **PASS** | Documented why Rule Baseline is selected |
| Week 1 realtime state integration | `demand.py` | Consumes `DriverStateStore` position/segment | `test_demand_api.py` | **PASS** | In-memory store; Week 1 untouched |
| Dataset V1.3.1 validation | `validate_dataset.py` | 152 checks PASS, 22 scenario checks PASS | `validate_dataset.py` | **PASS** | Dataset remains byte-for-byte read-only |
| Week 1 Regression | Pytest test suite | 41 baseline tests PASS | `python -m pytest backend/tests` | **PASS** | 0 regressions |

---

## 11. Known Limitations & Week 3 Handoff Contract

### Known Limitations
1. **Dynamic Battery Degradation:** Usable capacity uses nominal catalog values; state of health (SOH) degradation is not yet simulated in Dataset V1.3.1.
2. **In-Memory Driver State:** Week 1 realtime driver state is stored in memory (`DriverStateStore`).
3. **Local Docker/OSRM Environment:** Docker Desktop was offline on the host machine during development (503 on readiness check). Code and unit tests pass 100%.

### Week 3 Handoff Contract
Week 3 (Candidate Search & Routing) can consume `EnergyServiceRequest`:
- `service_request_id`: Unique request identifier.
- `driver_id`: Driver identifier.
- `vehicle_id`: Vehicle identifier.
- `allowed_service_types`: Determines station service compatibility.
- `resolved_service_type`:
  - If concrete (`CHARGING` or `BATTERY_SWAP`), candidate search only generates candidates for that specific service.
  - If `None` (unresolved swap bike AUTO or driver `ANY`), candidate search generates candidates for **both** `CHARGING` and `BATTERY_SWAP`.
- `latitude` and `longitude`: Current origin position for routing.
- `current_soc_pct` and `estimated_remaining_range_km`: Range feasibility filter for reaching candidate stations.
