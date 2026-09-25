"""
Cross-process driver state repository for productionization.

Provides Redis-backed persistence for DriverTraceState to enable
shared state across multiple API processes.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis

from backend.app.config import settings


logger = logging.getLogger(__name__)


# Constants matching state.py
DEFAULT_CONTEXT_WINDOW_SECONDS = 30.0
DEFAULT_MAX_CONTEXT_POINTS = 50
DEFAULT_GAP_THRESHOLD_SECONDS = 60.0
DEFAULT_STATIONARY_THRESHOLD = 3
DEFAULT_STATIONARY_DISTANCE_M = 5.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters."""
    import math
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Re-export models from state.py for serialization
# These must stay in sync with state.py
@dataclass
class GPSObservation:
    observation_id: str
    driver_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    speed_kmh: Optional[float] = None
    heading_deg: Optional[float] = None
    accuracy_m: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "driver_id": self.driver_id,
            "timestamp": self.timestamp.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed_kmh": self.speed_kmh,
            "heading_deg": self.heading_deg,
            "accuracy_m": self.accuracy_m,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GPSObservation":
        ts = data["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(
            observation_id=data["observation_id"],
            driver_id=data["driver_id"],
            timestamp=ts,
            latitude=data["latitude"],
            longitude=data["longitude"],
            speed_kmh=data.get("speed_kmh"),
            heading_deg=data.get("heading_deg"),
            accuracy_m=data.get("accuracy_m"),
        )


@dataclass
class MatchedState:
    matched_latitude: float
    matched_longitude: float
    road_segment_id: Optional[str] = None
    osm_way_id: Optional[int] = None
    direction: Optional[str] = None
    confidence: Optional[float] = None
    route_geometry: Optional[str] = None
    matched_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "matched_latitude": self.matched_latitude,
            "matched_longitude": self.matched_longitude,
            "road_segment_id": self.road_segment_id,
            "osm_way_id": self.osm_way_id,
            "direction": self.direction,
            "confidence": self.confidence,
            "route_geometry": self.route_geometry,
            "matched_at": self.matched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MatchedState":
        matched_at = data.get("matched_at")
        if isinstance(matched_at, str):
            matched_at = datetime.fromisoformat(matched_at.replace("Z", "+00:00"))
        return cls(
            matched_latitude=data["matched_latitude"],
            matched_longitude=data["matched_longitude"],
            road_segment_id=data.get("road_segment_id"),
            osm_way_id=data.get("osm_way_id"),
            direction=data.get("direction"),
            confidence=data.get("confidence"),
            route_geometry=data.get("route_geometry"),
            matched_at=matched_at or datetime.utcnow(),
        )


@dataclass
class DriverTraceStateSnapshot:
    """
    Serializable snapshot of DriverTraceState for Redis persistence.

    Preserves all runtime state needed for cross-process continuity.
    """
    driver_id: str
    observations: list[dict] = field(default_factory=list)  # Serialized GPSObservation
    last_match_time: Optional[str] = None  # ISO format
    last_matched_state: Optional[dict] = None  # Serialized MatchedState
    movement_since_match: float = 0.0
    last_observation_timestamp: Optional[str] = None  # ISO format
    observations_since_match: int = 0
    consecutive_stationary: int = 0
    total_observations_received: int = 0
    total_match_calls: int = 0
    last_trigger_reason: Optional[str] = None
    last_match_latency_ms: Optional[float] = None
    current_status: str = "WARMING_UP"
    version: int = 1  # For optimistic concurrency control
    generation: int = 1  # Incremented on reset to invalidate old requests
    seen_observation_ids: list = field(default_factory=list)  # For deduplication
    seen_payloads: dict = field(default_factory=dict)  # ID -> payload hash for conflict detection

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)

    @classmethod
    def from_json(cls, raw: str) -> "DriverTraceStateSnapshot":
        data = json.loads(raw)
        # Handle missing seen_payloads for old snapshots
        if 'seen_payloads' not in data:
            data['seen_payloads'] = {}
        return cls(**data)

    def to_observations_deque(self) -> deque[GPSObservation]:
        """Reconstruct the observations deque."""
        obs = [GPSObservation.from_dict(d) for d in self.observations]
        result = deque(maxlen=1000)
        result.extend(obs)
        return result

    def to_matched_state(self) -> Optional[MatchedState]:
        if self.last_matched_state:
            return MatchedState.from_dict(self.last_matched_state)
        return None

    def to_seen_ids_set(self) -> set:
        """Reconstruct the seen observation IDs set."""
        return set(self.seen_observation_ids)

    def to_seen_payloads_dict(self) -> dict:
        """Reconstruct the seen payloads dict."""
        return dict(self.seen_payloads)


class DriverStateRepository(ABC):
    """Abstract interface for driver state persistence."""

    @abstractmethod
    async def get(self, driver_id: str) -> Optional[DriverTraceStateSnapshot]:
        """Load driver state snapshot."""
        pass

    @abstractmethod
    async def save(self, snapshot: DriverTraceStateSnapshot) -> bool:
        """Save driver state snapshot. Returns True on success."""
        pass

    @abstractmethod
    async def save_with_expected_version(
        self, snapshot: DriverTraceStateSnapshot, expected_version: int
    ) -> tuple[bool, int]:
        """
        Conditional save: only save if current version matches expected_version.

        Returns:
            (success, actual_version): success=True if saved, actual_version is current version in store

        Use this for CAS (Compare-And-Swap) pattern to prevent lost updates.
        """
        pass

    @abstractmethod
    async def delete(self, driver_id: str) -> bool:
        """Delete driver state."""
        pass

    @abstractmethod
    async def list_drivers(self) -> list[str]:
        """List all active driver IDs."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if repository is healthy."""
        pass


class InMemoryDriverStateRepository(DriverStateRepository):
    """In-memory implementation for testing and single-instance use."""

    def __init__(self):
        self._states: dict[str, DriverTraceStateSnapshot] = {}

    async def get(self, driver_id: str) -> Optional[DriverTraceStateSnapshot]:
        return self._states.get(driver_id)

    async def save(self, snapshot: DriverTraceStateSnapshot) -> bool:
        current = self._states.get(snapshot.driver_id)
        if current is not None:
            # Increment version like Redis would
            snapshot.version = current.version + 1
        else:
            snapshot.version = 1
        self._states[snapshot.driver_id] = snapshot
        return True

    async def save_with_expected_version(
        self, snapshot: DriverTraceStateSnapshot, expected_version: int
    ) -> tuple[bool, int]:
        current = self._states.get(snapshot.driver_id)
        actual_version = current.version if current else 0

        if actual_version != expected_version:
            # Conflict - state changed since we read it
            return False, actual_version

        # Save with incremented version
        snapshot.version = expected_version + 1
        self._states[snapshot.driver_id] = snapshot
        return True, snapshot.version

    async def delete(self, driver_id: str) -> bool:
        if driver_id in self._states:
            del self._states[driver_id]
            return True
        return False

    async def list_drivers(self) -> list[str]:
        return list(self._states.keys())

    async def health_check(self) -> bool:
        return True

    async def get_or_create_local(self, driver_id: str):
        """
        Get or create driver state using the global in-memory store.

        This is used when InMemoryDriverStateRepository is the configured store.
        """
        from backend.app.services.realtime.state import get_state_store
        local = get_state_store()
        return local.get_or_create(driver_id)

    async def save_local(self, state: DriverTraceState) -> None:
        """Save state to the global in-memory store."""
        from backend.app.services.realtime.state import get_state_store
        local = get_state_store()
        local._states[state.driver_id] = state


class RedisDriverStateRepository(DriverStateRepository):
    """
    Redis-backed driver state repository.

    Key design:
    - One Redis key per driver: driver_state:{driver_id}
    - JSON serialization of DriverTraceStateSnapshot
    - Version-based optimistic locking for concurrent updates
    - TTL of 1 hour per driver (refreshed on access)
    """

    KEY_PREFIX = "driver_state:"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        driver_state_ttl: int = 3600,  # 1 hour
        max_drivers: int = 10000,
    ):
        self._redis_url = redis_url or settings.redis_url
        self._client: Optional[redis.Redis] = None
        self._driver_state_ttl = driver_state_ttl
        self._max_drivers = max_drivers

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, driver_id: str) -> str:
        return f"{self.KEY_PREFIX}{driver_id}"

    async def get(self, driver_id: str) -> Optional[DriverTraceStateSnapshot]:
        client = await self._get_client()
        raw = await client.get(self._key(driver_id))
        if raw is None:
            return None

        # Refresh TTL on access
        await client.expire(self._key(driver_id), self._driver_state_ttl)

        return DriverTraceStateSnapshot.from_json(raw)

    async def save(self, snapshot: DriverTraceStateSnapshot) -> bool:
        client = await self._get_client()
        key = self._key(snapshot.driver_id)

        # Use atomic Lua script for compare-and-swap to prevent lost updates.
        # The script reads the current version, increments it atomically, and saves.
        # This prevents two writers from both succeeding with the same version.
        lua_script = """
        local key = KEYS[1]
        local new_value = ARGV[1]
        local ttl = tonumber(ARGV[2])

        local current = redis.call('GET', key)
        local new_version = 1

        if current then
            local current_snapshot = cjson.decode(current)
            local current_version = current_snapshot.version or 0
            new_version = current_version + 1
        end

        -- Update version in the snapshot
        local updated = cjson.decode(new_value)
        updated.version = new_version

        -- Save with TTL
        redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
        return new_version
        """

        try:
            new_version = await client.eval(
                lua_script,
                1,
                key,
                snapshot.to_json(),
                self._driver_state_ttl,
            )
            return new_version is not None
        except Exception as e:
            # CRITICAL: Do NOT fallback to unchecked SET - this would bypass
            # the atomic version increment and potentially cause lost updates.
            # If Lua script fails, the save must fail so the caller can retry.
            logger.error(f"Redis Lua script failed, save aborted: {e}")
            raise

    async def save_with_expected_version(
        self, snapshot: DriverTraceStateSnapshot, expected_version: int
    ) -> tuple[bool, int]:
        """
        Conditional save using CAS (Compare-And-Swap).

        Only saves if the current version in Redis matches expected_version.
        This prevents lost updates when two requests try to update simultaneously.

        Returns:
            (success, actual_version): success=True if saved, actual_version is current version
        """
        client = await self._get_client()
        key = self._key(snapshot.driver_id)

        # Lua script for atomic CAS
        lua_script = """
        local key = KEYS[1]
        local new_value = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local expected_version = tonumber(ARGV[3])

        local current = redis.call('GET', key)

        if current then
            local current_snapshot = cjson.decode(current)
            local current_version = current_snapshot.version or 0

            -- Check if version matches
            if current_version ~= expected_version then
                -- Conflict: return current version
                return {0, current_version}
            end

            -- Version matches, save with incremented version
            local updated = cjson.decode(new_value)
            updated.version = current_version + 1
            redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
            return {1, current_version + 1}
        else
            -- No existing state, this is a new driver
            -- Only save if expected_version is 0 (meaning no state existed)
            if expected_version ~= 0 then
                return {0, 0}
            end

            local updated = cjson.decode(new_value)
            updated.version = 1
            redis.call('SET', key, cjson.encode(updated), 'EX', ttl)
            return {1, 1}
        end
        """

        try:
            result = await client.eval(
                lua_script,
                1,
                key,
                snapshot.to_json(),
                self._driver_state_ttl,
                expected_version,
            )
            success = bool(result[0])
            actual_version = int(result[1])
            return success, actual_version
        except Exception as e:
            logger.error(f"Redis CAS failed: {e}")
            raise

    async def delete(self, driver_id: str) -> bool:
        client = await self._get_client()
        result = await client.delete(self._key(driver_id))
        return result > 0

    async def list_drivers(self) -> list[str]:
        client = await self._get_client()
        pattern = f"{self.KEY_PREFIX}*"
        keys = []
        async for key in client.scan_iter(match=pattern, count=100):
            keys.append(key)
        prefix_len = len(self.KEY_PREFIX)
        return [k[prefix_len:] for k in keys]

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# Global repository instance
_driver_state_repo: Optional[DriverStateRepository] = None


def get_driver_state_repository() -> DriverStateRepository:
    """Get the global driver state repository instance."""
    global _driver_state_repo
    if _driver_state_repo is None:
        # Default to Redis in production, can be overridden for testing
        _driver_state_repo = RedisDriverStateRepository()
    return _driver_state_repo


def set_driver_state_repository(repo: DriverStateRepository):
    """Set the global driver state repository (for testing)."""
    global _driver_state_repo
    _driver_state_repo = repo


def reset_driver_state_repository():
    """Reset global repository (for testing)."""
    global _driver_state_repo
    _driver_state_repo = None
