"""
Tests for Week 3 Routing domain models.
"""

import pytest
from pydantic import ValidationError

from backend.app.services.routing.models import (
    Position,
    RouteStatus,
    OptimizationObjective,
    RouteLeg,
    RouteRequest,
    RouteResult,
    VehicleRoutingProfile,
)


def test_position_coordinates():
    pos = Position(latitude=21.0285, longitude=105.8542, node_id="N001")
    assert pos.coordinates_lat_lon == (21.0285, 105.8542)
    assert pos.coordinates_lon_lat == (105.8542, 21.0285)


def test_route_request_creation():
    orig = Position(latitude=21.01, longitude=105.80)
    dest = Position(latitude=21.05, longitude=105.85)
    req = RouteRequest(
        origin=orig,
        destination=dest,
        objective=OptimizationObjective.MIN_TRAVEL_TIME,
    )
    assert req.origin == orig
    assert req.destination == dest
    assert req.via == []
    assert req.objective == OptimizationObjective.MIN_TRAVEL_TIME


def test_route_result_creation():
    orig = Position(latitude=21.01, longitude=105.80)
    dest = Position(latitude=21.05, longitude=105.85)
    leg = RouteLeg(
        from_position=orig,
        to_position=dest,
        distance_m=5400.0,
        duration_s=620.0,
    )
    res = RouteResult(
        status=RouteStatus.SUCCESS,
        distance_m=5400.0,
        duration_s=620.0,
        legs=[leg],
        engine_name="test_engine",
    )
    assert res.status == RouteStatus.SUCCESS
    assert res.distance_m == 5400.0
    assert len(res.legs) == 1
    assert res.engine_name == "test_engine"


def test_no_osrm_url_fields_in_route_models():
    with pytest.raises(ValidationError):
        RouteRequest(
            origin=Position(latitude=21.01, longitude=105.80),
            destination=Position(latitude=21.05, longitude=105.85),
            osrm_url="http://localhost:5000/route",  # type: ignore # FORBIDDEN
        )
