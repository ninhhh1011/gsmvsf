from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.services.ranking.models import CandidateStateChanged


@pytest.mark.asyncio
async def test_orchestrator_retries_once_only_outside_ranking():
    from backend.app.services.ranking.orchestration import RecommendationWorkflow
    conflict = CandidateStateChanged('old', [dict(station_id='S001', service_type='CHARGING',
                                       previous_state='ELIGIBLE', current_state='OFFLINE')])
    workflow = RecommendationWorkflow(None, None, None)
    saved = SimpleNamespace(result=SimpleNamespace(total_candidates_evaluated=1))
    success = SimpleNamespace(eligible_count=1, policy=SimpleNamespace(name='test'),
                              recommended_station_id='S001', recommended_service_type='CHARGING')
    workflow.search = AsyncMock(side_effect=[saved, saved])
    workflow.ranking = SimpleNamespace(recommend=AsyncMock(side_effect=[conflict, success]))
    assert await workflow.recommend('request') == success
    assert workflow.search.await_count == 2
    workflow.search.reset_mock(side_effect=True)
    workflow.search.side_effect = [saved, saved]
    workflow.ranking.recommend.side_effect = [conflict, conflict]
    with pytest.raises(CandidateStateChanged):
        await workflow.recommend('request')
    assert workflow.search.await_count == 2


@pytest.mark.asyncio
async def test_api_structured_conflict_and_ingestion_auth(monkeypatch):
    from backend.app.main import create_app
    from backend.app.api.v1.ranking import get_workflow, get_ingestion
    from backend.app.config import settings
    app = create_app()
    workflow = SimpleNamespace(repository=SimpleNamespace(get_search=AsyncMock(return_value='evidence')),
        ranking=SimpleNamespace(recommend=AsyncMock(side_effect=CandidateStateChanged('search', [
            dict(station_id='S010', service_type='CHARGING', previous_state='ELIGIBLE', current_state='FULL')]))))
    app.dependency_overrides[get_workflow] = lambda: workflow
    app.dependency_overrides[get_ingestion] = lambda: None
    monkeypatch.setattr(settings, 'snapshot_ingestion_token', 'test-token')
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/ranking', json={'candidate_search_id': 'search'})
        assert response.status_code == 409
        assert response.json()['error_code'] == 'CANDIDATE_STATE_CHANGED'
        assert response.json()['action'] == 'RERUN_CANDIDATE_SEARCH'
        assert (await client.post('/api/v1/internal/snapshots/traffic', json={})).status_code == 401
        assert (await client.post('/api/v1/internal/snapshots/traffic', json={},
                                headers={'X-Ingestion-Token': 'wrong'})).status_code == 403
        assert (await client.post('/api/v1/internal/snapshots/traffic', json={},
                                headers={'X-Ingestion-Token': 'test-token'})).status_code == 422


@pytest.mark.asyncio
async def test_snapshot_search_and_rank_use_existing_candidate_service(repository):
    from backend.tests.test_week4_database import station, traffic
    from backend.tests.mock_routing_adapter import MockRoutingAdapter
    from backend.app.services.snapshots.resolver import SnapshotResolver
    from backend.app.services.ranking.orchestration import RecommendationWorkflow
    from backend.app.services.candidate.station_catalog import station_catalog
    from backend.app.services.candidate.models import CandidateSearchRequest
    from backend.app.services.demand.models import DemandContext, RequestedServiceType
    from backend.app.services.demand.service import get_demand_service
    catalog = SimpleNamespace(get_all_stations=lambda: [station_catalog.get_station('S001')],
                              get_station=station_catalog.get_station)
    timestamp = traffic().timestamp
    await repository.ingest(station())
    energy = get_demand_service().process_driver_request(DemandContext(vehicle_id='V0001',
        timestamp=timestamp, current_soc_pct=60, estimated_remaining_range_km=200,
        raw_latitude=21.028, raw_longitude=105.854), RequestedServiceType.CHARGING)
    request = CandidateSearchRequest(energy_request=energy)
    workflow = RecommendationWorkflow(repository, SnapshotResolver(repository), MockRoutingAdapter(), catalog=catalog)
    evidence = await workflow.search(request)
    assert evidence.result.eligible_count == 1
    assert evidence.result.search_timestamp.utcoffset().total_seconds() == 0
    result = await workflow.ranking.recommend(evidence)
    assert result.recommended_station_id == 'S001'
    assert result.degraded  # Queue and traffic are explicitly missing.
    for changed in [request.model_copy(update={'destination_latitude': 21.0}),
                    request.model_copy(update={'energy_request': energy.model_copy(update={'current_soc_pct': -1})})]:
        with pytest.raises(Exception) as invalid:
            await workflow.search(changed)
        assert getattr(invalid.value, 'status', None) == 422
    await repository.ingest(station(timestamp=timestamp + timedelta(seconds=1), operating_status='OFFLINE'))
    with pytest.raises(CandidateStateChanged):
        await workflow.ranking.recommend(evidence, timestamp + timedelta(seconds=1))


from backend.tests.test_week4_database import repository


@pytest.mark.asyncio
async def test_lifespan_real_resources_and_recommend_http_success(monkeypatch):
    import os
    from backend.app.config import settings
    from backend.app.main import create_app
    from backend.app.core.lifespan import lifespan
    monkeypatch.setattr(settings, 'database_url', os.environ.get('WEEK4_TEST_DATABASE_URL',
        'postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation'))
    app = create_app()
    async with lifespan(app):
        resolver = app.state.snapshot_resolver
        pool = resolver.repository.pool
        redis = resolver.cache.client
        assert await redis.ping()
        connections = list(redis.connection_pool._available_connections)
        client = app.state.recommendation_workflow.routing_engine._client
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
            response = await http.post('/api/v1/recommend', json={'context': {
                'vehicle_id': 'V0001', 'timestamp': '2026-09-01T06:00:00+07:00',
                'current_soc_pct': 95, 'estimated_remaining_range_km': 200,
                'remaining_trip_distance_km': 1, 'raw_latitude': 21.028,
                'raw_longitude': 105.854}})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['has_recommendation'] is False
        assert result['ranked_candidates'] == []
        assert not pool.is_closing()
    assert pool.is_closing()
    assert client.is_closed
    assert all(not connection.is_connected for connection in connections)
    assert app.state.recommendation_workflow is None
