from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BASELINE_SHA256 = 'f69011f81fdc40d63e32a978a8ab15366ba87e8922f75c55821daf139e53ddb7'
EXPECTED_PATCHED_SHA256 = '0d3a66b2fb03019fd9d7877115c1ed9efbb736a83c5ac6f6e5440d71ddcfff60'
SOC_REACH_BUFFER_KM = 0.5
MAX_WAIT_MIN = 90.0
MAX_RANK_CANDIDATES = 8
NEAR_TIE_THRESHOLD_MIN = 3.0
FARTHER_MIN_DISTANCE_DELTA_M = 500.0
FARTHER_MEANINGFUL_ETA_MARGIN_MIN = 10.0
CHARGING_SERVICE_TIME_MIN = 18.0
SWAP_SERVICE_TIME_MIN = 6.0
res = []
scenario_results = []


def check(name, ok, details=''):
    ok = bool(ok)
    res.append({'check': name, 'status': 'PASS' if ok else 'FAIL', 'details': str(details)})
    return ok


def scenario_check(name, ok, details='', metrics=None):
    ok = bool(ok)
    scenario_results.append({'scenario_id': name, 'status': 'PASS' if ok else 'FAIL', 'details': str(details), 'metrics': metrics or {}})
    return ok


def bs(s):
    if getattr(s, 'dtype', None) == bool:
        return s
    return s.astype(str).str.lower().isin(['true', '1', 'yes'])


def tokens(v):
    if pd.isna(v): return set()
    return {x.strip() for x in str(v).replace(',', ';').split(';') if x.strip()}


def compatible(v, s, service):
    if service == 'CHARGING':
        if not bool(v.charging_supported) or 'CHARGING' not in str(s.station_type): return False
    elif service == 'BATTERY_SWAP':
        if not bool(v.swap_supported) or 'SWAP' not in str(s.station_type): return False
    else:
        return False
    if str(v.vehicle_type) not in tokens(s.supported_vehicle_type): return False
    if str(v.connector_type) not in tokens(s.connector_type): return False
    if service == 'BATTERY_SWAP' and (pd.isna(s.battery_type) or str(v.battery_type) not in tokens(s.battery_type)): return False
    return True


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1024 * 1024), b''):
            h.update(c)
    return h.hexdigest()


def hav_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# Load current patched data.
nodes = pd.read_csv(ROOT / 'map/processed/road_nodes.csv.gz')
segs = pd.read_csv(ROOT / 'map/processed/road_segments.csv.gz', dtype={'osm_way_id': str})
drivers = pd.read_csv(ROOT / 'drivers/drivers.csv')
vehicles = pd.read_csv(ROOT / 'vehicles/vehicles.csv')
trips = pd.read_csv(ROOT / 'trips/trips.csv')
true = pd.read_csv(ROOT / 'trajectories/true_trajectories.csv.gz')
gps = pd.read_csv(ROOT / 'gps/gps_observations.csv.gz')
bat = pd.read_csv(ROOT / 'battery/soc_history.csv.gz')
st = pd.read_csv(ROOT / 'stations/stations.csv')
ss = pd.read_csv(ROOT / 'stations/station_status.csv.gz')
q = pd.read_csv(ROOT / 'queue/queue_status.csv.gz')
traf = pd.read_csv(ROOT / 'traffic/traffic_snapshots.csv.gz')
replay = pd.read_csv(ROOT / 'realtime/events.csv.gz')
splits = pd.read_csv(ROOT / 'training/trip_splits.csv')
mm_labels = pd.read_csv(ROOT / 'labels/map_matching_labels.csv.gz')
mmc = pd.read_csv(ROOT / 'training/map_matching_candidates_with_split.csv.gz')
demand = pd.read_csv(ROOT / 'labels/demand_labels.csv')
df = pd.read_csv(ROOT / 'training/demand_features.csv')
cand = pd.read_csv(ROOT / 'labels/candidate_labels.csv')
rank = pd.read_csv(ROOT / 'training/ranking_reference.csv')
rec = pd.read_csv(ROOT / 'labels/recommendation_labels.csv')
sc = pd.read_csv(ROOT / 'scenarios/scenario_coverage.csv')

# -----------------------------------------------------------------------------
# 1. Structural / referential / chronology checks.
# -----------------------------------------------------------------------------
for name, d, key in [
    ('nodes', nodes, 'node_id'), ('segments', segs, 'segment_id'), ('drivers', drivers, 'driver_id'),
    ('vehicles', vehicles, 'vehicle_id'), ('trips', trips, 'trip_id'), ('gps', gps, 'observation_id'),
    ('stations', st, 'station_id'), ('replay', replay, 'event_id'), ('demand', demand, 'event_id')
]:
    check(f'PK unique: {name}', d[key].notna().all() and not d[key].duplicated().any(), f'rows={len(d)}')
check('Candidate composite key unique', not cand.duplicated(['event_id', 'station_id']).any(), f'rows={len(cand)}')
check('Ranking composite key unique', not rank.duplicated(['event_id', 'station_id']).any(), f'rows={len(rank)}')
check('Station state composite key unique', not ss.duplicated(['station_id', 'timestamp']).any())
check('Queue state composite key unique', not q.duplicated(['station_id', 'timestamp']).any())
check('FK vehicle.driver -> drivers', set(vehicles.driver_id) <= set(drivers.driver_id))
check('FK trip.driver -> drivers', set(trips.driver_id) <= set(drivers.driver_id))
check('FK trip.vehicle -> vehicles', set(trips.vehicle_id) <= set(vehicles.vehicle_id))
check('FK segment nodes exist', set(segs.from_node_id) <= set(nodes.node_id) and set(segs.to_node_id) <= set(nodes.node_id))
check('FK true.segment -> road_segments', set(true.true_segment_id) <= set(segs.segment_id))
check('FK GPS trip/trajectory', set(gps.trip_id) <= set(trips.trip_id) and set(gps.trajectory_id) <= set(true.trajectory_id))
check('FK station.access_node -> road_nodes', set(st.access_node_id) <= set(nodes.node_id))
check('FK traffic.segment -> road_segments', set(traf.segment_id) <= set(segs.segment_id))
check('FK station temporal state -> stations', set(ss.station_id) <= set(st.station_id) and set(q.station_id) <= set(st.station_id))
check('FK demand -> trips', set(demand.trip_id) <= set(trips.trip_id))
check('FK candidates -> demand/stations', set(cand.event_id) <= set(demand.event_id) and set(cand.station_id) <= set(st.station_id))
check('FK ranking -> demand/stations/trips', set(rank.event_id) <= set(demand.event_id) and set(rank.station_id) <= set(st.station_id) and set(rank.trip_id) <= set(trips.trip_id))
check('FK recommendations -> demand', set(rec.event_id) <= set(demand.event_id))

for name, d, cols in [
    ('trips', trips, ['trip_id', 'driver_id', 'vehicle_id', 'origin_node_id', 'destination_node_id']),
    ('true', true, ['trip_id', 'timestamp', 'true_segment_id', 'true_latitude', 'true_longitude']),
    ('gps', gps, ['observation_id', 'trip_id', 'timestamp', 'latitude', 'longitude']),
    ('battery', bat, ['vehicle_id', 'trip_id', 'timestamp', 'soc_pct']),
    ('traffic', traf, ['segment_id', 'timestamp', 'current_speed_kmh']),
    ('demand', demand, ['event_id', 'trip_id', 'timestamp', 'service_type']),
    ('candidate', cand, ['event_id', 'station_id', 'service_type', 'reason']),
    ('ranking', rank, ['event_id', 'station_id', 'service_type', 'ranking_cost_label']),
    ('station_status', ss, ['station_id', 'timestamp', 'operating_status']),
    ('queue', q, ['station_id', 'timestamp'])
]:
    check(f'Critical nulls: {name}', not d[cols].isna().any().any())

check('Road node coordinate bounds', nodes.latitude.between(-90, 90).all() and nodes.longitude.between(-180, 180).all())
check('GPS coordinate bounds', gps.latitude.between(-90, 90).all() and gps.longitude.between(-180, 180).all())
check('Station coordinate bounds', st.latitude.between(-90, 90).all() and st.longitude.between(-180, 180).all())
check('Trajectory timestamp ordering', all(pd.to_datetime(g.timestamp, format='mixed').is_monotonic_increasing for _, g in true.groupby('trip_id')))
check('SOC timestamp ordering', all(pd.to_datetime(g.timestamp, format='mixed').is_monotonic_increasing for _, g in bat.groupby('trip_id')))
check('Replay event chronology', pd.to_datetime(replay.timestamp, format='mixed').is_monotonic_increasing)
segmap = segs.set_index('segment_id')[['from_node_id', 'to_node_id']].to_dict('index')
bad = 0
for _, g in true.groupby('trip_id'):
    seq = g.true_segment_id[g.true_segment_id.ne(g.true_segment_id.shift())].tolist()
    bad += sum(segmap[a]['to_node_id'] != segmap[b]['from_node_id'] for a, b in zip(seq[:-1], seq[1:]))
check('Trajectory road connectivity', bad == 0, f'bad_transitions={bad}')
check('GPS map-matching truth coverage', len(mm_labels) == len(gps) and set(mm_labels.observation_id) == set(gps.observation_id), f'labels={len(mm_labels)}, gps={len(gps)}')
check('SOC range', bat.soc_pct.between(0, 100).all(), f'min={bat.soc_pct.min():.3f}, max={bat.soc_pct.max():.3f}')
soc_ok = True
for _, g in bat.groupby('trip_id'):
    if (g.distance_travelled_km.diff().fillna(0) < -1e-9).any() or (g.energy_consumed_kwh.diff().fillna(0) < -1e-9).any() or (g.soc_pct.diff().fillna(0) > 0.05).any():
        soc_ok = False; break
check('SOC/distance/energy monotonic consistency', soc_ok)
check('Training split unique per trip', splits.trip_id.is_unique and splits.split.isin(['train', 'validation', 'test']).all())
check('Training split covers trips', set(splits.trip_id) == set(trips.trip_id))

# -----------------------------------------------------------------------------
# 2. Service-specific station capacity and queue semantics.
# -----------------------------------------------------------------------------
state = ss.merge(st[['station_id', 'station_type', 'charging_slots', 'swap_slots']], on='station_id')
for c in ['available_charging_slots', 'occupied_charging_slots', 'available_swap_slots', 'occupied_swap_slots', 'available_swap_batteries']:
    check(f'Station state nonnegative: {c}', (state[c] >= 0).all())
check('Charging capacity <= charging_slots', ((state.available_charging_slots + state.occupied_charging_slots) <= state.charging_slots).all())
check('Swap capacity <= swap_slots', ((state.available_swap_slots + state.occupied_swap_slots) <= state.swap_slots).all())
check('Charging-only station has zero swap state', (state.loc[state.swap_slots.eq(0), ['available_swap_slots', 'occupied_swap_slots', 'available_swap_batteries']].sum(axis=1) == 0).all())
check('Swap-only station has zero charging state', (state.loc[state.charging_slots.eq(0), ['available_charging_slots', 'occupied_charging_slots']].sum(axis=1) == 0).all())
check('Offline station service capacities zero', (state.loc[state.operating_status.ne('OPEN'), ['available_charging_slots', 'occupied_charging_slots', 'available_swap_slots', 'occupied_swap_slots', 'available_swap_batteries']].sum(axis=1) == 0).all())
check('Charging service time column semantics', ((state.charging_slots.eq(0) & state.charging_service_time_min.eq(0)) | (state.charging_slots.gt(0) & np.isclose(state.charging_service_time_min, CHARGING_SERVICE_TIME_MIN))).all())
check('Swap service time column semantics', ((state.swap_slots.eq(0) & state.swap_service_time_min.eq(0)) | (state.swap_slots.gt(0) & np.isclose(state.swap_service_time_min, SWAP_SERVICE_TIME_MIN))).all())
mixed = state[state.station_type.eq('CHARGING_SWAP')]
check('Mixed-station charging capacity bounded', ((mixed.available_charging_slots + mixed.occupied_charging_slots) <= mixed.charging_slots).all(), f'rows={len(mixed)}')
check('Mixed-station swap capacity bounded', ((mixed.available_swap_slots + mixed.occupied_swap_slots) <= mixed.swap_slots).all(), f'rows={len(mixed)}')

qstate = q.merge(ss[['station_id', 'timestamp', 'occupied_charging_slots', 'occupied_swap_slots']], on=['station_id', 'timestamp']).merge(st[['station_id', 'charging_slots', 'swap_slots']], on='station_id')
for c in ['charging_queue_length', 'charging_active_service_count', 'charging_estimated_wait_min', 'swap_queue_length', 'swap_active_service_count', 'swap_estimated_wait_min']:
    check(f'Queue nonnegative: {c}', (qstate[c] >= 0).all())
check('Charging queue active count <= occupied charging slots', (qstate.charging_active_service_count <= qstate.occupied_charging_slots).all())
check('Swap queue active count <= occupied swap slots', (qstate.swap_active_service_count <= qstate.occupied_swap_slots).all())
check('Charging queue uses charging service time', ((qstate.charging_slots.eq(0) & qstate.charging_service_time_min.eq(0)) | (qstate.charging_slots.gt(0) & np.isclose(qstate.charging_service_time_min, CHARGING_SERVICE_TIME_MIN))).all())
check('Swap queue uses swap service time', ((qstate.swap_slots.eq(0) & qstate.swap_service_time_min.eq(0)) | (qstate.swap_slots.gt(0) & np.isclose(qstate.swap_service_time_min, SWAP_SERVICE_TIME_MIN))).all())
ch_expected = np.where((qstate.charging_queue_length > 0) & (qstate.charging_active_service_count > 0), qstate.charging_queue_length * qstate.charging_service_time_min / qstate.charging_active_service_count, 0.0)
sw_expected = np.where((qstate.swap_queue_length > 0) & (qstate.swap_active_service_count > 0), qstate.swap_queue_length * qstate.swap_service_time_min / qstate.swap_active_service_count, 0.0)
check('Charging queue wait formula service-specific', np.allclose(ch_expected, qstate.charging_estimated_wait_min, atol=0.011), f'max_err={float(np.max(np.abs(ch_expected-qstate.charging_estimated_wait_min))):.4f}')
check('Swap queue wait formula service-specific', np.allclose(sw_expected, qstate.swap_estimated_wait_min, atol=0.011), f'max_err={float(np.max(np.abs(sw_expected-qstate.swap_estimated_wait_min))):.4f}')

# -----------------------------------------------------------------------------
# 3. Leakage and demand semantics (must not regress V1.1).
# -----------------------------------------------------------------------------
for name, d in [('gps', gps), ('battery', bat), ('trips', trips), ('station_status', ss), ('traffic', traf)]:
    prohibited = {'is_correct', 'need_service', 'service_type', 'recommended_station_id', 'reference_station_id', 'ranking_cost_label'}
    leak = sorted(prohibited & set(d.columns))
    check(f'No label leakage: {name}', not leak, ','.join(leak))
classes = demand.service_type.value_counts().to_dict()
check('Demand sample count target', len(demand) == 1200, f'rows={len(demand)}')
check('Demand class set', set(classes) == {'NONE', 'CHARGING', 'BATTERY_SWAP'}, classes)
check('Demand all classes non-trivial', all(classes.get(c, 0) >= 50 for c in ['NONE', 'CHARGING', 'BATTERY_SWAP']), classes)
check('Demand snapshots per trip', demand.groupby('trip_id').size().eq(8).all(), demand.groupby('trip_id').size().value_counts().to_dict())
check('Demand feature-label event coverage', set(df.event_id) == set(demand.event_id) and df.event_id.is_unique)
check('Demand need_service consistency', ((demand.service_type.eq('NONE')) == (~bs(demand.need_service))).all())
check('Demand feature split matches trip split', df.merge(splits, on='trip_id', suffixes=('_feature', '_trip')).eval('split_feature == split_trip').all())
trv = trips.merge(vehicles, on='vehicle_id', suffixes=('', '_veh'))
dv = demand.merge(trips[['trip_id', 'vehicle_id', 'scenario_id']], on='trip_id').merge(vehicles[['vehicle_id', 'charging_supported', 'swap_supported', 'vehicle_type', 'connector_type', 'battery_type']], on='vehicle_id')
check('NEED_SWAP vehicle capability', bs(trv.loc[trv.scenario_id.eq('NEED_SWAP'), 'swap_supported']).all(), f"trips={sum(trv.scenario_id.eq('NEED_SWAP'))}")
ns = dv[dv.scenario_id.eq('NEED_SWAP')]
check('NEED_SWAP labels are BATTERY_SWAP', len(ns) > 0 and ns.service_type.eq('BATTERY_SWAP').all(), f'rows={len(ns)}')
check('BATTERY_SWAP label vehicle capability', bs(dv.loc[dv.service_type.eq('BATTERY_SWAP'), 'swap_supported']).all(), f"rows={sum(dv.service_type.eq('BATTERY_SWAP'))}")
check('CHARGING label vehicle capability', bs(dv.loc[dv.service_type.eq('CHARGING'), 'charging_supported']).all(), f"rows={sum(dv.service_type.eq('CHARGING'))}")
check('NO_SERVICE_NEEDED scenario has NONE', dv.loc[dv.scenario_id.eq('NO_SERVICE_NEEDED'), 'service_type'].eq('NONE').all())

# -----------------------------------------------------------------------------
# 4. Candidate Search semantic recomputation with service-specific state.
# -----------------------------------------------------------------------------
v_idx = vehicles.set_index('vehicle_id')
s_idx = st.set_index('station_id')
dmeta = demand.merge(df[['event_id', 'estimated_remaining_range_km']], on='event_id').merge(trips[['trip_id', 'vehicle_id']], on='trip_id').set_index('event_id')
ss_idx = ss.set_index(['station_id', 'timestamp']); q_idx = q.set_index(['station_id', 'timestamp'])
reason_bad = state_bad = soc_bad = service_bad = 0
for r in cand.itertuples(index=False):
    ev = dmeta.loc[r.event_id]; v = v_idx.loc[ev.vehicle_id]; s = s_idx.loc[r.station_id]
    need = bool(demand.loc[demand.event_id.eq(r.event_id), 'need_service'].iloc[0]); service = demand.loc[demand.event_id.eq(r.event_id), 'service_type'].iloc[0]
    comp = compatible(v, s, service) if need else False
    reach = pd.notna(r.network_distance_m) and np.isfinite(float(r.network_distance_m))
    key = (r.station_id, r.state_timestamp)
    sr = ss_idx.loc[key] if key in ss_idx.index else None; qr = q_idx.loc[key] if key in q_idx.index else None
    if isinstance(sr, pd.DataFrame): sr = sr.iloc[0]
    if isinstance(qr, pd.DataFrame): qr = qr.iloc[0]
    op = sr.operating_status if sr is not None else 'UNKNOWN'
    if service == 'CHARGING':
        slots = int(sr.available_charging_slots) if sr is not None else 0
        swap_batt = 0
        capacity = slots
        wait = float(qr.charging_estimated_wait_min) if qr is not None else float('inf')
        svc = float(sr.charging_service_time_min) if sr is not None else CHARGING_SERVICE_TIME_MIN
        qlen = int(qr.charging_queue_length) if qr is not None else 0
    elif service == 'BATTERY_SWAP':
        slots = int(sr.available_swap_slots) if sr is not None else 0
        swap_batt = int(sr.available_swap_batteries) if sr is not None else 0
        capacity = min(slots, swap_batt)
        wait = float(qr.swap_estimated_wait_min) if qr is not None else float('inf')
        svc = float(sr.swap_service_time_min) if sr is not None else SWAP_SERVICE_TIME_MIN
        qlen = int(qr.swap_queue_length) if qr is not None else 0
    else:
        slots = swap_batt = capacity = qlen = 0; wait = 0.0; svc = 0.0
    feasible = bool(reach and (float(r.network_distance_m) / 1000 + SOC_REACH_BUFFER_KM <= float(ev.estimated_remaining_range_km)))
    if not need: expected = 'NO_SERVICE_NEEDED'
    elif not comp: expected = 'INCOMPATIBLE'
    elif not reach: expected = 'UNREACHABLE'
    elif op != 'OPEN': expected = 'OFFLINE'
    elif service == 'BATTERY_SWAP' and slots > 0 and swap_batt <= 0: expected = 'NO_SWAP_BATTERY'
    elif capacity <= 0: expected = 'FULL'
    elif wait > MAX_WAIT_MIN: expected = 'EXCESSIVE_QUEUE'
    elif not feasible: expected = 'INSUFFICIENT_SOC_TO_REACH'
    else: expected = 'ELIGIBLE'
    reason_bad += expected != r.reason
    state_bad += (str(op) != str(r.operating_status) or int(capacity) != int(r.available_capacity) or int(slots) != int(r.available_service_slots) or int(swap_batt) != int(r.available_swap_batteries) or int(qlen) != int(r.queue_length) or (np.isfinite(wait) and abs(wait - float(r.estimated_wait_min)) > 0.011))
    soc_bad += bool(r.soc_feasible) != feasible
    service_bad += (str(r.service_type) != str(service) or abs(float(r.service_time_min) - float(svc)) > 0.011)
check('Candidate full station coverage per event', cand.groupby('event_id').size().eq(len(st)).all(), f'stations={len(st)}')
allowed_reasons = {'ELIGIBLE', 'INCOMPATIBLE', 'OFFLINE', 'FULL', 'UNREACHABLE', 'INSUFFICIENT_SOC_TO_REACH', 'NO_SERVICE_NEEDED', 'NO_SWAP_BATTERY', 'EXCESSIVE_QUEUE'}
check('Candidate allowed reason vocabulary', set(cand.reason) <= allowed_reasons, cand.reason.value_counts().to_dict())
check('Candidate eligible iff ELIGIBLE reason', (bs(cand.eligible) == cand.reason.eq('ELIGIBLE')).all())
check('Candidate reason semantic recomputation', reason_bad == 0, f'mismatches={reason_bad}')
check('Candidate service-state consistency', state_bad == 0, f'mismatches={state_bad}')
check('Candidate SOC-feasibility consistency', soc_bad == 0, f'mismatches={soc_bad}')
check('Candidate service type/time consistency', service_bad == 0, f'mismatches={service_bad}')
for reason in ['ELIGIBLE', 'INCOMPATIBLE', 'OFFLINE', 'FULL', 'UNREACHABLE', 'INSUFFICIENT_SOC_TO_REACH', 'NO_SERVICE_NEEDED']:
    check(f'Candidate reason present: {reason}', int((cand.reason == reason).sum()) > 0, f"count={int((cand.reason == reason).sum())}")
swap_c = cand[cand.service_type.eq('BATTERY_SWAP')]
check('Swap candidate capacity <= available swap slots', (swap_c.available_capacity <= swap_c.available_service_slots).all())
check('Swap candidate capacity <= available swap batteries', (swap_c.available_capacity <= swap_c.available_swap_batteries).all())
charge_c = cand[cand.service_type.eq('CHARGING')]
check('Charging candidate uses charging capacity', (charge_c.available_capacity == charge_c.available_service_slots).all())
charge_supported = charge_c.merge(st[['station_id','charging_slots']], on='station_id', how='left')
swap_supported_rows = swap_c.merge(st[['station_id','swap_slots']], on='station_id', how='left')
check('Charging supported candidate uses charging service time', np.isclose(charge_supported.loc[charge_supported.charging_slots.gt(0), 'service_time_min'], CHARGING_SERVICE_TIME_MIN).all(), f"supported_rows={int(charge_supported.charging_slots.gt(0).sum())}")
check('Battery-swap supported candidate uses swap service time', np.isclose(swap_supported_rows.loc[swap_supported_rows.swap_slots.gt(0), 'service_time_min'], SWAP_SERVICE_TIME_MIN).all(), f"supported_rows={int(swap_supported_rows.swap_slots.gt(0).sum())}")

# -----------------------------------------------------------------------------
# 5. Map-matching guarantees (must not regress).
# -----------------------------------------------------------------------------
mmc['pos'] = bs(mmc.is_correct); mmc['hard'] = bs(mmc.hard_negative)
g = mmc.groupby('observation_id')
check('MM selected observations sufficient', mmc.observation_id.nunique() >= 3000, f'obs={mmc.observation_id.nunique()}')
check('MM exactly one positive per group', g.pos.sum().eq(1).all())
check('MM at least one negative per group', g.pos.apply(lambda x: (~x).sum()).ge(1).all())
truth = mm_labels.set_index('observation_id').true_segment_id.astype(str)
pos = mmc[mmc.pos]
check('MM positive candidate equals true segment', (pos.candidate_segment_id.astype(str).values == pos.observation_id.map(truth).astype(str).values).all())
neg = mmc[~mmc.pos]
check('MM negative candidate differs from truth', (neg.candidate_segment_id.astype(str).values != neg.observation_id.map(truth).astype(str).values).all())
check('MM hard-negative definition', (~mmc.hard | ((~mmc.pos) & (mmc.distance_to_segment_m <= 20.0001) & (mmc.heading_difference_deg <= 45.0001))).all(), f'hard={int(mmc.hard.sum())}')
mm_split = mmc[['observation_id', 'trip_id', 'split']].drop_duplicates().merge(splits, on='trip_id', suffixes=('_mm', '_trip'))
check('MM split follows trip split', mm_split.eval('split_mm == split_trip').all())
check('MM all split partitions present', set(mm_split.split_mm) == {'train', 'validation', 'test'}, mm_split.split_mm.value_counts().to_dict())

# -----------------------------------------------------------------------------
# 6. Ranking/recommendation pipeline: Candidate Search -> eligible -> top-N -> rank.
# -----------------------------------------------------------------------------
required_rank = {
    'driver_to_station_distance_m', 'driver_to_station_eta_min', 'station_to_destination_distance_m', 'station_to_destination_eta_min',
    'direct_driver_to_destination_distance_m', 'direct_driver_to_destination_eta_min', 'detour_distance_m', 'detour_time_min',
    'traffic_adjusted_eta_min', 'queue_wait_min', 'service_time_min', 'available_capacity', 'operating_status', 'soc_feasible',
    'service_type', 'eligible_candidate_count', 'ranking_group_size', 'is_ltr_group', 'candidate_eligible'
}
check('Ranking required feature columns', required_rank <= set(rank.columns), sorted(required_rank - set(rank.columns)))
service_events = demand[bs(demand.need_service)].copy()
elig_counts = cand[cand.event_id.isin(service_events.event_id)].groupby('event_id').eligible.apply(lambda x: int(bs(x).sum()))
elig_counts = service_events.set_index('event_id').index.to_series().map(elig_counts).fillna(0).astype(int)
rank_groups = rank.groupby('event_id').size()
rec_idx = rec.set_index('event_id')
check('Recommendation event coverage = all service events', set(rec.event_id) == set(service_events.event_id), f'rec={len(rec)}, service_events={len(service_events)}')
check('No recommendation labels for NONE events', not set(rec.event_id) & set(demand.loc[demand.service_type.eq('NONE'), 'event_id']))

iff_ok = True; ref_eligible_ok = True; one_ok = True
for eid, cnt in elig_counts.items():
    rr = rec_idx.loc[eid]
    has = bool(rr.has_recommendation)
    if (cnt > 0) != has: iff_ok = False
    if cnt == 0:
        if pd.notna(rr.reference_station_id) and str(rr.reference_station_id).strip() not in ['', 'nan']: ref_eligible_ok = False
    else:
        refs = cand[(cand.event_id.eq(eid)) & (cand.station_id.eq(str(rr.reference_station_id)))]
        if refs.empty or not bool(bs(refs.eligible).iloc[0]): ref_eligible_ok = False
        if cnt == 1:
            only = cand[(cand.event_id.eq(eid)) & bs(cand.eligible)].iloc[0].station_id
            if str(rr.reference_station_id) != str(only): one_ok = False
check('Recommendation exists iff eligible candidate exists', iff_ok, f'eligible_events={(elig_counts>0).sum()}, no_eligible={(elig_counts==0).sum()}')
check('Recommended/reference station is ELIGIBLE', ref_eligible_ok)
check('Exactly-one-eligible event returns that station', one_ok, f'events={(elig_counts==1).sum()}')
check('Ranking groups exist iff eligible count > 0', set(rank.event_id) == set(elig_counts[elig_counts > 0].index), f'rank_groups={rank.event_id.nunique()}')

# Every ranking candidate must be eligible and ranking pool must equal nearest top-N eligible set.
rj = rank.merge(cand[['event_id', 'station_id', 'eligible', 'network_distance_m', 'estimated_wait_min', 'service_time_min', 'available_capacity']].rename(columns={'service_time_min': 'candidate_service_time_min', 'available_capacity': 'candidate_available_capacity', 'estimated_wait_min': 'candidate_wait_min'}), on=['event_id', 'station_id'], how='left')
check('Ranking candidates are ELIGIBLE', bs(rj.eligible).all())
check('Ranking candidate_eligible flag true', bs(rank.candidate_eligible).all())
nearest_ok = True; group_count_ok = True
for eid, cnt in elig_counts[elig_counts > 0].items():
    expected = cand[(cand.event_id.eq(eid)) & bs(cand.eligible)].sort_values(['network_distance_m', 'station_id']).head(MAX_RANK_CANDIDATES).station_id.tolist()
    actual = rank[rank.event_id.eq(eid)].sort_values(['driver_to_station_distance_m', 'station_id']).station_id.tolist()
    if set(expected) != set(actual): nearest_ok = False
    if len(actual) != min(int(cnt), MAX_RANK_CANDIDATES): group_count_ok = False
check('Ranking consumes nearest top-N eligible candidates only', nearest_ok)
check('Ranking variable group size matches eligible count capped at 8', group_count_ok, rank_groups.value_counts().sort_index().to_dict())
check('Ranking group size range 1..8', rank_groups.between(1, MAX_RANK_CANDIDATES).all(), rank_groups.value_counts().sort_index().to_dict())
check('LTR flag only for groups >=2', all(bs(g.is_ltr_group).eq(len(g) >= 2).all() for _, g in rank.groupby('event_id')))
check('Single-candidate groups retained', int((rank_groups == 1).sum()) == int((elig_counts == 1).sum()), f'rank_single={(rank_groups==1).sum()}, eligible_single={(elig_counts==1).sum()}')

calc_det_d = np.maximum(0, rank.driver_to_station_distance_m + rank.station_to_destination_distance_m - rank.direct_driver_to_destination_distance_m)
calc_det_t = np.maximum(0, rank.driver_to_station_eta_min + rank.station_to_destination_eta_min - rank.direct_driver_to_destination_eta_min)
check('Ranking detour distance consistency', np.allclose(calc_det_d, rank.detour_distance_m, atol=0.2))
check('Ranking detour time consistency', np.allclose(calc_det_t, rank.detour_time_min, atol=0.003))
calc_traf = rank.driver_to_station_eta_min * rank.traffic_delay_factor_driver_leg + rank.station_to_destination_eta_min * rank.traffic_delay_factor_station_leg
check('Ranking traffic-adjusted ETA consistency', np.allclose(calc_traf, rank.traffic_adjusted_eta_min, atol=0.01))
check('Ranking total ETA consistency', np.allclose(rank.traffic_adjusted_eta_min + rank.queue_wait_min + rank.service_time_min, rank.total_eta_min, atol=0.011))
cost = rank.traffic_adjusted_eta_min + rank.queue_wait_min + rank.service_time_min + 0.25 * rank.detour_time_min + 0.002 * rank.detour_distance_m - 0.35 * np.minimum(rank.available_capacity, 6)
check('Ranking baseline cost v3 recomputation', np.allclose(cost, rank.ranking_cost_label, atol=0.02), f'max_abs_err={float(np.max(np.abs(cost-rank.ranking_cost_label))):.4f}')
check('Ranking service time matches Candidate Search', np.allclose(rj.service_time_min, rj.candidate_service_time_min, atol=0.011))
check('Ranking queue wait matches Candidate Search', np.allclose(rj.queue_wait_min, rj.candidate_wait_min, atol=0.011))
check('Ranking capacity matches Candidate Search', (rj.available_capacity.astype(int) == rj.candidate_available_capacity.astype(int)).all())
check('CHARGING ranking uses charging service time', np.isclose(rank.loc[rank.service_type.eq('CHARGING'), 'service_time_min'], CHARGING_SERVICE_TIME_MIN).all())
check('BATTERY_SWAP ranking uses swap service time', np.isclose(rank.loc[rank.service_type.eq('BATTERY_SWAP'), 'service_time_min'], SWAP_SERVICE_TIME_MIN).all())
rank_order_ok = all(g.sort_values(['ranking_cost_label', 'station_id']).reference_rank.tolist() == list(range(1, len(g) + 1)) for _, g in rank.groupby('event_id'))
check('Ranking reference rank ordering', rank_order_ok)
check('Ranking exactly one best per group', rank.groupby('event_id').is_reference_best.apply(lambda x: bs(x).sum()).eq(1).all())
rank_split = rank[['event_id', 'trip_id', 'split']].drop_duplicates().merge(splits, on='trip_id', suffixes=('_rank', '_trip'))
check('Ranking split follows trip split', rank_split.eval('split_rank == split_trip').all())
check('Ranking all split partitions present', set(rank_split.split_rank) == {'train', 'validation', 'test'}, rank_split.split_rank.value_counts().to_dict())
check('Recommendation labels evaluation-only', not ({'reference_station_id', 'has_recommendation', 'recommended_station_id'} & set(df.columns)) and not ({'reference_station_id', 'has_recommendation', 'recommended_station_id'} & set(cand.columns)))
# Explicit audit cases supplied by reviewer.
for eid in ['DE000147', 'DE000148', 'DE000149', 'DE000150', 'DE000824']:
    ec = cand[(cand.event_id.eq(eid)) & bs(cand.eligible)]
    rg = rank[rank.event_id.eq(eid)]
    ok = len(ec) > 0 and set(rg.station_id) <= set(ec.station_id) and str(rec_idx.loc[eid].reference_station_id) in set(ec.station_id)
    check(f'Audit event eligible station retained in ranking/recommendation: {eid}', ok, f"eligible={ec.station_id.tolist()}, ranking={rg.station_id.tolist()}, ref={rec_idx.loc[eid].reference_station_id}")

# -----------------------------------------------------------------------------
# 7. Realtime service-specific state coverage.
# -----------------------------------------------------------------------------
replay_types = set(replay.event_type)
check('Realtime includes service-specific QUEUE_UPDATE events', 'QUEUE_UPDATE' in replay_types)
status_keys = set(zip(ss.station_id.astype(str), ss.timestamp.astype(str)))
queue_keys = set(zip(q.station_id.astype(str), q.timestamp.astype(str)))
replay_status_keys = set(zip(replay.loc[replay.event_type.eq('STATION_STATUS_UPDATE'), 'entity_id'].astype(str), replay.loc[replay.event_type.eq('STATION_STATUS_UPDATE'), 'timestamp'].astype(str)))
replay_queue_keys = set(zip(replay.loc[replay.event_type.eq('QUEUE_UPDATE'), 'entity_id'].astype(str), replay.loc[replay.event_type.eq('QUEUE_UPDATE'), 'timestamp'].astype(str)))
check('Realtime covers every station state', status_keys <= replay_status_keys, f'states={len(status_keys)}, replay={len(replay_status_keys)}')
check('Realtime covers every queue state', queue_keys <= replay_queue_keys, f'queues={len(queue_keys)}, replay={len(replay_queue_keys)}')
# Validate payload schema for a representative sample and the scenario-transition rows.
payload_ok = True
for r in replay[replay.event_type.eq('STATION_STATUS_UPDATE')].iloc[::max(1, len(ss)//100)].itertuples(index=False):
    p = json.loads(r.payload_json)
    req = {'status', 'available_charging_slots', 'occupied_charging_slots', 'available_swap_slots', 'occupied_swap_slots', 'available_swap_batteries', 'charging_service_time_min', 'swap_service_time_min'}
    payload_ok &= req <= set(p)
for r in replay[replay.event_type.eq('QUEUE_UPDATE')].iloc[::max(1, len(q)//100)].itertuples(index=False):
    p = json.loads(r.payload_json)
    req = {'charging_queue_length', 'charging_active_service_count', 'charging_estimated_wait_min', 'swap_queue_length', 'swap_active_service_count', 'swap_estimated_wait_min'}
    payload_ok &= req <= set(p)
check('Realtime service-specific payload schema', payload_ok)

# -----------------------------------------------------------------------------
# 8. Independent scenario assertions.
# -----------------------------------------------------------------------------
scx = sc.set_index('scenario_id')
trip_meta = trips.set_index('trip_id')
veh_meta = vehicles.set_index('vehicle_id')

# BRIDGE_AMBIGUITY: trajectory touches bridge and MM selected candidates contain negatives.
r = scx.loc['BRIDGE_AMBIGUITY']; tid = r.example_trip_id
bridge_sids = set(segs.loc[segs.bridge.astype(str).str.lower().isin(['yes', 'true', '1']), 'segment_id'])
touch_bridge = true.loc[true.trip_id.eq(tid), 'true_segment_id'].isin(bridge_sids).any()
mmg = mmc[mmc.trip_id.eq(tid)]
scenario_check('BRIDGE_AMBIGUITY', touch_bridge and ((~bs(mmg.is_correct)).sum() >= 1), f'bridge={touch_bridge}, negatives={int((~bs(mmg.is_correct)).sum())}')

# FARTHER_BUT_FASTER: both stations must be eligible, farther by >=500m, total ETA better by >=10m.
r = scx.loc['FARTHER_BUT_FASTER']; rr = rank[rank.event_id.eq(r.example_event_id)].set_index('station_id')
try:
    a, b = rr.loc[str(r.evidence_entity_a)], rr.loc[str(r.evidence_entity_b)]
    dd = float(b.driver_to_station_distance_m) - float(a.driver_to_station_distance_m)
    gain = float(a.total_eta_min) - float(b.total_eta_min)
    ec = cand[(cand.event_id.eq(r.example_event_id)) & cand.station_id.isin([str(r.evidence_entity_a), str(r.evidence_entity_b)])]
    ok = dd >= FARTHER_MIN_DISTANCE_DELTA_M and gain >= FARTHER_MEANINGFUL_ETA_MARGIN_MIN and bs(ec.eligible).all()
except Exception:
    dd = gain = float('nan'); ok = False
scenario_check('FARTHER_BUT_FASTER', ok, f'distance_delta_m={dd:.1f}, eta_improvement_min={gain:.3f}', {'distance_delta_m': dd, 'eta_improvement_min': gain, 'threshold_min': FARTHER_MEANINGFUL_ETA_MARGIN_MIN})
check('FARTHER_BUT_FASTER meaningful ETA difference', ok, f'distance_delta_m={dd:.1f}, eta_gain_min={gain:.3f}')

# GPS_MISSING.
r = scx.loc['GPS_MISSING']; tid = r.example_trip_id; ratio = len(gps[gps.trip_id.eq(tid)]) / len(true[true.trip_id.eq(tid)])
scenario_check('GPS_MISSING', ratio < 0.85, f'ratio={ratio:.4f}', {'gps_to_true_ratio': ratio})

# GPS_NOISE: median observation-to-truth error >=10m.
r = scx.loc['GPS_NOISE']; tid = r.example_trip_id
j = gps[gps.trip_id.eq(tid)][['observation_id', 'latitude', 'longitude']].merge(mm_labels[['observation_id', 'true_latitude', 'true_longitude']], on='observation_id')
errs = [hav_m(a, b, c, d) for a, b, c, d in zip(j.latitude, j.longitude, j.true_latitude, j.true_longitude)]
med_err = float(np.median(errs)) if errs else 0.0
scenario_check('GPS_NOISE', med_err >= 10.0, f'median_error_m={med_err:.2f}', {'median_error_m': med_err})

# HEAVY_TRAFFIC.
r = scx.loc['HEAVY_TRAFFIC']; tr = traf[(traf.segment_id.eq(r.evidence_entity_a)) & (traf.timestamp.eq(r.evidence_timestamp))]
ok = len(tr) > 0 and tr.iloc[0].traffic_level in ['HEAVY', 'INCIDENT'] and float(tr.iloc[0].delay_factor) > 1.5
scenario_check('HEAVY_TRAFFIC', ok, tr.iloc[0].to_dict() if len(tr) else 'missing')

# INCOMPATIBLE_STATION.
r = scx.loc['INCOMPATIBLE_STATION']; cc = cand[cand.event_id.eq(r.example_event_id)]
scenario_check('INCOMPATIBLE_STATION', (cc.reason.eq('INCOMPATIBLE')).any() and bs(cc.eligible).any(), f"incompatible={(cc.reason=='INCOMPATIBLE').sum()}, eligible={int(bs(cc.eligible).sum())}")

# INSUFFICIENT_RANGE.
r = scx.loc['INSUFFICIENT_RANGE']; cc = cand[cand.event_id.eq(r.example_event_id)]
scenario_check('INSUFFICIENT_RANGE', (cc.reason.eq('INSUFFICIENT_SOC_TO_REACH')).any(), f"count={(cc.reason=='INSUFFICIENT_SOC_TO_REACH').sum()}")

# LONG_QUEUE uses requested service-specific queue wait.
r = scx.loc['LONG_QUEUE']; cr = cand[(cand.event_id.eq(r.example_event_id)) & cand.station_id.eq(r.evidence_entity_a)]
ok = len(cr) > 0 and float(cr.iloc[0].estimated_wait_min) >= 30.0
scenario_check('LONG_QUEUE', ok, cr.iloc[0][['service_type', 'queue_length', 'estimated_wait_min', 'service_time_min']].to_dict() if len(cr) else 'missing')

# LOW_SOC.
r = scx.loc['LOW_SOC']; feat = df[df.event_id.eq(r.example_event_id)].iloc[0]; tid = demand[demand.event_id.eq(r.example_event_id)].iloc[0].trip_id; v = veh_meta.loc[trip_meta.loc[tid].vehicle_id]
scenario_check('LOW_SOC', float(feat.soc_pct) <= float(v.minimum_safe_soc_pct), f'soc={feat.soc_pct}, safe={v.minimum_safe_soc_pct}')

# NEAREST_FULL.
r = scx.loc['NEAREST_FULL']; cr = cand[(cand.event_id.eq(r.example_event_id)) & cand.station_id.eq(r.evidence_entity_a)]
ok = len(cr) > 0 and cr.iloc[0].reason == 'FULL' and int(cr.iloc[0].available_capacity) == 0
scenario_check('NEAREST_FULL', ok, cr.iloc[0][['reason', 'available_capacity', 'service_type']].to_dict() if len(cr) else 'missing')

# NEAR_TIE_STATIONS.
r = scx.loc['NEAR_TIE_STATIONS']; rr = rank[rank.event_id.eq(r.example_event_id)].sort_values('ranking_cost_label')
if len(rr) >= 2:
    tie_diff = float(rr.iloc[1].ranking_cost_label - rr.iloc[0].ranking_cost_label)
else:
    tie_diff = float('inf')
scenario_check('NEAR_TIE_STATIONS', tie_diff <= NEAR_TIE_THRESHOLD_MIN, f'diff_min={tie_diff:.4f}', {'top2_cost_diff_min': tie_diff})

# NEED_CHARGING.
r = scx.loc['NEED_CHARGING']; dtrip = demand[demand.trip_id.eq(r.example_trip_id)]; vid = trip_meta.loc[r.example_trip_id].vehicle_id
scenario_check('NEED_CHARGING', (dtrip.service_type.eq('CHARGING')).any() and bool(veh_meta.loc[vid].charging_supported), f"charging_labels={(dtrip.service_type=='CHARGING').sum()}")

# NEED_SWAP.
r = scx.loc['NEED_SWAP']; dtrip = demand[demand.trip_id.eq(r.example_trip_id)]; vid = trip_meta.loc[r.example_trip_id].vehicle_id
scenario_check('NEED_SWAP', dtrip.service_type.eq('BATTERY_SWAP').all() and bool(veh_meta.loc[vid].swap_supported), f'labels={dtrip.service_type.value_counts().to_dict()}, swap_supported={veh_meta.loc[vid].swap_supported}')

# NORMAL_TRIP and NO_SERVICE_NEEDED.
for name in ['NORMAL_TRIP', 'NO_SERVICE_NEEDED']:
    r = scx.loc[name]; dtrip = demand[demand.trip_id.eq(r.example_trip_id)]
    scenario_check(name, dtrip.service_type.eq('NONE').all(), dtrip.service_type.value_counts().to_dict())

# NO_AVAILABLE_STATION.
r = scx.loc['NO_AVAILABLE_STATION']; cc = cand[cand.event_id.eq(r.example_event_id)]
scenario_check('NO_AVAILABLE_STATION', int(bs(cc.eligible).sum()) == 0, f'eligible={int(bs(cc.eligible).sum())}')

# PARALLEL_ROADS.
r = scx.loc['PARALLEL_ROADS']; mmg = mmc[(mmc.trip_id.eq(r.example_trip_id)) & bs(mmc.hard_negative)]
scenario_check('PARALLEL_ROADS', len(mmg) > 0, f'hard_negatives={len(mmg)}')

# STATION_OFFLINE.
r = scx.loc['STATION_OFFLINE']; cr = cand[(cand.event_id.eq(r.example_event_id)) & cand.station_id.eq(r.evidence_entity_a)]
scenario_check('STATION_OFFLINE', len(cr) > 0 and cr.iloc[0].reason == 'OFFLINE' and cr.iloc[0].operating_status != 'OPEN', cr.iloc[0][['reason', 'operating_status']].to_dict() if len(cr) else 'missing')

# Realtime queue/status/traffic transitions.
replay_key = set(zip(replay.event_type.astype(str), replay.entity_id.astype(str), replay.timestamp.astype(str)))
# queue
r = scx.loc['QUEUE_REALTIME_CHANGE']; sid = str(r.evidence_entity_a); before = str(r.before_timestamp); after = str(r.after_timestamp); service = demand[demand.event_id.eq(r.example_event_id)].iloc[0].service_type
qa = q[(q.station_id.eq(sid)) & q.timestamp.eq(before)]; qb = q[(q.station_id.eq(sid)) & q.timestamp.eq(after)]
if len(qa) and len(qb):
    if service == 'CHARGING': w0, w1 = float(qa.iloc[0].charging_estimated_wait_min), float(qb.iloc[0].charging_estimated_wait_min)
    else: w0, w1 = float(qa.iloc[0].swap_estimated_wait_min), float(qb.iloc[0].swap_estimated_wait_min)
    qok = abs(w1 - w0) >= 20 and ('QUEUE_UPDATE', sid, before) in replay_key and ('QUEUE_UPDATE', sid, after) in replay_key
else:
    w0 = w1 = float('nan'); qok = False
scenario_check('QUEUE_REALTIME_CHANGE', qok, f'{service} wait {w0}->{w1}')
# status
r = scx.loc['STATION_STATUS_CHANGE']; sid = str(r.evidence_entity_a); before = str(r.before_timestamp); after = str(r.after_timestamp)
sa = ss[(ss.station_id.eq(sid)) & ss.timestamp.eq(before)]; sb = ss[(ss.station_id.eq(sid)) & ss.timestamp.eq(after)]
sok = len(sa) and len(sb) and sa.iloc[0].operating_status != sb.iloc[0].operating_status and ('STATION_STATUS_UPDATE', sid, before) in replay_key and ('STATION_STATUS_UPDATE', sid, after) in replay_key
scenario_check('STATION_STATUS_CHANGE', sok, f"{sa.iloc[0].operating_status if len(sa) else '?'}->{sb.iloc[0].operating_status if len(sb) else '?'}")
# traffic
r = scx.loc['TRAFFIC_REALTIME_CHANGE']; sid = str(r.evidence_entity_a); before = str(r.before_timestamp); after = str(r.after_timestamp)
ta = traf[(traf.segment_id.eq(sid)) & traf.timestamp.eq(before)]; tb = traf[(traf.segment_id.eq(sid)) & traf.timestamp.eq(after)]
tok = len(ta) and len(tb) and (ta.iloc[0].traffic_level != tb.iloc[0].traffic_level or float(ta.iloc[0].current_speed_kmh) != float(tb.iloc[0].current_speed_kmh)) and ('TRAFFIC_UPDATE', sid, before) in replay_key and ('TRAFFIC_UPDATE', sid, after) in replay_key
scenario_check('TRAFFIC_REALTIME_CHANGE', tok, f"{ta.iloc[0].traffic_level if len(ta) else '?'}->{tb.iloc[0].traffic_level if len(tb) else '?'}")

check('Scenario set complete', set(x['scenario_id'] for x in scenario_results) == set(trips.scenario_id), f'results={len(scenario_results)}')
check('All independent scenario assertions PASS', all(x['status'] == 'PASS' for x in scenario_results), {x['scenario_id']: x['status'] for x in scenario_results})
# Sync scenario_coverage validator status from independent assertions.
status_map = {x['scenario_id']: x['status'] for x in scenario_results}
sc['validator_status'] = sc.scenario_id.map(status_map).fillna('FAIL')
sc.to_csv(ROOT / 'scenarios/scenario_coverage.csv', index=False)

# -----------------------------------------------------------------------------
# 9. Raw-map integrity + explicit human confirmation warning.
# -----------------------------------------------------------------------------
base = ROOT / 'map/raw/hanoi-baseline.osm.pbf'; patch = ROOT / 'map/raw/hanoi-patched.osm.pbf'
check('Baseline PBF byte integrity', sha256(base) == EXPECTED_BASELINE_SHA256, sha256(base))
check('Patched PBF byte integrity', sha256(patch) == EXPECTED_PATCHED_SHA256, sha256(patch))
diff = pd.read_csv(ROOT / 'map/processed/pbf_diff.csv', dtype={'osm_way_id': str})
row = diff[diff.osm_way_id.eq('881947000')]
check('Cầu Thanh Trì diff explicitly preserved', len(row) == 1 and (not bool(row.iloc[0].geometry_changed)) and '"motorcar"=>"designated"' in str(row.iloc[0].baseline_other_tags) and '"motorcar"=>"no"' in str(row.iloc[0].patched_other_tags))
warn = json.load(open(ROOT / 'validation/pbf_integrity.json', encoding='utf-8')).get('warning', '')
check('Cầu Thanh Trì human-confirmation warning present', 'Human confirmation is required' in warn and '881947000' in warn)

# -----------------------------------------------------------------------------
# 10. Write independent validation outputs and current counts/stats.
# -----------------------------------------------------------------------------
summary = {
    'passed': sum(x['status'] == 'PASS' for x in res),
    'failed': sum(x['status'] == 'FAIL' for x in res),
    'overall': 'PASS' if all(x['status'] == 'PASS' for x in res) else 'FAIL',
    'results': res
}
json.dump(summary, open(ROOT / 'validation/validation_results.json', 'w'), indent=2, ensure_ascii=False)
pd.DataFrame(res).to_csv(ROOT / 'validation/validation_results.csv', index=False)

sc_summary = {
    'overall': 'PASS' if all(x['status'] == 'PASS' for x in scenario_results) else 'FAIL',
    'passed': sum(x['status'] == 'PASS' for x in scenario_results),
    'failed': sum(x['status'] == 'FAIL' for x in scenario_results),
    'results': scenario_results
}
json.dump(sc_summary, open(ROOT / 'validation/scenario_validation_results.json', 'w'), indent=2, ensure_ascii=False)

group_sizes = rank.groupby('event_id').size()
rank_stats = {
    'rows': int(len(rank)),
    'event_groups': int(rank.event_id.nunique()),
    'group_size_min': int(group_sizes.min()) if len(group_sizes) else 0,
    'group_size_max': int(group_sizes.max()) if len(group_sizes) else 0,
    'group_size_distribution': {str(int(k)): int(v) for k, v in group_sizes.value_counts().sort_index().items()},
    'ltr_event_groups': int(rank.loc[bs(rank.is_ltr_group), 'event_id'].nunique()),
    'single_candidate_groups': int((group_sizes == 1).sum()),
    'split_groups': rank.drop_duplicates('event_id').split.value_counts().to_dict(),
    'service_event_count': int(len(service_events)),
    'events_with_eligible_station': int((elig_counts > 0).sum()),
    'events_with_no_eligible_station': int((elig_counts == 0).sum()),
    'events_with_exactly_one_eligible_station': int((elig_counts == 1).sum()),
    'events_with_two_or_more_eligible_stations': int((elig_counts >= 2).sum()),
    'recommendation_event_count': int(len(rec)),
    'has_recommendation_true': int(bs(rec.has_recommendation).sum()),
    'has_recommendation_false': int((~bs(rec.has_recommendation)).sum()),
    'pipeline': 'all stations -> Candidate Search -> eligible=true -> nearest top-N eligible (max 8) -> Ranking'
}
json.dump(rank_stats, open(ROOT / 'validation/ranking_stats.json', 'w'), indent=2)

mm_stats = json.load(open(ROOT / 'validation/map_matching_candidate_stats.json'))
counts = {
    'road_nodes': len(nodes), 'road_segments': len(segs), 'drivers': len(drivers), 'vehicles': len(vehicles), 'trips': len(trips),
    'true_trajectory_points': len(true), 'gps_observations': len(gps), 'soc_history': len(bat), 'stations': len(st),
    'station_status': len(ss), 'queue_status': len(q), 'traffic_snapshots': len(traf), 'realtime_events': len(replay),
    'map_matching_candidates': len(mmc), 'map_matching_selected_observations': int(mmc.observation_id.nunique()),
    'demand_labels': len(demand), 'candidate_labels': len(cand), 'ranking_reference': len(rank),
    'ranking_event_groups': int(rank.event_id.nunique()), 'recommendation_labels': len(rec), 'scenario_rows': len(sc)
}
json.dump(counts, open(ROOT / 'validation/data_counts.json', 'w'), indent=2)

print(json.dumps({'passed': summary['passed'], 'failed': summary['failed'], 'overall': summary['overall'], 'scenario_passed': sc_summary['passed'], 'scenario_failed': sc_summary['failed'], 'ranking_stats': rank_stats}, indent=2))
if summary['failed'] or sc_summary['failed']:
    print(pd.DataFrame([x for x in res if x['status'] == 'FAIL']).to_string(index=False))
    print(json.dumps([x for x in scenario_results if x['status'] == 'FAIL'], indent=2))
    raise SystemExit(1)
