from backend.app.config import settings
from backend.app.services.map_matching import (
    GraphHopperMapMatchingAdapter,
    MapMatchingEngineError,
    MapMatchingInvalidRequestError,
    MapMatchingNoMatchError,
    MapMatchingService,
    MapMatchingTimeoutError,
    MapMatchRequest,
    MapMatchResponse,
    RouteConstrainedSegmentResolver,
    SegmentResolverUnavailableError,
)
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()
_segment_resolver = None


def get_map_matching_adapter():
    return GraphHopperMapMatchingAdapter(base_url=settings.graphhopper_base_url)


def get_segment_resolver(request: Request = None, database_url=None, mapping_dir=None):
    if request is not None and hasattr(request, "app") and getattr(request.app.state, "segment_resolver", None) is not None:
        return request.app.state.segment_resolver
    global _segment_resolver
    if _segment_resolver is None:
        _segment_resolver = RouteConstrainedSegmentResolver(database_url or settings.database_url_sync)
    return _segment_resolver


def get_map_matching_service(request: Request = None):
    if request is not None and hasattr(request, "app") and getattr(request.app.state, "map_matching_service", None) is not None:
        return request.app.state.map_matching_service
    return MapMatchingService(get_map_matching_adapter(), get_segment_resolver(request))


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
