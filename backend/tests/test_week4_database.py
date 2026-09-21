"""Required real PostgreSQL checks; each test owns an isolated schema."""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio

from backend.app.services.snapshots.models import StateError, StationStateSnapshot, TrafficSnapshot


@pytest_asyncio.fixture
async def repository():
    from backend.app.services.snapshots.repository import SnapshotRepository
    dsn = os.environ.get('WEEK4_TEST_DATABASE_URL',
                         'postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation')
    schema = 'week4_test_' + uuid4().hex
    connection = await asyncpg.connect(dsn, timeout=5)
    await connection.execute(f'CREATE SCHEMA {schema}')
    pool = None
    try:
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5,
                                        server_settings={'search_path': f'{schema},public'})
        repo = SnapshotRepository(pool)
        await repo.setup()
        await repo.setup()
        assert await pool.fetchval('SELECT count(*) FROM state_snapshots') == 0
        yield repo
    finally:
        if pool is not None:
            await pool.close()
        assert schema.startswith('week4_test_') and schema[11:].isalnum()
        await connection.execute(f'DROP SCHEMA {schema} CASCADE')
        await connection.close()


def traffic(**changes):
    return TrafficSnapshot(**(dict(entity_id='602290106_14_F',
        timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc), source='test',
        traffic_level='HEAVY', free_flow_speed_kmh=30, current_speed_kmh=10,
        delay_factor=3) | changes))


def station(**changes):
    return StationStateSnapshot(**(dict(entity_id='S001',
        timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc), source='test',
        operating_status='OPEN', available_charging_slots=5, occupied_charging_slots=1,
        available_swap_slots=0, occupied_swap_slots=0, available_swap_batteries=0,
        charging_service_time_min=18, swap_service_time_min=0) | changes))


@pytest.mark.asyncio
async def test_concurrent_retry_conflict_and_historical_pinning(repository):
    old = traffic()
    results = await asyncio.gather(*(repository.ingest(old) for _ in range(8)))
    assert sum(created for _, created in results) == 1
    assert all(snapshot == old for snapshot, _ in results)
    for changed in [traffic(source='other'), traffic(delay_factor=4)]:
        with pytest.raises(StateError) as exc:
            await repository.ingest(changed)
        assert exc.value.status == 409
    newer = traffic(timestamp=old.timestamp + timedelta(hours=1))
    older = traffic(timestamp=old.timestamp - timedelta(hours=1))
    await repository.ingest(newer)
    await repository.ingest(older)
    assert await repository.heads([old.key, 'station:missing'], old.timestamp) == {
        old.key: old.snapshot_id, 'station:missing': None}
    assert await repository.heads([old.key], newer.timestamp) == {old.key: newer.snapshot_id}
    assert await repository.heads([old.key], older.timestamp - timedelta(seconds=1)) == {old.key: None}
    assert await repository.payloads([old.snapshot_id, newer.snapshot_id]) == {
        old.snapshot_id: old, newer.snapshot_id: newer}
    with pytest.raises(ValueError):
        await repository.heads([old.key], datetime(2026, 9, 1))


@pytest.mark.asyncio
async def test_batch_conflict_rolls_back_and_id_collision(repository):
    first = traffic()
    second = traffic(timestamp=first.timestamp + timedelta(hours=1))
    assert await repository.ingest_many([first, first, second]) == 2
    assert await repository.ingest_many([second, first]) == 0
    third = traffic(timestamp=first.timestamp + timedelta(hours=2))
    with pytest.raises(StateError):
        await repository.ingest_many([third, traffic(source='changed')])
    assert third.snapshot_id not in await repository.payloads([third.snapshot_id])
    # Exercise an identity collision against an existing persisted row.
    async with repository.pool.acquire() as conn:
        await conn.execute('UPDATE state_snapshots SET snapshot_id=$1 WHERE snapshot_id=$2',
                           uuid4(), UUID(first.snapshot_id))
    with pytest.raises(StateError) as exc:
        await repository.ingest(first)
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_ingestion_checks_catalog_capacity_and_traffic(repository):
    from backend.app.services.snapshots.ingestion import IngestionService
    from backend.app.services.snapshots.models import QueueSnapshot
    service = IngestionService(repository)
    assert (await service.ingest(station()))[1]
    assert (await service.ingest(traffic()))[1]
    queue = QueueSnapshot(entity_id='S001', timestamp=station().timestamp, source='test',
        charging_queue_length=1, charging_active_service_count=2,
        charging_service_time_min=18, charging_estimated_wait_min=3,
        swap_queue_length=0, swap_active_service_count=0,
        swap_service_time_min=0, swap_estimated_wait_min=0)
    assert (await service.ingest(queue))[1]
    invalid = [station(entity_id='missing'), traffic(entity_id='missing'),
        station(available_charging_slots=6, occupied_charging_slots=1),
        station(charging_service_time_min=0), station(available_swap_batteries=1),
        station(swap_service_time_min=6), traffic(delay_factor=2),
        queue.model_copy(update={'charging_active_service_count': 7}),
        queue.model_copy(update={'swap_estimated_wait_min': 2})]
    for snapshot in invalid:
        with pytest.raises(StateError) as exc:
            await service.ingest(snapshot)
        assert exc.value.status == 422
    rounded = traffic(timestamp=traffic().timestamp + timedelta(minutes=1),
                      current_speed_kmh=28.54, delay_factor=1.051)
    assert (await service.ingest(rounded))[1]


@pytest.mark.asyncio
async def test_candidate_search_evidence_is_immutable(repository):
    from backend.app.services.ranking.models import CandidateSearchEvidence
    from backend.app.services.demand.models import EnergyServiceRequest
    from backend.app.services.candidate.models import CandidateSearchResult
    request = EnergyServiceRequest(service_request_id='request', vehicle_id='V001',
        timestamp=traffic().timestamp, request_source='DRIVER_REQUEST', need_service=True,
        allowed_service_types=['CHARGING'], reason_code='VALID_REQUEST')
    evidence = CandidateSearchEvidence(request_time=traffic().timestamp, energy_request=request,
        result=CandidateSearchResult(service_request_id='request', total_candidates_evaluated=0,
            eligible_count=0, candidates=[]), snapshot_ids={}, catalog_digest='digest')
    await repository.save_search(evidence)
    await repository.save_search(evidence)
    assert await repository.get_search(evidence.candidate_search_id) == evidence
    with pytest.raises(StateError) as exc:
        await repository.save_search(evidence.model_copy(update={'catalog_digest': 'changed'}))
    assert exc.value.status == 409
    with pytest.raises(StateError) as exc:
        await repository.get_search('missing')
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_source_loader_batches_are_idempotent(repository):
    from scripts.load_week4_snapshots import iter_snapshots, load_snapshots
    from backend.app.config import settings
    from backend.app.services.snapshots.ingestion import IngestionService
    from itertools import islice
    source_rows = list(islice(iter_snapshots(settings.dataset_path), 7))
    assert len(source_rows) == 7
    service = IngestionService(repository)
    assert await load_snapshots(service, source_rows, batch_size=3) == {'read': 7, 'created': 7}
    assert await load_snapshots(service, source_rows, batch_size=3) == {'read': 7, 'created': 0}


@pytest.mark.asyncio
async def test_conflicting_writers_and_indexed_history(repository):
    versions = [traffic(), traffic(source='other-writer')]
    results = await asyncio.gather(*(repository.ingest(value) for value in versions),
                                   return_exceptions=True)
    assert sum(isinstance(value, StateError) and value.status == 409 for value in results) == 1
    assert sum(isinstance(value, tuple) and value[1] for value in results) == 1
    base = traffic().timestamp
    history = [traffic(timestamp=base + timedelta(minutes=i)) for i in range(1, 1001)]
    assert await repository.ingest_many(history) == 1000
    async with repository.pool.acquire() as connection:
        await connection.execute('ANALYZE state_snapshots')
        plan = await connection.fetch('''EXPLAIN (ANALYZE, COSTS OFF)
            SELECT snapshot_id FROM state_snapshots
            WHERE kind=$1 AND entity_id=$2 AND timestamp <= $3
            ORDER BY timestamp DESC LIMIT 1''', 'traffic', traffic().entity_id, history[-1].timestamp)
    assert 'Index Scan Backward' in '\n'.join(row[0] for row in plan)
    assert await repository.heads([history[0].key], history[400].timestamp) == {
        history[0].key: history[400].snapshot_id}


@pytest.mark.asyncio
async def test_repository_reports_database_failure(repository):
    await repository.pool.close()
    with pytest.raises(StateError) as exc:
        await repository.heads(['station:S001'], traffic().timestamp)
    assert exc.value.status == 503
    assert exc.value.detail['error_code'] == 'SNAPSHOT_DATABASE_UNAVAILABLE'


@pytest.mark.asyncio
async def test_snapshot_identity_survives_jsonb_signed_zero(repository):
    value = station(swap_service_time_min=-0.0)
    await repository.ingest(value)
    loaded = (await repository.payloads([value.snapshot_id]))[value.snapshot_id]
    assert loaded.snapshot_id == value.snapshot_id
    assert loaded.snapshot_id == station(swap_service_time_min=0.0).snapshot_id
