"""Map matching service models."""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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
    speed_kmh: float | None = None
    heading_deg: float | None = None
    accuracy_m: float | None = None


class MapMatchRequest(BaseModel):
    """Request for map matching a trajectory."""
    trajectory_id: str
    trip_id: str
    vehicle_id: str | None = None
    vehicle_category: Literal["EV_CAR", "EV_MOTORBIKE"] | None = None
    observations: list[GPSObservation] = Field(..., min_length=1)


class MatchedObservation(BaseModel):
    """Result of matching a single observation."""
    observation_id: str
    timestamp: str
    raw_latitude: float
    raw_longitude: float
    matched: bool
    matched_latitude: float | None = None
    matched_longitude: float | None = None
    road_segment_id: str | None = None
    osm_way_id: int | None = None
    direction: str | None = None  # FORWARD, REVERSE, or null if UNKNOWN
    confidence: float | None = None  # Project geometry proximity quality, not probability
    distance_to_road_m: float | None = None
    resolution_status: ResolutionStatus | None = None
    null_reason: str | None = None


class MapMatchResponse(BaseModel):
    """Response from map matching a trajectory."""
    trajectory_id: str
    trip_id: str
    total_observations: int
    matched_count: int
    unmatched_count: int
    observations: list[MatchedObservation]
    overall_confidence: float | None = None
    trace_geometry: str | None = None
    engine_name: str = "graphhopper"
    profile: str | None = None
    quality_semantics: str = "mean(max(0, 1 - distance_to_matched_path_m / 100)); not a probability"
