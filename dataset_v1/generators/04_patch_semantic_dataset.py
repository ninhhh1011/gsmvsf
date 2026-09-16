from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path('/mnt/data/dataset_v1')
SEED = 20260916
rng = random.Random(SEED + 4)
np.random.seed(SEED + 4)

DEMAND_SNAPSHOTS_PER_TRIP = 8
CANDIDATE_MAX_WAIT_MIN = 90.0
RANKING_GROUP_SIZE = 8
NEAR_TIE_THRESHOLD_MIN = 3.0
LONG_QUEUE_THRESHOLD_MIN = 30.0
SOC_REACH_BUFFER_KM = 0.5

FORCE_SERVICE_SCENARIOS = {
    'LOW_SOC', 'NEED_CHARGING', 'NEED_SWAP', 'NEAREST_FULL', 'STATION_OFFLINE',
    'INCOMPATIBLE_STATION', 'LONG_QUEUE', 'FARTHER_BUT_FASTER', 'HEAVY_TRAFFIC',
    'INSUFFICIENT_RANGE', 'QUEUE_REALTIME_CHANGE', 'TRAFFIC_REALTIME_CHANGE',
    'STATION_STATUS_CHANGE', 'NO_AVAILABLE_STATION', 'NEAR_TIE_STATIONS'
}

STATUS_PATCH_KEYS: set[tuple[str, str]] = set()
TRAFFIC_PATCH_KEYS: set[tuple[str, str]] = set()
SCENARIO_TARGETS: dict[str, list[dict]] = defaultdict(list)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def hav_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def heading(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def parse_linestring_endpoints(wkt: str):
    nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', str(wkt))]
    if len(nums) < 4:
        return None
    return (nums[0], nums[1]), (nums[-2], nums[-1])


def projected_to_segment(lat, lon, wkt):
    ep = parse_linestring_endpoints(wkt)
    if not ep:
        return lat, lon
    (x1, y1), (x2, y2) = ep
    # local equirectangular coordinates around GPS point
    scale_x = 111320.0 * max(0.2, math.cos(math.radians(lat)))
    scale_y = 111320.0
    ax, ay = (x1 - lon) * scale_x, (y1 - lat) * scale_y
    bx, by = (x2 - lon) * scale_x, (y2 - lat) * scale_y
    vx, vy = bx - ax, by - ay
    denom = vx * vx + vy * vy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, -(ax * vx + ay * vy) / denom))
    px, py = ax + t * vx, ay + t * vy
    return lat + py / scale_y, lon + px / scale_x


def split_tokens(value):
    if pd.isna(value):
        return set()
    return {x.strip() for x in str(value).split(';') if x.strip()}


def static_compatible(vehicle, station, service_type: str) -> bool:
    station_types = split_tokens(station.station_type.replace('_', ';'))
    # explicit station type check
    if service_type == 'CHARGING':
        if not bool(vehicle.charging_supported) or 'CHARGING' not in str(station.station_type):
            return False
    elif service_type == 'BATTERY_SWAP':
        if not bool(vehicle.swap_supported) or 'SWAP' not in str(station.station_type):
            return False
    else:
        return False
    if str(vehicle.vehicle_type) not in split_tokens(station.supported_vehicle_type):
        return False
    if str(vehicle.connector_type) not in split_tokens(station.connector_type):
        return False
    if service_type == 'BATTERY_SWAP':
        if pd.isna(station.battery_type) or str(vehicle.battery_type) not in split_tokens(station.battery_type):
            return False
    return True


def state_key(ts: pd.Timestamp, minutes: int) -> str:
    return ts.floor(f'{minutes}min').isoformat()


def set_queue_state(status, queue, station_id, ts_iso, target_wait_min, total_slots, service_time, keep_available=1):
    sm = (status.station_id.eq(station_id) & status.timestamp.eq(ts_iso))
    qm = (queue.station_id.eq(station_id) & queue.timestamp.eq(ts_iso))
    if not sm.any() or not qm.any():
        return
    avail = max(1, min(int(keep_available), max(1, int(total_slots) - 1)))
    occupied = max(1, int(total_slots) - avail)
    active = max(1, min(occupied, int(total_slots)))
    qlen = int(math.ceil(max(0.0, target_wait_min) * active / max(1.0, float(service_time))))
    actual_wait = qlen * float(service_time) / active if qlen else 0.0
    status.loc[sm, ['operating_status', 'available_slots', 'occupied_slots', 'queue_length']] = ['OPEN', avail, occupied, qlen]
    queue.loc[qm, ['queue_length', 'active_service_count', 'average_service_time_min', 'estimated_wait_min']] = [qlen, active, service_time, round(actual_wait, 2)]
    STATUS_PATCH_KEYS.add((station_id, ts_iso))


def set_station_open(status, queue, station, ts_iso, available=1, queue_wait=0.0):
    sm = (status.station_id.eq(station.station_id) & status.timestamp.eq(ts_iso))
    qm = (queue.station_id.eq(station.station_id) & queue.timestamp.eq(ts_iso))
    if not sm.any() or not qm.any():
        return
    total = int(station.total_slots)
    avail = max(1, min(int(available), total))
    occupied = max(0, total - avail)
    status.loc[sm, ['operating_status', 'available_slots', 'occupied_slots']] = ['OPEN', avail, occupied]
    if 'SWAP' in str(station.station_type):
        status.loc[sm, 'available_swap_batteries'] = max(1, int(station.swap_slots))
    if queue_wait <= 0:
        status.loc[sm, 'queue_length'] = 0
        queue.loc[qm, ['queue_length', 'active_service_count', 'average_service_time_min', 'estimated_wait_min']] = [0, max(1, occupied), int(status.loc[sm, 'estimated_service_time_min'].iloc[0]), 0.0]
    else:
        svc = int(status.loc[sm, 'estimated_service_time_min'].iloc[0])
        set_queue_state(status, queue, station.station_id, ts_iso, queue_wait, total, svc, keep_available=avail)
    STATUS_PATCH_KEYS.add((station.station_id, ts_iso))


def set_station_full(status, queue, station, ts_iso):
    sm = (status.station_id.eq(station.station_id) & status.timestamp.eq(ts_iso))
    qm = (queue.station_id.eq(station.station_id) & queue.timestamp.eq(ts_iso))
    if not sm.any() or not qm.any():
        return
    total = int(station.total_slots)
    service = int(status.loc[sm, 'estimated_service_time_min'].iloc[0])
    qlen = 3
    active = max(1, total)
    wait = round(qlen * service / active, 2)
    status.loc[sm, ['operating_status', 'available_slots', 'occupied_slots', 'queue_length']] = ['OPEN', 0, total, qlen]
    if 'SWAP' in str(station.station_type):
        status.loc[sm, 'available_swap_batteries'] = max(1, int(station.swap_slots))
    queue.loc[qm, ['queue_length', 'active_service_count', 'average_service_time_min', 'estimated_wait_min']] = [qlen, active, service, wait]
    STATUS_PATCH_KEYS.add((station.station_id, ts_iso))


def set_station_offline(status, queue, station, ts_iso):
    sm = (status.station_id.eq(station.station_id) & status.timestamp.eq(ts_iso))
    qm = (queue.station_id.eq(station.station_id) & queue.timestamp.eq(ts_iso))
    if not sm.any() or not qm.any():
        return
    service = int(status.loc[sm, 'estimated_service_time_min'].iloc[0])
    status.loc[sm, ['operating_status', 'available_slots', 'occupied_slots', 'available_swap_batteries', 'queue_length']] = ['OFFLINE', 0, 0, 0, 0]
    queue.loc[qm, ['queue_length', 'active_service_count', 'average_service_time_min', 'estimated_wait_min']] = [0, 0, service, 0.0]
    STATUS_PATCH_KEYS.add((station.station_id, ts_iso))


def set_traffic(traffic, segment_id, ts_iso, level, factor):
    m = (traffic.segment_id.eq(segment_id) & traffic.timestamp.eq(ts_iso))
    if not m.any():
        return False
    ff = traffic.loc[m, 'free_flow_speed_kmh'].astype(float)
    cur = np.maximum(5.0, ff * factor)
    traffic.loc[m, 'traffic_level'] = level
    traffic.loc[m, 'current_speed_kmh'] = np.round(cur, 2)
    traffic.loc[m, 'delay_factor'] = np.round(ff / cur, 3)
    TRAFFIC_PATCH_KEYS.add((segment_id, ts_iso))
    return True


# -----------------------------------------------------------------------------
# Load base dataset and protect raw PBFs
# -----------------------------------------------------------------------------
base_pbf = ROOT / 'map/raw/hanoi-baseline.osm.pbf'
patched_pbf = ROOT / 'map/raw/hanoi-patched.osm.pbf'
pbf_before = {'baseline_sha256': sha256(base_pbf), 'patched_sha256': sha256(patched_pbf)}

nodes = pd.read_csv(ROOT / 'map/processed/road_nodes.csv.gz')
segs = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str})
drivers = pd.read_csv(ROOT / 'drivers/drivers.csv')
vehicles = pd.read_csv(ROOT / 'vehicles/vehicles.csv')
trips = pd.read_csv(ROOT / 'trips/trips.csv')
true = pd.read_csv(ROOT / 'trajectories/true_trajectories.csv.gz')
gps = pd.read_csv(ROOT / 'gps/gps_observations.csv.gz')
battery = pd.read_csv(ROOT / 'battery/soc_history.csv.gz')
stations = pd.read_csv(ROOT / 'stations/stations.csv')
status = pd.read_csv(ROOT / 'stations/station_status.csv.gz')
queue = pd.read_csv(ROOT / 'queue/queue_status.csv.gz')
traffic = pd.read_csv(ROOT / 'traffic/traffic_snapshots.csv.gz')
splits = pd.read_csv(ROOT / 'training/trip_splits.csv')
mm_labels = pd.read_csv(ROOT / 'labels/map_matching_labels.csv.gz')
old_mm_candidates = pd.read_csv(ROOT / 'training/map_matching_candidates_with_split.csv.gz')

veh_idx = vehicles.set_index('vehicle_id')
trip_idx = trips.set_index('trip_id')
seg_idx = segs.set_index('segment_id')
st_idx = stations.set_index('station_id')
split_map = splits.set_index('trip_id').split.to_dict()

# -----------------------------------------------------------------------------
# 1) Fix NEED_SWAP trip -> swap-capable vehicle assignment and recalc affected SOC
# 2) Force service-oriented scenarios to contain actual low/insufficient SOC states
# -----------------------------------------------------------------------------
swap_vehicles = vehicles[vehicles.swap_supported.astype(bool)].copy().sort_values('vehicle_id')
swap_vids = swap_vehicles.vehicle_id.tolist()
need_swap_trips = trips.loc[trips.scenario_id.eq('NEED_SWAP'), 'trip_id'].tolist()

# assign NEED_SWAP to distinct swap-capable vehicles deterministically
for i, tid in enumerate(need_swap_trips):
    vid = swap_vids[i % len(swap_vids)]
    v = veh_idx.loc[vid]
    trips.loc[trips.trip_id.eq(tid), ['vehicle_id', 'driver_id']] = [vid, v.driver_id]

# refresh trip index after reassignment
trip_idx = trips.set_index('trip_id')

# Recompute battery rows for all forced-service scenarios using actual assigned vehicle
# This changes only SOC/energy tables, not road trajectories or GPS.
for tid, tr in trip_idx.iterrows():
    sc = tr.scenario_id
    if sc not in FORCE_SERVICE_SCENARIOS:
        continue
    v = veh_idx.loc[tr.vehicle_id]
    mask = battery.trip_id.eq(tid)
    b = battery.loc[mask].copy()
    if b.empty:
        continue
    # scenario-specific initial SOC; all are deterministic and physically recomputed
    if sc == 'INSUFFICIENT_RANGE':
        init_soc = 7.0
    elif sc == 'LOW_SOC':
        init_soc = 12.0
    elif sc == 'NEED_SWAP':
        init_soc = 16.0
    else:
        init_soc = 18.0
    cons = float(v.consumption_wh_per_km)
    cap = float(v.usable_capacity_kwh)
    heavy_factor = 1.12 if sc == 'HEAVY_TRAFFIC' else 1.0
    dist_km = b.distance_travelled_km.astype(float).to_numpy()
    energy = dist_km * cons / 1000.0 * heavy_factor
    soc = np.maximum(0.0, init_soc - energy / cap * 100.0)
    remain = np.maximum(0.0, soc / 100.0 * cap / (cons / 1000.0))
    battery.loc[mask, 'vehicle_id'] = tr.vehicle_id
    battery.loc[mask, 'energy_consumed_kwh'] = np.round(energy, 5)
    battery.loc[mask, 'soc_pct'] = np.round(soc, 3)
    battery.loc[mask, 'estimated_remaining_range_km'] = np.round(remain, 2)

trips.to_csv(ROOT / 'trips/trips.csv', index=False)
battery.to_csv(ROOT / 'battery/soc_history.csv.gz', index=False, compression='gzip')
trip_idx = trips.set_index('trip_id')

# -----------------------------------------------------------------------------
# 3) Demand snapshots: 8 per trip, split by trip, no label leakage in features
# -----------------------------------------------------------------------------
bg = {k: v.reset_index(drop=True) for k, v in battery.groupby('trip_id', sort=False)}
tg = {k: v.reset_index(drop=True) for k, v in true.groupby('trip_id', sort=False)}

demand_rows = []
feature_rows = []
event_context_rows = []
for tid, tr in trip_idx.iterrows():
    b = bg[tid]
    t = tg[tid]
    n = len(b)
    # evenly spaced interior decision snapshots; stable and deterministic
    positions = sorted(set(int(round(x)) for x in np.linspace(max(1, n * 0.08), max(1, n * 0.92), DEMAND_SNAPSHOTS_PER_TRIP)))
    while len(positions) < DEMAND_SNAPSHOTS_PER_TRIP:
        candidate = min(n - 1, positions[-1] + 1 if positions else 1)
        if candidate not in positions:
            positions.append(candidate)
        else:
            break
    positions = positions[:DEMAND_SNAPSHOTS_PER_TRIP]
    v = veh_idx.loc[tr.vehicle_id]
    for snap_idx, pos in enumerate(positions, 1):
        pos = min(pos, n - 1)
        br = b.iloc[pos]
        truer = t.iloc[min(pos, len(t) - 1)]
        remaining_km = max(0.0, float(tr.planned_network_distance_m) / 1000.0 - float(br.distance_travelled_km))
        reserve_buffer_km = max(1.0, remaining_km * 0.15)
        below_safe = float(br.soc_pct) <= float(v.minimum_safe_soc_pct) + 5.0
        insufficient = float(br.estimated_remaining_range_km) < remaining_km + reserve_buffer_km
        need = bool(below_safe or insufficient)
        if need:
            if bool(v.swap_supported) and str(v.battery_type).startswith('SWAP_'):
                service_type = 'BATTERY_SWAP'
            else:
                service_type = 'CHARGING'
            if below_safe and insufficient:
                reason = 'LOW_SOC_AND_INSUFFICIENT_RANGE'
            elif below_safe:
                reason = 'LOW_SOC'
            else:
                reason = 'INSUFFICIENT_RANGE'
        else:
            service_type = 'NONE'
            reason = 'SUFFICIENT_SOC_RANGE'
        eid = f'DE{len(demand_rows) + 1:06d}'
        ts = str(br.timestamp)
        progress = 100.0 * float(br.distance_travelled_km) / max(0.001, float(tr.planned_network_distance_m) / 1000.0)
        demand_rows.append({
            'event_id': eid, 'trip_id': tid, 'timestamp': ts, 'need_service': need,
            'service_type': service_type, 'reason_code': reason
        })
        feature_rows.append({
            'event_id': eid, 'trip_id': tid, 'timestamp': ts, 'snapshot_index': snap_idx,
            'trip_progress_pct': round(progress, 2), 'soc_pct': float(br.soc_pct),
            'estimated_remaining_range_km': float(br.estimated_remaining_range_km),
            'remaining_trip_distance_km': round(remaining_km, 3),
            'reserve_buffer_km': round(reserve_buffer_km, 3),
            'consumption_wh_per_km': float(v.consumption_wh_per_km),
            'minimum_safe_soc_pct': float(v.minimum_safe_soc_pct),
            'charging_supported': bool(v.charging_supported), 'swap_supported': bool(v.swap_supported),
            'connector_type': v.connector_type, 'battery_type': v.battery_type,
            'split': split_map[tid]
        })
        source_node = seg_idx.loc[truer.true_segment_id, 'from_node_id']
        direct_eta = max(0.0, (pd.Timestamp(tr.end_time) - pd.Timestamp(ts)).total_seconds() / 60.0)
        event_context_rows.append({
            'event_id': eid, 'trip_id': tid, 'scenario_id': tr.scenario_id,
            'timestamp': ts, 'source_node_id': source_node, 'true_segment_id': truer.true_segment_id,
            'destination_node_id': tr.destination_node_id, 'vehicle_id': tr.vehicle_id,
            'service_type': service_type, 'need_service': need,
            'estimated_remaining_range_km': float(br.estimated_remaining_range_km),
            'direct_distance_m': remaining_km * 1000.0, 'direct_eta_min': direct_eta,
            'snapshot_index': snap_idx, 'split': split_map[tid]
        })

demand = pd.DataFrame(demand_rows)
demand_features = pd.DataFrame(feature_rows)
events = pd.DataFrame(event_context_rows)
demand.to_csv(ROOT / 'labels/demand_labels.csv', index=False)
demand_features.to_csv(ROOT / 'training/demand_features.csv', index=False)

# -----------------------------------------------------------------------------
# 4) Build directed sparse graph once; derive network distances/times without OSRM
# -----------------------------------------------------------------------------
node_ids = nodes.node_id.astype(str).tolist()
node_to_i = {nid: i for i, nid in enumerate(node_ids)}
usable = segs[~segs.access.astype(str).str.lower().isin(['no', 'private'])].copy()
usable = usable[usable.from_node_id.isin(node_to_i) & usable.to_node_id.isin(node_to_i)]
usable['ff_time_sec'] = usable.length_m.astype(float) / np.maximum(5.0, usable.maxspeed_kmh.astype(float)) * 3.6
# collapse parallel edges by min weight per ordered node pair
pair = usable.groupby(['from_node_id', 'to_node_id'], as_index=False).agg(length_m=('length_m', 'min'), ff_time_sec=('ff_time_sec', 'min'))
rows = pair.from_node_id.map(node_to_i).to_numpy()
cols = pair.to_node_id.map(node_to_i).to_numpy()
N = len(node_ids)
Gdist = csr_matrix((pair.length_m.to_numpy(float), (rows, cols)), shape=(N, N))
Gtime = csr_matrix((pair.ff_time_sec.to_numpy(float), (rows, cols)), shape=(N, N))
station_node_idx = np.array([node_to_i[x] for x in stations.access_node_id.astype(str)], dtype=int)
event_node_idx = np.array([node_to_i[x] for x in events.source_node_id.astype(str)], dtype=int)
dest_node_idx_by_trip = {tid: node_to_i[str(tr.destination_node_id)] for tid, tr in trip_idx.iterrows()}

# event -> station distances/times via reverse graph from station nodes
rev_dist_full = dijkstra(Gdist.T.tocsr(), directed=True, indices=station_node_idx, return_predecessors=False)
event_station_dist = rev_dist_full[:, event_node_idx].T
rev_dist_full = None
rev_time_full = dijkstra(Gtime.T.tocsr(), directed=True, indices=station_node_idx, return_predecessors=False)
event_station_time = (rev_time_full[:, event_node_idx].T) / 60.0
rev_time_full = None

# station -> destination distances/times (extract only trip destinations)
forward_dist_full = dijkstra(Gdist, directed=True, indices=station_node_idx, return_predecessors=False)
forward_time_full = dijkstra(Gtime, directed=True, indices=station_node_idx, return_predecessors=False)
unique_dest_indices = np.array([dest_node_idx_by_trip[tid] for tid in events.trip_id], dtype=int)
station_dest_dist = forward_dist_full[:, unique_dest_indices].T
station_dest_time = (forward_time_full[:, unique_dest_indices].T) / 60.0
forward_dist_full = None
forward_time_full = None

station_pos = {sid: i for i, sid in enumerate(stations.station_id)}
event_pos = {eid: i for i, eid in enumerate(events.event_id)}

# -----------------------------------------------------------------------------
# 5) Make state/traffic scenarios real by patching exact temporal rows
# -----------------------------------------------------------------------------
# normalize timestamp strings exactly as files use
status['timestamp'] = pd.to_datetime(status.timestamp, format='mixed').map(lambda x: x.isoformat())
queue['timestamp'] = pd.to_datetime(queue.timestamp, format='mixed').map(lambda x: x.isoformat())
traffic['timestamp'] = pd.to_datetime(traffic.timestamp, format='mixed').map(lambda x: x.isoformat())

# representative service event per trip = snapshot 4 or nearest service snapshot
rep_event_by_trip = {}
for tid, g in events.groupby('trip_id', sort=False):
    svc = g[g.need_service.astype(bool)]
    if not svc.empty:
        target = svc.iloc[(svc.snapshot_index.astype(int) - 4).abs().argmin()]
    else:
        target = g.iloc[(g.snapshot_index.astype(int) - 4).abs().argmin()]
    rep_event_by_trip[tid] = target

# helpers using precomputed matrices
vehicle_rows = vehicles.set_index('vehicle_id')

def compatible_reachable_for_event(ev):
    ei = event_pos[ev.event_id]
    v = vehicle_rows.loc[ev.vehicle_id]
    out = []
    for sj, s in enumerate(stations.itertuples(index=False)):
        d = event_station_dist[ei, sj]
        comp = static_compatible(v, s, ev.service_type)
        if comp and np.isfinite(d):
            out.append((float(d), s, sj))
    return sorted(out, key=lambda x: x[0])

# Patch every trip of targeted scenarios so scenario labels are not decorative.
for tid, tr in trip_idx.iterrows():
    sc = tr.scenario_id
    ev = rep_event_by_trip[tid]
    if not bool(ev.need_service) and sc in FORCE_SERVICE_SCENARIOS:
        continue
    compat = compatible_reachable_for_event(ev) if bool(ev.need_service) else []
    sts = state_key(pd.Timestamp(ev.timestamp), 10)
    traf_ts = state_key(pd.Timestamp(ev.timestamp), 30)

    if sc == 'NEAREST_FULL' and compat:
        _, s, _ = compat[0]
        set_station_full(status, queue, s, sts)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': s.station_id, 'timestamp': sts})

    elif sc == 'STATION_OFFLINE' and compat:
        _, s, _ = compat[0]
        set_station_offline(status, queue, s, sts)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': s.station_id, 'timestamp': sts})

    elif sc == 'LONG_QUEUE' and compat:
        _, s, _ = compat[0]
        sm = (status.station_id.eq(s.station_id) & status.timestamp.eq(sts))
        service = int(status.loc[sm, 'estimated_service_time_min'].iloc[0]) if sm.any() else (6 if s.station_type == 'SWAP' else 18)
        set_queue_state(status, queue, s.station_id, sts, 45.0, int(s.total_slots), service, keep_available=1)
        if sm.any() and 'SWAP' in str(s.station_type):
            status.loc[sm, 'available_swap_batteries'] = max(1, int(s.swap_slots))
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': s.station_id, 'timestamp': sts})

    elif sc == 'FARTHER_BUT_FASTER' and len(compat) >= 2:
        # Pick a close pair among first 8; make nearer station slow via queue.
        candidates = compat[:8]
        best_pair = None
        for a in range(len(candidates) - 1):
            for b in range(a + 1, len(candidates)):
                da, sa, _ = candidates[a]
                db, sb, _ = candidates[b]
                gap = db - da
                if gap > 0 and (best_pair is None or gap < best_pair[0]):
                    best_pair = (gap, da, sa, db, sb)
        if best_pair:
            _, da, sa, db, sb = best_pair
            set_station_open(status, queue, sa, sts, available=1, queue_wait=60.0)
            set_station_open(status, queue, sb, sts, available=1, queue_wait=0.0)
            SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': sa.station_id, 'station_b': sb.station_id, 'timestamp': sts, 'distance_a': da, 'distance_b': db})

    elif sc == 'NO_AVAILABLE_STATION' and compat:
        affected = []
        for j, (_, s, _) in enumerate(compat):
            if j % 2 == 0:
                set_station_offline(status, queue, s, sts)
            else:
                set_station_full(status, queue, s, sts)
            affected.append(s.station_id)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'stations': affected, 'timestamp': sts})

    elif sc == 'NEAR_TIE_STATIONS' and len(compat) >= 2:
        ei = event_pos[ev.event_id]
        # choose pair with closest free-flow via-destination travel ETA
        pool = compat[:10]
        pairs = []
        for a in range(len(pool) - 1):
            for b in range(a + 1, len(pool)):
                da, sa, sja = pool[a]; db, sb, sjb = pool[b]
                ta = event_station_time[ei, sja] + station_dest_time[ei, sja]
                tb = event_station_time[ei, sjb] + station_dest_time[ei, sjb]
                if np.isfinite(ta) and np.isfinite(tb):
                    pairs.append((abs(float(ta - tb)), sa, sb, float(ta), float(tb)))
        if pairs:
            _, sa, sb, ta, tb = min(pairs, key=lambda x: x[0])
            set_station_open(status, queue, sa, sts, available=2, queue_wait=0.0)
            set_station_open(status, queue, sb, sts, available=2, queue_wait=0.0)
            SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': sa.station_id, 'station_b': sb.station_id, 'timestamp': sts, 'base_eta_a': ta, 'base_eta_b': tb})

    elif sc == 'QUEUE_REALTIME_CHANGE' and compat:
        _, s, _ = compat[0]
        t0 = sts
        t1 = (pd.Timestamp(sts) + pd.Timedelta(minutes=10)).isoformat()
        set_station_open(status, queue, s, t0, available=2, queue_wait=0.0)
        sm = (status.station_id.eq(s.station_id) & status.timestamp.eq(t1))
        service = int(status.loc[sm, 'estimated_service_time_min'].iloc[0]) if sm.any() else 18
        set_queue_state(status, queue, s.station_id, t1, 45.0, int(s.total_slots), service, keep_available=1)
        if sm.any() and 'SWAP' in str(s.station_type):
            status.loc[sm, 'available_swap_batteries'] = max(1, int(s.swap_slots))
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': s.station_id, 'before': t0, 'after': t1})

    elif sc == 'STATION_STATUS_CHANGE' and compat:
        _, s, _ = compat[0]
        t0 = sts
        t1 = (pd.Timestamp(sts) + pd.Timedelta(minutes=10)).isoformat()
        set_station_open(status, queue, s, t0, available=2, queue_wait=0.0)
        set_station_offline(status, queue, s, t1)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'station_a': s.station_id, 'before': t0, 'after': t1})

    elif sc == 'TRAFFIC_REALTIME_CHANGE':
        sid = ev.true_segment_id
        t0 = traf_ts
        t1 = (pd.Timestamp(traf_ts) + pd.Timedelta(minutes=30)).isoformat()
        set_traffic(traffic, sid, t0, 'FREE_FLOW', 0.90)
        set_traffic(traffic, sid, t1, 'HEAVY', 0.35)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'segment_id': sid, 'before': t0, 'after': t1})

    elif sc == 'HEAVY_TRAFFIC':
        # current and next few unique route segments at decision time are truly HEAVY
        trgrp = tg[tid]
        pos = min(len(trgrp) - 1, int((trgrp.timestamp == ev.timestamp).to_numpy().argmax()) if (trgrp.timestamp == ev.timestamp).any() else len(trgrp) // 2)
        unique_sids = []
        for sid in trgrp.iloc[pos:].true_segment_id:
            if sid not in unique_sids:
                unique_sids.append(sid)
            if len(unique_sids) >= 4:
                break
        for sid in unique_sids:
            set_traffic(traffic, sid, traf_ts, 'HEAVY', 0.35)
        SCENARIO_TARGETS[sc].append({'trip_id': tid, 'event_id': ev.event_id, 'segments': unique_sids, 'timestamp': traf_ts})

# save patched temporal state
status.to_csv(ROOT / 'stations/station_status.csv.gz', index=False, compression='gzip')
queue.to_csv(ROOT / 'queue/queue_status.csv.gz', index=False, compression='gzip')
traffic.to_csv(ROOT / 'traffic/traffic_snapshots.csv.gz', index=False, compression='gzip')

# -----------------------------------------------------------------------------
# 6) Candidate labels with compatibility/status/capacity/queue/reachability/SOC
# -----------------------------------------------------------------------------
status_lookup = status.set_index(['station_id', 'timestamp'])
queue_lookup = queue.set_index(['station_id', 'timestamp'])
traffic_lookup = traffic.set_index(['segment_id', 'timestamp'])

candidate_rows = []
for ei, ev in events.iterrows():
    v = vehicle_rows.loc[ev.vehicle_id]
    state_ts = state_key(pd.Timestamp(ev.timestamp), 10)
    for sj, s in enumerate(stations.itertuples(index=False)):
        d = event_station_dist[ei, sj]
        reach = bool(np.isfinite(d))
        comp = static_compatible(v, s, ev.service_type) if bool(ev.need_service) else False
        if (s.station_id, state_ts) in status_lookup.index:
            sr = status_lookup.loc[(s.station_id, state_ts)]
            qr = queue_lookup.loc[(s.station_id, state_ts)]
        else:
            sr = None; qr = None
        op = sr.operating_status if sr is not None else 'UNKNOWN'
        available_slots = int(sr.available_slots) if sr is not None else 0
        available_swap = int(sr.available_swap_batteries) if sr is not None else 0
        wait = float(qr.estimated_wait_min) if qr is not None else float('inf')
        if ev.service_type == 'BATTERY_SWAP':
            available_capacity = min(available_slots, available_swap)
        else:
            available_capacity = available_slots
        soc_feasible = bool(reach and (float(d) / 1000.0 + SOC_REACH_BUFFER_KM <= float(ev.estimated_remaining_range_km)))
        if not bool(ev.need_service):
            eligible = False; reason = 'NO_SERVICE_NEEDED'
        elif not comp:
            eligible = False; reason = 'INCOMPATIBLE'
        elif not reach:
            eligible = False; reason = 'UNREACHABLE'
        elif op != 'OPEN':
            eligible = False; reason = 'OFFLINE'
        elif available_capacity <= 0:
            if ev.service_type == 'BATTERY_SWAP' and available_slots > 0 and available_swap <= 0:
                eligible = False; reason = 'NO_SWAP_BATTERY'
            else:
                eligible = False; reason = 'FULL'
        elif wait > CANDIDATE_MAX_WAIT_MIN:
            eligible = False; reason = 'EXCESSIVE_QUEUE'
        elif not soc_feasible:
            eligible = False; reason = 'INSUFFICIENT_SOC_TO_REACH'
        else:
            eligible = True; reason = 'ELIGIBLE'
        candidate_rows.append({
            'event_id': ev.event_id, 'station_id': s.station_id, 'eligible': bool(eligible), 'reason': reason,
            'network_distance_m': None if not reach else round(float(d), 1),
            'soc_feasible': bool(soc_feasible), 'operating_status': op,
            'available_capacity': int(available_capacity), 'estimated_wait_min': None if not np.isfinite(wait) else round(wait, 2),
            'state_timestamp': state_ts
        })

candidate_labels = pd.DataFrame(candidate_rows)
candidate_labels.to_csv(ROOT / 'labels/candidate_labels.csv', index=False)

# -----------------------------------------------------------------------------
# 7) Expanded ranking reference using documented baseline cost
# -----------------------------------------------------------------------------
# traffic factor helper, current true segment with snapshot median fallback
traffic_median = traffic.groupby('timestamp').delay_factor.median().to_dict()

ranking_rows = []
recommendation_rows = []
for ei, ev in events[events.need_service.astype(bool)].iterrows():
    v = vehicle_rows.loc[ev.vehicle_id]
    state_ts = state_key(pd.Timestamp(ev.timestamp), 10)
    traf_ts = state_key(pd.Timestamp(ev.timestamp), 30)
    local_factor = traffic_median.get(traf_ts, 1.0)
    if (ev.true_segment_id, traf_ts) in traffic_lookup.index:
        local_factor = float(traffic_lookup.loc[(ev.true_segment_id, traf_ts)].delay_factor)
    static_pool = []
    for sj, s in enumerate(stations.itertuples(index=False)):
        if not static_compatible(v, s, ev.service_type):
            continue
        d1 = event_station_dist[ei, sj]
        d2 = station_dest_dist[ei, sj]
        if not (np.isfinite(d1) and np.isfinite(d2)):
            continue
        static_pool.append((float(d1), s, sj))
    static_pool.sort(key=lambda x: x[0])
    group = static_pool[:RANKING_GROUP_SIZE]
    if len(group) < 2:
        continue
    tmp = []
    for d1, s, sj in group:
        sr = status_lookup.loc[(s.station_id, state_ts)]
        qr = queue_lookup.loc[(s.station_id, state_ts)]
        d2 = float(station_dest_dist[ei, sj])
        eta1 = float(event_station_time[ei, sj])
        eta2 = float(station_dest_time[ei, sj])
        # station leg traffic uses snapshot median; driver leg uses observed current road factor
        driver_factor = float(local_factor)
        station_factor = float(traffic_median.get(traf_ts, 1.0))
        traffic_eta = eta1 * driver_factor + eta2 * station_factor
        direct_d = float(ev.direct_distance_m)
        direct_eta = float(ev.direct_eta_min)
        detour_d = max(0.0, d1 + d2 - direct_d)
        detour_t = max(0.0, eta1 + eta2 - direct_eta)
        wait = float(qr.estimated_wait_min)
        service = float(sr.estimated_service_time_min)
        available_capacity = int(min(sr.available_slots, sr.available_swap_batteries)) if ev.service_type == 'BATTERY_SWAP' else int(sr.available_slots)
        soc_feasible = bool(d1 / 1000.0 + SOC_REACH_BUFFER_KM <= float(ev.estimated_remaining_range_km))
        total_eta = traffic_eta + wait + service
        penalty = 0.0
        if sr.operating_status != 'OPEN': penalty += 10000.0
        if available_capacity <= 0: penalty += 5000.0
        if not soc_feasible: penalty += 5000.0
        # Uses all requested ranking dimensions. Capacity has a small benefit; detour is explicitly penalized.
        cost = total_eta + 0.25 * detour_t + 0.002 * detour_d - 0.35 * min(available_capacity, 6) + penalty
        tmp.append({
            'event_id': ev.event_id, 'trip_id': ev.trip_id, 'station_id': s.station_id, 'split': ev.split,
            'driver_to_station_distance_m': round(d1, 1), 'driver_to_station_eta_min': round(eta1, 3),
            'station_to_destination_distance_m': round(d2, 1), 'station_to_destination_eta_min': round(eta2, 3),
            'direct_driver_to_destination_distance_m': round(direct_d, 1), 'direct_driver_to_destination_eta_min': round(direct_eta, 3),
            'detour_distance_m': round(detour_d, 1), 'detour_time_min': round(detour_t, 3),
            'traffic_delay_factor_driver_leg': round(driver_factor, 3), 'traffic_delay_factor_station_leg': round(station_factor, 3),
            'traffic_adjusted_eta_min': round(traffic_eta, 3), 'queue_wait_min': round(wait, 2),
            'service_time_min': round(service, 2), 'total_eta_min': round(total_eta, 3),
            'available_capacity': available_capacity, 'operating_status': sr.operating_status,
            'soc_feasible': bool(soc_feasible), 'ranking_cost_label': round(cost, 4)
        })
    tmp = sorted(tmp, key=lambda x: (x['ranking_cost_label'], x['station_id']))
    for rank_i, row in enumerate(tmp, 1):
        row['reference_rank'] = rank_i
        row['is_reference_best'] = rank_i == 1
        ranking_rows.append(row)
    # recommendation evaluation label only if best candidate is actually eligible per candidate labels
    eligible_lookup = candidate_labels[(candidate_labels.event_id == ev.event_id) & (candidate_labels.eligible.astype(bool))]
    eligible_ids = set(eligible_lookup.station_id)
    best_eligible = next((r for r in tmp if r['station_id'] in eligible_ids), None)
    recommendation_rows.append({
        'event_id': ev.event_id,
        'reference_station_id': best_eligible['station_id'] if best_eligible else None,
        'has_recommendation': bool(best_eligible),
        'label_method': 'documented_baseline_cost_v2' if best_eligible else 'NO_ELIGIBLE_STATION'
    })

ranking = pd.DataFrame(ranking_rows)
reclabels = pd.DataFrame(recommendation_rows)
ranking.to_csv(ROOT / 'training/ranking_reference.csv', index=False)
reclabels.to_csv(ROOT / 'labels/recommendation_labels.csv', index=False)

# -----------------------------------------------------------------------------
# 8) Map-matching candidates: all selected groups guaranteed positive + negative
# -----------------------------------------------------------------------------
# Select existing geographically queried observations only when at least one negative exists.
group_has_negative = old_mm_candidates.groupby('observation_id').is_correct.apply(lambda s: (~s.astype(bool)).any())
selected_obs = set(group_has_negative[group_has_negative].index)
base = old_mm_candidates[old_mm_candidates.observation_id.isin(selected_obs)].copy()
truth = mm_labels.set_index('observation_id')
gps_idx = gps.set_index('observation_id')
true_key = true.set_index(['trip_id', 'timestamp'])

patched_groups = []
for oid, g in base.groupby('observation_id', sort=False):
    tr = truth.loc[oid]
    gr = g.copy()
    # Exact directional truth is the positive candidate.
    gr['is_correct'] = gr.candidate_segment_id.astype(str).eq(str(tr.true_segment_id))
    gr = gr.sort_values(['distance_to_segment_m', 'heading_difference_deg']).drop_duplicates('candidate_segment_id', keep='first')
    # keep up to 5 negatives
    neg = gr[~gr.is_correct.astype(bool)].head(5).copy()
    if neg.empty:
        continue
    pos = gr[gr.is_correct.astype(bool)].head(1).copy()
    if pos.empty:
        gp = gps_idx.loc[oid]
        sr = seg_idx.loc[str(tr.true_segment_id)]
        plat, plon = projected_to_segment(float(gp.latitude), float(gp.longitude), sr.geometry)
        try:
            trow = true_key.loc[(gp.trip_id, gp.timestamp)]
            if isinstance(trow, pd.DataFrame): trow = trow.iloc[0]
            true_heading = float(trow.heading_deg)
        except Exception:
            ep = parse_linestring_endpoints(sr.geometry)
            true_heading = 0.0 if not ep else heading(ep[0][1], ep[0][0], ep[1][1], ep[1][0])
        hd = min(abs(float(gp.heading_deg) - true_heading) % 360.0, 360.0 - abs(float(gp.heading_deg) - true_heading) % 360.0)
        pos = pd.DataFrame([{
            'observation_id': oid, 'candidate_segment_id': str(tr.true_segment_id),
            'distance_to_segment_m': round(hav_m(float(gp.latitude), float(gp.longitude), plat, plon), 2),
            'projected_lat': plat, 'projected_lon': plon, 'heading_difference_deg': round(hd, 2),
            'is_correct': True, 'hard_negative': False, 'trip_id': gp.trip_id, 'split': split_map[gp.trip_id]
        }])
    out = pd.concat([pos, neg], ignore_index=True)
    out['hard_negative'] = (~out.is_correct.astype(bool)) & (out.distance_to_segment_m.astype(float) <= 20.0) & (out.heading_difference_deg.astype(float) <= 45.0)
    out['trip_id'] = out.get('trip_id', gps_idx.loc[oid].trip_id)
    out['split'] = split_map[gps_idx.loc[oid].trip_id]
    patched_groups.append(out)

mmc = pd.concat(patched_groups, ignore_index=True)
mmc = mmc[['observation_id', 'candidate_segment_id', 'distance_to_segment_m', 'projected_lat', 'projected_lon', 'heading_difference_deg', 'is_correct', 'hard_negative', 'trip_id', 'split']]
mmc.to_csv(ROOT / 'training/map_matching_candidates_with_split.csv.gz', index=False, compression='gzip')
mmc.drop(columns=['trip_id', 'split']).to_csv(ROOT / 'training/map_matching_candidates.csv.gz', index=False, compression='gzip')

# -----------------------------------------------------------------------------
# 9) Rebuild replay using patched state + guarantee before/after transition events
# -----------------------------------------------------------------------------
recs = []
def add_replay(ts, typ, entity, payload):
    recs.append({'timestamp': ts, 'event_type': typ, 'entity_id': entity, 'payload_json': json.dumps(payload, separators=(',', ':'))})

for r in gps.iloc[::8].itertuples(index=False):
    add_replay(r.timestamp, 'GPS_UPDATE', r.trip_id, {'observation_id': r.observation_id, 'lat': round(float(r.latitude), 7), 'lon': round(float(r.longitude), 7)})
for r in battery.iloc[::12].itertuples(index=False):
    add_replay(r.timestamp, 'SOC_UPDATE', r.trip_id, {'soc_pct': float(r.soc_pct), 'remaining_range_km': float(r.estimated_remaining_range_km)})
# normal station sample + every patched station state row
sample_status = status.iloc[::4]
forced_status = status[status.apply(lambda r: (r.station_id, r.timestamp) in STATUS_PATCH_KEYS, axis=1)]
for r in pd.concat([sample_status, forced_status]).drop_duplicates(['station_id', 'timestamp']).itertuples(index=False):
    add_replay(r.timestamp, 'STATION_STATUS_UPDATE', r.station_id, {'status': r.operating_status, 'available_slots': int(r.available_slots), 'queue_length': int(r.queue_length)})
# random traffic sample + all patched traffic state rows
sample_traffic = traffic.sample(min(3000, len(traffic)), random_state=SEED)
forced_traffic = traffic[traffic.apply(lambda r: (r.segment_id, r.timestamp) in TRAFFIC_PATCH_KEYS, axis=1)]
for r in pd.concat([sample_traffic, forced_traffic]).drop_duplicates(['segment_id', 'timestamp']).itertuples(index=False):
    add_replay(r.timestamp, 'TRAFFIC_UPDATE', r.segment_id, {'traffic_level': r.traffic_level, 'current_speed_kmh': float(r.current_speed_kmh)})
replay = pd.DataFrame(recs).sort_values(['timestamp', 'event_type', 'entity_id']).reset_index(drop=True)
replay.insert(0, 'event_id', [f'RE{i+1:08d}' for i in range(len(replay))])
replay.to_csv(ROOT / 'realtime/events.csv.gz', index=False, compression='gzip')

# -----------------------------------------------------------------------------
# 10) Scenario coverage with quantified evidence and actual assertions
# -----------------------------------------------------------------------------
# convenience tables
cand_by_event = {k: v for k, v in candidate_labels.groupby('event_id')}
rank_by_event = {k: v for k, v in ranking.groupby('event_id')}
mmc_with_scenario = mmc.merge(trips[['trip_id', 'scenario_id']], on='trip_id', how='left')
mm_labels_trip = mm_labels.merge(gps[['observation_id', 'trip_id', 'timestamp', 'latitude', 'longitude']], on='observation_id', how='left')
mm_labels_trip = mm_labels_trip.merge(trips[['trip_id', 'scenario_id']], on='trip_id', how='left')
seg_bridge = segs.set_index('segment_id').bridge.astype(str).str.lower().isin(['yes', 'true', '1'])

scenario_rows = []
for sc, trip_group in trips.groupby('scenario_id', sort=True):
    tids = trip_group.trip_id.tolist()
    example_trip = tids[0]
    eg = events[events.trip_id.eq(example_trip)]
    ev = rep_event_by_trip[example_trip]
    status_name = 'FAIL'
    metric = 'assertion'; value = 0.0; threshold = 1.0
    secondary_name = ''; secondary_value = None; entity = ''; ets = ev.timestamp
    note = ''

    if sc == 'NORMAL_TRIP':
        svc = int(demand[demand.trip_id.eq(example_trip)].need_service.astype(bool).sum())
        value = svc; metric = 'service_snapshots'; threshold = 0.0; status_name = 'PASS' if svc == 0 else 'FAIL'
        note = 'normal high-SOC trip has no forced service condition'
    elif sc == 'NO_SERVICE_NEEDED':
        svc = int(demand[demand.trip_id.eq(example_trip)].need_service.astype(bool).sum())
        value = svc; metric = 'service_snapshots'; threshold = 0.0; status_name = 'PASS' if svc == 0 else 'FAIL'
    elif sc == 'LOW_SOC':
        min_soc = float(battery[battery.trip_id.eq(example_trip)].soc_pct.min())
        value = min_soc; metric = 'min_soc_pct'; threshold = float(vehicle_rows.loc[trip_idx.loc[example_trip].vehicle_id].minimum_safe_soc_pct)
        status_name = 'PASS' if min_soc <= threshold else 'FAIL'
    elif sc == 'NEED_CHARGING':
        labs = demand[demand.trip_id.eq(example_trip)]
        n = int((labs.service_type == 'CHARGING').sum())
        v = vehicle_rows.loc[trip_idx.loc[example_trip].vehicle_id]
        value = n; metric = 'charging_label_count'; threshold = 1.0
        secondary_name = 'charging_supported'; secondary_value = int(bool(v.charging_supported))
        status_name = 'PASS' if n > 0 and bool(v.charging_supported) else 'FAIL'
    elif sc == 'NEED_SWAP':
        labs = demand[demand.trip_id.eq(example_trip)]
        n = int((labs.service_type == 'BATTERY_SWAP').sum())
        v = vehicle_rows.loc[trip_idx.loc[example_trip].vehicle_id]
        value = n; metric = 'battery_swap_label_count'; threshold = 1.0
        secondary_name = 'swap_supported'; secondary_value = int(bool(v.swap_supported))
        status_name = 'PASS' if n > 0 and bool(v.swap_supported) else 'FAIL'
    elif sc == 'NEAREST_FULL':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            c = cand_by_event[target['event_id']]
            vrow = c[c.station_id.eq(target['station_a'])].iloc[0]
            value = float(vrow.available_capacity); metric = 'nearest_available_capacity'; threshold = 0.0
            secondary_name = 'reason_is_FULL'; secondary_value = int(vrow.reason == 'FULL')
            entity = target['station_a']; ets = target['timestamp']; status_name = 'PASS' if value == 0 and vrow.reason == 'FULL' else 'FAIL'
    elif sc == 'STATION_OFFLINE':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            c = cand_by_event[target['event_id']]; vrow = c[c.station_id.eq(target['station_a'])].iloc[0]
            value = 1.0 if vrow.operating_status == 'OFFLINE' else 0.0; metric = 'offline_state'; threshold = 1.0
            secondary_name = 'reason_is_OFFLINE'; secondary_value = int(vrow.reason == 'OFFLINE'); entity = target['station_a']; ets = target['timestamp']
            status_name = 'PASS' if value == 1 and vrow.reason == 'OFFLINE' else 'FAIL'
    elif sc == 'INCOMPATIBLE_STATION':
        c = cand_by_event[ev.event_id]
        nbad = int((c.reason == 'INCOMPATIBLE').sum()); nok = int(c.eligible.astype(bool).sum())
        value = nbad; metric = 'incompatible_candidate_count'; threshold = 1.0
        secondary_name = 'eligible_candidate_count'; secondary_value = nok
        status_name = 'PASS' if nbad > 0 and nok > 0 else 'FAIL'
    elif sc == 'LONG_QUEUE':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            qr = queue_lookup.loc[(target['station_a'], target['timestamp'])]
            value = float(qr.estimated_wait_min); metric = 'estimated_wait_min'; threshold = LONG_QUEUE_THRESHOLD_MIN
            entity = target['station_a']; ets = target['timestamp']; status_name = 'PASS' if value >= threshold else 'FAIL'
    elif sc == 'FARTHER_BUT_FASTER':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target and target['event_id'] in rank_by_event:
            r = rank_by_event[target['event_id']].set_index('station_id')
            if target['station_a'] in r.index and target['station_b'] in r.index:
                a = r.loc[target['station_a']]; b = r.loc[target['station_b']]
                value = float(b.driver_to_station_distance_m - a.driver_to_station_distance_m); metric = 'farther_distance_delta_m'; threshold = 0.0
                secondary_name = 'faster_total_eta_delta_min'; secondary_value = round(float(a.total_eta_min - b.total_eta_min), 3)
                entity = f"{target['station_a']}->{target['station_b']}"; ets = target['timestamp']
                status_name = 'PASS' if value > 0 and secondary_value > 0 else 'FAIL'
    elif sc == 'HEAVY_TRAFFIC':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            x = traffic[(traffic.segment_id.isin(target['segments'])) & traffic.timestamp.eq(target['timestamp'])]
            heavy = int(x.traffic_level.isin(['HEAVY', 'INCIDENT']).sum())
            value = heavy; metric = 'heavy_or_incident_segment_count'; threshold = 1.0
            secondary_name = 'patched_route_segment_count'; secondary_value = len(target['segments']); ets = target['timestamp']
            status_name = 'PASS' if heavy >= 1 else 'FAIL'
    elif sc == 'INSUFFICIENT_RANGE':
        f = demand_features[demand_features.trip_id.eq(example_trip)].copy()
        margin = (f.estimated_remaining_range_km - f.remaining_trip_distance_km).min()
        value = float(margin); metric = 'min_range_margin_km'; threshold = 0.0
        status_name = 'PASS' if value < 0 else 'FAIL'
    elif sc == 'GPS_NOISE':
        obs = mm_labels_trip[mm_labels_trip.trip_id.eq(example_trip)].copy()
        errs = [hav_m(r.latitude, r.longitude, r.true_latitude, r.true_longitude) for r in obs.itertuples()]
        med = float(np.median(errs)) if errs else 0.0
        value = med; metric = 'median_gps_error_m'; threshold = 10.0; status_name = 'PASS' if med >= 10.0 else 'FAIL'
    elif sc == 'GPS_MISSING':
        ntrue = int((true.trip_id == example_trip).sum()); ngps = int((gps.trip_id == example_trip).sum()); ratio = ngps / max(1, ntrue)
        value = round(ratio, 4); metric = 'gps_to_true_point_ratio'; threshold = 0.85; status_name = 'PASS' if ratio < 0.85 else 'FAIL'
        secondary_name = 'missing_points'; secondary_value = ntrue - ngps
    elif sc == 'PARALLEL_ROADS':
        x = mmc_with_scenario[mmc_with_scenario.scenario_id.eq(sc)]
        hn = int(x.hard_negative.astype(bool).sum())
        mind = float(x.loc[x.hard_negative.astype(bool), 'distance_to_segment_m'].min()) if hn else float('inf')
        value = hn; metric = 'hard_negative_candidate_count'; threshold = 1.0
        secondary_name = 'min_hard_negative_distance_m'; secondary_value = None if not np.isfinite(mind) else round(mind, 2)
        status_name = 'PASS' if hn > 0 and mind <= 20.0 else 'FAIL'
    elif sc == 'BRIDGE_AMBIGUITY':
        obs = mm_labels_trip[mm_labels_trip.scenario_id.eq(sc)].copy()
        obs['is_bridge'] = obs.true_segment_id.map(seg_bridge.to_dict()).fillna(False)
        bridge_obs = set(obs.loc[obs.is_bridge, 'observation_id'])
        x = mmc_with_scenario[(mmc_with_scenario.scenario_id.eq(sc)) & (mmc_with_scenario.observation_id.isin(bridge_obs))]
        ambiguous = int((~x.is_correct.astype(bool)).sum())
        value = len(bridge_obs); metric = 'bridge_observation_count'; threshold = 1.0
        secondary_name = 'bridge_negative_candidate_count'; secondary_value = ambiguous
        status_name = 'PASS' if len(bridge_obs) > 0 and ambiguous > 0 else 'FAIL'
    elif sc == 'QUEUE_REALTIME_CHANGE':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            q0 = float(queue_lookup.loc[(target['station_a'], target['before'])].estimated_wait_min)
            q1 = float(queue_lookup.loc[(target['station_a'], target['after'])].estimated_wait_min)
            value = abs(q1 - q0); metric = 'queue_wait_change_min'; threshold = 20.0
            secondary_name = 'before_after_wait'; secondary_value = f'{q0:.1f}->{q1:.1f}'; entity = target['station_a']; ets = target['before']
            status_name = 'PASS' if value >= 20.0 else 'FAIL'
    elif sc == 'TRAFFIC_REALTIME_CHANGE':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            a = traffic_lookup.loc[(target['segment_id'], target['before'])]; b = traffic_lookup.loc[(target['segment_id'], target['after'])]
            value = abs(float(a.current_speed_kmh) - float(b.current_speed_kmh)); metric = 'speed_change_kmh'; threshold = 5.0
            secondary_name = 'level_transition'; secondary_value = f'{a.traffic_level}->{b.traffic_level}'; entity = target['segment_id']; ets = target['before']
            status_name = 'PASS' if value >= 5.0 and a.traffic_level != b.traffic_level else 'FAIL'
    elif sc == 'STATION_STATUS_CHANGE':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target:
            a = status_lookup.loc[(target['station_a'], target['before'])]; b = status_lookup.loc[(target['station_a'], target['after'])]
            value = 1.0 if a.operating_status != b.operating_status else 0.0; metric = 'status_changed'; threshold = 1.0
            secondary_name = 'status_transition'; secondary_value = f'{a.operating_status}->{b.operating_status}'; entity = target['station_a']; ets = target['before']
            status_name = 'PASS' if value == 1 else 'FAIL'
    elif sc == 'NO_AVAILABLE_STATION':
        c = cand_by_event[ev.event_id]; n = int(c.eligible.astype(bool).sum())
        value = n; metric = 'eligible_station_count'; threshold = 0.0; status_name = 'PASS' if n == 0 else 'FAIL'
    elif sc == 'NEAR_TIE_STATIONS':
        target = SCENARIO_TARGETS[sc][0] if SCENARIO_TARGETS[sc] else None
        if target and target['event_id'] in rank_by_event:
            r = rank_by_event[target['event_id']].sort_values('ranking_cost_label')
            if len(r) >= 2:
                diff = float(r.iloc[1].ranking_cost_label - r.iloc[0].ranking_cost_label)
                value = diff; metric = 'top2_cost_difference_min_equiv'; threshold = NEAR_TIE_THRESHOLD_MIN
                secondary_name = 'top2_stations'; secondary_value = f"{r.iloc[0].station_id},{r.iloc[1].station_id}"
                status_name = 'PASS' if diff <= threshold else 'FAIL'
    else:
        status_name = 'PASS'; value = 1.0

    scenario_rows.append({
        'scenario_id': sc, 'trip_count': len(tids), 'example_trip_id': example_trip,
        'example_event_id': ev.event_id, 'validator_status': status_name,
        'metric_name': metric, 'metric_value': value, 'threshold': threshold,
        'secondary_metric_name': secondary_name, 'secondary_metric_value': secondary_value,
        'evidence_entity_id': entity, 'evidence_timestamp': ets, 'notes': note
    })

scenario_coverage = pd.DataFrame(scenario_rows)
scenario_coverage.to_csv(ROOT / 'scenarios/scenario_coverage.csv', index=False)

# -----------------------------------------------------------------------------
# 11) Config/counts/baseline documentation artifacts
# -----------------------------------------------------------------------------
config_path = ROOT / 'config/generation_config.json'
config = json.load(open(config_path))
config.update({
    'semantic_patch_version': 'v1.1',
    'demand_snapshots_per_trip': DEMAND_SNAPSHOTS_PER_TRIP,
    'candidate_max_wait_min': CANDIDATE_MAX_WAIT_MIN,
    'soc_reach_buffer_km': SOC_REACH_BUFFER_KM,
    'ranking_group_size': RANKING_GROUP_SIZE,
    'near_tie_threshold_min': NEAR_TIE_THRESHOLD_MIN,
    'long_queue_threshold_min': LONG_QUEUE_THRESHOLD_MIN
})
json.dump(config, open(config_path, 'w'), indent=2)

ranking_baseline = {
    'version': 'v2',
    'candidate_pool': 'top network-nearest static-compatible reachable stations, up to ranking_group_size',
    'traffic_adjustment': 'driver leg uses current true-segment traffic delay_factor; station leg uses snapshot median delay_factor',
    'cost_formula': 'traffic_adjusted_eta_min + queue_wait_min + service_time_min + 0.25*detour_time_min + 0.002*detour_distance_m - 0.35*min(available_capacity,6) + penalties',
    'penalties': {'station_not_open': 10000, 'no_available_capacity': 5000, 'soc_infeasible': 5000},
    'note': 'ranking/reference labels are training/evaluation-only and are not runtime recommendation inputs'
}
json.dump(ranking_baseline, open(ROOT / 'config/ranking_baseline.json', 'w'), indent=2)

pbf_after = {'baseline_sha256': sha256(base_pbf), 'patched_sha256': sha256(patched_pbf)}
pbf_integrity = {
    'before': pbf_before, 'after': pbf_after, 'unchanged': pbf_before == pbf_after,
    'warning': 'hanoi-patched.osm.pbf changes OSM way 881947000 (Cầu Thanh Trì) motorcar=designated to motorcar=no. Dataset patch does not decide correctness. Human confirmation is required before freezing patched PBF as primary routing map.'
}
json.dump(pbf_integrity, open(ROOT / 'validation/pbf_integrity.json', 'w'), indent=2, ensure_ascii=False)

counts = {
    'road_nodes': len(nodes), 'road_segments': len(segs), 'drivers': len(drivers), 'vehicles': len(vehicles),
    'trips': len(trips), 'true_trajectory_points': len(true), 'gps_observations': len(gps),
    'soc_history': len(battery), 'stations': len(stations), 'station_status': len(status),
    'queue_status': len(queue), 'traffic_snapshots': len(traffic), 'realtime_events': len(replay),
    'map_matching_candidates': len(mmc), 'map_matching_selected_observations': mmc.observation_id.nunique(),
    'demand_labels': len(demand), 'candidate_labels': len(candidate_labels),
    'ranking_reference': len(ranking), 'ranking_event_groups': ranking.event_id.nunique(),
    'recommendation_labels': len(reclabels), 'scenario_rows': len(scenario_coverage)
}
json.dump(counts, open(ROOT / 'validation/data_counts.json', 'w'), indent=2)

summary = {
    'demand_distribution': demand.service_type.value_counts().to_dict(),
    'demand_split_distribution': demand_features.groupby(['split']).size().to_dict(),
    'map_matching': {
        'selected_observations': int(mmc.observation_id.nunique()),
        'positive_candidates': int(mmc.is_correct.astype(bool).sum()),
        'negative_candidates': int((~mmc.is_correct.astype(bool)).sum()),
        'hard_negative_candidates': int(mmc.hard_negative.astype(bool).sum()),
        'split_observations': mmc.drop_duplicates('observation_id').split.value_counts().to_dict()
    },
    'ranking': {'rows': len(ranking), 'event_groups': int(ranking.event_id.nunique()), 'split_groups': ranking.drop_duplicates('event_id').split.value_counts().to_dict()},
    'scenarios': scenario_coverage.validator_status.value_counts().to_dict(),
    'pbf_unchanged': bool(pbf_integrity['unchanged'])
}
json.dump(summary, open(ROOT / 'validation/patch_summary.json', 'w'), indent=2)
print(json.dumps(summary, indent=2))
