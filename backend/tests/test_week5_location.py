from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.api.v1.candidate import EvaluateAndSearchApiRequest, evaluate_and_search
from backend.app.api.v1.demand import EvaluateDemandApiRequest, evaluate_driver_demand_with_realtime_state
from backend.app.services.realtime.state import GPSObservation, MatchedState, get_state_store

T = datetime(2026, 9, 1, tzinfo=timezone.utc)
DRIVER = 'week5-location-test'

@pytest.fixture
def state():
    store = get_state_store()
    store.remove(DRIVER)
    value = store.get_or_create(DRIVER)
    value.add_observation(GPSObservation('obs', DRIVER, T, 21.0, 105.0))
    value.reset_after_match(MatchedState(21.1, 105.1, road_segment_id='segment', matched_at=T + timedelta(days=1)))
    yield value
    store.remove(DRIVER)

@pytest.mark.asyncio
async def test_candidate_current_state_uses_existing_fields(state):
    service = SimpleNamespace(search_candidates=AsyncMock(return_value='result'))
    assert await evaluate_and_search(EvaluateAndSearchApiRequest(vehicle_id='V0001',
        driver_id=DRIVER, timestamp=T, current_soc_pct=10), service) == 'result'
    energy = service.search_candidates.call_args.args[0].energy_request
    assert (energy.latitude, energy.longitude, energy.road_segment_id) == (21.1, 105.1, 'segment')

@pytest.mark.asyncio
@pytest.mark.parametrize('coordinates', [(0.0, 0.0), (0.0, 106.0), (22.0, 0.0), (22.0, 106.0)])
async def test_explicit_coordinates_not_overwritten(state, coordinates):
    result = await evaluate_driver_demand_with_realtime_state(DRIVER, EvaluateDemandApiRequest(
        vehicle_id='V0001', timestamp=T, current_soc_pct=10,
        raw_latitude=coordinates[0], raw_longitude=coordinates[1]))
    assert (result.latitude, result.longitude) == coordinates
    assert result.road_segment_id is None  # A cached match belongs to a different position.


def test_resolver_respects_event_time_and_week1_gap_reset(state):
    from backend.app.services.realtime.location import resolve_current_location
    resolve = lambda at: resolve_current_location(DRIVER, None, None, None, at)
    assert resolve(T).source == 'MATCHED'
    assert resolve(T - timedelta(microseconds=1)).source == 'LOCATION_UNAVAILABLE'
    # matched_at is execution time and must not block historical observation matches.
    assert state.last_matched_state.matched_at > T
    state.add_observation(GPSObservation('gap', DRIVER, T + timedelta(seconds=61), 21.2, 105.2))
    assert resolve(T + timedelta(seconds=61)).source == 'RAW_GPS_FALLBACK'
    assert resolve(T).source == 'LOCATION_UNAVAILABLE'

@pytest.mark.asyncio
@pytest.mark.parametrize('branch,coordinates,expected', [
    ('matched', None, 'MATCHED'), ('raw', None, 'RAW_GPS_FALLBACK'),
    ('explicit', (0.0, 0.0), 'EXPLICIT'), ('explicit', (0.0, 106.0), 'EXPLICIT'),
    ('explicit', (22.0, 0.0), 'EXPLICIT'), ('explicit', (22.0, 106.0), 'EXPLICIT'),
    ('missing', None, 'LOCATION_UNAVAILABLE'), ('future', None, 'LOCATION_UNAVAILABLE'),
    ('no_service', None, 'LOCATION_UNAVAILABLE'),
])
async def test_recommend_location_bridge(state, branch, coordinates, expected):
    from httpx import ASGITransport, AsyncClient
    from backend.app.main import create_app
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.services.ranking.models import RecommendationResult, RankingPolicy
    captured = []
    async def recommend(request, top_n=None, metrics=None):
        captured.append(request.energy_request)
        metrics.update(workflow_attempts=1, candidate_state_conflicts=0,
                       candidate_search_calls=1, ranking_calls=1,
                       timings_ms={'candidate_search': 1.0, 'ranking': 1.0})
        return RecommendationResult(candidate_search_id='test', request_time=T,
            has_recommendation=False, recommended_station_id=None, recommended_service_type=None,
            ranked_candidates=[], eligible_count=0, policy=RankingPolicy(),
            energy_context=request.energy_request, degraded=False, degraded_reasons=[], reason='TEST')
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: SimpleNamespace(recommend=recommend)
    if branch == 'raw':
        state.last_matched_state = None
    elif branch in ('missing', 'no_service'):
        get_state_store().remove(DRIVER)
    elif branch == 'future':
        state.last_match_time = T + timedelta(seconds=1)
        state.observations[-1].timestamp = T + timedelta(seconds=1)
    context = dict(vehicle_id='V0001', driver_id=DRIVER, timestamp=T.isoformat(),
                   current_soc_pct=95, estimated_remaining_range_km=200,
                   remaining_trip_distance_km=1)
    if coordinates is not None:
        context.update(raw_latitude=coordinates[0], raw_longitude=coordinates[1])
    payload = {'context': context}
    if branch != 'no_service':
        payload['requested_service'] = 'CHARGING'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        response = await http.post('/api/v1/recommend', json=payload)
    if branch in ('missing', 'future'):
        assert response.status_code == 422, response.text
        assert response.json()['error_code'] == 'LOCATION_UNAVAILABLE'
        assert not captured
    else:
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['location_source'] == expected
        if coordinates is not None:
            assert (captured[0].latitude, captured[0].longitude) == coordinates
        elif branch == 'matched':
            assert (captured[0].latitude, captured[0].longitude) == (21.1, 105.1)
        elif branch == 'raw':
            assert captured[0].road_segment_id is None
        else:
            assert not captured[0].need_service
        assert all(result['timings_ms'][key] >= 0 for key in
                   ['location_resolution', 'demand', 'candidate_search', 'ranking', 'total'])
        assert result['workflow_attempts'] == result['candidate_search_calls'] == result['ranking_calls'] == 1

@pytest.mark.asyncio
async def test_partial_coordinates_are_not_mixed_with_cached_state(state):
    from backend.app.services.snapshots.models import StateError
    with pytest.raises(StateError) as error:
        await evaluate_driver_demand_with_realtime_state(DRIVER, EvaluateDemandApiRequest(
            vehicle_id='V0001', timestamp=T, raw_latitude=0.0))
    assert error.value.status == 422
    assert error.value.detail['error_code'] == 'INVALID_LOCATION'

@pytest.mark.asyncio
async def test_invalid_explicit_service_keeps_week4_error_without_location():
    from httpx import ASGITransport, AsyncClient
    from backend.app.main import create_app
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.services.ranking.orchestration import RecommendationWorkflow
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: RecommendationWorkflow(None, None, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as http:
        response = await http.post('/api/v1/recommend', json={'requested_service': 'BATTERY_SWAP',
            'context': {'vehicle_id': 'V0001', 'timestamp': T.isoformat(), 'current_soc_pct': 60}})
    assert response.status_code == 422
    assert response.json()['error_code'] == 'INVALID_ENERGY_REQUEST'

@pytest.mark.asyncio
@pytest.mark.parametrize('conflict_twice', [False, True])
async def test_metrics_preserve_one_retry_boundary(conflict_twice):
    from backend.app.services.ranking.models import CandidateStateChanged
    from backend.app.services.ranking.orchestration import RecommendationWorkflow
    conflict = CandidateStateChanged('old', [dict(station_id='S001', service_type='CHARGING',
        previous_state='ELIGIBLE', current_state='OFFLINE')])
    workflow = RecommendationWorkflow(None, None, None)
    saved = SimpleNamespace(result=SimpleNamespace(total_candidates_evaluated=1))
    result = SimpleNamespace(eligible_count=1, policy=SimpleNamespace(name='test'),
        recommended_station_id='S002', recommended_service_type='CHARGING')
    workflow.search = AsyncMock(return_value=saved)
    workflow.ranking = SimpleNamespace(recommend=AsyncMock(side_effect=[conflict,
        conflict if conflict_twice else result]))
    metrics = {}
    if conflict_twice:
        with pytest.raises(CandidateStateChanged):
            await workflow.recommend('request', metrics=metrics)
    else:
        assert await workflow.recommend('request', metrics=metrics) is result
    assert metrics['workflow_attempts'] == metrics['candidate_search_calls'] == metrics['ranking_calls'] == 2
    assert metrics['candidate_state_conflicts'] == (2 if conflict_twice else 1)
    assert workflow.search.await_count == workflow.ranking.recommend.await_count == 2
    assert all(value >= 0 for value in metrics['timings_ms'].values())
