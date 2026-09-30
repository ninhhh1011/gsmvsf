"""
Historical Route Search Service
==============================

Main service that orchestrates the historical route similarity analysis pipeline:

1. H3 Signature Generation
2. Inverted Index Query (candidate shortlist)
3. Hard Filters (OD, Direction, 7-day)
4. Time/Recency Weighting
5. Road-level Similarity Calculation
6. Route Family Clustering

Usage:
    search = HistoricalRouteSearch()
    search.initialize_from_dataset("dataset_v1/")

    results = search.find_similar_routes(
        route_coords=[(21.0285, 105.8542), ...],
        origin=(21.0285, 105.8542),
        destination=(21.0500, 105.7800),
        timestamp=datetime.now(),
        max_candidates=20
    )
"""

from typing import List, Dict, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import gzip
import csv
import json
from collections import defaultdict

from .signature import H3SignatureGenerator, H3Signature, H3_ROUTE_RESOLUTION
from .index import RouteInvertedIndex
from .filters import HardFilters, TimeRecencyWeight, RouteMetadata
from .similarity import RoadLevelSimilarity, RouteSegments, SegmentInfo, SimilarityResult


@dataclass
class HistoricalRoute:
    """A historical route with all associated data."""
    route_id: str
    trip_id: str
    driver_id: str
    timestamp: datetime
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    segment_ids: List[str]  # Ordered road segments
    h3_signature: Optional[H3Signature] = None
    total_distance_m: float = 0.0


@dataclass
class RouteFamily:
    """A cluster of similar routes."""
    family_id: str
    routes: List[HistoricalRoute]
    representative_segment_ids: List[str]  # Most common segments
    weight: float  # Relative weight (0-1)
    percentage: float  # Percentage of total relevant trips
    avg_similarity_to_representative: float = 0.0


@dataclass
class SimilarRouteResult:
    """Result of finding similar routes."""
    route: HistoricalRoute
    similarity_result: SimilarityResult
    time_weight: float
    recency_weight: float
    combined_weight: float
    final_score: float  # weighted_similarity * combined_weight


@dataclass
class RouteSearchResult:
    """Complete result of historical route search."""
    query_route_id: str
    total_candidates_found: int
    passing_hard_filters: int
    detailed_comparisons: int

    similar_routes: List[SimilarRouteResult]
    route_families: List[RouteFamily]

    # Summary statistics
    avg_similarity: float
    max_similarity: float
    dominant_family: Optional[RouteFamily]

    # Recommendation metadata
    familiarity_score: float  # How familiar this route is to drivers


class HistoricalRouteSearch:
    """
    Historical route search service.

    Finds similar historical routes and computes familiarity scores
    for route recommendation.

    Pipeline:
    1. Generate H3 signature from current route
    2. Query inverted index for candidate routes
    3. Apply hard filters
    4. Calculate time/recency weights
    5. Compute road-level similarity
    6. Cluster into route families
    """

    def __init__(
        self,
        h3_resolution: int = H3_ROUTE_RESOLUTION,
        origin_threshold_km: float = 2.0,
        dest_threshold_km: float = 2.0,
        days_window: int = 7
    ):
        self.signature_generator = H3SignatureGenerator(h3_resolution)
        self.inverted_index = RouteInvertedIndex()
        self.hard_filters = HardFilters(
            origin_threshold_km=origin_threshold_km,
            dest_threshold_km=dest_threshold_km,
            days_window=days_window
        )
        self.weight_calculator = TimeRecencyWeight()
        self.similarity_calculator = RoadLevelSimilarity()

        self.segment_lookup: Dict[str, SegmentInfo] = {}
        self.historical_routes: Dict[str, HistoricalRoute] = {}
        self.initialized = False

    def initialize_from_dataset(
        self,
        dataset_path: str,
        max_routes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Initialize from dataset_v1 files.

        Args:
            dataset_path: Path to dataset_v1 directory
            max_routes: Optional limit on number of routes to load

        Returns:
            Statistics about initialization
        """
        dataset_path = Path(dataset_path)
        stats = {
            "routes_loaded": 0,
            "segments_loaded": 0,
            "h3_cells": 0,
            "errors": []
        }

        # Load road segments
        segments_file = dataset_path / "map" / "processed" / "road_segments.csv.gz"
        if segments_file.exists():
            self._load_segments(segments_file)
            stats["segments_loaded"] = len(self.segment_lookup)

        # Load trajectories and build historical routes
        trajectories_file = dataset_path / "trajectories" / "true_trajectories.csv.gz"
        if trajectories_file.exists():
            routes = self._load_trajectories(trajectories_file, max_routes)
            stats["routes_loaded"] = len(routes)

            # Build inverted index
            for route in routes:
                if route.h3_signature:
                    self.inverted_index.add_route(
                        route.route_id,
                        list(route.h3_signature.hex_sequence)
                    )
                    stats["h3_cells"] += route.h3_signature.hex_count

        self.initialized = True
        return stats

    def _load_segments(self, segments_file: Path) -> None:
        """Load road segments from CSV."""
        with gzip.open(segments_file, "rt") as f:
            reader = csv.DictReader(f)
            for row in reader:
                seg_id = row["segment_id"]
                direction = row.get("travel_direction", "FORWARD")

                # Parse geometry
                geom = row.get("geometry", "")
                start_lat = start_lng = end_lat = end_lng = 0.0
                if geom and geom.startswith("LINESTRING"):
                    try:
                        coords_str = geom[11:-1]
                        parts = coords_str.split(",")
                        if len(parts) >= 2:
                            end_lng, end_lat = map(float, parts[-1].split())
                            start_lng, start_lat = map(float, parts[0].split())
                    except:
                        pass

                self.segment_lookup[seg_id] = SegmentInfo(
                    segment_id=seg_id,
                    base_segment_id=row.get("base_segment_id", seg_id.rsplit("_", 2)[0]),
                    direction=direction,
                    length_m=float(row.get("length_m", 0)),
                    start_lat=start_lat,
                    start_lng=start_lng,
                    end_lat=end_lat,
                    end_lng=end_lng,
                    road_name=row.get("road_name")
                )

    def _load_trajectories(
        self,
        trajectories_file: Path,
        max_routes: Optional[int] = None
    ) -> List[HistoricalRoute]:
        """Load trajectories and create historical routes."""
        # Group by trajectory_id to build ordered segment sequences
        trajectory_segments: Dict[str, List[Tuple[str, datetime]]] = defaultdict(list)
        trajectory_meta: Dict[str, Dict[str, Any]] = {}

        with gzip.open(trajectories_file, "rt") as f:
            reader = csv.DictReader(f)
            for row in reader:
                traj_id = row["trajectory_id"]
                trip_id = row["trip_id"]

                # Extract metadata from first row
                if traj_id not in trajectory_meta:
                    trajectory_meta[traj_id] = {
                        "trip_id": trip_id,
                        "timestamp": row["timestamp"],
                        "origin_lat": float(row["true_latitude"]),
                        "origin_lng": float(row["true_longitude"]),
                    }

                # Track last point for destination
                trajectory_meta[traj_id]["dest_lat"] = float(row["true_latitude"])
                trajectory_meta[traj_id]["dest_lng"] = float(row["true_longitude"])
                trajectory_meta[traj_id]["dest_time"] = row["timestamp"]

                # Collect segment IDs in order
                seg_id = row.get("true_segment_id")
                if seg_id:
                    ts = datetime.fromisoformat(row["timestamp"])
                    trajectory_segments[traj_id].append((seg_id, ts))

        # Build HistoricalRoute objects
        routes = []
        for traj_id, segments in trajectory_segments.items():
            if not segments:
                continue

            meta = trajectory_meta.get(traj_id, {})

            # Extract ordered segment IDs
            ordered_seg_ids = [seg for seg, _ in segments]

            # Calculate total distance
            total_dist = 0.0
            valid_segments = []
            for seg_id in ordered_seg_ids:
                if seg_id in self.segment_lookup:
                    total_dist += self.segment_lookup[seg_id].length_m
                    valid_segments.append(seg_id)

            if len(valid_segments) < 2:
                continue

            # Generate H3 signature from segment geometries
            coords = []
            prev_end = None
            for seg_id in valid_segments[:50]:  # Limit for performance
                seg = self.segment_lookup.get(seg_id)
                if seg:
                    if prev_end is None:
                        coords.append((seg.start_lat, seg.start_lng))
                    coords.append((seg.end_lat, seg.end_lng))
                    prev_end = (seg.end_lat, seg.end_lng)

            h3_sig = None
            if len(coords) >= 2:
                try:
                    h3_sig = self.signature_generator.signature_from_coords(
                        traj_id, coords
                    )
                except:
                    pass

            route = HistoricalRoute(
                route_id=traj_id,
                trip_id=meta.get("trip_id", traj_id),
                driver_id=f"DRIVER_{traj_id[:4]}",  # Extract from trip or generate
                timestamp=datetime.fromisoformat(meta.get("timestamp", "2026-09-01T00:00:00")),
                origin_lat=meta.get("origin_lat", 0),
                origin_lng=meta.get("origin_lng", 0),
                destination_lat=meta.get("dest_lat", 0),
                destination_lng=meta.get("dest_lng", 0),
                segment_ids=valid_segments,
                h3_signature=h3_sig,
                total_distance_m=total_dist
            )

            routes.append(route)
            self.historical_routes[traj_id] = route

            if max_routes and len(routes) >= max_routes:
                break

        return routes

    def find_similar_routes(
        self,
        route_coords: List[Tuple[float, float]],
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        timestamp: datetime,
        max_candidates: int = 20,
        similarity_threshold: float = 0.0
    ) -> RouteSearchResult:
        """
        Find historical routes similar to the given route.

        Args:
            route_coords: Ordered (lat, lng) coordinates of the route
            origin: (lat, lng) of route origin
            destination: (lat, lng) of route destination
            timestamp: When the route occurred
            max_candidates: Maximum number of similar routes to return
            similarity_threshold: Minimum similarity to include in results

        Returns:
            RouteSearchResult with similar routes and families
        """
        if not self.initialized:
            raise RuntimeError("HistoricalRouteSearch not initialized. Call initialize_from_dataset() first.")

        # Step 1: Generate H3 signature
        query_sig = self.signature_generator.signature_from_coords(
            "QUERY_ROUTE", route_coords
        )

        # Step 2: Query inverted index
        candidate_ids = self.inverted_index.query_by_signature(
            list(query_sig.hex_sequence),
            min_overlap_pct=0.1  # At least 10% H3 overlap
        )

        # Step 3: Build query route segments for similarity
        query_segments = self._build_route_segments("QUERY", route_coords)

        # Step 4: Apply filters and compute similarity
        similar_routes: List[SimilarRouteResult] = []
        hard_filter_passed = 0

        for route_id, shared_count, h3_overlap in candidate_ids:
            if route_id == "QUERY_ROUTE":
                continue

            historical_route = self.historical_routes.get(route_id)
            if not historical_route:
                continue

            # Create metadata for filtering
            route_meta = RouteMetadata(
                route_id=route_id,
                trip_id=historical_route.trip_id,
                driver_id=historical_route.driver_id,
                timestamp=historical_route.timestamp,
                origin_lat=historical_route.origin_lat,
                origin_lng=historical_route.origin_lng,
                destination_lat=historical_route.destination_lat,
                destination_lng=historical_route.destination_lng,
            )

            # Apply hard filters
            passed, failures = self.hard_filters.apply_all_filters(
                origin[0], origin[1],
                destination[0], destination[1],
                timestamp,
                route_meta
            )

            if not passed:
                continue

            hard_filter_passed += 1

            # Calculate time/recency weights
            weights = self.weight_calculator.combined_weight(timestamp, historical_route.timestamp)

            # Build historical route segments
            hist_segments = self._build_route_segments_from_ids(
                route_id,
                historical_route.segment_ids
            )

            if not hist_segments or not query_segments:
                continue

            # Calculate road-level similarity
            sim_result = self.similarity_calculator.calculate_similarity(
                query_segments, hist_segments
            )

            # Combined score: similarity * time_weight * recency_weight
            final_score = sim_result.symmetric_similarity * weights.combined_weight

            if final_score >= similarity_threshold:
                similar_routes.append(SimilarRouteResult(
                    route=historical_route,
                    similarity_result=sim_result,
                    time_weight=weights.time_weight,
                    recency_weight=weights.recency_weight,
                    combined_weight=weights.combined_weight,
                    final_score=final_score
                ))

        # Sort by final score descending
        similar_routes.sort(key=lambda x: -x.final_score)
        similar_routes = similar_routes[:max_candidates]

        # Step 5: Cluster into route families
        families = self._cluster_route_families(similar_routes)

        # Calculate summary statistics
        avg_sim = 0.0
        max_sim = 0.0
        if similar_routes:
            avg_sim = sum(r.final_score for r in similar_routes) / len(similar_routes)
            max_sim = max(r.final_score for r in similar_routes)

        return RouteSearchResult(
            query_route_id="QUERY_ROUTE",
            total_candidates_found=len(candidate_ids),
            passing_hard_filters=hard_filter_passed,
            detailed_comparisons=len(similar_routes),
            similar_routes=similar_routes,
            route_families=families,
            avg_similarity=avg_sim,
            max_similarity=max_sim,
            dominant_family=families[0] if families else None,
            familiarity_score=max_sim
        )

    def _build_route_segments(
        self,
        route_id: str,
        coords: List[Tuple[float, float]]
    ) -> RouteSegments:
        """Build RouteSegments from coordinates."""
        segments = []
        total_dist = 0.0

        for i in range(len(coords) - 1):
            lat1, lng1 = coords[i]
            lat2, lng2 = coords[i + 1]

            # Create synthetic segment ID
            seg_id = f"SYNTH_{i}"

            # Calculate distance
            dist = self._haversine_m(lat1, lng1, lat2, lng2)
            total_dist += dist

            segments.append(SegmentInfo(
                segment_id=seg_id,
                base_segment_id=seg_id,
                direction="FORWARD",
                length_m=dist,
                start_lat=lat1,
                start_lng=lng1,
                end_lat=lat2,
                end_lng=lng2
            ))

        return RouteSegments(
            route_id=route_id,
            segments=segments,
            total_distance_m=total_dist
        )

    def _build_route_segments_from_ids(
        self,
        route_id: str,
        segment_ids: List[str]
    ) -> RouteSegments:
        """Build RouteSegments from segment IDs."""
        segments = []
        total_dist = 0.0

        for seg_id in segment_ids:
            seg_info = self.segment_lookup.get(seg_id)
            if seg_info:
                segments.append(seg_info)
                total_dist += seg_info.length_m

        return RouteSegments(
            route_id=route_id,
            segments=segments,
            total_distance_m=total_dist
        )

    def _haversine_m(
        self, lat1: float, lng1: float, lat2: float, lng2: float
    ) -> float:
        """Calculate haversine distance in meters."""
        import math
        R = 6371000
        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)
        a = (math.sin(d_lat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(d_lng / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _cluster_route_families(
        self,
        similar_routes: List[SimilarRouteResult]
    ) -> List[RouteFamily]:
        """
        Cluster similar routes into families.

        Routes in the same family share significant road segments.
        """
        if not similar_routes:
            return []

        # Simple clustering: group by shared segments
        # More sophisticated: use segment overlap > 50%
        families: Dict[str, List[SimilarRouteResult]] = defaultdict(list)

        for result in similar_routes:
            # Use first 3 segments as family key (simplified)
            route = result.route
            if route.segment_ids:
                key = "|".join(route.segment_ids[:3])
                families[key].append(result)

        # Convert to RouteFamily objects
        family_list = []
        total_routes = len(similar_routes)

        for i, (key, routes) in enumerate(sorted(
            families.items(),
            key=lambda x: -len(x[1])
        )):
            weight = len(routes) / total_routes if total_routes > 0 else 0

            family = RouteFamily(
                family_id=f"FAMILY_{i+1}",
                routes=[r.route for r in routes],
                representative_segment_ids=routes[0].route.segment_ids[:5] if routes else [],
                weight=weight,
                percentage=weight * 100,
                avg_similarity_to_representative=sum(r.final_score for r in routes) / len(routes) if routes else 0
            )
            family_list.append(family)

        return family_list

    def get_familiarity_penalty(
        self,
        similarity_result: SimilarityResult,
        max_penalty: float = 0.1
    ) -> float:
        """
        Calculate familiarity penalty for ranking.

        If actual route is very different from historical patterns,
        apply small penalty.

        Args:
            similarity_result: Result of comparing actual to recommended route
            max_penalty: Maximum penalty value (0-0.1)

        Returns:
            Penalty value to add to route cost
        """
        adherence = similarity_result.recommended_adherence
        penalty = max_penalty * (1 - adherence)
        return penalty


def test_historical_route_search():
    """Test the historical route search service."""
    search = HistoricalRouteSearch()

    # Check if dataset exists
    dataset_path = Path("dataset_v1")
    if not dataset_path.exists():
        print("Dataset not found, skipping initialization test")
        return

    # Initialize from dataset
    print("Initializing from dataset...")
    stats = search.initialize_from_dataset("dataset_v1", max_routes=1000)

    print("\n=== Initialization Statistics ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    if not search.initialized:
        print("Failed to initialize search service")
        return

    # Test search
    print("\n=== Testing Route Search ===")

    # Example: Route from Ba Đình to Cầu Giấy
    query_coords = [
        (21.0285, 105.8542),  # Ba Đình
        (21.0300, 105.8560),
        (21.0350, 105.8600),
        (21.0400, 105.8500),
        (21.0500, 105.7800),  # Cầu Giấy
    ]

    origin = (21.0285, 105.8542)
    destination = (21.0500, 105.7800)
    timestamp = datetime(2026, 9, 21, 8, 15)

    result = search.find_similar_routes(
        route_coords=query_coords,
        origin=origin,
        destination=destination,
        timestamp=timestamp,
        max_candidates=10
    )

    print(f"\nQuery Route: Ba Đình → Cầu Giấy")
    print(f"Timestamp: {timestamp}")
    print(f"Total candidates found: {result.total_candidates_found}")
    print(f"Passing hard filters: {result.passing_hard_filters}")
    print(f"Detailed comparisons: {result.detailed_comparisons}")
    print(f"Avg similarity: {result.avg_similarity:.2%}")
    print(f"Max similarity: {result.max_similarity:.2%}")

    if result.route_families:
        print(f"\n=== Route Families ===")
        for family in result.route_families[:3]:
            print(f"  {family.family_id}: {family.percentage:.1f}% ({len(family.routes)} routes)")

    if result.similar_routes:
        print(f"\n=== Top Similar Routes ===")
        for i, sr in enumerate(result.similar_routes[:5]):
            r = sr.route
            sim = sr.similarity_result
            print(f"\n  {i+1}. Route {r.route_id}")
            print(f"     Similarity: {sim.symmetric_similarity:.2%}")
            print(f"     Recommended Adherence: {sim.recommended_adherence:.2%}")
            print(f"     Time Weight: {sr.time_weight:.2f}")
            print(f"     Recency Weight: {sr.recency_weight:.2f}")
            print(f"     Final Score: {sr.final_score:.2f}")


if __name__ == "__main__":
    test_historical_route_search()
