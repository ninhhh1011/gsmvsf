"""
Unit tests for DemandService and EnergyServiceRequest convergence.
"""

from datetime import datetime
import pytest

from backend.app.services.demand.models import (
    DemandContext,
    ReasonCode,
    RequestedServiceType,
    RequestSource,
    ServiceType,
)
from backend.app.services.demand.service import DemandService, get_demand_service


@pytest.fixture
def service():
    return get_demand_service()


def test_auto_demand_car_no_service(service):
    """Car with high SOC -> AUTO_DETECTED, need_service=False, resolved=None."""
    ctx = DemandContext(
        vehicle_id="V0001",  # VF_3 (car)
        driver_id="D0001",
        trip_id="T0001",
        timestamp=datetime.utcnow(),
        current_soc_pct=85.0,
        estimated_remaining_range_km=150.0,
        remaining_trip_distance_km=10.0,
        minimum_safe_soc_pct=15.0,
    )
    req = service.evaluate_auto_demand(ctx, service_request_id="REQ-TEST-001")
    assert req.service_request_id == "REQ-TEST-001"
    assert req.request_source == RequestSource.AUTO_DETECTED
    assert req.need_service is False
    assert req.allowed_service_types == [ServiceType.CHARGING]
    assert req.resolved_service_type is None
    assert req.reason_code == ReasonCode.SUFFICIENT_SOC_RANGE
    assert req.vehicle_model == "VF_3"
    assert req.swap_supported is False
    assert req.charging_supported is True


def test_auto_demand_car_need_charge(service):
    """Car with low SOC -> AUTO_DETECTED, need_service=True, resolved=CHARGING."""
    ctx = DemandContext(
        vehicle_id="V0002",  # VF_5 (car)
        driver_id="D0002",
        trip_id="T0002",
        timestamp=datetime.utcnow(),
        current_soc_pct=15.0,  # <= 20%
        estimated_remaining_range_km=30.0,
        remaining_trip_distance_km=20.0,
        minimum_safe_soc_pct=15.0,
    )
    req = service.evaluate_auto_demand(ctx)
    assert req.request_source == RequestSource.AUTO_DETECTED
    assert req.need_service is True
    assert req.allowed_service_types == [ServiceType.CHARGING]
    assert req.resolved_service_type == ServiceType.CHARGING
    assert req.reason_code in (ReasonCode.LOW_SOC, ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE)
    assert req.vehicle_model == "VF_5"


def test_auto_demand_swap_bike_remains_unresolved(service):
    """Swap-capable bike with need_service=True -> AUTO_DETECTED, resolved=None (no forced swap)."""
    ctx = DemandContext(
        vehicle_id="V0003",  # EVO (swap-capable bike)
        driver_id="D0003",
        trip_id="T0003",
        timestamp=datetime.utcnow(),
        current_soc_pct=10.0,
        estimated_remaining_range_km=8.0,
        remaining_trip_distance_km=15.0,
        minimum_safe_soc_pct=15.0,
    )
    req = service.evaluate_auto_demand(ctx)
    assert req.request_source == RequestSource.AUTO_DETECTED
    assert req.need_service is True
    assert set(req.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}
    assert req.resolved_service_type is None, "Swap-capable bike MUST remain unresolved in AUTO mode"
    assert req.vehicle_model == "EVO"
    assert req.swap_supported is True


def test_driver_request_car_charging(service):
    """Car driver explicitly requesting CHARGING -> valid, resolved=CHARGING."""
    ctx = DemandContext(
        vehicle_id="V0001",
        driver_id="D0001",
        timestamp=datetime.utcnow(),
        current_soc_pct=40.0,
    )
    req = service.process_driver_request(ctx, RequestedServiceType.CHARGING)
    assert req.request_source == RequestSource.DRIVER_REQUEST
    assert req.need_service is True
    assert req.requested_service_type == RequestedServiceType.CHARGING
    assert req.resolved_service_type == ServiceType.CHARGING
    assert req.request_valid is True
    assert req.reason_code == ReasonCode.VALID_REQUEST


def test_driver_request_car_swap_rejected(service):
    """Car driver explicitly requesting BATTERY_SWAP -> invalid, reason=UNSUPPORTED_SERVICE."""
    ctx = DemandContext(
        vehicle_id="V0001",
        driver_id="D0001",
        timestamp=datetime.utcnow(),
        current_soc_pct=40.0,
    )
    req = service.process_driver_request(ctx, RequestedServiceType.BATTERY_SWAP)
    assert req.request_source == RequestSource.DRIVER_REQUEST
    assert req.need_service is True
    assert req.requested_service_type == RequestedServiceType.BATTERY_SWAP
    assert req.resolved_service_type is None
    assert req.request_valid is False
    assert req.reason_code == ReasonCode.UNSUPPORTED_SERVICE


def test_driver_request_swap_bike_any(service):
    """Swap-capable bike requesting ANY -> valid, resolved=None (unconstrained)."""
    ctx = DemandContext(
        vehicle_id="V0003",
        driver_id="D0003",
        timestamp=datetime.utcnow(),
        current_soc_pct=40.0,
    )
    req = service.process_driver_request(ctx, RequestedServiceType.ANY)
    assert req.request_source == RequestSource.DRIVER_REQUEST
    assert req.need_service is True
    assert req.requested_service_type == RequestedServiceType.ANY
    assert req.resolved_service_type is None
    assert req.request_valid is True
    assert req.reason_code == ReasonCode.VALID_REQUEST
    assert set(req.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}


def test_driver_request_swap_bike_swap(service):
    """Swap-capable bike requesting BATTERY_SWAP -> valid, resolved=BATTERY_SWAP."""
    ctx = DemandContext(
        vehicle_id="V0003",
        driver_id="D0003",
        timestamp=datetime.utcnow(),
        current_soc_pct=40.0,
    )
    req = service.process_driver_request(ctx, RequestedServiceType.BATTERY_SWAP)
    assert req.request_source == RequestSource.DRIVER_REQUEST
    assert req.need_service is True
    assert req.requested_service_type == RequestedServiceType.BATTERY_SWAP
    assert req.resolved_service_type == ServiceType.BATTERY_SWAP
    assert req.request_valid is True
    assert req.reason_code == ReasonCode.VALID_REQUEST
