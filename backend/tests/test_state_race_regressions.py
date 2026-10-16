from datetime import datetime
import pytest
from backend.app.api.v1.realtime import _add_observation_with_cas
from backend.app.services.realtime.driver_state_manager import DriverStateManager, DriverStateUnavailableError
from backend.app.services.realtime.driver_state_repository import InMemoryDriverStateRepository
from backend.app.services.realtime.state import GPSObservation

@pytest.mark.asyncio
async def test_stale_full_state_cannot_erase_new_observation():
    manager = DriverStateManager.for_testing()
    first, *_ = await _add_observation_with_cas('race', GPSObservation('a','race',datetime(2026,1,1),21,105),manager)
    second, *_ = await _add_observation_with_cas('race', GPSObservation('b','race',datetime(2026,1,1,0,0,1),21,105),manager)
    with pytest.raises(DriverStateUnavailableError):
        await manager.save_with_retry(first)
    assert [o.observation_id for o in (await manager.get_or_create('race')).observations] == ['a','b']

@pytest.mark.asyncio
async def test_reset_withholds_old_match_commit():
    manager = DriverStateManager.for_testing()
    stale, *_ = await _add_observation_with_cas('race', GPSObservation('a','race',datetime(2026,1,1),21,105),manager)
    await manager.delete('race')
    with pytest.raises(DriverStateUnavailableError):
        await manager.save_with_retry(stale)
    current = await manager.get_or_create('race')
    assert not current.observations
    assert current.generation > stale.generation

@pytest.mark.asyncio
async def test_batch_timestamp_order_is_chronological():
    from unittest.mock import AsyncMock
    from backend.app.services.map_matching.models import GPSObservation as BatchObservation, MapMatchRequest
    from backend.app.services.map_matching.service import MapMatchingService
    engine = AsyncMock()
    engine.match.side_effect = RuntimeError('stop after input')
    observations = [BatchObservation(observation_id=str(i),trajectory_id='x',trip_id='external',
        timestamp=stamp, latitude=21+i*.001,longitude=105) for i,stamp in enumerate(
        ['2026-01-01T00:01:00Z','2026-01-01T07:00:00+07:00'])]
    with pytest.raises(RuntimeError):
        await MapMatchingService(engine).match_trajectory(MapMatchRequest(trajectory_id='x',trip_id='external',vehicle_category='EV_CAR',observations=observations))
    assert engine.match.call_args.args[0] == [(105,21.001),(105,21)]

def test_batch_rejects_malformed_timestamp():
    from pydantic import ValidationError
    from backend.app.services.map_matching.models import GPSObservation as BatchObservation
    with pytest.raises(ValidationError):
        BatchObservation(observation_id='x',trajectory_id='x',trip_id='x',timestamp='not-time',latitude=21,longitude=105)

@pytest.mark.asyncio
async def test_ingest_replays_mutation_on_the_snapshot_it_read():
    from backend.app.services.realtime.driver_state_manager import trace_state_to_snapshot, snapshot_to_trace_state
    repo = InMemoryDriverStateRepository()
    manager = DriverStateManager(repo)
    await _add_observation_with_cas('race',GPSObservation('initial','race',datetime(2026,1,1),21,105),manager)
    original_get = repo.get
    first = True
    async def competing_read(driver):
        nonlocal first
        snapshot = await original_get(driver)
        if first:
            first = False
            competing = snapshot_to_trace_state(snapshot)
            competing.add_observation(GPSObservation('b','race',datetime(2026,1,1,0,0,1),21,105))
            await repo.save_with_expected_version(trace_state_to_snapshot(competing),snapshot.version,snapshot.generation)
        return snapshot
    repo.get = competing_read
    state, *_ = await _add_observation_with_cas('race',GPSObservation('a','race',datetime(2026,1,1,0,0,2),21,105),manager)
    assert [o.observation_id for o in state.observations] == ['initial','b','a']

@pytest.mark.asyncio
async def test_shared_location_uses_other_manager_and_reset():
    from backend.app.services.realtime.location import resolve_shared_current_location
    repo = InMemoryDriverStateRepository()
    writer, reader = DriverStateManager(repo),DriverStateManager(repo)
    await _add_observation_with_cas('race',GPSObservation('a','race',datetime(2026,1,1),21,105),writer)
    location = await resolve_shared_current_location('race',None,None,None,datetime(2026,1,2),reader)
    assert location.source == 'RAW_GPS_FALLBACK'
    assert location.latitude == 21
    await writer.delete('race')
    assert (await resolve_shared_current_location('race',None,None,None,datetime(2026,1,2),reader)).source == 'LOCATION_UNAVAILABLE'

@pytest.mark.asyncio
async def test_explicit_location_skips_unavailable_store():
    from unittest.mock import AsyncMock
    from backend.app.services.realtime.location import resolve_shared_current_location
    manager = AsyncMock()
    manager.get_or_create.side_effect = DriverStateUnavailableError('down')
    explicit = await resolve_shared_current_location('race',0,0,None,datetime(2026,1,2),manager)
    assert explicit.source == 'EXPLICIT' and explicit.latitude == 0
    with pytest.raises(DriverStateUnavailableError):
        await resolve_shared_current_location('race',None,None,None,datetime(2026,1,2),manager)

@pytest.mark.asyncio
async def test_generation_cas_blocks_same_version_aba():
    from backend.app.services.realtime.driver_state_manager import trace_state_to_snapshot
    from backend.app.services.realtime.state import DriverTraceState
    repo = InMemoryDriverStateRepository()
    old = DriverTraceState('race')
    await repo.save_with_expected_version(trace_state_to_snapshot(old),0,1)
    await repo.delete('race')
    fresh = DriverTraceState('race')
    fresh.generation = 2
    await repo.save_with_expected_version(trace_state_to_snapshot(fresh),0)
    success,_ = await repo.save_with_expected_version(trace_state_to_snapshot(old),1,1)
    assert not success

@pytest.mark.asyncio
async def test_reset_store_read_failure_is_explicit_unavailable():
    from unittest.mock import AsyncMock
    from backend.app.services.realtime.driver_state_repository import RedisDriverStateRepository
    repo = AsyncMock(spec=RedisDriverStateRepository)
    repo.get.side_effect = ConnectionError('down')
    with pytest.raises(DriverStateUnavailableError):
        await DriverStateManager(repo).delete('race')

@pytest.mark.asyncio
async def test_missing_shared_manager_is_explicit_unavailable():
    from backend.app.services.realtime.location import resolve_shared_current_location
    with pytest.raises(DriverStateUnavailableError):
        await resolve_shared_current_location('race',None,None,None,datetime(2026,1,2),None)
