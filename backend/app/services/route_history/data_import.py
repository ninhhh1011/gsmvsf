#!/usr/bin/env python
"""
Import dataset_v1 trajectories into route_history_db
===============================================

This script:
1. Reads true_trajectories.csv.gz
2. Groups by trajectory_id
3. Generates H3 signatures
4. Creates directed road segment sequences
5. Bulk inserts into PostgreSQL
6. Builds route families

Usage:
    python -m backend.app.services.route_history.data_import \
        --dataset dataset_v1 \
        --batch-size 500
"""

import argparse
import gzip
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import time

# Add backend to path - go up 3 levels from app/services/route_history/
import os
import sys
_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _path)

from app.config import settings
from app.services.route_history.repository import RouteHistoryRepository
from app.services.route_history.signature import H3SignatureGenerator
from app.services.route_history.families import RouteFamilyCluster, RouteFamilyMember
from app.services.route_history.similarity import RoadLevelSimilarity, SegmentInfo


def load_trajectories(dataset_path: Path, max_routes: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load and group trajectories by trajectory_id."""
    trajectories_path = dataset_path / "trajectories" / "true_trajectories.csv.gz"

    if not trajectories_path.exists():
        raise FileNotFoundError(f"Trajectories file not found: {trajectories_path}")

    trajectories: Dict[str, Dict[str, Any]] = {}

    print(f"Loading trajectories from {trajectories_path}...")
    with gzip.open(trajectories_path, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            traj_id = row["trajectory_id"]

            if traj_id not in trajectories:
                trajectories[traj_id] = {
                    "trajectory_id": traj_id,
                    "trip_id": row["trip_id"],
                    "points": [],
                    "first_timestamp": row["timestamp"],
                    "last_timestamp": row["timestamp"],
                }

            traj = trajectories[traj_id]

            # Track origin and destination
            if "origin_lat" not in traj:
                traj["origin_lat"] = float(row["true_latitude"])
                traj["origin_lng"] = float(row["true_longitude"])

            traj["dest_lat"] = float(row["true_latitude"])
            traj["dest_lng"] = float(row["true_longitude"])
            traj["last_timestamp"] = row["timestamp"]

            # Track points
            traj["points"].append({
                "timestamp": row["timestamp"],
                "lat": float(row["true_latitude"]),
                "lng": float(row["true_longitude"]),
                "segment_id": row["true_segment_id"],
                "speed_kmh": float(row["speed_kmh"]),
                "heading_deg": float(row["heading_deg"]),
                "direction": row["travel_direction"],
            })

            if max_routes and len(trajectories) >= max_routes:
                break

    # Filter routes with insufficient segments
    result = []
    for traj_id, data in trajectories.items():
        if len(data["points"]) >= 2:
            result.append(data)

    return result


def build_route_record(data: Dict[str, Any], h3_gen: H3SignatureGenerator) -> Dict[str, Any]:
    """Build a route record from trajectory data."""
    points = data["points"]

    # Extract ordered segment IDs
    segment_ids = []
    total_distance = 0.0
    prev_end = None

    for point in points:
        seg_id = point["segment_id"]
        if seg_id and seg_id != "NONE":
            # Assume 100m per segment for now
            segment_ids.append(seg_id)
            total_distance += 100.0

    # Build coordinates for H3 signature
    coords = [(p["lat"], p["lng"]) for p in points[:50]]  # Limit for performance

    # Generate H3 signature
    h3_cells = []
    if len(coords) >= 2:
        try:
            sig = h3_gen.signature_from_coords(data["trajectory_id"], coords)
            h3_cells = list(sig.hex_sequence)
        except Exception as e:
            print(f"  Warning: Could not generate H3 signature: {e}")

    # Parse timestamps
    started_at = datetime.fromisoformat(data["first_timestamp"].replace("Z", "+00:00"))
    ended_at = datetime.fromisoformat(data["last_timestamp"].replace("Z", "+00:00"))

    return {
        "route_id": data["trajectory_id"],
        "trip_id": data["trip_id"],
        "driver_id": f"DRIVER_{data['trip_id'][:4]}",
        "started_at": started_at,
        "ended_at": ended_at,
        "origin_lat": data["origin_lat"],
        "origin_lng": data["origin_lng"],
        "dest_lat": data["dest_lat"],
        "dest_lng": data["dest_lng"],
        "total_distance_m": total_distance,
        "segment_ids": segment_ids,
        "h3_cells": h3_cells,
    }


def import_routes(
    repo: RouteHistoryRepository,
    routes: List[Dict[str, Any]],
    batch_size: int = 500
) -> Dict[str, int]:
    """Import routes in batches."""
    stats = {
        "routes_processed": 0,
        "routes_inserted": 0,
        "families_created": 0,
        "errors": 0,
    }

    total = len(routes)
    print(f"\nImporting {total} routes in batches of {batch_size}...")

    for i in range(0, total, batch_size):
        batch = routes[i:i+batch_size]
        try:
            inserted = repo.bulk_insert_routes(batch)
            stats["routes_inserted"] += inserted
            stats["routes_processed"] += len(batch)

            if (i + batch_size) % 1000 == 0 or i + batch_size >= total:
                print(f"  Processed {min(i + batch_size, total)}/{total} routes")
        except Exception as e:
            print(f"  Error in batch {i}-{i+batch_size}: {e}")
            stats["errors"] += len(batch)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Import route history from dataset_v1")
    parser.add_argument("--dataset", default="dataset_v1", help="Dataset path")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for inserts")
    parser.add_argument("--max-routes", type=int, help="Maximum routes to import")

    args = parser.parse_args()

    dataset_path = Path(args.dataset)

    # Create repository
    repo_url = settings.route_history_database_url_sync
    print(f"Connecting to: {repo_url}")
    repo = RouteHistoryRepository(repo_url)

    # Initialize H3 generator
    h3_gen = H3SignatureGenerator()

    # Load trajectories
    start_time = time.perf_counter()
    trajectories = load_trajectories(dataset_path, args.max_routes)
    load_time = time.perf_counter() - start_time
    print(f"Loaded {len(trajectories)} trajectories in {load_time:.1f}s")

    if not trajectories:
        print("No trajectories to import")
        return

    # Build route records
    print("\nBuilding route records...")
    build_start = time.perf_counter()
    routes = []
    for i, traj in enumerate(trajectories):
        route = build_route_record(traj, h3_gen)
        routes.append(route)
        if (i + 1) % 1000 == 0:
            print(f"  Built {i+1}/{len(trajectories)} records")

    build_time = time.perf_counter() - build_start
    print(f"Built {len(routes)} route records in {build_time:.1f}s")

    # Import routes
    import_start = time.perf_counter()
    stats = import_routes(repo, routes, args.batch_size)
    import_time = time.perf_counter() - import_start
    print(f"Imported in {import_time:.1f}s")

    # Get final stats
    final_stats = repo.get_stats()

    print("\n" + "="*60)
    print("IMPORT COMPLETE")
    print("="*60)
    print(f"Routes processed: {stats['routes_processed']}")
    print(f"Routes inserted: {stats['routes_inserted']}")
    print(f"Errors: {stats['errors']}")
    print(f"\nDatabase statistics:")
    for key, value in final_stats.items():
        print(f"  {key}: {value}")
    print(f"\nTotal time: {load_time + build_time + import_time:.1f}s")


if __name__ == "__main__":
    main()
