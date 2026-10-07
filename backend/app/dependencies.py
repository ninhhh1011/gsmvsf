"""FastAPI dependency injection via request.app.state.

All services are initialized in the lifespan context manager and stored in
app.state. This module provides FastAPI Depends() getters that read from state.
"""

from fastapi import HTTPException, Request

from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.service import DemandService
from backend.app.services.ranking.orchestration import RecommendationWorkflow
from backend.app.services.snapshots.ingestion import IngestionService
from backend.app.services.snapshots.resolver import SnapshotResolver


def _require_state(state_key: str, request: Request):
    """Read from request.app.state or raise 500 if not initialized."""
    value = getattr(request.app.state, state_key, None)
    if value is None:
        raise HTTPException(
            500,
            detail=f"Application state '{state_key}' not initialized. "
                   f"Ensure the server is running with proper lifespan startup."
        )
    return value


def _get_state_or_fallback(request, state_key: str, fallback_global_name: str = None) -> object | None:
    """Safely get from request.app.state or from fallback global, returning None for invalid requests."""
    # Handle test fixtures that pass mock objects or non-Request values
    if not isinstance(request, Request):
        if fallback_global_name:
            import sys
            module = sys.modules[__name__]
            return getattr(module, fallback_global_name, None)
        return None
    return getattr(request.app.state, state_key, None)


def get_db_pool(request: Request):
    """PostgreSQL asyncpg connection pool."""
    return _require_state("db_pool", request)


def get_redis(request: Request):
    """Redis async client."""
    return _require_state("redis", request)


def get_http_client(request: Request):
    """Shared httpx AsyncClient from lifespan."""
    return _require_state("http_client", request)


def get_routing_adapter(request: Request):
    """GraphHopperRoutingAdapter instance from lifespan."""
    return _require_state("routing_adapter", request)


def get_candidate_service(request: Request = None) -> CandidateSearchService:
    """CandidateSearchService instance from app.state, fixture singleton, or auto-created."""
    svc = _get_state_or_fallback(request, "candidate_service", "_candidate_service_fallback")
    if svc is not None:
        return svc
    # Fallback for test fixtures that set module-level singleton
    global _candidate_service_fallback
    if _candidate_service_fallback is not None:
        return _candidate_service_fallback
    # Last resort: auto-create (tests only)
    from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
    return CandidateSearchService(routing_engine=GraphHopperRoutingAdapter())


# Fallback reference for test fixtures (module-level singleton)
_candidate_service_fallback: CandidateSearchService | None = None


def set_candidate_service_fallback(service: CandidateSearchService | None) -> None:
    """Set fallback for test fixtures that can't use app.state."""
    global _candidate_service_fallback
    _candidate_service_fallback = service


def get_demand_service(request: Request) -> DemandService:
    """DemandService instance from app.state, fixture singleton, or auto-created."""
    svc = _get_state_or_fallback(request, "demand_service", "_demand_service_fallback")
    if svc is not None:
        return svc
    # Fallback for test fixtures that set module-level singleton
    global _demand_service_fallback
    if _demand_service_fallback is not None:
        return _demand_service_fallback
    # Last resort: auto-create (tests only)
    from backend.app.services.demand.capability import VehicleCapabilityResolver
    return DemandService(capability_resolver=VehicleCapabilityResolver())


# Fallback reference for test fixtures (module-level singleton)
_demand_service_fallback: DemandService | None = None


def set_demand_service_fallback(service: DemandService | None) -> None:
    """Set fallback for test fixtures that can't use app.state."""
    global _demand_service_fallback
    _demand_service_fallback = service


def get_segment_resolver(request: Request):
    """RouteConstrainedSegmentResolver from lifespan (asyncpg)."""
    return _require_state("segment_resolver", request)


def get_map_matching_service(request: Request):
    """MapMatchingService instance from lifespan."""
    return _require_state("map_matching_service", request)


def get_snapshot_resolver(request: Request) -> SnapshotResolver:
    """SnapshotResolver instance from lifespan."""
    return _require_state("snapshot_resolver", request)


def get_snapshot_ingestion(request: Request) -> IngestionService:
    """IngestionService instance from lifespan."""
    return _require_state("snapshot_ingestion", request)


def get_recommendation_workflow(request: Request) -> RecommendationWorkflow:
    """RecommendationWorkflow instance from lifespan."""
    return _require_state("recommendation_workflow", request)


def get_realtime_simulator(request: Request):
    """RealtimeSimulator instance (may be None if disabled)."""
    return getattr(request.app.state, "realtime_simulator", None)
