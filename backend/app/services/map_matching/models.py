"""Map matching service models."""
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Literal


class ResolutionStatus(str, Enum):
    """Status of segment resolution."""
    ROUTE_NODE_PAIR = "ROUTE_NODE_PAIR"
    ROUTE_SPATIAL = "ROUTE_SPATIAL"
    GLOBAL_SPATIAL = "GLOBAL_SPATIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


class GPSObservation(BaseModel):
    """A single GPS observation."""
    observation_id: str
    trajectory_id: str
    trip_id: str
    timestamp: str
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None


class MapMatchRequest(BaseModel):
    """Request for map matching a trajectory."""
    trajectory_id: str
    trip_id: str
    vehicle_id: Optional[str] = None
    vehicle_category: Optional[Literal["EV_CAR", "EV_MOTORBIKE"]] = None
    observations: list[GPSObservation] = Field(..., min_length=1)


class MatchedObservation(BaseModel):
    """Result of matching a single observation."""
    observation_id: str
    timestamp: str
    raw_latitude: float
    raw_longitude: float
    matched: bool
    matched_latitude: Optional[float] = None
    matched_longitude: Optional[float] = None
    road_segment_id: Optional[str] = None
    osm_way_id: Optional[int] = None
    direction: Optional[str] = None  # FORWARD, REVERSE, or null if UNKNOWN
    confidence: Optional[float] = None  # Project geometry proximity quality, not probability
    distance_to_road_m: Optional[float] = None
    resolution_status: Optional[ResolutionStatus] = None
    null_reason: Optional[str] = None


class MapMatchResponse(BaseModel):
    """Response from map matching a trajectory."""
    trajectory_id: str
    trip_id: str
    total_observations: int
    matched_count: int
    unmatched_count: int
    observations: list[MatchedObservation]
    overall_confidence: Optional[float] = None
    trace_geometry: Optional[str] = None
    engine_name: str = "graphhopper"
    profile: Optional[str] = None
    quality_semantics: str = "mean(max(0, 1 - distance_to_matched_path_m / 100)); not a probability"
