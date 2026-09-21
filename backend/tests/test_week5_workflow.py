from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from backend.app.services.ranking.models import CandidateStateChanged
from backend.app.services.ranking.orchestration import RecommendationWorkflow
from backend.app.services.snapshots.models import StateError
from scripts.verify_week5 import validate_isolation


def test_live_verifier_refuses_shared_history_or_cache():
    validate_isolation('week5_probe_a1', 'week5:probe:a1:')
    for schema, prefix in [('public', 'week5:test:'), ('week5_good', 'week4:snapshot:'),
                           ('week5_bad; DROP TABLE x', 'week5:test:')]:
        with pytest.raises(ValueError):
            validate_isolation(schema, prefix)


@pytest.mark.asyncio
async def test_second_conflict_propagates_http409_after_exactly_two_searches():
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.main import create_app
    conflict = CandidateStateChanged('search', [dict(station_id='S001', service_type='CHARGING',
        previous_state='ELIGIBLE', current_state='OFFLINE')])
    workflow = RecommendationWorkflow(None, None, None)
    workflow.search = AsyncMock(return_value=object())
    workflow.ranking = SimpleNamespace(recommend=AsyncMock(side_effect=conflict))
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/recommend', json={'requested_service': 'CHARGING', 'context': {
            'vehicle_id': 'V0001', 'timestamp': '2026-09-01T00:00:00Z', 'current_soc_pct': 50,
            'estimated_remaining_range_km': 100, 'raw_latitude': 21.028, 'raw_longitude': 105.854}})
    assert response.status_code == 409
    assert response.json()['error_code'] == 'CANDIDATE_STATE_CHANGED'
    assert workflow.search.await_count == workflow.ranking.recommend.await_count == 2


@pytest.mark.asyncio
async def test_dependency_failure_does_not_trigger_candidate_retry():
    workflow = RecommendationWorkflow(None, None, None)
    workflow.search = AsyncMock(side_effect=StateError('PostgreSQL unavailable'))
    workflow.ranking = SimpleNamespace(recommend=AsyncMock())
    with pytest.raises(StateError):
        await workflow.recommend(object())
    assert workflow.search.await_count == 1
    workflow.ranking.recommend.assert_not_awaited()
