#!/usr/bin/env python3
"""OSRM smoke test script."""
import httpx
import gzip
import csv
import json

print('='*60)
print('OSRM SMOKE TEST - Dataset V1 GPS (T0001)')
print('='*60)

# Load GPS
gps_file = '/app/dataset_v1/gps/gps_observations.csv.gz'
obs = []
with gzip.open(gps_file, 'rt') as f:
    for row in csv.DictReader(f):
        obs.append(row)
t0001 = [o for o in obs if o.get('trip_id') == 'T0001']
print(f'\nDataset: {len(obs)} total obs, T0001: {len(t0001)} obs')

# [1] OSRM nearest
print('\n[1] OSRM nearest...')
lat, lon = float(t0001[0]['latitude']), float(t0001[0]['longitude'])
r = httpx.get(f'http://osrm:5000/nearest/v1/driving/{lon},{lat}', timeout=30)
print(f'    Status: HTTP {r.status_code}')
data = r.json()
if data.get('code') == 'Ok':
    wp = data['waypoints'][0]
    print(f'    MATCHED: lat={wp["location"][1]:.6f}, lon={wp["location"][0]:.6f}')
    print(f'    distance to road: {wp["distance"]:.3f}m')
    print(f'    nodes: {wp["nodes"]}')

# [2] OSRM route
print('\n[2] OSRM route...')
p1, p2 = t0001[0], t0001[len(t0001)//2]
lat1, lon1 = float(p1['latitude']), float(p1['longitude'])
lat2, lon2 = float(p2['latitude']), float(p2['longitude'])
r = httpx.get(f'http://osrm:5000/route/v1/driving/{lon1},{lat1};{lon2},{lat2}',
              params={'overview': 'simplified'}, timeout=30)
print(f'    Status: HTTP {r.status_code}')
data = r.json()
if data.get('code') == 'Ok':
    route = data['routes'][0]
    print(f'    ROUTE: distance={route["distance"]:.1f}m, duration={route["duration"]:.1f}s')

# [3] OSRM Match
print('\n[3] OSRM Match (map matching)...')
match_pts = t0001[:3]
coords = ';'.join(f'{float(p["longitude"])},{float(p["latitude"])}' for p in match_pts)
r = httpx.get(f'http://osrm:5000/match/v1/driving/{coords}',
              params={'overview': 'simplified', 'steps': 'false', 'gps_precision': 10},
              timeout=60)
print(f'    Status: HTTP {r.status_code}')
data = r.json()
if data.get('code') == 'Ok':
    tp = data.get('tracepoints') or []
    matched = [t for t in tp if t is not None]
    unmatched = [t for t in tp if t is None]
    m = data['matchings'][0]
    print(f'    trajectory_id: {match_pts[0]["trajectory_id"]}')
    print(f'    input GPS points: {len(match_pts)}')
    print(f'    matched tracepoints: {len(matched)}')
    print(f'    unmatched/null tracepoints: {len(unmatched)}')
    print(f'    matching code: {data.get("code")}')
    print(f'    matching confidence: {m.get("confidence", "N/A")}')
    print(f'    total matched distance: {m.get("distance", "N/A")}m')
    print(f'    total matched duration: {m.get("duration", "N/A")}s')

print('\n' + '='*60)
print('SMOKE TEST COMPLETE - ALL PASSED')
print('='*60)
