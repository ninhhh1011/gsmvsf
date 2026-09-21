"""
Tests for MockRoutingAdapter and RoutingEngine protocol.
"""

import pytest

from backend.app.services.routing.engine import RoutingEngine
from backend.tests.mock_routing_adapter import MockRoutingAdapter
from backend.app.services.routing.models import (
    Position,
    RouteRequest,
    RouteStatus,
)


def test_mock_adapter_implements_protocol():
    adapter = MockRoutingAdapter()
    assert isinstance(adapter, RoutingEngine)


@pytest.mark.asyncio
async def test_mock_adapter_route_calculation():
    adapter = MockRoutingAdapter(winding_factor=1.0, average_speed_mps=10.0)
    orig = Position(latitude=21.000, longitude=105.800)
    dest = Position(latitude=21.010, longitude=105.800)  # ~1110 meters north
    req = RouteRequest(origin=orig, destination=dest)

    result = await adapter.route(req)
    assert result.status == RouteStatus.SUCCESS
    assert 1000.0 < result.distance_m < 1300.0
    assert result.duration_s > 0.0
    assert len(result.legs) == 1


@pytest.mark.asyncio
async def test_mock_adapter_unreachable_handling():
    adapter = MockRoutingAdapter()
    unreachable = Position(latitude=21.999, longitude=105.999)
    adapter.set_unreachable_point(unreachable.latitude, unreachable.longitude)

    req = RouteRequest(
        origin=Position(latitude=21.0, longitude=105.8),
        destination=unreachable,
    )
    result = await adapter.route(req)
    assert result.status == RouteStatus.NO_ROUTE
    assert result.distance_m == float("inf")
