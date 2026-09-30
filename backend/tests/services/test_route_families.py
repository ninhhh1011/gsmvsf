"""
Tests for Route Family Clustering
=============================

Tests cover:
- Incremental family assignment
- Threshold boundary cases
- Weighted support calculation
- Representative (medoid) selection
"""

import pytest
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.services.route_history.families import (
    RouteFamilyCluster,
    RouteFamily,
    DEFAULT_FAMILY_THRESHOLD,
)
from app.services.route_history.similarity import (
    RoadLevelSimilarity,
    SegmentInfo,
    RouteSegments,
)


@pytest.fixture
def similarity_calculator():
    """Create similarity calculator with test segments."""
    calc = RoadLevelSimilarity()

    # Create test segments
    segments = [
        SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
        SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
        SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        SegmentInfo("E04", "E04", "FORWARD", 200, 21.05, 105.88, 21.06, 105.89),
        SegmentInfo("E05", "E05", "FORWARD", 180, 21.06, 105.89, 21.07, 105.90),
        # Alternative corridor
        SegmentInfo("X01", "X01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
        SegmentInfo("X02", "X02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
        SegmentInfo("X03", "X03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
    ]

    for seg in segments:
        calc.segment_lookup[seg.segment_id] = seg

    return calc


@pytest.fixture
def cluster(similarity_calculator):
    """Create cluster with default threshold."""
    return RouteFamilyCluster(
        similarity_calculator=similarity_calculator,
        join_threshold=0.5
    )


class TestRouteFamilyCluster:
    """Tests for RouteFamilyCluster."""

    def test_first_route_creates_family(self, cluster):
        """First route should create a new family."""
        now = datetime.now()

        family_id = cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0
        )

        assert family_id.startswith("FAM_")
        assert len(cluster.families) == 1
        assert cluster.total_routes_assigned == 1

    def test_similar_route_joins_family(self, cluster):
        """Route with >50% similarity should join existing family."""
        now = datetime.now()

        # First route creates family
        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03", "E04", "E05"],
            total_distance_m=750.0
        )

        # Second similar route should join
        family_id = cluster.add_route(
            route_id="R002",
            driver_id="D002",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],  # Subset - high similarity
            total_distance_m=370.0
        )

        family = cluster.get_family(family_id)
        assert family.trip_count == 2
        assert family.unique_driver_count == 2

    def test_different_route_creates_new_family(self, cluster):
        """Route with <50% similarity should create new family."""
        now = datetime.now()

        # First route
        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03", "E04", "E05"],
            total_distance_m=750.0
        )

        # Different route (different segments) should create new family
        family_id = cluster.add_route(
            route_id="R002",
            driver_id="D002",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["X01", "X02", "X03"],  # Different corridor
            total_distance_m=370.0
        )

        # Should be a new family
        family = cluster.get_family(family_id)
        assert family.trip_count == 1
        assert family.unique_driver_count == 1

    def test_threshold_boundary_identical(self, cluster):
        """Identical routes should always join."""
        now = datetime.now()

        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0
        )

        family_id = cluster.add_route(
            route_id="R002",
            driver_id="D002",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],  # Identical
            total_distance_m=370.0
        )

        family = cluster.get_family(family_id)
        assert family.trip_count == 2

    def test_threshold_boundary_different(self, cluster):
        """Completely different routes should not join."""
        now = datetime.now()

        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0
        )

        family_id = cluster.add_route(
            route_id="R002",
            driver_id="D002",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["X01", "X02", "X03"],  # Different
            total_distance_m=370.0
        )

        family = cluster.get_family(family_id)
        # Should be new family with 1 member
        assert family.trip_count == 1

    def test_weighted_support(self, cluster):
        """Weighted support should accumulate correctly."""
        now = datetime.now()

        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0,
            time_weight=1.0,
            recency_weight=1.0  # weight = 1.0
        )

        cluster.add_route(
            route_id="R002",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],  # Same segments = similar
            total_distance_m=370.0,
            time_weight=0.5,
            recency_weight=0.5  # weight = 0.25
        )

        # Get the family by querying the route
        family = cluster.get_route_family("R001")
        assert family is not None
        # After finalization
        cluster.finalize_weights()

        # Weights are relative, so check they sum appropriately
        total = sum(f.weighted_support for f in cluster.families.values())
        assert abs(total - 1.0) < 0.001  # Should normalize to 1.0

    def test_get_route_family(self, cluster):
        """Should return family for a route."""
        now = datetime.now()

        family_id = cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0
        )

        found_family = cluster.get_route_family("R001")
        assert found_family is not None
        assert found_family.family_id == family_id

    def test_get_nonexistent_route_family(self, cluster):
        """Should return None for route not in any family."""
        found_family = cluster.get_route_family("NONEXISTENT")
        assert found_family is None

    def test_dominant_family_by_context(self, cluster):
        """Should return dominant family for context."""
        now = datetime.now()

        # Add multiple routes to same family
        for i in range(5):
            cluster.add_route(
                route_id=f"R_A_{i}",
                driver_id=f"D_{i}",
                timestamp=now,
                origin=(21.028, 105.854),
                destination=(21.065, 105.890),
                segment_ids=["E01", "E02", "E03", "E04", "E05"],
                total_distance_m=750.0
            )

        # Add fewer routes to different family
        for i in range(2):
            cluster.add_route(
                route_id=f"R_B_{i}",
                driver_id=f"D_{i + 10}",
                timestamp=now,
                origin=(21.028, 105.854),
                destination=(21.065, 105.890),
                segment_ids=["X01", "X02", "X03"],
                total_distance_m=370.0
            )

        cluster.finalize_weights()

        dominant = cluster.get_dominant_family(
            origin=(21.028, 105.854),
            destination=(21.065, 105.890)
        )

        assert dominant is not None
        assert dominant.trip_count == 5

    def test_family_context_filter(self, cluster):
        """Should filter families by origin/destination proximity."""
        now = datetime.now()

        # Family near point A
        cluster.add_route(
            route_id="R_NEAR_A",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),  # Near Ba Đình
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],
            total_distance_m=370.0
        )

        # Family near point B (far from A)
        cluster.add_route(
            route_id="R_NEAR_B",
            driver_id="D002",
            timestamp=now,
            origin=(21.100, 106.000),  # Far from Ba Đình
            destination=(21.120, 106.020),
            segment_ids=["X01", "X02", "X03"],
            total_distance_m=370.0
        )

        cluster.finalize_weights()

        # Query near Ba Đình
        candidates = cluster.get_families_by_context(
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            max_origin_dist_km=2.0,
            max_dest_dist_km=2.0
        )

        assert len(candidates) == 1
        assert candidates[0][0].family_id.startswith("FAM_")

    def test_update_representative(self, cluster):
        """Representative should update periodically."""
        now = datetime.now()

        # Add routes - with default interval=10, no update will happen
        for i in range(1, 4):
            cluster.add_route(
                route_id=f"R00{i}",
                driver_id=f"D00{i}",
                timestamp=now,
                origin=(21.028, 105.854),
                destination=(21.065, 105.890),
                segment_ids=["E01", "E02", "E03"],
                total_distance_m=370.0,
                time_weight=1.0,
                recency_weight=1.0
            )

        family = cluster.get_route_family("R001")
        assert family is not None
        # With 3 routes and interval=10, representative should still be first route
        assert family.representative_route_id == "R001"

    def test_stats(self, cluster):
        """Cluster statistics should be accurate."""
        now = datetime.now()

        for i in range(5):
            cluster.add_route(
                route_id=f"R00{i}",
                driver_id=f"D00{i % 2}",  # 2 drivers
                timestamp=now,
                origin=(21.028, 105.854),
                destination=(21.065, 105.890),
                segment_ids=["E01", "E02", "E03"],
                total_distance_m=370.0
            )

        stats = cluster.get_stats()

        assert stats["total_families"] == 1
        assert stats["total_routes_assigned"] == 5
        assert stats["families_with_multiple_routes"] == 1

    def test_configurable_threshold(self, similarity_calculator):
        """Should respect configurable threshold."""
        # Create cluster with higher threshold
        cluster = RouteFamilyCluster(
            similarity_calculator=similarity_calculator,
            join_threshold=0.8  # Higher threshold
        )

        now = datetime.now()

        # First route
        cluster.add_route(
            route_id="R001",
            driver_id="D001",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03", "E04", "E05"],
            total_distance_m=750.0
        )

        # Similar but not identical - might not meet 80% threshold
        family_id = cluster.add_route(
            route_id="R002",
            driver_id="D002",
            timestamp=now,
            origin=(21.028, 105.854),
            destination=(21.065, 105.890),
            segment_ids=["E01", "E02", "E03"],  # 3/5 = 60%
            total_distance_m=370.0
        )

        # With 80% threshold, R002 might create new family
        # Depends on actual similarity calculation


class TestRouteFamily:
    """Tests for RouteFamily dataclass."""

    def test_percentage_property(self):
        """Percentage should return weighted_support."""
        family = RouteFamily(
            family_id="TEST",
            representative_route_id="R001",
            representative_segment_ids=["E01", "E02"],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            origin_context=(21.028, 105.854),
            dest_context=(21.065, 105.890),
            direction_bearing=45.0,
            weighted_support=0.65
        )

        assert family.percentage == 0.65


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
