"""
Integration tests for CandidateSearchService.
"""

from datetime import datetime
import pytest

from backend.app.services.candidate.models import (
    CandidateEligibilityReason,
    CandidateSearchRequest,
)
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.models import (
    EnergyServiceRequest,
    ReasonCode,
    RequestSource,
    RequestedServiceType,
    ServiceType,
)
from backend.tests.mock_routing_adapter import MockRoutingAdapter


@pytest.fixture
def service():
    mock_engine = MockRoutingAdapter(winding_factor=1.2, average_speed_mps=8.33)
    return CandidateSearchService(routing_engine=mock_engine)


@pytest.mark.asyncio
async def test_invalid_request_short_circuit(service):
    # Invalid request
    esr = EnergyServiceRequest(
        service_request_id="REQ-INVALID",
        vehicle_id="V001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.DRIVER_REQUEST,
        requested_service_type=RequestedServiceType.BATTERY_SWAP,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=None,
        request_valid=False,
        reason_code=ReasonCode.UNSUPPORTED_SERVICE,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await service.search_candidates(req)

    assert res.search_status == "INVALID_REQUEST"
    assert res.total_candidates_evaluated == 0
    assert res.eligible_count == 0
    assert len(res.candidates) == 0


@pytest.mark.asyncio
async def test_no_service_needed_short_circuit(service):
    # AUTO_DETECTED with need_service=False
    esr = EnergyServiceRequest(
        service_request_id="REQ-NO-SERVICE",
        vehicle_id="V001",
        timestamp=datetime.utcnow(),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=False,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=None,
        request_valid=True,
        reason_code=ReasonCode.SUFFICIENT_SOC_RANGE,
        current_soc_pct=85.0,
        estimated_remaining_range_km=150.0,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await service.search_candidates(req)

    assert res.search_status == "NO_SERVICE_NEEDED"
    assert res.total_candidates_evaluated == 0
    assert res.eligible_count == 0


@pytest.mark.asyncio
async def test_car_charging_candidate_search(service):
    # Car needing charge
    esr = EnergyServiceRequest(
        service_request_id="REQ-CAR-CHARGE",
        vehicle_id="V001",
        vehicle_model="VF_8",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        request_valid=True,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=35.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(
        energy_request=esr,
        destination_latitude=21.050,
        destination_longitude=105.850,
    )
    res = await service.search_candidates(req)

    assert res.search_status == "SUCCESS"
    assert res.total_candidates_evaluated == 30  # All 30 stations evaluated for CHARGING
    assert res.eligible_count > 0

    # Verify no swap candidates generated for car
    assert all(c.service_type == ServiceType.CHARGING for c in res.candidates)

    # Check that route metrics and detours are computed for reachable stations
    eligible_cands = [c for c in res.candidates if c.eligible]
    for c in eligible_cands:
        assert c.route_metrics is not None
        assert c.route_metrics.distance_to_station_m > 0
        assert c.route_metrics.detour_distance_m is not None


@pytest.mark.asyncio
async def test_swap_bike_unresolved_evaluates_both_services(service):
    # Swap-capable motorcycle with unresolved AUTO need
    esr = EnergyServiceRequest(
        service_request_id="REQ-SWAP-BOTH",
        vehicle_id="V002",
        vehicle_model="EVO",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:10:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        request_valid=True,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=12.0,
        estimated_remaining_range_km=25.0,
        latitude=21.025,
        longitude=105.820,
        swap_supported=True,
    )
    req = CandidateSearchRequest(
        energy_request=esr,
        destination_latitude=21.060,
        destination_longitude=105.860,
    )
    res = await service.search_candidates(req)

    assert res.search_status == "SUCCESS"
    # 30 stations x 2 services = 60 candidate alternatives
    assert res.total_candidates_evaluated == 60

    charging_cands = [c for c in res.candidates if c.service_type == ServiceType.CHARGING]
    swap_cands = [c for c in res.candidates if c.service_type == ServiceType.BATTERY_SWAP]
    assert len(charging_cands) == 30
    assert len(swap_cands) == 30


@pytest.mark.asyncio
async def test_missing_destination_handling(service):
    # Candidate search without destination
    esr = EnergyServiceRequest(
        service_request_id="REQ-NO-DEST",
        vehicle_id="V001",
        vehicle_model="VF_8",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:10:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        request_valid=True,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=18.0,
        estimated_remaining_range_km=40.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(
        energy_request=esr,
        destination_latitude=None,  # No destination
        destination_longitude=None,
    )
    res = await service.search_candidates(req)

    assert res.search_status == "SUCCESS"
    assert res.total_candidates_evaluated == 30
    for c in res.candidates:
        if c.route_metrics:
            assert c.route_metrics.distance_to_station_m > 0
            assert c.route_metrics.detour_distance_m is None
            assert c.route_metrics.distance_station_to_dest_m is None
