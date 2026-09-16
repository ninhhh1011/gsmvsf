#!/usr/bin/env python3
"""OSRM smoke test."""
import httpx, gzip, csv, json

print("="*60)
print("OSRM SMOKE TEST - Dataset V1 GPS (T0001)")
print("="*60)

obs = []
with gzip.open("/app/dataset_v1/gps/gps_observations.csv.gz", "rt") as f:
    for row in csv.DictReader(f):
        obs.append(row)
t0001 = [o for o in obs if o.get("trip_id") == "T0001"]
print("Dataset: {} total obs, T0001: {} obs".format(len(obs), len(t0001)))

# Nearest
lat, lon = float(t0001[0]["latitude"]), float(t0001[0]["longitude"])
r = httpx.get("http://osrm:5000/nearest/v1/driving/{},{}".format(lon, lat), timeout=30)
data = r.json()
print("\n[1] NEAREST: HTTP {}, code={}".format(r.status_code, data.get("code")))
if data.get("code") == "Ok":
    wp = data["waypoints"][0]
    print("    MATCHED: lat={:.6f}, lon={:.6f}".format(wp["location"][1], wp["location"][0]))
    print("    distance: {:.3f}m, nodes: {}".format(wp["distance"], wp["nodes"]))

# Route
p1, p2 = t0001[0], t0001[len(t0001)//2]
r = httpx.get("http://osrm:5000/route/v1/driving/{};{}/{};{}".format(
    p1["longitude"], p1["latitude"], p2["longitude"], p2["latitude"]),
    params={"overview": "simplified"}, timeout=30)
data = r.json()
print("[2] ROUTE: HTTP {}, code={}".format(r.status_code, data.get("code")))
if data.get("code") == "Ok":
    print("    distance={:.1f}m, duration={:.1f}s".format(
        data["routes"][0]["distance"], data["routes"][0]["duration"]))

# Match
mp = t0001[:3]
coords = ";".join("{:.6f},{:.6f}".format(float(p["longitude"]), float(p["latitude"])) for p in mp)
r = httpx.get("http://osrm:5000/match/v1/driving/{}".format(coords),
    params={"overview": "simplified", "steps": "false", "gps_precision": 10}, timeout=60)
data = r.json()
print("[3] MATCH: HTTP {}, code={}".format(r.status_code, data.get("code")))
if data.get("code") == "Ok":
    tp = data.get("tracepoints") or []
    matched = [t for t in tp if t is not None]
    m = data["matchings"][0]
    print("    trajectory_id: {}".format(mp[0]["trajectory_id"]))
    print("    input GPS points: {}".format(len(mp)))
    print("    matched tracepoints: {}".format(len(matched)))
    print("    unmatched/null tracepoints: {}".format(len(tp) - len(matched)))
    print("    matching code: {}".format(data.get("code")))
    print("    matching confidence: {}".format(m.get("confidence", "N/A")))
    print("    total matched distance: {}m".format(m.get("distance", "N/A")))
    print("    total matched duration: {}s".format(m.get("duration", "N/A")))

print("\n" + "="*60)
print("SMOKE TEST COMPLETE")
print("="*60)
