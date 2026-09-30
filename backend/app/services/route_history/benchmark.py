"""
Route History Scale Benchmark
===========================

Measures retrieval performance at different scales.

Generates synthetic routes and measures:
- H3 candidate retrieval
- Context filtering
- Detailed similarity comparisons
- Latency breakdown

Usage:
    python -m backend.app.services.route_history.benchmark \
        --routes 1000 \
        --scales 1000,10000
"""

import sys
import os
import random
import time
import gzip
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any
from pathlib import Path
from dataclasses import dataclass

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.route_history.signature import H3SignatureGenerator
from app.services.route_history.index import RouteInvertedIndex
from app.services.route_history.filters import HardFilters, TimeRecencyWeight, RouteMetadata
from app.services.route_history.similarity import RoadLevelSimilarity, SegmentInfo, RouteSegments
from app.services.route_history.families import RouteFamilyCluster


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    scale: int
    total_routes: int
    h3_candidate_routes: int
    routes_after_context_filter: int
    detailed_comparisons: int
    h3_lookup_ms: float
    filter_ms: float
    similarity_ms: float
    total_ms: float


# Hanoi area bounding box
HANOI_LAT_MIN = 20.95
HANOI_LAT_MAX = 21.15
HANOI_LNG_MIN = 105.70
HANOI_LNG_MAX = 105.95


def generate_random_coords() -> Tuple[float, float]:
    """Generate random coordinates in Hanoi area."""
    lat = random.uniform(HANOI_LAT_MIN, HANOI_LAT_MAX)
    lng = random.uniform(HANOI_LNG_MIN, HANOI_LNG_MAX)
    return (lat, lng)


def generate_route_geometry(num_points: int = 10) -> List[Tuple[float, float]]:
    """Generate a random route geometry."""
    coords = [generate_random_coords()]

    for _ in range(num_points - 1):
        # Move roughly in same direction
        prev_lat, prev_lng = coords[-1]
        lat = prev_lat + random.uniform(-0.002, 0.002)
        lng = prev_lng + random.uniform(-0.002, 0.002)
        # Clamp to bounds
        lat = max(HANOI_LAT_MIN, min(HANOI_LAT_MAX, lat))
        lng = max(HANOI_LNG_MIN, min(HANOI_LNG_MAX, lng))
        coords.append((lat, lng))

    return coords


def generate_synthetic_routes(n: int) -> List[Dict[str, Any]]:
    """Generate n synthetic historical routes."""
    routes = []

    # Define some "popular corridors" for more realistic clustering
    corridors = [
        # Nguyễn Trãi corridor
        [(21.0285, 105.8542), (21.0320, 105.8560), (21.0350, 105.8580), (21.0380, 105.8600)],
        # Tố Hữu corridor
        [(21.0150, 105.7850), (21.0180, 105.7880), (21.0210, 105.7910), (21.0240, 105.7940)],
        # Đại lộ Thăng Long
        [(21.0500, 105.7600), (21.0550, 105.7650), (21.0600, 105.7700), (21.0650, 105.7750)],
    ]

    for i in range(n):
        # 70% of routes follow a corridor, 30% are random
        if random.random() < 0.7:
            corridor = random.choice(corridors)
            coords = []
            for pt in corridor:
                # Add small variation
                lat = pt[0] + random.uniform(-0.0005, 0.0005)
                lng = pt[1] + random.uniform(-0.0005, 0.0005)
                coords.append((lat, lng))
            # Add intermediate points
            for _ in range(random.randint(2, 5)):
                idx = random.randint(0, len(coords) - 1)
                lat = coords[idx][0] + random.uniform(-0.001, 0.001)
                lng = coords[idx][1] + random.uniform(-0.001, 0.001)
                coords.insert(idx + 1, (lat, lng))
        else:
            coords = generate_route_geometry(random.randint(5, 15))

        origin = coords[0]
        dest = coords[-1]

        # Generate timestamp within last 7 days
        days_ago = random.randint(0, 7)
        timestamp = datetime.now() - timedelta(days=days_ago, hours=random.randint(0, 23))

        routes.append({
            "route_id": f"SYNTH_{i:06d}",
            "trip_id": f"TRIP_{i:06d}",
            "driver_id": f"DRIVER_{i % 50:03d}",  # 50 drivers
            "timestamp": timestamp,
            "origin_lat": origin[0],
            "origin_lng": origin[1],
            "dest_lat": dest[0],
            "dest_lng": dest[1],
            "coords": coords,
        })

    return routes


def run_benchmark(
    total_routes: int,
    query_routes: int = 10,
) -> BenchmarkResult:
    """Run benchmark with specified scale."""
    print(f"\n{'='*60}")
    print(f"Running benchmark with {total_routes:,} routes")
    print(f"{'='*60}")

    # Generate synthetic routes
    print("Generating synthetic routes...")
    routes = generate_synthetic_routes(total_routes)

    # Initialize components
    h3_gen = H3SignatureGenerator()
    inverted_index = RouteInvertedIndex()
    filters = HardFilters(origin_threshold_km=2.0, dest_threshold_km=2.0, days_window=7)
    weight_calc = TimeRecencyWeight()
    similarity_calc = RoadLevelSimilarity()

    # Create fake segments for similarity calculation
    for i in range(100):
        seg_id = f"SEG_{i:03d}"
        similarity_calc.segment_lookup[seg_id] = SegmentInfo(
            segment_id=seg_id,
            base_segment_id=f"BASE_{i:03d}",
            direction="FORWARD",
            length_m=100.0,
            start_lat=0, start_lng=0, end_lat=0, end_lng=0,
        )

    family_cluster = RouteFamilyCluster(
        similarity_calculator=similarity_calc,
        join_threshold=0.6
    )

    # Index all routes
    print(f"Indexing {len(routes)} routes...")
    index_start = time.perf_counter()

    for route in routes:
        coords = route["coords"]
        sig = h3_gen.signature_from_coords(route["route_id"], coords)
        inverted_index.add_route(route["route_id"], list(sig.hex_sequence))

        # Add to family cluster
        family_cluster.add_route(
            route_id=route["route_id"],
            driver_id=route["driver_id"],
            timestamp=route["timestamp"],
            origin=(route["origin_lat"], route["origin_lng"]),
            destination=(route["dest_lat"], route["dest_lng"]),
            segment_ids=[f"SEG_{i % 100:03d}" for i in range(len(coords))],  # Fake segments
            total_distance_m=len(coords) * 100.0,
        )

    index_ms = (time.perf_counter() - index_start) * 1000
    print(f"Indexing complete: {index_ms:.1f}ms")

    # Finalize families
    family_cluster.finalize_weights()

    # Run query benchmarks
    print(f"\nRunning {query_routes} query benchmarks...")

    total_h3_lookup_ms = 0
    total_filter_ms = 0
    total_similarity_ms = 0
    total_detailed_comparisons = 0

    query_times = []

    for q in range(query_routes):
        # Pick a random route as query
        query_route = random.choice(routes)
        query_coords = query_route["coords"]
        query_origin = (query_route["origin_lat"], query_route["origin_lng"])
        query_dest = (query_route["dest_lat"], query_route["dest_lng"])
        query_time = query_route["timestamp"]

        # H3 lookup
        h3_start = time.perf_counter()
        sig = h3_gen.signature_from_coords(f"QUERY_{q}", query_coords)
        h3_cells = list(sig.hex_sequence)
        h3_results = inverted_index.query_by_hexes(h3_cells, min_overlap=1)
        h3_lookup_ms = (time.perf_counter() - h3_start) * 1000
        total_h3_lookup_ms += h3_lookup_ms

        h3_candidate_ids = [r[0] for r in h3_results]

        # Context filtering
        filter_start = time.perf_counter()
        passing_candidates = []

        for route_id in h3_candidate_ids:
            route = next((r for r in routes if r["route_id"] == route_id), None)
            if route is None:
                continue

            metadata = RouteMetadata(
                route_id=route["route_id"],
                trip_id=route["trip_id"],
                driver_id=route["driver_id"],
                timestamp=route["timestamp"],
                origin_lat=route["origin_lat"],
                origin_lng=route["origin_lng"],
                destination_lat=route["dest_lat"],
                destination_lng=route["dest_lng"],
            )

            passed, _ = filters.apply_all_filters(
                query_origin[0], query_origin[1],
                query_dest[0], query_dest[1],
                query_time,
                metadata
            )

            if passed:
                passing_candidates.append(route)

        filter_ms = (time.perf_counter() - filter_start) * 1000
        total_filter_ms += filter_ms

        # Detailed similarity (simulated - just count)
        sim_start = time.perf_counter()
        detailed_comparisons = len(passing_candidates)

        # Simulate similarity calculation time
        for _ in passing_candidates:
            # In real impl, would do road-level similarity here
            time.sleep(0.00001)  # Simulate some work

        similarity_ms = (time.perf_counter() - sim_start) * 1000
        total_similarity_ms += similarity_ms
        total_detailed_comparisons += detailed_comparisons

        query_time_total = h3_lookup_ms + filter_ms + similarity_ms
        query_times.append(query_time_total)

        if q < 3 or q % 5 == 0:
            print(f"  Query {q+1}: {len(h3_candidate_ids)} H3 candidates, "
                  f"{len(passing_candidates)} after filter, "
                  f"{detailed_comparisons} detailed comparisons, "
                  f"{query_time_total:.1f}ms total")

    # Calculate averages
    avg_h3_ms = total_h3_lookup_ms / query_routes
    avg_filter_ms = total_filter_ms / query_routes
    avg_similarity_ms = total_similarity_ms / query_routes
    avg_total_ms = sum(query_times) / len(query_times)
    avg_detailed = total_detailed_comparisons / query_routes

    return BenchmarkResult(
        scale=total_routes,
        total_routes=total_routes,
        h3_candidate_routes=int(inverted_index.get_stats()["avg_routes_per_hex"] * len(h3_cells)),
        routes_after_context_filter=int(avg_detailed),
        detailed_comparisons=int(avg_detailed),
        h3_lookup_ms=avg_h3_ms,
        filter_ms=avg_filter_ms,
        similarity_ms=avg_similarity_ms,
        total_ms=avg_total_ms,
    )


def main():
    parser = argparse.ArgumentParser(description="Route History Scale Benchmark")
    parser.add_argument("--scales", default="100,1000,10000", help="Comma-separated scales")
    parser.add_argument("--query-routes", type=int, default=10, help="Queries per scale")
    parser.add_argument("--output", help="Output CSV file")

    args = parser.parse_args()

    scales = [int(s) for s in args.scales.split(",")]

    results = []

    for scale in scales:
        result = run_benchmark(scale, args.query_routes)
        results.append(result)

    # Print summary table
    print("\n" + "=" * 80)
    print("SCALE BENCHMARK RESULTS")
    print("=" * 80)
    print(f"{'Scale':>10} | {'Total Routes':>12} | {'H3 Candidates':>13} | {'After Filter':>12} | {'Detailed':>8} | {'Total ms':>9}")
    print("-" * 80)

    for r in results:
        print(f"{r.scale:>10,} | {r.total_routes:>12,} | {r.h3_candidate_routes:>13,} | "
              f"{r.routes_after_context_filter:>12,} | {r.detailed_comparisons:>8,} | {r.total_ms:>9.1f}")

    print("-" * 80)

    # Check scale-up property
    if len(results) >= 2:
        print("\nScale-up Analysis:")
        for i in range(1, len(results)):
            prev = results[i - 1]
            curr = results[i]
            scale_factor = curr.scale / prev.scale
            candidate_factor = curr.h3_candidate_routes / max(prev.h3_candidate_routes, 1)
            filter_factor = curr.routes_after_context_filter / max(prev.routes_after_context_filter, 1)

            print(f"  {prev.scale} -> {curr.scale} ({scale_factor:.1f}x):")
            print(f"    H3 candidates: {prev.h3_candidate_routes} -> {curr.h3_candidate_routes} ({candidate_factor:.2f}x)")
            print(f"    After filter: {prev.routes_after_context_filter} -> {curr.routes_after_context_filter} ({filter_factor:.2f}x)")

    # Save to CSV if requested
    if args.output:
        with open(args.output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "scale", "total_routes", "h3_candidate_routes",
                "routes_after_context_filter", "detailed_comparisons",
                "h3_lookup_ms", "filter_ms", "similarity_ms", "total_ms"
            ])
            for r in results:
                writer.writerow([
                    r.scale, r.total_routes, r.h3_candidate_routes,
                    r.routes_after_context_filter, r.detailed_comparisons,
                    r.h3_lookup_ms, r.filter_ms, r.similarity_ms, r.total_ms
                ])
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
