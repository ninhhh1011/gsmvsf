"""
Unit tests for DRIVER_REQUEST Intent Resolution Engine.
"""

import pytest

from backend.app.services.demand.capability import get_capability_resolver
from backend.app.services.demand.driver_requester import DriverRequestProcessor
from backend.app.services.demand.models import (
    ReasonCode,
    RequestedServiceType,
    ServiceType,
)


@pytest.fixture
def processor():
    return DriverRequestProcessor()


@pytest.fixture
def resolver():
    return get_capability_resolver()


def test_car_driver_requests(processor, resolver):
    """
    Car rules:
    - Car + CHARGING -> valid, resolved CHARGING
    - Car + BATTERY_SWAP -> invalid UNSUPPORTED_SERVICE
    - Car + ANY -> invalid UNSUPPORTED_SERVICE
    """
    car_cap = resolver.resolve_by_model("VF_5")

    # 1. Car + CHARGING
    res_c = processor.process_request(car_cap, RequestedServiceType.CHARGING)
    assert res_c.request_valid is True
    assert res_c.resolved_service_type == ServiceType.CHARGING
    assert res_c.reason_code == ReasonCode.VALID_REQUEST

    # 2. Car + BATTERY_SWAP (Must NOT silently convert to CHARGING)
    res_s = processor.process_request(car_cap, RequestedServiceType.BATTERY_SWAP)
    assert res_s.request_valid is False
    assert res_s.resolved_service_type is None
    assert res_s.reason_code == ReasonCode.UNSUPPORTED_SERVICE

    # 3. Car + ANY
    res_a = processor.process_request(car_cap, RequestedServiceType.ANY)
    assert res_a.request_valid is False
    assert res_a.resolved_service_type is None
    assert res_a.reason_code == ReasonCode.UNSUPPORTED_SERVICE


def test_charge_only_motorcycle_driver_requests(processor, resolver):
    """
    Charge-only motorcycle rules:
    - EVO200 + CHARGING -> valid, resolved CHARGING
    - EVO200 + BATTERY_SWAP -> invalid UNSUPPORTED_SERVICE
    - EVO200 + ANY -> invalid UNSUPPORTED_SERVICE
    """
    bike_cap = resolver.resolve_by_model("EVO200")

    # 1. Charge-only bike + CHARGING
    res_c = processor.process_request(bike_cap, RequestedServiceType.CHARGING)
    assert res_c.request_valid is True
    assert res_c.resolved_service_type == ServiceType.CHARGING
    assert res_c.reason_code == ReasonCode.VALID_REQUEST

    # 2. Charge-only bike + BATTERY_SWAP
    res_s = processor.process_request(bike_cap, RequestedServiceType.BATTERY_SWAP)
    assert res_s.request_valid is False
    assert res_s.resolved_service_type is None
    assert res_s.reason_code == ReasonCode.UNSUPPORTED_SERVICE

    # 3. Charge-only bike + ANY
    res_a = processor.process_request(bike_cap, RequestedServiceType.ANY)
    assert res_a.request_valid is False
    assert res_a.resolved_service_type is None
    assert res_a.reason_code == ReasonCode.UNSUPPORTED_SERVICE


def test_swap_capable_motorcycle_driver_requests(processor, resolver):
    """
    Swap-capable motorcycle rules:
    - EVO + CHARGING -> valid, resolved CHARGING
    - EVO + BATTERY_SWAP -> valid, resolved BATTERY_SWAP
    - EVO + ANY -> valid, allowed [CHARGING, BATTERY_SWAP], resolved None (unresolved)
    """
    swap_cap = resolver.resolve_by_model("EVO")

    # 1. Swap bike + CHARGING
    res_c = processor.process_request(swap_cap, RequestedServiceType.CHARGING)
    assert res_c.request_valid is True
    assert res_c.resolved_service_type == ServiceType.CHARGING
    assert res_c.reason_code == ReasonCode.VALID_REQUEST

    # 2. Swap bike + BATTERY_SWAP
    res_s = processor.process_request(swap_cap, RequestedServiceType.BATTERY_SWAP)
    assert res_s.request_valid is True
    assert res_s.resolved_service_type == ServiceType.BATTERY_SWAP
    assert res_s.reason_code == ReasonCode.VALID_REQUEST

    # 3. Swap bike + ANY (Must NOT silently convert to CHARGING)
    res_a = processor.process_request(swap_cap, RequestedServiceType.ANY)
    assert res_a.request_valid is True
    assert set(res_a.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}
    assert res_a.resolved_service_type is None
    assert res_a.reason_code == ReasonCode.VALID_REQUEST


def test_additional_models_driver_requests(processor, resolver):
    """Verify matrix on other models: VF_9, FELIZ_S, VIPER."""
    # VF_9 (Car)
    vf9 = resolver.resolve_by_model("VF_9")
    assert processor.process_request(vf9, RequestedServiceType.BATTERY_SWAP).request_valid is False

    # FELIZ_S (Charge-only bike)
    feliz_s = resolver.resolve_by_model("FELIZ_S")
    assert processor.process_request(feliz_s, RequestedServiceType.BATTERY_SWAP).request_valid is False

    # VIPER (Swap-capable bike)
    viper = resolver.resolve_by_model("VIPER")
    viper_swap = processor.process_request(viper, RequestedServiceType.BATTERY_SWAP)
    assert viper_swap.request_valid is True
    assert viper_swap.resolved_service_type == ServiceType.BATTERY_SWAP

    viper_any = processor.process_request(viper, RequestedServiceType.ANY)
    assert viper_any.request_valid is True
    assert viper_any.resolved_service_type is None
