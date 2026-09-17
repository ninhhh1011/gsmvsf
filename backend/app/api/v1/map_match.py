"""Map matching API endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from backend.app.services.map_matching import (
    MapMatchRequest,
    MapMatchResponse,
    OsrmMapMatchingAdapter,
    OsrmAdapterError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Global instances (initialized lazily)
_osrm_adapter: Optional[OsrmMapMatchingAdapter] = None
_segment_resolver = None


def get_osrm_adapter(base_url: str) -> OsrmMapMatchingAdapter:
    """Get or create OSRM adapter."""
    global _osrm_adapter
    if _osrm_adapter is None:
        _osrm_adapter = OsrmMapMatchingAdapter(base_url)
    return _osrm_adapter


def get_segment_resolver(database_url: str):
    """Get or create PostGIS segment resolver."""
    global _segment_resolver
    if _segment_resolver is None:
        from backend.app.services.map_matching import PostGISSegmentResolver
        _segment_resolver = PostGISSegmentResolver(database_url)
    return _segment_resolver


@router.post("/map-match", response_model=MapMatchResponse)
async def map_match(
    request: MapMatchRequest,
) -> MapMatchResponse:
    """
    Match GPS observations to road network.

    This endpoint accepts a trajectory with GPS observations and returns
    matched road positions and segment identities.

    **Request body:**
    - trajectory_id: Trajectory identifier
    - trip_id: Trip identifier
    - observations: List of GPS observations

    **Response:**
    - Per-observation matched results with:
      - matched: boolean indicating OSRM match success
      - road_segment_id: Dataset V1 segment ID (or null if unresolved)
      - osm_way_id: OSM way ID (or null if unresolved)
      - direction: FORWARD/REVERSE (or null if unknown)
      - resolution_status: RESOLVED/AMBIGUOUS/UNRESOLVED
    - Match statistics
    - Overall OSRM confidence

    **Error codes:**
    - 400: Invalid request (too few observations, invalid coordinates)
    - 503: Map matching service unavailable
    """
    from backend.app.services.map_matching.service import MapMatchingService
    from backend.app.config import settings

    # Validate request
    if not request.observations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No observations provided",
        )

    if len(request.observations) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 observations required for map matching",
        )

    # Create adapters
    osrm_adapter = get_osrm_adapter(settings.osrm_base_url)
    segment_resolver = get_segment_resolver(settings.database_url_sync)

    # Create service with segment resolver
    service = MapMatchingService(osrm_adapter, segment_resolver)

    try:
        result = await service.match_trajectory(request)
        return result
    except OsrmAdapterError as e:
        logger.error(f"OSRM error during map matching: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Map matching service error: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Unexpected error during map matching")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )
