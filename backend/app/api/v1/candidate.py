"""
FastAPI router for Week 3 Candidate Search and Routing.

Provides:
- POST /api/v1/route: Compute a road-network route for a vehicle category
- POST /api/v1/candidate-search: Search eligible station candidates for an EnergyServiceRequest
- POST /api/v1/candidate-search/evaluate: End-to-end evaluation from telemetry to candidate search
"""

from datetime import UTC, datetime

from backend.app.dependencies import get_candidate_service, get_demand_service
from backend.app.services.candidate.models import (
    CandidateSearchRequest,
    CandidateSearchResult,
)
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.models import (
    DemandContext,
    EnergyServiceRequest,
    RequestedServiceType,
)
from backend.app.services.realtime.location import resolve_current_location
from backend.app.services.routing.engine import (
    RouteNotFoundError,
    RoutingEngineError,
    RoutingInvalidRequestError,
    RoutingTimeoutError,
    raise_for_routing_failure,
)
from backend.app.services.routing.models import RouteRequest, RouteResult, RouteStatus
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

router = APIRouter()


def set_candidate_service(service: CandidateSearchService | None) -> None:
    """Set the application service for tests; runtime getters read app.state."""
    from backend.app.main import app
    from backend.app.services.demand.capability import VehicleCapabilityResolver
    from backend.app.services.demand.service import DemandService
    from backend.app.services.realtime.state import DriverStateStore
    resolver = VehicleCapabilityResolver()
    app.state.candidate_service = service
    app.state.capability_resolver = resolver
    app.state.demand_service = DemandService(resolver)
    if not hasattr(app.state, 'driver_state_store'):
        app.state.driver_state_store = DriverStateStore()


def _routing_http_error(exc: RoutingEngineError) -> HTTPException:
    code = 503
    if isinstance(exc, RoutingTimeoutError):
        code = 504
    elif isinstance(exc, RoutingInvalidRequestError):
        code = 422
    elif isinstance(exc, RouteNotFoundError):
        code = 404
    return HTTPException(status_code=code, detail=str(exc))


@router.post("/route", response_model=RouteResult, summary="Compute a road route for a vehicle")
async def route(
    request: RouteRequest,
    request_obj: Request,
) -> RouteResult:
    service = get_candidate_service(request_obj)
    try:
        result = await service.routing_engine.route(request)
        raise_for_routing_failure(result)
        if result.status in {RouteStatus.NO_ROUTE, RouteStatus.UNREACHABLE}:
            raise RouteNotFoundError(result.error_message or "No road route found")
        return result
    except RoutingEngineError as exc:
        raise _routing_http_error(exc) from exc


class EvaluateAndSearchApiRequest(BaseModel):
    """
    Unified payload providing telemetry to evaluate demand and search candidates.
    """
    vehicle_id: str
    driver_id: str | None = None
    trip_id: str | None = None
    timestamp: datetime | None = None
    current_soc_pct: float | None = Field(None, description="Battery SOC percentage (0-100)")
    estimated_remaining_range_km: float | None = None
    remaining_trip_distance_km: float | None = None
    distance_travelled_km: float | None = None
    planned_trip_distance_km: float | None = None
    safety_reserve_km: float | None = None
    raw_latitude: float | None = None
    raw_longitude: float | None = None
    road_segment_id: str | None = None

    # Trip destination coordinates for route/detour calculations
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    destination_node_id: str | None = None

    requested_service: RequestedServiceType | None = None
    max_candidates: int | None = None
    eligible_only: bool = False


@router.post(
    "/candidate-search",
    response_model=CandidateSearchResult,
    status_code=status.HTTP_200_OK,
    summary="Search candidate stations and calculate routing metrics for an EnergyServiceRequest",
)
async def search_candidates(
    request: CandidateSearchRequest,
    request_obj: Request,
    eligible_only: bool = Query(False, description="If true, return only eligible candidates"),
) -> CandidateSearchResult:
    """
    Execute Week 3 candidate search and multi-leg routing for an EnergyServiceRequest.
    """
    service = get_candidate_service(request_obj)
    try:
        return await service.search_candidates(request, eligible_only=eligible_only)
    except RoutingEngineError as exc:
        raise _routing_http_error(exc) from exc


@router.post(
    "/candidate-search/evaluate",
    response_model=CandidateSearchResult,
    status_code=status.HTTP_200_OK,
    summary="End-to-end evaluation: telemetry -> demand detection -> candidate search",
)
async def evaluate_and_search(
    request: EvaluateAndSearchApiRequest,
    request_obj: Request = None,
) -> CandidateSearchResult:
    """
    Seamless integration endpoint:
    1. Look up Week 1 realtime driver state if driver_id is present and coordinates are missing.
    2. Evaluate Week 2 demand detection to produce canonical EnergyServiceRequest.
    3. Execute Week 3 candidate search and multi-leg routing.
    """
    request_time = request.timestamp if request.timestamp is not None else datetime.now(UTC)
    location = resolve_current_location(request.driver_id, request.raw_latitude,
                                        request.raw_longitude, request.road_segment_id, request_time,
                                        getattr(request_obj.app.state, "driver_state_store", None)
                                        if request_obj is not None else None)

    demand_ctx = DemandContext(
        vehicle_id=request.vehicle_id,
        driver_id=request.driver_id,
        trip_id=request.trip_id,
        timestamp=request_time,
        current_soc_pct=request.current_soc_pct,
        estimated_remaining_range_km=request.estimated_remaining_range_km,
        remaining_trip_distance_km=request.remaining_trip_distance_km,
        distance_travelled_km=request.distance_travelled_km,
        planned_trip_distance_km=request.planned_trip_distance_km,
        safety_reserve_km=request.safety_reserve_km,
        raw_latitude=location.latitude,
        raw_longitude=location.longitude,
        road_segment_id=location.road_segment_id,
    )

    demand_svc = get_demand_service(request_obj)
    if request.requested_service is not None:
        energy_req: EnergyServiceRequest = demand_svc.process_driver_request(
            demand_ctx, request.requested_service
        )
    else:
        energy_req: EnergyServiceRequest = demand_svc.evaluate_auto_demand(demand_ctx)

    search_req = CandidateSearchRequest(
        energy_request=energy_req,
        destination_latitude=request.destination_latitude,
        destination_longitude=request.destination_longitude,
        destination_node_id=request.destination_node_id,
        max_candidates=request.max_candidates,
    )

    service = get_candidate_service(request_obj)
    try:
        return await service.search_candidates(search_req, eligible_only=request.eligible_only)
    except RoutingEngineError as exc:
        raise _routing_http_error(exc) from exc
