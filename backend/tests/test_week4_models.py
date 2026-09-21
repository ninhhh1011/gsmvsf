from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def test_snapshot_contract_and_identity():
    from backend.app.services.snapshots.models import TrafficSnapshot
    values = dict(entity_id='segment', timestamp='2026-09-01T06:00:00+07:00',
                  source='dataset-v1.3.1', traffic_level='HEAVY',
                  free_flow_speed_kmh=30, current_speed_kmh=10, delay_factor=3)
    snapshot = TrafficSnapshot(**values)
    assert snapshot.timestamp == datetime(2026, 8, 31, 23, tzinfo=timezone.utc)
    assert snapshot.snapshot_id == TrafficSnapshot(**values).snapshot_id
    assert snapshot.snapshot_id != TrafficSnapshot(**(values | {'delay_factor': 4})).snapshot_id
    for field, value in [('delay_factor', -1), ('delay_factor', float('nan')),
                         ('current_speed_kmh', 0), ('timestamp', '2026-09-01T06:00:00'),
                         ('traffic_level', 'INVENTED'), ('extra', 1)]:
        with pytest.raises(ValidationError):
            TrafficSnapshot(**(values | {field: value}))
    with pytest.raises(ValidationError):
        snapshot.delay_factor = 4


def test_freshness_and_missing_provenance():
    from backend.app.services.snapshots.models import ResolvedSnapshot, TrafficSnapshot
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    snapshot = TrafficSnapshot(entity_id='segment', timestamp=now, source='test',
                               traffic_level='FREE_FLOW', free_flow_speed_kmh=30,
                               current_speed_kmh=30, delay_factor=1)
    from datetime import timedelta
    assert ResolvedSnapshot.resolve(snapshot, now, 600).freshness == 'FRESH'
    assert ResolvedSnapshot.resolve(snapshot, now + timedelta(seconds=601), 600).freshness == 'STALE'
    missing = ResolvedSnapshot.resolve(None, now, 600)
    assert missing.freshness == 'MISSING' and missing.snapshot_age_s is None
    with pytest.raises(ValueError):
        ResolvedSnapshot.resolve(snapshot, now - timedelta(seconds=1), 600)


def test_policy_rejects_unbounded_or_negative_assumptions():
    from backend.app.services.ranking.models import RankingPolicy, CandidateStateChanged
    assert RankingPolicy().missing_queue_wait_s == 5400
    with pytest.raises(ValidationError):
        RankingPolicy(missing_queue_wait_s=-1)
    error = CandidateStateChanged('search-1', [dict(station_id='S010',
        service_type='CHARGING', previous_state='ELIGIBLE', current_state='OFFLINE')])
    assert error.detail['error_code'] == 'CANDIDATE_STATE_CHANGED'
    assert error.detail['candidate_search_id'] == 'search-1'
    assert error.detail['action'] == 'RERUN_CANDIDATE_SEARCH'


def test_station_and_queue_contracts_reject_invalid_counts():
    from backend.app.services.snapshots.models import StationStateSnapshot, QueueSnapshot
    common = dict(entity_id='S001', timestamp='2026-09-01T06:00:00+07:00', source='test')
    station = dict(operating_status='OPEN', available_charging_slots=1,
        occupied_charging_slots=0, available_swap_slots=0, occupied_swap_slots=0,
        available_swap_batteries=0, charging_service_time_min=18, swap_service_time_min=0)
    queue = {f'{service}_{key}': value for service in ['charging', 'swap']
             for key, value in [('queue_length', 0), ('active_service_count', 0),
                                ('service_time_min', 0), ('estimated_wait_min', 0)]}
    assert StationStateSnapshot(**common, **station).kind == 'station'
    assert QueueSnapshot(**common, **queue).kind == 'queue'
    for value in [-1, 1.5, True]:
        with pytest.raises(ValidationError):
            StationStateSnapshot(**common, **(station | {'available_charging_slots': value}))
    with pytest.raises(ValidationError):
        QueueSnapshot(**common, **(queue | {'charging_estimated_wait_min': float('inf')}))


def test_provenance_cannot_claim_fresh_missing_state():
    from backend.app.services.snapshots.models import ResolvedSnapshot
    with pytest.raises(ValidationError):
        ResolvedSnapshot(snapshot=None, snapshot_id='fake', source='fake',
                         snapshot_timestamp=None, snapshot_age_s=0, freshness='FRESH')


def test_conflict_rejects_missing_composite_identity():
    from backend.app.services.ranking.models import CandidateStateChanged
    with pytest.raises(ValidationError):
        CandidateStateChanged('search', [{}])


@pytest.mark.parametrize('service', ['CHARGING', 'BATTERY_SWAP'])
def test_ranked_alternative_json_roundtrip(service):
    from backend.app.services.ranking.models import CandidateRankingFeatures, RankedCandidate
    from backend.app.services.snapshots.models import ResolvedSnapshot
    missing = ResolvedSnapshot.resolve(None, datetime.now(timezone.utc), 600)
    features = CandidateRankingFeatures(station_id='S010', service_type=service,
        base_travel_duration_s=60, adjusted_travel_duration_s=60, traffic_adjustment_s=0,
        traffic_method='BASE_DURATION_MISSING', observed_queue_wait_s=None,
        effective_queue_wait_s=5400, queue_assumption='PROJECT_POLICY', service_duration_s=360,
        detour_duration_s=None, detour_distance_m=None, distance_to_station_m=100,
        available_capacity=1, station_state=missing, queue_state=missing, traffic_state=missing)
    item = RankedCandidate(rank=1, station_id='S010', service_type=service, features=features,
        eta_to_station_s=60, eta_to_service_start_s=5460, eta_to_service_complete_s=5820,
        final_cost_s=5820)
    assert RankedCandidate.model_validate_json(item.model_dump_json()) == item


def test_recommendation_time_and_count_guards():
    from backend.app.services.ranking.models import RecommendationResult
    values = dict(candidate_search_id='search', request_time='2026-09-01T06:00:00+07:00',
        has_recommendation=False, recommended_station_id=None, recommended_service_type=None,
        ranked_candidates=[], eligible_count=0, policy={}, degraded=False, degraded_reasons=[],
        reason='NO_ELIGIBLE_CANDIDATES', energy_context=dict(service_request_id='energy',
        vehicle_id='V0001', timestamp='2026-09-01T06:00:00+07:00', request_source='AUTO_DETECTED',
        need_service=False, allowed_service_types=['CHARGING'], reason_code='SUFFICIENT_SOC_RANGE'))
    assert RecommendationResult(**values).request_time.utcoffset().total_seconds() == 0
    for change in [{'eligible_count': -1}, {'request_time': '2026-09-01T06:00:00'}]:
        with pytest.raises(ValidationError):
            RecommendationResult(**(values | change))
