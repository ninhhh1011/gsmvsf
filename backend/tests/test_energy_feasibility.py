"""
Unit and integration tests for Energy Feasibility Model,
Post-Destination Energy Risk, and State Transitions.
"""

import pytest

from backend.app.services.demand.auto_detector import AutoDemandDetector, SafetyReservePolicy
from backend.app.services.demand.capability import get_capability_resolver
from backend.app.services.demand.models import (
    DemandContext,
    ReasonCode,
    ServiceType,
)


@pytest.fixture
def resolver():
    return get_capability_resolver()


@pytest.fixture
def detector():
    return AutoDemandDetector()


def test_state_a_safe(detector, resolver):
    """
    STATE A — SAFE:
    estimated_range >= remaining_trip_distance + safety_reserve
    -> need_service = False, reason = SUFFICIENT_SOC_RANGE, energy_margin >= 0
    """
    cap = resolver.resolve_by_model("VF_5")
    # SOC=50%, range=110km, trip=60km, reserve=max(1.0, 60*0.15)=9.0km.
    # required = 69km. Margin = 110 - 69 = +41km.
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=50.0,
        estimated_remaining_range_km=110.0,
        remaining_trip_distance_km=60.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.need_service is False
    assert decision.reason_code == ReasonCode.SUFFICIENT_SOC_RANGE
    assert decision.energy_margin_km == pytest.approx(41.0, 0.1)
    assert decision.remaining_energy_kwh is not None


def test_state_b_destination_reachable_but_reserve_insufficient(resolver):
    """
    STATE B — DESTINATION REACHABLE, BUT RESERVE INSUFFICIENT:
    remaining_trip_distance <= estimated_range < remaining_trip_distance + safety_reserve
    -> need_service = True, reason = INSUFFICIENT_POST_DESTINATION_RESERVE, energy_margin < 0
    """
    # Use policy with fixed reserve = 20 km to test exact prompt scenario
    policy = SafetyReservePolicy(fixed_safety_reserve_km=20.0)
    det = AutoDemandDetector(policy=policy)
    cap = resolver.resolve_by_model("VF_5")

    # Prompt specification:
    # estimated range = 70 km
    # remaining distance = 55 km (can reach destination!)
    # reserve = 20 km
    # required safe range = 55 + 20 = 75 km
    # 70 < 75 -> need_service = True!
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,  # > 20% safe SOC
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=55.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = det.evaluate_need(ctx, cap)
    assert decision.need_service is True
    assert decision.reason_code == ReasonCode.INSUFFICIENT_POST_DESTINATION_RESERVE
    assert decision.energy_margin_km == pytest.approx(-5.0, 0.1)
    assert decision.remaining_energy_kwh is not None


def test_state_c_destination_not_reachable(resolver):
    """
    STATE C — DESTINATION NOT REACHABLE:
    estimated_range < remaining_trip_distance
    -> need_service = True, reason = DESTINATION_NOT_REACHABLE
    """
    det = AutoDemandDetector()
    cap = resolver.resolve_by_model("VF_5")

    # Range = 40 km, trip distance = 55 km
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=40.0,
        estimated_remaining_range_km=40.0,
        remaining_trip_distance_km=55.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = det.evaluate_need(ctx, cap)
    assert decision.need_service is True
    assert decision.reason_code == ReasonCode.DESTINATION_NOT_REACHABLE
    assert decision.energy_margin_km < -15.0


def test_same_soc_different_trip_mandatory_audit(resolver):
    """
    MANDATORY TEST: Same SOC, Same Vehicle, Different Trip Distance
    Proves Week 2 is NOT merely an SOC-threshold check.

    Vehicle: VF_5
    SOC: 45.0%
    Estimated Range: 70.0 km
    Safety Reserve: 20.0 km
    Required Range Formula: remaining_distance + 20.0 km

    Case A (Short Trip):
    - remaining_trip = 20.0 km
    - required safe range = 20 + 20 = 40 km
    - 70 >= 40 -> SAFE (need_service = False)

    Case B (Long Trip):
    - remaining_trip = 55.0 km
    - required safe range = 55 + 20 = 75 km
    - 70 < 75 -> NEED_SERVICE (need_service = True)
    """
    policy = SafetyReservePolicy(fixed_safety_reserve_km=20.0)
    det = AutoDemandDetector(policy=policy)
    cap = resolver.resolve_by_model("VF_5")

    # Case A: Short Trip
    ctx_a = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=20.0,
        minimum_safe_soc_pct=15.0,
    )
    decision_a = det.evaluate_need(ctx_a, cap)
    assert decision_a.need_service is False
    assert decision_a.reason_code == ReasonCode.SUFFICIENT_SOC_RANGE
    assert decision_a.energy_margin_km == pytest.approx(30.0, 0.1)

    # Case B: Long Trip
    ctx_b = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=55.0,
        minimum_safe_soc_pct=15.0,
    )
    decision_b = det.evaluate_need(ctx_b, cap)
    assert decision_b.need_service is True
    assert decision_b.reason_code == ReasonCode.INSUFFICIENT_POST_DESTINATION_RESERVE
    assert decision_b.energy_margin_km == pytest.approx(-5.0, 0.1)


def test_energy_domain_calculations(detector, resolver):
    """
    Verify energy-domain formula implementation:
    remaining_energy_kwh = usable_capacity_kwh * (SOC / 100)
    estimated_range_km = remaining_energy_kwh / (consumption_wh / 1000)
    energy_margin_km = estimated_range_km - (remaining_trip + reserve)
    """
    cap = resolver.resolve_by_model("VF_5")
    # VF_5 usable capacity = 34.25 kWh
    # At SOC=80%, remaining energy = 34.25 * 0.8 = 27.4 kWh
    # At consumption=150 Wh/km = 0.150 kWh/km, range = 27.4 / 0.150 = 182.667 km
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=80.0,
        consumption_wh_per_km=150.0,
        remaining_trip_distance_km=50.0,
        minimum_safe_soc_pct=15.0,
    )
    decision = detector.evaluate_need(ctx, cap)
    assert decision.remaining_energy_kwh == pytest.approx(27.4, 0.01)
    assert decision.safety_reserve_km == pytest.approx(7.5, 0.1)  # 50 * 0.15
    # required = 50 + 7.5 = 57.5 km. Margin = 182.667 - 57.5 = 125.167 km.
    assert decision.energy_margin_km == pytest.approx(125.167, 0.5)


def test_anomaly_and_invalid_state_handling(detector, resolver):
    """Verify negative distance and invalid consumption are caught as INVALID_STATE."""
    cap = resolver.resolve_by_model("VF_5")

    # Negative trip distance
    ctx_neg_dist = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=50.0,
        remaining_trip_distance_km=-10.0,
    )
    res_neg_dist = detector.evaluate_need(ctx_neg_dist, cap)
    assert res_neg_dist.need_service is False
    assert res_neg_dist.reason_code == ReasonCode.INVALID_STATE

    # Invalid non-positive consumption
    ctx_invalid_cons = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=50.0,
        consumption_wh_per_km=0.0,
    )
    res_invalid_cons = detector.evaluate_need(ctx_invalid_cons, cap)
    assert res_invalid_cons.need_service is False
    assert res_invalid_cons.reason_code == ReasonCode.INVALID_STATE
