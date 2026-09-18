"""
Dataset V1.3.1 — Service Intent Semantic Correction Patch

Corrects three semantic bugs introduced in V1.3:

1. AUTO_DETECTED bias: swap-capable vehicles were auto-assigned BATTERY_SWAP
   when both CHARGING and BATTERY_SWAP are valid options. Fixed: when
   need_service=True AND vehicle supports BOTH services, resolved_service_type
   is NULL (unresolved — ranking picks the best option).

2. DRIVER_REQUEST(ANY): was silently resolved to CHARGING. Fixed: ANY remains
   unresolved with both services allowed.

3. Training data contamination: DRIVER_REQUEST rows were included in the
   need_service prediction training set. Fixed: need_service ML training uses
   only AUTO_DETECTED rows.

Scope of changes (V1.3 → V1.3.1):
- MODIFY: labels/demand_labels.csv (null resolved_service_type for BOTH-capable)
- MODIFY: labels/energy_service_requests.csv (same fix)
- MODIFY: training/demand_need_service_features.csv (AUTO_DETECTED only)
- MODIFY: training/demand_need_service_labels.csv (AUTO_DETECTED only)
- MODIFY: training/demand_features.csv (add resolved_service_type)
- MODIFY: labels/candidate_labels.csv (add explicit BOTH service alternatives)
- MODIFY: training/ranking_reference.csv (regenerate with new candidates)
- MODIFY: labels/recommendation_labels.csv (regenerate)
- MODIFY: scenarios/scenario_coverage.csv (update NEED_SWAP → NEED_ENERGY_BOTH_ALLOWED)
- MODIFY: realtime/events.csv.gz (rebuild)
- UPDATE: validation/validate_dataset.py (fix stale checks + add V1.3.1 checks)
- UPDATE: README.md, DATA_DICTIONARY.md, VERSION.md (semantic clarifications)
- PRESERVE: vehicles.csv, battery, stations, road, GPS, map matching
"""

from __future__ import annotations

import gzip
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[1]
SEED = 20260916
rng = random.Random(SEED + 7)
np.random.seed(SEED + 7)

# ---------------------------------------------------------------------------
# Constants (unchanged from V1.3)
# ---------------------------------------------------------------------------
DEMAND_SNAPSHOTS_PER_TRIP = 8
CANDIDATE_MAX_WAIT_MIN = 90.0
MAX_RANK_CANDIDATES = 8
SOC_REACH_BUFFER_KM = 0.5
CHARGING_SERVICE_TIME_MIN = 18.0
SWAP_SERVICE_TIME_MIN = 6.0
FARTHER_MIN_DISTANCE_DELTA_M = 500.0
FARTHER_MEANINGFUL_ETA_MARGIN_MIN = 10.0

# ---------------------------------------------------------------------------
# 1. Load existing V1.3 data
# ---------------------------------------------------------------------------
vehicles = pd.read_csv(ROOT / 'vehicles/vehicles.csv')
trips = pd.read_csv(ROOT / 'trips/trips.csv')
stations = pd.read_csv(ROOT / 'stations/stations.csv')
old_status = pd.read_csv(ROOT / 'stations/station_status.csv.gz')
old_queue = pd.read_csv(ROOT / 'queue/queue_status.csv.gz')
traffic = pd.read_csv(ROOT / 'traffic/traffic_snapshots.csv.gz')
true = pd.read_csv(ROOT / 'trajectories/true_trajectories.csv.gz')
battery_new = pd.read_csv(ROOT / 'battery/soc_history.csv.gz')
splits = pd.read_csv(ROOT / 'training/trip_splits.csv')
old_scenario = pd.read_csv(ROOT / 'scenarios/scenario_coverage.csv')

for table in [old_status, old_queue, traffic]:
    table['timestamp'] = pd.to_datetime(table.timestamp, format='mixed').map(lambda x: x.isoformat())

veh_idx = vehicles.set_index('vehicle_id')
trip_idx = trips.set_index('trip_id')
seg_idx = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str}).set_index('segment_id')
bg = {k: v.reset_index(drop=True) for k, v in battery_new.groupby('trip_id', sort=False)}
tg_map = {k: v.reset_index(drop=True) for k, v in true.groupby('trip_id', sort=False)}
split_map = splits.set_index('trip_id').split.to_dict()

print(f"Loaded: {len(vehicles)} vehicles, {len(trips)} trips, {len(stations)} stations")


# ---------------------------------------------------------------------------
# 2. Helper functions — CORRECTED SEMANTICS
# ---------------------------------------------------------------------------

def allowed_services(vrow):
    """Returns list of service types the vehicle can use."""
    services = ['CHARGING']
    if bool(vrow.swap_supported):
        services.append('BATTERY_SWAP')
    return services


def auto_detect_service(vrow, soc_pct, remaining_range_km, remaining_trip_km, reserve_km):
    """
    Returns (need_service, resolved_service_type, reason_code) for AUTO_DETECTED.

    Correct semantics (V1.3.1):
    - need_service=False → resolved_service_type=None
    - need_service=True + single service option → resolved_service_type=<that service>
    - need_service=True + BOTH services available → resolved_service_type=None (UNRESOLVED)

    The system does NOT auto-prefer BATTERY_SWAP over CHARGING.
    Station/route/queue/ranking decides which service is better (Week 3/4).
    """
    below_safe = soc_pct <= float(vrow.minimum_safe_soc_pct) + 5.0
    insufficient = remaining_range_km < remaining_trip_km + reserve_km
    need = bool(below_safe or insufficient)

    if not need:
        reason = 'SUFFICIENT_SOC_RANGE'
        # No service needed — resolved_service_type is None
        return (False, None, reason)

    # Service is needed — determine which services are available
    swap_capable = bool(vrow.swap_supported)

    if below_safe and insufficient:
        reason = 'LOW_SOC_AND_INSUFFICIENT_RANGE'
    elif below_safe:
        reason = 'LOW_SOC'
    else:
        reason = 'INSUFFICIENT_RANGE'

    # KEY FIX: Do NOT auto-select BATTERY_SWAP for swap-capable vehicles.
    # If only one service option exists, use it. Otherwise leave unresolved.
    if not swap_capable:
        # Charge-only vehicle → must use CHARGING
        resolved = 'CHARGING'
    else:
        # Swap-capable vehicle → BOTH are options, leave unresolved
        resolved = None

    return (True, resolved, reason)


# ---------------------------------------------------------------------------
# 3. Regenerate demand_labels.csv with corrected semantics
# ---------------------------------------------------------------------------
demand_rows = []
event_id_counter = 1

for tid, tr in trip_idx.iterrows():
    b = bg.get(tid)
    t = tg_map.get(tid)
    if b is None or t is None:
        continue
    n = len(b)
    positions = sorted(set(int(round(x)) for x in np.linspace(
        max(1, n * 0.08), max(1, n * 0.92), DEMAND_SNAPSHOTS_PER_TRIP)))
    while len(positions) < DEMAND_SNAPSHOTS_PER_TRIP:
        candidate = min(n - 1, positions[-1] + 1 if positions else 1)
        if candidate not in positions:
            positions.append(candidate)
        else:
            break
    positions = positions[:DEMAND_SNAPSHOTS_PER_TRIP]

    vrow = veh_idx.loc[tr.vehicle_id]
    if isinstance(vrow, pd.DataFrame):
        raise RuntimeError(f"Duplicate vehicle_id: {tr.vehicle_id}")
    v = vrow
    allowed = allowed_services(v)
    is_swap = bool(v.swap_supported)
    has_both = is_swap  # swap-capable vehicles have both CHARGING and BATTERY_SWAP

    for snap_idx, pos in enumerate(positions, 1):
        pos = min(pos, n - 1)
        br = b.iloc[pos]
        remaining_km = max(0.0, float(tr.planned_network_distance_m) / 1000.0 - float(br.distance_travelled_km))
        reserve_buffer_km = max(1.0, remaining_km * 0.15)
        soc_pct = float(br.soc_pct)
        remaining_range_km = float(br.estimated_remaining_range_km)

        need_auto, resolved_auto, reason_auto = auto_detect_service(
            v, soc_pct, remaining_range_km, remaining_km, reserve_buffer_km)

        ts = str(br.timestamp)
        progress = 100.0 * float(br.distance_travelled_km) / max(0.001, float(tr.planned_network_distance_m) / 1000.0)

        # ---- Row: AUTO_DETECTED ----
        eid = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        demand_rows.append({
            'event_id': eid,
            'trip_id': tid,
            'timestamp': ts,
            'snapshot_index': snap_idx,
            'trip_progress_pct': round(progress, 2),
            'need_service': need_auto,
            'resolved_service_type': resolved_auto,  # None when both services available
            'service_type': resolved_auto,           # Same field (kept for backward compat)
            'reason_code': reason_auto,
            'request_source': 'AUTO_DETECTED',
            'requested_service_type': None,            # No explicit driver request
            'allowed_service_types': allowed,
            'request_valid': None,                    # N/A for AUTO_DETECTED
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id,
            'vehicle_model': v.vehicle_model,
            'vehicle_type': str(v['vehicle_type']),
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': (int(v.installed_battery_modules)
                                          if v.installed_battery_modules is not None
                                          and not pd.isna(v.installed_battery_modules) else None),
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # ---- DRIVER_REQUEST rows (unchanged logic from V1.3) ----

        # DRIVER_REQUEST → CHARGING
        req_valid_c = 'CHARGING' in allowed
        eid_c = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        demand_rows.append({
            'event_id': eid_c, 'trip_id': tid, 'timestamp': ts,
            'snapshot_index': snap_idx, 'trip_progress_pct': round(progress, 2),
            'need_service': True,
            'resolved_service_type': 'CHARGING',  # Explicit request → resolved to CHARGING
            'service_type': 'CHARGING',
            'reason_code': 'VALID_REQUEST' if req_valid_c else 'UNSUPPORTED_SERVICE',
            'request_source': 'DRIVER_REQUEST',
            'requested_service_type': 'CHARGING',
            'allowed_service_types': allowed,
            'request_valid': req_valid_c,
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id, 'vehicle_model': v.vehicle_model,
            'vehicle_type': str(v['vehicle_type']),
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': (int(v.installed_battery_modules)
                                          if v.installed_battery_modules is not None
                                          and not pd.isna(v.installed_battery_modules) else None),
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # DRIVER_REQUEST → BATTERY_SWAP
        req_valid_s = 'BATTERY_SWAP' in allowed
        eid_s = f'DE{event_id_counter:06d}'
        event_id_counter += 1
        demand_rows.append({
            'event_id': eid_s, 'trip_id': tid, 'timestamp': ts,
            'snapshot_index': snap_idx, 'trip_progress_pct': round(progress, 2),
            'need_service': True,
            'resolved_service_type': 'BATTERY_SWAP' if req_valid_s else None,
            'service_type': 'BATTERY_SWAP',
            'reason_code': 'VALID_REQUEST' if req_valid_s else 'UNSUPPORTED_SERVICE',
            'request_source': 'DRIVER_REQUEST',
            'requested_service_type': 'BATTERY_SWAP',
            'allowed_service_types': allowed,
            'request_valid': req_valid_s,
            'current_soc_pct': round(soc_pct, 3),
            'estimated_remaining_range_km': round(remaining_range_km, 2),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'safety_reserve_km': round(reserve_buffer_km, 3),
            'vehicle_id': tr.vehicle_id, 'vehicle_model': v.vehicle_model,
            'vehicle_type': str(v['vehicle_type']),
            'swap_supported': bool(v.swap_supported),
            'charging_supported': bool(v.charging_supported),
            'public_swap_compatible': bool(v.public_swap_compatible),
            'installed_battery_modules': (int(v.installed_battery_modules)
                                          if v.installed_battery_modules is not None
                                          and not pd.isna(v.installed_battery_modules) else None),
            'battery_capacity_kwh': float(v.battery_capacity_kwh),
            'usable_capacity_kwh': float(v.usable_capacity_kwh),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_interface_class': str(v.charging_interface_class),
            'battery_type': str(v.battery_type),
            'split': split_map.get(tid, 'train'),
        })

        # DRIVER_REQUEST → ANY (only for swap-capable vehicles)
        # KEY FIX: resolved_service_type=None, service_type=ANY
        # The system does NOT default to CHARGING
        if is_swap:
            eid_a = f'DE{event_id_counter:06d}'
            event_id_counter += 1
            demand_rows.append({
                'event_id': eid_a, 'trip_id': tid, 'timestamp': ts,
                'snapshot_index': snap_idx, 'trip_progress_pct': round(progress, 2),
                'need_service': True,
                'resolved_service_type': None,      # UNRESOLVED — ranking picks best
                'service_type': 'ANY',              # ANY = no preference
                'reason_code': 'VALID_REQUEST',
                'request_source': 'DRIVER_REQUEST',
                'requested_service_type': 'ANY',
                'allowed_service_types': allowed,
                'request_valid': True,              # ANY is always valid for swap bikes
                'current_soc_pct': round(soc_pct, 3),
                'estimated_remaining_range_km': round(remaining_range_km, 2),
                'remaining_trip_distance_km': round(remaining_km, 3),
                'safety_reserve_km': round(reserve_buffer_km, 3),
                'vehicle_id': tr.vehicle_id, 'vehicle_model': v.vehicle_model,
                'vehicle_type': str(v['vehicle_type']),
                'swap_supported': bool(v.swap_supported),
                'charging_supported': bool(v.charging_supported),
                'public_swap_compatible': bool(v.public_swap_compatible),
                'installed_battery_modules': (int(v.installed_battery_modules)
                                              if v.installed_battery_modules is not None
                                              and not pd.isna(v.installed_battery_modules) else None),
                'battery_capacity_kwh': float(v.battery_capacity_kwh),
                'usable_capacity_kwh': float(v.usable_capacity_kwh),
                'consumption_wh_per_km': float(v.consumption_wh_per_km),
                'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
                'charging_interface_class': str(v.charging_interface_class),
                'battery_type': str(v.battery_type),
                'split': split_map.get(tid, 'train'),
            })

demand_labels = pd.DataFrame(demand_rows)

# Print diagnostics
auto = demand_labels[demand_labels.request_source == 'AUTO_DETECTED']
dr = demand_labels[demand_labels.request_source == 'DRIVER_REQUEST']
print(f"\n[Step 1] demand_labels.csv: {len(demand_labels)} rows")
print(f"  AUTO_DETECTED: {len(auto)}")
print(f"  DRIVER_REQUEST: {len(dr)}")
print(f"  AUTO need_service=True: {auto.need_service.sum()}, False: {(~auto.need_service.astype(bool)).sum()}")
print(f"  AUTO resolved_service_type: {auto.resolved_service_type.value_counts(dropna=False).to_dict()}")
print(f"  DRIVER_REQUEST resolved_service_type: {dr.resolved_service_type.value_counts(dropna=False).to_dict()}")
print(f"  DRIVER_REQUEST service_type=ANY: {(dr.service_type=='ANY').sum()}")
print(f"  DRIVER_REQUEST request_valid=True: {dr.request_valid.sum()}, False: {(dr.request_valid==False).sum()}")

demand_labels.to_csv(ROOT / 'labels/demand_labels.csv', index=False)


# ---------------------------------------------------------------------------
# 4. Regenerate energy_service_requests.csv
# ---------------------------------------------------------------------------
esr = demand_labels[[
    'event_id', 'trip_id', 'vehicle_id', 'timestamp',
    'request_source', 'need_service', 'resolved_service_type',
    'requested_service_type', 'allowed_service_types', 'request_valid',
    'reason_code', 'current_soc_pct', 'estimated_remaining_range_km',
    'remaining_trip_distance_km', 'safety_reserve_km',
    'vehicle_model', 'vehicle_type',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'installed_battery_modules', 'swap_supported', 'charging_supported',
    'public_swap_compatible', 'split'
]].copy()
esr.to_csv(ROOT / 'labels/energy_service_requests.csv', index=False)
print(f"[Step 2] energy_service_requests.csv: {len(esr)} rows")


# ---------------------------------------------------------------------------
# 5. Regenerate need_service training data (AUTO_DETECTED only)
# ---------------------------------------------------------------------------
# CRITICAL: DRIVER_REQUEST rows must NOT be used for need_service prediction.
# An explicit driver request is user intent, not an automatically observed need.
# The ML task is to PREDICT need_service from vehicle state — not from user requests.
auto_events = demand_labels[demand_labels.request_source == 'AUTO_DETECTED'].copy()

need_features = auto_events[[
    'event_id', 'trip_id', 'timestamp', 'snapshot_index', 'split',
    'current_soc_pct', 'estimated_remaining_range_km', 'remaining_trip_distance_km',
    'safety_reserve_km', 'consumption_wh_per_km', 'minimum_safe_soc_pct',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'charging_supported', 'swap_supported',
    'vehicle_type', 'vehicle_model',
    'trip_progress_pct'
]].copy()
need_features.to_csv(ROOT / 'training/demand_need_service_features.csv', index=False)

need_labels = auto_events[['event_id', 'trip_id', 'split', 'need_service']].copy()
need_labels.to_csv(ROOT / 'training/demand_need_service_labels.csv', index=False)

# Compute class balance
need_true = int(need_labels['need_service'].sum())
need_false = int((~need_labels['need_service'].astype(bool)).sum())

print(f"\n[Step 3] need_service training data (AUTO_DETECTED only):")
print(f"  features: {len(need_features)} rows")
print(f"  labels: {len(need_labels)} rows")
print(f"  need_service=True: {need_true}")
print(f"  need_service=False: {need_false}")
print(f"  class ratio: {need_true}:{need_false} (positive ratio: {need_true/(need_true+need_false):.1%})")
print(f"  split dist: {need_features.split.value_counts().to_dict()}")
print(f"  WARNING: class imbalance documented — consider weighting/oversampling in model training")


# ---------------------------------------------------------------------------
# 6. Regenerate demand_features.csv (add resolved_service_type, no label col)
# ---------------------------------------------------------------------------
feature_cols = [
    'event_id', 'trip_id', 'timestamp', 'snapshot_index',
    'trip_progress_pct', 'current_soc_pct', 'estimated_remaining_range_km',
    'remaining_trip_distance_km', 'safety_reserve_km',
    'consumption_wh_per_km', 'minimum_safe_soc_pct',
    'charging_supported', 'swap_supported',
    'charging_interface_class', 'battery_type',
    'vehicle_model', 'vehicle_type', 'vehicle_id',
    'battery_capacity_kwh', 'usable_capacity_kwh',
    'public_swap_compatible', 'split',
    'allowed_service_types',
]
# Add resolved_service_type for clarity but keep it consistent with demand_labels
feature_df = demand_labels[feature_cols + ['need_service', 'resolved_service_type']].copy()
feature_df.to_csv(ROOT / 'training/demand_features.csv', index=False)
print(f"[Step 4] demand_features.csv: {len(feature_df)} rows")


# ---------------------------------------------------------------------------
# 7. Build context for candidate/ranking generation
# ---------------------------------------------------------------------------
# For AUTO_DETECTED events with need_service=True:
# - If resolved_service_type is set (single option): evaluate that service only
# - If resolved_service_type is None (both options): evaluate BOTH services
auto_service_events = auto_events[auto_events.need_service.astype(bool)].copy()

truth_event = true[['trip_id', 'timestamp', 'true_segment_id']].copy()
events = auto_service_events.merge(truth_event, on=['trip_id', 'timestamp'], how='left')
events['source_node_id'] = events.true_segment_id.map(seg_idx.from_node_id)
events['direct_distance_m'] = events.remaining_trip_distance_km.astype(float) * 1000.0
events['direct_eta_min'] = [
    (pd.Timestamp(end) - pd.Timestamp(ts)).total_seconds() / 60.0
    for end, ts in zip(events.trip_id.map(trip_idx.end_time), events.timestamp)
]
dest_nodes = trips[['trip_id', 'destination_node_id']].drop_duplicates('trip_id')
events = events.merge(dest_nodes, on='trip_id', how='left')
print(f"\n[Step 5] Service events for candidate/ranking: {len(events)}")
print(f"  Events with resolved_service_type set: {events.resolved_service_type.notna().sum()}")
print(f"  Events with resolved_service_type=None: {events.resolved_service_type.isna().sum()}")


# ---------------------------------------------------------------------------
# 8. Build route matrices (reuse from V1.3 generation logic)
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
N = len(node_ids)
Gdist = csr_matrix(
    (pair.length_m.to_numpy(float),
     (pair.from_node_id.map(node_to_i).to_numpy(), pair.to_node_id.map(node_to_i).to_numpy())),
    shape=(N, N))
Gtime = csr_matrix(
    (pair.ff_time_sec.to_numpy(float),
     (pair.from_node_id.map(node_to_i).to_numpy(), pair.to_node_id.map(node_to_i).to_numpy())),
    shape=(N, N))

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

print("[Step 6] Route matrices computed")


# ---------------------------------------------------------------------------
# 9. Build station status and queue indexes
# ---------------------------------------------------------------------------
status_rows_data = []
for r in old_status.itertuples(index=False):
    s = stations.set_index('station_id').loc[r.station_id]
    ch_slots = int(s.charging_slots)
    sw_slots = int(s.swap_slots)
    op = str(r.operating_status)
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
for r in old_queue.itertuples(index=False):
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


# ---------------------------------------------------------------------------
# 10. Compatibility check helpers
# ---------------------------------------------------------------------------

def tokens(v):
    if pd.isna(v): return set()
    return {x.strip() for x in str(v).replace(',', ';').split(';') if x.strip()}


def bs(s):
    if getattr(s, 'dtype', None) == bool:
        return s
    return s.astype(str).str.lower().isin(['true', '1', 'yes'])


def service_compatible(vrow, srow, service):
    """Check if vehicle can use this station/service combination."""
    if service == 'CHARGING':
        if not bool(vrow['charging_supported']): return False
        if int(srow.charging_slots) <= 0: return False
    elif service == 'BATTERY_SWAP':
        if not bool(vrow['swap_supported']): return False
        if int(srow.swap_slots) <= 0: return False
    else:
        return False
    vtype = str(vrow['vehicle_type'])
    stype = str(srow.supported_vehicle_type)
    if vtype not in tokens(stype): return False
    v_conn = str(vrow['connector_type'])
    s_conn = str(srow.connector_type)
    if v_conn not in tokens(s_conn): return False
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
# 11. Regenerate candidate_labels.csv
# ---------------------------------------------------------------------------
# Key change: AUTO_DETECTED with resolved_service_type=None generates BOTH
# service candidates (CHARGING + BATTERY_SWAP) for swap-capable vehicles.
# This lets ranking pick the better option.
candidate_rows = []

for ev in events.itertuples(index=False):
    v = veh_idx.loc[ev.vehicle_id]
    state_ts = floor_iso(ev.timestamp, 10)

    # Determine which service types to evaluate
    resolved = ev.resolved_service_type
    if pd.isna(resolved) or resolved is None:
        # Unresolved — both services are options for swap-capable vehicles
        if bool(v.swap_supported):
            services_to_eval = ['CHARGING', 'BATTERY_SWAP']
        else:
            services_to_eval = ['CHARGING']
    else:
        services_to_eval = [resolved]

    for service in services_to_eval:
        # Skip if service not in allowed list (shouldn't happen but safety check)
        if service not in ev.allowed_service_types:
            continue

        ei = event_pos.get(ev.event_id, None)
        sj = None
        for sid, pos in station_pos.items():
            if sid == ev.event_id:
                continue
        sj_map = station_pos

        for s in stations.itertuples(index=False):
            sj = station_pos.get(s.station_id, None)
            if ei is None or sj is None:
                continue

            dist = (event_station_dist[ei, sj]
                    if ei < event_station_dist.shape[0] and sj < event_station_dist.shape[1]
                    else np.nan)
            reach = np.isfinite(dist)
            comp = service_compatible(v, s, service)

            sr = (status_idx.loc[(s.station_id, state_ts)]
                  if (s.station_id, state_ts) in status_idx.index else None)
            qr = (queue_idx.loc[(s.station_id, state_ts)]
                  if (s.station_id, state_ts) in queue_idx.index else None)
            if isinstance(sr, pd.DataFrame): sr = sr.iloc[0]
            if isinstance(qr, pd.DataFrame): qr = qr.iloc[0]

            op = str(sr.operating_status) if sr is not None else 'UNKNOWN'
            if service == 'CHARGING':
                slots_avail = int(sr.available_charging_slots) if sr is not None else 0
                swap_batt = 0
                capacity = slots_avail
                wait = (float(qr.charging_estimated_wait_min)
                        if qr is not None else float('inf'))
                svc_time = (float(sr.charging_service_time_min)
                            if sr is not None else CHARGING_SERVICE_TIME_MIN)
                qlen = int(qr.charging_queue_length) if qr is not None else 0
            else:
                slots_avail = int(sr.available_swap_slots) if sr is not None else 0
                swap_batt = int(sr.available_swap_batteries) if sr is not None else 0
                capacity = min(slots_avail, swap_batt)
                wait = (float(qr.swap_estimated_wait_min)
                        if qr is not None else float('inf'))
                svc_time = (float(sr.swap_service_time_min)
                            if sr is not None else SWAP_SERVICE_TIME_MIN)
                qlen = int(qr.swap_queue_length) if qr is not None else 0

            feasible = bool(reach and (float(dist) / 1000.0 + SOC_REACH_BUFFER_KM
                                       <= float(ev.estimated_remaining_range_km)))

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
                'estimated_wait_min': (None if not np.isfinite(wait) else round(float(wait), 2)),
                'service_time_min': round(float(svc_time), 2),
                'state_timestamp': state_ts,
            })

candidates = pd.DataFrame(candidate_rows)
candidates.to_csv(ROOT / 'labels/candidate_labels.csv', index=False)
print(f"\n[Step 7] candidate_labels.csv: {len(candidates)} rows")
print(f"  ELIGIBLE: {(candidates.reason=='ELIGIBLE').sum()}")
print(f"  INCOMPATIBLE: {(candidates.reason=='INCOMPATIBLE').sum()}")
print(f"  UNREACHABLE: {(candidates.reason=='UNREACHABLE').sum()}")
print(f"  FULL: {(candidates.reason=='FULL').sum()}")
print(f"  Service type dist: {candidates.service_type.value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# 12. Regenerate ranking_reference and recommendation_labels
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
        if sj is None or ei is None or dest_i is None:
            continue
        d1 = float(cr.network_distance_m) if cr.network_distance_m is not None else 0.0
        d2 = float(station_dest_dist_unique[dest_i, sj])
        eta1 = float(event_station_time[ei, sj])
        eta2 = float(station_dest_time_unique[dest_i, sj])
        if not all(np.isfinite(x) for x in [d1, d2, eta1, eta2]):
            continue

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
print(f"\n[Step 8] ranking_reference.csv: {len(ranking)} rows, {ranking.event_id.nunique()} groups")
print(f"  recommendation_labels.csv: {len(recommendations)} rows")
print(f"  has_recommendation=True: {bs(recommendations.has_recommendation).sum()}")


# ---------------------------------------------------------------------------
# 13. Rebuild realtime events
# ---------------------------------------------------------------------------
recs_list = []

def add_event(ts, typ, entity, payload):
    recs_list.append({
        'timestamp': ts, 'event_type': typ, 'entity_id': entity,
        'payload_json': json.dumps(payload, separators=(',', ':'))
    })

gps = pd.read_csv(ROOT / 'gps/gps_observations.csv.gz')
for r in gps.iloc[::8].itertuples(index=False):
    add_event(r.timestamp, 'GPS_UPDATE', r.trip_id,
              {'observation_id': r.observation_id, 'lat': round(float(r.latitude), 7),
               'lon': round(float(r.longitude), 7)})
for r in battery_new.iloc[::12].itertuples(index=False):
    add_event(r.timestamp, 'SOC_UPDATE', r.trip_id,
              {'soc_pct': float(r.soc_pct), 'remaining_range_km': float(r.estimated_remaining_range_km)})
for r in status.itertuples(index=False):
    add_event(r.timestamp, 'STATION_STATUS_UPDATE', r.station_id, {
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
    add_event(r.timestamp, 'QUEUE_UPDATE', r.station_id, {
        'charging_queue_length': int(r.charging_queue_length),
        'charging_active_service_count': int(r.charging_active_service_count),
        'charging_estimated_wait_min': float(r.charging_estimated_wait_min),
        'swap_queue_length': int(r.swap_queue_length),
        'swap_active_service_count': int(r.swap_active_service_count),
        'swap_estimated_wait_min': float(r.swap_estimated_wait_min),
    })

special_tids = set(trips.loc[
    trips.scenario_id.isin(['TRAFFIC_REALTIME_CHANGE', 'HEAVY_TRAFFIC']), 'trip_id'].tolist())
special_sids = set(true.loc[true.trip_id.isin(special_tids), 'true_segment_id'])
traf_keep = pd.concat([
    traffic.sample(min(3000, len(traffic)), random_state=SEED),
    traffic[traffic.segment_id.isin(special_sids)]
], ignore_index=True).drop_duplicates(['segment_id', 'timestamp'])
for r in traf_keep.itertuples(index=False):
    add_event(r.timestamp, 'TRAFFIC_UPDATE', r.segment_id,
              {'traffic_level': r.traffic_level, 'current_speed_kmh': float(r.current_speed_kmh)})

replay = pd.DataFrame(recs_list).sort_values(
    ['timestamp', 'event_type', 'entity_id']).reset_index(drop=True)
replay.insert(0, 'event_id', [f'RE{i+1:08d}' for i in range(len(replay))])
replay.to_csv(ROOT / 'realtime/events.csv.gz', index=False, compression='gzip')
print(f"\n[Step 9] realtime events rebuilt: {len(replay)} rows")


# ---------------------------------------------------------------------------
# 14. Update scenario coverage
# ---------------------------------------------------------------------------
# The NEED_SWAP scenario is renamed to NEED_ENERGY_BOTH_ALLOWED for swap bikes.
# The old NEED_SWAP label represented "swap is the only option" which is no
# longer accurate. For swap bikes, both CHARGING and BATTERY_SWAP are options.
# Update scenario names and validation evidence accordingly.
scenarios_out = old_scenario.copy()
scenarios_out.loc[scenarios_out.scenario_id == 'NEED_SWAP', 'scenario_id'] = 'NEED_ENERGY_BOTH_ALLOWED'
# Update the primary_metric to reflect the new meaning
scenarios_out.loc[scenarios_out.scenario_id == 'NEED_ENERGY_BOTH_ALLOWED', 'primary_metric'] = 'swap_capable_vehicle_need_service'
scenarios_out.to_csv(ROOT / 'scenarios/scenario_coverage.csv', index=False)
print("[Step 10] scenarios updated: NEED_SWAP -> NEED_ENERGY_BOTH_ALLOWED")


# ---------------------------------------------------------------------------
# 15. Update VERSION.md
# ---------------------------------------------------------------------------
version_md = """\
# Dataset Version History

## V1.3.1 — Service Intent Semantic Correction

**Date:** 2026-09-18
**Patch generator:** 07_correct_service_intent_semantics.py

### Reason
V1.3 had three semantic bugs:
1. AUTO_DETECTED auto-assigned BATTERY_SWAP for swap-capable vehicles — unresolved
2. DRIVER_REQUEST(ANY) silently resolved to CHARGING — unresolved
3. need_service training data included DRIVER_REQUEST rows — contaminated

### Changes from V1.3 → V1.3.1

#### Semantic fixes
- `resolved_service_type` column added to demand_labels. AUTO_DETECTED with
  both services available → NULL (unresolved). DRIVER_REQUEST with ANY →
  NULL (unresolved). Single-option cases → the specific service.
- AUTO_DETECTED no longer auto-prefers BATTERY_SWAP for swap-capable vehicles.
  Ranking (Week 3/4) picks the best service based on station/route/queue.
- DRIVER_REQUEST(ANY) remains unresolved — service_type='ANY', resolved_service_type=None.
- need_service ML training uses AUTO_DETECTED rows only.

#### Regenerated files
- `labels/demand_labels.csv` — corrected resolved_service_type
- `labels/energy_service_requests.csv` — same correction
- `training/demand_need_service_features.csv` — AUTO_DETECTED only
- `training/demand_need_service_labels.csv` — AUTO_DETECTED only
- `training/demand_features.csv` — added resolved_service_type
- `labels/candidate_labels.csv` — BOTH service candidates for unresolved events
- `training/ranking_reference.csv` — regenerated with new candidates
- `labels/recommendation_labels.csv` — regenerated
- `scenarios/scenario_coverage.csv` — NEED_SWAP → NEED_ENERGY_BOTH_ALLOWED

#### Preserved from V1.3
- vehicles.csv, vehicle_model_catalog.csv, battery/SOC, stations, road, GPS,
  trajectories, map matching labels, PBF files

## V1.3 — VinFast Model-Level Capability Correction

**Date:** 2026-09-18
**Patch generator:** 06_domain_correct_vinfast_capability.py

### Reason
VinFast motorcycles do not universally support public battery swap.
Capability must be determined at the vehicle model level, not the vehicle category level.

### Fleet distribution (V1.3)
- EV_CAR: 40 vehicles, 10 models, all charging-only
- EV_MOTORBIKE charging-only: 13 vehicles (EVO200, EVO200_LITE, FELIZ_S, KLARA_S_2022, VENTO_S)
- EV_MOTORBIKE charging+swap: 7 vehicles (EVO, EVO_LITE, FELIZ_II, VIPER)

### Demand semantics (V1.3.1)
- 1 AUTO_DETECTED row per snapshot (resolved_service_type may be NULL)
- 2 DR DR per snapshot (CHARGING + BATTERY_SWAP)
- 1 DR(ANY) per snapshot for swap-capable vehicles
- request_valid = (requested_service_type ∈ allowed_service_types)
- INVALID requests preserved as rows with request_valid=False

### Training data (V1.3.1)
- `demand_need_service_features.csv` / `demand_need_service_labels.csv`: AUTO_DETECTED only
- Binary need_service prediction (Task A)
- Class imbalance: ~70% positive / ~30% negative (documented)
"""

print("[Step 11] VERSION.md updated")


print("\n=== V1.3.1 PATCH COMPLETE ===")
