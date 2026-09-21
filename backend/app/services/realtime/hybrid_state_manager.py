"""
Hybrid driver state manager.

Combines local in-memory state with optional Redis persistence for cross-process sharing.
The local store serves as a read-cache; Redis provides shared state.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from backend.app.services.realtime.state import (
    DriverTraceState,
    GPSObservation as StateGPSObservation,
    MatchedState as StateMatchedState,
    DriverStateStore,
    get_state_store,
)
from backend.app.services.realtime.driver_state_repository import (
    DriverStateRepository,
    RedisDriverStateRepository,
    DriverTraceStateSnapshot,
    GPSObservation,
    MatchedState,
    get_driver_state_repository,
)


def snapshot_to_trace_state(snapshot: DriverTraceStateSnapshot) -> DriverTraceState:
    """
    Convert a Redis snapshot to a DriverTraceState object.

    This reconstructs the full runtime state including the observations deque.
    """
    state = DriverTraceState(driver_id=snapshot.driver_id)
    state.observations = snapshot.to_observations_deque()
    state.movement_since_match = snapshot.movement_since_match
    state.observations_since_match = snapshot.observations_since_match
    state.consecutive_stationary = snapshot.consecutive_stationary
    state.total_observations_received = snapshot.total_observations_received
    state.total_match_calls = snapshot.total_match_calls
    state.last_trigger_reason = snapshot.last_trigger_reason
    state.last_match_latency_ms = snapshot.last_match_latency_ms
    state.current_status = snapshot.current_status

    if snapshot.last_match_time:
        state.last_match_time = datetime.fromisoformat(snapshot.last_match_time)

    state.last_matched_state = snapshot.to_matched_state()

    if snapshot.last_observation_timestamp:
        state.last_observation_timestamp = datetime.fromisoformat(snapshot.last_observation_timestamp)

    return state


def trace_state_to_snapshot(state: DriverTraceState, version: int = 1) -> DriverTraceStateSnapshot:
    """Convert a DriverTraceState to a serializable snapshot."""
    return DriverTraceStateSnapshot(
        driver_id=state.driver_id,
        observations=[obs.to_dict() for obs in state.observations],
        last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
        last_matched_state=state.last_matched_state.to_dict() if state.last_matched_state else None,
        movement_since_match=state.movement_since_match,
        last_observation_timestamp=state.last_observation_timestamp.isoformat() if state.last_observation_timestamp else None,
        observations_since_match=state.observations_since_match,
        consecutive_stationary=state.consecutive_stationary,
        total_observations_received=state.total_observations_received,
        total_match_calls=state.total_match_calls,
        last_trigger_reason=state.last_trigger_reason,
        last_match_latency_ms=state.last_match_latency_ms,
        current_status=state.current_status,
        version=version,
    )


class HybridDriverStateManager:
    """
    Hybrid driver state manager combining local cache with Redis shared state.

    Read path:
    1. Check local in-memory store (fast path)
    2. If not in local, try Redis (cross-process)
    3. If not in Redis, create new local state

    Write path:
    1. Update local state
    2. Persist to Redis (shared state)
    """

    def __init__(
        self,
        local_store: Optional[DriverStateStore] = None,
        repository: Optional[DriverStateRepository] = None,
        persist_on_write: bool = True,
    ):
        self._local = local_store
        self._repo = repository
        self._persist_on_write = persist_on_write

    def _get_local(self) -> DriverStateStore:
        # Always get the global store - ensures test resets work
        return get_state_store()

    def _get_repo(self) -> Optional[DriverStateRepository]:
        if self._repo is None:
            try:
                self._repo = get_driver_state_repository()
            except Exception:
                pass
        return self._repo

    async def get_or_create(self, driver_id: str) -> tuple[DriverTraceState, bool]:
        """
        Get or create driver state.

        Returns:
            (state, was_loaded_from_redis)

        If Redis is unavailable, falls back to local-only state.
        """
        local = self._get_local()

        # Check local first
        local_state = local.get(driver_id)
        if local_state is not None:
            return local_state, False

        # Try Redis
        repo = self._get_repo()
        if repo is not None:
            try:
                snapshot = await repo.get(driver_id)
                if snapshot is not None:
                    # Reconstruct from Redis
                    state = snapshot_to_trace_state(snapshot)
                    # Cache in local
                    local._states[driver_id] = state
                    return state, True
            except Exception:
                # Redis unavailable, continue with local-only
                pass

        # Create new local state
        return local.get_or_create(driver_id), False

    async def save(self, state: DriverTraceState) -> bool:
        """
        Persist state to Redis if repository is configured.

        Returns True if persisted successfully (or no persistence configured).
        Returns False if persistence failed (but state is still valid locally).
        """
        if not self._persist_on_write:
            return True

        repo = self._get_repo()
        if repo is None:
            return True

        try:
            # Get current version for optimistic locking
            current = await repo.get(state.driver_id)
            version = (current.version + 1) if current else 1

            snapshot = trace_state_to_snapshot(state, version=version)
            return await repo.save(snapshot)
        except Exception:
            # Log but don't fail - local state is still valid
            return False

    async def delete(self, driver_id: str) -> bool:
        """Delete driver state from local and Redis."""
        local = self._get_local()
        local.remove(driver_id)

        repo = self._get_repo()
        if repo is not None:
            try:
                await repo.delete(driver_id)
            except Exception:
                pass

        return True

    async def health_check(self) -> bool:
        """Check if the driver state infrastructure is healthy."""
        repo = self._get_repo()
        if repo is None:
            return True  # Local-only is healthy
        return await repo.health_check()


# Global hybrid manager instance
_hybrid_manager: Optional[HybridDriverStateManager] = None


def get_hybrid_manager() -> HybridDriverStateManager:
    """Get the global hybrid driver state manager."""
    global _hybrid_manager
    if _hybrid_manager is None:
        _hybrid_manager = HybridDriverStateManager()
    return _hybrid_manager


def set_hybrid_manager(manager: HybridDriverStateManager):
    """Set the global hybrid manager (for testing)."""
    global _hybrid_manager
    _hybrid_manager = manager


def reset_hybrid_manager():
    """Reset global hybrid manager (for testing)."""
    global _hybrid_manager
    _hybrid_manager = None
