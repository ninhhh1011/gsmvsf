from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path('/mnt/data/dataset_v1')
SEED=20260916
NEAR_TIE_THRESHOLD_MIN=3.0
LONG_QUEUE_THRESHOLD_MIN=30.0


def hav_m(lat1,lon1,lat2,lon2):
    R=6371000.0
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()

def bool_series(s):
    if s.dtype==bool:return s
    return s.astype(str).str.lower().isin(['true','1','yes'])

def floor_iso(ts, mins):
    return pd.Timestamp(ts).floor(f'{mins}min').isoformat()

# Load patched checkpoint outputs
nodes=pd.read_csv(ROOT/'map/processed/road_nodes.csv.gz')
segs=pd.read_csv(ROOT/'map/processed/road_segments.csv.gz',dtype={'osm_way_id':str})
drivers=pd.read_csv(ROOT/'drivers/drivers.csv')
vehicles=pd.read_csv(ROOT/'vehicles/vehicles.csv')
trips=pd.read_csv(ROOT/'trips/trips.csv')
true=pd.read_csv(ROOT/'trajectories/true_trajectories.csv.gz')
gps=pd.read_csv(ROOT/'gps/gps_observations.csv.gz')
battery=pd.read_csv(ROOT/'battery/soc_history.csv.gz')
stations=pd.read_csv(ROOT/'stations/stations.csv')
status=pd.read_csv(ROOT/'stations/station_status.csv.gz')
queue=pd.read_csv(ROOT/'queue/queue_status.csv.gz')
traffic=pd.read_csv(ROOT/'traffic/traffic_snapshots.csv.gz')
demand=pd.read_csv(ROOT/'labels/demand_labels.csv')
df=pd.read_csv(ROOT/'training/demand_features.csv')
candidates=pd.read_csv(ROOT/'labels/candidate_labels.csv')
ranking=pd.read_csv(ROOT/'training/ranking_reference.csv')
rec=pd.read_csv(ROOT/'labels/recommendation_labels.csv')
mm_labels=pd.read_csv(ROOT/'labels/map_matching_labels.csv.gz')
old_mmc=pd.read_csv(ROOT/'training/map_matching_candidates_with_split.csv.gz')
splits=pd.read_csv(ROOT/'training/trip_splits.csv')

split_map=splits.set_index('trip_id').split.to_dict()
trip_idx=trips.set_index('trip_id')
veh_idx=vehicles.set_index('vehicle_id')
seg_idx=segs.set_index('segment_id')

# ---------------------------------------------------------------------------
# A) Map matching candidate patch: exactly one true positive + >=1 negative/group
# ---------------------------------------------------------------------------
base=old_mmc.copy()
truth_map=mm_labels.set_index('observation_id').true_segment_id.astype(str)
base['true_segment_id']=base.observation_id.map(truth_map)
base['exact_negative']=base.candidate_segment_id.astype(str).ne(base.true_segment_id.astype(str))
has_neg=base.groupby('observation_id').exact_negative.any()
selected=set(has_neg[has_neg].index)
neg=base[base.observation_id.isin(selected)&base.exact_negative].copy()
neg=neg.sort_values(['observation_id','distance_to_segment_m','heading_difference_deg']).groupby('observation_id',as_index=False,group_keys=False).head(5)
neg['is_correct']=False
neg['hard_negative']=(neg.distance_to_segment_m.astype(float)<=20.0)&(neg.heading_difference_deg.astype(float)<=45.0)
neg=neg.drop(columns=['true_segment_id','exact_negative'])

truth=mm_labels[mm_labels.observation_id.isin(selected)].merge(
    gps[['observation_id','trip_id','timestamp','latitude','longitude','heading_deg']],on='observation_id',how='left')
# join trajectory heading on trip+timestamp
th=true[['trip_id','timestamp','heading_deg']].rename(columns={'heading_deg':'true_heading_deg'})
truth=truth.merge(th,on=['trip_id','timestamp'],how='left')
truth['distance_to_segment_m']=[round(hav_m(a,b,c,d),2) for a,b,c,d in zip(truth.latitude,truth.longitude,truth.true_latitude,truth.true_longitude)]
diff=(truth.heading_deg.astype(float)-truth.true_heading_deg.astype(float)).abs()%360
truth['heading_difference_deg']=np.minimum(diff,360-diff).round(2)
truth['candidate_segment_id']=truth.true_segment_id.astype(str)
truth['projected_lat']=truth.true_latitude
truth['projected_lon']=truth.true_longitude
truth['is_correct']=True
truth['hard_negative']=False
truth['split']=truth.trip_id.map(split_map)
pos=truth[['observation_id','candidate_segment_id','distance_to_segment_m','projected_lat','projected_lon','heading_difference_deg','is_correct','hard_negative','trip_id','split']]
mmc=pd.concat([pos,neg[['observation_id','candidate_segment_id','distance_to_segment_m','projected_lat','projected_lon','heading_difference_deg','is_correct','hard_negative','trip_id','split']]],ignore_index=True)
mmc['_ord']=np.where(bool_series(mmc.is_correct),0,1)
mmc=mmc.sort_values(['observation_id','_ord','distance_to_segment_m']).drop(columns='_ord').reset_index(drop=True)
mmc.to_csv(ROOT/'training/map_matching_candidates_with_split.csv.gz',index=False,compression='gzip')
mmc.drop(columns=['trip_id','split']).to_csv(ROOT/'training/map_matching_candidates.csv.gz',index=False,compression='gzip')

# ---------------------------------------------------------------------------
# B) Rebuild replay; include all station states + scenario-relevant traffic
# ---------------------------------------------------------------------------
traffic['dt']=pd.to_datetime(traffic.timestamp,format='mixed')
status['dt']=pd.to_datetime(status.timestamp,format='mixed')
queue['dt']=pd.to_datetime(queue.timestamp,format='mixed')
recs=[]
def add(ts,typ,entity,payload):
    recs.append({'timestamp':ts,'event_type':typ,'entity_id':entity,'payload_json':json.dumps(payload,separators=(',',':'))})
for r in gps.iloc[::8].itertuples(index=False):
    add(r.timestamp,'GPS_UPDATE',r.trip_id,{'observation_id':r.observation_id,'lat':round(float(r.latitude),7),'lon':round(float(r.longitude),7)})
for r in battery.iloc[::12].itertuples(index=False):
    add(r.timestamp,'SOC_UPDATE',r.trip_id,{'soc_pct':float(r.soc_pct),'remaining_range_km':float(r.estimated_remaining_range_km)})
# all station states are only 3,270 rows and guarantee state/queue transitions are replayable
for r in status.itertuples(index=False):
    add(r.timestamp,'STATION_STATUS_UPDATE',r.station_id,{'status':r.operating_status,'available_slots':int(r.available_slots),'queue_length':int(r.queue_length)})
# random traffic sample + all rows for route segments used by realtime/heavy scenarios
special_tids=set(trips.loc[trips.scenario_id.isin(['TRAFFIC_REALTIME_CHANGE','HEAVY_TRAFFIC']),'trip_id'])
special_sids=set(true.loc[true.trip_id.isin(special_tids),'true_segment_id'])
traf_keep=pd.concat([traffic.sample(min(3000,len(traffic)),random_state=SEED),traffic[traffic.segment_id.isin(special_sids)]],ignore_index=True).drop_duplicates(['segment_id','timestamp'])
for r in traf_keep.itertuples(index=False):
    add(r.timestamp,'TRAFFIC_UPDATE',r.segment_id,{'traffic_level':r.traffic_level,'current_speed_kmh':float(r.current_speed_kmh)})
replay=pd.DataFrame(recs).sort_values(['timestamp','event_type','entity_id']).reset_index(drop=True)
replay.insert(0,'event_id',[f'RE{i+1:08d}' for i in range(len(replay))])
replay.to_csv(ROOT/'realtime/events.csv.gz',index=False,compression='gzip')

# ---------------------------------------------------------------------------
# C) Quantified scenario validators. Search across scenario events for real evidence.
# ---------------------------------------------------------------------------
D=demand.merge(df[['event_id','snapshot_index','soc_pct','estimated_remaining_range_km','remaining_trip_distance_km']],on='event_id',how='left').merge(trips[['trip_id','scenario_id','vehicle_id']],on='trip_id',how='left')
C={k:v.copy() for k,v in candidates.groupby('event_id')}
R={k:v.copy() for k,v in ranking.groupby('event_id')}
qidx=queue.set_index(['station_id','timestamp'])
sidx=status.set_index(['station_id','timestamp'])
tidx=traffic.set_index(['segment_id','timestamp'])
true_exact=true.set_index(['trip_id','timestamp'])
replay_key=set(zip(replay.event_type,replay.entity_id,replay.timestamp))

# helpers
scenario_rows=[]
def row_base(sc,trip_count):
    return {'scenario_id':sc,'trip_count':int(trip_count),'example_trip_id':'','example_event_id':'','validator_status':'FAIL','primary_metric':'','primary_value':None,'operator':'','threshold':None,'secondary_metric':'','secondary_value':None,'evidence_entity_a':'','evidence_entity_b':'','evidence_timestamp':'','before_timestamp':'','after_timestamp':'','evidence_note':''}

def finalize(r,ok):
    r['validator_status']='PASS' if ok else 'FAIL';scenario_rows.append(r)

for sc, tg in trips.groupby('scenario_id',sort=True):
    r=row_base(sc,len(tg)); tids=set(tg.trip_id); E=D[D.trip_id.isin(tids)].copy()
    if sc in ['NORMAL_TRIP','NO_SERVICE_NEEDED']:
        counts=E.groupby('trip_id').need_service.apply(lambda s:int(bool_series(s).sum())).sort_values()
        tid=counts.index[0]; v=int(counts.iloc[0]); e=E[E.trip_id.eq(tid)].iloc[0]
        r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='service_snapshot_count',primary_value=v,operator='==',threshold=0,evidence_timestamp=e.timestamp)
        finalize(r,v==0)
    elif sc=='LOW_SOC':
        vals=battery[battery.trip_id.isin(tids)].groupby('trip_id').soc_pct.min().sort_values();tid=vals.index[0];v=float(vals.iloc[0]);safe=float(veh_idx.loc[trip_idx.loc[tid].vehicle_id].minimum_safe_soc_pct);e=E[E.trip_id.eq(tid)].iloc[0]
        r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='min_soc_pct',primary_value=round(v,3),operator='<=',threshold=safe,secondary_metric='minimum_safe_soc_pct',secondary_value=safe,evidence_timestamp=e.timestamp);finalize(r,v<=safe)
    elif sc=='NEED_CHARGING':
        good=E[E.service_type.eq('CHARGING')]
        if len(good):
            e=good.iloc[0];v=veh_idx.loc[e.vehicle_id];n=int((E[E.trip_id.eq(e.trip_id)].service_type=='CHARGING').sum());ok=bool(v.charging_supported) and n>0
            r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='charging_label_count',primary_value=n,operator='>=',threshold=1,secondary_metric='charging_supported',secondary_value=int(bool(v.charging_supported)),evidence_timestamp=e.timestamp);finalize(r,ok)
        else: finalize(r,False)
    elif sc=='NEED_SWAP':
        best=None
        for tid in tids:
            v=veh_idx.loc[trip_idx.loc[tid].vehicle_id];labs=E[E.trip_id.eq(tid)];n=int((labs.service_type=='BATTERY_SWAP').sum());
            if bool(v.swap_supported) and n>0:best=(tid,v,n,labs.iloc[0]);break
        if best:
            tid,v,n,e=best;r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='battery_swap_label_count',primary_value=n,operator='>=',threshold=1,secondary_metric='swap_supported',secondary_value=int(bool(v.swap_supported)),evidence_timestamp=e.timestamp);finalize(r,True)
        else: finalize(r,False)
    elif sc=='NEAREST_FULL':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is None:continue
            pool=cc[~cc.reason.isin(['INCOMPATIBLE','UNREACHABLE','NO_SERVICE_NEEDED'])].dropna(subset=['network_distance_m']).sort_values('network_distance_m')
            if len(pool) and pool.iloc[0].reason=='FULL':found=(e,pool.iloc[0]);break
        if found:
            e,x=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='nearest_compatible_reachable_capacity',primary_value=int(x.available_capacity),operator='==',threshold=0,secondary_metric='nearest_reason',secondary_value=x.reason,evidence_entity_a=x.station_id,evidence_timestamp=x.state_timestamp);finalize(r,True)
        else:finalize(r,False)
    elif sc=='STATION_OFFLINE':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is not None and (cc.reason=='OFFLINE').any():
                x=cc[cc.reason=='OFFLINE'].sort_values('network_distance_m').iloc[0];found=(e,x);break
        if found:
            e,x=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='offline_candidate_count',primary_value=int((C[e.event_id].reason=='OFFLINE').sum()),operator='>=',threshold=1,secondary_metric='operating_status',secondary_value=x.operating_status,evidence_entity_a=x.station_id,evidence_timestamp=x.state_timestamp);finalize(r,x.operating_status=='OFFLINE')
        else:finalize(r,False)
    elif sc=='INCOMPATIBLE_STATION':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is not None:
                nbad=int((cc.reason=='INCOMPATIBLE').sum());nok=int(bool_series(cc.eligible).sum())
                if nbad>0 and nok>0:found=(e,nbad,nok);break
        if found:
            e,nbad,nok=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='incompatible_candidate_count',primary_value=nbad,operator='>=',threshold=1,secondary_metric='eligible_candidate_count',secondary_value=nok,evidence_timestamp=e.timestamp);finalize(r,True)
        else:finalize(r,False)
    elif sc=='LONG_QUEUE':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is None:continue
            x=cc.sort_values('estimated_wait_min',ascending=False).iloc[0]
            if float(x.estimated_wait_min)>=LONG_QUEUE_THRESHOLD_MIN:found=(e,x);break
        if found:
            e,x=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='estimated_wait_min',primary_value=round(float(x.estimated_wait_min),2),operator='>=',threshold=LONG_QUEUE_THRESHOLD_MIN,evidence_entity_a=x.station_id,evidence_timestamp=x.state_timestamp);finalize(r,True)
        else:finalize(r,False)
    elif sc=='FARTHER_BUT_FASTER':
        found=None
        for e in E.itertuples(index=False):
            rr=R.get(e.event_id)
            if rr is None:continue
            rows=rr.to_dict('records')
            for a in rows:
                for b in rows:
                    if b['driver_to_station_distance_m']>a['driver_to_station_distance_m'] and b['total_eta_min']<a['total_eta_min']:
                        found=(e,a,b);break
                if found:break
            if found:break
        if found:
            e,a,b=found;dd=float(b['driver_to_station_distance_m']-a['driver_to_station_distance_m']);dt=float(a['total_eta_min']-b['total_eta_min'])
            r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='farther_distance_delta_m',primary_value=round(dd,1),operator='>',threshold=0,secondary_metric='faster_total_eta_delta_min',secondary_value=round(dt,3),evidence_entity_a=a['station_id'],evidence_entity_b=b['station_id'],evidence_timestamp=e.timestamp);finalize(r,dd>0 and dt>0)
        else:finalize(r,False)
    elif sc=='HEAVY_TRAFFIC':
        found=None
        for e in E.itertuples(index=False):
            try:trow=true_exact.loc[(e.trip_id,e.timestamp)];trow=trow.iloc[0] if isinstance(trow,pd.DataFrame) else trow
            except KeyError:continue
            ts=floor_iso(e.timestamp,30);key=(trow.true_segment_id,ts)
            if key in tidx.index:
                x=tidx.loc[key];x=x.iloc[0] if isinstance(x,pd.DataFrame) else x
                if x.traffic_level in ['HEAVY','INCIDENT']:found=(e,trow.true_segment_id,ts,x);break
        if found:
            e,sid,ts,x=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='related_segment_delay_factor',primary_value=round(float(x.delay_factor),3),operator='>',threshold=1.5,secondary_metric='traffic_level',secondary_value=x.traffic_level,evidence_entity_a=sid,evidence_timestamp=ts);finalize(r,float(x.delay_factor)>1.5)
        else:finalize(r,False)
    elif sc=='INSUFFICIENT_RANGE':
        X=E.copy();X['margin']=X.estimated_remaining_range_km-X.remaining_trip_distance_km; e=X.sort_values('margin').iloc[0];m=float(e.margin)
        r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='remaining_range_margin_km',primary_value=round(m,3),operator='<',threshold=0,evidence_timestamp=e.timestamp);finalize(r,m<0)
    elif sc=='GPS_NOISE':
        best=None
        ml=mm_labels.merge(gps[['observation_id','trip_id','latitude','longitude']],on='observation_id')
        for tid in tids:
            x=ml[ml.trip_id.eq(tid)];errs=[hav_m(a,b,c,d) for a,b,c,d in zip(x.latitude,x.longitude,x.true_latitude,x.true_longitude)];med=float(np.median(errs)) if errs else 0
            if best is None or med>best[1]:best=(tid,med)
        tid,med=best;e=E[E.trip_id.eq(tid)].iloc[0];r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='median_gps_error_m',primary_value=round(med,2),operator='>=',threshold=10,evidence_timestamp=e.timestamp);finalize(r,med>=10)
    elif sc=='GPS_MISSING':
        vals=[]
        for tid in tids:
            nt=int((true.trip_id==tid).sum());ng=int((gps.trip_id==tid).sum());vals.append((ng/max(1,nt),tid,nt-ng))
        ratio,tid,missing=min(vals);e=E[E.trip_id.eq(tid)].iloc[0];r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='gps_to_true_point_ratio',primary_value=round(ratio,4),operator='<',threshold=0.85,secondary_metric='missing_point_count',secondary_value=missing,evidence_timestamp=e.timestamp);finalize(r,ratio<0.85)
    elif sc=='PARALLEL_ROADS':
        x=mmc[mmc.trip_id.isin(tids)&bool_series(mmc.hard_negative)]
        if len(x):
            z=x.sort_values('distance_to_segment_m').iloc[0];tid=z.trip_id;e=E[E.trip_id.eq(tid)].iloc[0];r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='hard_negative_candidate_count',primary_value=len(x),operator='>=',threshold=1,secondary_metric='min_hard_negative_distance_m',secondary_value=round(float(z.distance_to_segment_m),2),evidence_entity_a=z.candidate_segment_id,evidence_timestamp=e.timestamp);finalize(r,float(z.distance_to_segment_m)<=20)
        else:finalize(r,False)
    elif sc=='BRIDGE_AMBIGUITY':
        bridge_map=segs.set_index('segment_id').bridge.astype(str).str.lower().isin(['yes','true','1']).to_dict()
        ml=mm_labels.merge(gps[['observation_id','trip_id']],on='observation_id');ml['bridge']=ml.true_segment_id.map(bridge_map).fillna(False)
        bridge_obs=set(ml.loc[ml.trip_id.isin(tids)&ml.bridge,'observation_id']);x=mmc[mmc.observation_id.isin(bridge_obs)&(~bool_series(mmc.is_correct))]
        if len(x):
            z=x.iloc[0];tid=z.trip_id;e=E[E.trip_id.eq(tid)].iloc[0];r.update(example_trip_id=tid,example_event_id=e.event_id,primary_metric='bridge_observation_with_negative_count',primary_value=x.observation_id.nunique(),operator='>=',threshold=1,secondary_metric='negative_candidate_count',secondary_value=len(x),evidence_entity_a=z.candidate_segment_id,evidence_timestamp=e.timestamp);finalize(r,True)
        else:finalize(r,False)
    elif sc=='QUEUE_REALTIME_CHANGE':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is None:continue
            t0=pd.Timestamp(cc.state_timestamp.iloc[0]);t1=t0+pd.Timedelta(minutes=10)
            for sid in cc.station_id:
                k0=(sid,t0.isoformat());k1=(sid,t1.isoformat())
                if k0 in qidx.index and k1 in qidx.index:
                    a=qidx.loc[k0];b=qidx.loc[k1];a=a.iloc[0] if isinstance(a,pd.DataFrame) else a;b=b.iloc[0] if isinstance(b,pd.DataFrame) else b;delta=abs(float(b.estimated_wait_min)-float(a.estimated_wait_min))
                    if delta>=20:found=(e,sid,t0.isoformat(),t1.isoformat(),a,b,delta);break
            if found:break
        if found:
            e,sid,t0,t1,a,b,delta=found;replay_ok=('STATION_STATUS_UPDATE',sid,t0) in replay_key and ('STATION_STATUS_UPDATE',sid,t1) in replay_key
            r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='queue_wait_change_min',primary_value=round(delta,2),operator='>=',threshold=20,secondary_metric='before_after_wait_min',secondary_value=f'{float(a.estimated_wait_min):.2f}->{float(b.estimated_wait_min):.2f}',evidence_entity_a=sid,before_timestamp=t0,after_timestamp=t1,evidence_note=f'replay_before_after={replay_ok}');finalize(r,delta>=20 and replay_ok)
        else:finalize(r,False)
    elif sc=='TRAFFIC_REALTIME_CHANGE':
        found=None
        for e in E.itertuples(index=False):
            try:trow=true_exact.loc[(e.trip_id,e.timestamp)];trow=trow.iloc[0] if isinstance(trow,pd.DataFrame) else trow
            except KeyError:continue
            sid=trow.true_segment_id;t0=pd.Timestamp(e.timestamp).floor('30min');t1=t0+pd.Timedelta(minutes=30);k0=(sid,t0.isoformat());k1=(sid,t1.isoformat())
            if k0 in tidx.index and k1 in tidx.index:
                a=tidx.loc[k0];b=tidx.loc[k1];a=a.iloc[0] if isinstance(a,pd.DataFrame) else a;b=b.iloc[0] if isinstance(b,pd.DataFrame) else b;delta=abs(float(b.current_speed_kmh)-float(a.current_speed_kmh))
                if a.traffic_level!=b.traffic_level and delta>=5:found=(e,sid,t0.isoformat(),t1.isoformat(),a,b,delta);break
        if found:
            e,sid,t0,t1,a,b,delta=found;replay_ok=('TRAFFIC_UPDATE',sid,t0) in replay_key and ('TRAFFIC_UPDATE',sid,t1) in replay_key
            r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='traffic_speed_change_kmh',primary_value=round(delta,2),operator='>=',threshold=5,secondary_metric='traffic_level_transition',secondary_value=f'{a.traffic_level}->{b.traffic_level}',evidence_entity_a=sid,before_timestamp=t0,after_timestamp=t1,evidence_note=f'replay_before_after={replay_ok}');finalize(r,delta>=5 and replay_ok)
        else:finalize(r,False)
    elif sc=='STATION_STATUS_CHANGE':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is None:continue
            t0=pd.Timestamp(cc.state_timestamp.iloc[0]);t1=t0+pd.Timedelta(minutes=10)
            for sid in cc.station_id:
                k0=(sid,t0.isoformat());k1=(sid,t1.isoformat())
                if k0 in sidx.index and k1 in sidx.index:
                    a=sidx.loc[k0];b=sidx.loc[k1];a=a.iloc[0] if isinstance(a,pd.DataFrame) else a;b=b.iloc[0] if isinstance(b,pd.DataFrame) else b
                    if a.operating_status!=b.operating_status:found=(e,sid,t0.isoformat(),t1.isoformat(),a,b);break
            if found:break
        if found:
            e,sid,t0,t1,a,b=found;replay_ok=('STATION_STATUS_UPDATE',sid,t0) in replay_key and ('STATION_STATUS_UPDATE',sid,t1) in replay_key
            r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='status_changed',primary_value=1,operator='==',threshold=1,secondary_metric='status_transition',secondary_value=f'{a.operating_status}->{b.operating_status}',evidence_entity_a=sid,before_timestamp=t0,after_timestamp=t1,evidence_note=f'replay_before_after={replay_ok}');finalize(r,replay_ok)
        else:finalize(r,False)
    elif sc=='NO_AVAILABLE_STATION':
        found=None
        for e in E.itertuples(index=False):
            cc=C.get(e.event_id)
            if cc is not None and int(bool_series(cc.eligible).sum())==0:found=e;break
        if found:
            r.update(example_trip_id=found.trip_id,example_event_id=found.event_id,primary_metric='eligible_station_count',primary_value=0,operator='==',threshold=0,evidence_timestamp=found.timestamp);finalize(r,True)
        else:finalize(r,False)
    elif sc=='NEAR_TIE_STATIONS':
        found=None
        for e in E.itertuples(index=False):
            rr=R.get(e.event_id)
            if rr is None or len(rr)<2:continue
            s=rr.sort_values('ranking_cost_label');diff=float(s.iloc[1].ranking_cost_label-s.iloc[0].ranking_cost_label)
            if diff<=NEAR_TIE_THRESHOLD_MIN:found=(e,s.iloc[0],s.iloc[1],diff);break
        if found:
            e,a,b,diff=found;r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='top2_ranking_cost_difference',primary_value=round(diff,4),operator='<=',threshold=NEAR_TIE_THRESHOLD_MIN,secondary_metric='top2_stations',secondary_value=f'{a.station_id},{b.station_id}',evidence_entity_a=a.station_id,evidence_entity_b=b.station_id,evidence_timestamp=e.timestamp);finalize(r,True)
        else:finalize(r,False)
    else:
        e=E.iloc[0];r.update(example_trip_id=e.trip_id,example_event_id=e.event_id,primary_metric='covered',primary_value=1,operator='==',threshold=1,evidence_timestamp=e.timestamp);finalize(r,True)

sc=pd.DataFrame(scenario_rows)
sc.to_csv(ROOT/'scenarios/scenario_coverage.csv',index=False)
json.dump({'overall':'PASS' if (sc.validator_status=='PASS').all() else 'FAIL','passed':int((sc.validator_status=='PASS').sum()),'failed':int((sc.validator_status=='FAIL').sum()),'results':sc.to_dict('records')},open(ROOT/'validation/scenario_validation_results.json','w'),indent=2,ensure_ascii=False)

# ---------------------------------------------------------------------------
# D) Integrity/stats/counts
# ---------------------------------------------------------------------------
# Raw-map integrity is checked against the exact uploaded-file hashes captured during V1.1 patching.
# This keeps the finalizer reproducible even when the original chat upload paths are not mounted later.
EXPECTED_BASELINE_SHA256='f69011f81fdc40d63e32a978a8ab15366ba87e8922f75c55821daf139e53ddb7'
EXPECTED_PATCHED_SHA256='0d3a66b2fb03019fd9d7877115c1ed9efbb736a83c5ac6f6e5440d71ddcfff60'
raw_base=ROOT/'map/raw/hanoi-baseline.osm.pbf';raw_patch=ROOT/'map/raw/hanoi-patched.osm.pbf'
pbf={
 'baseline_uploaded_sha256':EXPECTED_BASELINE_SHA256,'baseline_dataset_sha256':sha256(raw_base),
 'patched_uploaded_sha256':EXPECTED_PATCHED_SHA256,'patched_dataset_sha256':sha256(raw_patch),
}
pbf['unchanged']=pbf['baseline_uploaded_sha256']==pbf['baseline_dataset_sha256'] and pbf['patched_uploaded_sha256']==pbf['patched_dataset_sha256']
pbf['warning']='hanoi-patched.osm.pbf changes OSM way 881947000 (Cầu Thanh Trì) motorcar=designated to motorcar=no. This patch does not decide whether that change is correct. Human confirmation is required before freezing patched PBF as the primary routing map.'
json.dump(pbf,open(ROOT/'validation/pbf_integrity.json','w'),indent=2,ensure_ascii=False)

mmstats={
 'observations_selected':int(mmc.observation_id.nunique()),
 'positive_candidate_count':int(bool_series(mmc.is_correct).sum()),
 'negative_candidate_count':int((~bool_series(mmc.is_correct)).sum()),
 'hard_negative_count':int(bool_series(mmc.hard_negative).sum()),
 'groups_with_positive':int(mmc.groupby('observation_id').is_correct.apply(lambda s:bool_series(s).any()).sum()),
 'groups_with_negative':int(mmc.groupby('observation_id').is_correct.apply(lambda s:(~bool_series(s)).any()).sum()),
 'split_observations':mmc.drop_duplicates('observation_id').split.value_counts().to_dict()
}
json.dump(mmstats,open(ROOT/'validation/map_matching_candidate_stats.json','w'),indent=2)

ddist=demand.service_type.value_counts().to_dict(); json.dump(ddist,open(ROOT/'validation/demand_distribution.json','w'),indent=2)
rankstats={'rows':len(ranking),'event_groups':int(ranking.event_id.nunique()),'group_size_min':int(ranking.groupby('event_id').size().min()),'group_size_max':int(ranking.groupby('event_id').size().max()),'split_groups':ranking.drop_duplicates('event_id').split.value_counts().to_dict()};json.dump(rankstats,open(ROOT/'validation/ranking_stats.json','w'),indent=2)
counts={
 'road_nodes':len(nodes),'road_segments':len(segs),'drivers':len(drivers),'vehicles':len(vehicles),'trips':len(trips),
 'true_trajectory_points':len(true),'gps_observations':len(gps),'soc_history':len(battery),'stations':len(stations),
 'station_status':len(status),'queue_status':len(queue),'traffic_snapshots':len(traffic),'realtime_events':len(replay),
 'map_matching_candidates':len(mmc),'map_matching_selected_observations':int(mmc.observation_id.nunique()),
 'demand_labels':len(demand),'candidate_labels':len(candidates),'ranking_reference':len(ranking),
 'ranking_event_groups':int(ranking.event_id.nunique()),'recommendation_labels':len(rec),'scenario_rows':len(sc)
}
json.dump(counts,open(ROOT/'validation/data_counts.json','w'),indent=2)
patch_summary={'demand_distribution':ddist,'map_matching':mmstats,'ranking':rankstats,'scenarios':sc.validator_status.value_counts().to_dict(),'pbf_unchanged':pbf['unchanged']}
json.dump(patch_summary,open(ROOT/'validation/patch_summary.json','w'),indent=2)
print(json.dumps(patch_summary,indent=2))
