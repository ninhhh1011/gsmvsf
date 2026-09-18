# Dataset V1.3.1 — Driver Charging / Battery Swap Recommendation

## Overview

Dataset V1.3.1 is the canonical offline dataset for the 6-week EV Recommendation platform. It provides linked operational data, ground-truth labels, vehicle capabilities, and evaluation scenarios covering map matching, demand detection, candidate search, station ranking, and real-time event replay.

## V1.3.1 Key Semantic Corrections

Three semantic corrections were finalized in V1.3.1 over earlier V1.2/V1.3 baselines:

### 1. AUTO_DETECTED Service Resolution (No Forced Swap)
- When `need_service = True` for a vehicle supporting both charging and swap (e.g. EVO, EVO_LITE, FELIZ_II, VIPER), `resolved_service_type` is **NULL** (unresolved).
- The system does NOT auto-force `BATTERY_SWAP`. Both `CHARGING` and `BATTERY_SWAP` candidates are generated and evaluated downstream in Candidate Search and Ranking (Weeks 3–4).
- For charge-only vehicles (all cars and charge-only bikes), `resolved_service_type = 'CHARGING'`.
- For `need_service = False`, `resolved_service_type` is **NULL** and `service_type` is **NULL** (note: `NONE` is not an energy service type).

### 2. DRIVER_REQUEST(ANY) Semantics (No Forced Charge)
- When a driver explicitly requests `ANY` service on a swap-capable vehicle, `service_type = 'ANY'` and `resolved_service_type = NULL`.
- The request is NOT silently collapsed to `CHARGING`. Both services remain valid candidates.
- Explicit unsupported requests (e.g. car driver requesting `BATTERY_SWAP`) have `request_valid = False` and `reason_code = 'UNSUPPORTED_SERVICE'`.

### 3. Canonical Training Data Contract (Zero Contamination)
- **Canonical ML training files:**
  - `training/demand_need_service_features.csv` (1,200 rows)
  - `training/demand_need_service_labels.csv` (1,200 rows)
- Contains **strictly AUTO_DETECTED** telemetry snapshots. Zero `DRIVER_REQUEST` contamination.
- Clean feature/label separation: no `need_service`, `resolved_service_type`, or `service_type` columns inside the features file.
- **Class balance:** 848 positive (70.7%) / 352 negative (29.3%).
- **Training imbalance note:** The 70.7% positive rate reflects telemetry sampling where vehicles approaching low SOC are more frequently evaluated. ML models should apply appropriate class weighting, loss adjustment, or decision threshold tuning when optimizing for balanced detection.
- **Trip-safe split:** 840 train (105 trips) / 176 validation (22 trips) / 184 test (23 trips). Zero trip leakage across splits.
- **Legacy file status:** `training/demand_features.csv` is **SUPERSEDED / DERIVED REFERENCE (NOT CANONICAL ML TRAINING INPUT)**. It contains both AUTO_DETECTED and DRIVER_REQUEST events with embedded labels and is maintained solely for backward compatibility.

## Model-Level Vehicle Capabilities

Vehicle capabilities are defined at the individual model level in `vehicles/vehicle_model_catalog.csv`:

- **EV_CAR (40 vehicles, 10 models):** VF_3, VF_5, VF_6, VF_7_ECO, VF_7_PLUS, VF_8, VF_9, VF_E34, NERIO_GREEN.
  - Capability: `charging_supported = True`, `swap_supported = False` (CHARGING only).
  - Interface: `CCS2_TYPE2`.
- **EV_MOTORBIKE — Charge-only (13 vehicles, 5 models):** EVO200, EVO200_LITE, FELIZ_S, KLARA_S_2022, VENTO_S.
  - Capability: `charging_supported = True`, `swap_supported = False` (CHARGING only).
  - Interface: `VINFAST_MOTORCYCLE_CHARGING`.
- **EV_MOTORBIKE — Swap-capable (7 vehicles, 4 models):** EVO, EVO_LITE, FELIZ_II, VIPER.
  - Capability: `charging_supported = True`, `swap_supported = True` (CHARGING + BATTERY_SWAP).
  - Interface: `VINFAST_MOTORCYCLE_CHARGING` and `VINFAST_SWAP_LFP_1_5_KWH`.
  - Modules: Removable battery modules (1 or 2 modules × 1.5 kWh).
- **Invariants:** No vehicle in the fleet is swap-only (`swap_supported = True` and `charging_supported = False` is 0).

## Downstream Contracts

### Candidate Search
- `labels/candidate_labels.csv` contains 31,440 candidate evaluations (7,474 ELIGIBLE, 23,966 ineligible).
- Candidates are evaluated per `(event_id, station_id, service_type)` tuple.
- Unresolved requests generate candidates for all allowed service types.

### Ranking
- `training/ranking_reference.csv` contains 3,439 candidate rows across 553 event groups.
- Every ranking candidate is strictly **ELIGIBLE** (0 non-eligible candidates in ranking).
- Group sizes range from 1 to 8 candidates (478 LTR groups with size >= 2; 75 single-candidate groups).

### Recommendation
- `labels/recommendation_labels.csv` contains 848 rows (553 `has_recommendation = True`, 295 `has_recommendation = False`).
- Every recommended station references an **ELIGIBLE** candidate.
- Unsupported explicit requests and `need_service = False` snapshots have no recommendation.

## Map Source Status

- **MAP STATUS — APPROVED:** `hanoi-patched.osm.pbf` is the primary OSRM map.
- Contains `motorcar=no` for OSM way 881947000 (Cầu Thanh Trì).
- `hanoi-baseline.osm.pbf` is retained as byte-for-byte reference. Both raw PBFs remain unmodified.
- PBF integrity SHA-256: **PASS**.

## Key Dataset Counts (V1.3.1)

| Table | Records | Description |
|---|---:|---|
| road_nodes | 339,441 | Hanoi road network vertices |
| road_segments | 701,407 | Directed road edges with OSM tags |
| drivers | 60 | Driver profiles |
| vehicles | 60 | Fleet vehicles with model catalog link |
| trips | 150 | Scheduled driver trips |
| true_trajectory_points | 68,664 | Ground-truth simulation positions |
| gps_observations | 65,847 | Realistic noisy/sparse GPS observations |
| soc_history | 68,664 | Battery SOC telemetry (0.0% – 94.7%) |
| stations | 30 | Charging and battery swap stations |
| station_status | 3,270 | Service-specific slot and battery availability |
| queue_status | 3,270 | Service-specific queues and wait times |
| traffic_snapshots | 883,597 | Dynamic traffic speed and delay factors |
| realtime_events | 109,193 | Deterministic event replay stream |
| map_matching_candidates | 27,042 | Candidate road segments for GPS observations |
| demand_labels | 3,824 | Full demand events (1,200 AUTO + 2,624 DRIVER) |
| demand_need_service_features | 1,200 | Canonical ML features (AUTO_DETECTED only) |
| demand_need_service_labels | 1,200 | Canonical ML labels (848 pos / 352 neg) |
| candidate_labels | 31,440 | Multi-service candidate eligibility evaluations |
| ranking_reference | 3,439 | Pre-computed ranking rows across 553 groups |
| recommendation_labels | 848 | Decision recommendation targets |
| scenario_coverage | 21 | Independent semantic scenario assertions |

## Scenario Assertions (21/21 PASS)

All 21 semantic scenario assertions pass independent validation, including:
- `FARTHER_BUT_FASTER`: Validated on event `DE001858` / trip `T0073`. Station S028 is 542.9 m farther than S026 by network distance, but offers a 13.472 min total ETA improvement due to queue differences.
- `NEED_ENERGY_BOTH_ALLOWED`: Validated on swap-capable vehicle in trip `T0110` with both services allowed and neither forced.
- `NORMAL_TRIP` & `NO_SERVICE_NEEDED`: Validated on trips `T0001` and `T0002` with `need_service = False` and null energy service type.

## Validation

To run full validation:
```bash
python dataset_v1/validation/validate_dataset.py
```
Result: **152 / 152 checks PASS, 21 / 21 scenarios PASS**.
