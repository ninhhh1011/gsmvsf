"""Map matching domain and sole production adapter."""
from backend.app.services.map_matching.engine import (
    MapMatchingEngine,
    MapMatchingEngineError,
    MapMatchingEngineUnavailableError,
    MapMatchingInvalidRequestError,
    MapMatchingNoMatchError,
    MapMatchingTimeoutError,
    Matching,
    Tracepoint,
)
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter
from backend.app.services.map_matching.models import (
    GPSObservation,
    MapMatchRequest,
    MapMatchResponse,
    MatchedObservation,
    ResolutionStatus,
)
from backend.app.services.map_matching.segment_resolver import (
    PostGISSegmentResolver,
    ResolutionStatus as ResolverStatus,
    RouteConstrainedSegmentResolver,
    SegmentInfo,
    SegmentResolverError,
    SegmentResolverUnavailableError,
)
from backend.app.services.map_matching.service import MapMatchingService

__all__ = [
    "GPSObservation",
    "GraphHopperMapMatchingAdapter",
    "MapMatchRequest",
    "MapMatchResponse",
    "MapMatchingEngine",
    "MapMatchingEngineError",
    "MapMatchingEngineUnavailableError",
    "MapMatchingInvalidRequestError",
    "MapMatchingNoMatchError",
    "MapMatchingService",
    "MapMatchingTimeoutError",
    "MatchedObservation",
    "Matching",
    "PostGISSegmentResolver",
    "ResolutionStatus",
    "ResolverStatus",
    "RouteConstrainedSegmentResolver",
    "SegmentInfo",
    "SegmentResolverError",
    "SegmentResolverUnavailableError",
    "Tracepoint",
]
