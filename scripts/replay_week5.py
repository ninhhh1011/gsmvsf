"""Finite source-only causal replay against an isolated, real Week 5 API.

The API must use the supplied empty schema/cache prefix and a fresh process.
Predictions are flushed before the separate evaluate_week5 command opens labels.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from time import perf_counter

import asyncpg
import httpx
import pandas as pd
from redis.asyncio import Redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_week4 import reconstruct_contexts
from backend.app.services.snapshots.ingestion import IngestionService
from backend.app.services.snapshots.models import snapshot_adapter
from backend.app.services.snapshots.repository import SnapshotRepository


def representative_trips(dataset: Path, count: int) -> pd.DataFrame:
    """Cover source scenarios and all three vehicle classes without label access."""
    trips = pd.read_csv(dataset / 'trips/trips.csv').merge(
        pd.read_csv(dataset / 'vehicles/vehicles.csv')[['vehicle_id', 'vehicle_type', 'swap_supported']],
        on='vehicle_id', validate='many_to_one')
    if not 3 <= count <= len(trips):
        raise ValueError(f'trajectories must be between 3 and {len(trips)}')
    trips['vehicle_class'] = trips.apply(lambda r: 'EV_CAR' if r.vehicle_type == 'EV_CAR'
        else 'SWAP_MOTORCYCLE' if r.swap_supported else 'CHARGE_ONLY_MOTORCYCLE', axis=1)
    selected = []
    for _, rows in trips.groupby('vehicle_class', sort=True):
        selected.append(rows.index[0])
    for _, rows in trips.groupby('scenario_id', sort=True):
        if len(selected) >= count:
            break
        if not set(rows.index) & set(selected):
            selected.append(rows.index[0])
    # Round-robin classes prevents a 30-trip replay from being almost entirely cars.
    groups = [list(rows.index) for _, rows in trips.groupby('vehicle_class', sort=True)]
    for indices in zip(*groups):
        for index in indices:
            if index not in selected and len(selected) < count:
                selected.append(index)
    for index in trips.index:
        if len(selected) < count and index not in selected:
            selected.append(index)
    return trips.loc[selected].sort_values('trip_id')


def source_schedule(dataset: Path, count: int):
    trips = representative_trips(dataset, count)
    selected = set(trips.trip_id)
    contexts = [row for row in reconstruct_contexts(dataset) if row['context']['trip_id'] in selected]
    gps = pd.read_csv(dataset / 'gps/gps_observations.csv.gz')
    events = pd.read_csv(dataset / 'realtime/events.csv.gz')
    updates = events[events.event_type.eq('GPS_UPDATE') & events.entity_id.isin(selected)]
    observation_ids = {json.loads(payload)['observation_id'] for payload in updates.payload_json}
    observation_ids.update(row['observation_id'] for row in contexts)
    gps = gps[gps.observation_id.isin(observation_ids)]
    trip_map = trips.set_index('trip_id').to_dict('index')
    schedule = [(pd.Timestamp(row['timestamp']), 0, row) for row in gps.to_dict('records')]
    schedule.extend((pd.Timestamp(row['event_timestamp']), 1, row) for row in contexts)
    schedule.sort(key=lambda item: (item[0], item[1], item[2].get('event_id', item[2].get('observation_id'))))
    return trips, trip_map, schedule


def gps_request(source, trip):
    request = {key: source[key] for key in ('observation_id', 'timestamp', 'latitude',
        'longitude', 'speed_kmh', 'heading_deg', 'accuracy_m') if pd.notna(source[key])}
    # Source rounding can encode north as 360; Week 1's wire contract uses [0, 360).
    if request.get('heading_deg') == 360.:
        request['heading_deg'] = 0.
    return request | {'vehicle_id': trip['vehicle_id'], 'vehicle_category': trip['vehicle_type']}


class CausalSnapshots:
    """Finite sorted source tables; only the prefix <= T may enter the database."""
    def __init__(self, dataset: Path):
        self.frames = []
        for kind, filename, entity in (
            ('station', 'stations/station_status.csv.gz', 'station_id'),
            ('queue', 'queue/queue_status.csv.gz', 'station_id'),
            ('traffic', 'traffic/traffic_snapshots.csv.gz', 'segment_id'),
        ):
            frame = pd.read_csv(dataset / filename).rename(columns={entity: 'entity_id'})
            # Preserve submicrosecond decision boundaries with pandas 3's inferred units.
            frame['timestamp'] = pd.to_datetime(frame.timestamp, format='mixed', utc=True).astype(
                'datetime64[ns, UTC]')
            frame = frame.sort_values(['timestamp', 'entity_id']).reset_index(drop=True)
            self.frames.append([kind, frame, 0])

    async def advance(self, time, ingestion, counts, batch_size=2000):
        for source in self.frames:
            kind, frame, position = source
            stop = int(frame.timestamp.searchsorted(time, side='right'))
            for start in range(position, stop, batch_size):
                rows = frame.iloc[start:min(start + batch_size, stop)].to_dict('records')
                snapshots = [snapshot_adapter.validate_python(row | {'kind': kind,
                    'source': 'dataset-v1.3.1'}) for row in rows]
                assert all(pd.Timestamp(s.timestamp) <= time for s in snapshots)
                await ingestion.ingest_many(snapshots)
                counts[f'{kind}_snapshots_ingested'] += len(snapshots)
            source[2] = stop


def assert_causal_result(result: dict, event_time):
    limit = pd.Timestamp(event_time)
    for stamp in (result['request_time'], result['energy_context']['timestamp'],
                  result.get('location_timestamp')):
        if stamp is not None and pd.Timestamp(stamp) > limit:
            raise ValueError('Future request/location state leaked into replay')
    for candidate in result['ranked_candidates']:
        for kind in ('station', 'queue', 'traffic'):
            state = candidate['features'][f'{kind}_state']
            if state['snapshot_timestamp'] and pd.Timestamp(state['snapshot_timestamp']) > limit:
                raise ValueError(f'Future {kind} state leaked into replay')


def prediction_row(source, result, evidence, mode, latency):
    ranked = []
    for candidate in result['ranked_candidates']:
        features = candidate['features']
        ranked.append({key: candidate[key] for key in ('station_id', 'service_type',
            'eta_to_station_s', 'eta_to_service_start_s', 'eta_to_service_complete_s', 'final_cost_s')} |
            {key: features[key] for key in ('distance_to_station_m', 'traffic_method',
                'effective_queue_wait_s', 'service_duration_s', 'available_capacity')})
    return dict(event_id=source['event_id'] if mode == 'AUTO' else source['event_id'] + ':' + mode,
        mode=mode, source=source, need_service=result['energy_context']['need_service'],
        candidate_search_id=result['candidate_search_id'], ranked=ranked,
        candidates=evidence['result']['candidates'], response=result, latency_ms=latency)


COUNTERS = ('events_processed', 'trajectories_replayed', 'recommendation_requests',
    'matched_position_uses', 'raw_gps_fallbacks', 'no_service_short_circuits', 'candidate_searches',
    'ranking_calls', 'zero_candidate_results', 'candidate_state_conflicts', 'one_retry_recoveries',
    'second_conflict_failures', 'recommendation_changes', 'unchanged_recommendations',
    'stale_observations', 'no_match_observations', 'heading_wrap_normalizations',
    'graphhopper_failures', 'total_errors')


def count_request_failure(counts, status, result):
    counts['total_errors'] += 1
    if status == 409 and result.get('error_code') == 'CANDIDATE_STATE_CHANGED':
        # /recommend propagates this only after its existing two bounded attempts.
        counts['second_conflict_failures'] += 1
        counts['candidate_state_conflicts'] += 2
        counts['candidate_searches'] += 2
        counts['ranking_calls'] += 2
    if status in (503, 504) and 'graphhopper' in json.dumps(result).lower():
        counts['graphhopper_failures'] += 1


async def replay(args):
    if not re.fullmatch(r'week5_[a-z0-9_]+', args.schema):
        raise ValueError('An isolated week5_ schema is required')
    if not args.cache_prefix.startswith('week5:') or not args.cache_prefix.endswith(':'):
        raise ValueError('A dedicated week5: cache prefix is required')
    output = Path(args.output).resolve()
    dataset = Path(args.dataset).resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'dataset_v1') or \
            output.is_relative_to(dataset):
        raise ValueError('Replay artifacts must stay inside the repository and outside Dataset')
    output.mkdir(parents=True, exist_ok=False)
    trips, trip_map, schedule = source_schedule(dataset, args.trajectories)
    snapshots = CausalSnapshots(dataset)
    counts = Counter({key: 0 for key in COUNTERS})
    counts['trajectories_replayed'] = len(trips)
    previous, first_gps, accepted = {}, {}, {}
    namespace = args.schema + ':'
    prediction_path = output / 'predictions.jsonl'
    manifest = dict(status='RUNNING', dataset='V1.3.1', trajectories=trips.to_dict('records'),
        scope='Finite source-selected trajectories; realtime GPS event subset plus GPS at SOC decisions; '
              'eight AUTO SOC decisions per trajectory, explicit intent probes at the first decision.',
        labels_opened_during_inference=False, schema=args.schema, cache_prefix=args.cache_prefix,
        api_url=args.api_url, started_at=pd.Timestamp.now(tz='UTC').isoformat())
    manifest['scheduled_gps_observations'] = sum(kind == 0 for _, kind, _ in schedule)
    manifest['scheduled_auto_decisions'] = sum(kind == 1 for _, kind, _ in schedule)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    async with asyncpg.create_pool(args.database_url, min_size=1, max_size=2,
            server_settings={'search_path': args.schema + ',public'}) as pool, \
            httpx.AsyncClient(base_url=args.api_url, timeout=120) as client, \
            Redis.from_url(args.redis_url, decode_responses=True) as redis:
        # Never clear a shared DB/cache: refuse reused state instead.
        local_tables = await pool.fetchval('SELECT count(*) FROM information_schema.tables '
            'WHERE table_schema=$1 AND table_name=ANY($2::text[])', args.schema,
            ['state_snapshots', 'candidate_searches'])
        if local_tables != 2:
            raise ValueError('Both replay tables must exist in the isolated schema; no public fallback')
        if await pool.fetchval('SELECT count(*) FROM state_snapshots') or \
                await pool.fetchval('SELECT count(*) FROM candidate_searches'):
            raise ValueError('Replay requires empty isolated snapshot/search tables')
        if [key async for key in redis.scan_iter(match=args.cache_prefix + '*')]:
            raise ValueError('Replay requires an empty isolated cache prefix')
        for trip_id in trips.trip_id:
            response = await client.get(f'/api/v1/drivers/{namespace + trip_id}/location')
            if response.status_code != 404:
                raise ValueError('Replay requires fresh, absent namespaced driver state')
        ingestion = IngestionService(SnapshotRepository(pool))
        with prediction_path.open('x', encoding='utf-8') as predictions, \
                (output / 'events.jsonl').open('x', encoding='utf-8') as events:
            for event_time, kind, source in schedule:
                counts['events_processed'] += 1
                if kind == 0:
                    trip = trip_map[source['trip_id']]
                    driver = namespace + source['trip_id']
                    request = gps_request(source, trip)
                    normalized = source['heading_deg'] == 360.
                    counts['heading_wrap_normalizations'] += normalized
                    response = await client.post(f'/api/v1/drivers/{driver}/location', json=request)
                    body = response.json()
                    if response.status_code != 200:
                        counts['total_errors'] += 1
                    elif body['status'] == 'ENGINE_UNAVAILABLE':
                        counts['graphhopper_failures'] += 1
                        counts['total_errors'] += 1
                    else:
                        accepted[driver] = event_time
                        first_gps.setdefault(driver, request)
                        counts['no_match_observations'] += body['status'] == 'NO_MATCH'
                    events.write(json.dumps(dict(timestamp=str(event_time), kind='GPS',
                        observation_id=source['observation_id'], trip_id=source['trip_id'],
                        source_heading_deg=source['heading_deg'] if pd.notna(source['heading_deg']) else None,
                        transmitted_heading_deg=request.get('heading_deg'), heading_normalized=normalized,
                        status_code=response.status_code, result=body)) + '\n')
                    continue
                await snapshots.advance(event_time, ingestion, counts)
                newest = await pool.fetchval('SELECT max(timestamp) FROM state_snapshots')
                if newest and pd.Timestamp(newest) > event_time:
                    raise ValueError('Future snapshot was preloaded into isolated replay database')
                context = source['context'].copy()
                driver = namespace + context['trip_id']
                context['driver_id'] = driver
                for field in ('raw_latitude', 'raw_longitude', 'road_segment_id'):
                    context.pop(field, None)
                if driver not in accepted or accepted[driver] > event_time:
                    raise ValueError('Missing/future accepted GPS before recommendation')
                request = dict(context=context, **{key: source[key] for key in (
                    'destination_latitude', 'destination_longitude', 'destination_node_id')})
                modes = ['AUTO']
                if source['snapshot_index'] == 1:
                    modes += ['CHARGING', 'ANY']
                    if trip_map[context['trip_id']]['swap_supported']:
                        modes.append('BATTERY_SWAP')
                for mode in modes:
                    payload = request if mode == 'AUTO' else request | {'requested_service': mode}
                    counts['recommendation_requests'] += 1
                    start = perf_counter()
                    response = await client.post('/api/v1/recommend', json=payload)
                    latency = (perf_counter() - start) * 1000
                    result = response.json()
                    if response.status_code != 200:
                        count_request_failure(counts, response.status_code, result)
                        events.write(json.dumps(dict(timestamp=str(event_time), kind='RECOMMEND_ERROR',
                            source=source, mode=mode, status_code=response.status_code, result=result)) + '\n')
                        continue
                    assert_causal_result(result, event_time)
                    raw = await pool.fetchval('SELECT payload FROM candidate_searches '
                        'WHERE candidate_search_id=$1', result['candidate_search_id'])
                    if raw is None:
                        raise ValueError('API is not writing evidence into the replay schema')
                    evidence = json.loads(raw)
                    if pd.Timestamp(evidence['request_time']) > event_time:
                        raise ValueError('Future candidate evidence')
                    async for cache_key in redis.scan_iter(match=args.cache_prefix + '*'):
                        cached = await redis.get(cache_key)
                        if cached and pd.Timestamp(json.loads(cached)['payload']['timestamp']) > event_time:
                            raise ValueError('Future snapshot in replay cache at decision time')
                    attempts = result.get('workflow_attempts', 1)
                    counts['candidate_searches'] += attempts
                    counts['ranking_calls'] += attempts
                    counts['candidate_state_conflicts'] += attempts - 1
                    counts['one_retry_recoveries'] += attempts - 1
                    counts['matched_position_uses'] += result.get('location_source') == 'MATCHED'
                    counts['raw_gps_fallbacks'] += result.get('location_source') == 'RAW_GPS_FALLBACK'
                    counts['no_service_short_circuits'] += not result['energy_context']['need_service']
                    counts['zero_candidate_results'] += result['eligible_count'] == 0
                    identity = (result['recommended_station_id'], result['recommended_service_type'])
                    key = (driver, mode)
                    if key in previous:
                        counts['recommendation_changes' if previous[key] != identity
                               else 'unchanged_recommendations'] += 1
                    previous[key] = identity
                    if result['energy_context']['need_service'] and mode == 'AUTO':
                        (output / 'benchmark-request.json').write_text(
                            json.dumps(payload, indent=2), encoding='utf-8')
                    predictions.write(json.dumps(prediction_row(source, result, evidence, mode, latency),
                        allow_nan=False) + '\n')
                    predictions.flush()
                if source['snapshot_index'] == 8:
                    response = await client.post(f'/api/v1/drivers/{driver}/location', json=first_gps[driver])
                    stale = response.status_code == 200 and response.json()['status'] == 'STALE_OBSERVATION'
                    counts['stale_observations'] += stale
                    counts['total_errors'] += not stale
                    events.write(json.dumps(dict(timestamp=str(event_time), kind='STALE_PROBE',
                        trip_id=context['trip_id'], status_code=response.status_code,
                        result=response.json())) + '\n')
                events.flush()
                print(f'{counts["recommendation_requests"]} requests / {counts["events_processed"]} events '
                      f'at {event_time}; errors={counts["total_errors"]}', flush=True)
                manifest['counters'] = dict(counts)
                (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        # Inspect cache payloads explicitly; schema causality applies at every earlier decision.
        async for key in redis.scan_iter(match=args.cache_prefix + '*'):
            value = await redis.get(key)
            if value and pd.Timestamp(json.loads(value)['payload']['timestamp']) > schedule[-1][0]:
                raise ValueError('Future snapshot in replay cache')
    manifest.update(status='PASS' if not counts['total_errors'] else 'PARTIAL',
        finished_at=pd.Timestamp.now(tz='UTC').isoformat(), counters=dict(counts),
        predictions_sha256=sha256(prediction_path.read_bytes()).hexdigest(),
        temporal_audit='Chronological GPS and SOC; source snapshots inserted only <= T; '
            'DB max timestamp checked at each decision; returned provenance checked; dedicated cache '
            'starts empty and can only load this causal DB; candidate evidence schema checked.',
        reliability_scope='Natural replay outcomes and stale probes; controlled dependency/conflict '
            'failures are reported separately by verify_week5.')
    benchmark_path = output / 'benchmark-request.json'
    if benchmark_path.exists():
        benchmark = json.loads(benchmark_path.read_text(encoding='utf-8'))
        # Performance exercises final current state, separate from historical predictions.
        benchmark['context']['timestamp'] = schedule[-1][0].isoformat()
        benchmark_path.write_text(json.dumps(benchmark, indent=2), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=str(ROOT / 'dataset_v1'))
    parser.add_argument('--api-url', default='http://127.0.0.1:8005')
    parser.add_argument('--database-url', default='postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation')
    parser.add_argument('--redis-url', default='redis://127.0.0.1:6379/0')
    parser.add_argument('--schema', required=True)
    parser.add_argument('--cache-prefix', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--trajectories', type=int, default=30)
    args = parser.parse_args()
    started = pd.Timestamp.now(tz='UTC')
    try:
        result = asyncio.run(replay(args))
    except Exception as exc:
        path = (Path(args.output) / 'manifest.json').resolve()
        if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / 'dataset_v1') and \
                not path.is_relative_to(Path(args.dataset).resolve()) and path.exists():
            manifest = json.loads(path.read_text(encoding='utf-8'))
            # Never overwrite evidence belonging to an earlier invocation.
            if pd.Timestamp(manifest['started_at']) >= started:
                manifest.update(status='FAIL', error=f'{type(exc).__name__}: {exc}',
                    counter_scope='Last completed decision; failed event may be absent.',
                    finished_at=pd.Timestamp.now(tz='UTC').isoformat())
                path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        raise
    print(json.dumps(result['counters'], indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
