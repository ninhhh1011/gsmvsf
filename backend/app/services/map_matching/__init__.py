"""Map matching domain and sole production adapter."""
from backend.app.services.map_matching.engine import (
    MapMatchingEngine, MapMatchingEngineError, MapMatchingEngineUnavailableError,
    MapMatchingNoMatchError, MapMatchingTimeoutError, MapMatchingInvalidRequestError,
    Tracepoint, Matching,
)
from backend.app.services.map_matching.models import (
    GPSObservation, MapMatchRequest, MapMatchResponse, MatchedObservation, ResolutionStatus,
)
from backend.app.services.map_matching.service import MapMatchingService
from backend.app.services.map_matching.segment_resolver import (
    RouteConstrainedSegmentResolver, PostGISSegmentResolver, SegmentInfo,
    ResolutionStatus as ResolverStatus,
)
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter
