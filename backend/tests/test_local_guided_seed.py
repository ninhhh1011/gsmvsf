import random
from datetime import UTC, datetime
from collections import defaultdict

import pytest

from scripts.seed_local_guided import departure_indices, validate_route, nearby_points, make_inputs
from scripts.seed_guided_hanoi import sampled


def test_departure_indices_are_varied_confirmable_and_reproducible():
    first = [departure_indices(100, random.Random(seed)) for seed in range(20)]
    assert len(set(first)) > 10
    assert first == [departure_indices(100, random.Random(seed)) for seed in range(20)]
    assert all(5 <= a < b - 4 and b < 96 for a, b in first)


def test_real_routes_must_reach_requested_endpoints_and_have_local_length():
    route = {'coordinates': [[21, 105.8], [21.01, 105.8]], 'distance_m': 1200}
    validate_route(route, [21, 105.8], [21.01, 105.8], 5000)
    with pytest.raises(ValueError, match='snap'):
        validate_route(route, [21.1, 105.8], [21.01, 105.8], 5000)
    with pytest.raises(ValueError, match='length'):
        validate_route(route, [21, 105.8], [21.01, 105.8], 500)


def test_nearby_points_reject_far_hubs():
    points = [{'latitude': 21.01, 'longitude': 105.8}, {'latitude': 21.5, 'longitude': 105.8}]
    assert nearby_points([21, 105.8], points, 500, 2000) == points[:1]


def test_route_with_inside_endpoints_cannot_leave_available_map_scope():
    route = {'coordinates': [[21, 105.8], [21.2, 105.8], [21.01, 105.8]], 'distance_m': 4000}
    with pytest.raises(ValueError, match='outside available map scope'):
        validate_route(route, [21, 105.8], [21.01, 105.8], 5000, bbox=[105.7, 20.9, 105.9, 21.1])


def test_generated_driver_schedules_are_nonoverlapping_and_held_out_is_explicit():
    coordinates = [[21 + i * 0.0003, 105.8] for i in range(60)]
    points = sampled(coordinates)
    template = {'direct': {'coordinates': coordinates}, 'first_index': 8, 'second_index': 30,
        'tail_first': {'coordinates': points[8:]}, 'tail_second': {'coordinates': points[30:]},
        'loop': {'coordinates': [points[8], [points[8][0], 105.801], points[8]]},
        'target': {'id': 'road'}, 'held_out': False}
    manifest = {'seed': 3, 'as_of': datetime(2026, 10, 15, tzinfo=UTC).isoformat(),
        'templates': [dict(template, held_out=index % 6 == 5) for index in range(32)]}
    inputs, truth = make_inputs(manifest, 'testbatch')
    grouped = defaultdict(list)
    for trip in inputs:
        grouped[trip.driver_id].append(trip)
        assert trip.completed_at <= datetime(2026, 10, 15, tzinfo=UTC)
    for trips in grouped.values():
        trips.sort(key=lambda trip: trip.started_at)
        assert all(a.completed_at < b.started_at for a, b in zip(trips, trips[1:]))
    assert any(item['held_out'] for item in truth)
