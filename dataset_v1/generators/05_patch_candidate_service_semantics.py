from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

ROOT = Path(__file__).resolve().parents[1]
SOC_REACH_BUFFER_KM = 0.5
MAX_WAIT_MIN = 90.0
MAX_RANK_CANDIDATES = 8
CHARGING_SERVICE_TIME_MIN = 18.0
SWAP_SERVICE_TIME_MIN = 6.0
FARTHER_MIN_DISTANCE_DELTA_M = 500.0
FARTHER_MEANINGFUL_ETA_MARGIN_MIN = 10.0
SEED = 20260916


def bs(s):
    if getattr(s, 'dtype', None) == bool:
        return s
    return s.astype(str).str.lower().isin(['true', '1', 'yes'])


def tokens(v):
    if pd.isna(v):
        return set()
    return {x.strip() for x in str(v).replace(',', ';').split(';') if x.strip()}


def compatible(v, s, service):
    if service == 'CHARGING':
        if not bool(v.charging_supported) or 'CHARGING' not in str(s.station_type):
            return False
    elif service == 'BATTERY_SWAP':
        if not bool(v.swap_supported) or 'SWAP' not in str(s.station_type):
            return False
    else:
        return False
    if str(v.vehicle_type) not in tokens(s.supported_vehicle_type):
        return False
    if str(v.connector_type) not in tokens(s.connector_type):
        return False
    if service == 'BATTERY_SWAP':
        if pd.isna(s.battery_type) or str(v.battery_type) not in tokens(s.battery_type):
            return False
    return True


def floor_iso(ts, minutes):
    return pd.Timestamp(ts).floor(f'{minutes}min').isoformat()


def service_slots(station_row, service):
    return int(station_row.charging_slots if service == 'CHARGING' else station_row.swap_slots)


def service_time(service):
    return CHARGING_SERVICE_TIME_MIN if service == 'CHARGING' else SWAP_SERVICE_TIME_MIN


# -----------------------------------------------------------------------------
# Load current V1.1 artifacts only. No road/PBF regeneration.
# -----------------------------------------------------------------------------
nodes = pd.read_csv(ROOT / 'map/processed/road_nodes.csv.gz')
segs = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str})
vehicles = pd.read_csv(ROOT / 'vehicles/vehicles.csv')
trips = pd.read_csv(ROOT / 'trips/trips.csv')
true = pd.read_csv(ROOT / 'trajectories/true_trajectories.csv.gz')
gps = pd.read_csv(ROOT / 'gps/gps_observations.csv.gz')
battery = pd.read_csv(ROOT / 'battery/soc_history.csv.gz')
stations = pd.read_csv(ROOT / 'stations/stations.csv')
old_status = pd.read_csv(ROOT / 'stations/station_status.csv.gz')
old_queue = pd.read_csv(ROOT / 'queue/queue_status.csv.gz')
traffic = pd.read_csv(ROOT / 'traffic/traffic_snapshots.csv.gz')
demand = pd.read_csv(ROOT / 'labels/demand_labels.csv')
df = pd.read_csv(ROOT / 'training/demand_features.csv')
old_candidates = pd.read_csv(ROOT / 'labels/candidate_labels.csv')
splits = pd.read_csv(ROOT / 'training/trip_splits.csv')
scenario_cov = pd.read_csv(ROOT / 'scenarios/scenario_coverage.csv')

# Normalize time keys.
for table in [old_status, old_queue, traffic]:
    table['timestamp'] = pd.to_datetime(table.timestamp, format='mixed').map(lambda x: x.isoformat())

st_meta = stations.set_index('station_id')
veh_idx = vehicles.set_index('vehicle_id')
trip_idx = trips.set_index('trip_id')
seg_idx = segs.set_index('segment_id')
split_map = splits.set_index('trip_id').split.to_dict()

# Event context: demand timestamp matches an exact ground-truth trajectory row.
truth_event = true[['trip_id', 'timestamp', 'true_segment_id']].copy()
events = demand.merge(df[['event_id', 'trip_id', 'timestamp', 'snapshot_index', 'estimated_remaining_range_km', 'remaining_trip_distance_km']], on=['event_id', 'trip_id', 'timestamp'], how='left')
events = events.merge(trips[['trip_id', 'vehicle_id', 'destination_node_id', 'end_time', 'scenario_id']], on='trip_id', how='left')
events = events.merge(truth_event, on=['trip_id', 'timestamp'], how='left')
events['source_node_id'] = events.true_segment_id.map(seg_idx.from_node_id)
events['direct_distance_m'] = events.remaining_trip_distance_km.astype(float) * 1000.0
events['direct_eta_min'] = [(pd.Timestamp(end) - pd.Timestamp(ts)).total_seconds() / 60.0 for end, ts in zip(events.end_time, events.timestamp)]
events['split'] = events.trip_id.map(split_map)
events['need_service'] = bs(events.need_service)

# -----------------------------------------------------------------------------
# 1) Transform generic station state to service-specific state.
# -----------------------------------------------------------------------------
status_rows = []
for i, r in enumerate(old_status.itertuples(index=False)):
    s = st_meta.loc[r.station_id]
    total = int(s.total_slots)
    ch_slots = int(s.charging_slots)
    sw_slots = int(s.swap_slots)
    op = str(r.operating_status)
    old_occ = max(0, min(total, int(r.occupied_slots)))
    old_av = max(0, min(total, int(r.available_slots)))

    if op != 'OPEN':
        ch_occ = ch_av = sw_occ = sw_av = 0
        swap_batt = 0
    elif ch_slots > 0 and sw_slots == 0:
        ch_occ = min(ch_slots, old_occ)
        ch_av = min(ch_slots - ch_occ, old_av)
        if ch_occ + ch_av < ch_slots:
            ch_av = ch_slots - ch_occ
        sw_occ = sw_av = 0
        swap_batt = 0
    elif sw_slots > 0 and ch_slots == 0:
        sw_occ = min(sw_slots, old_occ)
        sw_av = min(sw_slots - sw_occ, old_av)
        if sw_occ + sw_av < sw_slots:
            sw_av = sw_slots - sw_occ
        ch_occ = ch_av = 0
        swap_batt = max(0, int(r.available_swap_batteries))
    else:
        # Preserve total utilization but allocate occupancy independently across both services.
        occ_total = min(old_occ, ch_slots + sw_slots)
        if ch_slots + sw_slots > 0:
            base_ch = int(round(occ_total * ch_slots / (ch_slots + sw_slots)))
        else:
            base_ch = 0
        # Deterministic one-slot bias prevents mixed stations from always mirroring identical utilization.
        bias = [-1, 0, 1][(i + sum(ord(c) for c in str(r.station_id))) % 3]
        ch_occ = max(0, min(ch_slots, base_ch + bias))
        sw_occ = occ_total - ch_occ
        if sw_occ < 0:
            sw_occ = 0
        if sw_occ > sw_slots:
            overflow = sw_occ - sw_slots
            sw_occ = sw_slots
            ch_occ = min(ch_slots, ch_occ + overflow)
        ch_av = max(0, ch_slots - ch_occ)
        sw_av = max(0, sw_slots - sw_occ)
        swap_batt = max(0, int(r.available_swap_batteries))

    status_rows.append({
        'station_id': r.station_id,
        'timestamp': r.timestamp,
        'operating_status': op,
        'available_charging_slots': int(ch_av),
        'occupied_charging_slots': int(ch_occ),
        'available_swap_slots': int(sw_av),
        'occupied_swap_slots': int(sw_occ),
        'available_swap_batteries': int(swap_batt),
        'charging_service_time_min': float(CHARGING_SERVICE_TIME_MIN if ch_slots > 0 else 0.0),
        'swap_service_time_min': float(SWAP_SERVICE_TIME_MIN if sw_slots > 0 else 0.0),
    })
status = pd.DataFrame(status_rows)

status_idx = status.set_index(['station_id', 'timestamp'])

# -----------------------------------------------------------------------------
# 2) Transform queue into independent charging/swap queue states.
# -----------------------------------------------------------------------------
queue_rows = []
for r in old_queue.itertuples(index=False):
    s = st_meta.loc[r.station_id]
    sr = status_idx.loc[(r.station_id, r.timestamp)]
    old_q = max(0, int(r.queue_length))
    ch_occ = int(sr.occupied_charging_slots)
    sw_occ = int(sr.occupied_swap_slots)
    op = str(sr.operating_status)

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
            if ch_occ == 0:
                ch_q, sw_q = 0, old_q
            if sw_occ == 0:
                ch_q, sw_q = old_q, 0

    ch_active = ch_occ if op == 'OPEN' else 0
    sw_active = sw_occ if op == 'OPEN' else 0
    ch_wait = (ch_q * CHARGING_SERVICE_TIME_MIN / ch_active) if ch_q > 0 and ch_active > 0 else 0.0
    sw_wait = (sw_q * SWAP_SERVICE_TIME_MIN / sw_active) if sw_q > 0 and sw_active > 0 else 0.0
    queue_rows.append({
        'station_id': r.station_id,
        'timestamp': r.timestamp,
        'charging_queue_length': int(ch_q),
        'charging_active_service_count': int(ch_active),
        'charging_service_time_min': float(CHARGING_SERVICE_TIME_MIN if int(s.charging_slots) > 0 else 0.0),
        'charging_estimated_wait_min': round(float(ch_wait), 2),
        'swap_queue_length': int(sw_q),
        'swap_active_service_count': int(sw_active),
        'swap_service_time_min': float(SWAP_SERVICE_TIME_MIN if int(s.swap_slots) > 0 else 0.0),
        'swap_estimated_wait_min': round(float(sw_wait), 2),
    })
queue = pd.DataFrame(queue_rows)

# Helpers patch one service at an exact station/timestamp while preserving the other service.
def set_service_state(station_id, ts_iso, service, *, available=1, target_wait_min=0.0):
    sm = status.station_id.eq(station_id) & status.timestamp.eq(ts_iso)
    qm = queue.station_id.eq(station_id) & queue.timestamp.eq(ts_iso)
    if not sm.any() or not qm.any():
        return None
    s = st_meta.loc[station_id]
    slots = service_slots(s, service)
    if slots <= 0:
        return None
    status.loc[sm, 'operating_status'] = 'OPEN'
    avail = max(1, min(int(available), slots))
    if target_wait_min > 0:
        if slots < 2:
            return None
        avail = min(avail, slots - 1)
        occupied = max(1, slots - avail)
    else:
        occupied = max(0, slots - avail)
    if service == 'CHARGING':
        status.loc[sm, ['available_charging_slots', 'occupied_charging_slots']] = [avail, occupied]
        svc = CHARGING_SERVICE_TIME_MIN
        active = occupied
        qlen = int(math.ceil(float(target_wait_min) * active / svc)) if target_wait_min > 0 and active > 0 else 0
        wait = qlen * svc / active if qlen and active else 0.0
        queue.loc[qm, ['charging_queue_length', 'charging_active_service_count', 'charging_service_time_min', 'charging_estimated_wait_min']] = [qlen, active, svc, round(wait, 2)]
    else:
        status.loc[sm, ['available_swap_slots', 'occupied_swap_slots']] = [avail, occupied]
        status.loc[sm, 'available_swap_batteries'] = max(1, int(status.loc[sm, 'available_swap_batteries'].iloc[0]))
        svc = SWAP_SERVICE_TIME_MIN
        active = occupied
        qlen = int(math.ceil(float(target_wait_min) * active / svc)) if target_wait_min > 0 and active > 0 else 0
        wait = qlen * svc / active if qlen and active else 0.0
        queue.loc[qm, ['swap_queue_length', 'swap_active_service_count', 'swap_service_time_min', 'swap_estimated_wait_min']] = [qlen, active, svc, round(wait, 2)]
    return round(float(wait), 2)

# Preserve explicit long-queue and realtime-queue conditions using the requested service.
for scenario_name in ['LONG_QUEUE', 'QUEUE_REALTIME_CHANGE']:
    row = scenario_cov[scenario_cov.scenario_id.eq(scenario_name)]
    if row.empty:
        continue
    r = row.iloc[0]
    ev = demand[demand.event_id.eq(r.example_event_id)]
    if ev.empty:
        continue
    service = str(ev.iloc[0].service_type)
    sid = str(r.evidence_entity_a)
    if scenario_name == 'LONG_QUEUE':
        set_service_state(sid, str(r.evidence_timestamp), service, available=1, target_wait_min=45.0)
    else:
        set_service_state(sid, str(r.before_timestamp), service, available=2, target_wait_min=0.0)
        set_service_state(sid, str(r.after_timestamp), service, available=1, target_wait_min=45.0)

# -----------------------------------------------------------------------------
# 3) Build route reference matrices from existing road network only.
# -----------------------------------------------------------------------------
node_ids = nodes.node_id.astype(str).tolist()
node_to_i = {nid: i for i, nid in enumerate(node_ids)}
usable = segs[~segs.access.astype(str).str.lower().isin(['no', 'private'])].copy()
usable = usable[usable.from_node_id.isin(node_to_i) & usable.to_node_id.isin(node_to_i)]
usable['speed'] = pd.to_numeric(usable.maxspeed_kmh, errors='coerce').fillna(30.0).clip(lower=5.0)
usable['ff_time_sec'] = usable.length_m.astype(float) / usable.speed * 3.6
pair = usable.groupby(['from_node_id', 'to_node_id'], as_index=False).agg(length_m=('length_m', 'min'), ff_time_sec=('ff_time_sec', 'min'))
rows = pair.from_node_id.map(node_to_i).to_numpy()
cols = pair.to_node_id.map(node_to_i).to_numpy()
N = len(node_ids)
Gdist = csr_matrix((pair.length_m.to_numpy(float), (rows, cols)), shape=(N, N))
Gtime = csr_matrix((pair.ff_time_sec.to_numpy(float), (rows, cols)), shape=(N, N))
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

# Traffic factor helper.
traffic_median = traffic.groupby('timestamp').delay_factor.median().to_dict()
traffic_lookup = traffic.set_index(['segment_id', 'timestamp'])

# -----------------------------------------------------------------------------
# 4) Strengthen FARTHER_BUT_FASTER with a documented >=10-minute ETA margin.
# -----------------------------------------------------------------------------
farther_patches = []
farther_trips = trips.loc[trips.scenario_id.eq('FARTHER_BUT_FASTER'), 'trip_id'].tolist()
for tid in farther_trips:
    egrp = events[(events.trip_id.eq(tid)) & events.need_service].copy()
    if egrp.empty:
        continue
    egrp['_mid'] = (egrp.snapshot_index.astype(int) - 4).abs()
    ev = egrp.sort_values('_mid').iloc[0]
    ei = event_pos[ev.event_id]
    v = veh_idx.loc[trip_idx.loc[tid].vehicle_id]
    service = str(ev.service_type)
    dest_i = dest_pos[str(ev.destination_node_id)]
    traf_ts = floor_iso(ev.timestamp, 30)
    station_factor = float(traffic_median.get(traf_ts, 1.0))
    local_factor = station_factor
    k = (str(ev.true_segment_id), traf_ts)
    if k in traffic_lookup.index:
        z = traffic_lookup.loc[k]
        z = z.iloc[0] if isinstance(z, pd.DataFrame) else z
        local_factor = float(z.delay_factor)

    pool = []
    for s in stations.itertuples(index=False):
        if not compatible(v, s, service):
            continue
        sj = station_pos[s.station_id]
        d1 = float(event_station_dist[ei, sj])
        d2 = float(station_dest_dist_unique[dest_i, sj])
        eta1 = float(event_station_time[ei, sj])
        eta2 = float(station_dest_time_unique[dest_i, sj])
        if not all(np.isfinite(x) for x in [d1, d2, eta1, eta2]):
            continue
        if d1 / 1000.0 + SOC_REACH_BUFFER_KM > float(ev.estimated_remaining_range_km):
            continue
        slots = service_slots(st_meta.loc[s.station_id], service)
        if slots <= 0:
            continue
        base_eta = eta1 * local_factor + eta2 * station_factor + service_time(service)
        pool.append({'station_id': s.station_id, 'd1': d1, 'base_eta': base_eta, 'slots': slots})
    pool = sorted(pool, key=lambda x: x['d1'])

    choices = []
    for a in range(len(pool) - 1):
        near = pool[a]
        if near['slots'] < 2:
            continue
        for b in range(a + 1, len(pool)):
            far = pool[b]
            delta_d = far['d1'] - near['d1']
            if delta_d < FARTHER_MIN_DISTANCE_DELTA_M:
                continue
            required_wait = far['base_eta'] - near['base_eta'] + FARTHER_MEANINGFUL_ETA_MARGIN_MIN + 2.0
            target_wait = max(20.0, required_wait)
            if target_wait <= 80.0:
                choices.append((target_wait, delta_d, near, far))
    if not choices:
        continue
    target_wait, delta_d, near, far = sorted(choices, key=lambda x: (x[0], x[1]))[0]
    state_ts = floor_iso(ev.timestamp, 10)
    actual_near_wait = set_service_state(near['station_id'], state_ts, service, available=1, target_wait_min=target_wait)
    actual_far_wait = set_service_state(far['station_id'], state_ts, service, available=min(2, far['slots']), target_wait_min=0.0)
    if actual_near_wait is None or actual_far_wait is None:
        continue
    near_total = near['base_eta'] + actual_near_wait
    far_total = far['base_eta'] + actual_far_wait
    farther_patches.append({
        'trip_id': tid,
        'event_id': ev.event_id,
        'service_type': service,
        'state_timestamp': state_ts,
        'near_station_id': near['station_id'],
        'far_station_id': far['station_id'],
        'near_distance_m': round(near['d1'], 1),
        'far_distance_m': round(far['d1'], 1),
        'distance_delta_m': round(far['d1'] - near['d1'], 1),
        'near_wait_min': round(actual_near_wait, 2),
        'far_wait_min': round(actual_far_wait, 2),
        'near_total_eta_min_pre_ranking': round(near_total, 3),
        'far_total_eta_min_pre_ranking': round(far_total, 3),
        'eta_improvement_min_pre_ranking': round(near_total - far_total, 3),
    })

# Persist service-specific station/queue states now that scenario patches are applied.
status.to_csv(ROOT / 'stations/station_status.csv.gz', index=False, compression='gzip')
queue.to_csv(ROOT / 'queue/queue_status.csv.gz', index=False, compression='gzip')

# -----------------------------------------------------------------------------
# 5) Recompute Candidate Search labels from service-specific state.
# -----------------------------------------------------------------------------
status_lookup = status.set_index(['station_id', 'timestamp'])
queue_lookup = queue.set_index(['station_id', 'timestamp'])
old_dist = old_candidates.set_index(['event_id', 'station_id']).network_distance_m.to_dict()

candidate_rows = []
for ev in events.itertuples(index=False):
    v = veh_idx.loc[trip_idx.loc[ev.trip_id].vehicle_id]
    state_ts = floor_iso(ev.timestamp, 10)
    for s in stations.itertuples(index=False):
        dist = old_dist.get((ev.event_id, s.station_id), np.nan)
        reach = pd.notna(dist) and np.isfinite(float(dist))
        comp = compatible(v, s, ev.service_type) if bool(ev.need_service) else False
        sr = status_lookup.loc[(s.station_id, state_ts)] if (s.station_id, state_ts) in status_lookup.index else None
        qr = queue_lookup.loc[(s.station_id, state_ts)] if (s.station_id, state_ts) in queue_lookup.index else None
        if isinstance(sr, pd.DataFrame): sr = sr.iloc[0]
        if isinstance(qr, pd.DataFrame): qr = qr.iloc[0]
        op = str(sr.operating_status) if sr is not None else 'UNKNOWN'
        if ev.service_type == 'CHARGING':
            slots_avail = int(sr.available_charging_slots) if sr is not None else 0
            swap_batt = 0
            capacity = slots_avail
            wait = float(qr.charging_estimated_wait_min) if qr is not None else float('inf')
            svc = float(sr.charging_service_time_min) if sr is not None else CHARGING_SERVICE_TIME_MIN
            qlen = int(qr.charging_queue_length) if qr is not None else 0
        elif ev.service_type == 'BATTERY_SWAP':
            slots_avail = int(sr.available_swap_slots) if sr is not None else 0
            swap_batt = int(sr.available_swap_batteries) if sr is not None else 0
            capacity = min(slots_avail, swap_batt)
            wait = float(qr.swap_estimated_wait_min) if qr is not None else float('inf')
            svc = float(sr.swap_service_time_min) if sr is not None else SWAP_SERVICE_TIME_MIN
            qlen = int(qr.swap_queue_length) if qr is not None else 0
        else:
            slots_avail = swap_batt = capacity = qlen = 0
            wait = 0.0
            svc = 0.0
        feasible = bool(reach and (float(dist) / 1000.0 + SOC_REACH_BUFFER_KM <= float(ev.estimated_remaining_range_km)))
        if not bool(ev.need_service):
            eligible, reason = False, 'NO_SERVICE_NEEDED'
        elif not comp:
            eligible, reason = False, 'INCOMPATIBLE'
        elif not reach:
            eligible, reason = False, 'UNREACHABLE'
        elif op != 'OPEN':
            eligible, reason = False, 'OFFLINE'
        elif ev.service_type == 'BATTERY_SWAP' and slots_avail > 0 and swap_batt <= 0:
            eligible, reason = False, 'NO_SWAP_BATTERY'
        elif capacity <= 0:
            eligible, reason = False, 'FULL'
        elif wait > MAX_WAIT_MIN:
            eligible, reason = False, 'EXCESSIVE_QUEUE'
        elif not feasible:
            eligible, reason = False, 'INSUFFICIENT_SOC_TO_REACH'
        else:
            eligible, reason = True, 'ELIGIBLE'
        candidate_rows.append({
            'event_id': ev.event_id,
            'station_id': s.station_id,
            'service_type': ev.service_type,
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
            'service_time_min': round(float(svc), 2),
            'state_timestamp': state_ts,
        })

candidates = pd.DataFrame(candidate_rows)
candidates.to_csv(ROOT / 'labels/candidate_labels.csv', index=False)

# -----------------------------------------------------------------------------
# 6) Ranking consumes ONLY Candidate Search eligible output.
# -----------------------------------------------------------------------------
status_lookup = status.set_index(['station_id', 'timestamp'])
queue_lookup = queue.set_index(['station_id', 'timestamp'])
ranking_rows = []
recommendation_rows = []
service_events = events[events.need_service].copy()

for ev in service_events.itertuples(index=False):
    eligible = candidates[(candidates.event_id.eq(ev.event_id)) & bs(candidates.eligible)].copy()
    eligible = eligible.sort_values(['network_distance_m', 'station_id'])
    eligible_count = len(eligible)
    if eligible_count == 0:
        recommendation_rows.append({
            'event_id': ev.event_id,
            'eligible_candidate_count': 0,
            'has_recommendation': False,
            'reference_station_id': None,
            'label_method': 'NO_ELIGIBLE_STATION',
        })
        continue

    group = eligible.head(MAX_RANK_CANDIDATES).copy()
    ei = event_pos[ev.event_id]
    dest_i = dest_pos[str(ev.destination_node_id)]
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
        sj = station_pos[cr.station_id]
        d1 = float(cr.network_distance_m)
        d2 = float(station_dest_dist_unique[dest_i, sj])
        eta1 = float(event_station_time[ei, sj])
        eta2 = float(station_dest_time_unique[dest_i, sj])
        if not all(np.isfinite(x) for x in [d1, d2, eta1, eta2]):
            # Candidate Search should already mark unreachable false; skip defensively.
            continue
        direct_d = float(ev.direct_distance_m)
        direct_eta = max(0.0, float(ev.direct_eta_min))
        detour_d = max(0.0, d1 + d2 - direct_d)
        detour_t = max(0.0, eta1 + eta2 - direct_eta)
        traffic_eta = eta1 * driver_factor + eta2 * station_factor
        wait = float(cr.estimated_wait_min)
        svc = float(cr.service_time_min)
        total_eta = traffic_eta + wait + svc
        cost = total_eta + 0.25 * detour_t + 0.002 * detour_d - 0.35 * min(int(cr.available_capacity), 6)
        tmp.append({
            'event_id': ev.event_id,
            'trip_id': ev.trip_id,
            'station_id': cr.station_id,
            'service_type': ev.service_type,
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
    recommendation_rows.append({
        'event_id': ev.event_id,
        'eligible_candidate_count': int(eligible_count),
        'has_recommendation': bool(best is not None),
        'reference_station_id': best['station_id'] if best else None,
        'label_method': 'eligible_candidates_documented_baseline_cost_v3' if best else 'NO_ELIGIBLE_STATION',
    })

ranking = pd.DataFrame(ranking_rows)
recommendations = pd.DataFrame(recommendation_rows)
ranking.to_csv(ROOT / 'training/ranking_reference.csv', index=False)
recommendations.to_csv(ROOT / 'labels/recommendation_labels.csv', index=False)

# -----------------------------------------------------------------------------
# 7) Rebuild realtime replay with explicit service-specific station + queue state.
# -----------------------------------------------------------------------------
recs = []
def add(ts, typ, entity, payload):
    recs.append({'timestamp': ts, 'event_type': typ, 'entity_id': entity, 'payload_json': json.dumps(payload, separators=(',', ':'))})

for r in gps.iloc[::8].itertuples(index=False):
    add(r.timestamp, 'GPS_UPDATE', r.trip_id, {'observation_id': r.observation_id, 'lat': round(float(r.latitude), 7), 'lon': round(float(r.longitude), 7)})
for r in battery.iloc[::12].itertuples(index=False):
    add(r.timestamp, 'SOC_UPDATE', r.trip_id, {'soc_pct': float(r.soc_pct), 'remaining_range_km': float(r.estimated_remaining_range_km)})
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

special_tids = set(trips.loc[trips.scenario_id.isin(['TRAFFIC_REALTIME_CHANGE', 'HEAVY_TRAFFIC']), 'trip_id'])
special_sids = set(true.loc[true.trip_id.isin(special_tids), 'true_segment_id'])
traf_keep = pd.concat([traffic.sample(min(3000, len(traffic)), random_state=SEED), traffic[traffic.segment_id.isin(special_sids)]], ignore_index=True).drop_duplicates(['segment_id', 'timestamp'])
for r in traf_keep.itertuples(index=False):
    add(r.timestamp, 'TRAFFIC_UPDATE', r.segment_id, {'traffic_level': r.traffic_level, 'current_speed_kmh': float(r.current_speed_kmh)})
replay = pd.DataFrame(recs).sort_values(['timestamp', 'event_type', 'entity_id']).reset_index(drop=True)
replay.insert(0, 'event_id', [f'RE{i+1:08d}' for i in range(len(replay))])
replay.to_csv(ROOT / 'realtime/events.csv.gz', index=False, compression='gzip')

# -----------------------------------------------------------------------------
# 8) Update FARTHER_BUT_FASTER quantitative evidence from the final ranking rows.
# -----------------------------------------------------------------------------
farther_evidence = None
for fp in farther_patches:
    rr = ranking[ranking.event_id.eq(fp['event_id'])].set_index('station_id')
    a = fp['near_station_id']; b = fp['far_station_id']
    if a in rr.index and b in rr.index:
        near = rr.loc[a]; far = rr.loc[b]
        dist_delta = float(far.driver_to_station_distance_m) - float(near.driver_to_station_distance_m)
        eta_gain = float(near.total_eta_min) - float(far.total_eta_min)
        if dist_delta >= FARTHER_MIN_DISTANCE_DELTA_M and eta_gain >= FARTHER_MEANINGFUL_ETA_MARGIN_MIN:
            farther_evidence = {**fp, 'distance_delta_m': round(dist_delta, 1), 'eta_improvement_min': round(eta_gain, 3), 'near_total_eta_min': round(float(near.total_eta_min), 3), 'far_total_eta_min': round(float(far.total_eta_min), 3)}
            break

if farther_evidence:
    m = scenario_cov.scenario_id.eq('FARTHER_BUT_FASTER')
    scenario_cov.loc[m, 'example_trip_id'] = farther_evidence['trip_id']
    scenario_cov.loc[m, 'example_event_id'] = farther_evidence['event_id']
    scenario_cov.loc[m, 'validator_status'] = 'PASS'
    scenario_cov.loc[m, 'primary_metric'] = 'farther_total_eta_improvement_min'
    scenario_cov.loc[m, 'primary_value'] = farther_evidence['eta_improvement_min']
    scenario_cov.loc[m, 'operator'] = '>='
    scenario_cov.loc[m, 'threshold'] = FARTHER_MEANINGFUL_ETA_MARGIN_MIN
    scenario_cov.loc[m, 'secondary_metric'] = 'farther_network_distance_delta_m'
    scenario_cov.loc[m, 'secondary_value'] = farther_evidence['distance_delta_m']
    scenario_cov.loc[m, 'evidence_entity_a'] = farther_evidence['near_station_id']
    scenario_cov.loc[m, 'evidence_entity_b'] = farther_evidence['far_station_id']
    scenario_cov.loc[m, 'evidence_timestamp'] = farther_evidence['state_timestamp']
    scenario_cov.loc[m, 'evidence_note'] = f"near_total_eta={farther_evidence['near_total_eta_min']:.3f}; far_total_eta={farther_evidence['far_total_eta_min']:.3f}; meaningful_margin_threshold={FARTHER_MEANINGFUL_ETA_MARGIN_MIN:.1f}min"
scenario_cov.to_csv(ROOT / 'scenarios/scenario_coverage.csv', index=False)

# -----------------------------------------------------------------------------
# 9) Stats/config. Validation script independently recomputes all invariants later.
# -----------------------------------------------------------------------------
elig_counts = candidates[candidates.event_id.isin(service_events.event_id)].groupby('event_id').eligible.apply(lambda x: int(bs(x).sum()))
elig_counts = service_events.set_index('event_id').index.to_series().map(elig_counts).fillna(0).astype(int)
group_sizes = ranking.groupby('event_id').size() if len(ranking) else pd.Series(dtype=int)
rank_stats = {
    'rows': int(len(ranking)),
    'event_groups': int(ranking.event_id.nunique()) if len(ranking) else 0,
    'group_size_min': int(group_sizes.min()) if len(group_sizes) else 0,
    'group_size_max': int(group_sizes.max()) if len(group_sizes) else 0,
    'group_size_distribution': {str(int(k)): int(v) for k, v in group_sizes.value_counts().sort_index().items()},
    'ltr_event_groups': int(ranking.loc[bs(ranking.is_ltr_group), 'event_id'].nunique()) if len(ranking) else 0,
    'single_candidate_groups': int((group_sizes == 1).sum()) if len(group_sizes) else 0,
    'split_groups': ranking.drop_duplicates('event_id').split.value_counts().to_dict() if len(ranking) else {},
    'pipeline': 'all stations -> Candidate Search -> eligible=true -> nearest top-N eligible (max 8) -> Ranking',
}
json.dump(rank_stats, open(ROOT / 'validation/ranking_stats.json', 'w'), indent=2)

eligible_stats = {
    'service_event_count': int(len(service_events)),
    'events_with_eligible_station': int((elig_counts > 0).sum()),
    'events_with_no_eligible_station': int((elig_counts == 0).sum()),
    'events_with_exactly_one_eligible_station': int((elig_counts == 1).sum()),
    'events_with_two_or_more_eligible_stations': int((elig_counts >= 2).sum()),
    'eligible_count_distribution': {str(int(k)): int(v) for k, v in elig_counts.value_counts().sort_index().items()},
    'recommendation_label_rows': int(len(recommendations)),
    'has_recommendation_true': int(bs(recommendations.has_recommendation).sum()),
    'has_recommendation_false': int((~bs(recommendations.has_recommendation)).sum()),
}
json.dump(eligible_stats, open(ROOT / 'validation/eligible_candidate_stats.json', 'w'), indent=2)
json.dump({'threshold_min': FARTHER_MEANINGFUL_ETA_MARGIN_MIN, 'min_distance_delta_m': FARTHER_MIN_DISTANCE_DELTA_M, 'evidence': farther_evidence, 'patched_events': farther_patches}, open(ROOT / 'validation/farther_but_faster_evidence.json', 'w'), indent=2)

baseline = {
    'version': 'v3',
    'candidate_pipeline': 'All stations -> Candidate Search -> eligible == true -> nearest top-N eligible candidates (N<=8) -> Ranking',
    'group_policy': 'Variable group size 1..8; groups with >=2 candidates are LTR-eligible; groups with 1 candidate retained for evaluation/recommendation only.',
    'features': [
        'driver_to_station_distance_m', 'driver_to_station_eta_min', 'station_to_destination_distance_m', 'station_to_destination_eta_min',
        'direct_driver_to_destination_distance_m', 'direct_driver_to_destination_eta_min', 'detour_distance_m', 'detour_time_min',
        'traffic_adjusted_eta_min', 'queue_wait_min', 'service_time_min', 'available_capacity', 'operating_status', 'soc_feasible'
    ],
    'cost_formula': 'traffic_adjusted_eta_min + queue_wait_min + service_time_min + 0.25*detour_time_min + 0.002*detour_distance_m - 0.35*min(available_capacity,6)',
    'eligibility_rule': 'Ranking rows are created only from candidate_labels.eligible == true.',
    'service_capacity': {'CHARGING': 'available_charging_slots', 'BATTERY_SWAP': 'min(available_swap_slots, available_swap_batteries)'},
    'service_time': {'CHARGING': CHARGING_SERVICE_TIME_MIN, 'BATTERY_SWAP': SWAP_SERVICE_TIME_MIN},
    'farther_but_faster_meaningful_margin_min': FARTHER_MEANINGFUL_ETA_MARGIN_MIN,
    'note': 'reference/recommendation labels are evaluation/training artifacts and are not runtime inputs.'
}
json.dump(baseline, open(ROOT / 'config/ranking_baseline.json', 'w'), indent=2)

print(json.dumps({'eligible_candidate_stats': eligible_stats, 'ranking_stats': rank_stats, 'farther_but_faster': farther_evidence}, indent=2))
