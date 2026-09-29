"""
Unit and live integration tests for Dynamic Congestion Route Avoidance (Block 3).
Verifies:
- RouteRequest with avoid_areas custom constraints sends POST to GraphHopper with custom_model.
- Live GraphHopper engine successfully calculates detour around congested zone.
"""
import pytest
from unittest.mock import AsyncMock
import httpx

from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import (
    OptimizationObjective,
    Position,
    RouteConstraints,
    RouteRequest,
    RouteStatus,
    VehicleRoutingProfile,
)


def sample_request(avoid_areas=None, priority=0.05) -> RouteRequest:
    constraints = RouteConstraints(custom={"avoid_areas": avoid_areas, "congestion_priority": priority}) if avoid_areas else None
    return RouteRequest(
        origin=Position(latitude=21.028, longitude=105.854),
        destination=Position(latitude=21.036, longitude=105.830),
        profile=VehicleRoutingProfile(vehicle_category="EV_CAR"),
        constraints=constraints,
        objective=OptimizationObjective.MIN_TRAVEL_TIME,
    )


@pytest.mark.asyncio
async def test_route_with_avoid_areas_constructs_custom_model():
    """Verify adapter serializes custom_model with areas and priority on POST."""
    poly = {
        "type": "Polygon",
        "coordinates": [[[105.84, 21.028], [105.85, 21.028], [105.85, 21.035], [105.84, 21.035], [105.84, 21.028]]]
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(200, json={
        "paths": [{
            "distance": 4500.0,
            "time": 360000,
            "points": "encoded_poly_test",
            "details": {
                "leg_distance": [[0, 10, 4500.0]],
                "leg_time": [[0, 10, 360000]],
            }
        }]
    })

    adapter = GraphHopperRoutingAdapter(base_url="http://gh:8989", client=client)
    req = sample_request(avoid_areas=[poly], priority=0.05)
    result = await adapter.route(req)

    assert result.status == RouteStatus.SUCCESS
    assert result.distance_m == 4500.0
    assert result.duration_s == 360.0
    assert client.post.call_count == 1
    call_args, call_kwargs = client.post.call_args
    assert call_args[0] == "http://gh:8989/route"
    json_body = call_kwargs["json"]
    assert json_body["ch.disable"] is True
    assert "custom_model" in json_body
    assert len(json_body["custom_model"]["areas"]["features"]) == 1
    assert json_body["custom_model"]["priority"][0]["multiply_by"] == "0.05"


@pytest.mark.asyncio
async def test_live_congestion_avoidance_detour():
    """Live verification against local GraphHopper container: detour geometry and distance shift."""
    poly = {
        "type": "Polygon",
        "coordinates": [[[105.840, 21.028], [105.850, 21.028], [105.850, 21.035], [105.840, 21.035], [105.840, 21.028]]]
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        adapter = GraphHopperRoutingAdapter(base_url="http://127.0.0.1:8989", client=client)

        # Standard Route
        normal_req = sample_request(avoid_areas=None)
        normal_res = await adapter.route(normal_req)
        assert normal_res.status == RouteStatus.SUCCESS

        # Congestion Avoidance Route
        avoid_req = sample_request(avoid_areas=[poly], priority=0.05)
        avoid_res = await adapter.route(avoid_req)
        assert avoid_res.status == RouteStatus.SUCCESS

        # Detour must be longer because direct shortest path through congested polygon is blocked
        assert avoid_res.distance_m > normal_res.distance_m
        assert avoid_res.geometry != normal_res.geometry
        print(f"Normal distance: {normal_res.distance_m:.1f}m -> Avoidance distance: {avoid_res.distance_m:.1f}m")
