"""
Tests verifying that the system supports multiple cities and multiple EV brands/models,
rather than having hardcoded Hanoi and VinFast assumptions.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.services.demand.capability import (
    VehicleCapabilityResolver,
    reset_capability_resolver,
)
from backend.app.services.demand.models import (
    DemandContext,
    VehicleCapability,
    VehicleCategory,
)
from backend.app.services.demand.service import DemandService


def test_city_configuration_supports_multiple_cities():
    """Verify city and geographic bounding boxes are configurable."""
    # 1. Default Hanoi configuration
    default_settings = Settings()
    assert default_settings.city_name == "Hanoi"
    assert default_settings.map_default_center_lat == pytest.approx(21.0285)
    assert default_settings.map_default_center_lng == pytest.approx(105.8542)

    # 2. Ho Chi Minh City configuration
    hcmc_settings = Settings(
        city_name="Ho Chi Minh City",
        map_default_center_lat=10.8231,
        map_default_center_lng=106.6297,
        map_default_zoom=12,
        map_bbox_min_lat=10.6000,
        map_bbox_min_lng=106.4000,
        map_bbox_max_lat=11.1000,
        map_bbox_max_lng=107.0000,
    )
    assert hcmc_settings.city_name == "Ho Chi Minh City"
    assert hcmc_settings.map_default_center_lat == pytest.approx(10.8231)
    assert hcmc_settings.map_default_center_lng == pytest.approx(106.6297)

    # 3. Da Nang configuration
    danang_settings = Settings(
        city_name="Da Nang",
        map_default_center_lat=16.0544,
        map_default_center_lng=108.2022,
    )
    assert danang_settings.city_name == "Da Nang"
    assert danang_settings.map_default_center_lat == pytest.approx(16.0544)


@pytest.mark.asyncio
async def test_config_endpoint_returns_city_and_map_center():
    """Verify GET /api/v1/config returns active city and map center."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "city_name" in data
        assert "map_center" in data
        assert "map_bounding_box" in data
        assert data["map_center"]["latitude"] == pytest.approx(21.0285)
        assert data["map_center"]["longitude"] == pytest.approx(105.8542)


def test_multibrand_ev_support_registration_and_resolution():
    """Verify non-VinFast EV brands (e.g. BYD, Tesla, Dat Bike) can be registered and resolved."""
    resolver = VehicleCapabilityResolver()

    # 1. Register BYD Atto 3
    byd_atto3 = VehicleCapability(
        vehicle_model="BYD_ATTO_3",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=60.48,
        usable_capacity_kwh=58.00,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
        estimated_consumption_wh_per_km=156.0,
    )
    resolver.register_model("BYD_ATTO_3", byd_atto3)

    # 2. Register Tesla Model 3
    tesla_m3 = VehicleCapability(
        vehicle_model="TESLA_MODEL_3",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=78.1,
        usable_capacity_kwh=75.0,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
        estimated_consumption_wh_per_km=144.0,
    )
    resolver.register_model("TESLA_MODEL_3", tesla_m3)

    # 3. Register Dat Bike Weaver++ (Vietnamese electric motorbike with swappable/charging)
    dat_bike = VehicleCapability(
        vehicle_model="DAT_BIKE_WEAVER_PLUS",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="REMOVABLE_STANDARD_MODULE",
        battery_capacity_kwh=5.0,
        usable_capacity_kwh=4.8,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
        charging_interface_class="STANDARD_MOTORBIKE_PLUG",
        estimated_consumption_wh_per_km=35.0,
    )
    resolver.register_model("DAT_BIKE_WEAVER_PLUS", dat_bike)

    # Verify resolution by model name
    res_byd = resolver.resolve_by_model("BYD_ATTO_3")
    assert res_byd.vehicle_model == "BYD_ATTO_3"
    assert res_byd.usable_capacity_kwh == 58.00

    res_tesla = resolver.resolve_by_model("TESLA_MODEL_3")
    assert res_tesla.vehicle_model == "TESLA_MODEL_3"
    assert res_tesla.estimated_consumption_wh_per_km == 144.0

    res_dat = resolver.resolve_by_model("DAT_BIKE_WEAVER_PLUS")
    assert res_dat.vehicle_model == "DAT_BIKE_WEAVER_PLUS"
    assert res_dat.swap_supported is True


def test_demand_service_with_non_vinfast_vehicles():
    """Verify DemandService correctly resolves and generates EnergyServiceRequest for non-VinFast vehicles."""
    resolver = VehicleCapabilityResolver()

    # Register Hyundai Ioniq 5
    hyundai_ioniq = VehicleCapability(
        vehicle_model="HYUNDAI_IONIQ_5",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=72.6,
        usable_capacity_kwh=70.0,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
        estimated_consumption_wh_per_km=165.0,
    )
    resolver.register_model("HYUNDAI_IONIQ_5", hyundai_ioniq)
    resolver.register_vehicle("V_HYUNDAI_01", {"vehicle_id": "V_HYUNDAI_01", "vehicle_model": "HYUNDAI_IONIQ_5"})

    service = DemandService(capability_resolver=resolver)

    context = DemandContext(
        vehicle_id="V_HYUNDAI_01",
        driver_id="DRIVER_TEST",
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        remaining_trip_distance_km=80.0,
        raw_latitude=10.8231,
        raw_longitude=106.6297,
    )

    req = service.evaluate_auto_demand(context)
    assert req.need_service is True
    assert req.vehicle_model == "HYUNDAI_IONIQ_5"
    assert req.battery_capacity_kwh == 72.6
