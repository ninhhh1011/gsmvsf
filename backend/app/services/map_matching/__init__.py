"""Map matching service module."""
from backend.app.services.map_matching.models import (
    GPSObservation,
    MapMatchRequest,
    MapMatchResponse,
    MatchedObservation,
)
from backend.app.services.map_matching.osrm_adapter import (
    OsrmMapMatchingAdapter,
    OsrmAdapterError,
    OsrmNoMatchError,
    OsrmUnavailableError,
    OsrmTimeoutError,
    OsrmBadRequestError,
)
from backend.app.services.map_matching.service import MapMatchingService
from backend.app.services.map_matching.segment_resolver import CoordinateSegmentResolver

__all__ = [
    "GPSObservation",
    "MapMatchRequest",
    "MapMatchResponse",
    "MatchedObservation",
    "OsrmMapMatchingAdapter",
    "OsrmAdapterError",
    "OsrmNoMatchError",
    "OsrmUnavailableError",
    "OsrmTimeoutError",
    "OsrmBadRequestError",
    "MapMatchingService",
    "CoordinateSegmentResolver",
]
