import pytest

from backend.app.services.candidate.service import CandidateSearchService
from backend.tests.test_route_familiarity_workflow import body, workflow, search_request
from backend.tests.test_week4_ranking import candidate, HistoryResolver, station, queue


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['/api/v1/candidate-search', '/api/v1/candidate-search/evaluate'])
@pytest.mark.parametrize('canonical_status,current_status', [('OFFLINE', 'OPEN'), ('OPEN', 'OFFLINE')])
async def test_public_candidate_endpoints_use_pinned_current_snapshots(client, app, endpoint, canonical_status, current_status):
    combined = workflow(resolver=HistoryResolver(station(operating_status=current_status), queue(), station('S002'), queue('S002')))
    combined.catalog.get_operational_snapshot = lambda **_: candidate().operational.model_copy(update={'operating_status': canonical_status})
    app.state.candidate_service = CandidateSearchService(combined.routing_engine, combined.catalog)
    app.state.recommendation_workflow = combined
    payload = search_request(app).model_dump(mode='json') if not endpoint.endswith('/evaluate') else body()['context'] | {'requested_service': 'CHARGING'}
    response = await client.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    selected = next(row for row in response.json()['candidates'] if row['station_id'] == 'S001')
    assert selected['eligible'] == (current_status == 'OPEN')
    assert selected['operational']['operating_status'] == current_status


@pytest.mark.asyncio
@pytest.mark.parametrize('endpoint', ['/api/v1/candidate-search', '/api/v1/candidate-search/evaluate'])
@pytest.mark.parametrize('eligible_only', [False, True])
async def test_standalone_limit_keeps_complete_counts_without_partial_ranking_evidence(client, app, endpoint, eligible_only):
    combined = workflow(resolver=HistoryResolver(station(operating_status='OFFLINE'), queue(), station('S002'), queue('S002')))
    app.state.recommendation_workflow = combined
    payload = search_request(app).model_dump(mode='json') if not endpoint.endswith('/evaluate') else body()['context'] | {'requested_service': 'CHARGING', 'eligible_only': eligible_only}
    payload['max_candidates'] = 1
    response = await client.post(endpoint + (f'?eligible_only={str(eligible_only).lower()}' if not endpoint.endswith('/evaluate') else ''), json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['total_candidates_evaluated'] == 2
    assert result['eligible_count'] == 1
    assert len(result['candidates']) == 1
    assert result['candidates'][0]['station_id'] == 'S002'
    assert combined.repository.saved == []


@pytest.mark.asyncio
async def test_missing_workflow_has_no_canonical_fallback(client, app):
    app.state.recommendation_workflow = None
    response = await client.post('/api/v1/candidate-search', json=search_request(app).model_dump(mode='json'))
    assert response.status_code == 503
