"""
Route History Data Importer
==========================

Imports historical route data from dataset_v1 into PostgreSQL.

Usage:
    python -m app.services.route_history.importer \
        --dataset dataset_v1 \
        --database-url postgresql://... \
        --max-routes 10000
"""

import argparse
import gzip
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import sys

from .repository import RouteHistoryRepository
from .signature import H3SignatureGenerator
from .families import RouteFamilyCluster
from .similarity import RoadLevelSimilarity


class RouteHistoryImporter:
    """
    Imports route data from dataset_v1 into PostgreSQL.

    Flow:
    1. Load trajectories from true_trajectories.csv.gz
    2. Load road segments from road_segments.csv.gz
    3. Generate H3 signatures
    4. Build route families
    5. Persist to PostgreSQL
    """

    def __init__(
        self,
        repository: RouteHistoryRepository,
        segment_csv_path: str
    ):
        self.repository = repository
        self.h3_generator = H3SignatureGenerator()
        self.similarity_calc = RoadLevelSimilarity()
        self.family_cluster = RouteFamilyCluster(
            similarity_calculator=self.similarity_calc,
            join_threshold=0.6
        )

        # Load segments
        self._load_segments(Path(segment_csv_path))

    def _load_segments(self, segments_path: Path) -> None:
        """Load road segments from CSV."""
        print(f"Loading segments from {segments_path}...")

        segment_data = []
        with gzip.open(segments_path, "rt") as f:
            reader = csv.DictReader(f)
            for row in reader:
                segment_data.append(row)

        self.similarity_calc.load_segments(segment_data)
        print(f"  Loaded {len(segment_data)} segments")

    def import_from_dataset(
        self,
        dataset_path: Path,
        max_routes: Optional[int] = None,
        batch_size: int = 1000
    ) -> Dict[str, int]:
        """
        Import routes from dataset_v1.

        Args:
            dataset_path: Path to dataset_v1 directory
            max_routes: Maximum number of routes to import
            batch_size: Batch size for bulk inserts

        Returns:
            Statistics about the import
        """
        stats = {
            "routes_processed": 0,
            "routes_inserted": 0,
            "families_created": 0,
            "errors": 0
        }

        trajectories_path = dataset_path / "trajectories" / "true_trajectories.csv.gz"

        if not trajectories_path.exists():
            print(f"Error: Trajectories file not found: {trajectories_path}")
            return stats

        # Group trajectories by trajectory_id
        print(f"Loading trajectories from {trajectories_path}...")
        trajectories = self._load_trajectories(trajectories_path, max_routes)
        print(f"  Loaded {len(trajectories)} unique trajectories")

        # Process in batches
        batch = []
        for route_data in trajectories:
            batch.append(route_data)

            if len(batch) >= batch_size:
                inserted = self._process_batch(batch)
                stats["routes_inserted"] += inserted
                stats["routes_processed"] += len(batch)
                batch = []

                if stats["routes_processed"] % 5000 == 0:
                    print(f"  Processed {stats['routes_processed']} routes...")

        # Process remaining
        if batch:
            inserted = self._process_batch(batch)
            stats["routes_inserted"] += inserted
            stats["routes_processed"] += len(batch)

        # Finalize families
        self.family_cluster.finalize_weights()
        stats["families_created"] = len(self.family_cluster.families)

        # Persist families to database
        self._persist_families()

        print(f"\nImport complete:")
        print(f"  Routes processed: {stats['routes_processed']}")
        print(f"  Routes inserted: {stats['routes_inserted']}")
        print(f"  Families created: {stats['families_created']}")
        print(f"  Errors: {stats['errors']}")

        return stats

    def _load_trajectories(
        self,
        trajectories_path: Path,
        max_routes: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Load and group trajectories."""
        trajectories: Dict[str, Dict[str, Any]] = {}

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

                # Track origin and destination
                if not trajectories[traj_id].get("origin_lat"):
                    trajectories[traj_id]["origin_lat"] = float(row["true_latitude"])
                    trajectories[traj_id]["origin_lng"] = float(row["true_longitude"])

                trajectories[traj_id]["dest_lat"] = float(row["true_latitude"])
                trajectories[traj_id]["dest_lng"] = float(row["true_longitude"])
                trajectories[traj_id]["last_timestamp"] = row["timestamp"]

                # Track segments in order
                trajectories[traj_id]["points"].append({
                    "timestamp": row["timestamp"],
                    "lat": float(row["true_latitude"]),
                    "lng": float(row["true_longitude"]),
                    "segment_id": row["true_segment_id"],
                    "speed_kmh": float(row["speed_kmh"]),
                    "heading_deg": float(row["heading_deg"]),
                    "direction": row["travel_direction"],
                })

        # Filter routes with insufficient segments
        result = []
        for traj_id, data in trajectories.items():
            if len(data["points"]) >= 2:
                result.append(data)

            if max_routes and len(result) >= max_routes:
                break

        return result

    def _process_batch(self, batch: List[Dict[str, Any]]) -> int:
        """Process a batch of routes."""
        routes_to_insert = []

        for route_data in batch:
            try:
                route = self._build_route(route_data)
                routes_to_insert.append(route)

                # Add to family cluster
                self._add_to_family(route)
            except Exception as e:
                print(f"  Error processing route {route_data['trajectory_id']}: {e}")

        if routes_to_insert:
            return self.repository.bulk_insert_routes(routes_to_insert)

        return 0

    def _build_route(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Build a route record from trajectory data."""
        points = data["points"]

        # Extract ordered segment IDs
        segment_ids = []
        segment_lookup = self.similarity_calc.segment_lookup
        total_distance = 0.0

        prev_end = None
        for point in points:
            seg_id = point["segment_id"]
            if seg_id in segment_lookup:
                seg = segment_lookup[seg_id]

                if prev_end is None:
                    prev_end = (seg.end_lat, seg.end_lng)
                else:
                    total_distance += seg.length_m

                segment_ids.append(seg_id)

        # Build coordinates for H3 signature
        coords = []
        for point in points[:50]:  # Limit for performance
            coords.append((point["lat"], point["lng"]))

        # Generate H3 signature
        h3_cells = []
        if len(coords) >= 2:
            try:
                sig = self.h3_generator.signature_from_coords(
                    data["trajectory_id"], coords
                )
                h3_cells = list(sig.hex_sequence)
            except:
                pass

        # Parse timestamps
        started_at = datetime.fromisoformat(data["first_timestamp"])
        ended_at = datetime.fromisoformat(data["last_timestamp"])

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

    def _add_to_family(self, route: Dict[str, Any]) -> None:
        """Add route to family cluster."""
        time_weight = 1.0  # Could be calculated from timestamp
        recency_weight = 1.0  # Could be calculated from days ago

        self.family_cluster.add_route(
            route_id=route["route_id"],
            driver_id=route["driver_id"],
            timestamp=route["started_at"],
            origin=(route["origin_lat"], route["origin_lng"]),
            destination=(route["dest_lat"], route["dest_lng"]),
            segment_ids=route["segment_ids"],
            total_distance_m=route["total_distance_m"],
            time_weight=time_weight,
            recency_weight=recency_weight
        )

    def _persist_families(self) -> None:
        """Persist route families to database."""
        for family in self.family_cluster.families.values():
            self.repository.insert_route_family(
                family_id=family.family_id,
                representative_route_id=family.representative_route_id,
                origin_lat=family.origin_context[0],
                origin_lng=family.origin_context[1],
                dest_lat=family.dest_context[0],
                dest_lng=family.dest_context[1],
                direction_bearing=family.direction_bearing,
                trip_count=family.trip_count,
                unique_driver_count=family.unique_driver_count,
                weighted_support=family.weighted_support
            )

            # Add members
            for member in family.members:
                self.repository.add_family_member(
                    family_id=family.family_id,
                    route_id=member.route_id,
                    time_weight=member.time_weight,
                    recency_weight=member.recency_weight
                )


def main():
    parser = argparse.ArgumentParser(description="Import route history from dataset_v1")
    parser.add_argument("--dataset", default="dataset_v1", help="Dataset path")
    parser.add_argument("--database-url", help="PostgreSQL connection URL")
    parser.add_argument("--max-routes", type=int, help="Maximum routes to import")
    parser.add_argument("--init-schema", action="store_true", help="Initialize database schema")

    args = parser.parse_args()

    # Get database URL
    database_url = args.database_url
    if not database_url:
        # Try environment or default
        import os
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            database_url = "postgresql://postgres:postgres@localhost:5432/ev_recommendation"

    # Create repository
    repo = RouteHistoryRepository(database_url)

    # Initialize schema if requested
    if args.init_schema:
        print("Initializing database schema...")
        repo.initialize_schema()
        print("Schema initialized.")

    # Create importer
    dataset_path = Path(args.dataset)
    segments_path = dataset_path / "map" / "processed" / "road_segments.csv.gz"

    if not segments_path.exists():
        print(f"Error: Segments file not found: {segments_path}")
        sys.exit(1)

    importer = RouteHistoryImporter(repo, str(segments_path))

    # Import data
    stats = importer.import_from_dataset(dataset_path, args.max_routes)

    # Print final stats
    print("\nDatabase statistics:")
    db_stats = repo.get_stats()
    for key, value in db_stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
