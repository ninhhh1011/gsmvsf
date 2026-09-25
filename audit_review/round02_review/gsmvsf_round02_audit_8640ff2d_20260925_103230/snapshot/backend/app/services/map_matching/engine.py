"""Engine-independent matching contracts and explicit failure categories."""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class MapMatchingEngineError(Exception):
    """Malformed engine response or internal engine failure."""


class MapMatchingEngineUnavailableError(MapMatchingEngineError):
    """Engine cannot be reached."""


class MapMatchingNoMatchError(MapMatchingEngineError):
    """No path matches the trace."""


class MapMatchingTimeoutError(MapMatchingEngineError):
    """Engine request timed out."""


class MapMatchingInvalidRequestError(MapMatchingEngineError):
    """Unsupported or invalid input."""


@dataclass
class Tracepoint:
    waypoint_index: int
    location: tuple[float, float]  # longitude, latitude
    distance: float
    name: str
    matched: bool
    osm_way_id: int | None = None
    bearing: float | None = None
    null_reason: str | None = None


@dataclass
class Matching:
    confidence: float
    distance: float
    duration: float
    geometry: str
    tracepoints: list[Tracepoint]
    profile: str


@runtime_checkable
class MapMatchingEngine(Protocol):
    async def match(self, coordinates: list[tuple[float, float]], *,
                    vehicle_category: str) -> tuple[Matching, list[Tracepoint]]:
        """Match longitude/latitude observations for a domain vehicle category."""
        ...
