import os,re,json,math,random,heapq
from pathlib import Path
from datetime import datetime,timedelta
import numpy as np,pandas as pd
from shapely.geometry import Point,LineString
from shapely.strtree import STRtree
ROOT=Path('/mnt/data/dataset_v1'); SEED=20260916; rng=random.Random(SEED); np.random.seed(SEED)
for d in ['config','drivers','vehicles','trips','trajectories','gps','battery','stations','queue','traffic','realtime','training','labels','scenarios','validation','evaluation']:(ROOT/d).mkdir(parents=True,exist_ok=True)
segs=pd.read_csv(ROOT/'map/processed/road_segments.csv.gz',dtype={'osm_way_id':str}); nodes=pd.read_csv(ROOT/'map/processed/road_nodes.csv.gz'); coord=nodes.set_index('node_id')[['latitude','longitude']].to_dict('index')
def hav(lat1,lon1,lat2,lon2):
 R=6371000; p1=math.radians(lat1);p2=math.radians(lat2);dp=math.radians(lat2-lat1);dl=math.radians(lon2-lon1);a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*R*math.asin(math.sqrt(a))
def hdg(lat1,lon1,lat2,lon2):
 y=math.sin(math.radians(lon2-lon1))*math.cos(math.radians(lat2));x=math.cos(math.radians(lat1))*math.sin(math.radians(lat2))-math.sin(math.radians(lat1))*math.cos(math.radians(lat2))*math.cos(math.radians(lon2-lon1));return(math.degrees(math.atan2(y,x))+360)%360
usable=segs[~segs.access.astype(str).str.lower().isin(['no','private'])].copy(); edge_by_id=segs.set_index('segment_id').to_dict('index')
adj={}; indeg={}
for r in usable.itertuples():
 adj.setdefault(r.from_node_id,[]).append((r.to_node_id,r.segment_id,float(r.length_m)))
 indeg[r.to_node_id]=indeg.get(r.to_node_id,0)+1
for n in adj: indeg[n]=indeg.get(n,0)
# Prefer urban-connected nodes with degree >=2
candidate_nodes=[n for n,es in adj.items() if len(es)>=2 and indeg.get(n,0)>=1]
config={'seed':SEED,'drivers':60,'vehicles':60,'trips':150,'stations':30,'trajectory_spacing_m':12,'traffic_update_min':30,'station_update_min':10,'simulation_start':'2026-09-01T06:00:00+07:00','simulation_hours':18}
json.dump(config,open(ROOT/'config/generation_config.json','w'),indent=2)
drivers=pd.DataFrame([{'driver_id':f'D{i:04d}','status':'ACTIVE','operating_shift':['MORNING','DAY','EVENING'][(i-1)%3]} for i in range(1,61)])
vehicles=[]
for i,d in enumerate(drivers.driver_id,1):
 vt='EV_MOTORBIKE' if i%3==0 else 'EV_CAR';cap=3.5 if vt=='EV_MOTORBIKE' else [42,50,55][i%3];cons=45 if vt=='EV_MOTORBIKE' else [135,150,165][i%3]
 vehicles.append({'vehicle_id':f'V{i:04d}','driver_id':d,'vehicle_type':vt,'battery_capacity_kwh':cap,'usable_capacity_kwh':round(cap*.92,2),'consumption_wh_per_km':cons,'minimum_safe_soc_pct':15,'charging_supported':True,'swap_supported':vt=='EV_MOTORBIKE','connector_type':'BIKE_DC' if vt=='EV_MOTORBIKE' else 'CCS2','battery_type':'SWAP_PACK_A' if vt=='EV_MOTORBIKE' else 'FIXED_PACK'})
vehicles=pd.DataFrame(vehicles); drivers.to_csv(ROOT/'drivers/drivers.csv',index=False);vehicles.to_csv(ROOT/'vehicles/vehicles.csv',index=False); veh=vehicles.set_index('vehicle_id')
# Station nodes spaced roughly and high degree
ranked=sorted(candidate_nodes,key=lambda n:len(adj.get(n,[]))+indeg.get(n,0),reverse=True)[:12000];rng.shuffle(ranked);sn=[]
for n in ranked:
 lat,lon=coord[n]['latitude'],coord[n]['longitude']
 if all(hav(lat,lon,coord[x]['latitude'],coord[x]['longitude'])>600 for x in sn):sn.append(n)
 if len(sn)>=30:break
stations=[]
for i,n in enumerate(sn,1):
 typ='SWAP' if i%3==0 else ('CHARGING_SWAP' if i%5==0 else 'CHARGING');total=[4,6,8,10][i%4];ch=total if typ=='CHARGING' else (max(2,total//2) if typ=='CHARGING_SWAP' else 0);sw=total-ch
 stations.append({'station_id':f'S{i:03d}','access_node_id':n,'latitude':coord[n]['latitude'],'longitude':coord[n]['longitude'],'access_latitude':coord[n]['latitude'],'access_longitude':coord[n]['longitude'],'station_type':typ,'connector_type':'CCS2' if typ=='CHARGING' else ('BIKE_DC;CCS2' if typ=='CHARGING_SWAP' else 'BIKE_DC'),'battery_type':'SWAP_PACK_A' if 'SWAP' in typ else None,'supported_vehicle_type':'EV_CAR' if typ=='CHARGING' else ('EV_MOTORBIKE;EV_CAR' if typ=='CHARGING_SWAP' else 'EV_MOTORBIKE'),'total_slots':total,'charging_slots':ch,'swap_slots':sw})
stations=pd.DataFrame(stations);stations.to_csv(ROOT/'stations/stations.csv',index=False)
scenarios=['NORMAL_TRIP','NO_SERVICE_NEEDED','LOW_SOC','NEED_CHARGING','NEED_SWAP','NEAREST_FULL','STATION_OFFLINE','INCOMPATIBLE_STATION','LONG_QUEUE','FARTHER_BUT_FASTER','HEAVY_TRAFFIC','INSUFFICIENT_RANGE','GPS_NOISE','GPS_MISSING','PARALLEL_ROADS','BRIDGE_AMBIGUITY','QUEUE_REALTIME_CHANGE','TRAFFIC_REALTIME_CHANGE','STATION_STATUS_CHANGE','NO_AVAILABLE_STATION','NEAR_TIE_STATIONS']
start0=pd.Timestamp(config['simulation_start']); trip_rows=[];true=[];gps=[];bat=[];trip_node_at={}; trip_paths={}
def random_walk(start,target_m):
 path=[start];edges=[];dist=0;prev=None;vis={}
 cur=start
 while dist<target_m and len(edges)<800:
  opts=adj.get(cur,[])
  if not opts:break
  nonback=[x for x in opts if x[0]!=prev] or opts
  # prefer less visited, major roads modestly
  cand=sorted(nonback,key=lambda x:vis.get(x[1],0))[:min(4,len(nonback))];nxt,sid,L=rng.choice(cand)
  vis[sid]=vis.get(sid,0)+1;edges.append((cur,nxt,sid,L));path.append(nxt);dist+=L;prev,cur=cur,nxt
 return path,edges,dist
for ti in range(1,151):
 for _ in range(30):
  o=rng.choice(candidate_nodes);path,edges,dist=random_walk(o,rng.uniform(2500,9000))
  if dist>1800 and len(edges)>10:break
 vid=vehicles.iloc[(ti-1)%60].vehicle_id;v=veh.loc[vid]; sc=scenarios[(ti-1)%len(scenarios)]; trip=f'T{ti:04d}';traj=f'TRJ{ti:04d}';st=start0+pd.Timedelta(minutes=(ti*6)%870)
 init=rng.uniform(10,24) if sc in ['LOW_SOC','NEED_CHARGING','NEED_SWAP','INSUFFICIENT_RANGE'] else rng.uniform(45,95)
 distcum=0;elapsed=0;idx=0;points=[]
 for u,w,sid,L in edges:
  sr=edge_by_id[sid];lat1,lon1=coord[u]['latitude'],coord[u]['longitude'];lat2,lon2=coord[w]['latitude'],coord[w]['longitude'];speed=min(float(sr['maxspeed_kmh']),{'motorway':60,'trunk':50,'primary':40,'secondary':35,'tertiary':32,'residential':25,'service':18}.get(sr['road_type'],25));n=max(1,int(L/12))
  for j in range(n):
   f=j/n;lat=lat1+(lat2-lat1)*f;lon=lon1+(lon2-lon1)*f;ts=st+pd.Timedelta(seconds=elapsed);points.append((idx,ts,lat,lon,sid,speed,hdg(lat1,lon1,lat2,lon2),distcum,u));dd=L/n;distcum+=dd;elapsed+=dd/(speed*1000/3600);idx+=1
 lat,lon=coord[path[-1]]['latitude'],coord[path[-1]]['longitude'];points.append((idx,st+pd.Timedelta(seconds=elapsed),lat,lon,edges[-1][2],0,points[-1][6],distcum,path[-1])); trip_paths[trip]=path
 trip_rows.append({'trip_id':trip,'driver_id':v.driver_id,'vehicle_id':vid,'origin_node_id':path[0],'destination_node_id':path[-1],'start_time':st.isoformat(),'end_time':points[-1][1].isoformat(),'planned_network_distance_m':round(distcum,1),'scenario_id':sc})
 cap=float(v.usable_capacity_kwh);cons=float(v.consumption_wh_per_km)
 for pidx,ts,lat,lon,sid,speed,head,dm,nodeat in points:
  e=dm/1000*cons/1000*(1.12 if sc=='HEAVY_TRAFFIC' else 1);soc=max(0,init-e/cap*100);rr=max(0,soc/100*cap/(cons/1000));true.append({'trajectory_id':traj,'trip_id':trip,'point_index':pidx,'timestamp':ts.isoformat(),'true_latitude':lat,'true_longitude':lon,'true_segment_id':sid,'speed_kmh':speed,'heading_deg':head,'travel_direction':'FORWARD' if sid.endswith('_F') else 'REVERSE'});bat.append({'vehicle_id':vid,'trip_id':trip,'timestamp':ts.isoformat(),'soc_pct':round(soc,3),'distance_travelled_km':round(dm/1000,4),'energy_consumed_kwh':round(e,5),'estimated_remaining_range_km':round(rr,2)})
  profile='normal';sigma=6
  if sc=='GPS_NOISE':sigma=20
  elif sc in ['PARALLEL_ROADS','BRIDGE_AMBIGUITY']:sigma=14
  if sc=='GPS_MISSING' and pidx%7 in (0,1):continue
  if ti%19==0 and pidx%4!=0:continue
  dx=np.random.normal(0,sigma);dy=np.random.normal(0,sigma);glat=lat+dy/111320;glon=lon+dx/(111320*max(.2,math.cos(math.radians(lat))));gps.append({'observation_id':f'O{len(gps)+1:08d}','trajectory_id':traj,'trip_id':trip,'timestamp':ts.isoformat(),'latitude':glat,'longitude':glon,'speed_kmh':round(max(0,speed+np.random.normal(0,2.5)),2),'heading_deg':round((head+np.random.normal(0,25 if sigma>=14 else 7))%360,2),'accuracy_m':round(sigma*1.4,1)})
trips=pd.DataFrame(trip_rows);true=pd.DataFrame(true);gps=pd.DataFrame(gps);battery=pd.DataFrame(bat);trips.to_csv(ROOT/'trips/trips.csv',index=False);true.to_csv(ROOT/'trajectories/true_trajectories.csv.gz',index=False,compression='gzip');gps.to_csv(ROOT/'gps/gps_observations.csv.gz',index=False,compression='gzip');battery.to_csv(ROOT/'battery/soc_history.csv.gz',index=False,compression='gzip')
truth=true[['trajectory_id','trip_id','timestamp','true_segment_id','true_latitude','true_longitude','travel_direction']];mm=gps.merge(truth,on=['trajectory_id','trip_id','timestamp']);mm[['observation_id','true_segment_id','true_latitude','true_longitude','travel_direction']].rename(columns={'travel_direction':'true_direction'}).to_csv(ROOT/'labels/map_matching_labels.csv.gz',index=False,compression='gzip')
# map matching candidate generation restricted to segments appearing in trips + nearby full network sample
phys=segs[segs.travel_direction=='FORWARD'].copy(); phys_sample=phys[phys.base_segment_id.isin(set(edge_by_id[s]['base_segment_id'] for s in true.true_segment_id.unique()))].copy(); geoms=[]
for w in phys_sample.geometry:
 nums=[float(x) for x in re.findall(r'-?\d+\.\d+',w)];geoms.append(LineString([(nums[0],nums[1]),(nums[2],nums[3])]))
tree=STRtree(geoms);cand=[];samplemm=mm.iloc[::max(1,len(mm)//5000)]
for r in samplemm.itertuples():
 p=Point(r.longitude,r.latitude);inds=tree.query(p.buffer(.0012),predicate='intersects');sc=[]
 for ix in inds[:40]:
  g=geoms[ix];pr=g.interpolate(g.project(p));d=hav(r.latitude,r.longitude,pr.y,pr.x);sr=phys_sample.iloc[ix];h=hdg(g.coords[0][1],g.coords[0][0],g.coords[-1][1],g.coords[-1][0]);diff=min(abs(r.heading_deg-h)%360,360-abs(r.heading_deg-h)%360);sc.append((d,ix,pr,diff))
 for d,ix,pr,diff in sorted(sc,key=lambda x:x[0])[:5]:
  sr=phys_sample.iloc[ix];correct=sr.base_segment_id==edge_by_id[r.true_segment_id]['base_segment_id'];cand.append({'observation_id':r.observation_id,'candidate_segment_id':sr.segment_id,'distance_to_segment_m':round(d,2),'projected_lat':pr.y,'projected_lon':pr.x,'heading_difference_deg':round(diff,2),'is_correct':bool(correct),'hard_negative':bool((not correct) and d<12 and diff<35)})
pd.DataFrame(cand).to_csv(ROOT/'training/map_matching_candidates.csv.gz',index=False,compression='gzip')
# demand labels/features
splits_ids=list(trips.trip_id);rng.shuffle(splits_ids);n=len(splits_ids);sm={t:('train' if i<int(.7*n) else 'validation' if i<int(.85*n) else 'test') for i,t in enumerate(splits_ids)};pd.DataFrame([{'trip_id':t,'split':sm[t]} for t in trips.trip_id]).to_csv(ROOT/'training/trip_splits.csv',index=False)
demand=[];features=[];bgroups={k:v.reset_index(drop=True) for k,v in battery.groupby('trip_id')}
for tr in trips.itertuples():
 b=bgroups[tr.trip_id];ix=int(len(b)*.6);r=b.iloc[ix];v=veh.loc[tr.vehicle_id];remain=max(0,tr.planned_network_distance_m/1000-r.distance_travelled_km);need=(r.estimated_remaining_range_km<remain+5 or r.soc_pct<=v.minimum_safe_soc_pct+5);typ='NONE';reason='SUFFICIENT_SOC_RANGE'
 if need:typ='BATTERY_SWAP' if v.swap_supported and tr.scenario_id=='NEED_SWAP' else 'CHARGING';reason='LOW_SOC_OR_INSUFFICIENT_RANGE'
 eid=f'E{len(demand)+1:04d}';demand.append({'event_id':eid,'trip_id':tr.trip_id,'timestamp':r.timestamp,'need_service':bool(need),'service_type':typ,'reason_code':reason});features.append({'event_id':eid,'trip_id':tr.trip_id,'timestamp':r.timestamp,'soc_pct':r.soc_pct,'estimated_remaining_range_km':r.estimated_remaining_range_km,'remaining_trip_distance_km':round(remain,3),'consumption_wh_per_km':v.consumption_wh_per_km,'minimum_safe_soc_pct':v.minimum_safe_soc_pct,'swap_supported':v.swap_supported,'split':sm[tr.trip_id]})
demand=pd.DataFrame(demand);demand.to_csv(ROOT/'labels/demand_labels.csv',index=False);pd.DataFrame(features).to_csv(ROOT/'training/demand_features.csv',index=False)
# add splits to mm candidate training
cm=pd.DataFrame(cand).merge(gps[['observation_id','trip_id']],on='observation_id',how='left');cm['split']=cm.trip_id.map(sm);cm.to_csv(ROOT/'training/map_matching_candidates_with_split.csv.gz',index=False,compression='gzip')
# station state / queue temporal consistency
status=[];qrows=[]
for si,s in stations.iterrows():
 for k in range(109):
  ts=start0+pd.Timedelta(minutes=10*k);peak=ts.hour in [7,8,17,18];occ=max(0,min(int(s.total_slots),int(s.total_slots*(.7 if peak else .35)+1.5*math.sin(k/5+si)+rng.choice([-1,0,0,1]))));avail=int(s.total_slots)-occ;q=0;op='OPEN'
  if si==2 and 30<=k<42:op='OFFLINE';occ=avail=q=0
  if si==0 and 35<=k<45:occ=int(s.total_slots);avail=0;q=2+k%4
  service=6 if s.station_type=='SWAP' else 18;active=min(occ,max(1,int(s.total_slots)));wait=0 if q==0 else q*service/max(1,active);sw=max(0,int(s.swap_slots)*2-q) if s.swap_slots>0 and op=='OPEN' else 0
  status.append({'station_id':s.station_id,'timestamp':ts.isoformat(),'operating_status':op,'available_slots':avail,'occupied_slots':occ,'available_swap_batteries':sw,'queue_length':q,'estimated_service_time_min':service});qrows.append({'station_id':s.station_id,'timestamp':ts.isoformat(),'queue_length':q,'active_service_count':active,'average_service_time_min':service,'estimated_wait_min':round(wait,2)})
status=pd.DataFrame(status);qdf=pd.DataFrame(qrows);status.to_csv(ROOT/'stations/station_status.csv.gz',index=False,compression='gzip');qdf.to_csv(ROOT/'queue/queue_status.csv.gz',index=False,compression='gzip')
# traffic on route segments + major sampled
route_sids=set(true.true_segment_id);major=usable[usable.road_type.isin(['motorway','trunk','primary','secondary'])];major_sids=set(major.sample(min(3000,len(major)),random_state=SEED).segment_id);traf=[]
for k in range(37):
 ts=start0+pd.Timedelta(minutes=30*k);peak=ts.hour in [7,8,17,18]
 for sid in route_sids|major_sids:
  sr=edge_by_id[sid];ff=float(sr['maxspeed_kmh']);factor=rng.uniform(.35,.65) if peak else rng.uniform(.75,1);incident=(abs(hash(sid+str(k)))%997==0)
  if incident:factor*=.35;level='INCIDENT'
  elif factor<.5:level='HEAVY'
  elif factor<.8:level='MODERATE'
  else:level='FREE_FLOW'
  cur=max(5,ff*factor);traf.append({'segment_id':sid,'timestamp':ts.isoformat(),'traffic_level':level,'free_flow_speed_kmh':ff,'current_speed_kmh':round(cur,2),'delay_factor':round(ff/cur,3)})
traffic=pd.DataFrame(traf);traffic.to_csv(ROOT/'traffic/traffic_snapshots.csv.gz',index=False,compression='gzip')
# candidate labels eligibility and ranking reference with actual graph Dijkstra for a limited evaluation set
station_nodes=set(stations.access_node_id); station_by_node={r.access_node_id:r for r in stations.itertuples()}
def dijkstra_targets(source,targets,limit=30000):
 dist={source:0};pq=[(0,source)];found={};tset=set(targets)
 while pq and len(found)<len(tset):
  d,u=heapq.heappop(pq)
  if d!=dist.get(u):continue
  if d>limit:break
  if u in tset:found[u]=d
  for v,sid,w in adj.get(u,[]):
   nd=d+w
   if nd<dist.get(v,1e100) and nd<=limit:dist[v]=nd;heapq.heappush(pq,(nd,v))
 return found
candlab=[];rank=[];reclab=[]
for ev in demand[demand.need_service].head(25).itertuples():
 tr=trips[trips.trip_id==ev.trip_id].iloc[0];td=true[true.trip_id==ev.trip_id].reset_index(drop=True);rr=td.iloc[int(len(td)*.6)];source=edge_by_id[rr.true_segment_id]['from_node_id'];dmap=dijkstra_targets(source,station_nodes);v=veh.loc[tr.vehicle_id];eligible=[]
 for s in stations.itertuples():
  comp=v.vehicle_type in s.supported_vehicle_type and ((ev.service_type=='CHARGING' and 'CHARGING' in s.station_type) or (ev.service_type=='BATTERY_SWAP' and 'SWAP' in s.station_type));reach=s.access_node_id in dmap;candlab.append({'event_id':ev.event_id,'station_id':s.station_id,'eligible':bool(comp and reach),'reason':'ELIGIBLE' if comp and reach else ('INCOMPATIBLE' if not comp else 'UNREACHABLE')})
  if comp and reach:eligible.append((dmap[s.access_node_id],s))
 scored=[]
 for d,s in sorted(eligible,key=lambda x:x[0])[:6]:
  es=pd.Timestamp(ev.timestamp);k=max(0,min(108,round((es-start0).total_seconds()/600)));st=status[status.station_id==s.station_id].iloc[k];qq=qdf[qdf.station_id==s.station_id].iloc[k]; eta=d/1000/30*60; b=bgroups[ev.trip_id].iloc[int(len(bgroups[ev.trip_id])*.6)];feas=d/1000<=b.estimated_remaining_range_km;cost=eta+qq.estimated_wait_min+(0 if feas else 1000)+(0 if st.operating_status=='OPEN' else 1000);rank.append({'event_id':ev.event_id,'station_id':s.station_id,'route_distance_m_ref':round(d,1),'eta_min_ref':round(eta,2),'queue_wait_min':qq.estimated_wait_min,'available_slots':st.available_slots,'operating_status':st.operating_status,'soc_feasible':bool(feas),'ranking_cost_label':round(cost,3)});scored.append((cost,s.station_id))
 if scored:reclab.append({'event_id':ev.event_id,'reference_station_id':min(scored)[1],'label_method':'minimum_reference_cost_with_network_distance_feasibility_queue_status'})
pd.DataFrame(candlab).to_csv(ROOT/'labels/candidate_labels.csv',index=False);pd.DataFrame(rank).to_csv(ROOT/'training/ranking_reference.csv',index=False);pd.DataFrame(reclab).to_csv(ROOT/'labels/recommendation_labels.csv',index=False)
# realtime replay
recs=[]
def add(ts,typ,eid,p):recs.append({'timestamp':ts,'event_type':typ,'entity_id':eid,'payload_json':json.dumps(p,separators=(',',':'))})
for r in gps.iloc[::6].itertuples():add(r.timestamp,'GPS_UPDATE',r.trip_id,{'observation_id':r.observation_id,'lat':round(r.latitude,7),'lon':round(r.longitude,7)})
for r in battery.iloc[::10].itertuples():add(r.timestamp,'SOC_UPDATE',r.trip_id,{'soc_pct':r.soc_pct,'remaining_range_km':r.estimated_remaining_range_km})
for r in status.iloc[::3].itertuples():add(r.timestamp,'STATION_STATUS_UPDATE',r.station_id,{'status':r.operating_status,'available_slots':r.available_slots,'queue_length':r.queue_length})
for r in traffic.sample(min(6000,len(traffic)),random_state=SEED).itertuples():add(r.timestamp,'TRAFFIC_UPDATE',r.segment_id,{'traffic_level':r.traffic_level,'current_speed_kmh':r.current_speed_kmh})
replay=pd.DataFrame(recs).sort_values('timestamp').reset_index(drop=True);replay.insert(0,'event_id',[f'RE{i+1:08d}' for i in range(len(replay))]);replay.to_csv(ROOT/'realtime/events.csv.gz',index=False,compression='gzip')
sc=trips.groupby('scenario_id').agg(trip_count=('trip_id','count'),example_trip_id=('trip_id','first')).reset_index();sc['data_evidence']='linked trip + network trajectory + GPS + SOC + temporal station/queue/traffic + replay';sc.to_csv(ROOT/'scenarios/scenario_coverage.csv',index=False)
counts={'drivers':len(drivers),'vehicles':len(vehicles),'trips':len(trips),'true_trajectory_points':len(true),'gps_observations':len(gps),'soc_history':len(battery),'stations':len(stations),'station_status':len(status),'queue_status':len(qdf),'traffic_snapshots':len(traffic),'realtime_events':len(replay),'map_matching_candidates':len(cand),'demand_labels':len(demand),'ranking_reference':len(rank),'road_nodes':len(nodes),'road_segments':len(segs)};json.dump(counts,open(ROOT/'validation/data_counts.json','w'),indent=2);print(json.dumps(counts,indent=2))
