"""
Tests for vehicle-station service compatibility engine.
"""

import pytest

from backend.app.services.candidate.compatibility import check_station_service_compatibility
from backend.app.services.candidate.station_catalog import StationRecord
from backend.app.services.demand.capability import CANONICAL_MODEL_CATALOG
from backend.app.services.demand.models import ServiceType


@pytest.fixture
def stations():
    s_car = StationRecord(
        station_id="S_CAR",
        access_node_id="N1",
        latitude=21.0,
        longitude=105.8,
        access_latitude=21.0,
        access_longitude=105.8,
        station_type="CHARGING",
        connector_type="CCS2_TYPE2",
        battery_type="",
        supported_vehicle_type="EV_CAR",
        total_slots=6,
        charging_slots=6,
        swap_slots=0,
    )
    s_bike_swap = StationRecord(
        station_id="S_SWAP",
        access_node_id="N2",
        latitude=21.01,
        longitude=105.81,
        access_latitude=21.01,
        access_longitude=105.81,
        station_type="SWAP",
        connector_type="VINFAST_MOTORCYCLE_CHARGING",
        battery_type="VINFAST_SWAP_LFP_1_5_KWH",
        supported_vehicle_type="EV_MOTORBIKE",
        total_slots=10,
        charging_slots=0,
        swap_slots=10,
    )
    s_dual = StationRecord(
        station_id="S_DUAL",
        access_node_id="N3",
        latitude=21.02,
        longitude=105.82,
        access_latitude=21.02,
        access_longitude=105.82,
        station_type="CHARGING_SWAP",
        connector_type="VINFAST_MOTORCYCLE_CHARGING;CCS2_TYPE2",
        battery_type="VINFAST_SWAP_LFP_1_5_KWH",
        supported_vehicle_type="EV_MOTORBIKE;EV_CAR",
        total_slots=6,
        charging_slots=3,
        swap_slots=3,
    )
    return {"car": s_car, "swap": s_bike_swap, "dual": s_dual}


def test_car_compatibility(stations):
    vf8 = CANONICAL_MODEL_CATALOG["VF_8"]
    # Car at car charging station -> True
    assert check_station_service_compatibility(vf8, stations["car"], ServiceType.CHARGING) is True
    # Car requesting swap at car charging station -> False
    assert check_station_service_compatibility(vf8, stations["car"], ServiceType.BATTERY_SWAP) is False
    # Car at motorcycle swap station -> False
    assert check_station_service_compatibility(vf8, stations["swap"], ServiceType.CHARGING) is False
    assert check_station_service_compatibility(vf8, stations["swap"], ServiceType.BATTERY_SWAP) is False
    # Car at dual station -> Charging True, Swap False
    assert check_station_service_compatibility(vf8, stations["dual"], ServiceType.CHARGING) is True
    assert check_station_service_compatibility(vf8, stations["dual"], ServiceType.BATTERY_SWAP) is False


def test_charge_only_motorcycle_compatibility(stations):
    feliz_s = CANONICAL_MODEL_CATALOG["FELIZ_S"]
    # Charge-only bike at car station -> False
    assert check_station_service_compatibility(feliz_s, stations["car"], ServiceType.CHARGING) is False
    # Charge-only bike at swap station -> False (no charging slots, swap unsupported)
    assert check_station_service_compatibility(feliz_s, stations["swap"], ServiceType.CHARGING) is False
    assert check_station_service_compatibility(feliz_s, stations["swap"], ServiceType.BATTERY_SWAP) is False
    # Charge-only bike at dual station -> Charging True, Swap False
    assert check_station_service_compatibility(feliz_s, stations["dual"], ServiceType.CHARGING) is True
    assert check_station_service_compatibility(feliz_s, stations["dual"], ServiceType.BATTERY_SWAP) is False


def test_swap_capable_motorcycle_compatibility(stations):
    evo = CANONICAL_MODEL_CATALOG["EVO"]
    # Swap bike at car station -> False
    assert check_station_service_compatibility(evo, stations["car"], ServiceType.CHARGING) is False
    # Swap bike at swap station -> Swap True, Charging False (0 charging slots)
    assert check_station_service_compatibility(evo, stations["swap"], ServiceType.BATTERY_SWAP) is True
    assert check_station_service_compatibility(evo, stations["swap"], ServiceType.CHARGING) is False
    # Swap bike at dual station -> Both True
    assert check_station_service_compatibility(evo, stations["dual"], ServiceType.CHARGING) is True
    assert check_station_service_compatibility(evo, stations["dual"], ServiceType.BATTERY_SWAP) is True
