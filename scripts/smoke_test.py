#!/usr/bin/env python3
"""
OSRM Smoke Test Script

Tests OSRM with Dataset V1 GPS observations.
Uses hanoi-baseline.osm.pbf (primary map).

Usage:
    python scripts/smoke_test.py
    make smoke
"""
import gzip
import json
import sys
from pathlib import Path

import httpx

DATASET_PATH = Path("dataset_v1")
OSRM_URL = "http://localhost:5000"


def load_gps_observations():
    """Load GPS observations from Dataset V1."""
    gps_file = DATASET_PATH / "gps" / "gps_observations.csv.gz"
    observations = []
    with gzip.open(gps_file, "rt", encoding="utf-8") as f:
        header = f.readline().strip().split(",")
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 6:
                obs = dict(zip(header, parts))
                observations.append(obs)
    return observations


async def test_osrm_nearest(lat: float, lon: float) -> dict:
    """Test OSRM nearest service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{OSRM_URL}/nearest/v1/driving/{lon},{lat}")
            return {"status": response.status_code, "data": response.json()}
    except Exception as e:
        return {"error": str(e)}


async def test_osrm_route(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Test OSRM route service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{OSRM_URL}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}",
                params={"overview": "simplified"}
            )
            return {"status": response.status_code, "data": response.json()}
    except Exception as e:
        return {"error": str(e)}


async def test_osrm_match(gps_points: list[dict]) -> dict:
    """Test OSRM match service with a sequence of GPS points."""
    try:
        coords = ";".join(f'{p["longitude"]},{p["latitude"]}' for p in gps_points)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{OSRM_URL}/match/v1/driving/{coords}",
                params={"overview": "simplified", "steps": "false", "gps_precision": 10}
            )
            return {"status": response.status_code, "data": response.json()}
    except Exception as e:
        return {"error": str(e)}


async def run_smoke_tests():
    """Run all smoke tests."""
    print("=" * 60)
    print("OSRM SMOKE TEST - Dataset V1 GPS")
    print("=" * 60)

    # Check OSRM availability
    print(f"\n[1] Checking OSRM at {OSRM_URL}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{OSRM_URL}/route/v1/driving/0,0")
            print(f"    OSRM reachable: HTTP {r.status_code}")
    except Exception as e:
        print(f"    ERROR: OSRM not reachable: {e}")
        print("    Start OSRM with: docker compose up osrm")
        return

    # Load data
    print("\n[2] Loading Dataset V1 GPS observations...")
    gps_obs = load_gps_observations()
    print(f"    Total GPS observations: {len(gps_obs):,}")

    # Select T0001 trip observations
    t0001_obs = [o for o in gps_obs if o.get("trip_id") == "T0001"]
    if not t0001_obs:
        trip_counts = {}
        for obs in gps_obs:
            trip_id = obs.get("trip_id", "")
            trip_counts[trip_id] = trip_counts.get(trip_id, 0) + 1
        sorted_trips = sorted(trip_counts.items(), key=lambda x: x[1], reverse=True)
        if sorted_trips:
            best_trip = sorted_trips[0][0]
            sample_obs = [o for o in gps_obs if o.get("trip_id") == best_trip][:20]
        else:
            sample_obs = gps_obs[:20]
    else:
        sample_obs = t0001_obs[:20]

    print(f"    Sample observations: {len(sample_obs)}")
    if sample_obs:
        first = sample_obs[0]
        print(f"    First point: lat={first.get('latitude')}, lon={first.get('longitude')}")

    # Test nearest
    print("\n[3] Testing OSRM nearest...")
    if sample_obs:
        first = sample_obs[0]
        lat, lon = float(first["latitude"]), float(first["longitude"])
        result = await test_osrm_nearest(lat, lon)
        if "error" in result:
            print(f"    ERROR: {result['error']}")
        else:
            print(f"    Status: HTTP {result['status']}")
            if result["status"] == 200:
                data = result["data"]
                if data.get("code") == "Ok":
                    print(f"    MATCHED: Waypoint index {data['waypoints'][0]['waypoint_index']}")
                else:
                    print(f"    Response: {json.dumps(data)}")

    # Test route
    print("\n[4] Testing OSRM route...")
    if len(sample_obs) >= 2:
        p1, p2 = sample_obs[0], sample_obs[len(sample_obs) // 2]
        lat1, lon1 = float(p1["latitude"]), float(p1["longitude"])
        lat2, lon2 = float(p2["latitude"]), float(p2["longitude"])
        result = await test_osrm_route(lat1, lon1, lat2, lon2)
        if "error" in result:
            print(f"    ERROR: {result['error']}")
        else:
            print(f"    Status: HTTP {result['status']}")
            if result["status"] == 200:
                data = result["data"]
                if data.get("code") == "Ok":
                    route = data["routes"][0]
                    print(f"    ROUTE: distance={route['distance']:.1f}m, duration={route['duration']:.1f}s")
                else:
                    print(f"    Response: {json.dumps(data)}")

    # Test map matching
    print("\n[5] Testing OSRM Match (map matching)...")
    if len(sample_obs) >= 3:
        match_points = sample_obs[:10]
        result = await test_osrm_match(match_points)
        if "error" in result:
            print(f"    ERROR: {result['error']}")
        else:
            print(f"    Status: HTTP {result['status']}")
            if result["status"] == 200:
                data = result["data"]
                if data.get("code") == "Ok":
                    tracepoints = data.get("tracepoints") or []
                    matched = [tp for tp in tracepoints if tp is not None]
                    print(f"    MATCHED tracepoints: {len(matched)}/{len(tracepoints)}")
                    if data.get("matchings"):
                        print(f"    Total distance: {data['matchings'][0]['distance']:.1f}m")
                else:
                    print(f"    Response: {json.dumps(data)}")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_smoke_tests())
