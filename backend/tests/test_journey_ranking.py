from backend.tests.test_week4_ranking import candidate, evidence, view, station, queue, NOW
from backend.app.services.ranking.context import build_features
from backend.app.services.ranking.models import RankingPolicy
from backend.app.services.ranking.service import rank_features
from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.route_familiarity.service import FamiliarityAssessment
import pytest


def features():
    a = candidate('S001', duration=100)
    b = candidate('S002', duration=200)
    a = a.model_copy(update={'route_metrics': a.route_metrics.model_copy(update={'duration_station_to_dest_s': 1000})})
    b = b.model_copy(update={'route_metrics': b.route_metrics.model_copy(update={'duration_station_to_dest_s': 10})})
    return build_features(evidence([a, b]), view(station(), queue(), station('S002'), queue('S002')), NOW, RankingPolicy(), station_catalog)


def test_full_journey_changes_order():
    ranked = rank_features(features())
    assert ranked[0].station_id == 'S002'
    assert ranked[0].total_completion_time_s == 1410
    assert ranked[0].final_cost_s == 1410


def test_each_familiarity_share_can_change_order_without_changing_eta():
    fs = [f.model_copy(update={'duration_station_to_dest_s': 0, 'adjusted_travel_duration_s': 100 if f.station_id == 'S001' else 110}) for f in features()]
    for field, confidence in [('personal_adherence', 'confidence'), ('community_adherence', 'community_confidence')]:
        assessments = {('S001', 'CHARGING'): FamiliarityAssessment('AVAILABLE', **{field: 0, confidence: 1}), ('S002', 'CHARGING'): FamiliarityAssessment('AVAILABLE', **{field: 1, confidence: 1})}
        ranked = rank_features(fs, assessments)
        assert ranked[0].station_id == 'S002'
        assert ranked[0].total_completion_time_s == 1310


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,has_b,legs', [('BEFORE_DESTINATION', True, 2), ('BEFORE_DESTINATION', False, 1), ('AFTER_DESTINATION', True, 2)])
async def test_station_plan_goals_and_geometry(client, app, monkeypatch, mode, has_b, legs):
    from backend.tests.test_route_familiarity_workflow import body, workflow
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    app.state.recommendation_workflow = workflow()
    payload = body() | {'station_id': 'S001', 'service_type': 'CHARGING', 'plan_mode': mode}
    if not has_b:
        payload.pop('destination_latitude')
        payload.pop('destination_longitude')
    response = await client.post('/api/v1/station-plan', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['route']['distance_m'] == legs * 1000
    assert len(result['route']['geometry']) == legs + 1
    assert result['goal_role'] == ('PASSENGER_DESTINATION' if has_b and mode == 'BEFORE_DESTINATION' else 'STATION')
    assert result['ranked_candidate']['total_completion_time_s'] == result['ranked_candidate']['eta_to_service_complete_s'] + (131 if mode == 'BEFORE_DESTINATION' and has_b else 0)


@pytest.mark.asyncio
async def test_impossible_after_destination_and_ineligible_selection(client, app, monkeypatch):
    from backend.tests.test_route_familiarity_workflow import body, workflow
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    app.state.recommendation_workflow = workflow()
    payload = body() | {'station_id': 'missing', 'service_type': 'CHARGING'}
    response = await client.post('/api/v1/station-plan', json=payload)
    assert response.status_code == 409
    payload['plan_mode'] = 'AFTER_DESTINATION'
    payload['context']['estimated_remaining_range_km'] = 0.5
    response = await client.post('/api/v1/station-plan', json=payload)
    assert response.status_code == 409
    assert response.json()['error_code'] == 'DESTINATION_ENERGY_INFEASIBLE'


@pytest.mark.asyncio
async def test_frequency_counts_non_supporters_and_repeated_personal_usage():
    from backend.tests.test_route_familiarity_service import Repository, history_row, sig, NOW as as_of
    from backend.app.services.route_familiarity.service import RouteFamiliarityService
    supporting = [history_row(driver_id=f'd{i}', cells=['a', 'b']) for i in range(5)]
    not_supporting = [history_row(driver_id=f'n{i}', cells=['x', 'y']) for i in range(5)]
    signature = {('S001', 'CHARGING'): sig(['a', 'b'])}
    popular = (await RouteFamiliarityService(Repository(community=supporting)).assess_many('driver', signature, as_of))[('S001', 'CHARGING')]
    less_popular = (await RouteFamiliarityService(Repository(community=supporting + not_supporting)).assess_many('driver', signature, as_of))[('S001', 'CHARGING')]
    assert less_popular.community_adherence < popular.community_adherence
    assert less_popular.community_cohort_driver_count == 10
    personal = (await RouteFamiliarityService(Repository(personal=[supporting[0], not_supporting[0]])).assess_many('driver', signature, as_of))[('S001', 'CHARGING')]
    assert personal.personal_adherence == pytest.approx(0.5, abs=0.01)


@pytest.mark.asyncio
async def test_direct_and_station_routes_share_constraints(app):
    from backend.tests.test_route_familiarity_workflow import workflow, search_request, Routes
    from backend.app.services.routing.models import RouteConstraints
    routes = Routes()
    request = search_request(app)
    constraints = RouteConstraints(avoid_segments=['blocked'])
    request.constraints = constraints
    await workflow(routes=routes).recommend(request)
    assert len(routes.requests) == 5
    assert all(route.constraints == constraints for _, route in routes.requests)


@pytest.mark.asyncio
async def test_unproven_replenishment_cannot_make_onward_leg_feasible(client, app, monkeypatch):
    from backend.tests.test_route_familiarity_workflow import workflow, body
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    app.state.recommendation_workflow = workflow()
    payload = body()
    payload['context']['estimated_remaining_range_km'] = 1.5
    payload['context']['safety_reserve_km'] = 0
    response = await client.post('/api/v1/recommend', json=payload)
    assert response.status_code == 200, response.text
    assert not response.json()['has_recommendation']
    payload.pop('destination_latitude')
    payload.pop('destination_longitude')
    response = await client.post('/api/v1/recommend', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['has_recommendation']


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['/api/v1/recommend', '/api/v1/candidate-search/evaluate'])
async def test_recommend_without_shared_state_never_uses_replica_cache(client, app, monkeypatch, endpoint):
    from backend.tests.test_route_familiarity_workflow import workflow, body
    from backend.app.config import settings
    monkeypatch.setattr(settings, 'enable_route_familiarity', False)
    app.state.recommendation_workflow = workflow()
    app.state.driver_state_manager = None
    payload = body()
    payload['context'].pop('raw_latitude')
    payload['context'].pop('raw_longitude')
    if endpoint.endswith('/evaluate'):
        payload = payload['context'] | {'requested_service': 'CHARGING'}
    response = await client.post(endpoint, json=payload)
    assert response.status_code == 503, response.text
