import os, re, json, math, random, hashlib, shutil, struct, zlib, gzip
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import networkx as nx
from shapely.geometry import LineString, Point, mapping
from shapely.strtree import STRtree
from pyogrio import read_dataframe, write_dataframe
import geopandas as gpd

ROOT=Path('/mnt/data/dataset_v1')
BASE=Path('/mnt/data/hanoi-baseline.osm.pbf')
PATCH=Path('/mnt/data/hanoi-patched.osm.pbf')
SEED=20260916
rng=random.Random(SEED); np.random.seed(SEED)
for d in ['config','map/raw','map/processed','drivers','vehicles','trips','trajectories','gps','battery','stations','queue','traffic','realtime','training','labels','scenarios','generators','validation','evaluation']:
    (ROOT/d).mkdir(parents=True, exist_ok=True)
shutil.copy2(BASE, ROOT/'map/raw/hanoi-baseline.osm.pbf')
shutil.copy2(PATCH, ROOT/'map/raw/hanoi-patched.osm.pbf')

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def read_varint(buf, pos):
    val=0; shift=0
    while True:
        b=buf[pos]; pos+=1; val |= (b&127)<<shift
        if not b&128: return val,pos
        shift += 7

def fields(buf):
    pos=0
    while pos<len(buf):
        key,pos=read_varint(buf,pos); num=key>>3; wt=key&7
        if wt==0:
            v,pos=read_varint(buf,pos); yield num,wt,v
        elif wt==1:
            v=buf[pos:pos+8]; pos+=8; yield num,wt,v
        elif wt==2:
            ln,pos=read_varint(buf,pos); v=buf[pos:pos+ln]; pos+=ln; yield num,wt,v
        elif wt==5:
            v=buf[pos:pos+4]; pos+=4; yield num,wt,v
        else: raise ValueError('unsupported protobuf wire type')

def blob_decode(blob):
    raw=None
    for n,w,v in fields(blob):
        if n==1 and w==2: raw=v
        elif n==3 and w==2: raw=zlib.decompress(v)
    return raw

def pbf_stats(path):
    counts={'nodes':0,'ways':0,'relations':0,'changesets':0,'data_blobs':0,'header_blobs':0}
    types=[]; bbox=None
    with open(path,'rb') as f:
        while True:
            b=f.read(4)
            if not b: break
            if len(b)!=4: raise ValueError('truncated PBF header length')
            hlen=struct.unpack('>I',b)[0]
            if hlen<=0 or hlen>64*1024: raise ValueError('invalid BlobHeader length')
            bh=f.read(hlen); typ=None; dsize=None
            for n,w,v in fields(bh):
                if n==1: typ=v.decode('utf-8')
                elif n==3: dsize=v
            if not typ or dsize is None: raise ValueError('invalid BlobHeader')
            blob=f.read(dsize)
            if len(blob)!=dsize: raise ValueError('truncated Blob')
            raw=blob_decode(blob)
            if raw is None: raise ValueError('unsupported compression/no raw payload')
            types.append(typ)
            if typ=='OSMHeader':
                counts['header_blobs']+=1
                for n,w,v in fields(raw):
                    if n==1 and w==2:
                        vals={}
                        for bn,bw,bv in fields(v): vals[bn]=bv
                        # sint64 zigzag nanodegrees in HeaderBBox
                        def zz(x): return (x>>1)^-(x&1)
                        try: bbox={'left':zz(vals[1])*1e-9,'right':zz(vals[2])*1e-9,'top':zz(vals[3])*1e-9,'bottom':zz(vals[4])*1e-9}
                        except: pass
            elif typ=='OSMData':
                counts['data_blobs']+=1
                for n,w,v in fields(raw):
                    if n==2 and w==2: # PrimitiveGroup
                        for gn,gw,gv in fields(v):
                            if gn==1: counts['nodes']+=1
                            elif gn==2: # DenseNodes; packed ids field 1 count varints
                                for dn,dw,dv in fields(gv):
                                    if dn==1 and dw==2:
                                        p=0; c=0
                                        while p<len(dv): _,p=read_varint(dv,p); c+=1
                                        counts['nodes']+=c
                            elif gn==3: counts['ways']+=1
                            elif gn==4: counts['relations']+=1
                            elif gn==5: counts['changesets']+=1
    return {'file':path.name,'size_bytes':path.stat().st_size,'sha256':sha256(path),'valid_pbf':True,'blob_types':sorted(set(types)),**counts,'header_bbox':bbox}

stats_base=pbf_stats(BASE); stats_patch=pbf_stats(PATCH)
json.dump({'baseline':stats_base,'patched':stats_patch},open(ROOT/'map/processed/pbf_stats.json','w'),indent=2,ensure_ascii=False)

TAG_RE=re.compile(r'"([^"]+)"=>"([^"]*)"')
def tags(s): return {k:v for k,v in TAG_RE.findall(s or '')}
def hav(lat1,lon1,lat2,lon2):
    R=6371000; p1=math.radians(lat1); p2=math.radians(lat2); dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))
def heading(lat1,lon1,lat2,lon2):
    y=math.sin(math.radians(lon2-lon1))*math.cos(math.radians(lat2)); x=math.cos(math.radians(lat1))*math.sin(math.radians(lat2))-math.sin(math.radians(lat1))*math.cos(math.radians(lat2))*math.cos(math.radians(lon2-lon1))
    return (math.degrees(math.atan2(y,x))+360)%360

drivable={'motorway','trunk','primary','secondary','tertiary','unclassified','residential','living_street','service','motorway_link','trunk_link','primary_link','secondary_link','tertiary_link'}
lines=read_dataframe(PATCH,layer='lines',columns=['osm_id','name','highway','other_tags'])
base_lines=read_dataframe(BASE,layer='lines',columns=['osm_id','name','highway','other_tags'])
# diff
A=base_lines.set_index('osm_id'); B=lines.set_index('osm_id'); diffs=[]
for oid in A.index.intersection(B.index):
    a=A.loc[oid]; b=B.loc[oid]
    if (str(a['name'])!=str(b['name']) or str(a['highway'])!=str(b['highway']) or str(a['other_tags'])!=str(b['other_tags']) or not a.geometry.equals_exact(b.geometry,1e-12)):
        diffs.append({'osm_way_id':oid,'baseline_name':a['name'],'highway':a['highway'],'baseline_other_tags':a['other_tags'],'patched_other_tags':b['other_tags'],'geometry_changed':not a.geometry.equals_exact(b.geometry,1e-12)})
pd.DataFrame(diffs).to_csv(ROOT/'map/processed/pbf_diff.csv',index=False)
roads=lines[lines.highway.isin(drivable)].copy()
node_map={}; node_rows=[]; seg_rows=[]
def node_id(lon,lat):
    key=(round(lon,7),round(lat,7))
    if key not in node_map:
        nid=f'N{len(node_map)+1:07d}'; node_map[key]=nid; node_rows.append((nid,key[1],key[0]))
    return node_map[key]
for row in roads.itertuples():
    if row.geometry is None or row.geometry.geom_type!='LineString': continue
    t=tags(row.other_tags); coords=list(row.geometry.coords)
    oneway=str(t.get('oneway','')).lower() in ('yes','1','true') or row.highway=='motorway'
    access=t.get('access') or t.get('motor_vehicle') or t.get('motorcar') or 'yes'
    try: maxspeed=float(re.findall(r'\d+',t.get('maxspeed',''))[0])
    except: maxspeed={'motorway':80,'trunk':70,'primary':50,'secondary':45,'tertiary':40,'residential':30,'service':20}.get(row.highway,30)
    try: lanes=int(re.findall(r'\d+',t.get('lanes',''))[0])
    except: lanes=None
    for i,(c1,c2) in enumerate(zip(coords[:-1],coords[1:])):
        lon1,lat1=c1[:2]; lon2,lat2=c2[:2]; L=hav(lat1,lon1,lat2,lon2)
        if L<0.5: continue
        n1=node_id(lon1,lat1); n2=node_id(lon2,lat2); baseid=f'{row.osm_id}_{i}'
        common=dict(base_segment_id=baseid,osm_way_id=str(row.osm_id),geometry=f'LINESTRING ({lon1} {lat1}, {lon2} {lat2})',length_m=round(L,3),road_type=row.highway,road_name=row.name if pd.notna(row.name) else None,oneway=oneway,maxspeed_kmh=maxspeed,lanes=lanes,bridge=t.get('bridge','no'),tunnel=t.get('tunnel','no'),access=access)
        seg_rows.append({'segment_id':baseid+'_F','from_node_id':n1,'to_node_id':n2,'travel_direction':'FORWARD',**common})
        if not oneway:
            seg_rows.append({'segment_id':baseid+'_R','from_node_id':n2,'to_node_id':n1,'travel_direction':'REVERSE',**common})
nodes=pd.DataFrame(node_rows,columns=['node_id','latitude','longitude'])
segs=pd.DataFrame(seg_rows)
nodes.to_csv(ROOT/'map/processed/road_nodes.csv.gz',index=False,compression='gzip')
segs.to_csv(ROOT/'map/processed/road_segments.csv.gz',index=False,compression='gzip')
# sample geojson
sg=segs.sample(min(3000,len(segs)),random_state=SEED).copy(); sg['geometry']=gpd.GeoSeries.from_wkt(sg.geometry); gdf=gpd.GeoDataFrame(sg,geometry='geometry',crs='EPSG:4326'); gdf.to_file(ROOT/'map/processed/road_segments_sample.geojson',driver='GeoJSON')
# graph excluding explicit no/private access
coord=nodes.set_index('node_id')[['latitude','longitude']].to_dict('index')
G=nx.DiGraph()
usable=segs[~segs.access.astype(str).str.lower().isin(['no','private'])]
for r in usable.itertuples():
    G.add_edge(r.from_node_id,r.to_node_id,segment_id=r.segment_id,length_m=r.length_m,maxspeed_kmh=r.maxspeed_kmh,road_type=r.road_type,road_name=r.road_name,bridge=r.bridge)
comp=max(nx.weakly_connected_components(G),key=len); H=G.subgraph(comp).copy()
# config
config={'seed':SEED,'drivers':60,'vehicles':60,'trips':120,'stations':30,'gps_frequency_sec':5,'traffic_update_min':15,'station_update_min':10,'simulation_start':'2026-09-01T06:00:00+07:00','simulation_hours':18,'gps_noise_profiles':{'clean':2,'normal':6,'high_noise':18,'drift':12,'heading_noise':8,'low_sampling':6,'missing':6}}
json.dump(config,open(ROOT/'config/generation_config.json','w'),indent=2)
# drivers/vehicles
shifts=['MORNING','DAY','EVENING']; drivers=pd.DataFrame([{'driver_id':f'D{i:04d}','status':'ACTIVE','operating_shift':shifts[i%3]} for i in range(1,61)])
vehicles=[]
for i,d in enumerate(drivers.driver_id,1):
    vt='EV_MOTORBIKE' if i%3==0 else 'EV_CAR'; cap=3.5 if vt=='EV_MOTORBIKE' else rng.choice([42,50,55]); usable_cap=cap*0.92; cons=45 if vt=='EV_MOTORBIKE' else rng.choice([135,150,165]);
    vehicles.append({'vehicle_id':f'V{i:04d}','driver_id':d,'vehicle_type':vt,'battery_capacity_kwh':cap,'usable_capacity_kwh':round(usable_cap,2),'consumption_wh_per_km':cons,'minimum_safe_soc_pct':15,'charging_supported':True,'swap_supported':vt=='EV_MOTORBIKE','connector_type':'BIKE_DC' if vt=='EV_MOTORBIKE' else 'CCS2','battery_type':'SWAP_PACK_A' if vt=='EV_MOTORBIKE' else 'FIXED_PACK'})
vehicles=pd.DataFrame(vehicles); drivers.to_csv(ROOT/'drivers/drivers.csv',index=False); vehicles.to_csv(ROOT/'vehicles/vehicles.csv',index=False)
# stations at well-connected nodes, spread by degree and random
cand_nodes=sorted(H.nodes,key=lambda n:H.degree(n),reverse=True)[:5000]; rng.shuffle(cand_nodes); station_nodes=[]
for n in cand_nodes:
    lat,lon=coord[n]['latitude'],coord[n]['longitude']
    if all(hav(lat,lon,coord[x]['latitude'],coord[x]['longitude'])>700 for x in station_nodes): station_nodes.append(n)
    if len(station_nodes)>=30: break
stations=[]
for i,n in enumerate(station_nodes,1):
    lat,lon=coord[n]['latitude'],coord[n]['longitude']; stype='SWAP' if i%3==0 else ('CHARGING_SWAP' if i%5==0 else 'CHARGING')
    stations.append({'station_id':f'S{i:03d}','access_node_id':n,'latitude':lat,'longitude':lon,'access_latitude':lat,'access_longitude':lon,'station_type':stype,'connector_type':'CCS2' if stype=='CHARGING' else ('BIKE_DC;CCS2' if stype=='CHARGING_SWAP' else 'BIKE_DC'),'battery_type':'SWAP_PACK_A' if stype in ('SWAP','CHARGING_SWAP') else None,'supported_vehicle_type':'EV_CAR' if stype=='CHARGING' else ('EV_MOTORBIKE;EV_CAR' if stype=='CHARGING_SWAP' else 'EV_MOTORBIKE'),'total_slots':rng.choice([4,6,8,10]),'charging_slots':0,'swap_slots':0})
for s in stations:
    if s['station_type']=='CHARGING': s['charging_slots']=s['total_slots']
    elif s['station_type']=='SWAP': s['swap_slots']=s['total_slots']
    else: s['charging_slots']=max(2,s['total_slots']//2); s['swap_slots']=s['total_slots']-s['charging_slots']
stations=pd.DataFrame(stations); stations.to_csv(ROOT/'stations/stations.csv',index=False)
# trips with shortest path, ensure variety incl bridge when naturally occurs
allnodes=list(H.nodes); trip_rows=[]; trajectory_rows=[]; gps_rows=[]; battery_rows=[]; trip_paths={}; scenario_catalog=['NORMAL_TRIP','NO_SERVICE_NEEDED','LOW_SOC','NEED_CHARGING','NEED_SWAP','NEAREST_FULL','STATION_OFFLINE','INCOMPATIBLE_STATION','LONG_QUEUE','FARTHER_BUT_FASTER','HEAVY_TRAFFIC','INSUFFICIENT_RANGE','GPS_NOISE','GPS_MISSING','PARALLEL_ROADS','BRIDGE_AMBIGUITY','QUEUE_REALTIME_CHANGE','TRAFFIC_REALTIME_CHANGE','STATION_STATUS_CHANGE','NO_AVAILABLE_STATION','NEAR_TIE_STATIONS']
start0=datetime.fromisoformat(config['simulation_start'])
edge_by_id=segs.set_index('segment_id').to_dict('index')
veh_idx=vehicles.set_index('vehicle_id')
for ti in range(1,121):
    # select path 2-12km
    path=None
    for attempt in range(50):
        o=rng.choice(allnodes); lengths=nx.single_source_dijkstra_path_length(H,o,cutoff=12000,weight='length_m')
        targets=[n for n,d in lengths.items() if 2000<d<10000]
        if targets:
            dest=rng.choice(targets); path=nx.shortest_path(H,o,dest,weight='length_m'); break
    if not path: continue
    vid=vehicles.iloc[(ti-1)%len(vehicles)].vehicle_id; dr=veh_idx.loc[vid].driver_id; sc=scenario_catalog[(ti-1)%len(scenario_catalog)]
    st=start0+timedelta(minutes=(ti*7)%900); tripid=f'T{ti:04d}'; trajid=f'TRJ{ti:04d}'
    # scenario-sensitive initial soc
    vt=veh_idx.loc[vid]
    if sc in ['LOW_SOC','NEED_CHARGING','NEED_SWAP','INSUFFICIENT_RANGE']: init_soc=rng.uniform(10,24)
    else: init_soc=rng.uniform(45,95)
    # Build point sequence ~ every 15m, timestamp based on road-type speed
    pts=[]; elapsed=0.; distcum=0.; energy=0.; idx=0
    for u,v in zip(path[:-1],path[1:]):
        dat=H[u][v]; sid=dat['segment_id']; sr=edge_by_id[sid]; lat1,lon1=coord[u]['latitude'],coord[u]['longitude']; lat2,lon2=coord[v]['latitude'],coord[v]['longitude']; L=dat['length_m']
        base_speed=min(dat['maxspeed_kmh'], {'motorway':60,'trunk':50,'primary':40,'secondary':35,'tertiary':32,'residential':25,'service':18}.get(dat['road_type'],25)); n=max(1,int(L/18))
        for j in range(n):
            f=j/n; lat=lat1+(lat2-lat1)*f; lon=lon1+(lon2-lon1)*f
            pts.append((idx,st+timedelta(seconds=elapsed),lat,lon,sid,base_speed,heading(lat1,lon1,lat2,lon2),distcum)); idx+=1
            dd=L/n; distcum+=dd; elapsed += dd/(base_speed*1000/3600)
    # final
    lat,lon=coord[path[-1]]['latitude'],coord[path[-1]]['longitude']; pts.append((idx,st+timedelta(seconds=elapsed),lat,lon,pts[-1][4],0,pts[-1][6],distcum))
    trip_paths[tripid]=path; end=pts[-1][1]
    trip_rows.append({'trip_id':tripid,'driver_id':dr,'vehicle_id':vid,'origin_node_id':path[0],'destination_node_id':path[-1],'start_time':st.isoformat(),'end_time':end.isoformat(),'planned_network_distance_m':round(distcum,1),'scenario_id':sc})
    cap=float(vt.usable_capacity_kwh); cons=float(vt.consumption_wh_per_km)
    for pidx,ts,lat,lon,sid,spd,hdg,dm in pts:
        e=dm/1000*cons/1000; variation=1.0 + (0.12 if sc=='HEAVY_TRAFFIC' else 0) + 0.03*math.sin(pidx/30)
        e*=variation; soc=max(0,init_soc-e/cap*100); rr=max(0,soc/100*cap/(cons/1000))
        trajectory_rows.append({'trajectory_id':trajid,'trip_id':tripid,'point_index':pidx,'timestamp':ts.isoformat(),'true_latitude':lat,'true_longitude':lon,'true_segment_id':sid,'speed_kmh':spd,'heading_deg':hdg,'travel_direction':'FORWARD' if sid.endswith('_F') else 'REVERSE'})
        battery_rows.append({'vehicle_id':vid,'trip_id':tripid,'timestamp':ts.isoformat(),'soc_pct':round(soc,3),'distance_travelled_km':round(dm/1000,4),'energy_consumed_kwh':round(e,5),'estimated_remaining_range_km':round(rr,2)})
        # GPS noise tied to true point
        profile='normal'
        if sc=='GPS_NOISE': profile='high_noise'
        elif sc=='GPS_MISSING': profile='missing'
        elif sc in ['PARALLEL_ROADS','BRIDGE_AMBIGUITY']: profile='drift'
        sigma={'clean':2,'normal':6,'high_noise':20,'missing':7,'drift':14}.get(profile,6)
        if profile=='missing' and pidx%7 in (0,1): continue
        # low sample occasional
        if ti%17==0 and pidx%4!=0: continue
        dx=np.random.normal(0,sigma); dy=np.random.normal(0,sigma); glat=lat+dy/111320; glon=lon+dx/(111320*max(0.2,math.cos(math.radians(lat))))
        gh=(hdg+np.random.normal(0,25 if sc in ['BRIDGE_AMBIGUITY','PARALLEL_ROADS'] else 7))%360
        gps_rows.append({'observation_id':f'O{len(gps_rows)+1:08d}','trajectory_id':trajid,'trip_id':tripid,'timestamp':ts.isoformat(),'latitude':glat,'longitude':glon,'speed_kmh':max(0,spd+np.random.normal(0,2.5)),'heading_deg':gh,'accuracy_m':round(max(1,sigma*1.4),1)})
trips=pd.DataFrame(trip_rows); trajectories=pd.DataFrame(trajectory_rows); gps=pd.DataFrame(gps_rows); battery=pd.DataFrame(battery_rows)
trips.to_csv(ROOT/'trips/trips.csv',index=False); trajectories.to_csv(ROOT/'trajectories/true_trajectories.csv.gz',index=False,compression='gzip'); gps.to_csv(ROOT/'gps/gps_observations.csv.gz',index=False,compression='gzip'); battery.to_csv(ROOT/'battery/soc_history.csv.gz',index=False,compression='gzip')
# map match labels join by nearest timestamp exact due source generation
truth=trajectories[['trajectory_id','trip_id','timestamp','true_segment_id','true_latitude','true_longitude','travel_direction']]
mm=gps.merge(truth,on=['trajectory_id','trip_id','timestamp'],how='left')
mm[['observation_id','true_segment_id','true_latitude','true_longitude','travel_direction']].rename(columns={'travel_direction':'true_direction'}).to_csv(ROOT/'labels/map_matching_labels.csv.gz',index=False,compression='gzip')
# candidates on a sample of observations, STRtree over unique physical forward segments around route
phys=segs[segs.travel_direction=='FORWARD'].copy(); geoms=list(gpd.GeoSeries.from_wkt(phys.geometry)); tree=STRtree(geoms); geom_to_idx={id(g):i for i,g in enumerate(geoms)}
cand_rows=[]
for r in mm.iloc[::max(1,len(mm)//7000)].itertuples():
    p=Point(r.longitude,r.latitude); inds=tree.query(p.buffer(0.001),predicate='intersects')
    scored=[]
    for ix in inds[:30]:
        g=geoms[ix]; pr=g.interpolate(g.project(p)); d=hav(r.latitude,r.longitude,pr.y,pr.x); sr=phys.iloc[ix]; sh=heading(g.coords[0][1],g.coords[0][0],g.coords[-1][1],g.coords[-1][0]); hd=min(abs(r.heading_deg-sh)%360,360-abs(r.heading_deg-sh)%360); scored.append((d,ix,pr,hd))
    scored=sorted(scored,key=lambda x:x[0])[:5]
    for d,ix,pr,hd in scored:
        sr=phys.iloc[ix]; correct=(sr.base_segment_id==edge_by_id[r.true_segment_id]['base_segment_id'])
        cand_rows.append({'observation_id':r.observation_id,'candidate_segment_id':sr.segment_id,'distance_to_segment_m':round(d,2),'projected_lat':pr.y,'projected_lon':pr.x,'heading_difference_deg':round(hd,2),'is_correct':bool(correct),'hard_negative':bool((not correct) and d<12 and hd<35)})
pd.DataFrame(cand_rows).to_csv(ROOT/'training/map_matching_candidates.csv.gz',index=False,compression='gzip')
# demand labels one event per trip at ~60% progress
bgroup=battery.groupby('trip_id'); demand=[]
for tr in trips.itertuples():
    bg=bgroup.get_group(tr.trip_id).reset_index(drop=True); ix=min(len(bg)-1,int(len(bg)*0.6)); rr=bg.iloc[ix]; v=veh_idx.loc[tr.vehicle_id]; remaining_dest_km=max(0,(tr.planned_network_distance_m/1000-rr.distance_travelled_km)); need=rr.estimated_remaining_range_km < remaining_dest_km+5 or rr.soc_pct <= v.minimum_safe_soc_pct+5
    typ='NONE'; reason='SUFFICIENT_SOC_RANGE'
    if need:
        if v.swap_supported and tr.scenario_id=='NEED_SWAP': typ='BATTERY_SWAP'; reason='LOW_SOC_SWAP_CAPABLE'
        else: typ='CHARGING'; reason='LOW_SOC_OR_INSUFFICIENT_RANGE'
    demand.append({'event_id':f'E{len(demand)+1:04d}','trip_id':tr.trip_id,'timestamp':rr.timestamp,'need_service':bool(need),'service_type':typ,'reason_code':reason})
demand=pd.DataFrame(demand); demand.to_csv(ROOT/'labels/demand_labels.csv',index=False)
# station status + queue, temporally consistent
status=[]; qrows=[]
for si,s in stations.iterrows():
    for k in range(109):
        ts=start0+timedelta(minutes=10*k); hour=ts.hour; peak=hour in [7,8,17,18]; base_occ=int(s.total_slots*(0.65 if peak else 0.35)+2*math.sin(k/5+si)); occ=max(0,min(int(s.total_slots),base_occ+rng.choice([-1,0,0,1]))); avail=int(s.total_slots)-occ; q=max(0,(occ-int(s.total_slots)+1))
        # inject scenarios / outages
        op='OPEN'
        if si==2 and 30<=k<42: op='OFFLINE'; occ=0; avail=0; q=0
        if si==0 and 35<=k<45: occ=int(s.total_slots); avail=0; q=2+(k%4)
        service=18 if s.station_type!='SWAP' else 6; active=min(occ,max(1,int(s.total_slots))); wait=0 if q==0 else q*service/max(1,active)
        swaps=(max(0,int(s.swap_slots)*2-q) if s.swap_slots>0 and op=='OPEN' else 0)
        status.append({'station_id':s.station_id,'timestamp':ts.isoformat(),'operating_status':op,'available_slots':avail,'occupied_slots':occ,'available_swap_batteries':swaps,'queue_length':q,'estimated_service_time_min':service})
        qrows.append({'station_id':s.station_id,'timestamp':ts.isoformat(),'queue_length':q,'active_service_count':active,'average_service_time_min':service,'estimated_wait_min':round(wait,2)})
status=pd.DataFrame(status); qdf=pd.DataFrame(qrows); status.to_csv(ROOT/'stations/station_status.csv.gz',index=False,compression='gzip'); qdf.to_csv(ROOT/'queue/queue_status.csv.gz',index=False,compression='gzip')
# traffic on all route segments + majors sample
route_sids=set(trajectories.true_segment_id.unique()); major=set(usable[usable.road_type.isin(['motorway','trunk','primary','secondary'])].sample(min(8000,len(usable[usable.road_type.isin(['motorway','trunk','primary','secondary'])])),random_state=SEED).segment_id); traf_sids=list(route_sids|major); traf=[]
for k in range(73):
    ts=start0+timedelta(minutes=15*k); peak=ts.hour in [7,8,17,18]
    for sid in traf_sids:
        sr=edge_by_id[sid]; ff=float(sr['maxspeed_kmh']); factor= rng.uniform(0.35,0.65) if peak else rng.uniform(0.75,1.0); incident=(hash(sid+str(k))%997==0)
        if incident: factor*=0.35; level='INCIDENT'
        elif factor<0.5: level='HEAVY'
        elif factor<0.8: level='MODERATE'
        else: level='FREE_FLOW'
        cur=max(5,ff*factor); traf.append({'segment_id':sid,'timestamp':ts.isoformat(),'traffic_level':level,'free_flow_speed_kmh':ff,'current_speed_kmh':round(cur,2),'delay_factor':round(ff/cur,3)})
traffic=pd.DataFrame(traf); traffic.to_csv(ROOT/'traffic/traffic_snapshots.csv.gz',index=False,compression='gzip')
# realtime event stream merge sampled GPS/SOC + all station/queue/traffic changes relevant to scenario, capped
re=[]
for r in gps.iloc[::5].itertuples(): re.append({'event_id':f'RE{len(re)+1:08d}','timestamp':r.timestamp,'event_type':'GPS_UPDATE','entity_id':r.trip_id,'payload_json':json.dumps({'observation_id':r.observation_id,'lat':round(r.latitude,7),'lon':round(r.longitude,7)})})
for r in battery.iloc[::8].itertuples(): re.append({'event_id':f'RE{len(re)+1:08d}','timestamp':r.timestamp,'event_type':'SOC_UPDATE','entity_id':r.trip_id,'payload_json':json.dumps({'soc_pct':r.soc_pct,'remaining_range_km':r.estimated_remaining_range_km})})
for r in status.iloc[::3].itertuples(): re.append({'event_id':f'RE{len(re)+1:08d}','timestamp':r.timestamp,'event_type':'STATION_STATUS_UPDATE','entity_id':r.station_id,'payload_json':json.dumps({'status':r.operating_status,'available_slots':r.available_slots,'queue_length':r.queue_length})})
for r in traffic.sample(min(12000,len(traffic)),random_state=SEED).itertuples(): re.append({'event_id':f'RE{len(re)+1:08d}','timestamp':r.timestamp,'event_type':'TRAFFIC_UPDATE','entity_id':r.segment_id,'payload_json':json.dumps({'traffic_level':r.traffic_level,'current_speed_kmh':r.current_speed_kmh})})
re=pd.DataFrame(re).sort_values('timestamp').reset_index(drop=True); re['event_id']=[f'RE{i+1:08d}' for i in range(len(re))]; re.to_csv(ROOT/'realtime/events.csv.gz',index=False,compression='gzip')
# ranking/candidate/recommendation labels based on demand events. Compute network distances via one dijkstra/event, status nearest timestamp.
station_nodes_map=stations.set_index('station_id').access_node_id.to_dict(); ranking=[]; rec_labels=[]; cand_labels=[]
traj_by_trip={k:v.reset_index(drop=True) for k,v in trajectories.groupby('trip_id')}
for ev in demand[demand.need_service].head(40).itertuples():
    tr=trips.set_index('trip_id').loc[ev.trip_id]; tdf=traj_by_trip[ev.trip_id]; row=tdf.iloc[int(len(tdf)*0.6)]; sid=row.true_segment_id; cur_node=edge_by_id[sid]['from_node_id']; distmap=nx.single_source_dijkstra_path_length(H,cur_node,cutoff=25000,weight='length_m')
    v=veh_idx.loc[tr.vehicle_id]; compatible=[]
    for s in stations.itertuples():
        elig=(v.vehicle_type in s.supported_vehicle_type and ((ev.service_type=='CHARGING' and 'CHARGING' in s.station_type) or (ev.service_type=='BATTERY_SWAP' and 'SWAP' in s.station_type)))
        d=distmap.get(s.access_node_id)
        cand_labels.append({'event_id':ev.event_id,'station_id':s.station_id,'eligible':bool(elig and d is not None),'reason':'ELIGIBLE' if elig and d is not None else ('INCOMPATIBLE' if not elig else 'UNREACHABLE')})
        if elig and d is not None: compatible.append((d,s))
    compatible=sorted(compatible,key=lambda x:x[0])[:6]
    scored=[]
    for d,s in compatible:
        # destination route reference from station
        try: sd=nx.shortest_path_length(H,s.access_node_id,tr.destination_node_id,weight='length_m')
        except: sd=float('inf')
        direct=max(1,float(tr.planned_network_distance_m)*(1-0.6)); detour=max(0,d+sd-direct) if math.isfinite(sd) else 99999
        # nearest status record by simple timestamp within generated grid
        es=datetime.fromisoformat(ev.timestamp); k=max(0,min(108,round((es-start0).total_seconds()/600))); st=status[(status.station_id==s.station_id)].iloc[k]; qq=qdf[(qdf.station_id==s.station_id)].iloc[k]
        eta=d/1000/30*60; total=eta+qq.estimated_wait_min+detour/1000/30*60; feasible=(d/1000 <= battery[battery.trip_id==ev.trip_id].iloc[int(len(tdf)*0.6)].estimated_remaining_range_km)
        score=total + (0 if feasible else 1000) + (0 if st.operating_status=='OPEN' else 1000)
        ranking.append({'event_id':ev.event_id,'station_id':s.station_id,'route_distance_m_ref':round(d,1),'eta_min_ref':round(eta,2),'detour_m_ref':round(detour,1),'queue_wait_min':qq.estimated_wait_min,'available_slots':st.available_slots,'operating_status':st.operating_status,'soc_feasible':bool(feasible),'ranking_cost_label':round(score,3)})
        scored.append((score,s.station_id))
    if scored: rec_labels.append({'event_id':ev.event_id,'reference_station_id':min(scored)[1],'label_method':'minimum_reference_cost_with_feasibility_and_operating_status'})
pd.DataFrame(cand_labels).to_csv(ROOT/'labels/candidate_labels.csv',index=False); ranking=pd.DataFrame(ranking); ranking.to_csv(ROOT/'training/ranking_reference.csv',index=False); pd.DataFrame(rec_labels).to_csv(ROOT/'labels/recommendation_labels.csv',index=False)
# splits by trip to avoid leakage
trip_ids=list(trips.trip_id); rng.shuffle(trip_ids); n=len(trip_ids); train=set(trip_ids[:int(.7*n)]); val=set(trip_ids[int(.7*n):int(.85*n)]); test=set(trip_ids[int(.85*n):])
splits=pd.DataFrame([{'trip_id':t,'split':'train' if t in train else 'validation' if t in val else 'test'} for t in trips.trip_id]); splits.to_csv(ROOT/'training/trip_splits.csv',index=False)
# demand training feature snapshot separated from label
feat=[]
for ev in demand.itertuples():
    tr=trips.set_index('trip_id').loc[ev.trip_id]; bg=bgroup.get_group(ev.trip_id).reset_index(drop=True); ix=min(len(bg)-1,int(len(bg)*.6)); rr=bg.iloc[ix]; v=veh_idx.loc[tr.vehicle_id]
    feat.append({'event_id':ev.event_id,'trip_id':ev.trip_id,'timestamp':ev.timestamp,'soc_pct':rr.soc_pct,'estimated_remaining_range_km':rr.estimated_remaining_range_km,'remaining_trip_distance_km':max(0,tr.planned_network_distance_m/1000-rr.distance_travelled_km),'consumption_wh_per_km':v.consumption_wh_per_km,'minimum_safe_soc_pct':v.minimum_safe_soc_pct,'swap_supported':v.swap_supported})
pd.DataFrame(feat).merge(splits,on='trip_id').to_csv(ROOT/'training/demand_features.csv',index=False)
# map matching training split by trip, labels separate
mm_train=pd.DataFrame(cand_rows).merge(gps[['observation_id','trip_id']],on='observation_id').merge(splits,on='trip_id'); mm_train.to_csv(ROOT/'training/map_matching_candidates_with_split.csv.gz',index=False,compression='gzip')
# scenarios actual linkage
scen=trips.groupby('scenario_id').agg(trip_count=('trip_id','count'),example_trip_id=('trip_id','first')).reset_index(); scen['data_evidence']='trip + trajectory + GPS + SOC + temporal station/traffic/realtime datasets'; scen.to_csv(ROOT/'scenarios/scenario_coverage.csv',index=False)
# topology stats
roadstats={'source':'hanoi-patched.osm.pbf','road_line_features':int(len(roads)),'directed_road_segments':int(len(segs)),'road_nodes':int(len(nodes)),'usable_directed_segments':int(len(usable)),'graph_nodes':H.number_of_nodes(),'graph_edges':H.number_of_edges(),'largest_weak_component_nodes':len(comp),'bbox':{'min_lon':float(nodes.longitude.min()),'min_lat':float(nodes.latitude.min()),'max_lon':float(nodes.longitude.max()),'max_lat':float(nodes.latitude.max())},'changed_line_features_vs_baseline':len(diffs)}
json.dump(roadstats,open(ROOT/'map/processed/road_network_stats.json','w'),indent=2)
# counts
all_counts={'drivers':len(drivers),'vehicles':len(vehicles),'trips':len(trips),'true_trajectory_points':len(trajectories),'gps_observations':len(gps),'soc_history':len(battery),'stations':len(stations),'station_status':len(status),'queue_status':len(qdf),'traffic_snapshots':len(traffic),'realtime_events':len(re),'map_matching_candidates':len(cand_rows),'demand_labels':len(demand),'ranking_reference':len(ranking),'road_nodes':len(nodes),'road_segments':len(segs)}
json.dump(all_counts,open(ROOT/'validation/data_counts.json','w'),indent=2)
print(json.dumps({'pbf':{'baseline':stats_base,'patched':stats_patch},'road':roadstats,'counts':all_counts},ensure_ascii=False,indent=2))
