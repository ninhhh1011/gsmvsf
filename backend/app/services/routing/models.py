"""
Engine-independent routing domain models.

Defines project-level routing concepts that remain decoupled from concrete engines,
GraphHopper, or any specific HTTP/engine schema.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    """Geographic position with optional road network node reference."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    node_id: Optional[str] = None

    @property
    def coordinates_lat_lon(self) -> tuple[float, float]:
        """Return (latitude, longitude) tuple."""
        return (self.latitude, self.longitude)

    @property
    def coordinates_lon_lat(self) -> tuple[float, float]:
        """Return (longitude, latitude) tuple standard for GeoJSON."""
        return (self.longitude, self.latitude)


class RouteStatus(str, Enum):
    """Outcome status of a route calculation."""
    SUCCESS = "SUCCESS"
    NO_ROUTE = "NO_ROUTE"
    UNREACHABLE = "UNREACHABLE"
    ENGINE_ERROR = "ENGINE_ERROR"
    TIMEOUT = "TIMEOUT"
    INVALID_REQUEST = "INVALID_REQUEST"


class OptimizationObjective(str, Enum):
    """High-level route optimization objective."""
    MIN_TRAVEL_TIME = "MIN_TRAVEL_TIME"
    MIN_DISTANCE = "MIN_DISTANCE"
    MIN_DETOUR = "MIN_DETOUR"


class VehicleRoutingProfile(BaseModel):
    """Vehicle characteristics relevant to route computation."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    vehicle_id: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_category: Optional[str] = None
    routing_profile_hint: Optional[str] = None


class RouteConstraints(BaseModel):
    """Road and vehicle constraints for route search."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    avoid_segments: list[str] = Field(default_factory=list)
    max_distance_m: Optional[float] = None
    custom: dict[str, Any] = Field(default_factory=dict)


class DynamicRoutingContext(BaseModel):
    """Dynamic contextual data that directly impacts the road path."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: Optional[datetime] = None
    traffic_delay_factor: Optional[float] = None
    affected_segments: list[str] = Field(default_factory=list)


class RouteLeg(BaseModel):
    """A segment of a route between two waypoints."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_position: Position
    to_position: Position
    distance_m: float
    duration_s: float
    geometry: Optional[str] = None
    annotation_nodes: list[int] = Field(default_factory=list)


class RouteRequest(BaseModel):
    """
    Project-level routing request.
    Completely decoupled from any engine-specific URL structure or payload format.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Position
    destination: Position
    via: list[Position] = Field(default_factory=list)
    profile: Optional[VehicleRoutingProfile] = None
    constraints: Optional[RouteConstraints] = None
    objective: OptimizationObjective = OptimizationObjective.MIN_TRAVEL_TIME
    dynamic_context: Optional[DynamicRoutingContext] = None


class RouteResult(BaseModel):
    """
    Project-level routing result.
    Standardized schema returned by any RoutingEngine implementation.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RouteStatus
    distance_m: float = 0.0
    duration_s: float = 0.0
    legs: list[RouteLeg] = Field(default_factory=list)
    geometry: Optional[str] = None
    engine_name: str = "unknown"
    error_message: Optional[str] = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
