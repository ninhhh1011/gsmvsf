"""
Realtime trigger policies for map matching.

Implements time-based, distance-based, and hybrid triggers.
Policy parameters are from docs/WEEK_1_REALTIME_POLICY.md
"""

from datetime import datetime
from typing import Protocol, Tuple

from backend.app.services.realtime.state import DriverTraceState


class TriggerPolicy(Protocol):
    """Protocol for trigger policies."""

    @property
    def name(self) -> str:
        """Policy name for logging."""
        ...

    def should_trigger(
        self,
        obs_timestamp: datetime,
        state: DriverTraceState,
    ) -> Tuple[bool, str]:
        """
        Check if map matching should be triggered.

        Args:
            obs_timestamp: Current observation timestamp
            state: Current driver trace state

        Returns:
            Tuple of (should_trigger, reason_string)
        """
        ...


class TimeTrigger:
    """Trigger after elapsed time since last match."""

    def __init__(self, elapsed_seconds: float = 10.0):
        self.elapsed_seconds = elapsed_seconds
        self._name = f"TimeTrigger({elapsed_seconds}s)"

    @property
    def name(self) -> str:
        return self._name

    def should_trigger(
        self,
        obs_timestamp: datetime,
        state: DriverTraceState,
    ) -> Tuple[bool, str]:
        if state.last_match_time is None:
            return True, "INITIAL"

        elapsed = (obs_timestamp - state.last_match_time).total_seconds()
        if elapsed >= self.elapsed_seconds:
            return True, f"TIME({elapsed:.1f}s>={self.elapsed_seconds}s)"

        return False, f"NOT_TIME({elapsed:.1f}s<{self.elapsed_seconds}s)"


class DistanceTrigger:
    """Trigger after distance traveled since last match."""

    def __init__(self, distance_meters: float = 50.0):
        self.distance_meters = distance_meters
        self._name = f"DistanceTrigger({distance_meters}m)"

    @property
    def name(self) -> str:
        return self._name

    def should_trigger(
        self,
        obs_timestamp: datetime,
        state: DriverTraceState,
    ) -> Tuple[bool, str]:
        if state.movement_since_match < self.distance_meters:
            return False, f"NOT_DIST({state.movement_since_match:.0f}m<{self.distance_meters}m)"

        return True, f"DIST({state.movement_since_match:.0f}m>={self.distance_meters}m)"


class HybridTrigger:
    """
    Trigger on time OR distance (whichever first).

    Selected baseline policy from Phase B benchmark.
    """

    def __init__(
        self,
        elapsed_seconds: float = 10.0,
        distance_meters: float = 50.0,
    ):
        self.elapsed_seconds = elapsed_seconds
        self.distance_meters = distance_meters
        self._name = f"HybridTrigger({elapsed_seconds}s/{distance_meters}m)"

    @property
    def name(self) -> str:
        return self._name

    def should_trigger(
        self,
        obs_timestamp: datetime,
        state: DriverTraceState,
    ) -> Tuple[bool, str]:
        elapsed = 0.0

        # Check time condition
        if state.last_match_time is not None:
            elapsed = (obs_timestamp - state.last_match_time).total_seconds()
            if elapsed >= self.elapsed_seconds:
                return True, f"TIME({elapsed:.1f}s>={self.elapsed_seconds}s)"

        # Check distance condition
        if state.movement_since_match >= self.distance_meters:
            return True, f"DIST({state.movement_since_match:.0f}m>={self.distance_meters}m)"

        return False, f"NO_TRIGGER(elapsed={elapsed:.1f}s, dist={state.movement_since_match:.0f}m)"


# Default policy - selected from Phase B benchmark
def get_default_policy() -> HybridTrigger:
    """Get the default trigger policy."""
    return HybridTrigger(elapsed_seconds=10.0, distance_meters=50.0)
