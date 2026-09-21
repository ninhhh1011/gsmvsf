"""Replay scheduling and timestamp boundaries are independent of live dependencies."""
from pathlib import Path

import pandas as pd
import pytest

from collections import Counter
from scripts.replay_week5 import (
    CausalSnapshots, assert_causal_result, source_schedule, count_request_failure, gps_request,
)

ROOT = Path(__file__).resolve().parents[2]


def test_representative_schedule_uses_source_events_and_causal_gps(monkeypatch):
    read_csv = pd.read_csv
    def source_only(path, *args, **kwargs):
        assert not any(name in str(path) for name in ('demand_labels', 'candidate_labels',
            'recommendation_labels', 'ranking_reference', 'map_matching_labels')), 'Replay opened a label'
        return read_csv(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_csv', source_only)
    trips, _, schedule = source_schedule(ROOT / 'dataset_v1', 30)
    assert len(trips) == 30
    assert set(trips.vehicle_class) == {'EV_CAR', 'CHARGE_ONLY_MOTORCYCLE', 'SWAP_MOTORCYCLE'}
    assert {'NO_SERVICE_NEEDED', 'NEED_CHARGING', 'NEED_SWAP', 'QUEUE_REALTIME_CHANGE',
            'TRAFFIC_REALTIME_CHANGE', 'STATION_STATUS_CHANGE'} <= set(trips.scenario_id)
    assert schedule == sorted(schedule, key=lambda row: (row[0], row[1],
        row[2].get('event_id', row[2].get('observation_id'))))
    latest = {}
    decisions = 0
    for time, kind, source in schedule:
        if kind == 0:
            latest[source['trip_id']] = time
        else:
            decisions += 1
            assert latest[source['context']['trip_id']] <= time
            assert pd.Timestamp(source['gps_timestamp']) <= time
    assert decisions == 240


@pytest.mark.asyncio
async def test_source_snapshot_lookup_accepts_nanosecond_decision_time():
    source = CausalSnapshots(ROOT / 'dataset_v1')
    # One nanosecond before the first source snapshot: no ingestion is permitted.
    time = source.frames[0][1].timestamp.iloc[0] - pd.Timedelta(1, unit='ns')
    class Reject:
        async def ingest_many(self, batch):
            pytest.fail('Future snapshot ingestion')
    await source.advance(time, Reject(), Counter())


@pytest.mark.parametrize('field', ['request_time', 'location_timestamp', 'energy', 'traffic'])
def test_future_state_is_rejected(field):
    now, future = '2026-09-01T00:00:00Z', '2026-09-01T00:00:01Z'
    response = dict(request_time=now, location_timestamp=now, energy_context={'timestamp': now},
        ranked_candidates=[{'features': {f'{kind}_state': {'snapshot_timestamp': now}
            for kind in ('station', 'queue', 'traffic')}}])
    assert_causal_result(response, now)
    if field == 'energy':
        response['energy_context']['timestamp'] = future
    elif field == 'traffic':
        response['ranked_candidates'][0]['features']['traffic_state']['snapshot_timestamp'] = future
    else:
        response[field] = future
    with pytest.raises(ValueError, match='Future'):
        assert_causal_result(response, now)


@pytest.mark.asyncio
async def test_snapshot_advance_never_preloads_future_and_does_not_repeat_rows():
    times = pd.to_datetime(['2026-09-01T00:00:00Z', '2026-09-01T00:01:00Z'])
    frame = pd.DataFrame([dict(entity_id='segment', timestamp=stamp, traffic_level='FREE_FLOW',
        free_flow_speed_kmh=30., current_speed_kmh=30., delay_factor=1.) for stamp in times])
    source = CausalSnapshots.__new__(CausalSnapshots)
    source.frames = [['traffic', frame, 0]]
    ingested = []

    class Capture:
        async def ingest_many(self, batch):
            ingested.extend(batch)

    counts = Counter()
    await source.advance(times[0], Capture(), counts)
    await source.advance(times[0], Capture(), counts)
    assert [pd.Timestamp(row.timestamp) for row in ingested] == [times[0]]
    await source.advance(times[1], Capture(), counts)
    assert [pd.Timestamp(row.timestamp) for row in ingested] == list(times)
    assert counts['traffic_snapshots_ingested'] == 2


def test_failure_counters_separate_second_conflict_graphhopper_and_database():
    counts = Counter()
    count_request_failure(counts, 409, {'error_code': 'CANDIDATE_STATE_CHANGED'})
    assert counts == dict(total_errors=1, second_conflict_failures=1, candidate_state_conflicts=2,
                          candidate_searches=2, ranking_calls=2)
    count_request_failure(counts, 503, {'error_code': 'SNAPSHOT_DATABASE_UNAVAILABLE'})
    assert counts['graphhopper_failures'] == 0
    count_request_failure(counts, 504, {'detail': 'GraphHopper request timed out'})
    assert counts['graphhopper_failures'] == 1
    assert counts['total_errors'] == 3


@pytest.mark.parametrize('heading,expected', [(360., 0.), (0., 0.), (42., 42.), (361., 361.)])
def test_client_normalizes_only_equivalent_rounded_north_heading(heading, expected):
    source = dict(observation_id='gps', timestamp='2026-09-01T00:00:00Z', latitude=0.,
        longitude=0., speed_kmh=0., heading_deg=heading, accuracy_m=1.)
    result = gps_request(source, {'vehicle_id': 'car', 'vehicle_type': 'EV_CAR'})
    assert result['heading_deg'] == expected
    assert result['latitude'] == 0. and result['longitude'] == 0.
    assert source['heading_deg'] == heading
