"""
Unit tests for AUTO_DETECTED Demand Baseline Engine.
"""

import pytest

from backend.app.services.demand.auto_detector import AutoDemandDetector
from backend.app.services.demand.capability import get_capability_resolver
from backend.app.services.demand.models import (
    DemandContext,
    ReasonCode,
    ServiceType,
)


@pytest.fixture
def detector():
    return AutoDemandDetector()


@pytest.fixture
def resolver():
    return get_capability_resolver()


def test_high_soc_short_trip(detector, resolver):
    """High SOC and short trip -> No service needed, SUFFICIENT_SOC_RANGE."""
    cap = resolver.resolve_by_model("VF_5")
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=85.0,
        estimated_remaining_range_km=250.0,
        remaining_trip_distance_km=10.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.need_service is False
    assert decision.reason_code == ReasonCode.SUFFICIENT_SOC_RANGE

    resolved = detector.resolve_service_type(decision.need_service, cap)
    assert resolved is None


def test_low_soc_short_trip(detector, resolver):
    """Low SOC (<=20%) even on a short trip -> Service needed, LOW_SOC."""
    cap = resolver.resolve_by_model("VF_5")
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=18.0,  # <= 15 + 5 = 20%
        estimated_remaining_range_km=45.0,
        remaining_trip_distance_km=5.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.need_service is True
    assert decision.reason_code == ReasonCode.LOW_SOC

    resolved = detector.resolve_service_type(decision.need_service, cap)
    assert resolved == ServiceType.CHARGING


def test_medium_soc_long_trip_insufficient_range(detector, resolver):
    """Medium SOC (>20%) but remaining trip exceeds range -> Service needed, INSUFFICIENT_RANGE."""
    cap = resolver.resolve_by_model("VF_5")
    # Remaining trip = 70 km, reserve = max(1.0, 70 * 0.15) = 10.5 km.
    # Total required = 80.5 km. Estimated range = 50.0 km.
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=30.0,  # > 20%
        estimated_remaining_range_km=50.0,
        remaining_trip_distance_km=70.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.need_service is True
    assert decision.reason_code == ReasonCode.INSUFFICIENT_RANGE

    resolved = detector.resolve_service_type(decision.need_service, cap)
    assert resolved == ServiceType.CHARGING


def test_low_soc_and_insufficient_range(detector, resolver):
    """Both below safe SOC and insufficient range -> LOW_SOC_AND_INSUFFICIENT_RANGE."""
    cap = resolver.resolve_by_model("VF_5")
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=12.0,  # <= 20%
        estimated_remaining_range_km=25.0,
        remaining_trip_distance_km=50.0,  # > 25 km
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.need_service is True
    assert decision.reason_code == ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE


def test_exact_safety_threshold_boundary(detector, resolver):
    """Test exact threshold at 20.0% vs 20.01%."""
    cap = resolver.resolve_by_model("VF_5")

    # At exactly 20.0%: below_safe is True
    ctx_at_threshold = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=20.0,
        estimated_remaining_range_km=100.0,
        remaining_trip_distance_km=5.0,
        minimum_safe_soc_pct=15.0,
    )
    decision_at = detector.evaluate_need(ctx_at_threshold, cap)
    assert decision_at.need_service is True
    assert decision_at.reason_code == ReasonCode.LOW_SOC

    # At 20.01%: below_safe is False, and range (100km) > trip (5km) + reserve
    ctx_above_threshold = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=20.01,
        estimated_remaining_range_km=100.0,
        remaining_trip_distance_km=5.0,
        minimum_safe_soc_pct=15.0,
    )
    decision_above = detector.evaluate_need(ctx_above_threshold, cap)
    assert decision_above.need_service is False
    assert decision_above.reason_code == ReasonCode.SUFFICIENT_SOC_RANGE


def test_missing_and_invalid_soc(detector, resolver):
    """Missing or out-of-bounds SOC must be handled safely."""
    cap = resolver.resolve_by_model("VF_5")

    # Missing SOC
    ctx_missing = DemandContext(vehicle_id="V0002", current_soc_pct=None)
    decision_missing = detector.evaluate_need(ctx_missing, cap)
    assert decision_missing.need_service is False
    assert decision_missing.reason_code == ReasonCode.MISSING_DATA

    # Invalid SOC (-5%)
    ctx_negative = DemandContext(vehicle_id="V0002", current_soc_pct=-5.0)
    decision_negative = detector.evaluate_need(ctx_negative, cap)
    assert decision_negative.need_service is False
    assert decision_negative.reason_code == ReasonCode.INVALID_STATE

    # Invalid SOC (105%)
    ctx_overflow = DemandContext(vehicle_id="V0002", current_soc_pct=105.0)
    decision_overflow = detector.evaluate_need(ctx_overflow, cap)
    assert decision_overflow.need_service is False
    assert decision_overflow.reason_code == ReasonCode.INVALID_STATE


def test_swap_capable_vehicle_remains_unresolved(detector, resolver):
    """
    CRITICAL INVARIANT: For swap-capable vehicles with need_service=True,
    resolved_service_type MUST be None (unresolved). The system must NOT force swap.
    """
    swap_cap = resolver.resolve_by_model("EVO")
    assert swap_cap.swap_supported is True
    assert swap_cap.charging_supported is True

    ctx = DemandContext(
        vehicle_id="V0003",
        current_soc_pct=10.0,
        estimated_remaining_range_km=10.0,
        remaining_trip_distance_km=15.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, swap_cap)
    assert decision.need_service is True

    resolved = detector.resolve_service_type(decision.need_service, swap_cap)
    assert resolved is None, "Swap-capable vehicle in AUTO mode must remain unresolved (NULL)"


def test_charge_only_motorcycle_resolves_to_charging(detector, resolver):
    """Charge-only motorcycle with need_service=True resolves to CHARGING."""
    charge_cap = resolver.resolve_by_model("EVO200")
    assert charge_cap.swap_supported is False
    assert charge_cap.charging_supported is True

    ctx = DemandContext(
        vehicle_id="V0024",
        current_soc_pct=10.0,
        estimated_remaining_range_km=10.0,
        remaining_trip_distance_km=15.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, charge_cap)
    assert decision.need_service is True

    resolved = detector.resolve_service_type(decision.need_service, charge_cap)
    assert resolved == ServiceType.CHARGING
