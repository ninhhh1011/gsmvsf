"""Real Week 4 verification; synthetic September 3 state is explicitly labelled.

Run only after evaluation: this mutates persisted operational history and cache.
--smoke-only creates search evidence but does not ingest operational snapshots.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import statistics
import sys
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncpg
import httpx
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.models import RecommendationResult
from backend.app.services.ranking.service import rank_features
from backend.app.services.routing.engine import RoutingEngineUnavailableError, RoutingTimeoutError, raise_for_routing_failure
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, VehicleRoutingProfile
from backend.app.services.snapshots.models import QueueSnapshot, StateError, StationStateSnapshot, TrafficSnapshot
from backend.app.services.snapshots.repository import SnapshotRepository
from backend.app.services.snapshots.resolver import SnapshotCache, SnapshotResolver
from scripts.verify_graphhopper import INPUTS, dataset_cases, rows


def summary(samples, eligible_counts=()):
    values = sorted(samples)
    if not values:
        raise ValueError('At least one measurement is required')

    def percentile(fraction):
        position = (len(values) - 1) * fraction
        lower = int(position)
        return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)

    return dict(samples=len(values), median_ms=round(statistics.median(values), 3),
                p90_ms=round(percentile(.90), 3), p95_ms=round(percentile(.95), 3),
                max_ms=round(max(values), 3), latency_ms=[round(v, 3) for v in samples],
                eligible_counts=list(eligible_counts), percentile_method='linear interpolation')


def recommend_request(group, request):
    energy = request.energy_request
    return dict(context=dict(vehicle_id=energy.vehicle_id, driver_id=energy.driver_id,
        trip_id=energy.trip_id, timestamp=energy.timestamp.isoformat(),
        current_soc_pct=energy.current_soc_pct,
        estimated_remaining_range_km=energy.estimated_remaining_range_km,
        remaining_trip_distance_km=energy.remaining_trip_distance_km,
        raw_latitude=energy.latitude, raw_longitude=energy.longitude,
        road_segment_id=energy.road_segment_id), requested_service=(
            'ANY' if group == 'both' else 'BATTERY_SWAP' if group == 'swap' else 'CHARGING'),
        destination_latitude=request.destination_latitude,
        destination_longitude=request.destination_longitude,
        destination_node_id=request.destination_node_id)


async def post(client, path, payload, expected=(200,), headers=None):
    started = perf_counter()
    response = await client.post('/api/v1' + path, json=payload, headers=headers)
    elapsed = (perf_counter() - started) * 1000
    assert response.status_code in expected, (path, response.status_code, response.text[:1000])
    return response.json(), elapsed, response.status_code


async def search_rank(client, request, request_time=None):
    evidence, _, _ = await post(client, '/ranking/candidates', request.model_dump(mode='json'))
    payload = {'candidate_search_id': evidence['candidate_search_id']}
    if request_time is not None:
        payload['request_time'] = request_time.isoformat()
    result, elapsed, _ = await post(client, '/ranking', payload)
    assert result['eligible_count'] == evidence['result']['eligible_count']
    assert result['has_recommendation'] == (result['eligible_count'] > 0)
    return evidence, result, elapsed


async def smoke(client, cases):
    results = []
    for group in ('car', 'fixed_bike', 'swap', 'both'):
        request = next(request for name, request in cases if name == group)
        evidence, result, elapsed = await search_rank(client, request)
        orchestrated, recommend_ms, _ = await post(client, '/recommend', recommend_request(group, request))
        assert orchestrated['energy_context']['need_service']
        assert orchestrated['eligible_count'] == result['eligible_count']
        results.append(dict(case=group, trip_id=request.energy_request.trip_id,
            evaluated=evidence['result']['total_candidates_evaluated'],
            eligible_count=result['eligible_count'], ranking_http_ms=round(elapsed, 3),
            recommend_http_ms=round(recommend_ms, 3), recommend_status=200,
            selected_station=result['recommended_station_id'],
            selected_service=result['recommended_service_type']))
    return results


def operational(station, timestamp, source, open_station=True):
    state = StationStateSnapshot(entity_id=station.station_id, timestamp=timestamp, source=source,
        operating_status='OPEN' if open_station else 'OFFLINE',
        available_charging_slots=station.charging_slots if open_station else 0,
        occupied_charging_slots=0, available_swap_slots=station.swap_slots if open_station else 0,
        occupied_swap_slots=0, available_swap_batteries=station.swap_slots * 2 if open_station else 0,
        charging_service_time_min=18 if station.charging_slots else 0,
        swap_service_time_min=6 if station.swap_slots else 0)
    queue = QueueSnapshot(entity_id=station.station_id, timestamp=timestamp, source=source,
        charging_queue_length=0, charging_active_service_count=0,
        charging_service_time_min=state.charging_service_time_min, charging_estimated_wait_min=0,
        swap_queue_length=0, swap_active_service_count=0,
        swap_service_time_min=state.swap_service_time_min, swap_estimated_wait_min=0)
    return state, queue


async def ingest(client, snapshot):
    return await post(client, '/internal/snapshots/' + snapshot.kind,
                      snapshot.model_dump(mode='json'), expected=(200, 201))


def traffic_probe(timestamp, source):
    row = next(rows('traffic/traffic_snapshots.csv.gz'))
    free_flow = float(row['free_flow_speed_kmh'])
    return TrafficSnapshot(entity_id=row['segment_id'], timestamp=timestamp, source=source,
        traffic_level='HEAVY', free_flow_speed_kmh=free_flow,
        current_speed_kmh=free_flow / 2, delay_factor=2)


async def ingestion_probes(client, repository, timestamp, source):
    snapshot = traffic_probe(timestamp, source)
    before = await repository.heads([snapshot.key], timestamp - timedelta(seconds=1))
    saved, elapsed, status = await ingest(client, snapshot)
    assert status == 201 and saved['snapshot_id'] == snapshot.snapshot_id
    stored = await repository.payloads([snapshot.snapshot_id])
    assert stored[snapshot.snapshot_id] == snapshot
    assert await repository.heads([snapshot.key], timestamp) == {snapshot.key: snapshot.snapshot_id}
    assert await repository.heads([snapshot.key], timestamp - timedelta(seconds=1)) == before
    payload = snapshot.model_dump(mode='json')
    await post(client, '/internal/snapshots/traffic', payload, expected=(403,),
               headers={'X-Ingestion-Token': 'invalid-' + str(uuid4())})
    await post(client, '/internal/snapshots/traffic', payload, expected=(401,),
               headers={'X-Ingestion-Token': ''})
    station, _ = operational(station_catalog.get_all_stations()[0], timestamp, source)
    station_payload = station.model_dump(mode='json')
    await post(client, '/internal/snapshots/station', station_payload | {'entity_id': 'UNKNOWN_WEEK4'},
               expected=(422,))
    await post(client, '/internal/snapshots/station', station_payload | {
        'timestamp': timestamp.replace(tzinfo=None).isoformat()}, expected=(422,))
    return dict(traffic_status=status, traffic_snapshot_id=snapshot.snapshot_id,
        traffic_entity_id=snapshot.entity_id, traffic_delay_factor=2, traffic_ingestion_ms=round(elapsed, 3),
        traffic_payload_verified=True, prior_traffic_snapshot_id=before[snapshot.key],
        traffic_history_preserved=True, wrong_token_status=403, missing_token_status=401,
        unknown_station_status=422, naive_timestamp_status=422,
        traffic_scope='Synthetic speed update on a canonical source segment; no route/segment mapping asserted')


async def set_operations(client, timestamp, source, only_station=None):
    for station in station_catalog.get_all_stations():
        for snapshot in operational(station, timestamp, source,
                                    only_station is None or station.station_id == only_station):
            await ingest(client, snapshot)


async def dynamic_demo(client, repository, cache, cases, start, source):
    await set_operations(client, start, source)
    request = next(request for group, request in cases if group == 'car')
    request = request.model_copy(update={'energy_request': request.energy_request.model_copy(
        update={'timestamp': start})})
    evidence, before, _ = await search_rank(client, request)
    assert before['eligible_count'] >= 2, 'Queue flip requires two genuinely eligible alternatives'
    winner = before['recommended_station_id']
    master = station_catalog.get_station(winner)
    _, initial_queue = operational(master, start, source)
    queue = initial_queue.model_copy(update={'timestamp': start + timedelta(minutes=1),
        'charging_estimated_wait_min': 90.0, 'charging_queue_length': 1})
    created, _, status = await ingest(client, queue)
    assert status == 201 and created['created']
    retried, _, status = await ingest(client, queue)
    assert status == 200 and not retried['created'] and retried['snapshot_id'] == created['snapshot_id']
    conflicting = queue.model_copy(update={'charging_estimated_wait_min': 89.0})
    conflict, _, _ = await post(client, '/internal/snapshots/queue',
                                conflicting.model_dump(mode='json'), expected=(409,))
    rank_payload = dict(candidate_search_id=evidence['candidate_search_id'],
                        request_time=queue.timestamp.isoformat())
    after, _, _ = await post(client, '/ranking', rank_payload)
    assert after['eligible_count'] == before['eligible_count']
    assert after['recommended_station_id'] != winner, 'Queue update did not change recommendation'
    older = initial_queue.model_copy(update={'timestamp': start + timedelta(seconds=30)})
    await ingest(client, older)
    latest = (await cache.get_many([queue.key]))[queue.key]
    assert latest.snapshot_id == queue.snapshot_id
    pinned = await repository.heads([queue.key], start)
    assert pinned[queue.key] == initial_queue.snapshot_id
    historical, _, _ = await post(client, '/ranking', dict(candidate_search_id=evidence['candidate_search_id'],
                                                          request_time=start.isoformat()))
    assert historical['recommended_station_id'] == winner
    # A closed eligible station invalidates the whole stored set.
    offline, _ = operational(master, start + timedelta(minutes=2), source, False)
    await ingest(client, offline)
    invalidated, _, _ = await post(client, '/ranking', dict(candidate_search_id=evidence['candidate_search_id'],
        request_time=offline.timestamp.isoformat()), expected=(409,))
    assert invalidated['error_code'] == 'CANDIDATE_STATE_CHANGED'
    assert invalidated['action'] == 'RERUN_CANDIDATE_SEARCH'
    # Make precisely one compatible, reachable station operational; no top_n shortcut.
    single_time = start + timedelta(minutes=3)
    await set_operations(client, single_time, source, only_station=winner)
    single_request = request.model_copy(update={'energy_request': request.energy_request.model_copy(
        update={'timestamp': single_time})})
    _, single, _ = await search_rank(client, single_request)
    assert single['eligible_count'] == len(single['ranked_candidates']) == 1
    zero_time = start + timedelta(minutes=4)
    await set_operations(client, zero_time, source, only_station='NO_STATION')
    zero_request = request.model_copy(update={'energy_request': request.energy_request.model_copy(
        update={'timestamp': zero_time})})
    _, zero, _ = await search_rank(client, zero_request)
    assert zero['eligible_count'] == 0 and not zero['has_recommendation']
    await set_operations(client, start + timedelta(minutes=5), source)
    return request, dict(source=source, start=start.isoformat(), before_station=winner,
        after_station=after['recommended_station_id'], eligible_count=before['eligible_count'],
        queue_wait_before_min=0, queue_wait_after_min=90, same_search_id=evidence['candidate_search_id'],
        newer_snapshot_id=queue.snapshot_id, older_snapshot_id=older.snapshot_id,
        historical_snapshot_id=pinned[queue.key], historical_station=historical['recommended_station_id'],
        latest_cache_not_regressed=True, retry_status=200, conflicting_retry_status=409,
        conflict_payload=conflict, candidate_state_conflict=invalidated,
        true_single_eligible_count=single['eligible_count'], zero_eligible_count=zero['eligible_count'])


def routing_failure_evidence(route):
    try:
        raise_for_routing_failure(route)
    except (RoutingEngineUnavailableError, RoutingTimeoutError) as exc:
        assert route.engine_name == 'graphhopper'
        return dict(route_status=route.status.value, exception=type(exc).__name__,
                    http_status=504 if isinstance(exc, RoutingTimeoutError) else 503)
    raise AssertionError('Unavailable GraphHopper must fail explicitly')


async def failures(repository, cache, request, dsn, timestamp):
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.main import create_app
    from backend.app.services.ranking.orchestration import RecommendationWorkflow

    async def http_probe(workflow, path, payload, expected):
        app = create_app()
        app.dependency_overrides[get_workflow] = lambda: workflow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                      base_url='http://in-process') as api:
            result, _, status = await post(api, path, payload,
                expected=expected if isinstance(expected, tuple) else (expected,))
        return {'status': status, 'response': result}

    request = request.model_copy(update={'energy_request': request.energy_request.model_copy(
        update={'timestamp': timestamp})})
    payload = request.model_dump(mode='json')
    http_results = {}
    key = 'station:' + station_catalog.get_all_stations()[0].station_id
    await cache.populate_latest(repository, [key])
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]  # Bound but not listening: no service can take this port.
        async with httpx.AsyncClient(timeout=10) as routing_client:
            good_adapter = GraphHopperRoutingAdapter(client=routing_client)
            redis = Redis(host='127.0.0.1', port=port, socket_timeout=.2, socket_connect_timeout=.2,
                          retry=Retry(NoBackoff(), 0))
            try:
                resolver = SnapshotResolver(repository, SnapshotCache(redis))
                resolved = await resolver.resolve([key], timestamp)
                assert resolved[key].snapshot is not None and resolver.metrics['cache_error'] > 0
                workflow = RecommendationWorkflow(repository, resolver, good_adapter)
                http_results['redis_unavailable'] = await http_probe(
                    workflow, '/ranking/candidates', payload, 200)
                evidence = http_results['redis_unavailable']['response']
                assert evidence['result']['search_status'] == 'SUCCESS'
                recommendation = await http_probe(workflow, '/ranking',
                    {'candidate_search_id': evidence['candidate_search_id']}, 200)
                ranked = recommendation['response']
                assert ranked['has_recommendation'] and ranked['eligible_count'] > 0
                http_results['redis_unavailable'] = {
                    'search_status': 200, 'ranking_status': recommendation['status'],
                    'candidate_search_id': evidence['candidate_search_id'],
                    'eligible_count': ranked['eligible_count'],
                    'selected_station_id': ranked['recommended_station_id'],
                    'selected_service_type': ranked['recommended_service_type']}
            finally:
                await redis.aclose()
            async with asyncpg.create_pool(dsn, host='127.0.0.1', port=port, min_size=0,
                                           max_size=1, timeout=.3) as bad_pool:
                bad_repository = SnapshotRepository(bad_pool, timeout_s=.5)
                bad_resolver = SnapshotResolver(bad_repository, cache)
                try:
                    await bad_resolver.resolve([key], timestamp)
                except StateError as exc:
                    assert exc.status == 503
                    database_error = exc.detail
                else:
                    raise AssertionError('Warm Redis masked unavailable PostgreSQL')
                workflow = RecommendationWorkflow(bad_repository, bad_resolver, good_adapter)
                http_results['database_unavailable'] = await http_probe(workflow, '/ranking',
                    {'candidate_search_id': evidence['candidate_search_id']}, 503)
            adapter = GraphHopperRoutingAdapter(base_url=f'http://127.0.0.1:{port}',
                                                timeout_seconds=.3, client=routing_client)
            energy = request.energy_request
            route = await adapter.route(RouteRequest(
                origin=Position(latitude=energy.latitude, longitude=energy.longitude),
                destination=Position(latitude=request.destination_latitude, longitude=request.destination_longitude),
                profile=VehicleRoutingProfile(vehicle_category=energy.vehicle_type)))
            routing_error = routing_failure_evidence(route)
            workflow = RecommendationWorkflow(repository, SnapshotResolver(repository, cache), adapter)
            http_results['graphhopper_unavailable'] = await http_probe(
                workflow, '/ranking/candidates', payload, (503, 504))
            assert http_results['graphhopper_unavailable']['response']['detail']
    return dict(method='Real unavailable connections using a bound, non-listening local port '
                       '(connection refusal or timeout depends on the operating system); '
                       'real workflows through in-process ASGI HTTP routes; deployed services remain running',
                in_process_http=http_results,
                redis_falls_back_to_database=True, redis_metrics=dict(resolver.metrics),
                database_with_warm_cache_status=503, database_error=database_error,
                graphhopper_route_status=routing_error['route_status'],
                graphhopper_exception=routing_error['exception'],
                graphhopper_service_error_http_status=routing_error['http_status'])


async def performance(client, repository, cache, request, start, source, samples):
    measurements = []
    station = station_catalog.get_all_stations()[0]
    for index in range(samples):
        _, queue = operational(station, start + timedelta(minutes=5, seconds=index + 1), source)
        _, elapsed, status = await ingest(client, queue)
        assert status == 201
        measurements.append(elapsed)
    report = {'ingestion_http_new_rows': summary(measurements)}
    request_time = start + timedelta(minutes=6, seconds=samples)
    request = request.model_copy(update={'energy_request': request.energy_request.model_copy(
        update={'timestamp': request_time})})
    evidence, ranked, _ = await search_rank(client, request)
    features = [row.features for row in RecommendationResult.model_validate(ranked).ranked_candidates]
    timings = []
    for _ in range(samples):
        began = perf_counter()
        result = rank_features(features)
        timings.append((perf_counter() - began) * 1000)
        assert len(result) == ranked['eligible_count']
    report['ranking_pure_in_process'] = summary(timings, [len(features)] * samples)
    keys = [f'{kind}:{station.station_id}' for station in station_catalog.get_all_stations()
            for kind in ('station', 'queue')]
    resolver = SnapshotResolver(repository, cache)
    for mode in ('hit', 'miss'):
        timings = []
        resolver.metrics.clear()
        for _ in range(samples):
            if mode == 'miss':
                await cache.client.delete(*(cache.key(key) for key in keys))
            else:
                await cache.populate_latest(repository, keys)
            began = perf_counter()
            await resolver.resolve(keys, request_time)
            timings.append((perf_counter() - began) * 1000)
        assert resolver.metrics['cache_' + mode] == len(keys) * samples
        report['snapshot_lookup_cache_' + mode] = summary(timings) | {'metrics': dict(resolver.metrics)}
    for endpoint, payload in [('/ranking', dict(candidate_search_id=evidence['candidate_search_id'],
                                              request_time=request_time.isoformat())),
                              ('/recommend', recommend_request('car', request))]:
        for mode in ('hit', 'miss'):
            timings, counts = [], []
            for _ in range(samples):
                if mode == 'miss':
                    await cache.client.delete(*(cache.key(key) for key in keys))
                else:
                    await cache.populate_latest(repository, keys)
                result, elapsed, _ = await post(client, endpoint, payload)
                timings.append(elapsed)
                counts.append(result['eligible_count'])
            report[endpoint.strip('/') + '_http_cache_' + mode] = summary(timings, counts)
    report['recommend_http_concurrency'] = {}
    for concurrency in (1, 5, 10):
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one():
            async with semaphore:
                result, elapsed, _ = await post(client, '/recommend', recommend_request('car', request))
                return elapsed, result['eligible_count']

        values = await asyncio.gather(*(run_one() for _ in range(samples)))
        report['recommend_http_concurrency'][str(concurrency)] = summary(
            [row[0] for row in values], [row[1] for row in values]) | {
                'requested_concurrency': concurrency, 'effective_concurrency': min(samples, concurrency)}
    return report, request_time


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=10)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime/week4/backend-report.json')
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--database-url', default='postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation')
    parser.add_argument('--redis-url', default='redis://127.0.0.1:6379/0')
    parser.add_argument('--token-file', type=Path, default=ROOT / 'runtime/week4/ingestion-token.txt')
    parser.add_argument('--smoke-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.samples <= 100:
        parser.error('--samples must be between 1 and 100')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'dataset_v1'):
        parser.error('--output must be inside the repository and outside dataset_v1')
    report = dict(status='RUNNING', timestamp_utc=datetime.now(timezone.utc).isoformat(),
        scope='INITIAL LOCAL WEEK 4 BACKEND PERFORMANCE BASELINE', api_url=args.api_url,
        runtime_inputs=INPUTS + ['stations/stations.csv', 'traffic/traffic_snapshots.csv.gz',
                                'PostgreSQL persisted source snapshots'],
        labels_consumed=False, mode='smoke-only' if args.smoke_only else 'full',
        limitations=['Local laptop measurements; no production throughput or SLA claim.',
                     'Performance uses one real car trip; four vehicle/service categories covered by smoke.',
                     'HTTP cache misses clear only snapshot keys used by this experiment.',
                     'Failure probes exercise in-process HTTP with real unavailable connections; deployed services remain running.'])
    try:
        cases = dataset_cases()
        headers = {} if args.smoke_only else {'X-Ingestion-Token': args.token_file.read_text('utf-8').strip()}
        async with httpx.AsyncClient(base_url=args.api_url, headers=headers, timeout=120) as client:
            report['smoke'] = await smoke(client, cases)
            print('PASS source-based live API smoke', flush=True)
            if not args.smoke_only:
                dsn = args.database_url.replace('postgresql+asyncpg://', 'postgresql://')
                redis = Redis.from_url(args.redis_url, socket_timeout=.3, socket_connect_timeout=.3)
                try:
                    assert await redis.ping()
                    async with asyncpg.create_pool(dsn, min_size=1, max_size=3, timeout=5) as pool:
                        repository, cache = SnapshotRepository(pool), SnapshotCache(redis)
                        day = datetime(2026, 9, 3, tzinfo=timezone.utc)
                        last = await pool.fetchval('SELECT max(timestamp) FROM state_snapshots '
                            'WHERE timestamp >= $1 AND timestamp < $2', day, day + timedelta(days=1))
                        start = last + timedelta(minutes=1) if last else day
                        assert start + timedelta(minutes=10) < day + timedelta(days=1), 'September 3 demo window exhausted'
                        source = 'week4-verification:' + str(uuid4())
                        try:
                            report['ingestion_probes'] = await ingestion_probes(
                                client, repository, start, source)
                            request, report['dynamic'] = await dynamic_demo(
                                client, repository, cache, cases, start, source)
                            print('PASS dynamic queue flip, history, retries, conflict, single and zero', flush=True)
                            report['performance'], request_time = await performance(
                                client, repository, cache, request, start, source, args.samples)
                            report['failure_probes'] = await failures(repository, cache, request, dsn, request_time)
                        finally:
                            # Keep all evidence/history; restore operational serviceability with newer rows.
                            await set_operations(client, start + timedelta(minutes=9), source)
                            report['restored_open_at'] = (start + timedelta(minutes=9)).isoformat()
                finally:
                    await redis.aclose()
        report['status'] = 'PASS'
    except Exception as exc:
        report.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(f'Evidence: {output}', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
