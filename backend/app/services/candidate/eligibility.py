"""
Candidate Eligibility Engine and Reason Precedence for Week 3.

Evaluates eligibility of candidate station/service pairs against physical, operational,
routing, and energy constraints using exact deterministic precedence from Dataset V1.3.1.
"""

from typing import Optional
from backend.app.services.candidate.models import (
    CandidateEligibilityReason,
    StationOperationalSnapshot,
)
from backend.app.services.demand.models import ServiceType

CANDIDATE_MAX_WAIT_MIN: float = 90.0


def evaluate_candidate_eligibility(
    is_reachable: bool,
    is_compatible: bool,
    operational: StationOperationalSnapshot,
    service_type: ServiceType,
    is_soc_feasible: bool,
    max_wait_min: float = CANDIDATE_MAX_WAIT_MIN,
) -> tuple[bool, CandidateEligibilityReason]:
    """
    Evaluate candidate eligibility with deterministic reason precedence.

    Order of evaluation (Dataset V1.3.1 canonical):
    1. UNREACHABLE: No viable road network path
    2. INCOMPATIBLE: Physical connector/vehicle mismatch
    3. OFFLINE: Station not in OPEN operational status
    4. NO_SWAP_BATTERY: Swap station has bays but zero charged swap batteries
    5. FULL: Zero available charging or swap capacity
    6. EXCESSIVE_QUEUE: Queue wait time exceeds 90 minutes
    7. INSUFFICIENT_SOC_TO_REACH: Energy to station exceeds remaining range + 0.5km buffer
    8. ELIGIBLE: All constraints satisfied
    """
    # 1. Routing reachability
    if not is_reachable:
        return (False, CandidateEligibilityReason.UNREACHABLE)

    # 2. Physical & vehicle compatibility
    if not is_compatible:
        return (False, CandidateEligibilityReason.INCOMPATIBLE)

    # 3. Operational status
    if operational.operating_status != "OPEN":
        return (False, CandidateEligibilityReason.OFFLINE)

    # 4. Swap battery inventory check
    if (
        service_type == ServiceType.BATTERY_SWAP
        and operational.available_service_slots > 0
        and operational.available_swap_batteries <= 0
    ):
        return (False, CandidateEligibilityReason.NO_SWAP_BATTERY)

    # 5. Capacity availability
    if operational.available_capacity <= 0:
        return (False, CandidateEligibilityReason.FULL)

    # 6. Queue wait limit
    if operational.estimated_wait_min is not None and operational.estimated_wait_min > max_wait_min:
        return (False, CandidateEligibilityReason.EXCESSIVE_QUEUE)

    # 7. Energy feasibility to reach station
    if not is_soc_feasible:
        return (False, CandidateEligibilityReason.INSUFFICIENT_SOC_TO_REACH)

    # 8. All checks passed
    return (True, CandidateEligibilityReason.ELIGIBLE)
