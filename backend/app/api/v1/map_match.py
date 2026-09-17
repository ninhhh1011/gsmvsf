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

# Global OSRM adapter (initialized per-request for now)
_osrm_adapter: Optional[OsrmMapMatchingAdapter] = None


def get_osrm_adapter(base_url: str) -> OsrmMapMatchingAdapter:
    """Get or create OSRM adapter."""
    global _osrm_adapter
    if _osrm_adapter is None:
        _osrm_adapter = OsrmMapMatchingAdapter(base_url)
    return _osrm_adapter


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
    - Per-observation matched results
    - Match statistics
    - Overall confidence

    **Error codes:**
    - 400: Invalid request (too few observations, invalid coordinates)
    - 503: OSRM service unavailable
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

    # Create OSRM adapter
    adapter = get_osrm_adapter(settings.osrm_base_url)

    # Create service
    service = MapMatchingService(adapter)

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
