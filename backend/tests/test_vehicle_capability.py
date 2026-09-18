"""
Unit tests for deterministic Vehicle Capability Resolution.
"""

import pytest

from backend.app.services.demand.capability import (
    CANONICAL_MODEL_CATALOG,
    UnknownVehicleError,
    UnknownVehicleModelError,
    VehicleCapabilityResolver,
    get_capability_resolver,
)
from backend.app.services.demand.models import ServiceType, VehicleCategory


@pytest.fixture
def resolver():
    return get_capability_resolver()


def test_catalog_has_all_19_models(resolver):
    """Verify exact count of 19 official VinFast models."""
    models = resolver.list_all_models()
    assert len(models) == 19
    assert len(CANONICAL_MODEL_CATALOG) == 19


def test_car_models_charging_only(resolver):
    """Verify all 10 EV_CAR models support CHARGING only, never BATTERY_SWAP."""
    car_models = [
        "VF_3", "VF_5", "HERIO_GREEN", "VF_6", "VF_7_ECO",
        "VF_7_PLUS", "VF_8", "VF_9", "VF_E34", "NERIO_GREEN"
    ]
    for model in car_models:
        cap = resolver.resolve_by_model(model)
        assert cap.vehicle_category == VehicleCategory.EV_CAR
        assert cap.charging_supported is True
        assert cap.swap_supported is False
        assert cap.public_swap_compatible is False
        assert cap.allowed_service_types == [ServiceType.CHARGING]
        assert cap.is_service_supported(ServiceType.CHARGING) is True
        assert cap.is_service_supported(ServiceType.BATTERY_SWAP) is False


def test_charge_only_motorcycles(resolver):
    """Verify all 5 charge-only motorcycle models support CHARGING only."""
    charge_only_bikes = ["EVO200", "EVO200_LITE", "FELIZ_S", "KLARA_S_2022", "VENTO_S"]
    for model in charge_only_bikes:
        cap = resolver.resolve_by_model(model)
        assert cap.vehicle_category == VehicleCategory.EV_MOTORBIKE
        assert cap.charging_supported is True
        assert cap.swap_supported is False
        assert cap.allowed_service_types == [ServiceType.CHARGING]
        assert cap.is_service_supported(ServiceType.BATTERY_SWAP) is False


def test_swap_capable_motorcycles(resolver):
    """Verify all 4 swap-capable motorcycle models support CHARGING and BATTERY_SWAP."""
    swap_bikes = ["EVO", "EVO_LITE", "FELIZ_II", "VIPER"]
    for model in swap_bikes:
        cap = resolver.resolve_by_model(model)
        assert cap.vehicle_category == VehicleCategory.EV_MOTORBIKE
        assert cap.charging_supported is True
        assert cap.swap_supported is True
        assert cap.public_swap_compatible is True
        assert set(cap.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}
        assert cap.is_service_supported(ServiceType.CHARGING) is True
        assert cap.is_service_supported(ServiceType.BATTERY_SWAP) is True


def test_no_category_level_swap_shortcut(resolver):
    """Verify that EV_MOTORBIKE category does NOT mean swap-capable."""
    # EVO200 is EV_MOTORBIKE, but CHARGE-ONLY
    evo200 = resolver.resolve_by_model("EVO200")
    assert evo200.vehicle_category == VehicleCategory.EV_MOTORBIKE
    assert evo200.swap_supported is False

    # EVO is EV_MOTORBIKE, and SWAP-CAPABLE
    evo = resolver.resolve_by_model("EVO")
    assert evo.vehicle_category == VehicleCategory.EV_MOTORBIKE
    assert evo.swap_supported is True


def test_resolve_by_vehicle_id(resolver):
    """Verify resolution of real fleet vehicle IDs from vehicles.csv."""
    # V0001 -> VF_3 (Car)
    v1 = resolver.resolve_by_vehicle_id("V0001")
    assert v1.vehicle_model == "VF_3"
    assert v1.swap_supported is False

    # V0003 -> EVO (Swap-capable bike)
    v3 = resolver.resolve_by_vehicle_id("V0003")
    assert v3.vehicle_model == "EVO"
    assert v3.swap_supported is True

    # V0024 -> EVO200 (Charge-only bike)
    v24 = resolver.resolve_by_vehicle_id("V0024")
    assert v24.vehicle_model == "EVO200"
    assert v24.swap_supported is False


def test_unknown_model_raises_error(resolver):
    """Unknown vehicle model must fail safely and explicitly."""
    with pytest.raises(UnknownVehicleModelError):
        resolver.resolve_by_model("TESLA_MODEL_3")

    with pytest.raises(UnknownVehicleModelError):
        resolver.resolve_by_model("")


def test_unknown_vehicle_id_raises_error(resolver):
    """Unknown vehicle ID must fail safely and explicitly."""
    with pytest.raises(UnknownVehicleError):
        resolver.resolve_by_vehicle_id("NONEXISTENT_VEHICLE_9999")
