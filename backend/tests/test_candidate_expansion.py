"""
Tests for candidate expansion engine.
"""

from datetime import datetime
import pytest

from backend.app.services.candidate.expansion import (
    determine_evaluable_services,
    expand_candidate_pairs,
)
from backend.app.services.candidate.station_catalog import StationRecord
from backend.app.services.demand.models import (
    EnergyServiceRequest,
    ReasonCode,
    RequestSource,
    RequestedServiceType,
    ServiceType,
)


@pytest.fixture
def sample_stations():
    return [
        StationRecord(
            station_id=f"S{i:03d}",
            access_node_id=f"N{i}",
            latitude=21.0 + i * 0.01,
            longitude=105.8 + i * 0.01,
            access_latitude=21.0 + i * 0.01,
            access_longitude=105.8 + i * 0.01,
            station_type="CHARGING",
            connector_type="CCS2_TYPE2",
            battery_type="",
            supported_vehicle_type="EV_CAR",
            total_slots=6,
            charging_slots=6,
            swap_slots=0,
        )
        for i in range(1, 31)
    ]


def test_car_expansion(sample_stations):
    # Car: only charging allowed
    req = EnergyServiceRequest(
        service_request_id="REQ-CAR",
        vehicle_id="V001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        swap_supported=False,
    )
    services = determine_evaluable_services(req)
    assert services == [ServiceType.CHARGING]

    pairs = expand_candidate_pairs(req, sample_stations)
    assert len(pairs) == 30  # 30 stations x 1 service
    assert all(s == ServiceType.CHARGING for _, s in pairs)


def test_swap_bike_unresolved_expansion(sample_stations):
    # Swap-capable bike: need_service=True, unresolved (resolved_service_type=None)
    req = EnergyServiceRequest(
        service_request_id="REQ-SWAP-UNRESOLVED",
        vehicle_id="V002",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.LOW_SOC,
        swap_supported=True,
    )
    services = determine_evaluable_services(req)
    assert ServiceType.CHARGING in services
    assert ServiceType.BATTERY_SWAP in services
    assert len(services) == 2

    pairs = expand_candidate_pairs(req, sample_stations)
    assert len(pairs) == 60  # 30 stations x 2 services
    charging_pairs = [p for p in pairs if p[1] == ServiceType.CHARGING]
    swap_pairs = [p for p in pairs if p[1] == ServiceType.BATTERY_SWAP]
    assert len(charging_pairs) == 30
    assert len(swap_pairs) == 30


def test_driver_request_any_expansion(sample_stations):
    # Driver request with ANY for swap-capable bike
    req = EnergyServiceRequest(
        service_request_id="REQ-DRIVER-ANY",
        vehicle_id="V002",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.DRIVER_REQUEST,
        requested_service_type=RequestedServiceType.ANY,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.VALID_REQUEST,
        swap_supported=True,
    )
    services = determine_evaluable_services(req)
    assert len(services) == 2

    pairs = expand_candidate_pairs(req, sample_stations)
    assert len(pairs) == 60
