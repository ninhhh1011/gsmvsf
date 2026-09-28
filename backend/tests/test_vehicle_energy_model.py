"""
Unit tests for VinFast Vehicle Energy Model & Dynamic SOC depletion.
Verifies that different vehicle models consume different energy/SOC per km,
and verifies the /api/v1/vehicles and /api/v1/vehicles/energy-step endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.demand.capability import get_capability_resolver, CANONICAL_MODEL_CATALOG
from backend.app.services.demand.models import VehicleCategory


def test_canonical_catalog_has_all_models_with_consumption():
    resolver = get_capability_resolver()
    all_models = resolver.list_all_models()
    assert len(all_models) == 19

    for model_name in all_models:
        cap = resolver.resolve_by_model(model_name)
        assert cap.vehicle_model == model_name
        assert cap.usable_capacity_kwh is not None
        assert cap.usable_capacity_kwh > 0
        assert cap.estimated_consumption_wh_per_km is not None
        assert cap.estimated_consumption_wh_per_km > 0
        assert cap.consumption_source == "PROJECT_ESTIMATE"


def test_energy_drop_variance_across_models():
    """
    Verify Problem A requirement:
    Across 10 km, different vehicle models must lose different SOC percentages:
    e.g. VF 3 drops ~5.5%, VF 9 drops ~2.1%, EVO200 drops ~12.4%.
    """
    resolver = get_capability_resolver()
    vf3 = resolver.resolve_by_model("VF_3")
    vf8 = resolver.resolve_by_model("VF_8")
    vf9 = resolver.resolve_by_model("VF_9")
    evo = resolver.resolve_by_model("EVO200")

    distance_km = 10.0

    drop_vf3 = vf3.calculate_soc_drop(distance_km)
    drop_vf8 = vf8.calculate_soc_drop(distance_km)
    drop_vf9 = vf9.calculate_soc_drop(distance_km)
    drop_evo = evo.calculate_soc_drop(distance_km)

    # Assertions on exact physics:
    # VF3: 10 km * 95 Wh/km = 0.95 kWh. 0.95 / 17.15 * 100 = 5.539%
    assert 5.0 <= drop_vf3 <= 6.0

    # VF8: 10 km * 195 Wh/km = 1.95 kWh. 1.95 / 80.68 * 100 = 2.417%
    assert 2.0 <= drop_vf8 <= 3.0

    # VF9: 10 km * 235 Wh/km = 2.35 kWh. 2.35 / 113.16 * 100 = 2.077%
    assert 1.5 <= drop_vf9 <= 2.5

    # EVO: 10 km * 40 Wh/km = 0.40 kWh. 0.40 / 3.22 * 100 = 12.422%
    assert 11.0 <= drop_evo <= 13.5

    # Crucial property: drop rates must be distinct!
    assert drop_evo > drop_vf3 > drop_vf8 > drop_vf9


def test_api_list_vehicles():
    client = TestClient(app)
    resp = client.get("/api/v1/vehicles")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 19
    models = {v["vehicle_model"] for v in data}
    assert "VF_3" in models
    assert "VF_8" in models
    assert "VF_9" in models
    assert "EVO200" in models


def test_api_energy_step_depletion():
    client = TestClient(app)
    payload = {
        "vehicle_model": "VF_3",
        "distance_km": 10.0,
        "current_soc_pct": 80.0
    }
    resp = client.post("/api/v1/vehicles/energy-step", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["vehicle_model"] == "VF_3"
    assert data["distance_km"] == 10.0
    assert data["previous_soc_pct"] == 80.0
    # Expected drop ~5.54% -> new SOC ~74.46%
    assert 74.0 <= data["current_soc_pct"] <= 75.0
    assert 5.0 <= data["soc_drop_pct"] <= 6.0
    assert data["energy_consumed_kwh"] == 0.95
    assert data["estimated_remaining_range_km"] > 100.0
