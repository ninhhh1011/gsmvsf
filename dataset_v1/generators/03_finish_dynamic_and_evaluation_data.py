import json,math,random,heapq,re
from pathlib import Path
import pandas as pd, numpy as np
ROOT=Path('/mnt/data/dataset_v1');SEED=20260916;rng=random.Random(SEED)
segs=pd.read_csv(ROOT/'map/processed/road_segments.csv.gz');nodes=pd.read_csv(ROOT/'map/processed/road_nodes.csv.gz');trips=pd.read_csv(ROOT/'trips/trips.csv');true=pd.read_csv(ROOT/'trajectories/true_trajectories.csv.gz');gps=pd.read_csv(ROOT/'gps/gps_observations.csv.gz');battery=pd.read_csv(ROOT/'battery/soc_history.csv.gz');stations=pd.read_csv(ROOT/'stations/stations.csv');status=pd.read_csv(ROOT/'stations/station_status.csv.gz');qdf=pd.read_csv(ROOT/'queue/queue_status.csv.gz');vehicles=pd.read_csv(ROOT/'vehicles/vehicles.csv');demand=pd.read_csv(ROOT/'labels/demand_labels.csv')
coord=nodes.set_index('node_id')[['latitude','longitude']].to_dict('index');edge=segs.set_index('segment_id').to_dict('index');veh=vehicles.set_index('vehicle_id');usable=segs[~segs.access.astype(str).str.lower().isin(['no','private'])]
adj={}
for r in usable.itertuples():adj.setdefault(r.from_node_id,[]).append((r.to_node_id,r.segment_id,float(r.length_m)))
start0=pd.Timestamp('2026-09-01T06:00:00+07:00')
# Traffic: all trajectory segments + sampled major, compact 30-min snapshots
route_sids=list(set(true.true_segment_id));major=usable[usable.road_type.isin(['motorway','trunk','primary','secondary'])];extra=list(major.sample(min(800,len(major)),random_state=SEED).segment_id);sids=list(dict.fromkeys(route_sids+extra));rows=[]
for k in range(37):
 ts=start0+pd.Timedelta(minutes=30*k);peak=ts.hour in [7,8,17,18]
 for sid in sids:
  sr=edge[sid];ff=float(sr['maxspeed_kmh']);u=(abs(hash((sid,k,SEED)))%10000)/10000;fac=(.35+.30*u) if peak else (.75+.25*u);inc=(abs(hash(('inc',sid,k)))%997==0)
  if inc:fac*=.35;level='INCIDENT'
  elif fac<.5:level='HEAVY'
  elif fac<.8:level='MODERATE'
  else:level='FREE_FLOW'
  cur=max(5,ff*fac);rows.append((sid,ts.isoformat(),level,ff,round(cur,2),round(ff/cur,3)))
traffic=pd.DataFrame(rows,columns=['segment_id','timestamp','traffic_level','free_flow_speed_kmh','current_speed_kmh','delay_factor']);traffic.to_csv(ROOT/'traffic/traffic_snapshots.csv.gz',index=False,compression='gzip')
# Eligibility labels for every demand event, and compact ranking reference based on network shortest paths for first 12 service events
def dijkstra_targets(source, targets, limit=22000):
 tset=set(targets);dist={source:0.0};pq=[(0.0,source)];found={}
 while pq and len(found)<len(tset):
  d,u=heapq.heappop(pq)
  if d!=dist.get(u):continue
  if d>limit:break
  if u in tset:found[u]=d
  for v,sid,w in adj.get(u,[]):
   nd=d+w
   if nd<dist.get(v,1e100) and nd<=limit:dist[v]=nd;heapq.heappush(pq,(nd,v))
 return found
station_nodes=list(stations.access_node_id); cand=[];rank=[];rec=[]
trip_lookup=trips.set_index('trip_id');bg={k:v.reset_index(drop=True) for k,v in battery.groupby('trip_id')};tg={k:v.reset_index(drop=True) for k,v in true.groupby('trip_id')}
service_events=demand[demand.need_service==True]
for ev in demand.itertuples():
 tr=trip_lookup.loc[ev.trip_id];v=veh.loc[tr.vehicle_id]
 for s in stations.itertuples():
  compatible=(v.vehicle_type in s.supported_vehicle_type and ((ev.service_type=='CHARGING' and 'CHARGING' in s.station_type) or (ev.service_type=='BATTERY_SWAP' and 'SWAP' in s.station_type))) if ev.need_service else False
  cand.append({'event_id':ev.event_id,'station_id':s.station_id,'eligible':bool(compatible),'reason':'ELIGIBLE_COMPATIBILITY' if compatible else ('NO_SERVICE_NEEDED' if not ev.need_service else 'INCOMPATIBLE')})
for ev in service_events.head(12).itertuples():
 tr=trip_lookup.loc[ev.trip_id];v=veh.loc[tr.vehicle_id];td=tg[ev.trip_id];rr=td.iloc[int(len(td)*.6)];source=edge[rr.true_segment_id]['from_node_id'];dmap=dijkstra_targets(source,station_nodes);eligible=[]
 for s in stations.itertuples():
  compatible=v.vehicle_type in s.supported_vehicle_type and ((ev.service_type=='CHARGING' and 'CHARGING' in s.station_type) or (ev.service_type=='BATTERY_SWAP' and 'SWAP' in s.station_type))
  if compatible and s.access_node_id in dmap:eligible.append((dmap[s.access_node_id],s))
 scored=[]
 for d,s in sorted(eligible,key=lambda x:x[0])[:5]:
  es=pd.Timestamp(ev.timestamp);k=max(0,min(108,round((es-start0).total_seconds()/600)));st=status[status.station_id==s.station_id].iloc[k];qq=qdf[qdf.station_id==s.station_id].iloc[k];b=bg[ev.trip_id].iloc[int(len(bg[ev.trip_id])*.6)];eta=d/1000/30*60;feas=d/1000<=b.estimated_remaining_range_km;cost=eta+qq.estimated_wait_min+(1000 if not feas else 0)+(1000 if st.operating_status!='OPEN' else 0)
  rank.append({'event_id':ev.event_id,'station_id':s.station_id,'route_distance_m_ref':round(d,1),'eta_min_ref':round(eta,2),'queue_wait_min':qq.estimated_wait_min,'available_slots':int(st.available_slots),'operating_status':st.operating_status,'soc_feasible':bool(feas),'ranking_cost_label':round(cost,3)});scored.append((cost,s.station_id))
 if scored:rec.append({'event_id':ev.event_id,'reference_station_id':min(scored)[1],'label_method':'minimum_reference_cost(network_distance+queue+feasibility+status)'})
pd.DataFrame(cand).to_csv(ROOT/'labels/candidate_labels.csv',index=False);pd.DataFrame(rank).to_csv(ROOT/'training/ranking_reference.csv',index=False);pd.DataFrame(rec).to_csv(ROOT/'labels/recommendation_labels.csv',index=False)
# realtime replay compact
recs=[]
def add(ts,typ,eid,p):recs.append((ts,typ,eid,json.dumps(p,separators=(',',':'))))
for r in gps.iloc[::8].itertuples():add(r.timestamp,'GPS_UPDATE',r.trip_id,{'observation_id':r.observation_id,'lat':round(r.latitude,7),'lon':round(r.longitude,7)})
for r in battery.iloc[::12].itertuples():add(r.timestamp,'SOC_UPDATE',r.trip_id,{'soc_pct':r.soc_pct,'remaining_range_km':r.estimated_remaining_range_km})
for r in status.iloc[::4].itertuples():add(r.timestamp,'STATION_STATUS_UPDATE',r.station_id,{'status':r.operating_status,'available_slots':int(r.available_slots),'queue_length':int(r.queue_length)})
for r in traffic.sample(min(3000,len(traffic)),random_state=SEED).itertuples():add(r.timestamp,'TRAFFIC_UPDATE',r.segment_id,{'traffic_level':r.traffic_level,'current_speed_kmh':r.current_speed_kmh})
replay=pd.DataFrame(recs,columns=['timestamp','event_type','entity_id','payload_json']).sort_values('timestamp').reset_index(drop=True);replay.insert(0,'event_id',[f'RE{i+1:08d}' for i in range(len(replay))]);replay.to_csv(ROOT/'realtime/events.csv.gz',index=False,compression='gzip')
# scenarios actual evidence
sc=trips.groupby('scenario_id').agg(trip_count=('trip_id','count'),example_trip_id=('trip_id','first')).reset_index();sc['data_evidence']='trip + road-network trajectory + GPS + SOC + temporal station/queue/traffic + replay';sc.to_csv(ROOT/'scenarios/scenario_coverage.csv',index=False)
counts={'road_nodes':len(nodes),'road_segments':len(segs),'drivers':60,'vehicles':60,'trips':len(trips),'true_trajectory_points':len(true),'gps_observations':len(gps),'soc_history':len(battery),'stations':len(stations),'station_status':len(status),'queue_status':len(qdf),'traffic_snapshots':len(traffic),'realtime_events':len(replay),'map_matching_candidates':len(pd.read_csv(ROOT/'training/map_matching_candidates.csv.gz')),'demand_labels':len(demand),'candidate_labels':len(cand),'ranking_reference':len(rank),'recommendation_labels':len(rec)}
json.dump(counts,open(ROOT/'validation/data_counts.json','w'),indent=2);print(json.dumps(counts,indent=2))
