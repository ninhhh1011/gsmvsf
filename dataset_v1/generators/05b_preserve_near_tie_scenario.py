from __future__ import annotations
import json, math
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
TARGET_MAX_DIFF_MIN=3.0
TARGET_DIFF_MIN=1.5


def bs(s):
    if getattr(s,'dtype',None)==bool:return s
    return s.astype(str).str.lower().isin(['true','1','yes'])

trips=pd.read_csv(ROOT/'trips/trips.csv')
demand=pd.read_csv(ROOT/'labels/demand_labels.csv')
cand=pd.read_csv(ROOT/'labels/candidate_labels.csv')
rank=pd.read_csv(ROOT/'training/ranking_reference.csv')
rec=pd.read_csv(ROOT/'labels/recommendation_labels.csv')
q=pd.read_csv(ROOT/'queue/queue_status.csv.gz')
ss=pd.read_csv(ROOT/'stations/station_status.csv.gz')
replay=pd.read_csv(ROOT/'realtime/events.csv.gz')
sc=pd.read_csv(ROOT/'scenarios/scenario_coverage.csv')

near_trips=set(trips.loc[trips.scenario_id.eq('NEAR_TIE_STATIONS'),'trip_id'])
choices=[]
for eid,g in rank[rank.trip_id.isin(near_trips)].groupby('event_id'):
    s=g.sort_values(['ranking_cost_label','station_id'])
    if len(s)<2:continue
    diff=float(s.iloc[1].ranking_cost_label-s.iloc[0].ranking_cost_label)
    if diff<=TARGET_MAX_DIFF_MIN:
        choices.append((0.0,eid,s.iloc[0],s.iloc[1],diff))
    else:
        choices.append((diff-TARGET_DIFF_MIN,eid,s.iloc[0],s.iloc[1],diff))

if not choices:
    raise SystemExit('No ranking group available for NEAR_TIE_STATIONS')
choices=sorted(choices,key=lambda x:(max(0,x[0]),x[4]))
needed,eid,a,b,old_diff=choices[0]
service=str(a.service_type)
state_ts=str(cand[(cand.event_id.eq(eid))&(cand.station_id.eq(a.station_id))].iloc[0].state_timestamp)
qm=q.station_id.eq(a.station_id)&q.timestamp.eq(state_ts)
sm=ss.station_id.eq(a.station_id)&ss.timestamp.eq(state_ts)
if not qm.any() or not sm.any():
    raise SystemExit('Missing queue/state row for near-tie target')

if old_diff>TARGET_MAX_DIFF_MIN:
    if service=='CHARGING':
        active=int(q.loc[qm,'charging_active_service_count'].iloc[0]); svc=float(q.loc[qm,'charging_service_time_min'].iloc[0])
        if active<=0:
            active=max(1,int(ss.loc[sm,'occupied_charging_slots'].iloc[0]))
            q.loc[qm,'charging_active_service_count']=active
        add_wait=max(0.0,old_diff-TARGET_DIFF_MIN)
        qlen=int(round(add_wait*active/max(svc,1e-9)))
        qlen=max(1,qlen)
        wait=qlen*svc/active
        q.loc[qm,['charging_queue_length','charging_estimated_wait_min']]=[qlen,round(wait,2)]
    else:
        active=int(q.loc[qm,'swap_active_service_count'].iloc[0]); svc=float(q.loc[qm,'swap_service_time_min'].iloc[0])
        if active<=0:
            active=max(1,int(ss.loc[sm,'occupied_swap_slots'].iloc[0]))
            q.loc[qm,'swap_active_service_count']=active
        add_wait=max(0.0,old_diff-TARGET_DIFF_MIN)
        qlen=int(round(add_wait*active/max(svc,1e-9)))
        qlen=max(1,qlen)
        wait=qlen*svc/active
        q.loc[qm,['swap_queue_length','swap_estimated_wait_min']]=[qlen,round(wait,2)]

    cm=cand.event_id.eq(eid)&cand.station_id.eq(a.station_id)
    cand.loc[cm,'queue_length']=qlen
    cand.loc[cm,'estimated_wait_min']=round(wait,2)
    rm=rank.event_id.eq(eid)&rank.station_id.eq(a.station_id)
    rank.loc[rm,'queue_wait_min']=round(wait,2)
    rank.loc[rm,'total_eta_min']=(rank.loc[rm,'traffic_adjusted_eta_min'].astype(float)+rank.loc[rm,'queue_wait_min'].astype(float)+rank.loc[rm,'service_time_min'].astype(float)).round(3)
    rank.loc[rm,'ranking_cost_label']=(rank.loc[rm,'total_eta_min'].astype(float)+0.25*rank.loc[rm,'detour_time_min'].astype(float)+0.002*rank.loc[rm,'detour_distance_m'].astype(float)-0.35*rank.loc[rm,'available_capacity'].clip(upper=6).astype(float)).round(4)

# Re-rank chosen event after patch.
g=rank[rank.event_id.eq(eid)].sort_values(['ranking_cost_label','station_id']).copy()
rank.loc[rank.event_id.eq(eid),'reference_rank']=0
rank.loc[rank.event_id.eq(eid),'is_reference_best']=False
for i,(idx,row) in enumerate(g.iterrows(),1):
    rank.loc[idx,'reference_rank']=i
    rank.loc[idx,'is_reference_best']=(i==1)

g=rank[rank.event_id.eq(eid)].sort_values(['ranking_cost_label','station_id'])
best=g.iloc[0]; second=g.iloc[1]
diff=float(second.ranking_cost_label-best.ranking_cost_label)
rm=rec.event_id.eq(eid)
rec.loc[rm,'reference_station_id']=best.station_id
rec.loc[rm,'has_recommendation']=True
rec.loc[rm,'label_method']='eligible_candidates_documented_baseline_cost_v3'

# Update replay queue payload for the changed state row.
rpm=replay.event_type.eq('QUEUE_UPDATE')&replay.entity_id.eq(a.station_id)&replay.timestamp.eq(state_ts)
if rpm.any():
    qr=q.loc[qm].iloc[0]
    payload={
        'charging_queue_length':int(qr.charging_queue_length),
        'charging_active_service_count':int(qr.charging_active_service_count),
        'charging_estimated_wait_min':float(qr.charging_estimated_wait_min),
        'swap_queue_length':int(qr.swap_queue_length),
        'swap_active_service_count':int(qr.swap_active_service_count),
        'swap_estimated_wait_min':float(qr.swap_estimated_wait_min),
    }
    replay.loc[rpm,'payload_json']=json.dumps(payload,separators=(',',':'))

m=sc.scenario_id.eq('NEAR_TIE_STATIONS')
sc.loc[m,'example_trip_id']=best.trip_id
sc.loc[m,'example_event_id']=eid
sc.loc[m,'validator_status']='PASS' if diff<=TARGET_MAX_DIFF_MIN else 'FAIL'
sc.loc[m,'primary_metric']='top2_ranking_cost_difference_min'
sc.loc[m,'primary_value']=round(diff,4)
sc.loc[m,'operator']='<='
sc.loc[m,'threshold']=TARGET_MAX_DIFF_MIN
sc.loc[m,'secondary_metric']='top2_stations'
sc.loc[m,'secondary_value']=f'{best.station_id},{second.station_id}'
sc.loc[m,'evidence_entity_a']=best.station_id
sc.loc[m,'evidence_entity_b']=second.station_id
sc.loc[m,'evidence_timestamp']=state_ts
sc.loc[m,'evidence_note']=f'input queue patched at service-specific state; service={service}'

q.to_csv(ROOT/'queue/queue_status.csv.gz',index=False,compression='gzip')
cand.to_csv(ROOT/'labels/candidate_labels.csv',index=False)
rank.to_csv(ROOT/'training/ranking_reference.csv',index=False)
rec.to_csv(ROOT/'labels/recommendation_labels.csv',index=False)
replay.to_csv(ROOT/'realtime/events.csv.gz',index=False,compression='gzip')
sc.to_csv(ROOT/'scenarios/scenario_coverage.csv',index=False)

print(json.dumps({'event_id':eid,'service_type':service,'top1':best.station_id,'top2':second.station_id,'old_diff_min':old_diff,'new_diff_min':diff,'state_timestamp':state_ts},indent=2))
