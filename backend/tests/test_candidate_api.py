"""
Tests for Candidate Search REST API endpoints.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.api.v1.candidate import set_candidate_service, get_candidate_service
from backend.app.main import app
from backend.app.services.candidate.service import CandidateSearchService
from backend.tests.mock_routing_adapter import MockRoutingAdapter
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter


@pytest.fixture(autouse=True)
def setup_mock_service():
    mock_engine = MockRoutingAdapter(winding_factor=1.2, average_speed_mps=8.33)
    service = CandidateSearchService(routing_engine=mock_engine)
    set_candidate_service(service)
    yield
    set_candidate_service(None)


@pytest.mark.asyncio
async def test_api_candidate_search_post():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "energy_request": {
                "service_request_id": "REQ-API-01",
                "vehicle_id": "V0004",
                "vehicle_model": "VF_6",
                "vehicle_type": "EV_CAR",
                "timestamp": "2026-09-01T06:20:00+07:00",
                "request_source": "AUTO_DETECTED",
                "need_service": True,
                "allowed_service_types": ["CHARGING"],
                "resolved_service_type": "CHARGING",
                "request_valid": True,
                "reason_code": "LOW_SOC",
                "current_soc_pct": 16.0,
                "estimated_remaining_range_km": 45.0,
                "latitude": 21.015,
                "longitude": 105.780,
                "swap_supported": False,
                "charging_supported": True,
            },
            "destination_latitude": 21.050,
            "destination_longitude": 105.850,
        }
        resp = await client.post("/api/v1/candidate-search", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["service_request_id"] == "REQ-API-01"
        assert data["search_status"] == "SUCCESS"
        assert data["total_candidates_evaluated"] == 30
        assert data["eligible_count"] > 0
        assert len(data["candidates"]) == 30


@pytest.mark.asyncio
async def test_api_candidate_search_eligible_only():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "energy_request": {
                "service_request_id": "REQ-API-02",
                "vehicle_id": "V0004",
                "vehicle_model": "VF_6",
                "vehicle_type": "EV_CAR",
                "timestamp": "2026-09-01T06:20:00+07:00",
                "request_source": "AUTO_DETECTED",
                "need_service": True,
                "allowed_service_types": ["CHARGING"],
                "resolved_service_type": "CHARGING",
                "request_valid": True,
                "reason_code": "LOW_SOC",
                "current_soc_pct": 16.0,
                "estimated_remaining_range_km": 45.0,
                "latitude": 21.015,
                "longitude": 105.780,
                "swap_supported": False,
                "charging_supported": True,
            },
            "destination_latitude": 21.050,
            "destination_longitude": 105.850,
        }
        resp = await client.post("/api/v1/candidate-search?eligible_only=true", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_status"] == "SUCCESS"
        assert len(data["candidates"]) == data["eligible_count"]
        assert all(c["eligible"] is True for c in data["candidates"])


@pytest.mark.asyncio
async def test_api_evaluate_and_search():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "vehicle_id": "V0004",
            "current_soc_pct": 12.0,
            "estimated_remaining_range_km": 25.0,
            "remaining_trip_distance_km": 50.0,
            "safety_reserve_km": 15.0,
            "raw_latitude": 21.015,
            "raw_longitude": 105.780,
            "destination_latitude": 21.050,
            "destination_longitude": 105.850,
        }
        resp = await client.post("/api/v1/candidate-search/evaluate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_status"] == "SUCCESS"
        assert data["total_candidates_evaluated"] > 0


def test_graphhopper_adapter_satisfies_protocol():
    """Verify GraphHopperRoutingAdapter satisfies the RoutingEngine protocol."""
    from backend.app.services.routing.engine import RoutingEngine

    adapter = GraphHopperRoutingAdapter(base_url="http://localhost:8989")
    assert isinstance(adapter, RoutingEngine)


@pytest.mark.asyncio
async def test_graphhopper_routing_adapter_route():
    """Test GraphHopperRoutingAdapter with a mocked response."""
    from backend.app.services.routing.models import Position, RouteRequest, VehicleRoutingProfile

    mock_json = {
        "paths": [
            {
                "distance": 5000.0,
                "time": 600000,  # milliseconds
                "points": "_p~iF~ps|U",
                "details": {"leg_distance": [[0, 4, 5000.0]], "leg_time": [[0, 4, 600000]]},
            }
        ],
        "waypoints": [
            {"location": [105.8542, 21.0285]},
            {"location": [105.8300, 21.0360]},
        ],
    }

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_json

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    adapter = GraphHopperRoutingAdapter(
        base_url="http://mock-gh:8989",
        client=mock_client,
    )

    from backend.app.services.routing.models import RouteStatus

    orig = Position(latitude=21.0285, longitude=105.8542)
    dest = Position(latitude=21.0360, longitude=105.8300)
    req = RouteRequest(origin=orig, destination=dest,
                       profile=VehicleRoutingProfile(vehicle_category="EV_MOTORBIKE"))
    result = await adapter.route(req)

    assert result.status == RouteStatus.SUCCESS
    assert result.distance_m == 5000.0
    assert result.duration_s == 600.0
    assert result.engine_name == "graphhopper"
