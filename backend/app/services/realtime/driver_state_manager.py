"""
Driver state manager for production use.

In production, driver state is authoritative in Redis.
In-memory store is only used for:
- Unit tests with explicit local-only configuration
- Local development with explicit local-only configuration

In production (Redis configured), the system does NOT fall back to local state
when Redis is unavailable. This prevents split-brain scenarios where different
API instances have different views of the same driver's state.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from datetime import datetime

from backend.app.services.realtime.driver_state_repository import (
    DriverStateRepository,
    DriverTraceStateSnapshot,
    InMemoryDriverStateRepository,
    RedisDriverStateRepository,
)
from backend.app.services.realtime.state import (
    DriverTraceState,
    get_state_store,
)

logger = logging.getLogger(__name__)


def snapshot_to_trace_state(snapshot: DriverTraceStateSnapshot) -> DriverTraceState:
    """
    Convert a Redis snapshot to a DriverTraceState object.

    This reconstructs the full runtime state including the observations deque.
    """
    state = DriverTraceState(driver_id=snapshot.driver_id)
    state._version = snapshot.version
    state._read_generation = snapshot.generation
    state.observations = snapshot.to_observations_deque()
    state.seen_observation_ids = snapshot.to_seen_ids_set()
    state.seen_payloads = snapshot.to_seen_payloads_dict()
    state.movement_since_match = snapshot.movement_since_match
    state.observations_since_match = snapshot.observations_since_match
    state.consecutive_stationary = snapshot.consecutive_stationary
    state.total_observations_received = snapshot.total_observations_received
    state.total_match_calls = snapshot.total_match_calls
    state.last_trigger_reason = snapshot.last_trigger_reason
    state.last_match_latency_ms = snapshot.last_match_latency_ms
    state.current_status = snapshot.current_status
    state.generation = getattr(snapshot, 'generation', 1)  # Default to 1 for old snapshots

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
        generation=state.generation,
        seen_observation_ids=list(state.seen_observation_ids),
        seen_payloads=state.seen_payloads,
    )


class DriverStateError(Exception):
    """Base exception for driver state operations."""


class DriverStateUnavailableError(DriverStateError):
    """Raised when the shared driver state store is unavailable."""


class DriverStateConflictError(DriverStateUnavailableError):
    """The source snapshot changed while work was in flight."""


class DriverStateManager:
    """
    Driver state manager for production use.

    This class manages driver state with the following policies:

    1. Redis (when configured): Authoritative shared state store
       - Reads come from Redis
       - Writes go to Redis
       - NO local fallback when Redis is unavailable

    2. Local-only (explicit configuration only):
       - Used for unit tests
       - Used for local development without Redis
       - NOT an automatic fallback in production

    Split-brain prevention:
    - When Redis is the configured store, we require it to be available
    - We do NOT fall back to local in-memory state
    - This ensures all API instances see the same driver state
    """

    def __init__(
        self,
        repository: DriverStateRepository | None = None,
    ):
        self._repository = repository

    @classmethod
    def for_production(cls) -> DriverStateManager:
        """Create a manager for production use with Redis."""
        return cls(repository=RedisDriverStateRepository())

    @classmethod
    def for_local(cls) -> DriverStateManager:
        """Create a manager for local development without Redis."""
        return cls(repository=InMemoryDriverStateRepository())

    @classmethod
    def for_testing(cls) -> DriverStateManager:
        """Create a manager for unit testing."""
        return cls(repository=InMemoryDriverStateRepository())

    def _get_repo(self) -> DriverStateRepository | None:
        """Get the configured repository."""
        return self._repository

    def _is_redis(self) -> bool:
        """Check if the configured repository is Redis."""
        repo = self._get_repo()
        return repo is not None and not isinstance(repo, InMemoryDriverStateRepository)

    async def get_or_create(self, driver_id: str) -> DriverTraceState:
        """
        Get or create driver state.

        In production (Redis configured):
        - Reads from Redis
        - If driver not in Redis, creates new state and saves to Redis
        - Raises DriverStateUnavailableError if Redis is unavailable

        In local mode (InMemory):
        - Uses in-memory store only
        - No Redis dependency

        Returns:
            DriverTraceState for the driver

        Raises:
            DriverStateUnavailableError: When Redis is required but unavailable
        """
        repo = self._get_repo()

        if repo is None:
            # No repository configured - use local only
            logger.warning("No driver state repository configured, using local-only mode")
            local = get_state_store()
            return local.get_or_create(driver_id)

        # Redis mode (production) - require Redis to be available
        try:
            if not await repo.health_check():
                raise DriverStateUnavailableError(
                    "Redis driver state store is not available. "
                    "Cannot serve stateful driver operations without shared state."
                )
        except Exception as e:
            raise DriverStateUnavailableError(
                f"Failed to check Redis driver state store: {e}"
            ) from e

        # Load from Redis
        try:
            snapshot = await repo.get(driver_id)
            if snapshot is not None:
                return snapshot_to_trace_state(snapshot)
        except DriverStateUnavailableError:
            raise
        except Exception as e:
            raise DriverStateUnavailableError(
                f"Failed to load driver state from Redis: {e}"
            ) from e

        # Create new state
        state = DriverTraceState(driver_id=driver_id)
        return state

    async def save(self, state: DriverTraceState) -> None:
        await self.save_with_retry(state)

    async def save_with_retry(self, state: DriverTraceState, max_retries: int = 3) -> None:
        """Commit only the snapshot read by this caller; stale full states cannot be rebased."""
        repo = self._get_repo()
        if repo is None:
            return
        try:
            if not await repo.health_check():
                raise DriverStateUnavailableError("Driver state store is not available")
            version = getattr(state, '_version', 0)
            success, actual = await repo.save_with_expected_version(
                trace_state_to_snapshot(state), version, getattr(state, '_read_generation', state.generation))
            if not success:
                raise DriverStateConflictError("Driver state changed; stale result withheld")
            state._version = actual
            state._read_generation = state.generation
        except DriverStateUnavailableError:
            raise
        except Exception as exc:
            raise DriverStateUnavailableError(f"Failed to persist driver state: {exc}") from exc

    async def update_with_cas(
        self,
        driver_id: str,
        update_fn,  # async def(state: DriverTraceState) -> DriverTraceState
        max_retries: int = 3,
    ) -> tuple[DriverTraceState, bool]:
        """
        Atomic read-modify-write using CAS.

        This method:
        1. Reads current state from Redis
        2. Applies update_fn to the state
        3. Attempts CAS save
        4. On conflict, re-reads and retries

        This prevents lost updates in concurrent scenarios.

        Args:
            driver_id: Driver ID to update
            update_fn: Async function that takes state and returns modified state
            max_retries: Maximum retry attempts on conflict

        Returns:
            (final_state, was_successful): The final state and whether save succeeded

        Raises:
            DriverStateUnavailableError: When Redis is unavailable or retries exhausted
        """
        repo = self._get_repo()

        if repo is None:
            local = get_state_store()
            state = local.get_or_create(driver_id)
            state = await update_fn(state)
            local._states[driver_id] = state
            return state, True

        # Redis mode
        for attempt in range(max_retries):
            # Read current state
            try:
                current = await repo.get(driver_id)
            except Exception as exc:
                raise DriverStateUnavailableError(f"Failed to read driver state: {exc}") from exc
            if current is not None:
                state = snapshot_to_trace_state(current)
                expected_version = current.version
            else:
                state = DriverTraceState(driver_id=driver_id)
                expected_version = 0

            # Apply update
            state = await update_fn(state)

            # Prepare snapshot with version
            snapshot = trace_state_to_snapshot(state, version=expected_version + 1)

            # Attempt CAS
            try:
                success, actual_version = await repo.save_with_expected_version(
                    snapshot, expected_version, current.generation if current else 1
                )

                if success:
                    logger.debug(
                        f"Driver {driver_id} updated at version {actual_version}"
                    )
                    state._version = actual_version
                    state._read_generation = state.generation
                    return state, True
                else:
                    logger.debug(
                        f"Driver {driver_id} CAS conflict: expected {expected_version}, "
                        f"actual {actual_version}, retry {attempt + 1}/{max_retries}"
                    )
                    # Conflict - loop will retry

            except DriverStateUnavailableError:
                raise
            except Exception as e:
                raise DriverStateUnavailableError(
                    f"Failed to update driver state: {e}"
                ) from e

        # All retries exhausted
        raise DriverStateUnavailableError(
            f"Failed to update driver {driver_id} after {max_retries} retries due to conflicts"
        )

    async def delete(self, driver_id: str) -> None:
        """
        Delete driver state.

        In Redis mode, we create a fresh state with incremented generation
        instead of deleting. This prevents old requests (that started before
        reset) from resurrecting state if they complete after reset.
        """
        repo = self._get_repo()

        if repo is None:
            local = get_state_store()
            local.remove(driver_id)
            return

        async def reset(state):
            fresh = DriverTraceState(driver_id=driver_id)
            fresh.generation = state.generation + 1
            return fresh
        await self.update_with_cas(driver_id, reset)

    async def health_check(self) -> bool:
        """
        Check if the driver state store is healthy.

        Returns True if:
        - No repository configured (local-only mode)
        - Repository is InMemory (always healthy)
        - Redis repository is reachable

        Returns False if Redis is not reachable.
        """
        repo = self._get_repo()
        if repo is None:
            return True
        return await repo.health_check()

    async def list_drivers(self) -> list[str]:
        """List all active driver IDs."""
        repo = self._get_repo()

        if repo is None:
            local = get_state_store()
            return local.list_drivers()

        if isinstance(repo, InMemoryDriverStateRepository):
            return await repo.list_drivers()

        # Redis mode
        return await repo.list_drivers()


_test_manager: ContextVar[DriverStateManager | None] = ContextVar('test_driver_state_manager', default=None)


def set_driver_state_manager(manager: DriverStateManager) -> None:
    _test_manager.set(manager)


def reset_driver_state_manager() -> None:
    _test_manager.set(None)


