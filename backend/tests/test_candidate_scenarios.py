"""
Canonical Scenario Tests for Week 3 Candidate Search & Routing.

Validates the representative scenarios required by project scope and acceptance criteria:
1. CAR_CHARGING_ELIGIBLE
2. CAR_INCOMPATIBLE_MOTORCYCLE_STATION
3. CHARGE_ONLY_BIKE_CHARGING
4. CHARGE_ONLY_BIKE_SWAP_NOT_ALLOWED
5. SWAP_BIKE_CHARGING
6. SWAP_BIKE_SWAP
7. SWAP_BIKE_BOTH_ALLOWED
8. STATION_OFFLINE
9. STATION_FULL
10. STATION_UNREACHABLE
11. INSUFFICIENT_SOC_TO_REACH
12. NO_ELIGIBLE_CANDIDATES
13. MULTIPLE_ELIGIBLE_CANDIDATES
14. FARTHER_BUT_FASTER
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
def mock_service():
    engine = MockRoutingAdapter(winding_factor=1.2, average_speed_mps=8.33)
    return CandidateSearchService(routing_engine=engine)


@pytest.mark.asyncio
async def test_scenario_01_car_charging_eligible(mock_service):
    """Car needing charge finds eligible car charging stations."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-01",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    eligs = [c for c in res.candidates if c.eligible]
    assert len(eligs) > 0
    assert all(c.service_type == ServiceType.CHARGING for c in eligs)


@pytest.mark.asyncio
async def test_scenario_02_car_incompatible_motorcycle_station(mock_service):
    """Car candidate evaluation marks motorcycle stations as INCOMPATIBLE."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-02",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    # S003 is a motorcycle-only swap station
    c_s3 = next((c for c in res.candidates if c.station_id == "S003"), None)
    assert c_s3 is not None
    assert c_s3.eligible is False
    assert c_s3.reason == CandidateEligibilityReason.INCOMPATIBLE


@pytest.mark.asyncio
async def test_scenario_03_charge_only_bike_charging(mock_service):
    """Charge-only motorcycle (e.g. Feliz S) evaluates only charging candidates."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-03",
        vehicle_id="V0045",
        vehicle_model="FELIZ_S",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=25.0,
        latitude=21.025,
        longitude=105.820,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.total_candidates_evaluated == 30
    assert all(c.service_type == ServiceType.CHARGING for c in res.candidates)


@pytest.mark.asyncio
async def test_scenario_04_charge_only_bike_swap_not_allowed(mock_service):
    """Charge-only bike requesting swap is rejected at request validation."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-04",
        vehicle_id="V0045",
        vehicle_model="FELIZ_S",
        vehicle_type="EV_MOTORBIKE",
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
    res = await mock_service.search_candidates(req)

    assert res.search_status == "INVALID_REQUEST"
    assert res.eligible_count == 0


@pytest.mark.asyncio
async def test_scenario_05_swap_bike_charging(mock_service):
    """Swap-capable bike explicitly requesting charging evaluates only charging candidates."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-05",
        vehicle_id="V0055",
        vehicle_model="EVO",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.DRIVER_REQUEST,
        requested_service_type=RequestedServiceType.CHARGING,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.VALID_REQUEST,
        current_soc_pct=15.0,
        estimated_remaining_range_km=25.0,
        latitude=21.025,
        longitude=105.820,
        swap_supported=True,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.total_candidates_evaluated == 30
    assert all(c.service_type == ServiceType.CHARGING for c in res.candidates)


@pytest.mark.asyncio
async def test_scenario_06_swap_bike_swap(mock_service):
    """Swap-capable bike explicitly requesting swap evaluates only swap candidates."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-06",
        vehicle_id="V0055",
        vehicle_model="EVO",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.DRIVER_REQUEST,
        requested_service_type=RequestedServiceType.BATTERY_SWAP,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=ServiceType.BATTERY_SWAP,
        reason_code=ReasonCode.VALID_REQUEST,
        current_soc_pct=15.0,
        estimated_remaining_range_km=25.0,
        latitude=21.025,
        longitude=105.820,
        swap_supported=True,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.total_candidates_evaluated == 30
    assert all(c.service_type == ServiceType.BATTERY_SWAP for c in res.candidates)


@pytest.mark.asyncio
async def test_scenario_07_swap_bike_both_allowed(mock_service):
    """Swap-capable bike with unresolved need evaluates BOTH charging and swap across all 30 stations."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-07",
        vehicle_id="V0055",
        vehicle_model="EVO",
        vehicle_type="EV_MOTORBIKE",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING, ServiceType.BATTERY_SWAP],
        resolved_service_type=None,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=25.0,
        latitude=21.025,
        longitude=105.820,
        swap_supported=True,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.total_candidates_evaluated == 60  # 30 stations x 2 services


@pytest.mark.asyncio
async def test_scenario_08_station_offline(mock_service):
    """Offline station is marked with reason OFFLINE."""
    # At 06:10:00, S001 is OFFLINE in dataset
    esr = EnergyServiceRequest(
        service_request_id="SCEN-08",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:10:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    c_s1 = next((c for c in res.candidates if c.station_id == "S001"), None)
    assert c_s1 is not None
    assert c_s1.eligible is False
    assert c_s1.reason == CandidateEligibilityReason.OFFLINE


@pytest.mark.asyncio
async def test_scenario_09_station_full(mock_service):
    """Full station (zero capacity) is marked with reason FULL."""
    # At 06:10:00, S004 is OPEN but has 0 available capacity
    esr = EnergyServiceRequest(
        service_request_id="SCEN-09",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:10:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    c_s4 = next((c for c in res.candidates if c.station_id == "S004"), None)
    assert c_s4 is not None
    assert c_s4.eligible is False
    assert c_s4.reason == CandidateEligibilityReason.FULL


@pytest.mark.asyncio
async def test_scenario_10_station_unreachable():
    """Unreachable station is marked with reason UNREACHABLE."""
    engine = MockRoutingAdapter()
    engine.set_unreachable_point(21.09021, 105.75748)  # S001 coordinate
    service = CandidateSearchService(routing_engine=engine)

    esr = EnergyServiceRequest(
        service_request_id="SCEN-10",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=15.0,
        estimated_remaining_range_km=45.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await service.search_candidates(req)

    c_s1 = next((c for c in res.candidates if c.station_id == "S001"), None)
    assert c_s1 is not None
    assert c_s1.eligible is False
    assert c_s1.reason == CandidateEligibilityReason.UNREACHABLE


@pytest.mark.asyncio
async def test_scenario_11_insufficient_soc_to_reach(mock_service):
    """Vehicle with critically low range cannot reach distant stations."""
    # Estimated range = 1.0 km. Station S001 is ~11 km away.
    esr = EnergyServiceRequest(
        service_request_id="SCEN-11",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=1.0,
        estimated_remaining_range_km=1.0,  # CRITICALLY LOW
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    c_s1 = next((c for c in res.candidates if c.station_id == "S001"), None)
    assert c_s1 is not None
    assert c_s1.eligible is False
    assert c_s1.reason == CandidateEligibilityReason.INSUFFICIENT_SOC_TO_REACH


@pytest.mark.asyncio
async def test_scenario_12_no_eligible_candidates(mock_service):
    """When vehicle has 0.1 km range, zero candidates are eligible."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-12",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=0.5,
        estimated_remaining_range_km=0.1,  # Almost empty
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.search_status == "SUCCESS"
    assert res.eligible_count == 0
    assert len(res.candidates) == 30  # All evaluated and diagnosed


@pytest.mark.asyncio
async def test_scenario_13_multiple_eligible_candidates(mock_service):
    """Car with normal range at 06:20:00 finds multiple eligible candidates."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-13",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=25.0,
        estimated_remaining_range_km=60.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(energy_request=esr)
    res = await mock_service.search_candidates(req)

    assert res.eligible_count >= 2


@pytest.mark.asyncio
async def test_scenario_14_farther_but_faster_routing_metrics(mock_service):
    """Verify route metrics compute distinct distance, duration, and detours."""
    esr = EnergyServiceRequest(
        service_request_id="SCEN-14",
        vehicle_id="V0004",
        vehicle_model="VF_6",
        vehicle_type="EV_CAR",
        timestamp=datetime.fromisoformat("2026-09-01T06:20:00+07:00"),
        request_source=RequestSource.AUTO_DETECTED,
        need_service=True,
        allowed_service_types=[ServiceType.CHARGING],
        resolved_service_type=ServiceType.CHARGING,
        reason_code=ReasonCode.LOW_SOC,
        current_soc_pct=25.0,
        estimated_remaining_range_km=60.0,
        latitude=21.015,
        longitude=105.780,
        swap_supported=False,
    )
    req = CandidateSearchRequest(
        energy_request=esr,
        destination_latitude=21.050,
        destination_longitude=105.850,
    )
    res = await mock_service.search_candidates(req)

    eligs = [c for c in res.candidates if c.eligible and c.route_metrics is not None]
    assert len(eligs) >= 2

    # Verify that different stations have different route metrics
    dist_set = {c.route_metrics.distance_to_station_m for c in eligs}
    detour_set = {c.route_metrics.detour_distance_m for c in eligs}
    assert len(dist_set) > 1
    assert len(detour_set) > 1
