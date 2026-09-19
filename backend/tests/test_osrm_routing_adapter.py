"""
Tests for OSRMRoutingAdapter using native unittest.mock.
"""

from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from backend.app.services.routing.models import (
    Position,
    RouteRequest,
    RouteStatus,
)
from backend.app.services.routing.osrm_routing_adapter import OSRMRoutingAdapter


@pytest.mark.asyncio
async def test_osrm_adapter_successful_route():
    orig = Position(latitude=21.0285, longitude=105.8542)
    dest = Position(latitude=21.0360, longitude=105.8300)
    req = RouteRequest(origin=orig, destination=dest)

    mock_json = {
        "code": "Ok",
        "routes": [
            {
                "distance": 3200.5,
                "duration": 480.2,
                "geometry": "sample_polyline",
                "legs": [
                    {
                        "distance": 3200.5,
                        "duration": 480.2,
                    }
                ],
            }
        ],
        "waypoints": [{"location": [105.8542, 21.0285]}, {"location": [105.8300, 21.0360]}],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_json

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    adapter = OSRMRoutingAdapter(base_url="http://mock-osrm:5000", client=mock_client)
    result = await adapter.route(req)

    assert result.status == RouteStatus.SUCCESS
    assert result.distance_m == 3200.5
    assert result.duration_s == 480.2
    assert len(result.legs) == 1
    assert result.engine_name == "osrm"


@pytest.mark.asyncio
async def test_osrm_adapter_no_route():
    orig = Position(latitude=21.0285, longitude=105.8542)
    dest = Position(latitude=21.0360, longitude=105.8300)
    req = RouteRequest(origin=orig, destination=dest)

    mock_json = {
        "code": "NoRoute",
        "message": "Impossible route between points",
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_json

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    adapter = OSRMRoutingAdapter(base_url="http://mock-osrm:5000", client=mock_client)
    result = await adapter.route(req)

    assert result.status == RouteStatus.NO_ROUTE
    assert result.distance_m == float("inf")
    assert result.duration_s == float("inf")


@pytest.mark.asyncio
async def test_osrm_adapter_timeout_handling():
    orig = Position(latitude=21.0285, longitude=105.8542)
    dest = Position(latitude=21.0360, longitude=105.8300)
    req = RouteRequest(origin=orig, destination=dest)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.side_effect = httpx.TimeoutException("Mocked timeout")

    adapter = OSRMRoutingAdapter(base_url="http://mock-osrm:5000", client=mock_client)
    result = await adapter.route(req)

    assert result.status == RouteStatus.TIMEOUT
    assert result.distance_m == float("inf")
    assert "timed out" in (result.error_message or "")


@pytest.mark.asyncio
async def test_osrm_adapter_server_error():
    orig = Position(latitude=21.0285, longitude=105.8542)
    dest = Position(latitude=21.0360, longitude=105.8300)
    req = RouteRequest(origin=orig, destination=dest)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    adapter = OSRMRoutingAdapter(base_url="http://mock-osrm:5000", client=mock_client)
    result = await adapter.route(req)

    assert result.status == RouteStatus.ENGINE_ERROR
    assert result.distance_m == float("inf")
