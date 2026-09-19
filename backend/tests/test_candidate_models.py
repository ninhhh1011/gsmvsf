"""
Tests for Week 3 Candidate domain models.
"""

from datetime import datetime
import pytest
from pydantic import ValidationError

from backend.app.services.candidate.models import (
    CandidateEligibilityReason,
    StationServiceCandidate,
    CandidateRouteMetrics,
    StationOperationalSnapshot,
    EvaluatedCandidate,
    CandidateSearchRequest,
    CandidateSearchResult,
)
from backend.app.services.demand.models import (
    EnergyServiceRequest,
    RequestSource,
    ReasonCode,
    ServiceType,
)


def sample_energy_request() -> EnergyServiceRequest:
    return EnergyServiceRequest(
        service_request_id="REQ-001",
        vehicle_id="V001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        request_valid=True,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=25.0,
    )


def test_station_service_candidate_creation():
    c = StationServiceCandidate(
        station_id="S001",
        service_type=ServiceType.CHARGING,
        eligible=True,
        reason=CandidateEligibilityReason.ELIGIBLE,
    )
    assert c.station_id == "S001"
    assert c.service_type == ServiceType.CHARGING
    assert c.eligible is True
    assert c.reason == CandidateEligibilityReason.ELIGIBLE


def test_station_service_candidate_immutable():
    c = StationServiceCandidate(
        station_id="S001",
        service_type=ServiceType.CHARGING,
        eligible=True,
        reason=CandidateEligibilityReason.ELIGIBLE,
    )
    with pytest.raises(ValidationError):
        c.eligible = False


def test_no_ranking_fields_in_models():
    # Verify neither Candidate nor EvaluatedCandidate accepts ranking score or rank position
    snapshot = StationOperationalSnapshot(
        operating_status="OPEN",
        available_service_slots=4,
        available_swap_batteries=0,
        available_capacity=4,
        queue_length=1,
        estimated_wait_min=5.0,
        service_time_min=18.0,
    )

    with pytest.raises(ValidationError):
        EvaluatedCandidate(
            station_id="S001",
            service_type=ServiceType.CHARGING,
            eligible=True,
            reason=CandidateEligibilityReason.ELIGIBLE,
            station_latitude=21.0,
            station_longitude=105.8,
            soc_feasible=True,
            operational=snapshot,
            ranking_score=0.95,  # type: ignore # FORBIDDEN
        )


def test_candidate_route_metrics():
    metrics = CandidateRouteMetrics(
        distance_to_station_m=5000.0,
        duration_to_station_s=600.0,
        distance_station_to_dest_m=10000.0,
        duration_station_to_dest_s=1200.0,
        via_total_distance_m=15000.0,
        via_total_duration_s=1800.0,
        direct_distance_m=12000.0,
        direct_duration_s=1500.0,
        detour_distance_m=3000.0,
        detour_duration_s=300.0,
        eta_to_station_s=600.0,
    )
    assert metrics.distance_to_station_m == 5000.0
    assert metrics.detour_distance_m == 3000.0
    assert metrics.detour_duration_s == 300.0


def test_candidate_search_request_and_result():
    req = sample_energy_request()
    search_req = CandidateSearchRequest(
        energy_request=req,
        destination_latitude=21.05,
        destination_longitude=105.85,
    )
    assert search_req.destination_latitude == 21.05

    snapshot = StationOperationalSnapshot(
        operating_status="OPEN",
        available_service_slots=2,
        available_swap_batteries=0,
        available_capacity=2,
        queue_length=0,
        estimated_wait_min=0.0,
        service_time_min=18.0,
    )
    cand = EvaluatedCandidate(
        station_id="S001",
        service_type=ServiceType.CHARGING,
        eligible=True,
        reason=CandidateEligibilityReason.ELIGIBLE,
        station_latitude=21.02,
        station_longitude=105.81,
        soc_feasible=True,
        operational=snapshot,
    )
    result = CandidateSearchResult(
        service_request_id=req.service_request_id,
        total_candidates_evaluated=1,
        eligible_count=1,
        candidates=[cand],
    )
    assert result.eligible_count == 1
    assert result.candidates[0].station_id == "S001"
