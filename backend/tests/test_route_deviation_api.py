from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import h3

from backend.app.config import settings
from backend.app.services.route_familiarity.repository import RouteHistoryRepository, aggregate_history_footprints
from backend.app.services.snapshots.models import StateError
from backend.tests.test_route_familiarity_repository import Pool
from backend.tests.test_route_deviations import evidence, point


@pytest.mark.asyncio
async def test_stress_cohort_filters_paired_evidence_without_legacy_or_private_rows():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=Pool(conn))
    conn.fetch.return_value = []
    conn.fetchrow.return_value = {'paired_trip_count': 5, 'excluded_unpaired_trip_count': 40,
                                'unknown_trip_count': 0, 'uncertain_intervals': 0}
    repo = RouteHistoryRepository(Pool(conn), 'synthetic')
    result = await repo.departure_heatmap(datetime.now(UTC), 9, 'stress')
    assert result['cohort'] == 'stress' and result['excluded_unpaired_trip_count'] == 0
    assert conn.fetch.await_count == 1
    assert conn.fetch.await_args.args[-1] == 'stress'
    assert "split_part(driver_id,'-',4)=$5" in conn.fetch.await_args.args[0]
    assert "split_part(driver_id,'-',4)=$3" in conn.fetchrow.await_args.args[0]
    with pytest.raises(StateError):
        await RouteHistoryRepository(Pool(conn), 'realtime').departure_heatmap(datetime.now(UTC), 9, 'stress')


@pytest.mark.asyncio
async def test_cohort_api_rejects_unknown_and_passes_valid_selection(client, app, monkeypatch):
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    repo = AsyncMock()
    repo.departure_heatmap.return_value = {'status': 'NO_PAIRED_EVIDENCE', 'cells': {}}
    app.state.route_history_repository = repo
    assert (await client.get('/api/v1/routing/departure-heatmap?cohort=invalid')).status_code == 422
    assert (await client.get('/api/v1/routing/departure-heatmap?cohort=stress')).status_code == 200
    assert repo.departure_heatmap.await_args.args[-1] == 'stress'


@pytest.mark.asyncio
async def test_stateless_guided_inspection_and_public_example_boundary(client, app, monkeypatch):
    payload = evidence([point(i * 20) for i in range(8)]).model_dump(mode='json')
    response = await client.post('/api/v1/routing/inspect-guided-trip', json=payload)
    assert response.status_code == 200
    assert response.json()['summary']['off_route_distance_m'] == 0
    assert 'driver_id' not in response.text and 'trip_id' not in response.text
    assert (await client.post('/api/v1/routing/inspect-guided-trip', json={})).status_code == 422
    monkeypatch.setattr(settings, 'enable_route_familiarity', True)
    monkeypatch.setattr(settings, 'public_synthetic_sample', True)
    repo = AsyncMock()
    repo.namespace = 'realtime'
    app.state.route_history_repository = repo
    assert (await client.get('/api/v1/routing/guided-examples')).status_code == 403
    repo.namespace = 'synthetic'
    repo.guided_examples.return_value = []
    assert (await client.get('/api/v1/routing/guided-examples')).status_code == 200
    monkeypatch.setattr(settings, 'public_synthetic_sample', False)
    assert (await client.get('/api/v1/routing/guided-examples')).status_code == 403


@pytest.mark.asyncio
async def test_public_examples_strip_synthetic_identities():
    conn = AsyncMock()
    payload = evidence([point(i * 20) for i in range(8)]).model_dump(mode='json')
    conn.fetch.return_value = [{'evidence': payload}]
    result = await RouteHistoryRepository(Pool(conn), 'synthetic').guided_examples()
    assert result[0]['driver_id'] == 'public-synthetic'
    assert result[0]['trip_id'] == 'example-1'
    assert 'fake-driver' not in str(result)


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
    sql, lower, upper, resolution, minimum_drivers = conn.fetch.await_args_list[0].args
    assert 'completed_at <= $2' in sql
    assert 'count(DISTINCT' in sql
    assert 'departure_at' in sql and 'reached_at' in sql
    assert (upper - lower).days == 7 and resolution == '9' and minimum_drivers == 5


def test_history_footprints_count_trips_once_per_cell_without_departure_weights():
    first = h3.latlng_to_cell(21, 105.8, 11)
    second = h3.latlng_to_cell(21.00001, 105.8, 11)
    rows = [{'cells': [first, second, first], 'trip_count': 10, 'drivers': ['d1', 'd2', 'd1']},
            {'cells': [first], 'trip_count': 3, 'drivers': ['d1', 'd3']}]
    result = aggregate_history_footprints(rows, 9, 1)
    assert len(result) == 1
    stats = next(iter(result.values()))
    assert stats['history_trip_count'] == 13
    assert stats['history_driver_count'] == 3
    assert stats['departure_pct'] is None
    assert stats['eligible_trip_count'] is None
    assert stats['status'] == 'HISTORY_ONLY'
    assert not aggregate_history_footprints(rows, 9, 5)


def test_history_footprints_reject_malformed_signatures():
    with pytest.raises(StateError):
        aggregate_history_footprints([{'cells': ['invalid'], 'trip_count': 10, 'drivers': ['d']}], 9, 1)


@pytest.mark.asyncio
async def test_history_only_heatmap_does_not_turn_visits_into_departures():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=Pool(conn))
    conn.fetchrow.return_value = {'paired_trip_count': 0, 'excluded_unpaired_trip_count': 10,
                                'unknown_trip_count': 0, 'uncertain_intervals': 0}
    conn.fetch.side_effect = [[], [{'cells': [h3.latlng_to_cell(21, 105.8, 11)],
                                  'trip_count': 10, 'drivers': ['d1', 'd2']}]]
    result = await RouteHistoryRepository(Pool(conn), 'synthetic').departure_heatmap(datetime.now(UTC), 9)
    assert result['status'] == 'HISTORY_ONLY'
    assert next(iter(result['cells'].values()))['departure_pct'] is None
    history_sql = conn.fetch.await_args_list[1].args[0]
    assert 'completed_at <= $2' in history_sql
    assert 'NOT EXISTS' in history_sql
    assert 'd.completed_at <= $2' in history_sql
    assert 'd.completed_at <= $2' in conn.fetchrow.await_args.args[0]
