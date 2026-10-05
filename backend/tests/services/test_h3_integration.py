"""
Integration tests for H3 Route Comparison Feature.
"""
import pytest
import sys
sys.path.insert(0, 'backend')

# Mock dependencies
class MockLogger:
    def get_logger(self): return self
    def error(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass

sys.modules['structlog'] = MockLogger()
sys.modules['h3'] = type('H3Mock', (), {
    'latlng_to_cell': lambda lat, lng, res: f"h3_cell_{lat}_{lng}",
    'cell_to_latlng': lambda cell: (21.0, 105.0),
})()

def test_h3_signature_generation():
    """Test H3 signature generation from coordinates."""
    from app.services.route_history.signature import H3SignatureGenerator

    gen = H3SignatureGenerator(resolution=10)

    coords = [
        (21.0285, 105.8542),
        (21.0300, 105.8560),
        (21.0315, 105.8580),
    ]

    sig = gen.signature_from_coords("TEST_ROUTE", coords)

    assert sig.route_id == "TEST_ROUTE"
    assert sig.hex_count > 0
    assert sig.start_hex != sig.end_hex

def test_h3_overlap_calculation():
    """Test H3 cell overlap between routes."""
    from app.services.route_history.signature import H3SignatureGenerator

    gen = H3SignatureGenerator(resolution=10)

    # Route A: goes through points 1,2,3,4
    route_a = [
        (21.028, 105.854),
        (21.030, 105.856),
        (21.032, 105.858),
        (21.034, 105.860),
    ]

    # Route B: goes through points 1,2,5,6 (shares 1,2)
    route_b = [
        (21.028, 105.854),
        (21.030, 105.856),
        (21.036, 105.862),
        (21.038, 105.864),
    ]

    sig_a = gen.signature_from_coords("ROUTE_A", route_a)
    sig_b = gen.signature_from_coords("ROUTE_B", route_b)

    common, only_a, only_b = gen.compute_hex_overlap(sig_a, sig_b)

    # Should have some overlap (at least the first 2 cells)
    assert len(common) >= 1

def test_sequential_overlap():
    """Test sequential overlap calculation."""
    from app.services.route_history.signature import H3SignatureGenerator

    gen = H3SignatureGenerator(resolution=10)

    # Nearly identical routes
    route_a = [(21.028, 105.854), (21.030, 105.856), (21.032, 105.858)]
    route_b = [(21.028, 105.854), (21.030, 105.856), (21.033, 105.859)]

    sig_a = gen.signature_from_coords("ROUTE_A", route_a)
    sig_b = gen.signature_from_coords("ROUTE_B", route_b)

    overlap = gen.compute_sequential_overlap(sig_a, sig_b)

    # Should have high overlap
    assert overlap > 0.5

def test_route_similarity_calculation():
    """Test road-level similarity between routes."""
    from app.services.route_history.similarity import (
        RoadLevelSimilarity,
        RouteSegments,
        SegmentInfo
    )

    calc = RoadLevelSimilarity()

    # Create mock segments
    seg1 = SegmentInfo("S1", "S1", "FORWARD", 100, 21.02, 105.85, 21.03, 105.86)
    seg2 = SegmentInfo("S2", "S2", "FORWARD", 150, 21.03, 105.86, 21.04, 105.87)
    seg3 = SegmentInfo("S3", "S3", "FORWARD", 120, 21.04, 105.87, 21.05, 105.88)
    seg4 = SegmentInfo("S4", "S4", "FORWARD", 200, 21.05, 105.88, 21.06, 105.89)

    calc.segment_lookup["S1"] = seg1
    calc.segment_lookup["S2"] = seg2
    calc.segment_lookup["S3"] = seg3
    calc.segment_lookup["S4"] = seg4

    # Route A: S1 -> S2 -> S3 -> S4
    route_a = RouteSegments(
        route_id="ROUTE_A",
        segments=[seg1, seg2, seg3, seg4],
        total_distance_m=570.0
    )

    # Route B: S1 -> S2 -> S4 (shorter, skips S3)
    route_b = RouteSegments(
        route_id="ROUTE_B",
        segments=[seg1, seg2, seg4],
        total_distance_m=450.0
    )

    result = calc.calculate_similarity(route_a, route_b)

    # Should have shared segments S1, S2
    assert result.shared_segment_count >= 2
    assert result.symmetric_similarity > 0
    assert result.symmetric_similarity < 1

def test_bayesian_penalty_integration():
    """Test Bayesian penalty with different family sizes."""
    from app.services.route_history.familiarity import (
        HistoricalFamiliarity,
        FamiliarityConfig,
        FamiliarityContext
    )

    config = FamiliarityConfig(
        enabled=True,
        max_penalty=0.1,
        adherence_threshold=0.5,
        prior_strength=10.0,
        max_reduction_factor=0.3,
    )

    familiarity = HistoricalFamiliarity(config)

    # Same adherence, different family sizes
    adherence = 0.3
    penalties = []

    for size in [1, 10, 50, 100]:
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=adherence,
            family_support=0.5,
            unique_driver_support=0.5,
            historical_trip_count=size,
            has_history=True,
        )

        penalty = familiarity.calculate_penalty(context)
        penalties.append((size, penalty.penalty))

    # Penalty should decrease as family size increases
    for i in range(1, len(penalties)):
        assert penalties[i][1] <= penalties[i-1][1], \
            f"Penalty should decrease: {penalties[i-1]} vs {penalties[i]}"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
