"""
Engine-independent routing domain models.

Defines project-level routing concepts that remain decoupled from concrete engines,
GraphHopper, or any specific HTTP/engine schema.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Position(BaseModel):
    """Geographic position with optional road network node reference."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    node_id: str | None = None

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

    vehicle_id: str | None = None
    vehicle_model: str | None = None
    vehicle_category: str | None = None
    routing_profile_hint: str | None = None


class RouteConstraints(BaseModel):
    """Road and vehicle constraints for route search."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    avoid_segments: list[str] = Field(default_factory=list)
    max_distance_m: float | None = None
    custom: dict[str, Any] = Field(default_factory=dict)


class DynamicRoutingContext(BaseModel):
    """Dynamic contextual data that directly impacts the road path."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime | None = None
    traffic_delay_factor: float | None = None
    affected_segments: list[str] = Field(default_factory=list)


class RouteLeg(BaseModel):
    """A segment of a route between two waypoints."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_position: Position
    to_position: Position
    distance_m: float
    duration_s: float
    geometry: str | None = None
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
    profile: VehicleRoutingProfile | None = None
    constraints: RouteConstraints | None = None
    objective: OptimizationObjective = OptimizationObjective.MIN_TRAVEL_TIME
    dynamic_context: DynamicRoutingContext | None = None


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
    geometry: str | None = None
    engine_name: str = "unknown"
    error_message: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
