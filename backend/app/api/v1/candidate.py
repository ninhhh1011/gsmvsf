"""
FastAPI router for Week 3 Candidate Search and Routing.

Provides:
- POST /api/v1/candidate-search: Search eligible station candidates for an EnergyServiceRequest
- POST /api/v1/candidate-search/evaluate: End-to-end evaluation from telemetry to candidate search
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from backend.app.services.candidate.models import (
    CandidateSearchRequest,
    CandidateSearchResult,
)
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.models import DemandContext, EnergyServiceRequest
from backend.app.services.demand.service import get_demand_service
from backend.app.services.realtime.state import get_state_store

router = APIRouter()

_candidate_service_instance: Optional[CandidateSearchService] = None


def get_candidate_service() -> CandidateSearchService:
    """Singleton provider for CandidateSearchService."""
    global _candidate_service_instance
    if _candidate_service_instance is None:
        _candidate_service_instance = CandidateSearchService()
    return _candidate_service_instance


def set_candidate_service(service: CandidateSearchService) -> None:
    """Override singleton for testing."""
    global _candidate_service_instance
    _candidate_service_instance = service


class EvaluateAndSearchApiRequest(BaseModel):
    """
    Unified payload providing telemetry to evaluate demand and search candidates.
    """
    vehicle_id: str
    driver_id: Optional[str] = None
    trip_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    current_soc_pct: Optional[float] = Field(None, description="Battery SOC percentage (0-100)")
    estimated_remaining_range_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    distance_travelled_km: Optional[float] = None
    planned_trip_distance_km: Optional[float] = None
    safety_reserve_km: Optional[float] = None
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    road_segment_id: Optional[str] = None

    # Trip destination coordinates for route/detour calculations
    destination_latitude: Optional[float] = None
    destination_longitude: Optional[float] = None
    destination_node_id: Optional[str] = None

    max_candidates: Optional[int] = None
    eligible_only: bool = False


@router.post(
    "/candidate-search",
    response_model=CandidateSearchResult,
    status_code=status.HTTP_200_OK,
    summary="Search candidate stations and calculate routing metrics for an EnergyServiceRequest",
)
async def search_candidates(
    request: CandidateSearchRequest,
    eligible_only: bool = Query(False, description="If true, return only eligible candidates"),
    service: CandidateSearchService = Depends(get_candidate_service),
) -> CandidateSearchResult:
    """
    Execute Week 3 candidate search and multi-leg routing for an EnergyServiceRequest.
    """
    return await service.search_candidates(request, eligible_only=eligible_only)


@router.post(
    "/candidate-search/evaluate",
    response_model=CandidateSearchResult,
    status_code=status.HTTP_200_OK,
    summary="End-to-end evaluation: telemetry -> demand detection -> candidate search",
)
async def evaluate_and_search(
    request: EvaluateAndSearchApiRequest,
    service: CandidateSearchService = Depends(get_candidate_service),
) -> CandidateSearchResult:
    """
    Seamless integration endpoint:
    1. Look up Week 1 realtime driver state if driver_id is present and coordinates are missing.
    2. Evaluate Week 2 demand detection to produce canonical EnergyServiceRequest.
    3. Execute Week 3 candidate search and multi-leg routing.
    """
    lat = request.raw_latitude
    lon = request.raw_longitude
    seg_id = request.road_segment_id

    # If coordinates missing, check Week 1 driver state store
    if (lat is None or lon is None) and request.driver_id:
        store = get_state_store()
        driver_state = store.get(request.driver_id)
        if driver_state:
            latest_obs = driver_state.get_latest_observation()
            if latest_obs:
                lat = latest_obs.latitude
                lon = latest_obs.longitude
            latest_match = driver_state.get_latest_match()
            if latest_match and latest_match.resolved_segment_id:
                seg_id = latest_match.resolved_segment_id

    demand_ctx = DemandContext(
        vehicle_id=request.vehicle_id,
        driver_id=request.driver_id,
        trip_id=request.trip_id,
        timestamp=request.timestamp or datetime.utcnow(),
        current_soc_pct=request.current_soc_pct,
        estimated_remaining_range_km=request.estimated_remaining_range_km,
        remaining_trip_distance_km=request.remaining_trip_distance_km,
        distance_travelled_km=request.distance_travelled_km,
        planned_trip_distance_km=request.planned_trip_distance_km,
        safety_reserve_km=request.safety_reserve_km,
        raw_latitude=lat,
        raw_longitude=lon,
        road_segment_id=seg_id,
    )

    demand_svc = get_demand_service()
    energy_req: EnergyServiceRequest = demand_svc.evaluate_auto_demand(demand_ctx)

    search_req = CandidateSearchRequest(
        energy_request=energy_req,
        destination_latitude=request.destination_latitude,
        destination_longitude=request.destination_longitude,
        destination_node_id=request.destination_node_id,
        max_candidates=request.max_candidates,
    )

    return await service.search_candidates(search_req, eligible_only=request.eligible_only)
