"""
Tests for deterministic candidate eligibility precedence.
"""

import pytest

from backend.app.services.candidate.eligibility import evaluate_candidate_eligibility
from backend.app.services.candidate.models import (
    CandidateEligibilityReason,
    StationOperationalSnapshot,
)
from backend.app.services.demand.models import ServiceType


def make_snapshot(status="OPEN", slots=4, batt=4, cap=4, wait=10.0):
    return StationOperationalSnapshot(
        operating_status=status,
        available_service_slots=slots,
        available_swap_batteries=batt,
        available_capacity=cap,
        queue_length=1,
        estimated_wait_min=wait,
        service_time_min=18.0,
    )


def test_unreachable_takes_highest_precedence():
    # If unreachable, reason must be UNREACHABLE even if also incompatible or offline
    snap = make_snapshot(status="OFFLINE", cap=0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=False,
        is_compatible=False,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=False,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.UNREACHABLE


def test_incompatible_takes_precedence_over_offline():
    snap = make_snapshot(status="OFFLINE")
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=False,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=True,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.INCOMPATIBLE


def test_offline_takes_precedence_over_full():
    snap = make_snapshot(status="OFFLINE", cap=0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=True,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.OFFLINE


def test_no_swap_battery_precedence():
    # Swap station has slots but 0 batteries
    snap = make_snapshot(status="OPEN", slots=4, batt=0, cap=0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.BATTERY_SWAP,
        is_soc_feasible=True,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.NO_SWAP_BATTERY


def test_full_capacity_precedence():
    snap = make_snapshot(status="OPEN", slots=0, cap=0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=True,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.FULL


def test_excessive_queue_precedence():
    # Wait > 90 min
    snap = make_snapshot(status="OPEN", slots=2, cap=2, wait=95.0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=True,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.EXCESSIVE_QUEUE


def test_insufficient_soc_precedence():
    snap = make_snapshot(status="OPEN", slots=2, cap=2, wait=10.0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=False,
    )
    assert eligible is False
    assert reason == CandidateEligibilityReason.INSUFFICIENT_SOC_TO_REACH


def test_fully_eligible():
    snap = make_snapshot(status="OPEN", slots=2, cap=2, wait=10.0)
    eligible, reason = evaluate_candidate_eligibility(
        is_reachable=True,
        is_compatible=True,
        operational=snap,
        service_type=ServiceType.CHARGING,
        is_soc_feasible=True,
    )
    assert eligible is True
    assert reason == CandidateEligibilityReason.ELIGIBLE
