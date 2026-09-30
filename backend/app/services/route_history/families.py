"""
Route Family Clustering
=====================

Incremental clustering of historical routes into Route Families.

Key design:
- Routes grouped by similar road segments
- Medoid (representative existing route), not synthetic geometry
- Configurable similarity threshold
- Weighted support based on time × recency
- Incremental assignment (no full pairwise comparison)

Example:
    Family A (Nguyễn Trãi corridor): 220 trips
    Family B (Tố Hữu corridor): 190 trips
    Family C (Đại lộ Thăng Long): 70 trips
"""

from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import uuid

from .similarity import RoadLevelSimilarity, RouteSegments, SimilarityResult


# Default threshold for joining a family (60% similarity)
DEFAULT_FAMILY_THRESHOLD = 0.6


@dataclass
class RouteFamilyMember:
    """A route that belongs to a family."""
    route_id: str
    driver_id: str
    timestamp: datetime
    segment_ids: List[str]
    total_distance_m: float
    time_weight: float = 1.0
    recency_weight: float = 1.0


@dataclass
class RouteFamily:
    """
    A cluster of similar routes.

    Maintains metadata about a group of routes that share
    similar road segments in the same direction.
    """
    family_id: str
    representative_route_id: str  # Medoid route - existing route, not synthetic
    representative_segment_ids: List[str]
    created_at: datetime
    updated_at: datetime
    origin_context: Tuple[float, float]  # (lat, lng) center
    dest_context: Tuple[float, float]  # (lat, lng) center
    direction_bearing: float  # Bearing in degrees

    # Member tracking
    members: List[RouteFamilyMember] = field(default_factory=list)

    # Aggregated statistics
    trip_count: int = 0
    unique_driver_count: int = 0

    # Weighted support (updated incrementally)
    weighted_support: float = 0.0

    @property
    def percentage(self) -> float:
        """Percentage of total relevant trips."""
        return self.weighted_support  # Will be normalized by caller

    @property
    def avg_similarity_to_representative(self) -> float:
        """Average similarity of members to representative."""
        return 0.0  # Computed during finalization


class RouteFamilyCluster:
    """
    Manages route families with incremental clustering.

    Uses representative-based clustering:
    1. Each family has a representative (medoid) route
    2. New routes compared only to representatives
    3. If similarity > threshold: assign to family
    4. Otherwise: create new family
    5. Periodically update representatives

    This avoids N×N comparisons.
    """

    def __init__(
        self,
        similarity_calculator: RoadLevelSimilarity,
        join_threshold: float = DEFAULT_FAMILY_THRESHOLD,
        representative_update_interval: int = 10  # Update medoid every N routes
    ):
        self.similarity_calculator = similarity_calculator
        self.join_threshold = join_threshold
        self.representative_update_interval = representative_update_interval

        # Family storage: family_id -> RouteFamily
        self.families: Dict[str, RouteFamily] = {}

        # Quick lookup: segment_id -> [family_ids]
        # Used for candidate family lookup
        self.segment_to_families: Dict[str, Set[str]] = defaultdict(set)

        # Route to family mapping
        self.route_to_family: Dict[str, str] = {}

        # Route segment cache
        self.route_segments: Dict[str, List[str]] = {}

        # Statistics
        self.total_routes_assigned = 0

    def add_route(
        self,
        route_id: str,
        driver_id: str,
        timestamp: datetime,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        segment_ids: List[str],
        total_distance_m: float,
        time_weight: float = 1.0,
        recency_weight: float = 1.0
    ) -> str:
        """
        Add a route and assign to family.

        Args:
            route_id: Unique route identifier
            driver_id: Driver who took this route
            timestamp: When the route occurred
            origin: (lat, lng) of origin
            destination: (lat, lng) of destination
            segment_ids: Ordered list of road segment IDs
            total_distance_m: Total route distance
            time_weight: Time of day relevance (0-1)
            recency_weight: Recency relevance (0-1)

        Returns:
            family_id the route was assigned to
        """
        # Cache route segments
        self.route_segments[route_id] = segment_ids

        # Find candidate families based on segment overlap
        candidate_family_ids = self._find_candidate_families(segment_ids)

        if candidate_family_ids:
            # Try to assign to existing family
            for family_id in candidate_family_ids:
                family = self.families[family_id]

                # Check if this route is similar to representative
                similarity = self._calculate_to_representative(
                    route_id, segment_ids, total_distance_m,
                    family.representative_route_id, family.representative_segment_ids
                )

                if similarity >= self.join_threshold:
                    # Assign to this family
                    self._assign_to_family(
                        route_id, driver_id, timestamp, segment_ids,
                        total_distance_m, time_weight, recency_weight, family_id
                    )
                    return family_id

        # No matching family - create new one
        new_family_id = self._create_family(
            route_id, driver_id, timestamp,
            origin, destination, segment_ids, total_distance_m,
            time_weight, recency_weight
        )

        return new_family_id

    def _find_candidate_families(self, segment_ids: List[str]) -> List[str]:
        """
        Find families that might contain routes similar to these segments.

        Uses inverted index on segments.
        """
        family_scores: Dict[str, int] = defaultdict(int)

        for seg_id in segment_ids:
            for family_id in self.segment_to_families.get(seg_id, set()):
                family_scores[family_id] += 1

        # Sort by overlap count descending
        candidates = sorted(
            family_scores.items(),
            key=lambda x: -x[1]
        )

        return [f[0] for f in candidates]

    def _calculate_to_representative(
        self,
        route_id: str,
        route_segments: List[str],
        route_distance: float,
        rep_route_id: str,
        rep_segments: List[str]
    ) -> float:
        """Calculate similarity to family representative."""
        # Build RouteSegments for similarity calculation
        rep_route = RouteSegments.from_segment_ids(
            rep_route_id,
            rep_segments,
            self.similarity_calculator.segment_lookup
        )

        new_route = RouteSegments.from_segment_ids(
            route_id,
            route_segments,
            self.similarity_calculator.segment_lookup
        )

        if not new_route.segments or not rep_route.segments:
            return 0.0

        result = self.similarity_calculator.calculate_similarity(rep_route, new_route)
        return result.symmetric_similarity

    def _assign_to_family(
        self,
        route_id: str,
        driver_id: str,
        timestamp: datetime,
        segment_ids: List[str],
        total_distance_m: float,
        time_weight: float,
        recency_weight: float,
        family_id: str
    ) -> None:
        """Assign route to existing family."""
        family = self.families[family_id]

        # Create member
        member = RouteFamilyMember(
            route_id=route_id,
            driver_id=driver_id,
            timestamp=timestamp,
            segment_ids=segment_ids,
            total_distance_m=total_distance_m,
            time_weight=time_weight,
            recency_weight=recency_weight
        )

        family.members.append(member)
        family.updated_at = datetime.now()
        family.trip_count += 1

        # Update weighted support
        combined_weight = time_weight * recency_weight
        family.weighted_support += combined_weight

        # Update unique drivers
        driver_ids = {m.driver_id for m in family.members}
        family.unique_driver_count = len(driver_ids)

        # Update segment index
        for seg_id in segment_ids:
            self.segment_to_families[seg_id].add(family_id)

        # Update route mapping
        self.route_to_family[route_id] = family_id
        self.total_routes_assigned += 1

        # Check if we should update representative
        if len(family.members) % self.representative_update_interval == 0:
            self._update_representative(family_id)

    def _create_family(
        self,
        route_id: str,
        driver_id: str,
        timestamp: datetime,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        segment_ids: List[str],
        total_distance_m: float,
        time_weight: float,
        recency_weight: float
    ) -> str:
        """Create a new family with this route as representative."""
        family_id = f"FAM_{uuid.uuid4().hex[:8]}"
        now = datetime.now()

        # Calculate direction bearing
        bearing = self._calculate_bearing(origin, destination)

        family = RouteFamily(
            family_id=family_id,
            representative_route_id=route_id,
            representative_segment_ids=segment_ids,
            created_at=now,
            updated_at=now,
            origin_context=origin,
            dest_context=destination,
            direction_bearing=bearing,
            trip_count=1,
            unique_driver_count=1,
            weighted_support=time_weight * recency_weight
        )

        # Add first member
        member = RouteFamilyMember(
            route_id=route_id,
            driver_id=driver_id,
            timestamp=timestamp,
            segment_ids=segment_ids,
            total_distance_m=total_distance_m,
            time_weight=time_weight,
            recency_weight=recency_weight
        )
        family.members.append(member)

        self.families[family_id] = family

        # Index segments
        for seg_id in segment_ids:
            self.segment_to_families[seg_id].add(family_id)

        # Map route to family
        self.route_to_family[route_id] = family_id
        self.total_routes_assigned += 1

        return family_id

    def _update_representative(self, family_id: str) -> None:
        """
        Update family representative to be the medoid.

        The medoid is the route that minimizes average distance
        to all other routes in the family.
        """
        family = self.families[family_id]

        if len(family.members) < 2:
            return

        # Find medoid (simplified: use route with highest weighted support)
        best_member = max(family.members, key=lambda m: m.time_weight * m.recency_weight)

        if best_member.route_id != family.representative_route_id:
            family.representative_route_id = best_member.route_id
            family.representative_segment_ids = best_member.segment_ids
            family.updated_at = datetime.now()

    def _calculate_bearing(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float]
    ) -> float:
        """Calculate bearing from origin to destination."""
        import math
        lat1, lng1 = origin
        lat2, lng2 = destination

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        d_lng = math.radians(lng2 - lng1)

        x = math.sin(d_lng) * math.cos(lat2_rad)
        y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lng))

        bearing = math.atan2(x, y)
        return (math.degrees(bearing) + 360) % 360

    def get_family(self, family_id: str) -> Optional[RouteFamily]:
        """Get family by ID."""
        return self.families.get(family_id)

    def get_route_family(self, route_id: str) -> Optional[RouteFamily]:
        """Get family that contains this route."""
        family_id = self.route_to_family.get(route_id)
        return self.families.get(family_id) if family_id else None

    def get_families_by_context(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        max_origin_dist_km: float = 2.0,
        max_dest_dist_km: float = 2.0
    ) -> List[Tuple[RouteFamily, float]]:
        """
        Get families matching origin/destination context.

        Returns:
            List of (family, relevance_score) sorted by relevance
        """
        import math

        def haversine_km(lat1, lng1, lat2, lng2):
            R = 6371.0
            d_lat = math.radians(lat2 - lat1)
            d_lng = math.radians(lng2 - lng1)
            a = (math.sin(d_lat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(d_lng / 2) ** 2)
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        results = []
        for family in self.families.values():
            origin_dist = haversine_km(
                origin[0], origin[1],
                family.origin_context[0], family.origin_context[1]
            )
            dest_dist = haversine_km(
                destination[0], destination[1],
                family.dest_context[0], family.dest_context[1]
            )

            if origin_dist <= max_origin_dist_km and dest_dist <= max_dest_dist_km:
                # Relevance based on distance and weighted support
                relevance = family.weighted_support / (1 + origin_dist + dest_dist)
                results.append((family, relevance))

        results.sort(key=lambda x: -x[1])
        return results

    def get_dominant_family(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        direction: Optional[float] = None,
        min_support: float = 0.0
    ) -> Optional[RouteFamily]:
        """
        Get the dominant (most common) family for this context.

        Args:
            origin: (lat, lng) of origin
            destination: (lat, lng) of destination
            direction: Optional bearing filter (degrees)
            min_support: Minimum weighted support threshold

        Returns:
            Dominant RouteFamily or None
        """
        candidates = self.get_families_by_context(origin, destination)

        if direction is not None:
            # Filter by direction (within 90 degrees)
            filtered = []
            for family, relevance in candidates:
                bearing_diff = abs(family.direction_bearing - direction)
                if bearing_diff > 180:
                    bearing_diff = 360 - bearing_diff
                if bearing_diff <= 90 and family.weighted_support >= min_support:
                    filtered.append((family, relevance))
            candidates = filtered

        if not candidates:
            return None

        # Normalize weights
        total_support = sum(f.weighted_support for f, _ in candidates)
        if total_support == 0:
            return None

        return candidates[0][0]

    def finalize_weights(self) -> None:
        """
        Normalize family weights to percentages.

        Call this after all routes are added and before querying.
        """
        total_support = sum(f.weighted_support for f in self.families.values())
        if total_support == 0:
            return

        for family in self.families.values():
            family.weighted_support = family.weighted_support / total_support

    def get_stats(self) -> Dict:
        """Get clustering statistics."""
        return {
            "total_families": len(self.families),
            "total_routes_assigned": self.total_routes_assigned,
            "avg_routes_per_family": (
                self.total_routes_assigned / len(self.families)
                if self.families else 0
            ),
            "families_with_multiple_routes": sum(
                1 for f in self.families.values() if f.trip_count > 1
            ),
        }


def test_route_family_cluster():
    """Test route family clustering."""
    from app.services.route_history.similarity import RoadLevelSimilarity, SegmentInfo, RouteSegments

    # Setup similarity calculator with test segments
    calc = RoadLevelSimilarity()

    # Create test segments
    test_segments = [
        SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
        SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
        SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        SegmentInfo("E04", "E04", "FORWARD", 200, 21.05, 105.88, 21.06, 105.89),
        SegmentInfo("E05", "E05", "FORWARD", 180, 21.06, 105.89, 21.07, 105.90),
        # Alternative segments
        SegmentInfo("X01", "X01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
        SegmentInfo("X02", "X02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
        SegmentInfo("X03", "X03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
    ]

    for seg in test_segments:
        calc.segment_lookup[seg.segment_id] = seg

    # Create cluster
    cluster = RouteFamilyCluster(
        similarity_calculator=calc,
        join_threshold=0.5
    )

    # Add routes
    now = datetime.now()

    # Family A: Routes along E01-E05 corridor
    for i in range(5):
        route_id = f"ROUTE_A_{i}"
        cluster.add_route(
            route_id=route_id,
            driver_id=f"D_{i % 2}",  # 2 drivers
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03", "E04", "E05"],
            total_distance_m=750.0,
            time_weight=0.8,
            recency_weight=0.9
        )

    # Family B: Routes along X01-X03 then E04-E05
    for i in range(3):
        route_id = f"ROUTE_B_{i}"
        cluster.add_route(
            route_id=route_id,
            driver_id=f"D_{i + 10}",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["X01", "X02", "X03", "E04", "E05"],
            total_distance_m=650.0,
            time_weight=0.6,
            recency_weight=0.7
        )

    # Finalize weights
    cluster.finalize_weights()

    # Check results
    stats = cluster.get_stats()
    print("=== Clustering Statistics ===")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n=== Families ===")
    for family in cluster.families.values():
        print(f"\n{family.family_id}:")
        print(f"  Representative: {family.representative_route_id}")
        print(f"  Trip count: {family.trip_count}")
        print(f"  Unique drivers: {family.unique_driver_count}")
        print(f"  Weighted support: {family.weighted_support:.1%}")

    # Test dominant family query
    dominant = cluster.get_dominant_family(
        origin=(21.028, 105.854),
        destination=(21.065, 105.890)
    )
    print(f"\n=== Dominant Family ===")
    if dominant:
        print(f"  {dominant.family_id}: {dominant.weighted_support:.1%} support")

    return cluster


if __name__ == "__main__":
    test_route_family_cluster()
