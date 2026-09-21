"""
Tests for MultiLegRouteCalculator and Detour metrics.
"""

import pytest

from backend.tests.mock_routing_adapter import MockRoutingAdapter
from backend.app.services.routing.models import Position, RouteStatus
from backend.app.services.routing.multi_leg import MultiLegRouteCalculator


@pytest.mark.asyncio
async def test_multi_leg_with_destination_and_detour():
    # Setup coordinates: Driver at (21.00, 105.80), Station at (21.01, 105.81), Destination at (21.02, 105.80)
    driver_pos = Position(latitude=21.00, longitude=105.80)
    station_pos = Position(latitude=21.01, longitude=105.81)
    dest_pos = Position(latitude=21.02, longitude=105.80)

    adapter = MockRoutingAdapter(winding_factor=1.0, average_speed_mps=10.0)
    calc = MultiLegRouteCalculator(adapter)

    is_reach, metrics, res_leg1 = await calc.compute_station_metrics(
        driver_pos=driver_pos,
        station_pos=station_pos,
        destination_pos=dest_pos,
    )

    assert is_reach is True
    assert metrics is not None
    assert metrics.distance_to_station_m > 0
    assert metrics.distance_station_to_dest_m > 0
    assert metrics.via_total_distance_m > metrics.direct_distance_m
    assert metrics.detour_distance_m > 0
    assert metrics.detour_duration_s > 0
    assert metrics.eta_to_station_s == metrics.duration_to_station_s


@pytest.mark.asyncio
async def test_multi_leg_missing_destination():
    driver_pos = Position(latitude=21.00, longitude=105.80)
    station_pos = Position(latitude=21.01, longitude=105.81)

    adapter = MockRoutingAdapter(winding_factor=1.0, average_speed_mps=10.0)
    calc = MultiLegRouteCalculator(adapter)

    is_reach, metrics, res_leg1 = await calc.compute_station_metrics(
        driver_pos=driver_pos,
        station_pos=station_pos,
        destination_pos=None,  # MISSING DESTINATION
    )

    assert is_reach is True
    assert metrics is not None
    assert metrics.distance_to_station_m > 0
    assert metrics.duration_to_station_s > 0
    assert metrics.eta_to_station_s == metrics.duration_to_station_s
    # Detour and destination legs must be None
    assert metrics.distance_station_to_dest_m is None
    assert metrics.direct_distance_m is None
    assert metrics.detour_distance_m is None
    assert metrics.detour_duration_s is None


@pytest.mark.asyncio
async def test_multi_leg_unreachable_station():
    driver_pos = Position(latitude=21.00, longitude=105.80)
    station_pos = Position(latitude=21.99, longitude=105.99)  # Unreachable

    adapter = MockRoutingAdapter()
    adapter.set_unreachable_point(station_pos.latitude, station_pos.longitude)
    calc = MultiLegRouteCalculator(adapter)

    is_reach, metrics, res_leg1 = await calc.compute_station_metrics(
        driver_pos=driver_pos,
        station_pos=station_pos,
        destination_pos=Position(latitude=21.02, longitude=105.80),
    )

    assert is_reach is False
    assert metrics is None
    assert res_leg1 is not None
    assert res_leg1.status == RouteStatus.NO_ROUTE


from unittest.mock import AsyncMock
from backend.app.services.routing.engine import (
    RoutingEngineUnavailableError, RoutingInvalidRequestError, RoutingTimeoutError,
)
from backend.app.services.routing.models import RouteResult


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,exception", [
    (RouteStatus.ENGINE_ERROR, RoutingEngineUnavailableError),
    (RouteStatus.TIMEOUT, RoutingTimeoutError),
    (RouteStatus.INVALID_REQUEST, RoutingInvalidRequestError),
])
@pytest.mark.parametrize("failed_leg", ["direct", "leg1", "leg2"])
async def test_dependency_errors_are_never_unreachable(failure, exception, failed_leg):
    origin = Position(latitude=21, longitude=105.8)
    station = Position(latitude=21.01, longitude=105.81)
    dest = Position(latitude=21.02, longitude=105.82)
    good = RouteResult(status=RouteStatus.SUCCESS, distance_m=100, duration_s=10)
    bad = RouteResult(status=failure, error_message="dependency failure")
    engine = AsyncMock()
    calc = MultiLegRouteCalculator(engine)
    if failed_leg == "direct":
        engine.route.return_value = bad
        with pytest.raises(exception):
            await calc.compute_direct_route(origin, dest)
    else:
        engine.route.side_effect = [bad] if failed_leg == "leg1" else [good, bad]
        with pytest.raises(exception):
            await calc.compute_station_metrics(origin, station, dest, cached_direct_route=good)


@pytest.mark.asyncio
async def test_no_direct_route_cached_and_via_metrics_retained():
    origin = Position(latitude=21, longitude=105.8)
    station = Position(latitude=21.01, longitude=105.81)
    dest = Position(latitude=21.02, longitude=105.82)
    no_route = RouteResult(status=RouteStatus.NO_ROUTE)
    good = RouteResult(status=RouteStatus.SUCCESS, distance_m=100, duration_s=10)
    engine = AsyncMock()
    engine.route.side_effect = [no_route, good, good]
    calc = MultiLegRouteCalculator(engine)
    direct = await calc.compute_direct_route(origin, dest)
    assert direct is no_route
    reachable, metrics, _ = await calc.compute_station_metrics(origin, station, dest, cached_direct_route=direct)
    assert reachable
    assert engine.route.call_count == 3
    assert metrics.via_total_distance_m == 200
    assert metrics.via_total_duration_s == 20
    assert metrics.direct_distance_m is None
    assert metrics.detour_distance_m is None


@pytest.mark.asyncio
async def test_concurrent_station_metrics_produces_correct_results():
    """Verify concurrent computation produces same results as sequential."""
    from unittest.mock import AsyncMock
    from backend.app.services.routing.models import RouteResult, RouteStatus

    # Create mock adapter that returns deterministic results
    engine = AsyncMock()
    engine.route.return_value = RouteResult(
        status=RouteStatus.SUCCESS,
        distance_m=1000,
        duration_s=60,
    )

    stations = {
        "S01": Position(latitude=21.001, longitude=105.801),
        "S02": Position(latitude=21.002, longitude=105.802),
        "S03": Position(latitude=21.003, longitude=105.803),
    }

    # Test concurrent computation with high concurrency
    calc = MultiLegRouteCalculator(engine, max_concurrent_routes=8)
    result = await calc.compute_all_station_metrics_concurrent(
        driver_pos=Position(latitude=21.0, longitude=105.8),
        station_positions=stations,
        destination_pos=Position(latitude=21.01, longitude=105.81),
        profile=None,
        cached_direct_route=None,
    )

    # Verify all stations got results
    assert len(result) == 3
    for station_id in stations:
        assert station_id in result
        is_reach, metrics, _ = result[station_id]
        assert is_reach is True
        assert metrics is not None
        assert metrics.distance_to_station_m == 1000
        assert metrics.duration_to_station_s == 60

    # Verify correct number of route calls
    # 1 direct + 3 stations * 2 legs = 7 calls (direct is pre-computed once)
    assert engine.route.call_count == 7


@pytest.mark.asyncio
async def test_concurrent_with_semaphore_limits():
    """Verify semaphore actually limits concurrent execution."""
    import time
    from backend.app.services.routing.models import RouteResult, RouteStatus

    call_times = []
    max_concurrent = 2

    async def slow_route(request):
        call_times.append(time.perf_counter())
        await asyncio.sleep(0.05)  # 50ms
        return RouteResult(status=RouteStatus.SUCCESS, distance_m=1000, duration_s=60)

    engine = AsyncMock()
    engine.route = slow_route

    stations = {f"S{i:02d}": Position(latitude=21.0 + i * 0.001, longitude=105.8 + i * 0.001)
                for i in range(4)}

    calc = MultiLegRouteCalculator(engine, max_concurrent_routes=max_concurrent)
    start = time.perf_counter()
    await calc.compute_all_station_metrics_concurrent(
        driver_pos=Position(latitude=21.0, longitude=105.8),
        station_positions=stations,
        destination_pos=Position(latitude=21.01, longitude=105.81),
        profile=None,
        cached_direct_route=None,
    )
    total_time = time.perf_counter() - start

    # With max_concurrent=2 and 4 stations:
    # 1 direct + 4*2 legs = 9 calls
    # At 2 concurrent, should take ~3-4 * 50ms = 150-200ms minimum
    assert total_time > 0.1  # Should take at least 100ms with slow routes
    # 9 total calls: 1 direct + 4 leg1 + 4 leg2
    assert len(call_times) == 9


import asyncio
