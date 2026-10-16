import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.services.route_familiarity.route_matcher import prepare_route, compare_prepared_routes
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.signature import create_route_signature
from backend.app.services.route_familiarity.similarity import ComparisonBudget
from backend.tests.test_route_familiarity_domain import polyline


def fixture():
    return json.loads(Path(__file__).with_name('fixtures').joinpath('synthetic-familiarity-217.json').read_text('utf-8'))


@pytest.mark.parametrize('resolution', [8, 9, 10])
def test_spatial_filter_preserves_reference_intervals_at_each_resolution(resolution):
    coordinates = fixture()['routes'][0]
    proposed = prepare_route(coordinates, resolution)
    for actual_coordinates in [coordinates, [(lat + 0.00025, lon) for lat, lon in coordinates], list(reversed(coordinates))]:
        actual = prepare_route(actual_coordinates, resolution)
        optimized_budget = ComparisonBudget()
        optimized = compare_prepared_routes(proposed, actual, budget=optimized_budget)
        # The exhaustive test oracle may exceed the production cap; production cap is unchanged.
        exhaustive = compare_prepared_routes(proposed, replace(actual, spatial_positions=None), budget=ComparisonBudget(10_000_000))
        assert optimized == exhaustive
        assert optimized_budget.used_pairs < 250_000


def test_spatial_lookup_reduces_217_vertex_route_pair_work():
    prepared = prepare_route(fixture()['routes'][0])
    assert len(fixture()['routes'][0]) == 217
    old_budget = ComparisonBudget()
    compare_prepared_routes(prepared, replace(prepared, spatial_positions=None), budget=old_budget)
    budget = ComparisonBudget()
    result = compare_prepared_routes(prepared, prepared, budget=budget)
    assert result.shared_pct_on_proposed == 100
    assert budget.used_pairs < 250_000
    assert budget.used_pairs * 5 < old_budget.used_pairs


@pytest.mark.asyncio
async def test_real_synthetic_manifest_multicandidate_history_is_available_within_caps(monkeypatch):
    data = fixture()
    def rows(items):
        return [dict(value, geometry=data['routes'][value['route']],
                     started_at=datetime.fromisoformat(value['started_at']),
                     completed_at=datetime.fromisoformat(value['completed_at'])) for value in items]
    class Repository:
        async def personal_routes(self, *_):
            return rows(data['personal'])
        async def community_routes(self, *_):
            return rows(data['community'])
    budgets = {}
    consume = ComparisonBudget.consume
    def record(self, count):
        consume(self, count)
        budgets[id(self)] = (self.max_pairs, self.used_pairs)
    monkeypatch.setattr(ComparisonBudget, 'consume', record)
    signatures = {f'station-{index}': create_route_signature([polyline(route)])
                  for index, route in enumerate(data['routes'][:3])}
    from backend.app.services.route_familiarity import service
    original = service.prepare_route
    monkeypatch.setattr(service, 'prepare_route', lambda *args, **kwargs: replace(original(*args, **kwargs), spatial_positions=None))
    old_result = await RouteFamiliarityService(Repository()).assess_many('fixture', signatures,
                                                                      datetime.fromisoformat(data['as_of']))
    assert all(value.status == 'UNAVAILABLE' and value.degraded_reason == 'SIMILARITY_WORK_LIMIT' for value in old_result.values())
    monkeypatch.setattr(service, 'prepare_route', original)
    budgets.clear()
    result = await RouteFamiliarityService(Repository()).assess_many('fixture', signatures,
                                                                  datetime.fromisoformat(data['as_of']))
    assert all(value.status == 'AVAILABLE' for value in result.values())
    assert all(value.personal_history_trip_count == 5 for value in result.values())
    assert any(value.community_driver_count is not None and value.community_driver_count >= 5 for value in result.values())
    assert all(used <= maximum for maximum, used in budgets.values())
    assert any(maximum == 250_000 for maximum, _ in budgets.values())


@pytest.mark.parametrize('coordinates', [[(0, 179.999), (0, -179.999)], [(85, 0), (85.001, 0.01)]])
def test_dateline_and_polar_index_fallback_retains_reference(coordinates):
    prepared = prepare_route(coordinates)
    assert prepared.spatial_positions is None
    assert compare_prepared_routes(prepared, prepared).shared_pct_on_proposed == 100


def test_near_dateline_neighbor_requires_wrapped_query_fallback():
    proposed = prepare_route([(0, 179.9999), (0.001, 179.9999)])
    actual = prepare_route([(0, -179.9999), (0.001, -179.9999)])
    assert compare_prepared_routes(proposed, actual) == compare_prepared_routes(proposed, replace(actual, spatial_positions=None))


@pytest.mark.parametrize('resolution', [8, 9, 10])
@pytest.mark.parametrize('lateral', [0, 20, 45])
def test_cached_queries_preserve_full_metrics_and_pair_accounting(resolution, lateral):
    route = [(21, 105.8), (21.002, 105.8), (21.002, 105.802)]
    proposed, actual = prepare_route(route, resolution), prepare_route([(lat, lon + 0.0002) for lat, lon in route], resolution)
    cached, reference = ComparisonBudget(), ComparisonBudget()
    result = compare_prepared_routes(proposed, actual, max_lateral_m=lateral, budget=cached)
    fallback = compare_prepared_routes(replace(proposed, query_tiles=None, neighbors=None), actual,
                                      max_lateral_m=lateral, budget=reference)
    assert result == fallback
    assert cached.used_pairs == reference.used_pairs


def test_prepared_query_geometry_is_not_recomputed_for_each_historical_route(monkeypatch):
    import backend.app.services.route_familiarity.route_matcher as matcher
    proposed = prepare_route([(21, 105.8), (21.002, 105.8)])
    actual = prepare_route([(21, 105.8002), (21.002, 105.8002)])
    def unexpected(*args):
        raise AssertionError('prepared default query was recomputed')
    monkeypatch.setattr(matcher, '_tiles', unexpected)
    monkeypatch.setattr(matcher.h3, 'grid_disk', unexpected)
    for _ in range(2):
        assert compare_prepared_routes(proposed, actual).shared_distance_m > 0
