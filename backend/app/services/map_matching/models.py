"""Map matching service models."""
from pydantic import BaseModel, Field
from typing import Optional


class GPSObservation(BaseModel):
    """A single GPS observation."""
    observation_id: str
    trajectory_id: str
    trip_id: str
    timestamp: str
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None


class MapMatchRequest(BaseModel):
    """Request for map matching a trajectory."""
    trajectory_id: str
    trip_id: str
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
    direction: Optional[str] = None
    confidence: Optional[float] = None
    distance_to_road_m: Optional[float] = None
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
