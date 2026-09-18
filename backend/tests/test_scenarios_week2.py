"""
Dataset V1.3.1 Scenario Replay and Acceptance Test Suite for Week 2.

Replays actual canonical events from dataset_v1/labels/demand_labels.csv:
1. CAR_AUTO_NO_SERVICE (DE000001)
2. CAR_AUTO_NEED_CHARGE (DE000081)
3. CAR_DRIVER_REQUEST_CHARGE (DE000002)
4. CAR_DRIVER_REQUEST_SWAP_INVALID (DE000003)
5. FIXED_BIKE_AUTO_NO_SERVICE (DE000913)
6. FIXED_BIKE_AUTO_NEED_CHARGE (DE000617)
7. FIXED_BIKE_REQUEST_CHARGE (DE000618)
8. FIXED_BIKE_REQUEST_SWAP_INVALID (DE000619)
9. SWAP_BIKE_AUTO_NO_SERVICE (DE000377)
10. SWAP_BIKE_AUTO_NEED_SERVICE_BOTH_ALLOWED (DE000049)
11. SWAP_BIKE_REQUEST_CHARGE (DE000050)
12. SWAP_BIKE_REQUEST_SWAP (DE000051)
13. SWAP_BIKE_REQUEST_ANY (DE000052)
"""

from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest

from backend.app.config import settings
from backend.app.services.demand.models import (
    DemandContext,
    RequestedServiceType,
    RequestSource,
    ServiceType,
)
from backend.app.services.demand.service import get_demand_service

DEMAND_LABELS_PATH = settings.dataset_path / "labels" / "demand_labels.csv"


@pytest.fixture(scope="module")
def demand_labels_df():
    assert DEMAND_LABELS_PATH.exists(), f"Missing canonical file: {DEMAND_LABELS_PATH}"
    df = pd.read_csv(DEMAND_LABELS_PATH)
    return df.set_index("event_id")


@pytest.fixture
def demand_service():
    return get_demand_service()


def run_event_replay(event_id: str, demand_labels_df: pd.DataFrame, demand_service):
    """Replay an event from demand_labels.csv through DemandService and verify match."""
    assert event_id in demand_labels_df.index, f"Event {event_id} not found in demand_labels.csv"
    row = demand_labels_df.loc[event_id]

    ts = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
    ctx = DemandContext(
        vehicle_id=str(row["vehicle_id"]),
        trip_id=str(row["trip_id"]),
        timestamp=ts,
        current_soc_pct=float(row["current_soc_pct"]),
        estimated_remaining_range_km=float(row["estimated_remaining_range_km"]),
        remaining_trip_distance_km=float(row["remaining_trip_distance_km"]),
        safety_reserve_km=float(row["safety_reserve_km"]),
        consumption_wh_per_km=float(row["consumption_wh_per_km"]),
        minimum_safe_soc_pct=float(row["minimum_safe_soc_pct"]),
    )

    req_source = str(row["request_source"])
    if req_source == "AUTO_DETECTED":
        result = demand_service.evaluate_auto_demand(ctx, service_request_id=event_id)
    elif req_source == "DRIVER_REQUEST":
        req_type_str = str(row["requested_service_type"])
        req_type = RequestedServiceType(req_type_str)
        result = demand_service.process_driver_request(ctx, req_type, service_request_id=event_id)
    else:
        raise ValueError(f"Unknown request_source: {req_source}")

    # Ground truth assertions
    expected_need = bool(row["need_service"])
    assert result.need_service == expected_need, (
        f"[{event_id}] need_service mismatch: got {result.need_service}, expected {expected_need}"
    )

    expected_reason = str(row["reason_code"])
    assert result.reason_code.value == expected_reason, (
        f"[{event_id}] reason_code mismatch: got {result.reason_code.value}, expected {expected_reason}"
    )

    if req_source == "DRIVER_REQUEST":
        expected_valid = bool(row["request_valid"])
        assert result.request_valid == expected_valid, (
            f"[{event_id}] request_valid mismatch: got {result.request_valid}, expected {expected_valid}"
        )

    expected_resolved = row["resolved_service_type"]
    if pd.isna(expected_resolved) or expected_resolved == "" or expected_resolved == "None":
        assert result.resolved_service_type is None, (
            f"[{event_id}] resolved_service_type must be None, got {result.resolved_service_type}"
        )
    else:
        assert result.resolved_service_type == ServiceType(expected_resolved), (
            f"[{event_id}] resolved_service_type mismatch: got {result.resolved_service_type}, expected {expected_resolved}"
        )

    return result


def test_scenario_01_car_auto_no_service(demand_labels_df, demand_service):
    """Scenario: CAR_AUTO_NO_SERVICE (DE000001)"""
    res = run_event_replay("DE000001", demand_labels_df, demand_service)
    assert res.need_service is False
    assert res.resolved_service_type is None
    assert res.reason_code.value == "SUFFICIENT_SOC_RANGE"


def test_scenario_02_car_auto_need_charge(demand_labels_df, demand_service):
    """Scenario: CAR_AUTO_NEED_CHARGE (DE000081)"""
    res = run_event_replay("DE000081", demand_labels_df, demand_service)
    assert res.need_service is True
    assert res.resolved_service_type == ServiceType.CHARGING
    assert res.allowed_service_types == [ServiceType.CHARGING]


def test_scenario_03_car_driver_request_charge(demand_labels_df, demand_service):
    """Scenario: CAR_DRIVER_REQUEST_CHARGE (DE000002)"""
    res = run_event_replay("DE000002", demand_labels_df, demand_service)
    assert res.request_valid is True
    assert res.resolved_service_type == ServiceType.CHARGING


def test_scenario_04_car_driver_request_swap_invalid(demand_labels_df, demand_service):
    """Scenario: CAR_DRIVER_REQUEST_SWAP_INVALID (DE000003)"""
    res = run_event_replay("DE000003", demand_labels_df, demand_service)
    assert res.request_valid is False
    assert res.resolved_service_type is None
    assert res.reason_code.value == "UNSUPPORTED_SERVICE"


def test_scenario_05_fixed_bike_auto_no_service(demand_labels_df, demand_service):
    """Scenario: FIXED_BIKE_AUTO_NO_SERVICE (DE000913)"""
    res = run_event_replay("DE000913", demand_labels_df, demand_service)
    assert res.need_service is False
    assert res.resolved_service_type is None
    assert res.allowed_service_types == [ServiceType.CHARGING]


def test_scenario_06_fixed_bike_auto_need_charge(demand_labels_df, demand_service):
    """Scenario: FIXED_BIKE_AUTO_NEED_CHARGE (DE000617)"""
    res = run_event_replay("DE000617", demand_labels_df, demand_service)
    assert res.need_service is True
    assert res.resolved_service_type == ServiceType.CHARGING
    assert res.allowed_service_types == [ServiceType.CHARGING]


def test_scenario_07_fixed_bike_request_charge(demand_labels_df, demand_service):
    """Scenario: FIXED_BIKE_REQUEST_CHARGE (DE000618)"""
    res = run_event_replay("DE000618", demand_labels_df, demand_service)
    assert res.request_valid is True
    assert res.resolved_service_type == ServiceType.CHARGING


def test_scenario_08_fixed_bike_request_swap_invalid(demand_labels_df, demand_service):
    """Scenario: FIXED_BIKE_REQUEST_SWAP_INVALID (DE000619)"""
    res = run_event_replay("DE000619", demand_labels_df, demand_service)
    assert res.request_valid is False
    assert res.resolved_service_type is None
    assert res.reason_code.value == "UNSUPPORTED_SERVICE"


def test_scenario_09_swap_bike_auto_no_service(demand_labels_df, demand_service):
    """Scenario: SWAP_BIKE_AUTO_NO_SERVICE (DE000377)"""
    res = run_event_replay("DE000377", demand_labels_df, demand_service)
    assert res.need_service is False
    assert res.resolved_service_type is None
    assert set(res.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}


def test_scenario_10_swap_bike_auto_need_service_both_allowed(demand_labels_df, demand_service):
    """
    Scenario: SWAP_BIKE_AUTO_NEED_SERVICE_BOTH_ALLOWED (DE000049)
    CRITICAL: For swap-capable bikes with need_service=True, resolved_service_type MUST be None!
    """
    res = run_event_replay("DE000049", demand_labels_df, demand_service)
    assert res.need_service is True
    assert res.resolved_service_type is None, "Must NOT auto-force BATTERY_SWAP"
    assert set(res.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}


def test_scenario_11_swap_bike_request_charge(demand_labels_df, demand_service):
    """Scenario: SWAP_BIKE_REQUEST_CHARGE (DE000050)"""
    res = run_event_replay("DE000050", demand_labels_df, demand_service)
    assert res.request_valid is True
    assert res.resolved_service_type == ServiceType.CHARGING


def test_scenario_12_swap_bike_request_swap(demand_labels_df, demand_service):
    """Scenario: SWAP_BIKE_REQUEST_SWAP (DE000051)"""
    res = run_event_replay("DE000051", demand_labels_df, demand_service)
    assert res.request_valid is True
    assert res.resolved_service_type == ServiceType.BATTERY_SWAP


def test_scenario_13_swap_bike_request_any(demand_labels_df, demand_service):
    """
    Scenario: SWAP_BIKE_REQUEST_ANY (DE000052)
    CRITICAL: For swap bike requesting ANY, resolved_service_type MUST be None (no forced charging)!
    """
    res = run_event_replay("DE000052", demand_labels_df, demand_service)
    assert res.request_valid is True
    assert res.requested_service_type == RequestedServiceType.ANY
    assert res.resolved_service_type is None, "Must NOT auto-force CHARGING on ANY request"
    assert set(res.allowed_service_types) == {ServiceType.CHARGING, ServiceType.BATTERY_SWAP}


def test_scenario_14_post_destination_reserve_ok(demand_service):
    """Scenario: POST_DESTINATION_RESERVE_OK"""
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=50.0,
        estimated_remaining_range_km=110.0,
        remaining_trip_distance_km=60.0,
        minimum_safe_soc_pct=15.0,
    )
    req = demand_service.evaluate_auto_demand(ctx)
    assert req.need_service is False
    assert req.reason_code.value == "SUFFICIENT_SOC_RANGE"
    assert req.energy_margin_km is not None
    assert req.energy_margin_km >= 0


def test_scenario_15_post_destination_reserve_insufficient(demand_service):
    """Scenario: POST_DESTINATION_RESERVE_INSUFFICIENT (70km range < 55km trip + 20km reserve)."""
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=55.0,
        safety_reserve_km=20.0,
        minimum_safe_soc_pct=15.0,
    )
    req = demand_service.evaluate_auto_demand(ctx)
    assert req.need_service is True
    assert req.reason_code.value == "INSUFFICIENT_POST_DESTINATION_RESERVE"
    assert req.energy_margin_km == pytest.approx(-5.0, 0.1)


def test_scenario_16_destination_not_reachable(demand_service):
    """Scenario: DESTINATION_NOT_REACHABLE (45km range < 60km trip)."""
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=35.0,
        estimated_remaining_range_km=45.0,
        remaining_trip_distance_km=60.0,
        minimum_safe_soc_pct=15.0,
    )
    req = demand_service.evaluate_auto_demand(ctx)
    assert req.need_service is True
    assert req.reason_code.value == "DESTINATION_NOT_REACHABLE"
    assert req.energy_margin_km < 0


def test_scenario_17_same_soc_short_trip(demand_service):
    """Scenario: SAME_SOC_SHORT_TRIP (SOC=45%, trip=20km, reserve=20km -> SAFE)."""
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=20.0,
        safety_reserve_km=20.0,
        minimum_safe_soc_pct=15.0,
    )
    req = demand_service.evaluate_auto_demand(ctx)
    assert req.need_service is False
    assert req.reason_code.value == "SUFFICIENT_SOC_RANGE"


def test_scenario_18_same_soc_long_trip(demand_service):
    """Scenario: SAME_SOC_LONG_TRIP (SOC=45%, trip=55km, reserve=20km -> NEED_SERVICE)."""
    ctx = DemandContext(
        vehicle_id="V0002",
        current_soc_pct=45.0,
        estimated_remaining_range_km=70.0,
        remaining_trip_distance_km=55.0,
        safety_reserve_km=20.0,
        minimum_safe_soc_pct=15.0,
    )
    req = demand_service.evaluate_auto_demand(ctx)
    assert req.need_service is True
    assert req.reason_code.value == "INSUFFICIENT_POST_DESTINATION_RESERVE"

