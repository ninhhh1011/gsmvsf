# backend/tests/test_direction_aware_h3_matcher.py
"""Tests for direction- and sequence-aware H3 route discretization and comparison."""
import pytest
from backend.app.services.route_familiarity.route_matcher import (
    match_and_compare_routes,
    RouteComparisonMetrics,
)

def test_identical_routes_100_percent():
    # Route along Nguyen Trai corridor (approx 1.5 km)
    route_a = [
        (21.0015, 105.8200),
        (20.9980, 105.8150),
        (20.9940, 105.8100),
        (20.9900, 105.8050),
    ]
    route_b = list(route_a)

    res = match_and_compare_routes(route_a, route_b, resolution=9)
    assert res.shared_distance_m > 0
    assert res.shared_pct_on_proposed == pytest.approx(100.0, abs=1.0)
    assert res.shared_pct_on_actual == pytest.approx(100.0, abs=1.0)
    assert res.resolution == 9
    assert res.shared_cells_count > 0

def test_parallel_opposite_direction_rejected():
    # Route Northbound vs Route Southbound along parallel lanes
    route_north = [
        (20.9900, 105.8050),
        (20.9940, 105.8100),
        (20.9980, 105.8150),
        (21.0015, 105.8200),
    ]
    # Opposite heading (180 deg reversal) on parallel lane (~25m away)
    route_south = [
        (21.0015, 105.8203),
        (20.9980, 105.8153),
        (20.9940, 105.8103),
        (20.9900, 105.8053),
    ]
    # Even if H3-9 contains both, direction verification must reject false match
    res = match_and_compare_routes(route_north, route_south, resolution=9)
    assert res.shared_pct_on_proposed < 10.0  # Rejected due to opposite direction

def test_dual_percentage_when_lengths_differ():
    # Route A (Proposed) shares 1 km then reaches destination.
    # Route B (Actual) shares 1 km then takes 2 km detour before ending.
    shared_part = [
        (21.000, 105.800),
        (21.005, 105.805),
        (21.010, 105.810),
    ]
    route_a_end = [(21.015, 105.815)]
    route_b_detour = [
        (21.015, 105.820),
        (21.020, 105.825),
        (21.025, 105.830),
    ]

    route_a = shared_part + route_a_end
    route_b = shared_part + route_b_detour

    res = match_and_compare_routes(route_a, route_b, resolution=9)
    assert res.shared_distance_m > 0
    # Overlap on proposed must be higher than overlap on actual because Route B is longer
    assert res.shared_pct_on_proposed > res.shared_pct_on_actual
    assert res.proposed_distance_m < res.actual_distance_m

def test_multi_resolution_support():
    route_a = [
        (21.0015, 105.8200),
        (20.9980, 105.8150),
        (20.9940, 105.8100),
        (20.9900, 105.8050),
    ]
    route_b = list(route_a)

    res8 = match_and_compare_routes(route_a, route_b, resolution=8)
    res9 = match_and_compare_routes(route_a, route_b, resolution=9)
    res10 = match_and_compare_routes(route_a, route_b, resolution=10)

    assert res8.resolution == 8
    assert res9.resolution == 9
    assert res10.resolution == 10
    # Number of unique cells traversed increases as resolution increases (finer cells)
    assert res8.shared_cells_count <= res9.shared_cells_count <= res10.shared_cells_count

def test_zero_length_routes():
    res = match_and_compare_routes([], [], resolution=9)
    assert res.shared_distance_m == 0.0
    assert res.shared_pct_on_proposed == 0.0
    assert res.shared_pct_on_actual == 0.0
