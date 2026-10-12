from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

from backend.app.services.snapshots.repository import SnapshotRepository
from backend.tests.test_week4_database import repository, traffic


@pytest.mark.asyncio
async def test_congestion_uses_indexed_entity_head_before_filter():
    captured = []
    class Connection:
        async def fetch(self, query, *args):
            captured.append((query, args))
            return []
    class Repository(SnapshotRepository):
        @asynccontextmanager
        async def connection(self):
            yield Connection()
    as_of = traffic().timestamp
    await Repository(None).get_congested_polygons(as_of=as_of)
    query, parameters = captured[0]
    assert 'LATERAL' in query
    assert 'entity_id = e.entity_id' in query
    assert 'timestamp <= $3' in query
    assert parameters == (1.6, 5, as_of)


@pytest.mark.asyncio
async def test_latest_clear_and_future_congestion_do_not_leak(repository):
    old = traffic()
    clear = traffic(timestamp=old.timestamp + timedelta(minutes=1), delay_factor=1)
    future = traffic(timestamp=old.timestamp + timedelta(minutes=2), delay_factor=4)
    async with repository.connection() as connection:
        await connection.execute('CREATE TABLE road_segments (segment_id text PRIMARY KEY, geom geometry)')
        await connection.execute("INSERT INTO road_segments VALUES ($1,ST_GeomFromText('LINESTRING(105 21,105.01 21)',4326))", old.entity_id)
    await repository.ingest_many([old, clear, future])
    assert len(await repository.get_congested_polygons(as_of=old.timestamp)) == 1
    assert await repository.get_congested_polygons(as_of=clear.timestamp) == []
    assert len(await repository.get_congested_polygons(as_of=future.timestamp)) == 1
