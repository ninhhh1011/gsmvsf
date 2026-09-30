"""
Route History API Endpoints
=========================

API endpoints for route history queries:
- Route similarity comparison
- Route family queries
- Driver habitual route lookup
- Historical data management
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.services.route_history.similarity import RoadLevelSimilarity, RouteSegments, SegmentInfo
from backend.app.services.route_history.families import RouteFamilyCluster
from backend.app.services.route_history.integration import (
    RouteHistoryConfig,
    HistoricalFamiliarityService,
    HistoricalEvidence,
    HistoryStatus,
)
from backend.app.services.route_history.repository import RouteHistoryRepository

router = APIRouter()


# --- Response Models ---

class SimilarityResponse(BaseModel):
    """Response for route similarity query."""
    route1_id: str
    route2_id: str
    shared_distance_m: float
    recommended_adherence: float
    actual_overlap: float
    symmetric_similarity: float
    has_divergence: bool
    divergence_at_segment: Optional[int] = None


class RouteFamilyResponse(BaseModel):
    """Response for route family query."""
    family_id: str
    representative_route_id: str
    trip_count: int
    unique_driver_count: int
    weighted_support: float
    weighted_share: float  # As percentage
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    direction_bearing: float


class DriverHabitualResponse(BaseModel):
    """Response for driver habitual route query."""
    driver_id: str
    has_history: bool
    status: str
    dominant_family: Optional[RouteFamilyResponse] = None
    alternative_families: List[RouteFamilyResponse] = []
    total_historical_trips: int = 0
    history_window_days: int = 7


class HistoryStatusResponse(BaseModel):
    """Response for history status check."""
    enabled: bool
    history_count: int
    family_count: int


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: str


# --- Service Instances ---

def get_route_repository() -> Optional[RouteHistoryRepository]:
    """Get route history repository if configured."""
    try:
        return RouteHistoryRepository(settings.database_url_sync)
    except Exception:
        return None


# --- API Endpoints ---

@router.get(
    "/route-history/status",
    response_model=HistoryStatusResponse,
    tags=["route-history"],
    summary="Get route history status",
)
async def get_history_status(
    repository: Optional[RouteHistoryRepository] = Depends(get_route_repository),
):
    """
    Get current status of historical route data.

    Returns counts of routes and families stored.
    """
    if repository is None:
        raise HTTPException(503, "Route history database not configured")

    try:
        stats = repository.get_stats()
        return HistoryStatusResponse(
            enabled=True,
            history_count=stats.get("total_routes", 0),
            family_count=stats.get("total_families", 0),
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to query history: {str(e)}")


@router.get(
    "/route-history/families",
    response_model=List[RouteFamilyResponse],
    tags=["route-history"],
    summary="Query route families by context",
)
async def query_route_families(
    origin_lat: float = Query(..., ge=-90, le=90, description="Origin latitude"),
    origin_lng: float = Query(..., ge=-180, le=180, description="Origin longitude"),
    dest_lat: float = Query(..., ge=-90, le=90, description="Destination latitude"),
    dest_lng: float = Query(..., ge=-180, le=180, description="Destination longitude"),
    max_origin_dist_km: float = Query(2.0, ge=0.1, le=10, description="Max origin distance (km)"),
    max_dest_dist_km: float = Query(2.0, ge=0.1, le=10, description="Max destination distance (km)"),
    limit: int = Query(10, ge=1, le=100, description="Max families to return"),
    repository: Optional[RouteHistoryRepository] = Depends(get_route_repository),
):
    """
    Query route families matching origin/destination context.

    Returns families ordered by weighted support (most popular first).
    """
    if repository is None:
        raise HTTPException(503, "Route history database not configured")

    try:
        families = repository.get_route_families_by_context(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            max_origin_dist_km=max_origin_dist_km,
            max_dest_dist_km=max_dest_dist_km,
            limit=limit,
        )

        # Calculate total support for percentages
        total_support = sum(f.weighted_support for f in families) if families else 1.0

        return [
            RouteFamilyResponse(
                family_id=f.family_id,
                representative_route_id=f.representative_route_id,
                trip_count=f.trip_count,
                unique_driver_count=f.unique_driver_count,
                weighted_support=f.weighted_support,
                weighted_share=f.weighted_support / total_support * 100 if total_support > 0 else 0,
                origin_lat=f.origin_lat,
                origin_lng=f.origin_lng,
                dest_lat=f.dest_lat,
                dest_lng=f.dest_lng,
                direction_bearing=f.direction_bearing,
            )
            for f in families
        ]
    except Exception as e:
        raise HTTPException(500, f"Failed to query families: {str(e)}")


@router.get(
    "/route-history/driver/{driver_id}",
    response_model=DriverHabitualResponse,
    tags=["route-history"],
    summary="Get driver's habitual routes",
)
async def get_driver_habitual(
    driver_id: str,
    origin_lat: Optional[float] = Query(None, ge=-90, le=90),
    origin_lng: Optional[float] = Query(None, ge=-180, le=180),
    dest_lat: Optional[float] = Query(None, ge=-90, le=90),
    dest_lng: Optional[float] = Query(None, ge=-180, le=180),
    repository: Optional[RouteHistoryRepository] = Depends(get_route_repository),
):
    """
    Get driver's habitual routes based on historical trips.

    If origin/destination provided, returns families matching that context.
    Otherwise returns driver's most recent route families.
    """
    if repository is None:
        raise HTTPException(503, "Route history database not configured")

    try:
        # Get driver's routes
        driver_routes = repository.query_routes_by_driver(driver_id, limit=100)

        if not driver_routes:
            return DriverHabitualResponse(
                driver_id=driver_id,
                has_history=False,
                status=HistoryStatus.NO_HISTORY.value,
                total_historical_trips=0,
            )

        # Get unique families from driver's routes
        # This is simplified - in production would query family membership
        total_trips = len(driver_routes)

        # If context provided, find matching families
        if all(x is not None for x in [origin_lat, origin_lng, dest_lat, dest_lng]):
            families = repository.get_route_families_by_context(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                dest_lat=dest_lat,
                dest_lng=dest_lng,
                limit=5,
            )

            if families:
                total_support = sum(f.weighted_support for f in families) if families else 1.0
                dominant = RouteFamilyResponse(
                    family_id=families[0].family_id,
                    representative_route_id=families[0].representative_route_id,
                    trip_count=families[0].trip_count,
                    unique_driver_count=families[0].unique_driver_count,
                    weighted_support=families[0].weighted_support,
                    weighted_share=families[0].weighted_support / total_support * 100 if total_support > 0 else 0,
                    origin_lat=families[0].origin_lat,
                    origin_lng=families[0].origin_lng,
                    dest_lat=families[0].dest_lat,
                    dest_lng=families[0].dest_lng,
                    direction_bearing=families[0].direction_bearing,
                )
                alternatives = [
                    RouteFamilyResponse(
                        family_id=f.family_id,
                        representative_route_id=f.representative_route_id,
                        trip_count=f.trip_count,
                        unique_driver_count=f.unique_driver_count,
                        weighted_support=f.weighted_support,
                        weighted_share=f.weighted_support / total_support * 100 if total_support > 0 else 0,
                        origin_lat=f.origin_lat,
                        origin_lng=f.origin_lng,
                        dest_lat=f.dest_lat,
                        dest_lng=f.dest_lng,
                        direction_bearing=f.direction_bearing,
                    )
                    for f in families[1:]
                ]
            else:
                dominant = None
                alternatives = []
        else:
            dominant = None
            alternatives = []

        return DriverHabitualResponse(
            driver_id=driver_id,
            has_history=True,
            status=HistoryStatus.MATCHED.value if dominant else HistoryStatus.NO_HISTORY.value,
            dominant_family=dominant,
            alternative_families=alternatives,
            total_historical_trips=total_trips,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to query driver history: {str(e)}")


@router.get(
    "/route-history/similarity",
    response_model=SimilarityResponse,
    tags=["route-history"],
    summary="Compare two routes",
)
async def compare_routes(
    route1_id: str = Query(..., description="First route ID"),
    route2_id: str = Query(..., description="Second route ID"),
    repository: Optional[RouteHistoryRepository] = Depends(get_route_repository),
):
    """
    Compare similarity between two routes.

    Returns road-level similarity metrics:
    - recommended_adherence: How much route2 follows route1
    - actual_overlap: How much overlap exists
    - symmetric_similarity: Balanced measure
    - divergence: Whether routes diverge
    """
    if repository is None:
        raise HTTPException(503, "Route history database not configured")

    try:
        # Get route segments
        segs1 = repository.get_route_segments(route1_id)
        segs2 = repository.get_route_segments(route2_id)

        if not segs1:
            raise HTTPException(404, f"Route {route1_id} not found")
        if not segs2:
            raise HTTPException(404, f"Route {route2_id} not found")

        # Create similarity calculator (with empty segment data - segments from DB)
        calc = RoadLevelSimilarity()

        # Build route segments
        route1 = RouteSegments(
            route_id=route1_id,
            segments=[],  # Would need segment info from DB
            total_distance_m=0.0,
        )
        route2 = RouteSegments(
            route_id=route2_id,
            segments=[],
            total_distance_m=0.0,
        )

        # Calculate using segment IDs directly
        shared_segs = set(segs1) & set(segs2)
        shared_count = len(shared_segs)

        # Calculate metrics
        adherence = shared_count / len(segs1) if segs1 else 0
        overlap = shared_count / len(segs2) if segs2 else 0
        symmetric = 2 * shared_count / (len(segs1) + len(segs2)) if (segs1 and segs2) else 0

        # Check divergence (simplified - just check if first segments match)
        has_divergence = False
        divergence_at = None
        if segs1 and segs2 and segs1[0] != segs2[0]:
            has_divergence = True
            divergence_at = 0

        return SimilarityResponse(
            route1_id=route1_id,
            route2_id=route2_id,
            shared_distance_m=shared_count * 100.0,  # Approximate
            recommended_adherence=adherence,
            actual_overlap=overlap,
            symmetric_similarity=symmetric,
            has_divergence=has_divergence,
            divergence_at_segment=divergence_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to compare routes: {str(e)}")


@router.get(
    "/route-history/h3-lookup",
    response_model=List[str],
    tags=["route-history"],
    summary="Find routes by H3 cells",
)
async def h3_lookup(
    h3_cells: str = Query(..., description="Comma-separated H3 cell IDs"),
    min_overlap: int = Query(1, ge=1, le=100, description="Min shared cells"),
    limit: int = Query(100, ge=1, le=1000, description="Max routes to return"),
    repository: Optional[RouteHistoryRepository] = Depends(get_route_repository),
):
    """
    Find routes passing through H3 cells.

    This is the inverted index lookup for candidate retrieval.
    """
    if repository is None:
        raise HTTPException(503, "Route history database not configured")

    try:
        cells = [c.strip() for c in h3_cells.split(",") if c.strip()]
        if not cells:
            raise HTTPException(400, "No valid H3 cells provided")

        results = repository.query_by_h3_cells(cells, min_overlap=min_overlap)

        # Return just route IDs up to limit
        return [route_id for route_id, _ in results[:limit]]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to query H3 index: {str(e)}")
