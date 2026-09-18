"""
Unit tests for Week 2 Demand Detection domain models and contracts.
"""

from datetime import datetime
import pytest
from pydantic import ValidationError

from backend.app.services.demand.models import (
    EnergyServiceRequest,
    NeedServiceDecision,
    ReasonCode,
    RequestedServiceType,
    RequestSource,
    ServiceType,
    VehicleCapability,
    VehicleCategory,
    DemandContext,
)


def test_enums_defined():
    """Verify all required enum variants exist."""
    assert ServiceType.CHARGING.value == "CHARGING"
    assert ServiceType.BATTERY_SWAP.value == "BATTERY_SWAP"
    assert "NONE" not in [s.value for s in ServiceType]

    assert RequestedServiceType.ANY.value == "ANY"
    assert RequestedServiceType.CHARGING.value == "CHARGING"
    assert RequestedServiceType.BATTERY_SWAP.value == "BATTERY_SWAP"

    assert RequestSource.AUTO_DETECTED.value == "AUTO_DETECTED"
    assert RequestSource.DRIVER_REQUEST.value == "DRIVER_REQUEST"

    assert ReasonCode.SUFFICIENT_SOC_RANGE.value == "SUFFICIENT_SOC_RANGE"
    assert ReasonCode.LOW_SOC.value == "LOW_SOC"
    assert ReasonCode.INSUFFICIENT_RANGE.value == "INSUFFICIENT_RANGE"
    assert ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE.value == "LOW_SOC_AND_INSUFFICIENT_RANGE"
    assert ReasonCode.VALID_REQUEST.value == "VALID_REQUEST"
    assert ReasonCode.UNSUPPORTED_SERVICE.value == "UNSUPPORTED_SERVICE"


def test_vehicle_capability_allowed_services():
    """Test allowed_service_types computation."""
    car = VehicleCapability(
        vehicle_model="VF_5",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_capacity_kwh=37.23,
        charging_supported=True,
        swap_supported=False,
    )
    assert car.allowed_service_types == [ServiceType.CHARGING]
    assert car.is_service_supported(ServiceType.CHARGING) is True
    assert car.is_service_supported(ServiceType.BATTERY_SWAP) is False

    swap_bike = VehicleCapability(
        vehicle_model="EVO",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_capacity_kwh=3.0,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
    )
    assert set(swap_bike.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}
    assert swap_bike.is_service_supported(ServiceType.CHARGING) is True
    assert swap_bike.is_service_supported(ServiceType.BATTERY_SWAP) is True


def test_energy_service_request_auto_no_need():
    """When need_service=False, resolved_service_type must be None."""
    req = EnergyServiceRequest(
        service_request_id="REQ-001",
        driver_id="D0001",
        vehicle_id="V0001",
        trip_id="T0001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=False,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=None,
        request_valid=True,
        reason_code=ReasonCode.SUFFICIENT_SOC_RANGE,
        current_soc_pct=85.0,
    )
    assert req.need_service is False
    assert req.resolved_service_type is None

    # Forcing resolved_service_type when need_service=False should raise ValidationError
    with pytest.raises(ValidationError):
        EnergyServiceRequest(
            service_request_id="REQ-002",
            vehicle_id="V0001",
            timestamp=datetime.utcnow(),
            request_source=RequestSource.AUTO_DETECTED,
            need_service=False,
            allowed_service_types=[ServiceType.CHARGING],
            resolved_service_type=ServiceType.CHARGING,
            reason_code=ReasonCode.SUFFICIENT_SOC_RANGE,
        )


def test_energy_service_request_auto_swap_capable_remains_unresolved():
    """AUTO_DETECTED with both allowed services must NOT resolve to a service."""
    req = EnergyServiceRequest(
        service_request_id="REQ-003",
        vehicle_id="V0003",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.LOW_SOC,
        swap_supported=True,
    )
    assert req.resolved_service_type is None

    # Forcing BATTERY_SWAP or CHARGING on AUTO for swap bike must fail
    with pytest.raises(ValidationError):
        EnergyServiceRequest(
            service_request_id="REQ-004",
            vehicle_id="V0003",
            timestamp=datetime.utcnow(),
            request_source=RequestSource.AUTO_DETECTED,
            need_service=True,
            allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
            resolved_service_type=ServiceType.BATTERY_SWAP,
            reason_code=ReasonCode.LOW_SOC,
            swap_supported=True,
        )


def test_energy_service_request_driver_any_remains_unresolved():
    """DRIVER_REQUEST with requested_service_type=ANY must NOT resolve to a service."""
    req = EnergyServiceRequest(
        service_request_id="REQ-005",
        vehicle_id="V0003",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.DRIVER_REQUEST,
        need_service=True,
        requested_service_type=RequestedServiceType.ANY,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.VALID_REQUEST,
        swap_supported=True,
    )
    assert req.resolved_service_type is None

    # Silently resolving ANY to CHARGING must fail validation
    with pytest.raises(ValidationError):
        EnergyServiceRequest(
            service_request_id="REQ-006",
            vehicle_id="V0003",
            timestamp=datetime.utcnow(),
            request_source=RequestSource.DRIVER_REQUEST,
            need_service=True,
            requested_service_type=RequestedServiceType.ANY,
            allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
            resolved_service_type=ServiceType.CHARGING,
            reason_code=ReasonCode.VALID_REQUEST,
            swap_supported=True,
        )


def test_energy_service_request_unsupported():
    """Unsupported request must have request_valid=False and resolved_service_type=None."""
    req = EnergyServiceRequest(
        service_request_id="REQ-007",
        vehicle_id="V0001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.DRIVER_REQUEST,
        need_service=True,
        requested_service_type=RequestedServiceType.BATTERY_SWAP,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=None,
        request_valid=False,
        reason_code=ReasonCode.UNSUPPORTED_SERVICE,
    )
    assert req.request_valid is False
    assert req.resolved_service_type is None
    assert req.reason_code == ReasonCode.UNSUPPORTED_SERVICE


def test_no_station_or_ranking_fields_allowed():
    """EnergyServiceRequest must forbid extra downstream fields (Week 3/4 leakage)."""
    with pytest.raises(ValidationError):
        EnergyServiceRequest(
            service_request_id="REQ-008",
            vehicle_id="V0001",
            timestamp=datetime.utcnow(),
            request_source=RequestSource.AUTO_DETECTED,
            need_service=True,
            allowed_service_types=[ServiceType.CHARGING],
            resolved_service_type=ServiceType.CHARGING,
            reason_code=ReasonCode.LOW_SOC,
            candidate_station_ids=["S001", "S002"],  # type: ignore
        )
