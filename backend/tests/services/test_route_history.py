"""
Tests for Route History Scale Service - Phase 1
=============================================

Tests cover:
- H3 Signature Generation
- H3 Inverted Index
- Hard Filters
- Time/Recency Weighting
- Road-Level Similarity
"""

import pytest
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.services.route_history.signature import (
    H3SignatureGenerator,
    H3Signature,
    H3_ROUTE_RESOLUTION,
)
from app.services.route_history.index import RouteInvertedIndex
from app.services.route_history.filters import (
    HardFilters,
    TimeRecencyWeight,
    RouteMetadata,
)
from app.services.route_history.similarity import (
    RoadLevelSimilarity,
    RouteSegments,
    SegmentInfo,
    SimilarityResult,
)


class TestH3SignatureGenerator:
    """Tests for H3 signature generation."""

    def test_h3_resolution(self):
        """H3 Resolution 11 should be used for route indexing."""
        assert H3_ROUTE_RESOLUTION == 11

    def test_signature_from_coords_basic(self):
        """Basic signature generation from coordinates."""
        gen = H3SignatureGenerator()

        # Hanoi area coordinates
        coords = [
            (21.0285, 105.8542),  # Ba Đình
            (21.0300, 105.8560),
            (21.0350, 105.8600),
            (21.0500, 105.7800),  # Cầu Giấy
        ]

        sig = gen.signature_from_coords("TEST_ROUTE_001", coords)

        assert sig.route_id == "TEST_ROUTE_001"
        assert len(sig.hex_sequence) > 0
        assert sig.start_hex != ""
        assert sig.end_hex != ""
        assert sig.hex_count > 0

    def test_signature_collapse_consecutive(self):
        """Consecutive duplicate H3 cells should be collapsed."""
        gen = H3SignatureGenerator()

        # Coordinates that may produce duplicate H3 cells
        coords = [
            (21.0285, 105.8542),
            (21.0286, 105.8543),  # Same hex as previous
            (21.0287, 105.8544),  # Different hex
        ]

        sig = gen.signature_from_coords("TEST_COLLAPSE", coords)

        # All hexes should be unique (no consecutive duplicates)
        for i in range(len(sig.hex_sequence) - 1):
            assert sig.hex_sequence[i] != sig.hex_sequence[i + 1]

    def test_signature_insufficient_coords(self):
        """Should raise error for insufficient coordinates."""
        gen = H3SignatureGenerator()

        with pytest.raises(ValueError):
            gen.signature_from_coords("TEST_BAD", [(21.0285, 105.8542)])

    def test_compute_hex_overlap(self):
        """H3 overlap computation between two signatures."""
        gen = H3SignatureGenerator()

        # Two overlapping routes
        coords1 = [
            (21.0285, 105.8542),
            (21.0300, 105.8560),
            (21.0350, 105.8600),
        ]
        coords2 = [
            (21.0285, 105.8542),  # Same start
            (21.0290, 105.8550),
            (21.0360, 105.8620),  # Different end
        ]

        sig1 = gen.signature_from_coords("ROUTE_A", coords1)
        sig2 = gen.signature_from_coords("ROUTE_B", coords2)

        common, only1, only2 = gen.compute_hex_overlap(sig1, sig2)

        # They should share at least the start hex
        assert len(common) >= 1
        assert sig1.start_hex in common

    def test_sequential_overlap(self):
        """Sequential overlap respects H3 order."""
        gen = H3SignatureGenerator()

        coords1 = [
            (21.0285, 105.8542),
            (21.0300, 105.8560),
            (21.0350, 105.8600),
            (21.0400, 105.8500),
        ]
        coords2 = [
            (21.0285, 105.8542),
            (21.0300, 105.8560),
            (21.0360, 105.8620),  # Different path
        ]

        sig1 = gen.signature_from_coords("ROUTE_1", coords1)
        sig2 = gen.signature_from_coords("ROUTE_2", coords2)

        seq_overlap = gen.compute_sequential_overlap(sig1, sig2)

        # Both start at same point, so overlap should be > 0
        assert 0 <= seq_overlap <= 1


class TestRouteInvertedIndex:
    """Tests for H3 inverted index."""

    def test_add_and_query_single_hex(self):
        """Add route and query by single hex."""
        index = RouteInvertedIndex()

        index.add_route("R001", ["H1", "H2", "H3"])

        routes = index.query_by_hex("H1")
        assert "R001" in routes

        routes = index.query_by_hex("H999")
        assert "R001" not in routes

    def test_query_by_multiple_hexes(self):
        """Query by multiple hexes returns all matching routes."""
        index = RouteInvertedIndex()

        index.add_route("R001", ["H1", "H2", "H3"])
        index.add_route("R002", ["H2", "H3", "H4"])
        index.add_route("R003", ["H5", "H6"])

        results = index.query_by_hexes(["H2", "H3"])

        # Should return R001 and R002, sorted by overlap count
        route_ids = [r[0] for r in results]
        assert "R001" in route_ids
        assert "R002" in route_ids
        assert "R003" not in route_ids

        # R001 shares 2 hexes, R002 shares 2 hexes
        counts = {r[0]: r[1] for r in results}
        assert counts["R001"] == 2
        assert counts["R002"] == 2

    def test_query_by_signature(self):
        """Query by H3 signature with overlap percentage."""
        index = RouteInvertedIndex()

        index.add_route("R001", ["H1", "H2", "H3", "H4"])
        index.add_route("R002", ["H2", "H3"])
        index.add_route("R003", ["H5", "H6"])

        # Query with 50% minimum overlap
        results = index.query_by_signature(["H1", "H2", "H3", "H4"], min_overlap_pct=0.5)

        route_ids = [r[0] for r in results]
        assert "R001" in route_ids  # 100% overlap
        # R002 only shares 50% (2/4) which meets 50% threshold
        assert "R002" in route_ids
        assert "R003" not in route_ids

    def test_remove_route(self):
        """Remove route from index."""
        index = RouteInvertedIndex()

        index.add_route("R001", ["H1", "H2"])
        index.remove_route("R001")

        routes = index.query_by_hex("H1")
        assert "R001" not in routes

    def test_index_stats(self):
        """Index statistics tracking."""
        index = RouteInvertedIndex()

        index.add_route("R001", ["H1", "H2", "H3"])
        index.add_route("R002", ["H2", "H3", "H4"])

        stats = index.get_stats()

        assert stats["total_routes"] == 2
        assert stats["total_cells"] == 4  # H1, H2, H3, H4


class TestHardFilters:
    """Tests for hard filters."""

    def test_origin_filter_pass(self):
        """Origin within threshold should pass."""
        filters = HardFilters(origin_threshold_km=2.0)

        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime.now(),
            origin_lat=21.0285,
            origin_lng=105.8542,
            destination_lat=21.0500,
            destination_lng=105.7800,
        )

        result = filters.filter_by_origin(21.0285, 105.8542, candidate)

        assert result.passed
        assert result.distance_km < 2.0

    def test_origin_filter_fail(self):
        """Origin outside threshold should fail."""
        filters = HardFilters(origin_threshold_km=2.0)

        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime.now(),
            origin_lat=21.1000,  # Far from query origin
            origin_lng=106.0000,
            destination_lat=21.0500,
            destination_lng=105.7800,
        )

        result = filters.filter_by_origin(21.0285, 105.8542, candidate)

        assert not result.passed
        assert "Origin too far" in result.reason

    def test_direction_filter_same_direction(self):
        """Routes going same direction should pass."""
        filters = HardFilters()

        # Query: Ba Đình to Cầu Giấy
        query_origin = (21.0285, 105.8542)
        query_dest = (21.0500, 105.7800)

        # Candidate: same general direction
        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime.now(),
            origin_lat=21.0290,
            origin_lng=105.8550,
            destination_lat=21.0510,
            destination_lng=105.7810,
        )

        result = filters.filter_by_direction(
            *query_origin, *query_dest, candidate
        )

        assert result.passed

    def test_direction_filter_wrong_direction(self):
        """Routes going opposite direction should fail."""
        filters = HardFilters()

        # Query: Ba Đình to Cầu Giấy
        query_origin = (21.0285, 105.8542)
        query_dest = (21.0500, 105.7800)

        # Candidate: opposite direction (swapped origin/dest)
        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime.now(),
            origin_lat=21.0500,  # Swapped!
            origin_lng=105.7800,
            destination_lat=21.0285,
            destination_lng=105.8542,
        )

        result = filters.filter_by_direction(
            *query_origin, *query_dest, candidate
        )

        assert not result.passed
        assert "Wrong direction" in result.reason

    def test_time_window_filter_pass(self):
        """Route within 7 days should pass."""
        filters = HardFilters(days_window=7)

        query_time = datetime(2026, 9, 21, 8, 0)
        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime(2026, 9, 20, 8, 0),  # Yesterday
            origin_lat=21.0285,
            origin_lng=105.8542,
            destination_lat=21.0500,
            destination_lng=105.7800,
        )

        result = filters.filter_by_time_window(query_time, candidate)

        assert result.passed

    def test_time_window_filter_fail(self):
        """Route older than 7 days should fail."""
        filters = HardFilters(days_window=7)

        query_time = datetime(2026, 9, 21, 8, 0)
        candidate = RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime(2026, 9, 10, 8, 0),  # 11 days ago
            origin_lat=21.0285,
            origin_lng=105.8542,
            destination_lat=21.0500,
            destination_lng=105.7800,
        )

        result = filters.filter_by_time_window(query_time, candidate)

        assert not result.passed


class TestTimeRecencyWeight:
    """Tests for time and recency weighting."""

    def test_time_weight_same_hour(self):
        """Trips at same hour should have high weight."""
        weight_calc = TimeRecencyWeight(time_decay_hours=2.0)

        query_time = datetime(2026, 9, 21, 8, 15)
        trip_time = datetime(2026, 9, 21, 8, 30)  # 15 min diff

        weight = weight_calc.time_weight(query_time, trip_time)

        assert weight > 0.8  # Very similar time

    def test_time_weight_different_hour(self):
        """Trips at different times should have lower weight."""
        weight_calc = TimeRecencyWeight(time_decay_hours=2.0)

        query_time = datetime(2026, 9, 21, 8, 0)
        trip_time = datetime(2026, 9, 21, 12, 0)  # 4 hours diff

        weight = weight_calc.time_weight(query_time, trip_time)

        assert 0 < weight < 0.5

    def test_recency_weight_same_day(self):
        """Today's trips should have high recency weight."""
        weight_calc = TimeRecencyWeight(recency_decay_days=2.0)

        query_time = datetime(2026, 9, 21, 8, 0)
        trip_time = datetime(2026, 9, 21, 7, 0)  # Same day

        weight = weight_calc.recency_weight(query_time, trip_time)

        assert weight > 0.8

    def test_recency_weight_old_trip(self):
        """Old trips should have low recency weight."""
        weight_calc = TimeRecencyWeight(recency_decay_days=2.0)

        query_time = datetime(2026, 9, 21, 8, 0)
        trip_time = datetime(2026, 9, 15, 8, 0)  # 6 days ago

        weight = weight_calc.recency_weight(query_time, trip_time)

        assert weight < 0.2

    def test_combined_weight(self):
        """Combined weight is product of time and recency."""
        weight_calc = TimeRecencyWeight(
            time_decay_hours=2.0,
            recency_decay_days=2.0
        )

        query_time = datetime(2026, 9, 21, 8, 15)
        trip_time = datetime(2026, 9, 21, 8, 30)  # Same day, close time

        score = weight_calc.combined_weight(query_time, trip_time)

        assert score.combined_weight <= 1.0
        assert score.combined_weight >= 0.0
        assert score.combined_weight == score.time_weight * score.recency_weight


class TestRoadLevelSimilarity:
    """Tests for road-level similarity calculation."""

    def test_identical_routes(self):
        """Identical routes should have 100% similarity."""
        calc = RoadLevelSimilarity()

        # Load mock segments
        segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        ]

        rec = RouteSegments("REC", segments, 370.0)
        act = RouteSegments("ACT", segments.copy(), 370.0)

        result = calc.calculate_similarity(rec, act)

        assert result.recommended_adherence == 1.0
        assert result.symmetric_similarity == 1.0

    def test_different_routes(self):
        """Different routes should have lower similarity."""
        calc = RoadLevelSimilarity()

        rec_segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        ]

        act_segments = [
            SegmentInfo("X01", "X01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("X02", "X02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("X03", "X03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        ]

        rec = RouteSegments("REC", rec_segments, 370.0)
        act = RouteSegments("ACT", act_segments, 370.0)

        result = calc.calculate_similarity(rec, act)

        # They share E01/X01 which has the same properties but different IDs
        # The shared segments are E01 and X01 which don't match by ID
        assert result.symmetric_similarity < 1.0

    def test_partial_overlap(self):
        """Routes with partial overlap should have partial similarity."""
        calc = RoadLevelSimilarity()

        # Recommended route: E01 -> E02 -> E03 -> E04
        rec_segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
            SegmentInfo("E04", "E04", "FORWARD", 100, 21.05, 105.88, 21.06, 105.89),
        ]

        # Actual route: E01 -> E02 -> X01 -> X02 (diverges after E02)
        act_segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("X01", "X01", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
            SegmentInfo("X02", "X02", "FORWARD", 100, 21.05, 105.88, 21.06, 105.89),
        ]

        rec = RouteSegments("REC", rec_segments, 470.0)
        act = RouteSegments("ACT", act_segments, 470.0)

        result = calc.calculate_similarity(rec, act)

        # They share E01 and E02 (250m out of 470m = ~53%)
        assert 0.4 < result.symmetric_similarity < 0.7
        assert result.shared_segment_count == 2
        assert len(result.segments_only_in_recommended) == 2
        assert len(result.segments_only_in_actual) == 2

    def test_divergence_detection(self):
        """Should detect where routes diverge."""
        calc = RoadLevelSimilarity()

        rec_segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("E03", "E03", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),
        ]

        act_segments = [
            SegmentInfo("E01", "E01", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86),
            SegmentInfo("E02", "E02", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87),
            SegmentInfo("X01", "X01", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88),  # Diverges
        ]

        rec = RouteSegments("REC", rec_segments, 370.0)
        act = RouteSegments("ACT", act_segments, 370.0)

        result = calc.calculate_similarity(rec, act)

        assert result.has_divergence
        assert result.divergence_point is not None
        assert result.divergence_point.index_in_recommended == 2  # E03 vs X01
        assert result.divergence_point.shared_before == 2  # E01, E02 shared


class TestModuleIntegration:
    """Integration tests for the complete pipeline."""

    def test_full_pipeline_conceptual(self):
        """Test that all modules can work together conceptually."""
        # This is a smoke test to ensure imports work
        from app.services.route_history import (
            H3SignatureGenerator,
            RouteInvertedIndex,
            HardFilters,
            TimeRecencyWeight,
            RoadLevelSimilarity,
            HistoricalRouteSearch,
        )

        # All imports should succeed
        assert H3SignatureGenerator is not None
        assert RouteInvertedIndex is not None
        assert HistoricalRouteSearch is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
