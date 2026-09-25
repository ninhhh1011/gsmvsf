"""Map matching API backed exclusively by GraphHopper."""
import psycopg2
from fastapi import APIRouter, HTTPException

from backend.app.config import settings
from backend.app.services.map_matching import (
    MapMatchRequest, MapMatchResponse, MapMatchingService, GraphHopperMapMatchingAdapter,
    MapMatchingEngineError, MapMatchingInvalidRequestError, MapMatchingNoMatchError,
    MapMatchingTimeoutError, RouteConstrainedSegmentResolver,
)

router = APIRouter()
_segment_resolver = None


def get_map_matching_adapter():
    return GraphHopperMapMatchingAdapter(base_url=settings.graphhopper_base_url)


def get_segment_resolver(database_url=None, mapping_dir=None):
    global _segment_resolver
    if _segment_resolver is None:
        _segment_resolver = RouteConstrainedSegmentResolver(database_url or settings.database_url_sync)
    return _segment_resolver


def get_map_matching_service():
    return MapMatchingService(get_map_matching_adapter(), get_segment_resolver())


@router.post("/map-match", response_model=MapMatchResponse)
async def map_match(request: MapMatchRequest):
    if len(request.observations) < 2:
        raise HTTPException(400, "At least 2 observations required for map matching")
    try:
        return await get_map_matching_service().match_trajectory(request)
    except (MapMatchingInvalidRequestError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except MapMatchingNoMatchError as exc:
        raise HTTPException(422, {"status": "NO_MATCH", "message": str(exc)}) from exc
    except MapMatchingTimeoutError as exc:
        raise HTTPException(504, {"status": "ENGINE_TIMEOUT", "message": str(exc)}) from exc
    except MapMatchingEngineError as exc:
        raise HTTPException(503, {"status": "ENGINE_UNAVAILABLE", "message": str(exc)}) from exc
    except psycopg2.Error as exc:
        raise HTTPException(503, {"status": "SEGMENT_RESOLVER_UNAVAILABLE"}) from exc
