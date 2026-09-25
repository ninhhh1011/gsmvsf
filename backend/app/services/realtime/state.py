"""
Per-driver trace state for realtime map matching.

Maintains bounded GPS observation history and match state per driver.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# Constants from benchmark policy
DEFAULT_CONTEXT_WINDOW_SECONDS = 30.0
DEFAULT_MAX_CONTEXT_POINTS = 50
DEFAULT_GAP_THRESHOLD_SECONDS = 60.0
DEFAULT_STATIONARY_THRESHOLD = 3  # consecutive observations
DEFAULT_STATIONARY_DISTANCE_M = 5.0  # movement below this = stationary


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters."""
    import math
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def make_naive(dt: datetime) -> datetime:
    """Convert datetime to naive (no timezone) UTC for consistent comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


@dataclass
class GPSObservation:
    """A single GPS observation."""
    observation_id: str
    driver_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None

    @classmethod
    def from_dict(cls, data: dict) -> "GPSObservation":
        """Create from API request dict."""
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(
            observation_id=data.get("observation_id", ""),
            driver_id=data.get("driver_id", ""),
            timestamp=ts,
            latitude=data["latitude"],
            longitude=data["longitude"],
            speed_kmh=data.get("speed_kmh"),
            heading_deg=data.get("heading_deg"),
            accuracy_m=data.get("accuracy_m"),
        )

    def to_dict(self) -> dict:
        """Export to dict for serialization."""
        return {
            "observation_id": self.observation_id,
            "driver_id": self.driver_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed_kmh": self.speed_kmh,
            "heading_deg": self.heading_deg,
            "accuracy_m": self.accuracy_m,
        }


@dataclass
class MatchedState:
    """Result of a map match operation."""
    matched_latitude: float
    matched_longitude: float
    road_segment_id: Optional[str] = None
    osm_way_id: Optional[int] = None
    direction: Optional[str] = None
    confidence: Optional[float] = None
    route_geometry: Optional[str] = None
    matched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Export to dict for serialization."""
        return {
            "matched_latitude": self.matched_latitude,
            "matched_longitude": self.matched_longitude,
            "road_segment_id": self.road_segment_id,
            "osm_way_id": self.osm_way_id,
            "direction": self.direction,
            "confidence": self.confidence,
            "route_geometry": self.route_geometry,
            "matched_at": self.matched_at.isoformat() if self.matched_at else None,
        }


@dataclass
class DriverTraceState:
    """
    Per-driver trace state for realtime map matching.

    Maintains a bounded window of recent GPS observations and match state.
    """
    driver_id: str
    observations: deque[GPSObservation] = field(default_factory=lambda: deque(maxlen=1000))
    last_match_time: Optional[datetime] = None
    last_matched_state: Optional[MatchedState] = None
    movement_since_match: float = 0.0
    last_observation_timestamp: Optional[datetime] = None
    observations_since_match: int = 0
    consecutive_stationary: int = 0
    total_observations_received: int = 0
    total_match_calls: int = 0
    last_trigger_reason: Optional[str] = None
    last_match_latency_ms: Optional[float] = None
    current_status: str = "WARMING_UP"
    generation: int = 1  # Incremented on reset to invalidate old requests

    def add_observation(self, obs: GPSObservation) -> tuple[bool, str]:
        """
        Add an observation and update state.

        Returns:
            (was_gap_reset, gap_reason)
        """
        gap_reset = False
        gap_reason = ""

        # Check for gap (session reset)
        if (self.last_observation_timestamp and
            (obs.timestamp - self.last_observation_timestamp).total_seconds() >
                DEFAULT_GAP_THRESHOLD_SECONDS):
            # Reset state
            self.observations.clear()
            self.last_match_time = None
            self.last_matched_state = None
            self.movement_since_match = 0.0
            self.observations_since_match = 0
            self.consecutive_stationary = 0
            gap_reset = True
            gap_reason = f"gap({(obs.timestamp - self.last_observation_timestamp).total_seconds():.0f}s)"

        # Calculate movement from last observation
        if self.observations:
            prev = self.observations[-1]
            dist = haversine_distance(
                prev.latitude, prev.longitude,
                obs.latitude, obs.longitude
            )
            self.movement_since_match += dist

            # Check for stationary (GPS jitter)
            if dist < DEFAULT_STATIONARY_DISTANCE_M:
                self.consecutive_stationary += 1
            else:
                self.consecutive_stationary = 0

        # Add observation
        self.observations.append(obs)
        self.last_observation_timestamp = obs.timestamp
        self.observations_since_match += 1
        self.total_observations_received += 1

        return gap_reset, gap_reason

    def get_context(
        self,
        window_seconds: float = DEFAULT_CONTEXT_WINDOW_SECONDS,
        max_points: int = DEFAULT_MAX_CONTEXT_POINTS,
    ) -> list[GPSObservation]:
        """Get recent observations within window."""
        if not self.observations:
            return []

        # Time-based filter
        cutoff = self.last_observation_timestamp - timedelta(seconds=window_seconds)
        recent = [o for o in self.observations if o.timestamp >= cutoff]

        # Point limit
        return recent[-max_points:]

    def is_warming_up(self) -> bool:
        """Check if enough observations for matching."""
        return len(self.observations) < 3

    def is_stationary(self) -> bool:
        """Check if driver appears to be stationary."""
        return self.consecutive_stationary >= DEFAULT_STATIONARY_THRESHOLD

    def reset_after_match(self, matched_state: Optional[MatchedState] = None):
        """Reset after successful match."""
        self.last_match_time = self.last_observation_timestamp
        self.movement_since_match = 0.0
        self.observations_since_match = 0
        self.last_matched_state = matched_state
        self.total_match_calls += 1

    def reset_state(self):
        """Reset state and increment generation to invalidate old requests."""
        self.observations.clear()
        self.last_match_time = None
        self.last_matched_state = None
        self.movement_since_match = 0.0
        self.observations_since_match = 0
        self.consecutive_stationary = 0
        self.total_match_calls = 0
        self.generation += 1  # Invalidate requests from previous generation

    def get_current_raw_position(self) -> Optional[tuple[float, float]]:
        """Get most recent raw GPS position."""
        if self.observations:
            last = self.observations[-1]
            return (last.latitude, last.longitude)
        return None

    def to_dict(self) -> dict:
        """Export current state for API response."""
        raw_pos = self.get_current_raw_position()
        return {
            "driver_id": self.driver_id,
            "status": self.current_status,
            "raw_position": {
                "latitude": raw_pos[0] if raw_pos else None,
                "longitude": raw_pos[1] if raw_pos else None,
                "timestamp": self.last_observation_timestamp.isoformat() if self.last_observation_timestamp else None,
            } if raw_pos else None,
            "matched_position": {
                "latitude": self.last_matched_state.matched_latitude if self.last_matched_state else None,
                "longitude": self.last_matched_state.matched_longitude if self.last_matched_state else None,
                "road_segment_id": self.last_matched_state.road_segment_id if self.last_matched_state else None,
                "osm_way_id": self.last_matched_state.osm_way_id if self.last_matched_state else None,
                "direction": self.last_matched_state.direction if self.last_matched_state else None,
                "confidence": self.last_matched_state.confidence if self.last_matched_state else None,
            } if self.last_matched_state else None,
            "last_match_time": self.last_match_time.isoformat() if self.last_match_time else None,
            "last_trigger_reason": self.last_trigger_reason,
            "last_match_latency_ms": self.last_match_latency_ms,
            "total_observations_received": self.total_observations_received,
            "total_match_calls": self.total_match_calls,
            "buffered_observations": len(self.observations),
            "observations_since_match": self.observations_since_match,
            "movement_since_match_m": self.movement_since_match,
            "is_stationary": self.is_stationary(),
        }


class DriverStateStore:
    """
    In-memory store for per-driver trace states.

    For Week 1, uses simple dict with bounded state.
    Can be replaced with Redis/PostgreSQL for production.
    """

    def __init__(self, max_drivers: int = 10000):
        self._states: dict[str, DriverTraceState] = {}
        self._max_drivers = max_drivers

    def get_or_create(self, driver_id: str) -> DriverTraceState:
        """Get existing or create new state for driver."""
        if driver_id not in self._states:
            # Simple LRU: remove oldest if at capacity
            if len(self._states) >= self._max_drivers:
                oldest = next(iter(self._states))
                del self._states[oldest]
            self._states[driver_id] = DriverTraceState(driver_id=driver_id)
        return self._states[driver_id]

    def get(self, driver_id: str) -> Optional[DriverTraceState]:
        """Get state if exists."""
        return self._states.get(driver_id)

    def remove(self, driver_id: str) -> bool:
        """Remove driver state."""
        if driver_id in self._states:
            del self._states[driver_id]
            return True
        return False

    def list_drivers(self) -> list[str]:
        """List all active driver IDs."""
        return list(self._states.keys())

    def __len__(self) -> int:
        return len(self._states)


# Global state store instance
_global_store: Optional[DriverStateStore] = None


def get_state_store() -> DriverStateStore:
    """Get global state store instance."""
    global _global_store
    if _global_store is None:
        _global_store = DriverStateStore()
    return _global_store


def reset_state_store():
    """Reset global state store (for testing)."""
    global _global_store
    _global_store = None
