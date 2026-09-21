"""Week 3 preserves candidate semantics while surfacing real routing failures."""
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.api.v1.candidate import get_candidate_service, set_candidate_service
from backend.app.main import app
from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.models import EnergyServiceRequest
from backend.app.services.routing.engine import RoutingInvalidRequestError
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import RouteResult, RouteStatus


def candidate_request(**changes):
    data = dict(service_request_id="migration", vehicle_id="test-bike", vehicle_model="EVO",
                timestamp=datetime.fromisoformat("2026-09-01T06:10:00+07:00"),
                request_source="AUTO_DETECTED", need_service=True,
                allowed_service_types=["CHARGING", "BATTERY_SWAP"], reason_code="LOW_SOC",
                estimated_remaining_range_km=100, latitude=21.025, longitude=105.82,
                swap_supported=True)
    data.update(changes)
    return CandidateSearchRequest(energy_request=EnergyServiceRequest(**data),
                                  destination_latitude=21.06, destination_longitude=105.86)


def good_route():
    return RouteResult(status=RouteStatus.SUCCESS, distance_m=1500, duration_s=200)


@pytest.mark.asyncio
async def test_both_services_share_station_routes_and_resolve_vehicle_category():
    engine = AsyncMock()
    engine.route.return_value = good_route()
    service = CandidateSearchService(routing_engine=engine)
    result = await service.search_candidates(candidate_request())
    assert result.total_candidates_evaluated == 60
    assert engine.route.call_count == 61
    assert all(call.args[0].profile.vehicle_category == "EV_MOTORBIKE" for call in engine.route.call_args_list)
    # Cache is confined to one request; every new search re-reads the road engine.
    await service.search_candidates(candidate_request())
    assert engine.route.call_count == 122


@pytest.mark.asyncio
async def test_conflicting_category_rejected_before_routing():
    engine = AsyncMock()
    with pytest.raises(RoutingInvalidRequestError):
        await CandidateSearchService(routing_engine=engine).search_candidates(candidate_request(vehicle_type="EV_CAR"))
    engine.route.assert_not_called()


def test_candidate_service_requires_injected_engine():
    with pytest.raises(TypeError):
        CandidateSearchService()


def test_candidate_factory_uses_graphhopper_only():
    set_candidate_service(None)
    try:
        assert isinstance(get_candidate_service().routing_engine, GraphHopperRoutingAdapter)
    finally:
        set_candidate_service(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(RouteStatus.ENGINE_ERROR, 503), (RouteStatus.TIMEOUT, 504),
                                             (RouteStatus.INVALID_REQUEST, 422)])
@pytest.mark.parametrize("endpoint", ["candidate-search", "candidate-search/evaluate", "route"])
async def test_api_dependency_failures_are_explicit(endpoint, status, expected):
    engine = AsyncMock()
    engine.route.return_value = RouteResult(status=status, error_message="test failure")
    set_candidate_service(CandidateSearchService(routing_engine=engine))
    payload = candidate_request().model_dump(mode="json")
    if endpoint == "candidate-search/evaluate":
        payload = dict(vehicle_id="V0004", current_soc_pct=10, estimated_remaining_range_km=20,
                       remaining_trip_distance_km=100, raw_latitude=21.015, raw_longitude=105.78,
                       destination_latitude=21.05, destination_longitude=105.85)
    elif endpoint == "route":
        payload = dict(origin=dict(latitude=21.015, longitude=105.78),
                       destination=dict(latitude=21.05, longitude=105.85),
                       profile=dict(vehicle_category="EV_CAR"))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/api/v1/{endpoint}", json=payload)
        assert response.status_code == expected
        assert "test failure" in response.json()["detail"]
    finally:
        set_candidate_service(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(RouteStatus.SUCCESS, 200), (RouteStatus.NO_ROUTE, 404)])
async def test_route_endpoint_domain_contract(status, expected):
    engine = AsyncMock()
    engine.route.return_value = good_route() if status == RouteStatus.SUCCESS else RouteResult(status=status)
    set_candidate_service(CandidateSearchService(routing_engine=engine))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/route", json=dict(
                origin=dict(latitude=21.015, longitude=105.78), destination=dict(latitude=21.05, longitude=105.85),
                profile=dict(vehicle_category="EV_CAR")))
        assert response.status_code == expected
        if expected == 200:
            assert response.json()["distance_m"] == 1500
            assert response.json()["status"] == "SUCCESS"
    finally:
        set_candidate_service(None)


@pytest.mark.asyncio
@pytest.mark.parametrize("location", [{"latitude": 95}, {"longitude": 190}])
async def test_invalid_candidate_coordinates_are_client_error(location):
    set_candidate_service(CandidateSearchService(routing_engine=AsyncMock()))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/candidate-search", json=candidate_request(**location).model_dump(mode="json"))
        assert response.status_code == 422
    finally:
        set_candidate_service(None)
