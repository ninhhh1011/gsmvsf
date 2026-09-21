"""
Realtime GPS replay script.

Replays Dataset V1 trajectories through the actual FastAPI realtime endpoint.
Supports accelerated replay (no real-time waits).

Usage:
    python scripts/replay_realtime.py --trajectory TRJ0001 --speed 10
    python scripts/replay_realtime.py --trajectory TRJ0001 --trajectory TRJ0002 --speed 5
    python scripts/replay_realtime.py --all --speed 10
"""

import asyncio
import argparse
import csv
import gzip
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import httpx

# Configuration
API_BASE = "http://127.0.0.1:8000/api/v1"
DATASET_PATH = Path("dataset_v1")
GPS_FILE = DATASET_PATH / "gps" / "gps_observations.csv.gz"


@dataclass
class GPSObservation:
    """Single GPS observation."""
    observation_id: str
    trajectory_id: str
    trip_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_kmh: float = None
    heading_deg: float = None


@dataclass
class ReplayResult:
    """Result of replaying one trajectory."""
    trajectory_id: str
    total_observations: int = 0
    match_calls: int = 0
    match_success: int = 0
    match_null: int = 0
    warming_up_count: int = 0
    gps_accepted_count: int = 0
    stationary_suppressed_count: int = 0
    status_counts: dict = field(default_factory=dict)
    trigger_reasons: dict = field(default_factory=dict)
    match_latencies_ms: list = field(default_factory=list)
    wall_time_ms: float = 0.0


def load_trajectory(trajectory_id: str) -> list[GPSObservation]:
    """Load observations for one trajectory."""
    observations = []
    with gzip.open(GPS_FILE, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['trajectory_id'] != trajectory_id:
                continue
            try:
                obs = GPSObservation(
                    observation_id=row['observation_id'],
                    trajectory_id=row['trajectory_id'],
                    trip_id=row['trip_id'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    latitude=float(row['latitude']),
                    longitude=float(row['longitude']),
                    speed_kmh=float(row['speed_kmh']) if row.get('speed_kmh') else None,
                    heading_deg=float(row['heading_deg']) if row.get('heading_deg') else None,
                )
                observations.append(obs)
            except Exception:
                continue
    return sorted(observations, key=lambda x: x.timestamp)


def load_all_trajectory_ids() -> list[str]:
    """Load all trajectory IDs."""
    ids = []
    with gzip.open(GPS_FILE, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        seen = set()
        for row in reader:
            tid = row['trajectory_id']
            if tid not in seen:
                seen.add(tid)
                ids.append(tid)
    return ids


async def replay_trajectory(
    client: httpx.AsyncClient,
    trajectory_id: str,
    speed_multiplier: float = 1.0,
    driver_prefix: str = "replay",
) -> ReplayResult:
    """Replay one trajectory through the API."""
    observations = load_trajectory(trajectory_id)
    if not observations:
        return ReplayResult(trajectory_id=trajectory_id)

    result = ReplayResult(trajectory_id=trajectory_id)
    result.total_observations = len(observations)

    # Use trajectory_id as driver_id (prefixed to avoid collision)
    driver_id = f"{driver_prefix}_{trajectory_id}"

    # Reset any existing state
    try:
        await client.delete(f"{API_BASE}/drivers/{driver_id}/location")
    except Exception:
        pass

    with open(DATASET_PATH / "trips/trips.csv", encoding="utf-8") as f:
        trips = {row["trip_id"]: row for row in csv.DictReader(f)}
    vehicle_id = trips[observations[0].trip_id]["vehicle_id"]
    start_wall_time = time.time()
    prev_obs_time = None

    for obs in observations:
        # Calculate accelerated wait time
        if prev_obs_time and speed_multiplier > 0:
            real_delta = (obs.timestamp - prev_obs_time).total_seconds()
            wait_time = real_delta / speed_multiplier if speed_multiplier > 0 else 0
            if wait_time > 0:
                await asyncio.sleep(min(wait_time, 0.1))  # Cap at 100ms

        # Build request
        request = {
            "vehicle_id": vehicle_id,
            "observation_id": obs.observation_id,
            "timestamp": obs.timestamp.isoformat(),
            "latitude": obs.latitude,
            "longitude": obs.longitude,
        }
        if obs.speed_kmh:
            request["speed_kmh"] = obs.speed_kmh
        if obs.heading_deg:
            request["heading_deg"] = obs.heading_deg

        try:
            response = await client.post(
                f"{API_BASE}/drivers/{driver_id}/location",
                json=request,
                timeout=30.0,
            )

            response.raise_for_status()
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "UNKNOWN")
                result.status_counts[status] = result.status_counts.get(status, 0) + 1

                if status == "MATCHED":
                    result.match_calls += 1
                    if data.get("matched_position", {}).get("latitude"):
                        result.match_success += 1
                    else:
                        result.match_null += 1
                    lat = data.get("last_match_latency_ms")
                    if lat:
                        result.match_latencies_ms.append(lat)
                elif status == "GPS_ACCEPTED":
                    result.gps_accepted_count += 1
                elif status == "WARMING_UP":
                    result.warming_up_count += 1
                elif status == "GPS_ACCEPTED" and data.get("trigger_reason", "").startswith("STATIONARY"):
                    result.stationary_suppressed_count += 1

                # Track trigger reasons
                trigger = data.get("trigger_reason", "")
                if trigger:
                    result.trigger_reasons[trigger] = result.trigger_reasons.get(trigger, 0) + 1

        except Exception:
            raise

        prev_obs_time = obs.timestamp

    result.wall_time_ms = (time.time() - start_wall_time) * 1000

    return result


async def main():
    parser = argparse.ArgumentParser(description="Replay Dataset V1 trajectories through realtime API")
    parser.add_argument("--trajectory", "-t", action="append", help="Trajectory ID to replay")
    parser.add_argument("--all", "-a", action="store_true", help="Replay all trajectories")
    parser.add_argument("--speed", "-s", type=float, default=10.0, help="Speed multiplier (10 = 10x faster)")
    parser.add_argument("--driver-prefix", "-p", default="replay", help="Driver ID prefix")
    parser.add_argument("--limit", "-l", type=int, default=0, help="Limit number of trajectories")
    args = parser.parse_args()

    # Get trajectories to replay
    if args.all:
        trajectory_ids = load_all_trajectory_ids()
    elif args.trajectory:
        trajectory_ids = args.trajectory
    else:
        # Default: first 5
        trajectory_ids = load_all_trajectory_ids()[:5]

    if args.limit > 0:
        trajectory_ids = trajectory_ids[:args.limit]

    print(f"Replaying {len(trajectory_ids)} trajectories at {args.speed}x speed")
    print(f"API: {API_BASE}")
    print()

    # Check API health
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_BASE}/health", timeout=5.0)
            print(f"API health: {resp.status_code}")
        except Exception as e:
            print(f"Warning: API health check failed: {e}")
    print()

    # Replay trajectories
    results = []
    async with httpx.AsyncClient() as client:
        for i, tid in enumerate(trajectory_ids):
            print(f"[{i+1}/{len(trajectory_ids)}] Replaying {tid}...", end=" ")
            result = await replay_trajectory(client, tid, speed_multiplier=args.speed, driver_prefix=args.driver_prefix)
            results.append(result)
            print(f"done. Obs={result.total_observations}, Matches={result.match_calls}, "
                  f"Success={result.match_success}, Null={result.match_null}")

    # Aggregate results
    print()
    print("=" * 60)
    print("REPLAY SUMMARY")
    print("=" * 60)

    total_obs = sum(r.total_observations for r in results)
    total_matches = sum(r.match_calls for r in results)
    total_success = sum(r.match_success for r in results)
    total_null = sum(r.match_null for r in results)
    all_latencies = [l for r in results for l in r.match_latencies_ms]

    print(f"Trajectories: {len(results)}")
    print(f"Total observations: {total_obs}")
    print(f"Total Match calls: {total_matches}")
    print(f"Match success: {total_success} ({100*total_success/total_matches if total_matches else 0:.1f}%)")
    print(f"Match null: {total_null} ({100*total_null/total_matches if total_matches else 0:.1f}%)")


    if all_latencies:
        all_latencies.sort()
        print(f"Match latency mean: {sum(all_latencies)/len(all_latencies):.1f}ms")
        print(f"Match latency p50: {all_latencies[len(all_latencies)//2]:.1f}ms")
        print(f"Match latency p95: {all_latencies[int(len(all_latencies)*0.95)]:.1f}ms")

    # Status distribution
    print()
    print("Status distribution:")
    all_statuses = defaultdict(int)
    for r in results:
        for s, c in r.status_counts.items():
            all_statuses[s] += c
    for s, c in sorted(all_statuses.items()):
        print(f"  {s}: {c} ({100*c/total_obs:.1f}%)")

    # Save results
    output_file = Path("runtime/migration/replay_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump({
            "total_trajectories": len(results),
            "total_observations": total_obs,
            "total_match_calls": total_matches,
            "match_success": total_success,
            "match_null": total_null,
            "latencies": all_latencies,
        }, f, indent=2)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
