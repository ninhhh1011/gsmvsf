import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from backend.tests.test_week4_database import repository, traffic
from backend.app.services.snapshots.models import StateError


@pytest_asyncio.fixture
async def cache():
    from backend.app.services.snapshots.resolver import SnapshotCache
    client = Redis.from_url('redis://127.0.0.1:6379', socket_timeout=.2, socket_connect_timeout=.2)
    prefix = 'week4-test:' + uuid4().hex + ':'
    result = SnapshotCache(client, ttl_s=60, prefix=prefix)
    try:
        assert await client.ping()
        yield result
    finally:
        keys = [key async for key in client.scan_iter(prefix + '*')]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.mark.asyncio
async def test_cache_miss_hit_history_and_atomic_old_write(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    old = traffic()
    new = traffic(timestamp=old.timestamp + timedelta(minutes=30))
    await repository.ingest_many([old, new])
    resolver = SnapshotResolver(repository, cache)
    view = await resolver.resolve([old.key], new.timestamp)
    assert view[old.key].snapshot == new
    assert resolver.metrics['cache_miss'] == 1
    assert (await resolver.resolve([old.key], new.timestamp))[old.key].snapshot == new
    assert resolver.metrics['cache_hit'] == 1
    await asyncio.gather(*(cache.put(s) for s in [new, old] * 5))
    assert (await cache.get_many([old.key]))[old.key] == new
    assert (await resolver.resolve([old.key], old.timestamp))[old.key].snapshot == old
    assert (await cache.get_many([old.key]))[old.key] == new


@pytest.mark.asyncio
async def test_committed_new_state_is_seen_after_failed_cache_update(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    old = traffic()
    await repository.ingest(old)
    await cache.put(old)
    new = traffic(timestamp=old.timestamp + timedelta(seconds=1))
    await repository.ingest(new)  # Deliberately omit cache update, simulating failed dual write.
    resolver = SnapshotResolver(repository, cache)
    assert (await resolver.resolve([old.key], new.timestamp))[old.key].snapshot == new
    assert resolver.metrics['db_fallback'] == 1
    # Valid JSON modified under the same logical identity must fail the content-ID check.
    value = json.loads(await cache.client.get(cache.key(old.key)))
    value['payload']['delay_factor'] = 8
    await cache.client.set(cache.key(old.key), json.dumps(value))
    assert (await resolver.resolve([old.key], new.timestamp))[old.key].snapshot == new


@pytest.mark.asyncio
async def test_redis_down_falls_back_but_database_down_is_explicit(repository):
    from backend.app.services.snapshots.resolver import SnapshotCache, SnapshotResolver
    client = Redis.from_url('redis://127.0.0.1:1', socket_timeout=.05, socket_connect_timeout=.05)
    try:
        snap = traffic()
        await repository.ingest(snap)
        resolver = SnapshotResolver(repository, SnapshotCache(client))
        assert (await resolver.resolve([snap.key], snap.timestamp))[snap.key].snapshot == snap
        assert resolver.metrics['cache_error'] > 0
        await repository.pool.close()
        with pytest.raises(StateError) as exc:
            await resolver.resolve([snap.key], snap.timestamp)
        assert exc.value.status == 503
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_missing_stale_and_corrupt_cache(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    snap = traffic()
    await repository.ingest(snap)
    await cache.client.set(cache.key(snap.key), 'bad json')
    resolver = SnapshotResolver(repository, cache)
    result = await resolver.resolve([snap.key, 'station:absent'], snap.timestamp + timedelta(hours=1))
    assert result[snap.key].freshness == 'STALE'
    assert result['station:absent'].freshness == 'MISSING'
    assert result[snap.key].snapshot_age_s == 3600


@pytest.mark.asyncio
async def test_resolution_pins_all_entities_before_concurrent_ingestion(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    from backend.tests.test_week4_database import station
    first, state = traffic(), station()
    await repository.ingest_many([first, state])
    timestamp = first.timestamp + timedelta(seconds=1)
    new_traffic = traffic(timestamp=timestamp)
    new_station = station(timestamp=timestamp, operating_status='OFFLINE')
    original = cache.get_many

    async def ingest_during_cache_read(keys):
        await repository.ingest_many([new_traffic, new_station])
        return await original(keys)

    cache.get_many = ingest_during_cache_read
    resolver = SnapshotResolver(repository, cache)
    result = await resolver.resolve([first.key, state.key], timestamp)
    assert result[first.key].snapshot == first
    assert result[state.key].snapshot == state
    cache.get_many = original
    result = await resolver.resolve([first.key, state.key], timestamp)
    assert result[first.key].snapshot == new_traffic
    assert result[state.key].snapshot == new_station


@pytest.mark.asyncio
async def test_warm_healthy_cache_does_not_mask_database_failure(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    snap = traffic()
    await repository.ingest(snap)
    await cache.put(snap)
    assert (await cache.get_many([snap.key]))[snap.key] == snap
    await repository.pool.close()
    with pytest.raises(StateError) as exc:
        await SnapshotResolver(repository, cache).resolve([snap.key], snap.timestamp)
    assert exc.value.status == 503


@pytest.mark.asyncio
async def test_empty_latest_cache_never_receives_older_database_state(repository, cache):
    from backend.app.services.snapshots.resolver import SnapshotResolver
    from backend.app.services.snapshots.ingestion import IngestionService
    old = traffic()
    new = traffic(timestamp=old.timestamp + timedelta(hours=1))
    await repository.ingest(new)
    await IngestionService(repository, cache=cache).ingest(old)
    assert (await cache.get_many([old.key]))[old.key] == new
    await cache.client.delete(cache.key(old.key))
    assert (await SnapshotResolver(repository, cache).resolve([old.key], old.timestamp))[old.key].snapshot == old
    assert (await cache.get_many([old.key]))[old.key] == new
