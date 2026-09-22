"""Tests for driver state manager with split-brain prevention."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.realtime.driver_state_manager import (
    DriverStateManager,
    DriverStateUnavailableError,
    snapshot_to_trace_state,
    trace_state_to_snapshot,
)
from backend.app.services.realtime.driver_state_repository import (
    InMemoryDriverStateRepository,
    RedisDriverStateRepository,
    DriverTraceStateSnapshot,
)
from backend.app.services.realtime.state import DriverTraceState, reset_state_store


@pytest.mark.asyncio
async def test_local_manager_allows_local_operations():
    """InMemory manager should work without Redis."""
    manager = DriverStateManager.for_local()

    # Should work without Redis
    state = await manager.get_or_create("D001")
    assert state.driver_id == "D001"

    # Save should work
    await manager.save(state)


@pytest.mark.asyncio
async def test_production_manager_requires_redis():
    """Production manager with failing Redis should raise error."""
    # Create a mock Redis repo that fails health check
    mock_repo = AsyncMock(spec=RedisDriverStateRepository)
    mock_repo.health_check = AsyncMock(return_value=False)

    manager = DriverStateManager(repository=mock_repo)

    with pytest.raises(DriverStateUnavailableError) as exc_info:
        await manager.get_or_create("D001")

    assert "not available" in str(exc_info.value)


@pytest.mark.asyncio
async def test_production_manager_with_healthy_redis():
    """Production manager with healthy Redis should work."""
    mock_repo = AsyncMock(spec=RedisDriverStateRepository)
    mock_repo.health_check = AsyncMock(return_value=True)
    mock_repo.get = AsyncMock(return_value=None)  # No existing state

    manager = DriverStateManager(repository=mock_repo)

    # Should work
    state = await manager.get_or_create("D001")
    assert state.driver_id == "D001"

    # Save should work
    await manager.save(state)


@pytest.mark.asyncio
async def test_production_manager_save_requires_redis():
    """Production manager save should fail when Redis unavailable."""
    mock_repo = AsyncMock(spec=RedisDriverStateRepository)
    mock_repo.health_check = AsyncMock(return_value=False)

    manager = DriverStateManager(repository=mock_repo)
    state = DriverTraceState(driver_id="D001")

    with pytest.raises(DriverStateUnavailableError):
        await manager.save(state)


@pytest.mark.asyncio
async def test_snapshot_conversion_roundtrip():
    """Verify state can be converted to/from snapshot."""
    state = DriverTraceState(driver_id="D001")
    state.current_status = "MATCHED"
    state.movement_since_match = 100.0

    snapshot = trace_state_to_snapshot(state, version=1)
    assert snapshot.driver_id == "D001"
    assert snapshot.current_status == "MATCHED"
    assert snapshot.movement_since_match == 100.0

    restored = snapshot_to_trace_state(snapshot)
    assert restored.driver_id == "D001"
    assert restored.current_status == "MATCHED"
    assert restored.movement_since_match == 100.0


@pytest.mark.asyncio
async def test_health_check_local():
    """Local manager should always be healthy."""
    manager = DriverStateManager.for_local()
    assert await manager.health_check() is True


@pytest.mark.asyncio
async def test_health_check_redis_healthy():
    """Manager with healthy Redis should report healthy."""
    mock_repo = AsyncMock(spec=RedisDriverStateRepository)
    mock_repo.health_check = AsyncMock(return_value=True)

    manager = DriverStateManager(repository=mock_repo)
    assert await manager.health_check() is True


@pytest.mark.asyncio
async def test_health_check_redis_unhealthy():
    """Manager with unhealthy Redis should report unhealthy."""
    mock_repo = AsyncMock(spec=RedisDriverStateRepository)
    mock_repo.health_check = AsyncMock(return_value=False)

    manager = DriverStateManager(repository=mock_repo)
    assert await manager.health_check() is False
