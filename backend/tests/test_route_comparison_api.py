# backend/tests/test_route_comparison_api.py
"""Tests for dedicated route comparison endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import create_app

@pytest.mark.asyncio
async def test_compare_routes_endpoint_success():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Sample coordinates for Hanoi route: Nga Tu So -> Nga Tu Vong along Truong Chinh
        payload = {
            "proposed_coordinates": [
                [21.0015, 105.8200],
                [21.0005, 105.8250],
                [20.9995, 105.8300],
                [20.9985, 105.8350],
                [20.9975, 105.8400],
            ],
            "actual_coordinates": [
                [21.0015, 105.8200],
                [21.0005, 105.8250],
                [20.9995, 105.8300],
                [20.9985, 105.8350],
                [20.9975, 105.8400],
            ],
            "resolution": 9,
            "lookback_days": 7,
            "vehicle_model": "VF_3",
            "as_of_iso": "2026-09-01T08:00:00+07:00"  # Morning peak
        }
        res = await client.post("/api/v1/routing/compare-routes", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["resolution"] == 9
        assert data["shared_pct_on_proposed"] == pytest.approx(100.0, abs=1.0)
        assert data["shared_pct_on_actual"] == pytest.approx(100.0, abs=1.0)
        assert data["shared_distance_m"] > 0
        assert data["time_window_info"]["time_window"] == "MORNING_PEAK"
        assert data["powertrain_spec"]["vehicle_model"] == "VF_3"
        assert data["powertrain_spec"]["max_motor_power_kw"] == 30.0

@pytest.mark.asyncio
async def test_compare_routes_endpoint_resolution_selector():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "proposed_coordinates": [
                [21.0015, 105.8200],
                [21.0005, 105.8250],
                [20.9995, 105.8300],
            ],
            "actual_coordinates": [
                [21.0015, 105.8200],
                [21.0005, 105.8250],
                [20.9995, 105.8300],
            ],
            "resolution": 8,  # Discrete Res 8
            "vehicle_model": "VF_3",
        }
        res = await client.post("/api/v1/routing/compare-routes", json=payload)
        assert res.status_code == 200
        assert res.json()["resolution"] == 8

@pytest.mark.asyncio
async def test_compare_routes_invalid_resolution_rejected():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "proposed_coordinates": [[21.0, 105.8], [21.01, 105.81]],
            "actual_coordinates": [[21.0, 105.8], [21.01, 105.81]],
            "resolution": 5,  # Only 8, 9, 10 allowed
        }
        res = await client.post("/api/v1/routing/compare-routes", json=payload)
        assert res.status_code == 422
