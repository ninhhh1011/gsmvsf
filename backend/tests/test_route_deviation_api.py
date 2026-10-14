from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.config import settings
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.snapshots.models import StateError
from backend.tests.test_route_familiarity_repository import Pool
from backend.tests.test_route_deviations import evidence, point


@pytest.mark.asyncio
async def test_guided_evidence_insert_retry_conflict():
    conn = AsyncMock()
    payload = evidence([point(i * 20) for i in range(6)]).model_dump(mode='json')
    conn.fetchrow.side_effect = [{'trip_id': 'fake-trip'}, None, {'evidence': payload}, None, {'evidence': {}}]
    repo = RouteHistoryRepository(Pool(conn), 'synthetic')
    assert await repo.ingest_guided_trip(payload, {'cells': {}})
    assert not await repo.ingest_guided_trip(payload, {'cells': {}})
    with pytest.raises(StateError) as exc:
        await repo.ingest_guided_trip(payload, {'cells': {}})
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_departure_ingestion_requires_token_and_valid_evidence(client, app, monkeypatch):
    monkeypatch.setattr(settings, 'snapshot_ingestion_token', 'trusted')
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    repo = AsyncMock()
    repo.ingest_guided_trip.return_value = True
    app.state.route_history_repository = repo
    payload = evidence([point(i * 20) for i in range(6)]).model_dump(mode='json')
    url = '/api/v1/internal/route-deviations/trips'
    assert (await client.post(url, json=payload)).status_code == 401
    assert (await client.post(url, json=payload, headers={'X-Ingestion-Token': 'wrong'})).status_code == 403
    response = await client.post(url, json=payload, headers={'X-Ingestion-Token': 'trusted'})
    assert response.status_code == 201
    assert repo.ingest_guided_trip.await_args.args[1]['comparable']
    response = await client.post(url, json={**payload, 'observations': []}, headers={'X-Ingestion-Token': 'trusted'})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_disabled_or_outage_is_explicit(client, app, monkeypatch):
    url = '/api/v1/routing/departure-heatmap'
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    response = await client.get(url)
    assert response.status_code == 200
    assert response.json()['status'] == 'DISABLED'
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    app.state.route_history_repository = AsyncMock()
    app.state.route_history_repository.departure_heatmap.side_effect = RuntimeError('private SQL error')
    response = await client.get(url)
    assert response.status_code == 503
    assert 'private SQL' not in response.text


@pytest.mark.asyncio
async def test_heatmap_uses_explicit_asof_and_effective_resolution(client, app, monkeypatch):
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    repo = AsyncMock()
    repo.departure_heatmap.return_value = {'status': 'NO_PAIRED_EVIDENCE', 'cells': {}, 'source': 'synthetic'}
    app.state.route_history_repository = repo
    response = await client.get('/api/v1/routing/departure-heatmap', params={
        'resolution': 7, 'as_of_iso': '2026-10-14T00:00:00Z'})
    assert response.status_code == 200
    assert response.json()['lookback_days'] == 7
    assert repo.departure_heatmap.await_args.args == (datetime(2026, 10, 14, tzinfo=UTC), 7)
    assert (await client.get('/api/v1/routing/departure-heatmap?resolution=11')).status_code == 422
    assert (await client.get('/api/v1/routing/departure-heatmap?as_of_iso=2026-10-14T00:00:00')).status_code == 422


@pytest.mark.asyncio
async def test_aggregate_query_has_causal_window_distinct_trip_counts_and_privacy():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=Pool(conn))
    conn.fetch.return_value = []
    conn.fetchrow.return_value = {'paired_trip_count': 0, 'excluded_unpaired_trip_count': 12,
                                'unknown_trip_count': 0, 'uncertain_intervals': 0}
    repo = RouteHistoryRepository(Pool(conn), 'realtime')
    result = await repo.departure_heatmap(datetime(2026, 10, 14, tzinfo=UTC), 9)
    assert result['status'] == 'NO_PAIRED_EVIDENCE'
    assert result['excluded_unpaired_trip_count'] == 12
    sql, lower, upper, resolution, minimum_drivers = conn.fetch.await_args.args
    assert 'completed_at <= $2' in sql
    assert 'count(DISTINCT' in sql
    assert 'departure_at' in sql and 'reached_at' in sql
    assert (upper - lower).days == 7 and resolution == '9' and minimum_drivers == 5
