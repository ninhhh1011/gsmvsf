"""
API Integration tests for Week 2 Demand Detection and Week 1 State Integration.
"""

from datetime import datetime
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.app.services.demand.models import (
    ReasonCode,
    RequestedServiceType,
    RequestSource,
    ServiceType,
)
from backend.app.services.realtime.state import reset_state_store
from backend.app.services.realtime.driver_state_manager import (
    reset_driver_state_manager,
    set_driver_state_manager,
    DriverStateManager,
)


@pytest.fixture
def app():
    return create_app()


@pytest.fixture(autouse=True)
def clean_state():
    reset_state_store()
    yield
    reset_state_store()


@pytest.mark.asyncio
async def test_evaluate_auto_demand_car(app):
    """POST /api/v1/demand/evaluate for a car with low SOC."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "vehicle_id": "V0001",
            "driver_id": "D0001",
            "trip_id": "T0001",
            "current_soc_pct": 12.0,
            "estimated_remaining_range_km": 20.0,
            "remaining_trip_distance_km": 30.0,
            "minimum_safe_soc_pct": 15.0,
        }
        res = await client.post("/api/v1/demand/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["request_source"] == RequestSource.AUTO_DETECTED.value
        assert data["need_service"] is True
        assert data["allowed_service_types"] == [ServiceType.CHARGING.value]
        assert data["resolved_service_type"] == ServiceType.CHARGING.value
        assert data["reason_code"] == ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE.value
        assert data["vehicle_model"] == "VF_3"


@pytest.mark.asyncio
async def test_evaluate_auto_demand_swap_bike_unresolved(app):
    """POST /api/v1/demand/evaluate for a swap-capable bike with low SOC must remain unresolved."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "vehicle_id": "V0003",  # EVO (swap-capable)
            "driver_id": "D0003",
            "current_soc_pct": 10.0,
            "estimated_remaining_range_km": 8.0,
            "remaining_trip_distance_km": 20.0,
            "minimum_safe_soc_pct": 15.0,
        }
        res = await client.post("/api/v1/demand/evaluate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["need_service"] is True
        assert set(data["allowed_service_types"]) == {ServiceType.CHARGING.value, ServiceType.BATTERY_SWAP.value}
        assert data["resolved_service_type"] is None, "Swap-capable bike must have resolved_service_type=None"


@pytest.mark.asyncio
async def test_driver_request_car_battery_swap_rejected(app):
    """POST /api/v1/demand/request: Car requesting swap is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "vehicle_id": "V0001",
            "requested_service_type": "BATTERY_SWAP",
            "current_soc_pct": 25.0,
        }
        res = await client.post("/api/v1/demand/request", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["request_source"] == RequestSource.DRIVER_REQUEST.value
        assert data["request_valid"] is False
        assert data["resolved_service_type"] is None
        assert data["reason_code"] == ReasonCode.UNSUPPORTED_SERVICE.value


@pytest.mark.asyncio
async def test_driver_request_swap_bike_any(app):
    """POST /api/v1/demand/request: Swap bike requesting ANY -> valid, unresolved."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "vehicle_id": "V0003",
            "requested_service_type": "ANY",
            "current_soc_pct": 25.0,
        }
        res = await client.post("/api/v1/demand/request", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["request_valid"] is True
        assert data["requested_service_type"] == "ANY"
        assert data["resolved_service_type"] is None
        assert set(data["allowed_service_types"]) == {ServiceType.CHARGING.value, ServiceType.BATTERY_SWAP.value}


@pytest.mark.asyncio
async def test_get_vehicle_capability(app):
    """GET /api/v1/vehicles/{vehicle_id}/capability and models endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Known vehicle
        res = await client.get("/api/v1/vehicles/V0001/capability")
        assert res.status_code == 200
        data = res.json()
        assert data["vehicle_model"] == "VF_3"
        assert data["charging_supported"] is True
        assert data["swap_supported"] is False

        # Unknown vehicle -> 404
        res_404 = await client.get("/api/v1/vehicles/UNKNOWN_999/capability")
        assert res_404.status_code == 404

        # Known model
        res_m = await client.get("/api/v1/vehicles/models/EVO/capability")
        assert res_m.status_code == 200
        data_m = res_m.json()
        assert data_m["swap_supported"] is True

        # Unknown model -> 404
        res_m_404 = await client.get("/api/v1/vehicles/models/UNKNOWN_MODEL/capability")
        assert res_m_404.status_code == 404


@pytest.mark.asyncio
async def test_week1_realtime_state_integration():
    """
    Test POST /api/v1/drivers/{driver_id}/demand/evaluate integrates with
    Week 1 realtime GPS tracking state.
    """
    # Set up local-only driver state manager for testing
    reset_state_store()
    reset_driver_state_manager()
    set_driver_state_manager(DriverStateManager.for_local())

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        driver_id = "D0001"

        # 1. Ingest GPS observation into Week 1 endpoint
        gps_payload = {
            "observation_id": "OBS-001",
            "driver_id": driver_id,
            "timestamp": "2026-09-01T06:06:00Z",
            "latitude": 21.0285,
            "longitude": 105.8542,
            "speed_kmh": 30.0,
        }
        loc_res = await client.post(f"/api/v1/drivers/{driver_id}/location", json=gps_payload)
        assert loc_res.status_code == 200

        # 2. Call Week 2 driver demand evaluation endpoint (without passing lat/lon)
        demand_payload = {
            "vehicle_id": "V0001",
            "current_soc_pct": 10.0,
            "estimated_remaining_range_km": 15.0,
            "remaining_trip_distance_km": 40.0,
            "minimum_safe_soc_pct": 15.0,
        }
        res = await client.post(f"/api/v1/drivers/{driver_id}/demand/evaluate", json=demand_payload)
        assert res.status_code == 200
        data = res.json()

        # 3. Verify location was populated from Week 1 state
        assert data["latitude"] == pytest.approx(21.0285)
        assert data["longitude"] == pytest.approx(105.8542)
        assert data["driver_id"] == driver_id
        assert data["need_service"] is True
        assert data["resolved_service_type"] == ServiceType.CHARGING.value

    # Clean up
    reset_state_store()
    reset_driver_state_manager()
