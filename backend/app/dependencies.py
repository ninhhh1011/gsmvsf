"""FastAPI dependency injection via request.app.state.

All services are initialized in the lifespan context manager and stored in
app.state. This module provides FastAPI Depends() getters that read from state.
"""

from fastapi import HTTPException, Request

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


def get_candidate_service(request: Request):
    """CandidateSearchService instance initialized by application lifespan."""
    return _require_state("candidate_service", request)


def get_demand_service(request: Request):
    """DemandService instance initialized by application lifespan."""
    return _require_state("demand_service", request)


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


def get_driver_state_manager(request: Request):
    """Driver state manager initialized by application lifespan."""
    return _require_state("driver_state_manager", request)
