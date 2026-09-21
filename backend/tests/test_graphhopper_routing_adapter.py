"""GraphHopper 11 HTTP contract and failure regression checks."""
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import (
    DynamicRoutingContext, OptimizationObjective, Position, RouteConstraints,
    RouteRequest, RouteStatus, VehicleRoutingProfile,
)

ORIGIN = Position(latitude=21.0285, longitude=105.8542)
DESTINATION = Position(latitude=21.036, longitude=105.83)
PATH = {
    "distance": 3200.5, "time": 480200, "points": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
    "details": {"leg_distance": [[0, 12, 3200.5]], "leg_time": [[0, 12, 480200]]},
}


def request(category="EV_CAR", **kwargs):
    return RouteRequest(origin=ORIGIN, destination=DESTINATION,
                        profile=VehicleRoutingProfile(vehicle_category=category), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("category,profile", [("EV_CAR", "car"), ("EV_MOTORBIKE", "motorcycle")])
async def test_route_uses_category_and_actual_encoded_geometry(category, profile):
    def handler(req):
        assert req.url.path == "/route"
        assert req.url.params.get_list("point") == ["21.028500,105.854200", "21.036000,105.830000"]
        assert req.url.params["profile"] == profile
        assert req.url.params.get_list("details") == ["leg_distance", "leg_time"]
        return httpx.Response(200, json={"paths": [PATH]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GraphHopperRoutingAdapter(base_url="http://gh", client=client).route(request(category))
    assert result.status == RouteStatus.SUCCESS
    assert result.geometry == PATH["points"]
    assert (result.distance_m, result.duration_s) == (3200.5, 480.2)
    assert (result.legs[0].distance_m, result.legs[0].duration_s) == (3200.5, 480.2)
    assert result.raw_metadata["profile"] == profile


@pytest.mark.asyncio
async def test_via_uses_unequal_actual_leg_metrics():
    waypoint = Position(latitude=21.032, longitude=105.84)
    path = dict(PATH, details={"leg_distance": [[0, 3, 200.5], [3, 12, 3000]],
                              "leg_time": [[0, 3, 20200], [3, 12, 460000]]})
    def handler(req):
        assert req.url.params.get_list("point")[1] == "21.032000,105.840000"
        return httpx.Response(200, json={"paths": [path]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GraphHopperRoutingAdapter(base_url="http://gh", client=client).route(request(via=[waypoint]))
    assert result.status == RouteStatus.SUCCESS
    assert [leg.distance_m for leg in result.legs] == [200.5, 3000]
    assert [leg.duration_s for leg in result.legs] == [20.2, 460]
    assert result.legs[0].to_position == result.legs[1].from_position == waypoint


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"paths": []}, {"paths": [None]}, {"paths": [dict(PATH, points={"encoded": "wrong"})]},
    {"paths": [dict(PATH, distance=-1)]}, {"paths": [dict(PATH, time="NaN")]},
    {"paths": [dict(PATH, details={})]}, {"paths": [dict(PATH, details={"leg_distance": [[0, 12, -1]], "leg_time": [[0, 12, 1]]})]}])
async def test_malformed_success_is_engine_error(body):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))) as client:
        result = await GraphHopperRoutingAdapter(base_url="http://gh", client=client).route(request())
    assert result.status == RouteStatus.ENGINE_ERROR
    assert result.distance_m == float("inf")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,expected", [
    (400, {"message": "Connection between locations not found", "hints": [{"details": "com.graphhopper.util.exceptions.ConnectionNotFoundException"}]}, RouteStatus.NO_ROUTE),
    (400, {"message": "Point not found", "hints": [{"details": "com.graphhopper.util.exceptions.PointNotFoundException"}]}, RouteStatus.NO_ROUTE),
    (400, {"message": "Unknown profile"}, RouteStatus.INVALID_REQUEST),
    (503, {"message": "Unavailable"}, RouteStatus.ENGINE_ERROR),
    (404, {}, RouteStatus.ENGINE_ERROR),
])
async def test_http_failure_classification(status, body, expected):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body))) as client:
        result = await GraphHopperRoutingAdapter(base_url="http://gh", client=client).route(request())
    assert result.status == expected
    assert result.distance_m == float("inf")


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [(httpx.ReadTimeout("slow"), RouteStatus.TIMEOUT),
                                           (httpx.ConnectError("offline"), RouteStatus.ENGINE_ERROR)])
async def test_transport_failure_no_fallback(error, expected):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = error
    result = await GraphHopperRoutingAdapter(client=client).route(request())
    assert result.status == expected
    assert client.get.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"profile": None}, {"profile": VehicleRoutingProfile(vehicle_category="UNKNOWN")},
    {"profile": VehicleRoutingProfile(vehicle_category="EV_CAR", routing_profile_hint="motorcycle")},
    {"constraints": RouteConstraints(avoid_segments=["123"])},
    {"constraints": RouteConstraints(max_distance_m=10)},
    {"constraints": RouteConstraints(custom={"avoid_tolls": True})},
    {"objective": OptimizationObjective.MIN_DISTANCE},
    {"dynamic_context": DynamicRoutingContext(traffic_delay_factor=1.2)},
])
async def test_unsupported_request_rejected_before_http(changes):
    client = AsyncMock(spec=httpx.AsyncClient)
    result = await GraphHopperRoutingAdapter(client=client).route(request().model_copy(update=changes))
    assert result.status == RouteStatus.INVALID_REQUEST
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_non_json_success_is_engine_error():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="bad json"))) as client:
        result = await GraphHopperRoutingAdapter(base_url="http://gh", client=client).route(request())
    assert result.status == RouteStatus.ENGINE_ERROR
