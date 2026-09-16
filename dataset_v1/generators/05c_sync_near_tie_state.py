from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TARGET_STATION = 'S030'
TARGET_STATE_TS = '2026-09-01T08:10:00+07:00'

cand = pd.read_csv(ROOT/'labels/candidate_labels.csv')
rank = pd.read_csv(ROOT/'training/ranking_reference.csv')
rec = pd.read_csv(ROOT/'labels/recommendation_labels.csv')
q = pd.read_csv(ROOT/'queue/queue_status.csv.gz')
ss = pd.read_csv(ROOT/'stations/station_status.csv.gz')

qm = q.station_id.eq(TARGET_STATION) & q.timestamp.eq(TARGET_STATE_TS)
sm = ss.station_id.eq(TARGET_STATION) & ss.timestamp.eq(TARGET_STATE_TS)
if not qm.any() or not sm.any():
    raise SystemExit('Target state missing')
qr = q.loc[qm].iloc[0]
sr = ss.loc[sm].iloc[0]

# Synchronize every candidate that references the changed service-specific state.
mask = cand.station_id.eq(TARGET_STATION) & cand.state_timestamp.eq(TARGET_STATE_TS)
affected_events = sorted(cand.loc[mask, 'event_id'].unique())
for idx, r in cand.loc[mask].iterrows():
    svc = str(r.service_type)
    if svc == 'CHARGING':
        slots = int(sr.available_charging_slots)
        cap = slots
        qlen = int(qr.charging_queue_length)
        wait = float(qr.charging_estimated_wait_min)
        stime = float(sr.charging_service_time_min)
        batt = 0
    elif svc == 'BATTERY_SWAP':
        slots = int(sr.available_swap_slots)
        batt = int(sr.available_swap_batteries)
        cap = min(slots, batt)
        qlen = int(qr.swap_queue_length)
        wait = float(qr.swap_estimated_wait_min)
        stime = float(sr.swap_service_time_min)
    else:
        slots = cap = qlen = batt = 0
        wait = stime = 0.0
    cand.loc[idx, ['available_service_slots','available_swap_batteries','available_capacity','queue_length','estimated_wait_min','service_time_min']] = [slots,batt,cap,qlen,round(wait,2),round(stime,2)]

# Ranking contains only eligible candidates; synchronize matching rows then rerank each affected group.
rank_affected_events = []
for eid in affected_events:
    rm = rank.event_id.eq(eid) & rank.station_id.eq(TARGET_STATION)
    if not rm.any():
        continue
    rank_affected_events.append(eid)
    cr = cand[cand.event_id.eq(eid) & cand.station_id.eq(TARGET_STATION)].iloc[0]
    rank.loc[rm, 'queue_wait_min'] = float(cr.estimated_wait_min)
    rank.loc[rm, 'service_time_min'] = float(cr.service_time_min)
    rank.loc[rm, 'available_capacity'] = int(cr.available_capacity)
    rank.loc[rm, 'total_eta_min'] = (
        rank.loc[rm, 'traffic_adjusted_eta_min'].astype(float)
        + rank.loc[rm, 'queue_wait_min'].astype(float)
        + rank.loc[rm, 'service_time_min'].astype(float)
    ).round(3)
    rank.loc[rm, 'ranking_cost_label'] = (
        rank.loc[rm, 'total_eta_min'].astype(float)
        + 0.25 * rank.loc[rm, 'detour_time_min'].astype(float)
        + 0.002 * rank.loc[rm, 'detour_distance_m'].astype(float)
        - 0.35 * rank.loc[rm, 'available_capacity'].clip(upper=6).astype(float)
    ).round(4)

    grp_idx = rank.index[rank.event_id.eq(eid)]
    ordered = rank.loc[grp_idx].sort_values(['ranking_cost_label','station_id'])
    rank.loc[grp_idx, 'reference_rank'] = 0
    rank.loc[grp_idx, 'is_reference_best'] = False
    for pos, idx in enumerate(ordered.index, 1):
        rank.loc[idx, 'reference_rank'] = pos
        rank.loc[idx, 'is_reference_best'] = pos == 1
    best = rank.loc[grp_idx].sort_values(['ranking_cost_label','station_id']).iloc[0]
    rr = rec.event_id.eq(eid)
    rec.loc[rr, 'reference_station_id'] = best.station_id
    rec.loc[rr, 'has_recommendation'] = True
    rec.loc[rr, 'label_method'] = 'eligible_candidates_documented_baseline_cost_v3'

cand.to_csv(ROOT/'labels/candidate_labels.csv', index=False)
rank.to_csv(ROOT/'training/ranking_reference.csv', index=False)
rec.to_csv(ROOT/'labels/recommendation_labels.csv', index=False)

print(json.dumps({
    'state': [TARGET_STATION, TARGET_STATE_TS],
    'candidate_events_synchronized': affected_events,
    'ranking_events_reranked': rank_affected_events,
    'swap_queue_length': int(qr.swap_queue_length),
    'swap_wait_min': float(qr.swap_estimated_wait_min),
}, indent=2))
