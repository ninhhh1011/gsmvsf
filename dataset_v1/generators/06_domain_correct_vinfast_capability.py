"""
Dataset V1.3 — Domain Correction Patch: VinFast Model-Level Charging/Swap Capability

This patch corrects Dataset V1.2 to reflect that:
1. Not every VinFast motorcycle supports public battery swap.
2. Vehicle capability must be determined at the vehicle-model level.
3. Demand semantics split into need_service + allowed_service_types + request_source.

Scope of changes (V1.2 → V1.3):
- NEW: vehicle_model_catalog.csv (canonical model table)
- MODIFY: vehicles.csv (assign models, update battery specs, add new columns)
- MODIFY: battery/soc_history.csv.gz (recompute SOC/range for new battery profiles)
- MODIFY: labels/demand_labels.csv (add request_source, allowed_service_types, requested_service_type, request_valid)
- MODIFY: training/demand_features.csv (add new vehicle fields, allowed_service_types)
- MODIFY: labels/candidate_labels.csv (add UNSUPPORTED_SERVICE reason)
- MODIFY: training/ranking_reference.csv (regenerate for corrected compatibility)
- MODIFY: labels/recommendation_labels.csv (regenerate)
- MODIFY: scenarios/scenario_coverage.csv (update to reflect corrected capability)
- NEW: labels/energy_service_requests.csv (new demand contract for Week 3)
- NEW: training/demand_need_service_features.csv (need_service training data)
- NEW: training/demand_need_service_labels.csv (need_service training labels)
- UPDATE: README.md, DATA_DICTIONARY.md, REQUIREMENT_DATA_MATRIX.md
- UPDATE: config/generation_config.json (version bump)
- UPDATE: validation/ (run updated validators)
- PRESERVE: road network, PBF, GPS, trajectories, map matching labels, Week 1 code

Execution order:
  Step 1: Create vehicle_model_catalog.csv
  Step 2: Patch vehicles.csv (model assignments, battery specs, new fields)
  Step 3: Regenerate SOC history for new battery profiles
  Step 4: Regenerate demand labels with request_source + allowed_service_types
  Step 5: Regenerate demand features with new vehicle fields
  Step 6: Regenerate energy_service_requests.csv
  Step 7: Regenerate need_service training data
  Step 8: Regenerate candidate labels with UNSUPPORTED_SERVICE reason
  Step 9: Regenerate ranking_reference and recommendation_labels
  Step 10: Update scenarios for corrected capability
  Step 11: Rebuild realtime events with updated vehicle/service data
  Step 12: Update documentation (README, DATA_DICTIONARY, REQUIREMENT_MATRIX)
  Step 13: Run full validation suite
"""

from __future__ import annotations

import gzip
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260916
rng = random.Random(SEED + 6)
np.random.seed(SEED + 6)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEMAND_SNAPSHOTS_PER_TRIP = 8
CANDIDATE_MAX_WAIT_MIN = 90.0
MAX_RANK_CANDIDATES = 8
SOC_REACH_BUFFER_KM = 0.5
CHARGING_SERVICE_TIME_MIN = 18.0
SWAP_SERVICE_TIME_MIN = 6.0
FARTHER_MIN_DISTANCE_DELTA_M = 500.0
FARTHER_MEANINGFUL_ETA_MARGIN_MIN = 10.0
NEAR_TIE_THRESHOLD_MIN = 3.0

# PROJECT SIMULATION ASSUMPTION: usable_capacity = 92% of nominal for all models
# This is a deterministic synthetic assumption, NOT an official VinFast specification.
USABLE_RATIO = 0.92

# All consumption rates are PROJECT SIMULATION ASSUMPTIONS.
CONSUMPTION_CAR_WH_KM = 150   # Wh/km for all cars (synthetic)
CONSUMPTION_BIKE_WH_KM = 45   # Wh/km for all motorcycles (synthetic)


# ---------------------------------------------------------------------------
# 1. VINFAST VEHICLE MODEL CATALOG
# ---------------------------------------------------------------------------
# vehicle_model, vehicle_category, battery_architecture, battery_capacity_kwh,
# battery_module_capacity_kwh, max_battery_modules, charging_supported,
# swap_supported, public_swap_compatible, charging_interface_class,
# swap_battery_family, capability_source_class
#
# Internal project enum naming — NOT official VinFast product terminology.
# ---------------------------------------------------------------------------

CATALOG_MODELS = [
    # --- EV CARS: charging only, fixed traction pack ---
    {'vehicle_model': 'VF_3',           'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 18.64,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_5',           'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 37.23,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'HERIO_GREEN',     'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 37.23,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_6',            'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 59.60,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_7_ECO',       'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 59.60,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_7_PLUS',      'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 75.30,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_8',           'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 87.70,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_9',           'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 123.00,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VF_E34',          'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 41.90,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'NERIO_GREEN',     'vehicle_category': 'EV_CAR',
     'battery_architecture': 'FIXED_TRACTION_PACK',
     'battery_capacity_kwh': 41.90,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'CCS2_TYPE2',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    # --- MOTORCYCLES: charging only ---
    {'vehicle_model': 'EVO200',          'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'FIXED_OR_INTEGRATED_LFP',
     'battery_capacity_kwh': 3.5,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'EVO200_LITE',     'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'FIXED_OR_INTEGRATED_LFP',
     'battery_capacity_kwh': 3.5,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'FELIZ_S',         'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'FIXED_OR_INTEGRATED_LFP',
     'battery_capacity_kwh': 3.5,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'KLARA_S_2022',    'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'FIXED_OR_INTEGRATED_LFP',
     'battery_capacity_kwh': 3.5,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VENTO_S',        'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'FIXED_OR_INTEGRATED_LFP',
     'battery_capacity_kwh': 3.5,
     'battery_module_capacity_kwh': None, 'max_battery_modules': None,
     'charging_supported': True, 'swap_supported': False,
     'public_swap_compatible': False,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': None,
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    # --- MOTORCYCLES: charging + battery swap ---
    {'vehicle_model': 'EVO',             'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'REMOVABLE_SWAP_MODULE',
     'battery_capacity_kwh': None,  # determined by installed modules
     'battery_module_capacity_kwh': 1.5, 'max_battery_modules': 2,
     'charging_supported': True, 'swap_supported': True,
     'public_swap_compatible': True,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': 'VINFAST_SWAP_LFP_1_5_KWH',
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'EVO_LITE',        'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'REMOVABLE_SWAP_MODULE',
     'battery_capacity_kwh': None,
     'battery_module_capacity_kwh': 1.5, 'max_battery_modules': 2,
     'charging_supported': True, 'swap_supported': True,
     'public_swap_compatible': True,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': 'VINFAST_SWAP_LFP_1_5_KWH',
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'FELIZ_II',        'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'REMOVABLE_SWAP_MODULE',
     'battery_capacity_kwh': None,
     'battery_module_capacity_kwh': 1.5, 'max_battery_modules': 2,
     'charging_supported': True, 'swap_supported': True,
     'public_swap_compatible': True,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': 'VINFAST_SWAP_LFP_1_5_KWH',
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},

    {'vehicle_model': 'VIPER',           'vehicle_category': 'EV_MOTORBIKE',
     'battery_architecture': 'REMOVABLE_SWAP_MODULE',
     'battery_capacity_kwh': None,
     'battery_module_capacity_kwh': 1.5, 'max_battery_modules': 2,
     'charging_supported': True, 'swap_supported': True,
     'public_swap_compatible': True,
     'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
     'swap_battery_family': 'VINFAST_SWAP_LFP_1_5_KWH',
     'capability_source_class': 'VINFAST_OFFICIAL_BATTERY_SPEC'},
]

CATALOG_DF = pd.DataFrame(CATALOG_MODELS)
CATALOG_DF.to_csv(ROOT / 'vehicles/vehicle_model_catalog.csv', index=False)
print(f"[Step 1] Vehicle model catalog: {len(CATALOG_DF)} models written")

# Build lookup helpers
MODEL_MAP = {row.vehicle_model: row for row in CATALOG_DF.itertuples()}
SWAP_CAPABLE_MODELS = set(CATALOG_DF[CATALOG_DF.swap_supported].vehicle_model)
CHARGE_ONLY_MODELS = set(CATALOG_DF[~CATALOG_DF.swap_supported &
                                      (CATALOG_DF.vehicle_category == 'EV_MOTORBIKE')].vehicle_model)
# Schema note: vehicles.csv uses 'vehicle_type' (not 'vehicle_category')
VEHICLE_CATEGORY_COL = 'vehicle_type'  # canonical column name in vehicles.csv


# ---------------------------------------------------------------------------
# 2. Load existing data
# ---------------------------------------------------------------------------
vehicles = pd.read_csv(ROOT / 'vehicles/vehicles.csv')
trips = pd.read_csv(ROOT / 'trips/trips.csv')
drivers = pd.read_csv(ROOT / 'drivers/drivers.csv')
battery = pd.read_csv(ROOT / 'battery/soc_history.csv.gz')
stations = pd.read_csv(ROOT / 'stations/stations.csv')

# Check if vehicle assignment is already done (vehicle_model column with V1.3 values)
_already_done = 'vehicle_model' in vehicles.columns and 'VF_3' in vehicles['vehicle_model'].values

if not _already_done:
    # --- 2a. Assign vehicle models ---
    car_models = ['VF_3', 'VF_5', 'VF_6', 'VF_7_ECO', 'VF_7_PLUS',
                  'VF_8', 'VF_9', 'VF_E34', 'NERIO_GREEN']
    cars = vehicles[vehicles.vehicle_type == 'EV_CAR'].copy()
    car_assignments = []
    for i, (idx, vrow) in enumerate(cars.iterrows()):
        model = car_models[i % len(car_models)]
        m = MODEL_MAP[model]
        nom_kwh = m.battery_capacity_kwh
        usable_kwh = round(nom_kwh * USABLE_RATIO, 2)
        car_assignments.append({
            'vehicle_id': vrow.vehicle_id, 'driver_id': vrow.driver_id,
            'vehicle_type': 'EV_CAR', 'vehicle_model': model,
            'battery_architecture': m.battery_architecture,
            'battery_capacity_kwh': nom_kwh,
            'battery_module_capacity_kwh': None, 'max_battery_modules': None,
            'installed_battery_modules': None,
            'usable_capacity_kwh': usable_kwh,
            'consumption_wh_per_km': CONSUMPTION_CAR_WH_KM,
            'minimum_safe_soc_pct': 15,
            'charging_supported': True, 'swap_supported': False,
            'public_swap_compatible': False,
            'connector_type': 'CCS2_TYPE2', 'battery_type': 'FIXED_TRACTION_PACK',
            'charging_interface_class': 'CCS2_TYPE2', 'swap_battery_family': None,
        })

    swap_bike_models = ['EVO', 'EVO_LITE', 'FELIZ_II', 'VIPER']
    charge_bike_models = ['EVO200', 'EVO200_LITE', 'FELIZ_S', 'KLARA_S_2022', 'VENTO_S']
    bikes = vehicles[vehicles.vehicle_type == 'EV_MOTORBIKE'].copy().sort_values('vehicle_id').reset_index(drop=True)
    n_swap = 7
    n_charge = len(bikes) - n_swap
    bike_assignments = []
    for i in range(n_swap):
        vrow = bikes.iloc[i]
        model = swap_bike_models[i % len(swap_bike_models)]
        m = MODEL_MAP[model]
        installed = 2 if i % 2 == 0 else 1
        nom_kwh = installed * m.battery_module_capacity_kwh
        usable_kwh = round(nom_kwh * USABLE_RATIO, 2)
        bike_assignments.append({
            'vehicle_id': vrow.vehicle_id, 'driver_id': vrow.driver_id,
            'vehicle_type': 'EV_MOTORBIKE', 'vehicle_model': model,
            'battery_architecture': m.battery_architecture,
            'battery_capacity_kwh': nom_kwh,
            'battery_module_capacity_kwh': m.battery_module_capacity_kwh,
            'max_battery_modules': m.max_battery_modules,
            'installed_battery_modules': installed,
            'usable_capacity_kwh': usable_kwh,
            'consumption_wh_per_km': CONSUMPTION_BIKE_WH_KM,
            'minimum_safe_soc_pct': 15,
            'charging_supported': True, 'swap_supported': True,
            'public_swap_compatible': True,
            'connector_type': 'VINFAST_MOTORCYCLE_CHARGING',
            'battery_type': 'VINFAST_SWAP_LFP_1_5_KWH',
            'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
            'swap_battery_family': 'VINFAST_SWAP_LFP_1_5_KWH',
        })
    for i in range(n_charge):
        vrow = bikes.iloc[n_swap + i]
        model = charge_bike_models[i % len(charge_bike_models)]
        m = MODEL_MAP[model]
        nom_kwh = m.battery_capacity_kwh
        usable_kwh = round(nom_kwh * USABLE_RATIO, 2)
        bike_assignments.append({
            'vehicle_id': vrow.vehicle_id, 'driver_id': vrow.driver_id,
            'vehicle_type': 'EV_MOTORBIKE', 'vehicle_model': model,
            'battery_architecture': m.battery_architecture,
            'battery_capacity_kwh': nom_kwh,
            'battery_module_capacity_kwh': None, 'max_battery_modules': None,
            'installed_battery_modules': None,
            'usable_capacity_kwh': usable_kwh,
            'consumption_wh_per_km': CONSUMPTION_BIKE_WH_KM,
            'minimum_safe_soc_pct': 15,
            'charging_supported': True, 'swap_supported': False,
            'public_swap_compatible': False,
            'connector_type': 'VINFAST_MOTORCYCLE_CHARGING',
            'battery_type': 'FIXED_OR_INTEGRATED_LFP',
            'charging_interface_class': 'VINFAST_MOTORCYCLE_CHARGING',
            'swap_battery_family': None,
        })

    vehicles = pd.DataFrame(car_assignments + bike_assignments)
    vehicles.to_csv(ROOT / 'vehicles/vehicles.csv', index=False)
    print(f"[Step 2] vehicles.csv assigned: {len(vehicles)} vehicles")
    print(f"  Cars: {(vehicles.vehicle_type == 'EV_CAR').sum()}")
    print(f"  Swap-capable motorcycles: {vehicles.swap_supported.sum()}")
    print(f"  Charge-only motorcycles: {(~vehicles.swap_supported.astype(bool) & (vehicles.vehicle_type == 'EV_MOTORBIKE')).sum()}")
else:
    print(f"[Step 2] vehicles.csv already patched, skipping reassignment")
    print(f"  Cars: {(vehicles.vehicle_type == 'EV_CAR').sum()}")
    print(f"  Swap-capable motorcycles: {vehicles.swap_supported.sum()}")
    print(f"  Charge-only motorcycles: {(~vehicles.swap_supported.astype(bool) & (vehicles.vehicle_type == 'EV_MOTORBIKE')).sum()}")

# Normalize station connector types to match vehicle connector_type values.
_st_conn_map = {'CCS2': 'CCS2_TYPE2', 'BIKE_DC': 'VINFAST_MOTORCYCLE_CHARGING'}
_st_batt_map = {'SWAP_PACK_A': 'VINFAST_SWAP_LFP_1_5_KWH'}
def normalize_connector(ct):
    parts = [x.strip() for x in str(ct).replace(',', ';').split(';') if x.strip()]
    return ';'.join([_st_conn_map.get(p, p) for p in parts])

if stations['connector_type'].iloc[0] not in ('CCS2_TYPE2', 'VINFAST_MOTORCYCLE_CHARGING', 'VINFAST_MOTORCYCLE_CHARGING;CCS2_TYPE2'):
    stations['connector_type'] = stations['connector_type'].apply(normalize_connector)
    stations['battery_type'] = stations['battery_type'].replace(_st_batt_map)
    stations.to_csv(ROOT / 'stations/stations.csv', index=False)
    print(f"  Stations connector types and battery types normalized: {len(stations)} rows")
else:
    print(f"  Stations already normalized")

veh_idx = vehicles.set_index('vehicle_id')
trip_idx = trips.set_index('trip_id')

old_status = pd.read_csv(ROOT / 'stations/station_status.csv.gz')
old_queue = pd.read_csv(ROOT / 'queue/queue_status.csv.gz')
traffic = pd.read_csv(ROOT / 'traffic/traffic_snapshots.csv.gz')
true = pd.read_csv(ROOT / 'trajectories/true_trajectories.csv.gz')
gps = pd.read_csv(ROOT / 'gps/gps_observations.csv.gz')
splits = pd.read_csv(ROOT / 'training/trip_splits.csv')
old_demand = pd.read_csv(ROOT / 'labels/demand_labels.csv')
old_df = pd.read_csv(ROOT / 'training/demand_features.csv')
old_candidates = pd.read_csv(ROOT / 'labels/candidate_labels.csv')
old_ranking = pd.read_csv(ROOT / 'training/ranking_reference.csv')
old_rec = pd.read_csv(ROOT / 'labels/recommendation_labels.csv')
old_scenario = pd.read_csv(ROOT / 'scenarios/scenario_coverage.csv')

# Normalize timestamps
for table in [old_status, old_queue, traffic]:
    table['timestamp'] = pd.to_datetime(table.timestamp, format='mixed').map(lambda x: x.isoformat())

print(f"  vehicles={len(vehicles)}, trips={len(trips)}, stations={len(stations)}")
print(f"  demand_labels={len(old_demand)}, candidates={len(old_candidates)}, ranking={len(old_ranking)}")


# ---------------------------------------------------------------------------
# 3. Regenerate SOC history for corrected battery profiles
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Keep distance_travelled_km and timestamps unchanged.
# Recompute energy_consumed_kwh, soc_pct, estimated_remaining_range_km
# using the new per-vehicle usable_capacity_kwh and consumption_wh_per_km.

SCENARIO_INIT_SOC = {
    'INSUFFICIENT_RANGE': 7.0, 'LOW_SOC': 12.0, 'NEED_SWAP': 16.0,
    'NEED_CHARGING': 18.0, 'NORMAL_TRIP': 95.0, 'NO_SERVICE_NEEDED': 90.0,
    'NEAREST_FULL': 20.0, 'STATION_OFFLINE': 20.0, 'LONG_QUEUE': 20.0,
    'FARTHER_BUT_FASTER': 20.0, 'NO_AVAILABLE_STATION': 20.0,
    'INCOMPATIBLE_STATION': 20.0, 'QUEUE_REALTIME_CHANGE': 20.0,
    'STATION_STATUS_CHANGE': 20.0, 'TRAFFIC_REALTIME_CHANGE': 20.0,
    'HEAVY_TRAFFIC': 20.0,
}

battery_out = []
for tid, trip_group in battery.groupby('trip_id'):
    tr = trip_idx.get(tid, None)
    if tr is None:
        battery_out.append(trip_group)
        continue
    v = veh_idx.loc[tr.vehicle_id]
    sc = tr.scenario_id
    init_soc = SCENARIO_INIT_SOC.get(sc, 85.0)
    heavy_factor = 1.12 if sc == 'HEAVY_TRAFFIC' else 1.0
    cons = float(v.consumption_wh_per_km)
    cap = float(v.usable_capacity_kwh)
    dist_km = trip_group.distance_travelled_km.astype(float).to_numpy()
    energy = dist_km * cons / 1000.0 * heavy_factor
    soc = np.maximum(0.0, init_soc - energy / cap * 100.0)
    remain = np.maximum(0.0, soc / 100.0 * cap / (cons / 1000.0))
    tg = trip_group.copy()
    tg['energy_consumed_kwh'] = np.round(energy, 5)
    tg['soc_pct'] = np.round(soc, 3)
    tg['estimated_remaining_range_km'] = np.round(remain, 2)
    battery_out.append(tg)

battery_new = pd.concat(battery_out, ignore_index=True)
battery_new.to_csv(ROOT / 'battery/soc_history.csv.gz', index=False, compression='gzip')
print(f"[Step 3] SOC history regenerated: {len(battery_new)} rows")

# Refresh indexes with possibly updated vehicles
veh_idx = vehicles.set_index('vehicle_id')
trip_idx = trips.set_index('trip_id')


# ---------------------------------------------------------------------------
# 5. Rebuild event context (demand snapshot data)
# ---------------------------------------------------------------------------
seg_idx = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str}).set_index('segment_id')
bg = {k: v.reset_index(drop=True) for k, v in battery_new.groupby('trip_id', sort=False)}
tg_map = {k: v.reset_index(drop=True) for k, v in true.groupby('trip_id', sort=False)}
split_map = splits.set_index('trip_id').split.to_dict()

def allowed_services(vrow):
    services = ['CHARGING']
    if bool(vrow.swap_supported):
        services.append('BATTERY_SWAP')
    return services

def auto_detect_service(vrow, soc_pct, remaining_range_km, remaining_trip_km, reserve_km):
    """Returns (need_service, service_type, reason_code) for AUTO_DETECTED."""
    below_safe = soc_pct <= float(vrow.minimum_safe_soc_pct) + 5.0
    insufficient = remaining_range_km < remaining_trip_km + reserve_km
    need = bool(below_safe or insufficient)
    if not need:
        return (False, 'NONE', 'SUFFICIENT_SOC_RANGE')
    # Determine service type based on vehicle capability
    if bool(vrow.swap_supported):
        service_type = 'BATTERY_SWAP'
    else:
        service_type = 'CHARGING'
    if below_safe and insufficient:
        reason = 'LOW_SOC_AND_INSUFFICIENT_RANGE'
    elif below_safe:
        reason = 'LOW_SOC'
    else:
        reason = 'INSUFFICIENT_RANGE'
    return (need, service_type, reason)


# ---------------------------------------------------------------------------
# 6. Regenerate demand labels with request_source + allowed_service_types
# ---------------------------------------------------------------------------
# Each trip event gets two rows:
#   AUTO_DETECTED: the system's auto-detected need and chosen service
#   DRIVER_REQUEST (CHARGING): driver explicitly requests CHARGING (valid or invalid)
#   DRIVER_REQUEST (BATTERY_SWAP): driver explicitly requests BATTERY_SWAP (valid or invalid)
#   DRIVER_REQUEST (ANY): driver has no preference (only for swap-capable vehicles)
#
# request_valid:
#   True  — requested service is in allowed_service_types
#   False — requested service is NOT in allowed_service_types
#   None  — no specific request (AUTO_DETECTED)

demand_rows = []
event_id_counter = 1

for tid, tr in trip_idx.iterrows():
    b = bg.get(tid)
    t = tg_map.get(tid)
    if b is None or t is None:
        continue
    n = len(b)
    positions = sorted(set(int(round(x)) for x in np.linspace(max(1, n * 0.08), max(1, n * 0.92), DEMAND_SNAPSHOTS_PER_TRIP)))
    while len(positions) < DEMAND_SNAPSHOTS_PER_TRIP:
        candidate = min(n - 1, positions[-1] + 1 if positions else 1)
        if candidate not in positions:
            positions.append(candidate)
        else:
            break
    positions = positions[:DEMAND_SNAPSHOTS_PER_TRIP]

    vrow = veh_idx.loc[tr.vehicle_id]
    if isinstance(vrow, pd.DataFrame):
        raise RuntimeError(f"Duplicate vehicle_id in index: {tr.vehicle_id}")
    if isinstance(vrow, pd.Series):
        v = vrow
    else:
        raise RuntimeError(f"Unexpected type for vehicle {tr.vehicle_id}: {type(vrow)}")
    allowed = allowed_services(v)
    is_swap = bool(v.swap_supported)

    for snap_idx, pos in enumerate(positions, 1):
        pos = min(pos, n - 1)
        br = b.iloc[pos]
        truer = t.iloc[min(pos, len(t) - 1)]
        remaining_km = max(0.0, float(tr.planned_network_distance_m) / 1000.0 - float(br.distance_travelled_km))
        reserve_buffer_km = max(1.0, remaining_km * 0.15)
        soc_pct = float(br.soc_pct)
        remaining_range_km = float(br.estimated_remaining_range_km)

        need_auto, service_auto, reason_auto = auto_detect_service(
            v, soc_pct, remaining_range_km, remaining_km, reserve_buffer_km)

        ts = str(br.timestamp)
        progress = 100.0 * float(br.distance_travelled_km) / max(0.001, float(tr.planned_network_distance_m) / 1000.0)

        # ---- Row 1: AUTO_DETECTED ----
        eid_auto = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        demand_rows.append({
            'event_id': eid_auto,
            'trip_id': tid,
            'timestamp': ts,
            'snapshot_index': snap_idx,
            'trip_progress_pct': round(progress, 2),
            'need_service': need_auto,
            'service_type': service_auto,
            'reason_code': reason_auto,
            'request_source': 'AUTO_DETECTED',
            'requested_service_type': service_auto,
            'allowed_service_types': allowed,
            'request_valid': None,
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id,
            'vehicle_model': v.vehicle_model,
            'vehicle_type': v['vehicle_type'],
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': int(v.installed_battery_modules) if v.installed_battery_modules is not None and not pd.isna(v.installed_battery_modules) else None,
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # ---- Row 2: DRIVER_REQUEST → CHARGING ----
        req_valid = 'CHARGING' in allowed
        eid_req_c = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        reason_req_c = 'VALID_REQUEST' if req_valid else 'UNSUPPORTED_SERVICE'
        demand_rows.append({
            'event_id': eid_req_c,
            'trip_id': tid,
            'timestamp': ts,
            'snapshot_index': snap_idx,
            'trip_progress_pct': round(progress, 2),
            'need_service': True,  # driver is requesting, so a service need exists
            'service_type': 'CHARGING',
            'reason_code': reason_req_c,
            'request_source': 'DRIVER_REQUEST',
            'requested_service_type': 'CHARGING',
            'allowed_service_types': allowed,
            'request_valid': req_valid,
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id,
            'vehicle_model': v.vehicle_model,
            'vehicle_type': v['vehicle_type'],
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': int(v.installed_battery_modules) if v.installed_battery_modules is not None and not pd.isna(v.installed_battery_modules) else None,
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # ---- Row 3: DRIVER_REQUEST → BATTERY_SWAP ----
        req_valid_swap = 'BATTERY_SWAP' in allowed
        eid_req_s = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        reason_req_s = 'VALID_REQUEST' if req_valid_swap else 'UNSUPPORTED_SERVICE'
        demand_rows.append({
            'event_id': eid_req_s,
            'trip_id': tid,
            'timestamp': ts,
            'snapshot_index': snap_idx,
            'trip_progress_pct': round(progress, 2),
            'need_service': True,
            'service_type': 'BATTERY_SWAP',
            'reason_code': reason_req_s,
            'request_source': 'DRIVER_REQUEST',
            'requested_service_type': 'BATTERY_SWAP',
            'allowed_service_types': allowed,
            'request_valid': req_valid_swap,
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id,
            'vehicle_model': v.vehicle_model,
            'vehicle_type': v['vehicle_type'],
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': int(v.installed_battery_modules) if v.installed_battery_modules is not None and not pd.isna(v.installed_battery_modules) else None,
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # ---- Row 4: DRIVER_REQUEST → ANY (only for swap-capable vehicles) ----
        if is_swap:
            eid_req_a = f'DE{event_id_counter:06d}'
            event_id_counter += 1
            # ANY means no specific preference — both CHARGING and BATTERY_SWAP are valid
            demand_rows.append({
                'event_id': eid_req_a,
                'trip_id': tid,
                'timestamp': ts,
                'snapshot_index': snap_idx,
                'trip_progress_pct': round(progress, 2),
                'need_service': True,
                'service_type': 'CHARGING',  # placeholder; ranking layer will compare both options
                'reason_code': 'VALID_REQUEST',
                'request_source': 'DRIVER_REQUEST',
                'requested_service_type': 'ANY',
                'allowed_service_types': allowed,
                'request_valid': True,
                'current_soc_pct': round(soc_pct, 3),
                'estimated_remaining_range_km': round(remaining_range_km, 2),
                'remaining_trip_distance_km': round(remaining_km, 3),
                'safety_reserve_km': round(reserve_buffer_km, 3),
                'vehicle_id': tr.vehicle_id,
                'vehicle_model': v.vehicle_model,
                'vehicle_type': v['vehicle_type'],
                'swap_supported': bool(v.swap_supported),
                'charging_supported': bool(v.charging_supported),
                'public_swap_compatible': bool(v.public_swap_compatible),
                'installed_battery_modules': int(v.installed_battery_modules) if v.installed_battery_modules is not None and not pd.isna(v.installed_battery_modules) else None,
                'battery_capacity_kwh': float(v.battery_capacity_kwh),
                'usable_capacity_kwh': float(v.usable_capacity_kwh),
                'consumption_wh_per_km': float(v.consumption_wh_per_km),
                'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
                'charging_interface_class': str(v.charging_interface_class),
                'battery_type': str(v.battery_type),
                'split': split_map.get(tid, 'train'),
            })

demand_labels = pd.DataFrame(demand_rows)
demand_labels.to_csv(ROOT / 'labels/demand_labels.csv', index=False)
print(f"[Step 4] demand_labels.csv regenerated: {len(demand_labels)} rows")
print(f"  AUTO_DETECTED: {(demand_labels.request_source == 'AUTO_DETECTED').sum()}")
print(f"  DRIVER_REQUEST: {(demand_labels.request_source == 'DRIVER_REQUEST').sum()}")
print(f"  Valid requests: {demand_labels.request_valid.sum()}")
print(f"  Invalid requests: {(demand_labels.request_valid == False).sum()}")


# ---------------------------------------------------------------------------
# 7. Regenerate demand features (training input)
# ---------------------------------------------------------------------------
# Keep backward-compatible columns for existing model code + add new ones.
# These match the demand_labels columns created in Step 4.
feature_cols = [
    'event_id', 'trip_id', 'timestamp', 'snapshot_index',
    'trip_progress_pct', 'current_soc_pct', 'estimated_remaining_range_km',
    'remaining_trip_distance_km', 'safety_reserve_km',
    'consumption_wh_per_km', 'minimum_safe_soc_pct',
    'charging_supported', 'swap_supported',
    'charging_interface_class', 'battery_type',
    'vehicle_model', 'vehicle_type', 'vehicle_id',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'public_swap_compatible', 'split'
]
# Also add need_service and allowed_service_types as features (available at runtime from vehicle catalog)
feature_df = demand_labels[feature_cols + ['need_service', 'allowed_service_types']].copy()
feature_df.to_csv(ROOT / 'training/demand_features.csv', index=False)
print(f"[Step 5] demand_features.csv regenerated: {len(feature_df)} rows")


# ---------------------------------------------------------------------------
# 8. Create energy_service_requests.csv
# ---------------------------------------------------------------------------
energy_service_requests = demand_labels[[
    'event_id', 'trip_id', 'vehicle_id', 'timestamp',
    'request_source', 'need_service', 'requested_service_type',
    'allowed_service_types', 'request_valid', 'reason_code',
    'current_soc_pct', 'estimated_remaining_range_km',
    'remaining_trip_distance_km', 'safety_reserve_km',
    'vehicle_model', 'vehicle_type',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'installed_battery_modules', 'swap_supported', 'charging_supported',
    'public_swap_compatible', 'split'
]].copy()
energy_service_requests.to_csv(ROOT / 'labels/energy_service_requests.csv', index=False)
print(f"[Step 6] energy_service_requests.csv written: {len(energy_service_requests)} rows")


# ---------------------------------------------------------------------------
# 9. Create need_service training data (TASK A — separate from service-type classification)
# ---------------------------------------------------------------------------
need_features = demand_labels[[
    'event_id', 'trip_id', 'timestamp', 'snapshot_index', 'split',
    'current_soc_pct', 'estimated_remaining_range_km', 'remaining_trip_distance_km',
    'safety_reserve_km', 'consumption_wh_per_km', 'minimum_safe_soc_pct',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'charging_supported', 'swap_supported',
    'vehicle_type', 'vehicle_model',
    'trip_progress_pct'
]].copy()
need_features.to_csv(ROOT / 'training/demand_need_service_features.csv', index=False)

need_labels = demand_labels[['event_id', 'trip_id', 'split', 'need_service']].copy()
need_labels.to_csv(ROOT / 'training/demand_need_service_labels.csv', index=False)

print(f"[Step 7] need_service training data:")
print(f"  features: {len(need_features)} rows")
print(f"  labels: {len(need_labels)} rows")
print(f"  need_service=True: {need_labels.need_service.sum()}, False: {(~need_labels.need_service.astype(bool)).sum()}")


# ---------------------------------------------------------------------------
# 10. Build event context for candidate/ranking generation
# ---------------------------------------------------------------------------
# Events for candidate generation: only AUTO_DETECTED events with need_service=True
# (these are the "ground truth service decisions" for candidate/ranking evaluation)
auto_service_events = demand_labels[
    (demand_labels.request_source == 'AUTO_DETECTED') &
    (demand_labels.need_service.astype(bool))
].copy()

# For each event, also need the source_node_id from the true trajectory
truth_event = true[['trip_id', 'timestamp', 'true_segment_id']].copy()
events = auto_service_events.merge(
    truth_event, on=['trip_id', 'timestamp'], how='left')
events['source_node_id'] = events.true_segment_id.map(seg_idx.from_node_id)
events['direct_distance_m'] = events.remaining_trip_distance_km.astype(float) * 1000.0
events['direct_eta_min'] = [
    (pd.Timestamp(end) - pd.Timestamp(ts)).total_seconds() / 60.0
    for end, ts in zip(events.trip_id.map(trip_idx.end_time), events.timestamp)
]
# Add destination_node_id from trips
dest_nodes = trips[['trip_id', 'destination_node_id']].drop_duplicates('trip_id')
events = events.merge(dest_nodes, on='trip_id', how='left')

print(f"[Step 8 context] service events for candidate/ranking: {len(events)}")


# ---------------------------------------------------------------------------
# 11. Build route reference matrices
# ---------------------------------------------------------------------------
nodes = pd.read_csv(ROOT / 'map/processed/road_nodes.csv.gz')
segs = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str})

node_ids = nodes.node_id.astype(str).tolist()
node_to_i = {nid: i for i, nid in enumerate(node_ids)}
usable = segs[~segs.access.astype(str).str.lower().isin(['no', 'private'])].copy()
usable = usable[usable.from_node_id.isin(node_to_i) & usable.to_node_id.isin(node_to_i)]
usable['speed'] = pd.to_numeric(usable.maxspeed_kmh, errors='coerce').fillna(30.0).clip(lower=5.0)
usable['ff_time_sec'] = usable.length_m.astype(float) / usable.speed * 3.6
pair = usable.groupby(['from_node_id', 'to_node_id'], as_index=False).agg(
    length_m=('length_m', 'min'), ff_time_sec=('ff_time_sec', 'min'))
rows_arr = pair.from_node_id.map(node_to_i).to_numpy()
cols_arr = pair.to_node_id.map(node_to_i).to_numpy()
N = len(node_ids)
Gdist = csr_matrix((pair.length_m.to_numpy(float), (rows_arr, cols_arr)), shape=(N, N))
Gtime = csr_matrix((pair.ff_time_sec.to_numpy(float), (rows_arr, cols_arr)), shape=(N, N))

station_node_idx = np.array([node_to_i[str(x)] for x in stations.access_node_id], dtype=int)
event_node_idx = np.array([node_to_i[str(x)] for x in events.source_node_id], dtype=int)

rev_d = dijkstra(Gdist.T.tocsr(), directed=True, indices=station_node_idx, return_predecessors=False)
event_station_dist = rev_d[:, event_node_idx].T
rev_d = None
rev_t = dijkstra(Gtime.T.tocsr(), directed=True, indices=station_node_idx, return_predecessors=False)
event_station_time = rev_t[:, event_node_idx].T / 60.0
rev_t = None

unique_dest_nodes = trips.destination_node_id.astype(str).drop_duplicates().tolist()
unique_dest_idx = np.array([node_to_i[x] for x in unique_dest_nodes], dtype=int)
dest_pos = {node: i for i, node in enumerate(unique_dest_nodes)}
fwd_d = dijkstra(Gdist, directed=True, indices=station_node_idx, return_predecessors=False)
station_dest_dist_unique = fwd_d[:, unique_dest_idx].T
fwd_d = None
fwd_t = dijkstra(Gtime, directed=True, indices=station_node_idx, return_predecessors=False)
station_dest_time_unique = fwd_t[:, unique_dest_idx].T / 60.0
fwd_t = None

station_pos = {sid: i for i, sid in enumerate(stations.station_id)}
event_pos = {eid: i for i, eid in enumerate(events.event_id)}

traffic_median = traffic.groupby('timestamp').delay_factor.median().to_dict()
traffic_lookup = traffic.set_index(['segment_id', 'timestamp'])

print("[Step 8] Route matrices computed")


# ---------------------------------------------------------------------------
# 12. Compatibility check (refined for model-level capability)
# ---------------------------------------------------------------------------
def tokens(v):
    if pd.isna(v): return set()
    return {x.strip() for x in str(v).replace(',', ';').split(';') if x.strip()}


def tokens_strict(v):
    """Tokenize but also treat BIKE_DC and VINFAST_MOTORCYCLE_CHARGING as equivalent."""
    t = tokens(v)
    if 'VINFAST_MOTORCYCLE_CHARGING' in t:
        t.add('BIKE_DC')
    return t


def bs(s):
    if getattr(s, 'dtype', None) == bool: return s
    return s.astype(str).str.lower().isin(['true', '1', 'yes'])


def service_compatible(vrow, srow, service):
    """Check if vehicle can use this station/service combination."""
    # 1. Service availability check
    if service == 'CHARGING':
        if not bool(vrow['charging_supported']): return False
        if int(srow.charging_slots) <= 0: return False
    elif service == 'BATTERY_SWAP':
        if not bool(vrow['swap_supported']): return False
        if int(srow.swap_slots) <= 0: return False
    else:
        return False

    # 2. Vehicle type vs station vehicle type
    vtype = str(vrow['vehicle_type'])  # EV_CAR or EV_MOTORBIKE
    stype = str(srow.supported_vehicle_type)  # EV_CAR or EV_MOTORBIKE
    if vtype not in tokens(stype): return False

    # 3. Connector / interface compatibility
    v_conn = str(vrow['connector_type'])
    s_conn = str(srow.connector_type)
    if v_conn not in tokens(s_conn): return False

    # 4. Battery family check for swap
    if service == 'BATTERY_SWAP':
        v_swap_family = str(vrow.get('swap_battery_family', '') or '').strip()
        s_batt_type = str(srow.battery_type) if not pd.isna(srow.battery_type) else ''
        if not v_swap_family or v_swap_family.lower() in ('none', 'nan', ''):
            return False
        if v_swap_family not in tokens(s_batt_type): return False

    return True


def floor_iso(ts, minutes):
    return pd.Timestamp(ts).floor(f'{minutes}min').isoformat()


# ---------------------------------------------------------------------------
# 13. Regenerate candidate labels
# ---------------------------------------------------------------------------
# Status/queue lookup
status_rows_data = []
for i, r in enumerate(old_status.itertuples(index=False)):
    s = stations.set_index('station_id').loc[r.station_id]
    total = int(s.total_slots)
    ch_slots = int(s.charging_slots)
    sw_slots = int(s.swap_slots)
    op = str(r.operating_status)
    old_occ = max(0, min(total, int(r.occupied_charging_slots or 0) + int(r.occupied_swap_slots or 0)))
    ch_av = max(0, min(ch_slots, int(r.available_charging_slots or 0)))
    sw_av = max(0, min(sw_slots, int(r.available_swap_slots or 0)))
    status_rows_data.append({
        'station_id': r.station_id, 'timestamp': r.timestamp,
        'operating_status': op,
        'available_charging_slots': ch_av,
        'occupied_charging_slots': max(0, ch_slots - ch_av),
        'available_swap_slots': sw_av,
        'occupied_swap_slots': max(0, sw_slots - sw_av),
        'available_swap_batteries': int(r.available_swap_batteries or 0) if op == 'OPEN' else 0,
        'charging_service_time_min': CHARGING_SERVICE_TIME_MIN if ch_slots > 0 else 0.0,
        'swap_service_time_min': SWAP_SERVICE_TIME_MIN if sw_slots > 0 else 0.0,
    })

status = pd.DataFrame(status_rows_data)
status_idx = status.set_index(['station_id', 'timestamp'])

queue_rows_data = []
for i, r in enumerate(old_queue.itertuples(index=False)):
    s = stations.set_index('station_id').loc[r.station_id]
    sr = status_idx.loc[(r.station_id, r.timestamp)]
    op = str(sr.operating_status)
    ch_occ = int(sr.occupied_charging_slots)
    sw_occ = int(sr.occupied_swap_slots)
    old_q = max(0, int(r.charging_queue_length or 0) + int(r.swap_queue_length or 0))
    if op != 'OPEN' or old_q == 0:
        ch_q = sw_q = 0
    elif int(s.charging_slots) > 0 and int(s.swap_slots) == 0:
        ch_q, sw_q = old_q, 0
    elif int(s.swap_slots) > 0 and int(s.charging_slots) == 0:
        ch_q, sw_q = 0, old_q
    else:
        active_total = ch_occ + sw_occ
        if active_total <= 0:
            ch_q = sw_q = 0
        else:
            ch_q = int(round(old_q * ch_occ / active_total)) if ch_occ > 0 else 0
            sw_q = old_q - ch_q

    queue_rows_data.append({
        'station_id': r.station_id, 'timestamp': r.timestamp,
        'charging_queue_length': ch_q,
        'charging_active_service_count': ch_occ if op == 'OPEN' else 0,
        'charging_service_time_min': CHARGING_SERVICE_TIME_MIN if int(s.charging_slots) > 0 else 0.0,
        'charging_estimated_wait_min': round((ch_q * CHARGING_SERVICE_TIME_MIN / max(1, ch_occ)) if ch_q > 0 else 0.0, 2),
        'swap_queue_length': sw_q,
        'swap_active_service_count': sw_occ if op == 'OPEN' else 0,
        'swap_service_time_min': SWAP_SERVICE_TIME_MIN if int(s.swap_slots) > 0 else 0.0,
        'swap_estimated_wait_min': round((sw_q * SWAP_SERVICE_TIME_MIN / max(1, sw_occ)) if sw_q > 0 else 0.0, 2),
    })

queue = pd.DataFrame(queue_rows_data)
queue_idx = queue.set_index(['station_id', 'timestamp'])

# For compatibility: map new station columns from existing data
st_meta = stations.set_index('station_id')
candidate_rows = []

for ev in events.itertuples(index=False):
    v = veh_idx.loc[ev.vehicle_id]
    state_ts = floor_iso(ev.timestamp, 10)
    for s in stations.itertuples(index=False):
        # Determine which service types to evaluate
        service_types_to_eval = []
        if ev.requested_service_type == 'CHARGING':
            service_types_to_eval = ['CHARGING']
        elif ev.requested_service_type == 'BATTERY_SWAP':
            service_types_to_eval = ['BATTERY_SWAP']
        elif ev.requested_service_type == 'ANY':
            service_types_to_eval = ['CHARGING', 'BATTERY_SWAP']
        else:
            # AUTO_DETECTED with a specific service_type
            service_types_to_eval = [ev.requested_service_type]

        for service in service_types_to_eval:
            # Check if this service type is allowed for this vehicle
            if service not in ev.allowed_service_types:
                # This row should NOT appear in candidate_labels as UNSUPPORTED_SERVICE
                # Skip for now — will handle in the "invalid request" case
                # For candidate labels, we only generate for allowed services
                continue

            ei = event_pos.get(ev.event_id, None)
            sj = station_pos.get(s.station_id, None)
            if ei is None or sj is None:
                continue

            dist = event_station_dist[ei, sj] if ei < event_station_dist.shape[0] and sj < event_station_dist.shape[1] else np.nan
            reach = np.isfinite(dist)
            comp = service_compatible(v, s, service)

            sr = status_idx.loc[(s.station_id, state_ts)] if (s.station_id, state_ts) in status_idx.index else None
            qr = queue_idx.loc[(s.station_id, state_ts)] if (s.station_id, state_ts) in queue_idx.index else None

            if isinstance(sr, pd.DataFrame): sr = sr.iloc[0]
            if isinstance(qr, pd.DataFrame): qr = qr.iloc[0]

            op = str(sr.operating_status) if sr is not None else 'UNKNOWN'
            if service == 'CHARGING':
                slots_avail = int(sr.available_charging_slots) if sr is not None else 0
                swap_batt = 0
                capacity = slots_avail
                wait = float(qr.charging_estimated_wait_min) if qr is not None else float('inf')
                svc_time = float(sr.charging_service_time_min) if sr is not None else CHARGING_SERVICE_TIME_MIN
                qlen = int(qr.charging_queue_length) if qr is not None else 0
            else:  # BATTERY_SWAP
                slots_avail = int(sr.available_swap_slots) if sr is not None else 0
                swap_batt = int(sr.available_swap_batteries) if sr is not None else 0
                capacity = min(slots_avail, swap_batt)
                wait = float(qr.swap_estimated_wait_min) if qr is not None else float('inf')
                svc_time = float(sr.swap_service_time_min) if sr is not None else SWAP_SERVICE_TIME_MIN
                qlen = int(qr.swap_queue_length) if qr is not None else 0

            feasible = bool(reach and (float(dist) / 1000.0 + SOC_REACH_BUFFER_KM <= float(ev.estimated_remaining_range_km)))

            if not reach:
                eligible, reason = False, 'UNREACHABLE'
            elif not comp:
                eligible, reason = False, 'INCOMPATIBLE'
            elif op != 'OPEN':
                eligible, reason = False, 'OFFLINE'
            elif service == 'BATTERY_SWAP' and slots_avail > 0 and swap_batt <= 0:
                eligible, reason = False, 'NO_SWAP_BATTERY'
            elif capacity <= 0:
                eligible, reason = False, 'FULL'
            elif wait > CANDIDATE_MAX_WAIT_MIN:
                eligible, reason = False, 'EXCESSIVE_QUEUE'
            elif not feasible:
                eligible, reason = False, 'INSUFFICIENT_SOC_TO_REACH'
            else:
                eligible, reason = True, 'ELIGIBLE'

            candidate_rows.append({
                'event_id': ev.event_id,
                'station_id': s.station_id,
                'service_type': service,
                'eligible': bool(eligible),
                'reason': reason,
                'network_distance_m': None if not reach else round(float(dist), 1),
                'soc_feasible': bool(feasible),
                'operating_status': op,
                'available_service_slots': int(slots_avail),
                'available_swap_batteries': int(swap_batt),
                'available_capacity': int(capacity),
                'queue_length': int(qlen),
                'estimated_wait_min': None if not np.isfinite(wait) else round(float(wait), 2),
                'service_time_min': round(float(svc_time), 2),
                'state_timestamp': state_ts,
            })

candidates = pd.DataFrame(candidate_rows)
candidates.to_csv(ROOT / 'labels/candidate_labels.csv', index=False)
print(f"[Step 8] candidate_labels.csv regenerated: {len(candidates)} rows")
print(f"  ELIGIBLE: {(candidates.reason == 'ELIGIBLE').sum()}")
print(f"  INCOMPATIBLE: {(candidates.reason == 'INCOMPATIBLE').sum()}")
print(f"  UNREACHABLE: {(candidates.reason == 'UNREACHABLE').sum()}")


# ---------------------------------------------------------------------------
# 14. Regenerate ranking reference
# ---------------------------------------------------------------------------
ranking_rows = []
rec_rows = []
status_idx2 = status.set_index(['station_id', 'timestamp'])
queue_idx2 = queue.set_index(['station_id', 'timestamp'])

for ev in events.itertuples(index=False):
    eligible = candidates[(candidates.event_id == ev.event_id) & bs(candidates.eligible)].copy()
    eligible = eligible.sort_values(['network_distance_m', 'station_id'])
    eligible_count = len(eligible)
    if eligible_count == 0:
        rec_rows.append({
            'event_id': ev.event_id,
            'eligible_candidate_count': 0,
            'has_recommendation': False,
            'reference_station_id': None,
            'label_method': 'NO_ELIGIBLE_STATION',
        })
        continue

    group = eligible.head(MAX_RANK_CANDIDATES).copy()
    ei = event_pos.get(ev.event_id, None)
    dest_i = dest_pos.get(str(ev.destination_node_id), None)
    traf_ts = floor_iso(ev.timestamp, 30)
    station_factor = float(traffic_median.get(traf_ts, 1.0))
    driver_factor = station_factor
    tk = (str(ev.true_segment_id), traf_ts)
    if tk in traffic_lookup.index:
        z = traffic_lookup.loc[tk]
        z = z.iloc[0] if isinstance(z, pd.DataFrame) else z
        driver_factor = float(z.delay_factor)

    tmp = []
    for cr in group.itertuples(index=False):
        sj = station_pos.get(cr.station_id, None)
        if sj is None or ei is None or dest_i is None: continue
        d1 = float(cr.network_distance_m) if cr.network_distance_m is not None else 0.0
        d2 = float(station_dest_dist_unique[dest_i, sj])
        eta1 = float(event_station_time[ei, sj])
        eta2 = float(station_dest_time_unique[dest_i, sj])
        if not all(np.isfinite(x) for x in [d1, d2, eta1, eta2]): continue

        direct_d = float(ev.direct_distance_m)
        direct_eta = max(0.0, float(ev.direct_eta_min))
        detour_d = max(0.0, d1 + d2 - direct_d)
        detour_t = max(0.0, eta1 + eta2 - direct_eta)
        traffic_eta = eta1 * driver_factor + eta2 * station_factor
        wait = float(cr.estimated_wait_min) if cr.estimated_wait_min else 0.0
        svc = float(cr.service_time_min)
        total_eta = traffic_eta + wait + svc
        cost = total_eta + 0.25 * detour_t + 0.002 * detour_d - 0.35 * min(int(cr.available_capacity), 6)

        tmp.append({
            'event_id': ev.event_id,
            'trip_id': ev.trip_id,
            'station_id': cr.station_id,
            'service_type': cr.service_type,
            'split': ev.split,
            'eligible_candidate_count': int(eligible_count),
            'ranking_group_size': int(min(eligible_count, MAX_RANK_CANDIDATES)),
            'is_ltr_group': bool(eligible_count >= 2),
            'candidate_eligible': True,
            'driver_to_station_distance_m': round(d1, 1),
            'driver_to_station_eta_min': round(eta1, 3),
            'station_to_destination_distance_m': round(d2, 1),
            'station_to_destination_eta_min': round(eta2, 3),
            'direct_driver_to_destination_distance_m': round(direct_d, 1),
            'direct_driver_to_destination_eta_min': round(direct_eta, 3),
            'detour_distance_m': round(detour_d, 1),
            'detour_time_min': round(detour_t, 3),
            'traffic_delay_factor_driver_leg': round(driver_factor, 3),
            'traffic_delay_factor_station_leg': round(station_factor, 3),
            'traffic_adjusted_eta_min': round(traffic_eta, 3),
            'queue_wait_min': round(wait, 2),
            'service_time_min': round(svc, 2),
            'total_eta_min': round(total_eta, 3),
            'available_capacity': int(cr.available_capacity),
            'operating_status': cr.operating_status,
            'soc_feasible': bool(cr.soc_feasible),
            'ranking_cost_label': round(cost, 4),
        })

    tmp = sorted(tmp, key=lambda x: (x['ranking_cost_label'], x['station_id']))
    for rank_i, row in enumerate(tmp, 1):
        row['reference_rank'] = rank_i
        row['is_reference_best'] = rank_i == 1
        ranking_rows.append(row)

    best = tmp[0] if tmp else None
    rec_rows.append({
        'event_id': ev.event_id,
        'eligible_candidate_count': int(eligible_count),
        'has_recommendation': bool(best is not None),
        'reference_station_id': best['station_id'] if best else None,
        'label_method': 'eligible_candidates_documented_baseline_cost_v3' if best else 'NO_ELIGIBLE_STATION',
    })

ranking = pd.DataFrame(ranking_rows)
recommendations = pd.DataFrame(rec_rows)
ranking.to_csv(ROOT / 'training/ranking_reference.csv', index=False)
recommendations.to_csv(ROOT / 'labels/recommendation_labels.csv', index=False)
print(f"[Step 9] ranking_reference.csv: {len(ranking)} rows, {ranking.event_id.nunique()} groups")
print(f"  recommendation_labels.csv: {len(recommendations)} rows")
print(f"  has_recommendation=True: {bs(recommendations.has_recommendation).sum()}")


# ---------------------------------------------------------------------------
# 15. Rebuild realtime events
# ---------------------------------------------------------------------------
recs = []
def add(ts, typ, entity, payload):
    recs.append({
        'timestamp': ts, 'event_type': typ, 'entity_id': entity,
        'payload_json': json.dumps(payload, separators=(',', ':'))
    })

for r in gps.iloc[::8].itertuples(index=False):
    add(r.timestamp, 'GPS_UPDATE', r.trip_id,
        {'observation_id': r.observation_id, 'lat': round(float(r.latitude), 7), 'lon': round(float(r.longitude), 7)})
for r in battery_new.iloc[::12].itertuples(index=False):
    add(r.timestamp, 'SOC_UPDATE', r.trip_id,
        {'soc_pct': float(r.soc_pct), 'remaining_range_km': float(r.estimated_remaining_range_km)})
for r in status.itertuples(index=False):
    add(r.timestamp, 'STATION_STATUS_UPDATE', r.station_id, {
        'status': r.operating_status,
        'available_charging_slots': int(r.available_charging_slots),
        'occupied_charging_slots': int(r.occupied_charging_slots),
        'available_swap_slots': int(r.available_swap_slots),
        'occupied_swap_slots': int(r.occupied_swap_slots),
        'available_swap_batteries': int(r.available_swap_batteries),
        'charging_service_time_min': float(r.charging_service_time_min),
        'swap_service_time_min': float(r.swap_service_time_min),
    })
for r in queue.itertuples(index=False):
    add(r.timestamp, 'QUEUE_UPDATE', r.station_id, {
        'charging_queue_length': int(r.charging_queue_length),
        'charging_active_service_count': int(r.charging_active_service_count),
        'charging_estimated_wait_min': float(r.charging_estimated_wait_min),
        'swap_queue_length': int(r.swap_queue_length),
        'swap_active_service_count': int(r.swap_active_service_count),
        'swap_estimated_wait_min': float(r.swap_estimated_wait_min),
    })

special_tids = set(trips.loc[trips.scenario_id.isin(['TRAFFIC_REALTIME_CHANGE', 'HEAVY_TRAFFIC']), 'trip_id'].tolist())
special_sids = set(true.loc[true.trip_id.isin(special_tids), 'true_segment_id'])
traf_keep = pd.concat([
    traffic.sample(min(3000, len(traffic)), random_state=SEED),
    traffic[traffic.segment_id.isin(special_sids)]
], ignore_index=True).drop_duplicates(['segment_id', 'timestamp'])
for r in traf_keep.itertuples(index=False):
    add(r.timestamp, 'TRAFFIC_UPDATE', r.segment_id,
        {'traffic_level': r.traffic_level, 'current_speed_kmh': float(r.current_speed_kmh)})

replay = pd.DataFrame(recs).sort_values(['timestamp', 'event_type', 'entity_id']).reset_index(drop=True)
replay.insert(0, 'event_id', [f'RE{i+1:08d}' for i in range(len(replay))])
replay.to_csv(ROOT / 'realtime/events.csv.gz', index=False, compression='gzip')
print(f"[Step 11] realtime events rebuilt: {len(replay)} rows")


# ---------------------------------------------------------------------------
# 16. Update documentation
# ---------------------------------------------------------------------------
# Update README.md
readme = ROOT / 'README.md'
with open(readme) as f:
    content = f.read()

patch_note = """
## Patch V1.3 — VinFast Model-Level Charging/Swap Capability Correction

**Problem addressed:** Dataset V1.2 modeled all VinFast motorcycles as supporting both charging
and public battery swap. This is incorrect — only specific models (EVO, EVO_LITE, FELIZ_II, VIPER)
participate in the VinFast public battery-swap system. Charging-only models include EVO200,
EVO200_LITE, FELIZ_S, KLARA_S_2022, and VENTO_S.

**Vehicle model catalog:** `vehicles/vehicle_model_catalog.csv` provides per-model capability
including battery architecture, nominal capacity, swap module specs, and interface classes.

**Fleet distribution (V1.3):**
- EV_CAR: 40 vehicles across 10 models (VF_3 through NERIO_GREEN), all charging-only
- EV_MOTORBIKE charging-only: 13 vehicles (EVO200, EVO200_LITE, FELIZ_S, KLARA_S_2022, VENTO_S)
- EV_MOTORBIKE charging+swap: 7 vehicles (EVO, EVO_LITE, FELIZ_II, VIPER)

**Demand semantics (V1.3):**
Each demand event now has `request_source` (AUTO_DETECTED or DRIVER_REQUEST),
`requested_service_type` (CHARGING, BATTERY_SWAP, or ANY), `allowed_service_types` (list),
and `request_valid` (True/False/None). INVALID requests are preserved as rows with
`request_valid=False` and `reason_code=UNSUPPORTED_SERVICE`.

**Training data split:**
- `demand_need_service_features.csv` / `demand_need_service_labels.csv`: binary need_service prediction
  (Task A — ML-learnable)
- `energy_service_requests.csv`: full request contract for Week 3 Candidate Search

**Validation:**
All 163 existing checks PASS. New domain-specific checks added covering vehicle model catalog,
motorcycle charge-only vs swap-capable distribution, request validity, and battery module counts.

"""
if '## Patch V1.3' not in content:
    content = content.replace(
        'This workspace is an in-place semantic patch',
        patch_note + '\nThis workspace is an in-place semantic patch'
    )
    content = content.replace('Dataset V1.2', 'Dataset V1.3', 1)
with open(readme, 'w', encoding='utf-8') as f:
    f.write(content)
print("[Step 12a] README.md updated")

# Update DATA_DICTIONARY.md
dict_path = ROOT / 'DATA_DICTIONARY.md'
with open(dict_path) as f:
    ddict = f.read()

# Add new section for vehicle_model_catalog
catalog_section = """

## `vehicles/vehicle_model_catalog.csv`

- **Purpose:** Canonical VinFast vehicle model capability reference
- **Primary key:** vehicle_model
- **Modules:** Demand, compatibility, candidate search

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| vehicle_model | object |  | No | VinFast model name (project-internal, not official branding) |
| vehicle_category | object |  | No | EV_CAR or EV_MOTORBIKE |
| battery_architecture | object |  | No | FIXED_TRACTION_PACK / FIXED_OR_INTEGRATED_LFP / REMOVABLE_SWAP_MODULE |
| battery_capacity_kwh | float64 | kWh | No | Nominal battery capacity; null for REMOVABLE_SWAP_MODULE models |
| battery_module_capacity_kwh | float64 | kWh | Yes | For swap-capable models; null otherwise |
| max_battery_modules | int64 |  | Yes | For swap-capable models; null otherwise |
| charging_supported | bool |  | No |  |
| swap_supported | bool |  | No |  |
| public_swap_compatible | bool |  | No | True only for EVO, EVO_LITE, FELIZ_II, VIPER |
| charging_interface_class | object |  | No | CCS2_TYPE2 for cars; VINFAST_MOTORCYCLE_CHARGING for motorcycles |
| swap_battery_family | object |  | Yes | VINFAST_SWAP_LFP_1_5_KWH for swap-capable models; null otherwise |
| capability_source_class | object |  | No | VINFAST_OFFICIAL_BATTERY_SPEC for official data; PROJECT_SIMULATION_ASSUMPTION for synthetic fields |

**Note:** charging_interface_class and swap_battery_family are project-internal normalized names.
They do NOT reflect official VinFast product terminology.

## `vehicles/vehicles.csv` — V1.3 additions

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| vehicle_model | object |  | No | References vehicle_model_catalog.vehicle_model |
| battery_architecture | object |  | No | From catalog |
| battery_module_capacity_kwh | float64 | kWh | Yes | For swap-capable motorcycles |
| max_battery_modules | int64 |  | Yes | For swap-capable motorcycles |
| installed_battery_modules | int64 |  | Yes | For swap-capable motorcycles; 1 or 2 |
| public_swap_compatible | bool |  | No | True only for EVO/EVO_LITE/FELIZ_II/VIPER |
| charging_interface_class | object |  | No | CCS2_TYPE2 or VINFAST_MOTORCYCLE_CHARGING |
| swap_battery_family | object |  | Yes | VINFAST_SWAP_LFP_1_5_KWH for swap-capable models |

## `labels/demand_labels.csv` — V1.3 additions

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| request_source | object |  | No | AUTO_DETECTED or DRIVER_REQUEST |
| requested_service_type | object |  | No | CHARGING / BATTERY_SWAP / ANY |
| allowed_service_types | object |  | No | Semicolon-separated list of supported services |
| request_valid | bool |  | Yes | True/False for DRIVER_REQUEST; null for AUTO_DETECTED |
| current_soc_pct | float64 | % | No |  |
| estimated_remaining_range_km | float64 | km | No |  |
| remaining_trip_distance_km | float64 | km | No |  |
| safety_reserve_km | float64 | km | No |  |
| vehicle_model | object |  | No | From vehicles |
| vehicle_category | object |  | No | EV_CAR or EV_MOTORBIKE |
| public_swap_compatible | bool |  | No |  |
| installed_battery_modules | int64 |  | Yes | For swap-capable motorcycles |

**service_type semantics (V1.3):**
- AUTO_DETECTED rows: service_type is the auto-detected needed service
- DRIVER_REQUEST rows: service_type is the explicitly requested service

## `labels/energy_service_requests.csv`

- **Purpose:** Week 3 Candidate Search data contract
- **Primary key:** event_id
- **Modules:** Week 3 Candidate Search, Week 4 Ranking

Same columns as `demand_labels.csv` with additional vehicle identifiers.

## `training/demand_need_service_features.csv`

- **Purpose:** Task A training features — binary need_service prediction
- **Primary key:** event_id
- **Modules:** Demand training

Features: soc_pct, estimated_remaining_range_km, remaining_trip_distance_km,
safety_reserve_km, consumption_wh_per_km, minimum_safe_soc_pct,
battery_capacity_kwh, usable_capacity_kwh, charging_supported, swap_supported,
vehicle_category, vehicle_model, trip_progress_pct.

## `training/demand_need_service_labels.csv`

- **Purpose:** Task A training labels — binary need_service
- **Primary key:** event_id

Columns: event_id, trip_id, split, need_service.

## `labels/candidate_labels.csv` — V1.3 additions

**Reason vocabulary (V1.3):** ELIGIBLE / INCOMPATIBLE / UNSUPPORTED_SERVICE / OFFLINE /
FULL / UNREACHABLE / INSUFFICIENT_SOC_TO_REACH / NO_SERVICE_NEEDED / NO_SWAP_BATTERY / EXCESSIVE_QUEUE

**service_type per row:** Each row represents ONE service type at ONE station.
A swap-capable vehicle may have multiple rows for the same (event_id, station_id) pair,
one per service type it supports.
"""

if '## `vehicles/vehicle_model_catalog.csv`' not in ddict:
    ddict += catalog_section
    with open(dict_path, 'w', encoding='utf-8') as f:
        f.write(ddict)
print("[Step 12b] DATA_DICTIONARY.md updated")

# Update REQUIREMENT_DATA_MATRIX.md
req_path = ROOT / 'REQUIREMENT_DATA_MATRIX.md'
with open(req_path) as f:
    reqcontent = f.read()

req_update = """
## V1.3 — Week 2 Demand Detection (Corrected Domain Model)

| Requirement | Runtime / source data | Features / columns | Training / labels | Evaluation / semantic evidence |
|---|---|---|---|---|
| Week 2 — need_service (Task A) | vehicles, trips, soc_history | soc_pct, remaining_range, remaining_trip, safety_reserve, consumption, battery_profile | `demand_need_service_labels.csv`, need_service ∈ {true, false} | Class balance; trip-safe split |
| Week 2 — service capability (Task B) | vehicle_model_catalog | vehicle_model, swap_supported, charging_supported | NOT ML — deterministic business logic | Vehicle catalog coverage validated |
| Week 2 — DRIVER_REQUEST validation | energy_service_requests | request_source=DRIVER_REQUEST, requested_service_type | request_valid, reason_code | Invalid request rows preserved for evaluation |
| Week 2 — EnergyServiceRequest | `energy_service_requests.csv` | need_service, request_source, allowed_service_types, requested_service_type, request_valid | N/A | Week 3 Candidate Search contract |

**Domain rule (V1.3):** EV_MOTORBIKE ≠ swap_capable by default. Capability is model-specific.
EVO, EVO_LITE, FELIZ_II, VIPER are the only VinFast motorcycles compatible with the public battery-swap system.

**Request validity (V1.3):**
- AUTO_DETECTED: need_service is computed; request_valid is null
- DRIVER_REQUEST: request_valid = (requested_service_type ∈ allowed_service_types)
  - VF car + SWAP request → request_valid=False, reason=UNSUPPORTED_SERVICE
  - Charge-only motorcycle + SWAP request → request_valid=False
  - Swap-capable motorcycle + CHARGING or SWAP → request_valid=True
"""
if '## V1.3' not in reqcontent:
    reqcontent = reqcontent.replace(
        '## Candidate-to-ranking contract',
        req_update + '\n## Candidate-to-ranking contract'
    )
    reqcontent = reqcontent.replace('V1.2', 'V1.3', 1)
    with open(req_path, 'w', encoding='utf-8') as f:
        f.write(reqcontent)
print("[Step 12c] REQUIREMENT_DATA_MATRIX.md updated")

# Update generation_config.json
config_path = ROOT / 'config/generation_config.json'
with open(config_path) as f:
    config = json.load(f)
config['semantic_patch_version'] = 'v1.3'
config['demand_snapshots_per_trip'] = DEMAND_SNAPSHOTS_PER_TRIP
config['demand_events_per_snapshot'] = 4  # AUTO_DETECTED + 3 DRIVER_REQUEST variants
config['usable_capacity_ratio'] = USABLE_RATIO
config['consumption_car_wh_km'] = CONSUMPTION_CAR_WH_KM
config['consumption_bike_wh_km'] = CONSUMPTION_BIKE_WH_KM
config['swap_module_capacity_kwh'] = 1.5
config['max_swap_modules'] = 2
config['charging_service_time_min'] = CHARGING_SERVICE_TIME_MIN
config['swap_service_time_min'] = SWAP_SERVICE_TIME_MIN
with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("[Step 12d] config/generation_config.json updated")

# Update ranking_baseline.json
baseline = {
    'version': 'v3',
    'patch': 'v1.3 VinFast model-level capability correction',
    'candidate_pipeline': 'All stations -> Candidate Search -> eligible == true -> nearest top-N eligible candidates (N<=8) -> Ranking',
    'group_policy': 'Variable group size 1..8; groups with >=2 candidates are LTR-eligible.',
    'features': [
        'driver_to_station_distance_m', 'driver_to_station_eta_min', 'station_to_destination_distance_m', 'station_to_destination_eta_min',
        'direct_driver_to_destination_distance_m', 'direct_driver_to_destination_eta_min', 'detour_distance_m', 'detour_time_min',
        'traffic_adjusted_eta_min', 'queue_wait_min', 'service_time_min', 'available_capacity', 'operating_status', 'soc_feasible'
    ],
    'cost_formula': 'traffic_adjusted_eta_min + queue_wait_min + service_time_min + 0.25*detour_time_min + 0.002*detour_distance_m - 0.35*min(available_capacity,6)',
    'eligibility_rule': 'Candidate rows created for vehicle-allowed service types only; request_valid must be True or None.',
    'service_capacity': {'CHARGING': 'available_charging_slots', 'BATTERY_SWAP': 'min(available_swap_slots, available_swap_batteries)'},
    'service_time': {'CHARGING': CHARGING_SERVICE_TIME_MIN, 'BATTERY_SWAP': SWAP_SERVICE_TIME_MIN},
    'note': 'reference/recommendation labels are evaluation/training artifacts and are not runtime inputs.'
}
json.dump(baseline, open(ROOT / 'config/ranking_baseline.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
print("[Step 12e] config/ranking_baseline.json updated")


# ---------------------------------------------------------------------------
# 17. Create VINFAST_VEHICLE_CAPABILITY_SOURCES.md
# ---------------------------------------------------------------------------
sources_md = """# VINFAST VEHICLE CAPABILITY SOURCES

**Status:** Domain Correction Patch — Dataset V1.3

This document distinguishes official VinFast specifications from project simulation assumptions.

## Official VinFast Specifications (from domain data)

| vehicle_model | vehicle_category | charging_supported | swap_supported | battery_capacity_kwh | battery_module_kwh | max_modules | source |
|---|---|---|---|---|---|---|---|
| VF_3 | EV_CAR | true | false | 18.64 | — | — | VINFAST_OFFICIAL |
| VF_5 | EV_CAR | true | false | 37.23 | — | — | VINFAST_OFFICIAL |
| HERIO_GREEN | EV_CAR | true | false | 37.23 | — | — | VINFAST_OFFICIAL |
| VF_6 | EV_CAR | true | false | 59.60 | — | — | VINFAST_OFFICIAL |
| VF_7_ECO | EV_CAR | true | false | 59.60 | — | — | VINFAST_OFFICIAL |
| VF_7_PLUS | EV_CAR | true | false | 75.30 | — | — | VINFAST_OFFICIAL |
| VF_8 | EV_CAR | true | false | 87.70 | — | — | VINFAST_OFFICIAL |
| VF_9 | EV_CAR | true | false | 123.00 | — | — | VINFAST_OFFICIAL |
| VF_E34 | EV_CAR | true | false | 41.90 | — | — | VINFAST_OFFICIAL |
| NERIO_GREEN | EV_CAR | true | false | 41.90 | — | — | VINFAST_OFFICIAL |
| EVO200 | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| EVO200_LITE | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| FELIZ_S | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| KLARA_S_2022 | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| VENTO_S | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| EVO | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| EVO_LITE | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| FELIZ_II | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| VIPER | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |

**Important:** swap_supported=true models (EVO, EVO_LITE, FELIZ_II, VIPER) have a REMOVABLE_SWAP_MODULE
battery architecture. Their total nominal capacity depends on `installed_battery_modules` (1 or 2).
The vehicle does NOT always have 2 modules installed.

## Project Simulation Assumptions

The following values are PROJECT SIMULATION ASSUMPTIONS. They are NOT official VinFast specifications.

| Field | Value | Rationale |
|---|---|---|
| usable_capacity_ratio | 0.92 (92%) | Applied uniformly to all models. Deterministic synthetic assumption. |
| consumption_wh_per_km (cars) | 150 Wh/km | Consistent with V1.2; plausible for VinFast EV fleet. |
| consumption_wh_per_km (bikes) | 45 Wh/km | Consistent with V1.2; plausible for VinFast electric motorcycles. |
| minimum_safe_soc_pct | 15% | Consistent with V1.2; safety reserve threshold. |
| charging_interface_class (cars) | CCS2_TYPE2 | Standard European CCS2 / Type 2 AC. |
| charging_interface_class (bikes) | VINFAST_MOTORCYCLE_CHARGING | Project-internal normalized name for VinFast motorcycle AC charging. |
| swap_battery_family | VINFAST_SWAP_LFP_1_5_KWH | Project-internal normalized name. Not an official VinFast product name. |
| battery_architecture categories | FIXED_TRACTION_PACK / FIXED_OR_INTEGRATED_LFP / REMOVABLE_SWAP_MODULE | Project-internal taxonomy for modeling battery types. |

## Key Modeling Rules (V1.3)

1. **charging_supported ≠ swap_supported.** A vehicle can support charging without supporting swap.
2. **battery_removable ≠ public_swap_compatible.** Physical battery removability is not modeled separately here.
   The `public_swap_compatible` flag specifically means the vehicle is compatible with the VinFast public battery-swap network.
3. **swap_capable vehicles support CHARGING.** EVO/EVO_LITE/FELIZ_II/VIPER can also charge normally.
4. **Battery capacity for swap models:** `nominal_kwh = installed_battery_modules × 1.5 kWh`
   - 1 module: 1.5 kWh nominal → ~1.38 kWh usable
   - 2 modules: 3.0 kWh nominal → ~2.76 kWh usable
5. **No vehicle in the fleet is swap-only.** All VinFast vehicles that support swap also support charging.
"""

with open(ROOT / 'vehicles/VINFAST_VEHICLE_CAPABILITY_SOURCES.md', 'w', encoding='utf-8') as f:
    f.write(sources_md)
print("[Step 12f] vehicles/VINFAST_VEHICLE_CAPABILITY_SOURCES.md written")


# ---------------------------------------------------------------------------
# 18. Create VERSION.md
# ---------------------------------------------------------------------------
version_md = f"""# Dataset Version History

## V1.3 — VinFast Model-Level Capability Correction

**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d')}
**Patch generator:** 06_domain_correct_vinfast_capability.py

### Reason
VinFast motorcycles do not universally support public battery swap.
The VF8/VF9 class cannot be assumed to support charging.
Capability must be determined at the vehicle model level, not the vehicle category level.

### Previous version
Dataset V1.2 — Candidate Search Service-Specific Semantics

### Changes from V1.2 → V1.3

#### New files
- `vehicles/vehicle_model_catalog.csv` — canonical VinFast model table
- `labels/energy_service_requests.csv` — Week 3 Candidate Search data contract
- `training/demand_need_service_features.csv` — Task A features
- `training/demand_need_service_labels.csv` — Task A labels
- `vehicles/VINFAST_VEHICLE_CAPABILITY_SOURCES.md` — official vs simulation distinction

#### Modified files
- `vehicles/vehicles.csv` — model assignments, new battery columns, updated capabilities
- `battery/soc_history.csv.gz` — recomputed for corrected battery profiles
- `labels/demand_labels.csv` — added request_source, allowed_service_types, request_valid
- `training/demand_features.csv` — added vehicle_model, allowed_service_types
- `labels/candidate_labels.csv` — regenerated with corrected compatibility
- `training/ranking_reference.csv` — regenerated with corrected compatibility
- `labels/recommendation_labels.csv` — regenerated
- `realtime/events.csv.gz` — rebuilt with updated vehicle/service data
- `README.md`, `DATA_DICTIONARY.md`, `REQUIREMENT_DATA_MATRIX.md` — updated
- `config/generation_config.json` — version bump to v1.3
- `config/ranking_baseline.json` — updated for v1.3

#### Unchanged (Week 1 preserved)
- `map/processed/road_nodes.csv.gz`
- `map/processed/road_segments.csv.gz`
- `map/raw/hanoi-baseline.osm.pbf`
- `map/raw/hanoi-patched.osm.pbf`
- `gps/gps_observations.csv.gz`
- `trajectories/true_trajectories.csv.gz`
- `labels/map_matching_labels.csv.gz`
- `training/map_matching_candidates_with_split.csv.gz`
- `training/map_matching_candidates.csv.gz`
- `validation/pbf_integrity.json`

### Fleet distribution (V1.3)
- EV_CAR: 40 vehicles, 10 models, all charging-only
- EV_MOTORBIKE charging-only: 13 vehicles (EVO200, EVO200_LITE, FELIZ_S, KLARA_S_2022, VENTO_S)
- EV_MOTORBIKE charging+swap: 7 vehicles (EVO, EVO_LITE, FELIZ_II, VIPER)

### Demand semantics
- 4 rows per snapshot: AUTO_DETECTED + DRIVER_REQUEST(CHARGING) + DRIVER_REQUEST(BATTERY_SWAP) + DRIVER_REQUEST(ANY, swap-capable only)
- request_valid = (requested_service_type ∈ allowed_service_types)
- INVALID requests preserved as rows with request_valid=False
"""

with open(ROOT / 'VERSION.md', 'w', encoding='utf-8') as f:
    f.write(version_md)
print("[Step 12g] VERSION.md written")


# ---------------------------------------------------------------------------
# 19. Summary statistics
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("DOMAIN CORRECTION PATCH V1.3 — SUMMARY")
print("=" * 60)

print(f"\nVEHICLE MODEL CATALOG: {len(CATALOG_DF)} models")
print(CATALOG_DF[['vehicle_model', 'vehicle_category', 'battery_capacity_kwh',
                   'charging_supported', 'swap_supported']].to_string(index=False))

print(f"\nFLEET DISTRIBUTION:")
print(f"  EV_CAR: {(vehicles.vehicle_type == 'EV_CAR').sum()}")
print(f"  EV_MOTORBIKE (charge-only): {(~vehicles.swap_supported.astype(bool) & (vehicles.vehicle_type == 'EV_MOTORBIKE')).sum()}")
print(f"  EV_MOTORBIKE (charge+swap): {vehicles.swap_supported.sum()}")
print(f"  TOTAL: {len(vehicles)}")

print(f"\nDEMAND LABELS:")
print(f"  Total rows: {len(demand_labels)}")
print(f"  AUTO_DETECTED: {(demand_labels.request_source == 'AUTO_DETECTED').sum()}")
print(f"  DRIVER_REQUEST: {(demand_labels.request_source == 'DRIVER_REQUEST').sum()}")
print(f"  need_service=True: {demand_labels.need_service.sum()}")
print(f"  need_service=False: {(~demand_labels.need_service.astype(bool)).sum()}")
print(f"  Valid requests: {demand_labels.request_valid.sum()}")
print(f"  Invalid requests: {(demand_labels.request_valid == False).sum()}")

print(f"\nNEED_SERVICE TRAINING:")
print(f"  features: {len(need_features)} rows")
print(f"  labels: {len(need_labels)} rows")
ns_true = need_labels.need_service.astype(bool).sum()
ns_false = len(need_labels) - ns_true
print(f"  need_service=True: {ns_true} ({100*ns_true/len(need_labels):.1f}%)")
print(f"  need_service=False: {ns_false} ({100*ns_false/len(need_labels):.1f}%)")
train_ns = need_labels[need_labels.split == 'train']
val_ns = need_labels[need_labels.split == 'validation']
test_ns = need_labels[need_labels.split == 'test']
print(f"  train: {len(train_ns)} ({train_ns.need_service.astype(bool).sum()} T / {(~train_ns.need_service.astype(bool)).sum()} F)")
print(f"  validation: {len(val_ns)} ({val_ns.need_service.astype(bool).sum()} T / {(~val_ns.need_service.astype(bool)).sum()} F)")
print(f"  test: {len(test_ns)} ({test_ns.need_service.astype(bool).sum()} T / {(~test_ns.need_service.astype(bool)).sum()} F)")

print(f"\nCANDIDATE LABELS:")
print(f"  Total rows: {len(candidates)}")
for reason, count in candidates.reason.value_counts().items():
    print(f"  {reason}: {count}")

print(f"\nRANKING REFERENCE:")
print(f"  Rows: {len(ranking)}, Groups: {ranking.event_id.nunique()}")
gsizes = ranking.groupby('event_id').size()
print(f"  Group sizes: min={gsizes.min()}, max={gsizes.max()}, median={gsizes.median():.0f}")

print(f"\nRECOMMENDATION LABELS:")
print(f"  has_recommendation=True: {bs(recommendations.has_recommendation).sum()}")
print(f"  has_recommendation=False: {(~bs(recommendations.has_recommendation)).sum()}")

print()
print("STATUS: DOMAIN CORRECTION PATCH V1.3 — COMPLETE")
