"""Map matching endpoints using GraphHopper and PostGIS segment resolver."""

from backend.app.dependencies import get_map_matching_service, get_segment_resolver
from backend.app.services.map_matching import (
    MapMatchingEngineError,
    MapMatchingInvalidRequestError,
    MapMatchingNoMatchError,
    MapMatchingService,
    MapMatchingTimeoutError,
    MapMatchRequest,
    MapMatchResponse,
    SegmentResolverUnavailableError,
)
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.post("/map-match", response_model=MapMatchResponse)
async def map_match(
    request: MapMatchRequest,
    service: MapMatchingService = Depends(get_map_matching_service),
):
    if len(request.observations) < 2:
        raise HTTPException(400, "At least 2 observations required for map matching")
    try:
        return await service.match_trajectory(request)
    except (MapMatchingInvalidRequestError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except MapMatchingNoMatchError as exc:
        raise HTTPException(422, {"status": "NO_MATCH", "message": str(exc)}) from exc
    except MapMatchingTimeoutError as exc:
        raise HTTPException(504, {"status": "ENGINE_TIMEOUT", "message": str(exc)}) from exc
    except MapMatchingEngineError as exc:
        raise HTTPException(503, {"status": "ENGINE_UNAVAILABLE", "message": str(exc)}) from exc
    except SegmentResolverUnavailableError as exc:
        raise HTTPException(503, {"status": "SEGMENT_RESOLVER_UNAVAILABLE"}) from exc
