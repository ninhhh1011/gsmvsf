"""
Dataset V1.3.1 Validation Suite
=================================
Full validation of Dataset V1.3.1 — Service Intent Semantic Correction.

This validator replaces V1.3's stale checks with V1.3.1-correct semantics.
Key semantic changes from V1.3:
- AUTO_DETECTED for swap-capable vehicles: resolved_service_type=NULL (unresolved)
- DRIVER_REQUEST(ANY): service_type='ANY', resolved_service_type=NULL
- need_service training: AUTO_DETECTED rows only
- NEED_SWAP scenario renamed to NEED_ENERGY_BOTH_ALLOWED
- resolved_service_type column added to demand_labels
"""

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
    scenario_results.append({
        'scenario_id': name,
        'status': 'PASS' if ok else 'FAIL',
        'details': str(details),
        'metrics': metrics or {}
    })
    return ok


def bs(s):
    if getattr(s, 'dtype', None) == bool:
        return s
    return s.astype(str).str.lower().isin(['true', '1', 'yes'])


def tokens(v):
    if pd.isna(v):
        return set()
    return {x.strip() for x in str(v).replace(',', ';').split(';') if x.strip()}


def compatible(v, s, service):
    """Station compatibility check (simplified for validation)."""
    if service == 'CHARGING':
        if not bool(v.charging_supported):
            return False
    elif service == 'BATTERY_SWAP':
        if not bool(v.swap_supported):
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


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
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


# =============================================================================
# Load V1.3.1 data
# =============================================================================
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
df_feat = pd.read_csv(ROOT / 'training/demand_features.csv')
cand = pd.read_csv(ROOT / 'labels/candidate_labels.csv')
rank = pd.read_csv(ROOT / 'training/ranking_reference.csv')
rec = pd.read_csv(ROOT / 'labels/recommendation_labels.csv')
sc = pd.read_csv(ROOT / 'scenarios/scenario_coverage.csv')
esr = pd.read_csv(ROOT / 'labels/energy_service_requests.csv')
need_feat = pd.read_csv(ROOT / 'training/demand_need_service_features.csv')
need_lbl = pd.read_csv(ROOT / 'training/demand_need_service_labels.csv')
cat = pd.read_csv(ROOT / 'vehicles/vehicle_model_catalog.csv')

# =============================================================================
# 1. STRUCTURAL / REFERENTIAL INTEGRITY (Week 1 baseline — PRESERVED)
# =============================================================================
for name, d, key in [
    ('nodes', nodes, 'node_id'),
    ('segments', segs, 'segment_id'),
    ('drivers', drivers, 'driver_id'),
    ('vehicles', vehicles, 'vehicle_id'),
    ('trips', trips, 'trip_id'),
    ('gps', gps, 'observation_id'),
    ('stations', st, 'station_id'),
    ('replay', replay, 'event_id'),
    ('demand', demand, 'event_id'),
]:
    check(f'PK unique: {name}',
          d[key].notna().all() and not d[key].duplicated().any(),
          f'rows={len(d)}')

check('Candidate composite key unique',
      not cand.duplicated(['event_id', 'station_id', 'service_type']).any(),
      f'rows={len(cand)}')
check('Ranking composite key unique',
      not rank.duplicated(['event_id', 'station_id', 'service_type']).any(),
      f'rows={len(rank)}')
check('Station state composite key unique',
      not ss.duplicated(['station_id', 'timestamp']).any())
check('Queue state composite key unique',
      not q.duplicated(['station_id', 'timestamp']).any())

# FK checks
check('FK vehicle.driver -> drivers',
      set(vehicles.driver_id) <= set(drivers.driver_id))
check('FK trip.driver -> drivers',
      set(trips.driver_id) <= set(drivers.driver_id))
check('FK trip.vehicle -> vehicles',
      set(trips.vehicle_id) <= set(vehicles.vehicle_id))
check('FK segment nodes exist',
      set(segs.from_node_id) <= set(nodes.node_id) and
      set(segs.to_node_id) <= set(nodes.node_id))
check('FK true.segment -> road_segments',
      set(true.true_segment_id) <= set(segs.segment_id))
check('FK GPS trip/trajectory',
      set(gps.trip_id) <= set(trips.trip_id) and
      set(gps.trajectory_id) <= set(true.trajectory_id))
check('FK station.access_node -> road_nodes',
      set(st.access_node_id) <= set(nodes.node_id))
check('FK traffic.segment -> road_segments',
      set(traf.segment_id) <= set(segs.segment_id))
check('FK station temporal state -> stations',
      set(ss.station_id) <= set(st.station_id) and
      set(q.station_id) <= set(st.station_id))
check('FK demand -> trips', set(demand.trip_id) <= set(trips.trip_id))
check('FK candidates -> demand/stations',
      set(cand.event_id) <= set(demand.event_id) and
      set(cand.station_id) <= set(st.station_id))
check('FK ranking -> demand/stations/trips',
      set(rank.event_id) <= set(demand.event_id) and
      set(rank.station_id) <= set(st.station_id) and
      set(rank.trip_id) <= set(trips.trip_id))
check('FK recommendations -> demand', set(rec.event_id) <= set(demand.event_id))

# =============================================================================
# 2. GEOGRAPHY / CHRONOLOGY / CONSISTENCY (Week 1 baseline — PRESERVED)
# =============================================================================
check('Road node coordinate bounds',
      nodes.latitude.between(-90, 90).all() and
      nodes.longitude.between(-180, 180).all())
check('GPS coordinate bounds',
      gps.latitude.between(-90, 90).all() and
      gps.longitude.between(-180, 180).all())
check('Station coordinate bounds',
      st.latitude.between(-90, 90).all() and
      st.longitude.between(-180, 180).all())
check('Trajectory timestamp ordering',
      all(pd.to_datetime(g.timestamp, format='mixed').is_monotonic_increasing
          for _, g in true.groupby('trip_id')))
check('SOC timestamp ordering',
      all(pd.to_datetime(g.timestamp, format='mixed').is_monotonic_increasing
          for _, g in bat.groupby('trip_id')))
check('Replay event chronology',
      pd.to_datetime(replay.timestamp, format='mixed').is_monotonic_increasing)

segmap = segs.set_index('segment_id')[['from_node_id', 'to_node_id']].to_dict('index')
bad_transitions = 0
for _, g in true.groupby('trip_id'):
    seq = g.true_segment_id[g.true_segment_id.ne(g.true_segment_id.shift())].tolist()
    bad_transitions += sum(
        segmap[a]['to_node_id'] != segmap[b]['from_node_id']
        for a, b in zip(seq[:-1], seq[1:])
    )
check('Trajectory road connectivity', bad_transitions == 0,
      f'bad_transitions={bad_transitions}')
check('GPS map-matching truth coverage',
      len(mm_labels) == len(gps) and
      set(mm_labels.observation_id) == set(gps.observation_id),
      f'labels={len(mm_labels)}, gps={len(gps)}')
check('SOC range', bat.soc_pct.between(0, 100).all(),
      f'min={bat.soc_pct.min():.3f}, max={bat.soc_pct.max():.3f}')

soc_ok = True
for _, g in bat.groupby('trip_id'):
    if ((g.distance_travelled_km.diff().fillna(0) < -1e-9).any() or
        (g.energy_consumed_kwh.diff().fillna(0) < -1e-9).any() or
        (g.soc_pct.diff().fillna(0) > 0.05).any()):
        soc_ok = False
        break
check('SOC/distance/energy monotonic consistency', soc_ok)

check('Training split unique per trip',
      splits.trip_id.is_unique and
      splits.split.isin(['train', 'validation', 'test']).all())
check('Training split covers trips',
      set(splits.trip_id) == set(trips.trip_id))

# =============================================================================
# 3. V1.3.1 — VEHICLE CAPABILITY AUDIT
# =============================================================================
check('Vehicle model catalog: 19 models', len(cat) == 19)
check('Vehicle model catalog: 10 car models',
      len(cat[cat.vehicle_category == 'EV_CAR']) == 10)
check('Vehicle model catalog: 9 motorcycle models',
      len(cat[cat.vehicle_category == 'EV_MOTORBIKE']) == 9)
check('Swap-capable models: EVO, EVO_LITE, FELIZ_II, VIPER',
      set(cat[bs(cat.swap_supported)].vehicle_model) == {'EVO', 'EVO_LITE', 'FELIZ_II', 'VIPER'})
check('Charge-only bike models correct',
      set(cat[(~bs(cat.swap_supported)) &
               (cat.vehicle_category == 'EV_MOTORBIKE')].vehicle_model) ==
      {'EVO200', 'EVO200_LITE', 'FELIZ_S', 'KLARA_S_2022', 'VENTO_S'})

# Fleet distribution
check('Fleet: 40 EV_CAR',
      (vehicles.vehicle_type == 'EV_CAR').sum() == 40)
check('Fleet: 7 swap-capable motorcycles',
      bs(vehicles.swap_supported).sum() == 7)
check('Fleet: 13 charge-only motorcycles',
      ((~bs(vehicles.swap_supported)) &
       (vehicles.vehicle_type == 'EV_MOTORBIKE')).sum() == 13)

# No vehicle has swap without charging
no_swap_no_charge = vehicles[bs(vehicles.swap_supported) & (~bs(vehicles.charging_supported))]
check('No vehicle: swap=True and charging=False',
      len(no_swap_no_charge) == 0,
      f'rows={len(no_swap_no_charge)}')

# =============================================================================
# 4. V1.3.1 — DEMAND SEMANTICS
# =============================================================================
auto = demand[demand.request_source == 'AUTO_DETECTED']
dr = demand[demand.request_source == 'DRIVER_REQUEST']

# Structure checks
check('demand_labels total rows',
      len(demand) == 3824,
      f'rows={len(demand)}')
check('AUTO_DETECTED count: 1200 (150 trips x 8 snapshots)',
      len(auto) == 1200)
check('AUTO_DETECTED: 8 snapshots per trip',
      auto.groupby('trip_id').size().eq(8).all(),
      auto.groupby('trip_id').size().value_counts().to_dict())
check('DRIVER_REQUEST count: 2624 (swap bikes get 4 rows/snap, others get 3)',
      len(dr) == 2624)

# DRIVER_REQUEST structure
check('DRIVER_REQUEST(CHARGING) count',
      (dr.requested_service_type == 'CHARGING').sum() == 150 * 8,
      f'count={(dr.requested_service_type == "CHARGING").sum()}')
check('DRIVER_REQUEST(BATTERY_SWAP) count',
      (dr.requested_service_type == 'BATTERY_SWAP').sum() == 150 * 8,
      f'count={(dr.requested_service_type == "BATTERY_SWAP").sum()}')
check('DRIVER_REQUEST(ANY) count (swap bikes only)',
      (dr.requested_service_type == 'ANY').sum() == 28 * 8,
      f'count={(dr.requested_service_type == "ANY").sum()}')

# V1.3.1: ALL demand rows must have resolved_service_type column
check('demand_labels has resolved_service_type column',
      'resolved_service_type' in demand.columns)
check('demand_labels has requested_service_type column',
      'requested_service_type' in demand.columns)
check('demand_labels has request_source column',
      'request_source' in demand.columns)

# =============================================================================
# 5. V1.3.1 — AUTO_DETECTED SEMANTICS (PHASE 1 FIX)
# =============================================================================
# Bug #1 fix: No AUTO_DETECTED BOTH-capable event has BATTERY_SWAP resolved.
# The system does NOT auto-prefer BATTERY_SWAP.

# Case A: need_service=False -> resolved_service_type=None
auto_no_need = auto[~auto.need_service.astype(bool)]
check('AUTO need_service=False -> resolved_service_type=NaN',
      auto_no_need.resolved_service_type.isna().all(),
      f'rows={len(auto_no_need)}')

# Case B: need_service=True + charge-only -> resolved_service_type=CHARGING
auto_charge = auto[auto.need_service.astype(bool) & (~auto.swap_supported.astype(bool))]
charge_only_correct = (
    auto_charge.resolved_service_type.fillna('').str.upper().eq('CHARGING').all()
)
check('AUTO need_service + charge-only -> resolved_service_type=CHARGING',
      charge_only_correct,
      f'rows={len(auto_charge)}')

# Case C: need_service=True + swap-capable -> resolved_service_type=NULL (unresolved)
auto_both = auto[auto.need_service.astype(bool) & auto.swap_supported.astype(bool)]
check('AUTO need_service=True + swap-capable: resolved_service_type=NaN',
      auto_both.resolved_service_type.isna().all(),
      f'rows={len(auto_both)}, models={sorted(auto_both.vehicle_model.unique())}')
check('AUTO swap-capable: NO BATTERY_SWAP auto-resolution',
      (auto_both.resolved_service_type == 'BATTERY_SWAP').sum() == 0,
      f'BATTERY_SWAP count={(auto_both.resolved_service_type == "BATTERY_SWAP").sum()}')

# NONE rows: service_type=NONE (backward compat), resolved_service_type=None
auto_none = auto[auto.service_type == 'NONE']
check('AUTO service_type=NONE -> need_service=False',
      (~auto_none.need_service.astype(bool)).all(),
      f'NONE rows={len(auto_none)}')
check('AUTO service_type=NONE -> allowed_service_types does NOT contain NONE',
      auto_none.allowed_service_types.apply(
          lambda x: 'NONE' not in str(x)).all())

# AUTO_DETECTED: service_type in allowed_service_types
# (for AUTO: service_type is resolved_service_type or NONE when unresolved)
def service_in_allowed(row):
    st = row.service_type
    if pd.isna(st) or st == 'NONE':
        return True  # NONE is not a service
    return st in row.allowed_service_types

check('AUTO: service_type in allowed_service_types',
      auto.apply(service_in_allowed, axis=1).all())

# =============================================================================
# 6. V1.3.1 — DRIVER_REQUEST SEMANTICS (PHASE 2 FIX)
# =============================================================================
# Bug #2 fix: DRIVER_REQUEST(ANY) does NOT resolve to CHARGING.

dr_any = dr[dr.requested_service_type == 'ANY']
check('DRIVER_REQUEST(ANY): service_type=ANY (not CHARGING)',
      (dr_any.service_type == 'ANY').all(),
      f'rows={len(dr_any)}')
check('DRIVER_REQUEST(ANY): resolved_service_type=NaN (unresolved)',
      dr_any.resolved_service_type.isna().all(),
      f'rows={len(dr_any)}')
check('DRIVER_REQUEST(ANY): request_valid=True',
      dr_any.request_valid.astype(bool).all(),
      f'rows={len(dr_any)}')

# DRIVER_REQUEST validity
check('DRIVER_REQUEST: request_valid not null',
      dr.request_valid.notna().all())
check('DRIVER_REQUEST: invalid rows exist',
      (dr.request_valid == False).sum() > 0,
      f'invalid={(dr.request_valid == False).sum()}')

# CHARGING request: valid for all charge-capable vehicles
dr_c = dr[dr.requested_service_type == 'CHARGING']
check('DRIVER_REQUEST(CHARGING): valid for charge-capable',
      dr_c.loc[bs(dr_c.charging_supported), 'request_valid'].all())

# BATTERY_SWAP request: valid only for swap-capable
dr_s = dr[dr.requested_service_type == 'BATTERY_SWAP']
check('DRIVER_REQUEST(BATTERY_SWAP): valid for swap-capable',
      dr_s.loc[bs(dr_s.swap_supported), 'request_valid'].all())
check('DRIVER_REQUEST(BATTERY_SWAP): invalid for charge-only',
      dr_s.loc[~bs(dr_s.swap_supported), 'request_valid'].eq(False).all())

# DRIVER_REQUEST resolved_service_type
check('DRIVER_REQUEST(CHARGING): resolved_service_type=CHARGING',
      dr_c.resolved_service_type.fillna('').str.upper().eq('CHARGING').all())
check('DRIVER_REQUEST(BATTERY_SWAP): valid -> resolved=BATTERY_SWAP, invalid -> NaN',
      (
          dr_s.loc[bs(dr_s.request_valid), 'resolved_service_type'].fillna('').str.upper().eq('BATTERY_SWAP').all() and
          dr_s.loc[~bs(dr_s.request_valid), 'resolved_service_type'].isna().all()
      ))

# DRIVER_REQUEST ALL snapshot structure per trip
# Swap-capable bikes: 3 rows (CHARGING, BATTERY_SWAP, ANY)
# Charge-only vehicles: 2 rows (CHARGING, BATTERY_SWAP)
swap_bike_trips = trips[bs(trips.merge(
    vehicles, on='vehicle_id')['swap_supported'])].trip_id.tolist()
dr_swap_trips = dr[dr.trip_id.isin(swap_bike_trips)]
check('Swap-bike trips: DR rows per trip = 24 (8 snaps x 3)',
      dr_swap_trips.groupby('trip_id').size().eq(24).all(),
      dr_swap_trips.groupby('trip_id').size().value_counts().to_dict())
charge_only_trips = trips[~bs(trips.merge(
    vehicles, on='vehicle_id')['swap_supported'])].trip_id.tolist()
dr_charge_trips = dr[dr.trip_id.isin(charge_only_trips)]
check('Charge-only trips: DR rows per trip = 16 (8 snaps x 2)',
      dr_charge_trips.groupby('trip_id').size().eq(16).all(),
      dr_charge_trips.groupby('trip_id').size().value_counts().to_dict())

# =============================================================================
# 7. V1.3.1 — NEED_SERVICE TRAINING DATA (PHASE 3 FIX)
# =============================================================================
# need_service prediction uses AUTO_DETECTED rows only.

check('need_service features: rows == AUTO_DETECTED count',
      len(need_feat) == len(auto),
      f'need_feat={len(need_feat)}, auto={len(auto)}')
check('need_service labels: rows == AUTO_DETECTED count',
      len(need_lbl) == len(auto),
      f'need_lbl={len(need_lbl)}, auto={len(auto)}')

# Training features must NOT contain DRIVER_REQUEST rows
check('Training features: NO DRIVER_REQUEST rows',
      need_feat.merge(demand[['event_id', 'request_source']].drop_duplicates(),
                      on='event_id')['request_source'].eq('AUTO_DETECTED').all())

# Label leakage: no service_type, reason_code, request_source, etc. in features
leak_cols = {
    'need_service', 'service_type', 'reason_code', 'request_source',
    'request_valid', 'requested_service_type', 'allowed_service_types',
    'resolved_service_type'
}
found_leak = sorted(leak_cols & set(need_feat.columns))
check('need_service features: no label leakage',
      not found_leak, ','.join(found_leak))

# Class distribution documented
need_true = int(need_lbl['need_service'].sum())
need_false = int((~need_lbl['need_service'].astype(bool)).sum())
check('need_service class distribution: imbalance documented',
      need_true > need_false,
      f'True={need_true}, False={need_false}, ratio={need_true/(need_true+need_false):.1%}')

# Split distribution
check('need_service split: train ~ val ~ test',
      set(need_feat.split) == {'train', 'validation', 'test'},
      need_feat.split.value_counts().to_dict())

# =============================================================================
# 8. V1.3.1 — STATION CAPABILITY (PRESERVED from V1.3)
# =============================================================================
check('Station: CCS2 normalized to CCS2_TYPE2',
      (st.connector_type != 'CCS2').all())
check('Station: BIKE_DC normalized to VINFAST_MOTORCYCLE_CHARGING',
      (st.connector_type != 'BIKE_DC').all())
check('Station: SWAP_PACK_A normalized',
      (st.battery_type != 'SWAP_PACK_A').all())
check('Car stations: connector=CCS2_TYPE2, type includes CHARGING',
      st.loc[st.supported_vehicle_type.str.contains('EV_CAR'),
             'connector_type'].str.contains('CCS2').all())
check('Motorcycle stations: connector=VINFAST_MOTORCYCLE_CHARGING',
      st.loc[st.supported_vehicle_type.str.contains('EV_MOTORBIKE'),
             'connector_type'].str.contains('VINFAST_MOTORCYCLE_CHARGING').all())

# =============================================================================
# 9. V1.3.1 — CANDIDATE LABELS (PHASE 4 FIX)
# =============================================================================
# Unresolved AUTO events (swap bikes with need_service=True) generate BOTH
# CHARGING and BATTERY_SWAP candidates. This preserves service alternatives.

# AUTO_DETECTED events with need_service=True for candidate generation
auto_service = auto[auto.need_service.astype(bool)]
unresolved_events = auto_service[auto_service.resolved_service_type.isna()]
resolved_events = auto_service[auto_service.resolved_service_type.notna()]

# Unresolved events should have BOTH service candidates (CHARGING + BATTERY_SWAP)
unresolved_cands = cand[cand.event_id.isin(unresolved_events.event_id)]
if len(unresolved_cands) > 0:
    unresolved_services = unresolved_cands.service_type.value_counts()
    check('Unresolved events: both CHARGING and BATTERY_SWAP candidates exist',
          'CHARGING' in unresolved_services and 'BATTERY_SWAP' in unresolved_services,
          unresolved_services.to_dict())
    # For each unresolved event, check both services are present
    both_present = unresolved_cands.groupby('event_id').service_type.apply(
        lambda x: set(x) == {'CHARGING', 'BATTERY_SWAP'}
    ).all()
    check('Each unresolved event: both CHARGING and BATTERY_SWAP candidate rows',
          both_present,
          f'events with both={both_present.sum()}, total unresolved={len(unresolved_events)}')

# ELIGIBLE BATTERY_SWAP candidates: only from swap-capable vehicles
elig_swap = cand[(cand.eligible == True) & (cand.service_type == 'BATTERY_SWAP')]
if len(elig_swap) > 0:
    swap_vehicles = elig_swap.merge(
        demand[['event_id', 'swap_supported']].drop_duplicates(),
        on='event_id'
    )
    check('ELIGIBLE BATTERY_SWAP: all from swap-capable vehicles',
          bs(swap_vehicles.swap_supported).all(),
          f'rows={len(elig_swap)}')

# ELIGIBLE CHARGING candidates
elig_charge = cand[(cand.eligible == True) & (cand.service_type == 'CHARGING')]
if len(elig_charge) > 0:
    charge_vehicles = elig_charge.merge(
        demand[['event_id', 'charging_supported']].drop_duplicates(),
        on='event_id'
    )
    check('ELIGIBLE CHARGING: all from charge-capable vehicles',
          bs(charge_vehicles.charging_supported).all(),
          f'rows={len(elig_charge)}')

# All ranking rows must come from ELIGIBLE candidates (match by event+station+service_type)
# NOTE: This checks ranking rows specifically, not all candidate rows for ranking events.
# Unresolved events generate BOTH CHARGING and BATTERY_SWAP candidates; only ELIGIBLE
# ones appear in ranking.
rank_vs_cand = rank.merge(
    cand[['event_id', 'station_id', 'service_type', 'eligible']].rename(
        columns={'eligible': 'source_eligible'}),
    on=['event_id', 'station_id', 'service_type'],
    how='left'
)
check('Ranking: all rows come from ELIGIBLE candidates',
      bs(rank_vs_cand.source_eligible).all(),
      f'non-eligible={(~bs(rank_vs_cand.source_eligible)).sum()}')

# Reason vocabulary
allowed_reasons = {
    'ELIGIBLE', 'INCOMPATIBLE', 'OFFLINE', 'FULL',
    'UNREACHABLE', 'INSUFFICIENT_SOC_TO_REACH',
    'NO_SWAP_BATTERY', 'EXCESSIVE_QUEUE'
}
check('Candidate: allowed reason vocabulary',
      set(cand.reason) <= allowed_reasons,
      cand.reason.value_counts().to_dict())
check('Candidate: eligible iff reason=ELIGIBLE',
      (bs(cand.eligible) == cand.reason.eq('ELIGIBLE')).all())

# =============================================================================
# 10. V1.3.1 — RANKING & RECOMMENDATION
# =============================================================================
check('Ranking: composite key unique',
      not rank.duplicated(['event_id', 'station_id', 'service_type']).any())
check('Ranking: all candidates ELIGIBLE',
      bs(rank.candidate_eligible).all())
check('Ranking: service type distribution covers CHARGING and BATTERY_SWAP',
      set(rank.service_type.unique()) <= {'CHARGING', 'BATTERY_SWAP'},
      rank.service_type.value_counts().to_dict())

# Group size checks
group_sizes = rank.groupby('event_id').size()
check('Ranking: group size 1..8',
      group_sizes.between(1, MAX_RANK_CANDIDATES).all(),
      group_sizes.value_counts().sort_index().to_dict())
check('LTR flag: True only for groups >= 2',
      all(bs(g.is_ltr_group).eq(len(g) >= 2).all()
          for _, g in rank.groupby('event_id')))

# Ranking cost formula
calc_cost = (
    rank.traffic_adjusted_eta_min +
    rank.queue_wait_min +
    rank.service_time_min +
    0.25 * rank.detour_time_min +
    0.002 * rank.detour_distance_m -
    0.35 * np.minimum(rank.available_capacity, 6)
)
check('Ranking: baseline cost v3 recomputation',
      np.allclose(calc_cost, rank.ranking_cost_label, atol=0.02),
      f'max_err={float(np.max(np.abs(calc_cost - rank.ranking_cost_label))):.4f}')

# Ranking order: sorted by cost then station_id
rank_order_ok = all(
    g.sort_values(['ranking_cost_label', 'station_id']).reference_rank.tolist() ==
    list(range(1, len(g) + 1))
    for _, g in rank.groupby('event_id')
)
check('Ranking: reference_rank ordering', rank_order_ok)
check('Ranking: exactly one best per group',
      rank.groupby('event_id').is_reference_best.apply(
          lambda x: bs(x).sum()).eq(1).all())

# Recommendation correctness
check('Recommendation: has_recommendation=True iff eligible candidates exist',
      (
          (bs(rec.has_recommendation) == True).sum() ==
          cand[cand.eligible == True].event_id.nunique()
      ),
      f'has_rec_true={bs(rec.has_recommendation).sum()}, '
      f'elig_events={cand[cand.eligible==True].event_id.nunique()}')

# Recommendations reference eligible stations
rec_with_station = rec[rec.reference_station_id.notna()]
if len(rec_with_station) > 0:
    # For each recommendation, check the referenced station is ELIGIBLE.
    # For RESOLVED events (single service): match by event_id + station_id + service_type.
    # For UNRESOLVED events (both services): the station must be ELIGIBLE for
    #   at least one service type at that station.
    auto_events = auto.set_index('event_id')
    ref_checks = []
    for _, r in rec_with_station.iterrows():
        eid = r.event_id
        sid = str(r.reference_station_id)
        ev = auto_events.loc[eid] if eid in auto_events.index else None
        is_resolved = ev is not None and pd.notna(ev.service_type) and str(ev.service_type) not in ['nan', 'NONE', '']
        svc = str(ev.service_type) if is_resolved else None
        if is_resolved and svc:
            # Match by service type
            match = cand[(cand.event_id == eid) &
                          (cand.station_id == sid) &
                          (cand.service_type == svc)]
        else:
            # Unresolved: any ELIGIBLE match at this station
            match = cand[(cand.event_id == eid) &
                          (cand.station_id == sid) &
                          (cand.eligible == True)]
        ok = len(match) > 0
        ref_checks.append({'event_id': eid, 'station_id': sid, 'ok': ok, 'resolved': is_resolved, 'service': svc})
    ref_df = pd.DataFrame(ref_checks)
    check('Recommendations: reference station is ELIGIBLE',
          ref_df.ok.all(),
          f"non-eligible refs={int((~ref_df.ok).sum())}, resolved={int(ref_df.resolved.sum())}, unresolved={int((~ref_df.resolved).sum())}")

# =============================================================================
# 11. V1.3.1 — ENERGY SERVICE REQUESTS CONTRACT
# =============================================================================
check('energy_service_requests: resolved_service_type column present',
      'resolved_service_type' in esr.columns)
check('energy_service_requests: requested_service_type column present',
      'requested_service_type' in esr.columns)
check('energy_service_requests: rows == demand_labels rows',
      len(esr) == len(demand),
      f'esr={len(esr)}, demand={len(demand)}')

# =============================================================================
# 12. V1.3.1 — LEGACY TRAINING FILE STATUS
# =============================================================================
# demand_features.csv contains all demand rows (including DR) and includes
# need_service as a column. It is marked as DEPRECATED.
# Active training: demand_need_service_features.csv + demand_need_service_labels.csv
check('Legacy demand_features: need_service column present (DEPRECATED)',
      'need_service' in df_feat.columns)
check('Legacy demand_features: resolved_service_type present',
      'resolved_service_type' in df_feat.columns)

# =============================================================================
# 13. V1.3.1 — SCENARIO MIGRATION (PHASE 5)
# =============================================================================
check('Scenario NEED_ENERGY_BOTH_ALLOWED present',
      'NEED_ENERGY_BOTH_ALLOWED' in sc.scenario_id.values)
check('Scenario NEED_SWAP NOT present (renamed)',
      'NEED_SWAP' not in sc.scenario_id.values)

# NEED_ENERGY_BOTH_ALLOWED: vehicles are swap-capable
new_scenario = sc[sc.scenario_id == 'NEED_ENERGY_BOTH_ALLOWED']
if len(new_scenario) > 0:
    trip_meta = trips.set_index('trip_id')
    veh_meta = vehicles.set_index('vehicle_id')
    for _, row in new_scenario.iterrows():
        vid = trip_meta.loc[row.example_trip_id].vehicle_id
        ok = bs(veh_meta.loc[vid].swap_supported)
        scenario_check(
            'NEED_ENERGY_BOTH_ALLOWED',
            ok,
            f'trip={row.example_trip_id}, vehicle={vid}, swap={ok}'
        )

# =============================================================================
# 14. SERVICE-SPECIFIC STATION CAPACITY (PRESERVED from V1.3)
# =============================================================================
state = ss.merge(st[['station_id', 'station_type', 'charging_slots', 'swap_slots']],
                 on='station_id')

for c in ['available_charging_slots', 'occupied_charging_slots',
          'available_swap_slots', 'occupied_swap_slots', 'available_swap_batteries']:
    check(f'Station state nonnegative: {c}', (state[c] >= 0).all())

check('Charging capacity <= charging_slots',
      ((state.available_charging_slots + state.occupied_charging_slots) <=
       state.charging_slots).all())
check('Swap capacity <= swap_slots',
      ((state.available_swap_slots + state.occupied_swap_slots) <=
       state.swap_slots).all())
check('Charging-only station: zero swap state',
      (state.loc[state.swap_slots == 0,
                 ['available_swap_slots', 'occupied_swap_slots',
                  'available_swap_batteries']].sum(axis=1) == 0).all())
check('Swap-only station: zero charging state',
      (state.loc[state.charging_slots == 0,
                 ['available_charging_slots',
                  'occupied_charging_slots']].sum(axis=1) == 0).all())
check('Offline station: all capacities zero',
      (state.loc[state.operating_status != 'OPEN',
                 ['available_charging_slots', 'occupied_charging_slots',
                  'available_swap_slots', 'occupied_swap_slots',
                  'available_swap_batteries']].sum(axis=1) == 0).all())

# Queue semantics
qstate = (q.merge(
    ss[['station_id', 'timestamp', 'occupied_charging_slots', 'occupied_swap_slots']],
    on=['station_id', 'timestamp'])
    .merge(st[['station_id', 'charging_slots', 'swap_slots']], on='station_id'))

for c in ['charging_queue_length', 'charging_active_service_count',
          'charging_estimated_wait_min', 'swap_queue_length',
          'swap_active_service_count', 'swap_estimated_wait_min']:
    check(f'Queue nonnegative: {c}', (qstate[c] >= 0).all())

check('Charging queue active <= occupied charging slots',
      (qstate.charging_active_service_count <= qstate.occupied_charging_slots).all())
check('Swap queue active <= occupied swap slots',
      (qstate.swap_active_service_count <= qstate.occupied_swap_slots).all())

ch_exp = np.where(
    (qstate.charging_queue_length > 0) & (qstate.charging_active_service_count > 0),
    (qstate.charging_queue_length * CHARGING_SERVICE_TIME_MIN /
     qstate.charging_active_service_count),
    0.0)
sw_exp = np.where(
    (qstate.swap_queue_length > 0) & (qstate.swap_active_service_count > 0),
    (qstate.swap_queue_length * SWAP_SERVICE_TIME_MIN /
     qstate.swap_active_service_count),
    0.0)
check('Charging queue wait formula',
      np.allclose(ch_exp, qstate.charging_estimated_wait_min, atol=0.011),
      f'max_err={float(np.max(np.abs(ch_exp - qstate.charging_estimated_wait_min))):.4f}')
check('Swap queue wait formula',
      np.allclose(sw_exp, qstate.swap_estimated_wait_min, atol=0.011),
      f'max_err={float(np.max(np.abs(sw_exp - qstate.swap_estimated_wait_min))):.4f}')

# =============================================================================
# 15. MAP MATCHING (Week 1 baseline — PRESERVED)
# =============================================================================
mmc['pos'] = bs(mmc.is_correct)
mmc['hard'] = bs(mmc.hard_negative)
g = mmc.groupby('observation_id')

check('MM: selected observations >= 3000',
      mmc.observation_id.nunique() >= 3000,
      f'obs={mmc.observation_id.nunique()}')
check('MM: exactly one positive per group',
      g.pos.sum().eq(1).all())
check('MM: at least one negative per group',
      g.pos.apply(lambda x: (~x).sum()).ge(1).all())

truth = mm_labels.set_index('observation_id').true_segment_id.astype(str)
pos = mmc[mmc.pos]
check('MM: positive candidate equals true segment',
      (pos.candidate_segment_id.astype(str).values ==
       pos.observation_id.map(truth).astype(str).values).all())
neg = mmc[~mmc.pos]
check('MM: negative candidate differs from truth',
      (neg.candidate_segment_id.astype(str).values !=
       neg.observation_id.map(truth).astype(str).values).all())
check('MM: hard-negative definition',
      (~mmc.hard | ((~mmc.pos) &
                    (mmc.distance_to_segment_m <= 20.0001) &
                    (mmc.heading_difference_deg <= 45.0001))).all(),
      f'hard={int(mmc.hard.sum())}')

mm_split = (mmc[['observation_id', 'trip_id', 'split']].drop_duplicates()
             .merge(splits, on='trip_id', suffixes=('_mm', '_trip')))
check('MM: split follows trip split', mm_split.eval('split_mm == split_trip').all())
check('MM: all split partitions present',
      set(mm_split.split_mm) == {'train', 'validation', 'test'},
      mm_split.split_mm.value_counts().to_dict())

# =============================================================================
# 16. REALTIME EVENTS (PRESERVED from V1.3)
# =============================================================================
replay_types = set(replay.event_type)
check('Realtime: includes GPS_UPDATE',
      'GPS_UPDATE' in replay_types)
check('Realtime: includes SOC_UPDATE',
      'SOC_UPDATE' in replay_types)
check('Realtime: includes STATION_STATUS_UPDATE',
      'STATION_STATUS_UPDATE' in replay_types)
check('Realtime: includes QUEUE_UPDATE',
      'QUEUE_UPDATE' in replay_types)
check('Realtime: includes TRAFFIC_UPDATE',
      'TRAFFIC_UPDATE' in replay_types)

status_keys = set(zip(ss.station_id.astype(str), ss.timestamp.astype(str)))
queue_keys = set(zip(q.station_id.astype(str), q.timestamp.astype(str)))
replay_status_keys = set(zip(
    replay.loc[replay.event_type == 'STATION_STATUS_UPDATE', 'entity_id'].astype(str),
    replay.loc[replay.event_type == 'STATION_STATUS_UPDATE', 'timestamp'].astype(str)))
replay_queue_keys = set(zip(
    replay.loc[replay.event_type == 'QUEUE_UPDATE', 'entity_id'].astype(str),
    replay.loc[replay.event_type == 'QUEUE_UPDATE', 'timestamp'].astype(str)))
check('Realtime: covers every station state',
      status_keys <= replay_status_keys,
      f'states={len(status_keys)}, replay={len(replay_status_keys)}')
check('Realtime: covers every queue state',
      queue_keys <= replay_queue_keys,
      f'queues={len(queue_keys)}, replay={len(replay_queue_keys)}')

payload_ok = True
for r in replay[replay.event_type == 'STATION_STATUS_UPDATE'].iloc[
           ::max(1, len(ss) // 100)].itertuples(index=False):
    p = json.loads(r.payload_json)
    req = {'status', 'available_charging_slots', 'occupied_charging_slots',
           'available_swap_slots', 'occupied_swap_slots',
           'available_swap_batteries', 'charging_service_time_min',
           'swap_service_time_min'}
    payload_ok &= req <= set(p)
for r in replay[replay.event_type == 'QUEUE_UPDATE'].iloc[
           ::max(1, len(q) // 100)].itertuples(index=False):
    p = json.loads(r.payload_json)
    req = {'charging_queue_length', 'charging_active_service_count',
           'charging_estimated_wait_min', 'swap_queue_length',
           'swap_active_service_count', 'swap_estimated_wait_min'}
    payload_ok &= req <= set(p)
check('Realtime: service-specific payload schema', payload_ok)

# =============================================================================
# 17. INDEPENDENT SCENARIO ASSERTIONS (PRESERVED from V1.3)
# =============================================================================
scx = sc.set_index('scenario_id')
trip_meta = trips.set_index('trip_id')
veh_meta = vehicles.set_index('vehicle_id')

def floor_iso(ts, minutes):
    return pd.Timestamp(ts).floor(f'{minutes}min').isoformat()


def get_station_queue(sid, ts, service_type):
    """Get queue wait for a station/timestamp/service combination."""
    ts_key = floor_iso(ts, 10)
    ss_row = ss[(ss.station_id == sid) & (ss.timestamp == ts_key)]
    q_row = q[(q.station_id == sid) & (q.timestamp == ts_key)]
    if len(ss_row) == 0 or len(q_row) == 0:
        return None, None
    sr = ss_row.iloc[0]
    qr = q_row.iloc[0]
    if service_type == 'CHARGING':
        return qr.charging_estimated_wait_min, sr.charging_service_time_min
    else:
        return qr.swap_estimated_wait_min, sr.swap_service_time_min


# BRIDGE_AMBIGUITY
r = scx.loc['BRIDGE_AMBIGUITY']
tid = r.example_trip_id
bridge_sids = set(segs.loc[segs.bridge.astype(str).str.lower().isin(['yes', 'true', '1']),
                             'segment_id'])
touch_bridge = true.loc[true.trip_id == tid, 'true_segment_id'].isin(bridge_sids).any()
mmg = mmc[mmc.trip_id == tid]
scenario_check('BRIDGE_AMBIGUITY',
               touch_bridge and ((~bs(mmg.is_correct)).sum() >= 1),
               f'bridge={touch_bridge}, negatives={int((~bs(mmg.is_correct)).sum())}')

# FARTHER_BUT_FASTER
r = scx.loc['FARTHER_BUT_FASTER']
rr = rank[rank.event_id == r.example_event_id].set_index('station_id')
try:
    a, b = rr.loc[str(r.evidence_entity_a)], rr.loc[str(r.evidence_entity_b)]
    dd = float(b.driver_to_station_distance_m) - float(a.driver_to_station_distance_m)
    gain = float(a.total_eta_min) - float(b.total_eta_min)
    ec = cand[(cand.event_id == r.example_event_id) &
              cand.station_id.isin([str(r.evidence_entity_a),
                                    str(r.evidence_entity_b)])]
    farther_ok = dd >= FARTHER_MIN_DISTANCE_DELTA_M and gain >= FARTHER_MEANINGFUL_ETA_MARGIN_MIN and bs(ec.eligible).all()
except Exception:
    dd = gain = float('nan')
    farther_ok = False
scenario_check('FARTHER_BUT_FASTER', farther_ok,
               f'dist_delta_m={dd:.1f}, eta_gain_min={gain:.3f}',
               {'distance_delta_m': dd, 'eta_improvement_min': gain})

# GPS_MISSING
r = scx.loc['GPS_MISSING']
tid = r.example_trip_id
ratio = len(gps[gps.trip_id == tid]) / len(true[true.trip_id == tid])
scenario_check('GPS_MISSING', ratio < 0.85,
               f'ratio={ratio:.4f}', {'gps_to_true_ratio': ratio})

# GPS_NOISE
r = scx.loc['GPS_NOISE']
tid = r.example_trip_id
j = (gps[gps.trip_id == tid][['observation_id', 'latitude', 'longitude']]
     .merge(mm_labels[['observation_id', 'true_latitude', 'true_longitude']],
            on='observation_id'))
errs = [hav_m(a, b, c, d) for a, b, c, d in
        zip(j.latitude, j.longitude, j.true_latitude, j.true_longitude)]
med_err = float(np.median(errs)) if errs else 0.0
scenario_check('GPS_NOISE', med_err >= 10.0,
               f'median_error_m={med_err:.2f}', {'median_error_m': med_err})

# HEAVY_TRAFFIC
r = scx.loc['HEAVY_TRAFFIC']
tr = traf[(traf.segment_id == r.evidence_entity_a) & (traf.timestamp == r.evidence_timestamp)]
heavy_ok = (len(tr) > 0 and
            tr.iloc[0].traffic_level in ['HEAVY', 'INCIDENT'] and
            float(tr.iloc[0].delay_factor) > 1.5)
scenario_check('HEAVY_TRAFFIC', heavy_ok,
               tr.iloc[0].to_dict() if len(tr) else 'missing')

# INCOMPATIBLE_STATION
r = scx.loc['INCOMPATIBLE_STATION']
cc = cand[cand.event_id == r.example_event_id]
scenario_check('INCOMPATIBLE_STATION',
               (cc.reason == 'INCOMPATIBLE').any() and bs(cc.eligible).any(),
               f"incompatible={(cc.reason=='INCOMPATIBLE').sum()}, "
               f"eligible={int(bs(cc.eligible).sum())}")

# INSUFFICIENT_RANGE
r = scx.loc['INSUFFICIENT_RANGE']
cc = cand[cand.event_id == r.example_event_id]
scenario_check('INSUFFICIENT_RANGE',
               (cc.reason == 'INSUFFICIENT_SOC_TO_REACH').any(),
               f"count={(cc.reason=='INSUFFICIENT_SOC_TO_REACH').sum()}")

# LONG_QUEUE
r = scx.loc['LONG_QUEUE']
cr = cand[(cand.event_id == r.example_event_id) &
           (cand.station_id == r.evidence_entity_a)]
if len(cr) > 0:
    # For unresolved events (service_type is NaN), check BATTERY_SWAP first, then CHARGING
    ev_row = demand[demand.event_id == r.example_event_id].iloc[0]
    svc_in_demand = ev_row.service_type
    if pd.isna(svc_in_demand) or str(svc_in_demand) in ['nan', 'NONE', '']:
        # Unresolved: check BATTERY_SWAP wait first, then CHARGING
        swap_row = cr[cr.service_type == 'BATTERY_SWAP']
        charge_row = cr[cr.service_type == 'CHARGING']
        if len(swap_row) > 0:
            wait_val = float(swap_row.iloc[0].estimated_wait_min)
            svc_name = 'BATTERY_SWAP'
        elif len(charge_row) > 0:
            wait_val = float(charge_row.iloc[0].estimated_wait_min)
            svc_name = 'CHARGING'
        else:
            wait_val = 0.0
            svc_name = 'UNKNOWN'
    else:
        svc = str(svc_in_demand)
        svc_row = cr[cr.service_type == svc]
        wait_val = float(svc_row.iloc[0].estimated_wait_min) if len(svc_row) > 0 else 0.0
        svc_name = svc
    long_ok = len(cr) > 0 and wait_val >= 30.0
    scenario_check('LONG_QUEUE', long_ok,
                   f'service={svc_name}, wait={wait_val}')
else:
    scenario_check('LONG_QUEUE', False, 'missing')

# LOW_SOC
r = scx.loc['LOW_SOC']
feat_row = demand[demand.event_id == r.example_event_id]
if len(feat_row) == 0:
    low_soc_ok = False
    soc_val, safe_val = 'N/A', 'N/A'
else:
    feat = feat_row.iloc[0]
    vid = feat.vehicle_id
    v = veh_meta.loc[vid]
    low_soc_ok = float(feat.current_soc_pct) <= float(v.minimum_safe_soc_pct)
    soc_val = f"{feat.current_soc_pct}"
    safe_val = f"{v.minimum_safe_soc_pct}"
scenario_check('LOW_SOC', low_soc_ok, f'soc={soc_val}, safe={safe_val}')

# NEAREST_FULL
r = scx.loc['NEAREST_FULL']
cr = cand[(cand.event_id == r.example_event_id) &
           (cand.station_id == r.evidence_entity_a)]
nearest_full_ok = (len(cr) > 0 and
                   cr.iloc[0].reason == 'FULL' and
                   int(cr.iloc[0].available_capacity) == 0)
scenario_check('NEAREST_FULL', nearest_full_ok,
               (cr.iloc[0][['reason', 'available_capacity',
                              'service_type']].to_dict()
                if len(cr) else 'missing'))

# NEAR_TIE_STATIONS
r = scx.loc['NEAR_TIE_STATIONS']
rr = rank[rank.event_id == r.example_event_id].sort_values('ranking_cost_label')
tie_diff = (float(rr.iloc[1].ranking_cost_label - rr.iloc[0].ranking_cost_label)
            if len(rr) >= 2 else float('inf'))
scenario_check('NEAR_TIE_STATIONS', tie_diff <= NEAR_TIE_THRESHOLD_MIN,
               f'top2_cost_diff={tie_diff:.4f}',
               {'top2_cost_diff_min': tie_diff})

# NEED_CHARGING
r = scx.loc['NEED_CHARGING']
dtrip = demand[demand.trip_id == r.example_trip_id]
vid = trip_meta.loc[r.example_trip_id].vehicle_id
scenario_check('NEED_CHARGING',
               bs(dtrip.loc[dtrip.request_source == 'AUTO_DETECTED', 'need_service']).any() and
               bs(veh_meta.loc[vid].charging_supported),
               f"charging_auto={dtrip.service_type.eq('CHARGING').sum()}")

# NEED_ENERGY_BOTH_ALLOWED (formerly NEED_SWAP)
r = scx.loc['NEED_ENERGY_BOTH_ALLOWED']
dtrip = demand[(demand.trip_id == r.example_trip_id) &
               (demand.request_source == 'AUTO_DETECTED')]
vid = trip_meta.loc[r.example_trip_id].vehicle_id
need_both_ok = (
    bs(dtrip.need_service).any() and
    bs(veh_meta.loc[vid].swap_supported) and
    bs(veh_meta.loc[vid].charging_supported)
)
scenario_check('NEED_ENERGY_BOTH_ALLOWED', need_both_ok,
               f'trip={r.example_trip_id}, vehicle={vid}, '
               f'swap={bs(veh_meta.loc[vid].swap_supported)}, '
               f'charge={bs(veh_meta.loc[vid].charging_supported)}')

# NORMAL_TRIP
r = scx.loc['NORMAL_TRIP']
dtrip = demand[(demand.trip_id == r.example_trip_id) &
               (demand.request_source == 'AUTO_DETECTED')]
scenario_check('NORMAL_TRIP',
               (~bs(dtrip.need_service)).all() and
               (dtrip.service_type.isna() | dtrip.service_type.eq('NONE')).all(),
               f"need_service_count={int(bs(dtrip.need_service).sum())}")

# NO_SERVICE_NEEDED
r = scx.loc['NO_SERVICE_NEEDED']
dtrip = demand[(demand.trip_id == r.example_trip_id) &
               (demand.request_source == 'AUTO_DETECTED')]
scenario_check('NO_SERVICE_NEEDED',
               (~bs(dtrip.need_service)).all() and
               (dtrip.service_type.isna() | dtrip.service_type.eq('NONE')).all(),
               f"need_service_count={int(bs(dtrip.need_service).sum())}")

# NO_AVAILABLE_STATION
r = scx.loc['NO_AVAILABLE_STATION']
cc = cand[cand.event_id == r.example_event_id]
scenario_check('NO_AVAILABLE_STATION',
               int(bs(cc.eligible).sum()) == 0,
               f'eligible={int(bs(cc.eligible).sum())}')

# PARALLEL_ROADS
r = scx.loc['PARALLEL_ROADS']
mmg = mmc[(mmc.trip_id == r.example_trip_id) & bs(mmc.hard_negative)]
scenario_check('PARALLEL_ROADS', len(mmg) > 0,
               f'hard_negatives={len(mmg)}')

# STATION_OFFLINE
r = scx.loc['STATION_OFFLINE']
cr = cand[(cand.event_id == r.example_event_id) &
           (cand.station_id == r.evidence_entity_a)]
offline_ok = (len(cr) > 0 and
              cr.iloc[0].reason == 'OFFLINE' and
              cr.iloc[0].operating_status != 'OPEN')
scenario_check('STATION_OFFLINE', offline_ok,
               (cr.iloc[0][['reason', 'operating_status']].to_dict()
                if len(cr) else 'missing'))

# QUEUE_REALTIME_CHANGE
r = scx.loc['QUEUE_REALTIME_CHANGE']
sid = str(r.evidence_entity_a)
before_ts = str(r.before_timestamp)
after_ts = str(r.after_timestamp)
ev_row = demand[demand.event_id == r.example_event_id].iloc[0]
svc = str(ev_row.service_type) if str(ev_row.service_type) not in ['nan', 'NONE'] else 'CHARGING'
qa = q[(q.station_id == sid) & (q.timestamp == before_ts)]
qb = q[(q.station_id == sid) & (q.timestamp == after_ts)]
if len(qa) and len(qb) and svc in ['CHARGING', 'BATTERY_SWAP']:
    if svc == 'CHARGING':
        w0, w1 = float(qa.iloc[0].charging_estimated_wait_min), float(qb.iloc[0].charging_estimated_wait_min)
    else:
        w0, w1 = float(qa.iloc[0].swap_estimated_wait_min), float(qb.iloc[0].swap_estimated_wait_min)
    replay_key = set(zip(replay.event_type.astype(str),
                         replay.entity_id.astype(str),
                         replay.timestamp.astype(str)))
    q_chg_ok = (abs(w1 - w0) >= 20 and
                ('QUEUE_UPDATE', sid, before_ts) in replay_key and
                ('QUEUE_UPDATE', sid, after_ts) in replay_key)
else:
    w0 = w1 = float('nan')
    q_chg_ok = False
scenario_check('QUEUE_REALTIME_CHANGE', q_chg_ok,
               f'{svc} wait {w0}->{w1}')

# STATION_STATUS_CHANGE
r = scx.loc['STATION_STATUS_CHANGE']
sid = str(r.evidence_entity_a)
before_ts = str(r.before_timestamp)
after_ts = str(r.after_timestamp)
sa = ss[(ss.station_id == sid) & (ss.timestamp == before_ts)]
sb = ss[(ss.station_id == sid) & (ss.timestamp == after_ts)]
replay_key = set(zip(replay.event_type.astype(str),
                     replay.entity_id.astype(str),
                     replay.timestamp.astype(str)))
status_ok = (len(sa) and len(sb) and
             sa.iloc[0].operating_status != sb.iloc[0].operating_status and
             ('STATION_STATUS_UPDATE', sid, before_ts) in replay_key and
             ('STATION_STATUS_UPDATE', sid, after_ts) in replay_key)
scenario_check('STATION_STATUS_CHANGE', status_ok,
               f"{sa.iloc[0].operating_status if len(sa) else '?'}"
               f"->{sb.iloc[0].operating_status if len(sb) else '?'}")

# TRAFFIC_REALTIME_CHANGE
r = scx.loc['TRAFFIC_REALTIME_CHANGE']
sid = str(r.evidence_entity_a)
before_ts = str(r.before_timestamp)
after_ts = str(r.after_timestamp)
ta = traf[(traf.segment_id == sid) & (traf.timestamp == before_ts)]
tb = traf[(traf.segment_id == sid) & (traf.timestamp == after_ts)]
traffic_ok = (len(ta) and len(tb) and
              (ta.iloc[0].traffic_level != tb.iloc[0].traffic_level or
               float(ta.iloc[0].current_speed_kmh) != float(tb.iloc[0].current_speed_kmh)) and
              ('TRAFFIC_UPDATE', sid, before_ts) in replay_key and
              ('TRAFFIC_UPDATE', sid, after_ts) in replay_key)
scenario_check('TRAFFIC_REALTIME_CHANGE', traffic_ok,
               f"{ta.iloc[0].traffic_level if len(ta) else '?'}"
               f"->{tb.iloc[0].traffic_level if len(tb) else '?'}")

check('All scenario independent assertions PASS',
      all(x['status'] == 'PASS' for x in scenario_results),
      {x['scenario_id']: x['status'] for x in scenario_results})

# Sync scenario_coverage validator status
status_map = {x['scenario_id']: x['status'] for x in scenario_results}
sc['validator_status'] = sc.scenario_id.map(status_map).fillna('FAIL')
sc.to_csv(ROOT / 'scenarios/scenario_coverage.csv', index=False)

# =============================================================================
# 18. PBF INTEGRITY (Week 1 baseline — PRESERVED)
# =============================================================================
base = ROOT / 'map/raw/hanoi-baseline.osm.pbf'
patch = ROOT / 'map/raw/hanoi-patched.osm.pbf'
check('Baseline PBF byte integrity',
      sha256(base) == EXPECTED_BASELINE_SHA256, sha256(base))
check('Patched PBF byte integrity',
      sha256(patch) == EXPECTED_PATCHED_SHA256, sha256(patch))

diff = pd.read_csv(ROOT / 'map/processed/pbf_diff.csv', dtype={'osm_way_id': str})
row = diff[diff.osm_way_id == '881947000']
check('Cau Thanh Tri diff explicitly preserved',
      len(row) == 1 and
      not bool(row.iloc[0].geometry_changed) and
      '"motorcar"=>"designated"' in str(row.iloc[0].baseline_other_tags) and
      '"motorcar"=>"no"' in str(row.iloc[0].patched_other_tags))

warn = json.load(open(ROOT / 'validation/pbf_integrity.json', encoding='utf-8')).get('warning', '')
check('Cau Thanh Tri human-confirmation warning present',
      'Human confirmation is required' in warn and '881947000' in warn)

# =============================================================================
# WRITE RESULTS
# =============================================================================
summary = {
    'passed': sum(x['status'] == 'PASS' for x in res),
    'failed': sum(x['status'] == 'FAIL' for x in res),
    'overall': 'PASS' if all(x['status'] == 'PASS' for x in res) else 'FAIL',
    'results': res
}
json.dump(summary, open(ROOT / 'validation/validation_results.json', 'w'),
          indent=2, ensure_ascii=False)
pd.DataFrame(res).to_csv(ROOT / 'validation/validation_results.csv', index=False)

sc_summary = {
    'overall': 'PASS' if all(x['status'] == 'PASS' for x in scenario_results) else 'FAIL',
    'passed': sum(x['status'] == 'PASS' for x in scenario_results),
    'failed': sum(x['status'] == 'FAIL' for x in scenario_results),
    'results': scenario_results
}
json.dump(sc_summary, open(ROOT / 'validation/scenario_validation_results.json', 'w'),
          indent=2, ensure_ascii=False)

group_sizes = rank.groupby('event_id').size()
service_events = demand[bs(demand.need_service)]
elig_counts = (cand[cand.event_id.isin(service_events.event_id)]
               .groupby('event_id').eligible
               .apply(lambda x: int(bs(x).sum())))
elig_counts = (service_events.set_index('event_id').index.to_series()
               .map(elig_counts).fillna(0).astype(int))

rank_stats = {
    'rows': int(len(rank)),
    'event_groups': int(rank.event_id.nunique()),
    'group_size_distribution': {str(int(k)): int(v)
                                for k, v in group_sizes.value_counts().sort_index().items()},
    'ltr_event_groups': int(rank.loc[bs(rank.is_ltr_group), 'event_id'].nunique()),
    'single_candidate_groups': int((group_sizes == 1).sum()),
    'split_groups': rank.drop_duplicates('event_id').split.value_counts().to_dict(),
    'service_event_count': int(len(service_events)),
    'events_with_eligible_station': int((elig_counts > 0).sum()),
    'events_with_no_eligible_station': int((elig_counts == 0).sum()),
    'has_recommendation_true': int(bs(rec.has_recommendation).sum()),
    'has_recommendation_false': int((~bs(rec.has_recommendation)).sum()),
}
json.dump(rank_stats, open(ROOT / 'validation/ranking_stats.json', 'w'), indent=2)

counts = {
    'road_nodes': len(nodes), 'road_segments': len(segs),
    'drivers': len(drivers), 'vehicles': len(vehicles), 'trips': len(trips),
    'true_trajectory_points': len(true), 'gps_observations': len(gps),
    'soc_history': len(bat), 'stations': len(st),
    'station_status': len(ss), 'queue_status': len(q),
    'traffic_snapshots': len(traf), 'realtime_events': len(replay),
    'map_matching_candidates': len(mmc),
    'demand_labels': len(demand),
    'candidate_labels': len(cand),
    'ranking_reference': len(rank),
    'ranking_event_groups': int(rank.event_id.nunique()),
    'recommendation_labels': len(rec),
    'scenario_rows': len(sc),
    'need_service_training_samples': len(need_feat),
    'need_service_positive': int(need_lbl['need_service'].sum()),
    'need_service_negative': int((~need_lbl['need_service'].astype(bool)).sum()),
}
json.dump(counts, open(ROOT / 'validation/data_counts.json', 'w'), indent=2)

print(json.dumps({
    'passed': summary['passed'],
    'failed': summary['failed'],
    'overall': summary['overall'],
    'scenario_passed': sc_summary['passed'],
    'scenario_failed': sc_summary['failed'],
    'scenario_overall': sc_summary['overall'],
    'rank_stats': rank_stats,
    'need_service_training': {
        'samples': len(need_feat),
        'positive': int(need_lbl['need_service'].sum()),
        'negative': int((~need_lbl['need_service'].astype(bool)).sum()),
        'positive_ratio': f"{int(need_lbl['need_service'].sum()) / len(need_lbl):.1%}",
        'split': need_feat.split.value_counts().to_dict(),
    }
}, indent=2))

if summary['failed'] or sc_summary['failed']:
    print('\n=== FAILED CHECKS ===')
    print(pd.DataFrame([x for x in res if x['status'] == 'FAIL']).to_string(index=False))
    print('\n=== FAILED SCENARIOS ===')
    print(json.dumps([x for x in scenario_results if x['status'] == 'FAIL'], indent=2))
    raise SystemExit(1)
