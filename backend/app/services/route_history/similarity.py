"""
Road-Level Similarity Calculator
==============================

Calculates similarity between two routes using directed road segments.

This is the "Route Truth" comparison - using actual road segments,
NOT H3 cells. H3 is only used for candidate lookup/scaling.

Similarity metrics:
1. Shared directed segments (both segment ID and direction must match)
2. Recommended Adherence: shared_distance / recommended_distance
3. Actual Route Overlap: shared_distance / actual_distance
4. Symmetric Score: 2 * shared / (recommended + actual)
5. Divergence/Rejoin detection
"""

from typing import List, Optional, Tuple, Dict, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import math


@dataclass
class SegmentInfo:
    """Information about a road segment."""
    segment_id: str  # e.g., "897474222_0_F"
    base_segment_id: str  # e.g., "897474222_0"
    direction: str  # "FORWARD" or "REVERSE"
    length_m: float
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    road_name: Optional[str] = None


@dataclass
class RouteSegments:
    """Ordered sequence of road segments for a route."""
    route_id: str
    segments: List[SegmentInfo]
    total_distance_m: float

    @classmethod
    def from_segment_ids(
        cls,
        route_id: str,
        segment_ids: List[str],
        segment_lookup: Dict[str, SegmentInfo]
    ) -> "RouteSegments":
        """Build RouteSegments from ordered segment IDs and lookup."""
        segments = []
        total_dist = 0.0

        for seg_id in segment_ids:
            info = segment_lookup.get(seg_id)
            if info:
                segments.append(info)
                total_dist += info.length_m

        return cls(
            route_id=route_id,
            segments=segments,
            total_distance_m=total_dist
        )


@dataclass
class DivergencePoint:
    """Point where routes diverge."""
    index_in_recommended: int
    index_in_actual: int
    recommended_segment: str
    actual_segment: str
    shared_before: int  # Number of shared segments before divergence


@dataclass
class RejoinPoint:
    """Point where routes rejoin after diverging."""
    index_in_recommended: int
    index_in_actual: int
    shared_segment: str
    divergence_before: int  # Index of divergence point
    segments_differed: int  # Number of segments that differed


@dataclass
class SimilarityResult:
    """Result of route similarity comparison."""
    recommended_route_id: str
    actual_route_id: str

    # Distance-based metrics
    recommended_distance_m: float
    actual_distance_m: float
    shared_distance_m: float

    # Percentage metrics
    recommended_adherence: float  # shared / recommended (0-1)
    actual_route_overlap: float   # shared / actual (0-1)
    symmetric_similarity: float   # 2 * shared / (recommended + actual) (0-1)

    # Segment-based metrics
    recommended_segment_count: int
    actual_segment_count: int
    shared_segment_count: int

    # Divergence analysis
    has_divergence: bool
    divergence_point: Optional[DivergencePoint] = None
    rejoin_point: Optional[RejoinPoint] = None

    # Detailed differences
    segments_only_in_recommended: List[str] = field(default_factory=list)
    segments_only_in_actual: List[str] = field(default_factory=list)


class RoadLevelSimilarity:
    """
    Calculate road-level similarity between two routes.

    Uses directed road segments (Route Truth), NOT H3 cells.
    H3 is only used for candidate lookup.

    Key metrics:
    - Recommended Adherence: How much of the recommended route the actual route covers
    - Actual Route Overlap: How much of the actual route overlaps with recommended
    - Symmetric Similarity: Balanced measure of both
    - Divergence/Rejoin: Where routes differ
    """

    def __init__(self):
        self.segment_lookup: Dict[str, SegmentInfo] = {}

    def load_segments(
        self,
        segment_data: List[Dict[str, Any]]
    ) -> None:
        """
        Load road segment data from CSV/dict source.

        Args:
            segment_data: List of dicts with segment info
                Required keys: segment_id, base_segment_id, travel_direction, length_m
                Optional keys: start_lat, start_lng, end_lat, end_lng, road_name
        """
        for row in segment_data:
            seg_id = row["segment_id"]
            direction = row.get("travel_direction", "FORWARD")

            # Parse coordinates if available
            start_lat = start_lng = end_lat = end_lng = 0.0
            geom = row.get("geometry", "")
            if geom and geom.startswith("LINESTRING"):
                # Parse "LINESTRING (lng1 lat1, lng2 lat2)"
                try:
                    coords_str = geom[11:-1]  # Remove "LINESTRING (" and ")"
                    parts = coords_str.split(",")
                    if len(parts) >= 2:
                        start_lng, start_lat = map(float, parts[0].split())
                        end_lng, end_lat = map(float, parts[-1].split())
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

    def calculate_similarity(
        self,
        recommended: RouteSegments,
        actual: RouteSegments
    ) -> SimilarityResult:
        """
        Calculate similarity between recommended and actual routes.

        Args:
            recommended: The system-recommended route
            actual: The driver's actual route

        Returns:
            SimilarityResult with detailed metrics
        """
        # Build segment ID sets with direction
        rec_segment_ids = [s.segment_id for s in recommended.segments]
        act_segment_ids = [s.segment_id for s in actual.segments]

        rec_set = set(rec_segment_ids)
        act_set = set(act_segment_ids)

        # Shared segments
        shared_ids = rec_set & act_set
        shared_count = len(shared_ids)

        # Calculate shared distance
        shared_distance = 0.0
        segments_only_in_rec = []
        segments_only_in_act = []

        for seg in recommended.segments:
            if seg.segment_id in shared_ids:
                shared_distance += seg.length_m
            else:
                segments_only_in_rec.append(seg.segment_id)

        for seg in actual.segments:
            if seg.segment_id not in shared_ids:
                segments_only_in_act.append(seg.segment_id)

        # Calculate percentages
        rec_dist = recommended.total_distance_m
        act_dist = actual.total_distance_m

        rec_adherence = shared_distance / rec_dist if rec_dist > 0 else 0.0
        act_overlap = shared_distance / act_dist if act_dist > 0 else 0.0
        symmetric = (2 * shared_distance / (rec_dist + act_dist)) if (rec_dist + act_dist) > 0 else 0.0

        # Find divergence/rejoin points
        divergence, rejoin = self._find_divergence_rejoin(
            rec_segment_ids, act_segment_ids, shared_ids
        )

        return SimilarityResult(
            recommended_route_id=recommended.route_id,
            actual_route_id=actual.route_id,
            recommended_distance_m=rec_dist,
            actual_distance_m=act_dist,
            shared_distance_m=shared_distance,
            recommended_adherence=rec_adherence,
            actual_route_overlap=act_overlap,
            symmetric_similarity=symmetric,
            recommended_segment_count=len(rec_segment_ids),
            actual_segment_count=len(act_segment_ids),
            shared_segment_count=shared_count,
            has_divergence=divergence is not None,
            divergence_point=divergence,
            rejoin_point=rejoin,
            segments_only_in_recommended=segments_only_in_rec,
            segments_only_in_actual=segments_only_in_act
        )

    def _find_divergence_rejoin(
        self,
        rec_ids: List[str],
        act_ids: List[str],
        shared_ids: Set[str]
    ) -> Tuple[Optional[DivergencePoint], Optional[RejoinPoint]]:
        """
        Find where routes diverge and potentially rejoin.

        Returns:
            Tuple of (divergence_point, rejoin_point) or (None, None)
        """
        # Find first divergence
        divergence = None
        rejoin = None

        min_len = min(len(rec_ids), len(act_ids))

        # Find divergence point
        divergence_idx_rec = None
        divergence_idx_act = None

        for i in range(min_len):
            if rec_ids[i] != act_ids[i]:
                divergence_idx_rec = i
                divergence_idx_act = i
                break

        if divergence_idx_rec is not None:
            divergence = DivergencePoint(
                index_in_recommended=divergence_idx_rec,
                index_in_actual=divergence_idx_act,
                recommended_segment=rec_ids[divergence_idx_rec],
                actual_segment=act_ids[divergence_idx_act],
                shared_before=divergence_idx_rec
            )

            # Find rejoin point (if routes converge again)
            # Start from divergence point + 1
            rec_offset = divergence_idx_rec + 1
            act_offset = divergence_idx_act + 1

            while rec_offset < len(rec_ids) and act_offset < len(act_ids):
                if rec_ids[rec_offset] == act_ids[act_offset]:
                    # Found rejoin
                    rejoin = RejoinPoint(
                        index_in_recommended=rec_offset,
                        index_in_actual=act_offset,
                        shared_segment=rec_ids[rec_offset],
                        divergence_before=divergence_idx_rec,
                        segments_differed=rec_offset - divergence_idx_rec - 1
                    )
                    break
                rec_offset += 1
                act_offset += 1

        return divergence, rejoin

    def calculate_weighted_similarity(
        self,
        recommended: RouteSegments,
        actual: RouteSegments,
        familiarity_weight: float,
        familiarity_penalty_max: float = 0.1
    ) -> Tuple[float, SimilarityResult]:
        """
        Calculate similarity with historical familiarity penalty.

        If actual route is very different from recommended, apply small penalty.

        Args:
            recommended: System-recommended route
            actual: Driver's actual route
            familiarity_weight: How much the driver follows recommended route (0-1)
            familiarity_penalty_max: Maximum penalty for divergence (0-0.1)

        Returns:
            Tuple of (adjusted_similarity, raw_similarity_result)
        """
        sim_result = self.calculate_similarity(recommended, actual)

        # Calculate familiarity penalty
        # Higher adherence = lower penalty
        adherence = sim_result.recommended_adherence
        penalty = familiarity_penalty_max * (1 - adherence)

        # Adjusted similarity (recommended adherence minus penalty)
        adjusted = adherence - penalty
        adjusted = max(0, min(1, adjusted))  # Clamp to 0-1

        return adjusted, sim_result

    def format_similarity_report(self, result: SimilarityResult) -> str:
        """Format similarity result as human-readable report."""
        lines = [
            f"Route Similarity Report",
            f"{'=' * 50}",
            f"Recommended Route: {result.recommended_route_id}",
            f"Actual Route:       {result.actual_route_id}",
            f"",
            f"Distance Metrics:",
            f"  Recommended: {result.recommended_distance_m:.0f} m ({result.recommended_distance_m/1000:.2f} km)",
            f"  Actual:      {result.actual_distance_m:.0f} m ({result.actual_distance_m/1000:.2f} km)",
            f"  Shared:      {result.shared_distance_m:.0f} m ({result.shared_distance_m/1000:.2f} km)",
            f"",
            f"Similarity Scores:",
            f"  Recommended Adherence:  {result.recommended_adherence:.1%}",
            f"  Actual Route Overlap:   {result.actual_route_overlap:.1%}",
            f"  Symmetric Similarity:  {result.symmetric_similarity:.1%}",
            f"",
            f"Segment Counts:",
            f"  Recommended: {result.recommended_segment_count}",
            f"  Actual:      {result.actual_segment_count}",
            f"  Shared:      {result.shared_segment_count}",
        ]

        if result.has_divergence and result.divergence_point:
            div = result.divergence_point
            lines.append(f"")
            lines.append(f"Divergence Detected:")
            lines.append(f"  At segment #{div.index_in_recommended}")
            lines.append(f"  Recommended diverges to: {div.recommended_segment}")
            lines.append(f"  Actual diverges to:     {div.actual_segment}")
            lines.append(f"  Shared before: {div.shared_before} segments")

        if result.rejoin_point:
            rej = result.rejoin_point
            lines.append(f"  Rejoin at segment #{rej.index_in_recommended}")
            lines.append(f"  Segments differed: {rej.segments_differed}")

        return "\n".join(lines)


def test_road_similarity():
    """Test road-level similarity calculation."""
    calc = RoadLevelSimilarity()

    # Load mock segment data
    mock_segments = [
        {"segment_id": "E01_F", "base_segment_id": "E01", "travel_direction": "FORWARD", "length_m": 100, "geometry": "LINESTRING (105.85 21.02, 105.86 21.03)"},
        {"segment_id": "E02_F", "base_segment_id": "E02", "travel_direction": "FORWARD", "length_m": 150, "geometry": "LINESTRING (105.86 21.03, 105.87 21.04)"},
        {"segment_id": "E03_F", "base_segment_id": "E03", "travel_direction": "FORWARD", "length_m": 120, "geometry": "LINESTRING (105.87 21.04, 105.88 21.05)"},
        {"segment_id": "E04_F", "base_segment_id": "E04", "travel_direction": "FORWARD", "length_m": 200, "geometry": "LINESTRING (105.88 21.05, 105.89 21.06)"},
        {"segment_id": "E05_F", "base_segment_id": "E05", "travel_direction": "FORWARD", "length_m": 180, "geometry": "LINESTRING (105.89 21.06, 105.90 21.07)"},
        # Alternative segments
        {"segment_id": "X01_F", "base_segment_id": "X01", "travel_direction": "FORWARD", "length_m": 100, "geometry": "LINESTRING (105.86 21.03, 105.87 21.04)"},
        {"segment_id": "X02_F", "base_segment_id": "X02", "travel_direction": "FORWARD", "length_m": 150, "geometry": "LINESTRING (105.87 21.04, 105.88 21.05)"},
    ]
    calc.load_segments(mock_segments)

    # Test Case 1: Identical routes
    print("=== Test 1: Identical Routes ===")
    rec1 = RouteSegments(
        route_id="REC001",
        segments=[calc.segment_lookup[f"E0{i}_F"] for i in range(1, 6)],
        total_distance_m=750.0
    )
    act1 = RouteSegments(
        route_id="ACT001",
        segments=[calc.segment_lookup[f"E0{i}_F"] for i in range(1, 6)],
        total_distance_m=750.0
    )
    result1 = calc.calculate_similarity(rec1, act1)
    print(calc.format_similarity_report(result1))

    # Test Case 2: Routes with divergence
    print("\n=== Test 2: Routes with Divergence ===")
    rec2 = RouteSegments(
        route_id="REC002",
        segments=[calc.segment_lookup[f"E0{i}_F"] for i in range(1, 6)],
        total_distance_m=750.0
    )
    act2 = RouteSegments(
        route_id="ACT002",
        segments=[
            calc.segment_lookup["E01_F"],
            calc.segment_lookup["E02_F"],
            calc.segment_lookup["X01_F"],  # Diverges here
            calc.segment_lookup["X02_F"],
            calc.segment_lookup["E05_F"],   # Rejoins here
        ],
        total_distance_m=620.0
    )
    result2 = calc.calculate_similarity(rec2, act2)
    print(calc.format_similarity_report(result2))

    # Test Case 3: Completely different routes
    print("\n=== Test 3: Completely Different Routes ===")
    rec3 = RouteSegments(
        route_id="REC003",
        segments=[calc.segment_lookup[f"E0{i}_F"] for i in range(1, 4)],
        total_distance_m=370.0
    )
    act3 = RouteSegments(
        route_id="ACT003",
        segments=[calc.segment_lookup[f"X0{i}_F"] for i in range(1, 3)],
        total_distance_m=250.0
    )
    result3 = calc.calculate_similarity(rec3, act3)
    print(calc.format_similarity_report(result3))


if __name__ == "__main__":
    test_road_similarity()
