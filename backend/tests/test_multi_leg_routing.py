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
