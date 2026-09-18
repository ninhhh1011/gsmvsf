# Dataset Version History

## V1.3.1 — Service Intent Semantic Correction

**Date:** 2026-09-18

### Summary

Three semantic bugs in V1.3's service intent system were identified and corrected.

### Bug 1: AUTO_DETECTED Bias (Swap-Capable Vehicles)

**Problem:** When need_service=True for a swap-capable vehicle, the system auto-assigned
resolved_service_type=BATTERY_SWAP, effectively choosing a service before candidate
generation.

**Fix:** resolved_service_type=NULL for swap-capable vehicles with need_service=True.
Both CHARGING and BATTERY_SWAP candidates are now generated, letting ranking (Weeks 3-4)
select the best service based on station availability, queue, and route.

### Bug 2: DRIVER_REQUEST(ANY) Silent Resolution

**Problem:** A DRIVER_REQUEST with requested_service_type=ANY was silently resolved to
CHARGING, losing the "no preference" signal.

**Fix:** DRIVER_REQUEST(ANY) now has service_type='ANY' and resolved_service_type=NULL.
Both services remain as candidates. Only explicit CHARGING/BATTERY_SWAP requests are
resolved to their specific type.

### Bug 3: Training Data Contamination

**Problem:** The need_service prediction training set included DRIVER_REQUEST rows,
which represent explicit user intent rather than automatically-detected state. This
contaminates the ML task of predicting need from vehicle telemetry alone.

**Fix:** demand_need_service_features.csv and demand_need_service_labels.csv now
contain only AUTO_DETECTED rows (1200 samples). Class distribution: 848 positive /
352 negative (70.7% positive).

**Training imbalance note:** The 70.7% positive / 29.3% negative class balance reflects
telemetry sampling where vehicles approaching low SOC are more frequently evaluated.
Downstream models should consider loss weighting or decision threshold adjustments.

**Legacy training file:** `training/demand_features.csv` is marked as SUPERSEDED / DERIVED REFERENCE
(NOT CANONICAL ML TRAINING INPUT).

### Files Regenerated

- labels/demand_labels.csv — corrected resolved_service_type
- labels/energy_service_requests.csv — same correction
- training/demand_need_service_features.csv — AUTO_DETECTED rows only
- training/demand_need_service_labels.csv — AUTO_DETECTED rows only
- training/demand_features.csv — added resolved_service_type column (superseded reference)
- labels/candidate_labels.csv — both CHARGING+SWAP candidates for unresolved events
- training/ranking_reference.csv — regenerated with new candidates
- labels/recommendation_labels.csv — regenerated
- scenarios/scenario_coverage.csv — NEED_SWAP renamed to NEED_ENERGY_BOTH_ALLOWED; event IDs updated (DE001858 for FARTHER_BUT_FASTER)

### Files Preserved

vehicles.csv, vehicle_model_catalog.csv, battery/soc_history.csv.gz, stations/,
road/, GPS/, trajectories/, labels/map_matching_labels.csv.gz, map/raw/

### Semantics Reference

| request_source | need_service | swap_capable | resolved_service_type | service_type | Notes |
|---|---|---|---|---|---|
| AUTO_DETECTED | False | Any | NULL | NULL | NONE is not an energy service type |
| AUTO_DETECTED | True | Charge-only | CHARGING | CHARGING | Resolved to single supported service |
| AUTO_DETECTED | True | Swap-capable | NULL | NULL | Unresolved: both services evaluated |
| DRIVER_REQUEST | True | Any | CHARGING | CHARGING | Explicit request |
| DRIVER_REQUEST | True | Swap-capable | BATTERY_SWAP | BATTERY_SWAP | Explicit request |
| DRIVER_REQUEST | True | Charge-only | NULL | BATTERY_SWAP | Invalid (UNSUPPORTED_SERVICE) |
| DRIVER_REQUEST | True | Swap-capable | NULL | ANY | No preference: both services evaluated |

---

## V1.3 — VinFast Model-Level Capability Correction

**Date:** 2026-09-18

### Problem

VinFast motorcycles were inconsistently assigned battery swap capability. The category-level
assumption that all motorcycles support swap was incorrect.

### Fix

Vehicle capability is now determined at the model level from vehicle_model_catalog.csv.

### Fleet Distribution (V1.3 / V1.3.1)

| Category | Count | Models | Swap Support |
|---|---|---|---|
| EV_CAR | 40 | 10 (VF5-VF34) | No |
| EV_MOTORBIKE (charge-only) | 13 | EVO200, EVO200_LITE, FELIZ_S, KLARA_S_2022, VENTO_S | No |
| EV_MOTORBIKE (swap-capable) | 7 | EVO, EVO_LITE, FELIZ_II, VIPER | Yes |

---

## V1.2 — Baseline Multi-Service Station and Queue Semantics

Full dataset with service-specific station state, queue wait times, and real-time
replay event stream. See DATA_DICTIONARY.md for schema documentation.
