"""Ranking tests use controlled snapshot history, never a routing runtime."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

from backend.app.services.candidate.models import (
    CandidateRouteMetrics, CandidateSearchResult, EvaluatedCandidate,
    StationOperationalSnapshot,
)
from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.demand.models import EnergyServiceRequest, ServiceType
from backend.app.services.ranking.models import CandidateSearchEvidence, CandidateStateChanged, RankingPolicy
from backend.app.services.snapshots.models import (
    QueueSnapshot, ResolvedSnapshot, StateError, StationStateSnapshot, TrafficSnapshot,
)

NOW = datetime(2026, 9, 1, 6, tzinfo=timezone.utc)


def station(sid='S001', **changes):
    return StationStateSnapshot(**(dict(entity_id=sid, timestamp=NOW, source='test',
        operating_status='OPEN', available_charging_slots=2, occupied_charging_slots=0,
        available_swap_slots=2, occupied_swap_slots=0, available_swap_batteries=3,
        charging_service_time_min=18, swap_service_time_min=6) | changes))


def queue(sid='S001', **changes):
    return QueueSnapshot(**(dict(entity_id=sid, timestamp=NOW, source='test',
        charging_queue_length=1, charging_active_service_count=0, charging_service_time_min=99,
        charging_estimated_wait_min=2, swap_queue_length=0, swap_active_service_count=0,
        swap_service_time_min=99, swap_estimated_wait_min=1) | changes))


def traffic(**changes):
    return TrafficSnapshot(**(dict(entity_id='segment', timestamp=NOW, source='test',
        traffic_level='HEAVY', free_flow_speed_kmh=30, current_speed_kmh=15,
        delay_factor=2) | changes))


def view(*snapshots, when=NOW):
    policy = RankingPolicy()
    return {s.key: ResolvedSnapshot.resolve(s, when, getattr(policy, s.kind + '_fresh_s'))
            for s in snapshots}


def candidate(sid='S001', service=ServiceType.CHARGING, duration=100, **changes):
    return EvaluatedCandidate(**(dict(station_id=sid, service_type=service, eligible=True,
        reason='ELIGIBLE', station_latitude=21, station_longitude=105, soc_feasible=True,
        network_distance_m=1000,
        operational=StationOperationalSnapshot(operating_status='OPEN', available_service_slots=2,
            available_swap_batteries=3, available_capacity=2, queue_length=1,
            estimated_wait_min=2, service_time_min=18, state_timestamp=NOW.isoformat()),
        route_metrics=CandidateRouteMetrics(distance_to_station_m=1000,
            duration_to_station_s=duration, detour_duration_s=20, detour_distance_m=100)) | changes))


def evidence(candidates, baseline=None, segment='segment'):
    from backend.app.services.ranking.context import catalog_digest
    if baseline is None:
        baseline = view(*(s for sid in {c.station_id for c in candidates}
                          for s in (station(sid), queue(sid))))
    return CandidateSearchEvidence(request_time=NOW,
        energy_request=EnergyServiceRequest(service_request_id='energy', vehicle_id='V0001',
            timestamp=NOW, request_source='AUTO_DETECTED', need_service=True,
            allowed_service_types=list(ServiceType), reason_code='LOW_SOC', road_segment_id=segment),
        result=CandidateSearchResult(service_request_id='energy', total_candidates_evaluated=len(candidates),
            eligible_count=sum(c.eligible for c in candidates), candidates=candidates),
        snapshot_ids={key: value.snapshot_id for key, value in baseline.items()},
        catalog_digest=catalog_digest(station_catalog))


class HistoryResolver:
    def __init__(self, *snapshots):
        self.snapshots, self.calls = snapshots, []

    async def resolve(self, keys, when):
        self.calls.append((set(keys), when))
        return {key: ResolvedSnapshot.resolve(max(
            (s for s in self.snapshots if s.key == key and s.timestamp <= when),
            key=lambda s: s.timestamp, default=None), when,
            getattr(RankingPolicy(), key.split(':')[0] + '_fresh_s')) for key in keys}


def test_feature_arithmetic_and_canonical_station_service_time():
    from backend.app.services.ranking.context import build_features, operational_snapshot
    state = view(station(), queue(), traffic())
    op = operational_snapshot('S001', ServiceType.CHARGING, state)
    assert op.estimated_wait_min == 2 and op.service_time_min == 18
    f, = build_features(evidence([candidate()]), state, NOW, RankingPolicy(), station_catalog)
    assert (f.base_travel_duration_s, f.adjusted_travel_duration_s, f.traffic_adjustment_s) == (100, 200, 100)
    assert f.traffic_method == 'ORIGIN_SEGMENT_PROXY'
    assert (f.observed_queue_wait_s, f.effective_queue_wait_s, f.service_duration_s) == (120, 120, 1080)
    assert f.available_capacity == 2 and f.queue_assumption is None


@pytest.mark.asyncio
async def test_nearer_but_slower_and_top_n_applied_after_full_ranking():
    from backend.app.services.ranking.service import RankingService
    resolver = HistoryResolver(station(), queue(charging_estimated_wait_min=30),
                               station('S002'), queue('S002'), traffic())
    result = await RankingService(resolver).recommend(evidence([candidate(), candidate('S002', duration=200)]), top_n=1)
    assert result.recommended_station_id == 'S002' and result.eligible_count == 2
    assert len(result.ranked_candidates) == 1
    best = result.ranked_candidates[0]
    assert (best.eta_to_station_s, best.eta_to_service_start_s, best.final_cost_s) == (400, 520, 1600)
    assert best.eta_to_service_complete_s == best.final_cost_s
    assert best.penalty_components_s == {}


@pytest.mark.asyncio
async def test_zero_single_both_and_rejected_never_promoted():
    from backend.app.services.ranking.service import RankingService
    service = RankingService(HistoryResolver(station(), queue(), traffic()))
    rejected = candidate(eligible=False, reason='FULL', route_metrics=None)
    result = await service.recommend(evidence([rejected]))
    assert not result.has_recommendation and result.eligible_count == 0
    assert result.recommended_station_id is None and result.ranked_candidates == []
    for candidates in [[candidate()], [candidate(), candidate(service=ServiceType.BATTERY_SWAP)]]:
        result = await service.recommend(evidence(candidates))
        assert result.has_recommendation and result.eligible_count == len(candidates)
        assert len(result.ranked_candidates) == len(candidates)
    assert result.recommended_service_type == ServiceType.BATTERY_SWAP


@pytest.mark.parametrize('change,reason', [
    ({'operating_status': 'OFFLINE'}, 'OFFLINE'),
    ({'available_charging_slots': 0}, 'FULL'),
    ({'available_swap_batteries': 0}, 'NO_SWAP_BATTERY'),
])
def test_any_invalidated_candidate_fails_whole_set(change, reason):
    from backend.app.services.ranking.context import build_features
    service = ServiceType.BATTERY_SWAP if reason == 'NO_SWAP_BATTERY' else ServiceType.CHARGING
    candidates = [candidate('S002'), candidate(service=service)]
    state = view(station(**change), queue(), station('S002'), queue('S002'))
    with pytest.raises(CandidateStateChanged) as error:
        build_features(evidence(candidates), state, NOW, RankingPolicy(), station_catalog)
    assert error.value.status == 409
    assert error.value.detail['changed_candidates'] == [dict(station_id='S001', service_type=service.value,
        previous_state='ELIGIBLE', current_state=reason)]


@pytest.mark.asyncio
async def test_history_future_state_backfill_and_queue_limit_boundary():
    from backend.app.services.ranking.service import RankingService
    later = NOW + timedelta(minutes=5)
    old, newer = queue(), queue(timestamp=later, charging_estimated_wait_min=91)
    service = RankingService(HistoryResolver(station(), old, newer, traffic()))
    saved = evidence([candidate()])
    assert (await service.recommend(saved)).has_recommendation
    with pytest.raises(CandidateStateChanged) as error:
        await service.recommend(saved, request_time=later)
    assert error.value.detail['changed_candidates'][0]['current_state'] == 'EXCESSIVE_QUEUE'
    for wait in [5, 90]:
        result = await RankingService(HistoryResolver(station(), queue(charging_estimated_wait_min=wait))).recommend(saved)
        assert result.ranked_candidates[0].features.observed_queue_wait_s == wait * 60
    # Newly arrived evidence can change the head even at the original search time.
    with pytest.raises(CandidateStateChanged):
        await RankingService(HistoryResolver(station(operating_status='OFFLINE'), old)).recommend(saved)


@pytest.mark.asyncio
async def test_missing_queue_traffic_and_stale_state_are_visible():
    from backend.app.services.ranking.context import operational_snapshot
    from backend.app.services.ranking.service import RankingService
    resolver = HistoryResolver(station())
    later = NOW + timedelta(seconds=601)
    result = await RankingService(resolver).recommend(evidence([candidate()], segment=None), later)
    f = result.ranked_candidates[0].features
    assert f.observed_queue_wait_s is None and f.effective_queue_wait_s == 5400
    assert f.queue_assumption and f.queue_state.freshness == 'MISSING'
    assert f.traffic_state.freshness == 'MISSING' and f.traffic_method == 'BASE_DURATION_MISSING'
    assert f.base_travel_duration_s == f.adjusted_travel_duration_s
    assert f.station_state.freshness == 'STALE' and result.degraded
    assert all(not key.startswith('traffic:') for key in resolver.calls[0][0])
    op = operational_snapshot('S001', ServiceType.CHARGING, view(station()))
    assert op.estimated_wait_min is None and op.queue_length == 0
    with pytest.raises(StateError) as error:
        await RankingService(HistoryResolver()).recommend(evidence([candidate()]))
    assert error.value.status == 503


def test_catalog_digest_order_independence_and_static_change_conflict():
    from backend.app.services.ranking.context import build_features, catalog_digest
    class Catalog:
        def __init__(self, records): self.records = records
        def get_all_stations(self): return self.records
    records = station_catalog.get_all_stations()
    assert catalog_digest(Catalog(records[::-1])) == catalog_digest(station_catalog)
    modified = Catalog([replace(records[0], connector_type='changed'), *records[1:]])
    with pytest.raises(CandidateStateChanged) as error:
        build_features(evidence([candidate()]), view(station(), queue()), NOW, RankingPolicy(), modified)
    assert error.value.detail['changed_candidates'][0]['current_state'] == 'CATALOG_CHANGED'


@pytest.mark.parametrize('mutation', ['duplicate', 'reason', 'missing', 'nan', 'negative', 'infinite_detour'])
def test_malformed_eligible_evidence_fails_explicitly(mutation):
    from backend.app.services.ranking.context import build_features
    c = candidate()
    if mutation == 'reason': c = c.model_copy(update={'reason': 'FULL'})
    elif mutation == 'missing': c = c.model_copy(update={'route_metrics': None})
    elif mutation in ['nan', 'negative', 'infinite_detour']:
        changes = {'duration_to_station_s': float('nan') if mutation == 'nan' else -1}
        if mutation == 'infinite_detour': changes = {'detour_duration_s': float('inf')}
        c = c.model_copy(update={'route_metrics': c.route_metrics.model_copy(update=changes)})
    with pytest.raises(StateError) as error:
        build_features(evidence([c, c] if mutation == 'duplicate' else [c]),
                       view(station(), queue()), NOW, RankingPolicy(), station_catalog)
    assert error.value.status == 422


@pytest.mark.asyncio
async def test_rejects_request_before_evidence_and_invalid_top_n():
    from backend.app.services.ranking.service import RankingService
    service = RankingService(HistoryResolver(station(), queue()))
    for kwargs in [{'request_time': NOW - timedelta(seconds=1)}, {'top_n': 0}, {'top_n': -1}]:
        with pytest.raises(StateError) as error:
            await service.recommend(evidence([candidate()]), **kwargs)
        assert error.value.status == 422


def test_pure_ranking_near_ties_permutations_and_unrounded_cost():
    from backend.app.services.ranking.context import build_features
    from backend.app.services.ranking.service import rank_features
    state = view(station(), queue(), station('S002'), queue('S002'), station('S003'), queue('S003'))
    cs = [candidate('S003', duration=100.0001), candidate('S002', duration=100.0002), candidate(duration=100.0003)]
    features = build_features(evidence(cs, segment=None), state, NOW, RankingPolicy(), station_catalog)
    for permutation in permutations(features):
        ranked = rank_features(permutation)
        assert [r.station_id for r in ranked] == ['S001', 'S002', 'S003']
        assert ranked[0].final_cost_s == 1300.0003
        assert [r.rank for r in ranked] == [1, 2, 3]


@pytest.mark.asyncio
async def test_context_changes_recompute_cost_without_eligibility_or_routing(monkeypatch):
    from backend.app.services.candidate import eligibility
    from backend.app.services.ranking.service import RankingService
    def forbidden(*args, **kwargs): raise AssertionError('Ranking must not evaluate eligibility')
    monkeypatch.setattr(eligibility, 'evaluate_candidate_eligibility', forbidden)
    saved = evidence([candidate()])
    before = await RankingService(HistoryResolver(station(), queue(), traffic())).recommend(saved)
    after = await RankingService(HistoryResolver(station(charging_service_time_min=20),
        queue(charging_estimated_wait_min=10), traffic(delay_factor=3))).recommend(saved)
    assert before.ranked_candidates[0].final_cost_s == 1400
    assert after.ranked_candidates[0].final_cost_s == 2100
    assert after.energy_context == saved.energy_request


@pytest.mark.parametrize('change', [
    {'adjusted_travel_duration_s': 99, 'service_duration_s': 1081},
    {'detour_duration_s': 19},
    {'detour_duration_s': 20, 'detour_distance_m': 99},
    {'available_capacity': 3},
])
def test_completion_tie_breakers_in_documented_order(change):
    from backend.app.services.ranking.context import build_features
    from backend.app.services.ranking.service import rank_features
    f, = build_features(evidence([candidate()]), view(station(), queue()), NOW, RankingPolicy(), station_catalog)
    alternative = f.model_copy(update={'station_id': 'Z-LAST', **change})
    assert rank_features([f, alternative])[0].station_id == 'Z-LAST'
    assert rank_features([alternative, f])[0].station_id == 'Z-LAST'


def test_ties_missing_detour_freshness_capacity_and_composite_identity():
    from backend.app.services.ranking.context import build_features
    from backend.app.services.ranking.service import rank_features
    f, = build_features(evidence([candidate()]), view(station(), queue()), NOW, RankingPolicy(), station_catalog)
    for change in [{'detour_duration_s': None}, {'detour_distance_m': None},
                   {'station_state': ResolvedSnapshot.resolve(station(timestamp=NOW-timedelta(seconds=1)), NOW, 600)},
                   {'station_state': ResolvedSnapshot.resolve(None, NOW, 600)}]:
        worse = f.model_copy(update={'station_id': 'A-FIRST', **change})
        assert rank_features([worse, f])[0].station_id == f.station_id
    swap = f.model_copy(update={'service_type': ServiceType.BATTERY_SWAP})
    assert rank_features([f, swap])[0].service_type == ServiceType.BATTERY_SWAP


@pytest.mark.asyncio
async def test_offline_both_conflict_before_scoring_and_all_changes_reported(monkeypatch):
    from backend.app.services.ranking import service as ranking_module
    def forbidden(*args): raise AssertionError('No scoring before validating the whole candidate set')
    monkeypatch.setattr(ranking_module, 'rank_features', forbidden)
    saved = evidence([candidate(service=ServiceType.BATTERY_SWAP), candidate()])
    with pytest.raises(CandidateStateChanged) as error:
        await ranking_module.RankingService(HistoryResolver(station(operating_status='OFFLINE'), queue())).recommend(saved)
    changes = error.value.detail['changed_candidates']
    assert [c['service_type'] for c in changes] == ['BATTERY_SWAP', 'CHARGING']
    assert all(c['current_state'] == 'OFFLINE' for c in changes)


@pytest.mark.asyncio
async def test_stale_traffic_and_queue_remain_observed_with_missing_last_detour():
    from backend.app.services.ranking.service import RankingService
    later = NOW + timedelta(seconds=1801)
    c = candidate(route_metrics=CandidateRouteMetrics(distance_to_station_m=1000, duration_to_station_s=100))
    result = await RankingService(HistoryResolver(station(), queue(), traffic())).recommend(evidence([c]), later)
    f = result.ranked_candidates[0].features
    assert f.traffic_state.freshness == f.queue_state.freshness == 'STALE'
    assert f.detour_duration_s is None and f.detour_distance_m is None
    assert f.observed_queue_wait_s == 120 and f.queue_assumption is None
    assert f.adjusted_travel_duration_s == 200
    assert result.degraded_reasons == ['QUEUE_STALE', 'STATION_STALE', 'TRAFFIC_STALE']
