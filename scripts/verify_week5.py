"""Week 5 request-driven refresh and real dependency verification.

Use a dedicated empty week5_* PostgreSQL schema and week5:* Redis namespace.
Canonical Dataset and the shared production history are never changed.
"""
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import socket
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
from backend.app.services.ranking.orchestration import RecommendationWorkflow
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.snapshots.repository import SnapshotRepository
from backend.app.services.snapshots.resolver import SnapshotCache, SnapshotResolver
from scripts.verify_graphhopper import dataset_cases, rows
from scripts.verify_week4 import (ingest, operational, post, recommend_request,
                                 search_rank, set_operations, traffic_probe)


def validate_isolation(schema, prefix):
    if not schema.startswith('week5_') or not schema.replace('_', '').isalnum():
        raise ValueError('Verification requires a dedicated week5_* schema')
    if not prefix.startswith('week5:') or not prefix.endswith(':'):
        raise ValueError('Verification requires a dedicated week5:*: Redis prefix')


def at_time(payload, timestamp):
    payload = deepcopy(payload)
    payload['context']['timestamp'] = timestamp.isoformat()
    return payload


async def refresh_probes(client, request, start, source):
    # At this first timestamp only station state exists: queue/traffic absence
    # must be explicit in features, without inventing observations.
    for station in station_catalog.get_all_stations():
        await ingest(client, operational(station, start, source)[0])
    payload = at_time(recommend_request('car', request), start)
    missing, _, _ = await post(client, '/recommend', payload)
    assert missing['eligible_count'] >= 2, 'Probe needs two genuinely eligible alternatives'
    assert missing['degraded']
    for row in missing['ranked_candidates']:
        assert row['features']['queue_state']['freshness'] == 'MISSING'
        assert row['features']['traffic_state']['freshness'] == 'MISSING'
    stamp = start + timedelta(seconds=10)
    await set_operations(client, stamp, source)
    before, _, _ = await post(client, '/recommend', at_time(payload, stamp))
    same, _, _ = await post(client, '/recommend', at_time(payload, stamp))
    assert same['recommended_station_id'] == before['recommended_station_id']
    assert same['candidate_search_id'] != before['candidate_search_id']
    winner = before['recommended_station_id']
    station = station_catalog.get_station(winner)
    _, queue = operational(station, stamp + timedelta(seconds=10), source)
    queue = queue.model_copy(update={'charging_estimated_wait_min': 90.0, 'charging_queue_length': 1})
    await ingest(client, queue)
    changed, _, _ = await post(client, '/recommend', at_time(payload, queue.timestamp))
    assert changed['recommended_station_id'] != winner
    # Controlled canonical segment input makes the traffic update visible in ranking.
    # This is a synthetic context probe, not a claim of matched segment identity.
    traffic = traffic_probe(stamp + timedelta(seconds=20), source)
    await ingest(client, traffic)
    traffic_payload = at_time(payload, traffic.timestamp)
    traffic_payload['context']['road_segment_id'] = traffic.entity_id
    traffic_result, _, _ = await post(client, '/recommend', traffic_payload)
    assert all(r['features']['traffic_state']['snapshot_id'] == traffic.snapshot_id
               for r in traffic_result['ranked_candidates'])
    # Search once; mutate the persisted station version before rank. Both
    # OFFLINE and capacity FULL must reject the whole old eligible set.
    conflicts = []
    for index, reason in enumerate(('OFFLINE', 'FULL')):
        current = start + timedelta(minutes=1 + index)
        await set_operations(client, current, source)
        current_request = request.model_copy(update={'energy_request': request.energy_request.model_copy(update={'timestamp': current})})
        evidence, ranked, _ = await search_rank(client, current_request)
        selected = station_catalog.get_station(ranked['recommended_station_id'])
        state, _ = operational(selected, current + timedelta(seconds=1), source, reason != 'OFFLINE')
        if reason == 'FULL':
            state = state.model_copy(update={'available_charging_slots': 0, 'available_swap_slots': 0})
        await ingest(client, state)
        conflict, _, status = await post(client, '/ranking', dict(candidate_search_id=evidence['candidate_search_id'],
            request_time=state.timestamp.isoformat()), expected=(409,))
        assert conflict['error_code'] == 'CANDIDATE_STATE_CHANGED'
        assert reason in [row['current_state'] for row in conflict['changed_candidates']]
        conflicts.append({'reason': reason, 'status': status, 'response': conflict})
    zero_time = start + timedelta(minutes=3)
    await set_operations(client, zero_time, source, only_station='NO_STATION')
    zero, _, _ = await post(client, '/recommend', at_time(payload, zero_time))
    assert not zero['has_recommendation'] and zero['eligible_count'] == 0
    await set_operations(client, start + timedelta(minutes=4), source)
    return dict(missing_queue_traffic='PASS', initial_station=winner,
        changed_station=changed['recommended_station_id'], recommendation_changes=1,
        unchanged_recommendations=1, refresh_new_search_evidence=True,
        traffic_snapshot_id=traffic.snapshot_id, traffic_update='PASS',
        traffic_scope='Synthetic road_segment_id using a canonical segment, no matched-origin claim',
        invalidations=conflicts, zero_candidates=zero['eligible_count'])


async def location_probes(client, request, start):
    payload = at_time(recommend_request('car', request), start)
    driver = 'week5-probe-' + uuid4().hex
    payload['context']['driver_id'] = driver
    latitude = payload['context'].pop('raw_latitude')
    longitude = payload['context'].pop('raw_longitude')
    missing, _, missing_status = await post(client, '/recommend', payload, expected=(422,))
    assert missing['error_code'] == 'LOCATION_UNAVAILABLE'
    raw = dict(timestamp=start.isoformat(), vehicle_id=request.energy_request.vehicle_id,
               observation_id='accepted', latitude=latitude, longitude=longitude)
    accepted, _, _ = await post(client, f'/drivers/{driver}/location', raw)
    assert accepted['status'] == 'WARMING_UP'
    result, _, _ = await post(client, '/recommend', payload)
    assert result['location_source'] == 'RAW_GPS_FALLBACK'
    stale, _, _ = await post(client, f'/drivers/{driver}/location', raw | {
        'observation_id': 'stale', 'timestamp': (start-timedelta(seconds=1)).isoformat()})
    assert stale['status'] == 'STALE_OBSERVATION'
    again, _, _ = await post(client, '/recommend', payload)
    assert again['location_timestamp'] == result['location_timestamp']
    invalid, _, invalid_status = await post(client, '/recommend', payload | {'requested_service': 'BATTERY_SWAP'}, expected=(422,))
    assert invalid['error_code'] == 'INVALID_ENERGY_REQUEST'
    no_service = deepcopy(payload)
    no_service.pop('requested_service')
    no_service['context'].update(driver_id='week5-no-state-'+uuid4().hex,
        current_soc_pct=95, estimated_remaining_range_km=200, remaining_trip_distance_km=1)
    none, _, _ = await post(client, '/recommend', no_service)
    assert not none['energy_context']['need_service'] and not none['has_recommendation']
    return dict(missing_location_status=missing_status, raw_fallback=result['location_source'],
        stale_status=stale['status'], stale_did_not_replace_current=True,
        invalid_explicit_status=invalid_status, no_service_short_circuit=True)


async def conflict_retry_probe(repository, cache, request, start, source, change_twice):
    """Real PG/GH workflow; schedule real ingestion after search, no fake results."""
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.main import create_app
    base = start + timedelta(minutes=6 if change_twice else 5)
    for station in station_catalog.get_all_stations():
        for snapshot in operational(station, base, source):
            await repository.ingest(snapshot)
    payload = at_time(recommend_request('car', request), base + timedelta(seconds=10))
    searches = []
    async with httpx.AsyncClient(timeout=30) as routing_client:
        adapter = GraphHopperRoutingAdapter(client=routing_client)
        workflow = RecommendationWorkflow(repository, SnapshotResolver(repository, cache), adapter)
        original = workflow.search
        async def search_then_ingest(search_request):
            evidence = await original(search_request)
            searches.append(evidence)
            assert len(searches) <= 2, 'Unbounded search retry'
            if len(searches) == 1 or change_twice:
                candidate = next(c for c in evidence.result.candidates if c.eligible)
                state, _ = operational(station_catalog.get_station(candidate.station_id),
                    base + timedelta(seconds=len(searches)), source, False)
                await repository.ingest(state)
            return evidence
        workflow.search = search_then_ingest
        app = create_app()
        app.dependency_overrides[get_workflow] = lambda: workflow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://in-process') as client:
            result, _, status = await post(client, '/recommend', payload, expected=(409 if change_twice else 200,))
    assert len(searches) == 2
    if change_twice:
        assert result['error_code'] == 'CANDIDATE_STATE_CHANGED'
    else:
        assert result['workflow_attempts'] == 2
        assert result['candidate_search_id'] == searches[1].candidate_search_id
    return dict(status=status, searches=len(searches), ranking_calls=2,
        conflicts=2 if change_twice else 1, recovered=not change_twice,
        method='Real in-process FastAPI /recommend with real PostgreSQL, Redis and GraphHopper; timed ingestion after real search')


async def dependency_probes(repository, cache, request, dsn, timestamp):
    """Refuse real connections; exercise /recommend and actual Week 1 matching."""
    from backend.app.api.v1 import map_match
    from backend.app.api.v1.ranking import get_workflow
    from backend.app.main import create_app
    from backend.app.services.map_matching import GraphHopperMapMatchingAdapter
    from backend.app.services.realtime.state import get_state_store
    payload = at_time(recommend_request('car', request), timestamp)
    async def probe(workflow, expected):
        app = create_app()
        app.dependency_overrides[get_workflow] = lambda: workflow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://in-process') as api:
            result, _, status = await post(api, '/recommend', payload, expected=expected)
        return result, status
    report = {'method': 'Real in-process FastAPI HTTP with real adapters and bound non-listening sockets; no fake responses'}
    keys = [f'{kind}:{s.station_id}' for s in station_catalog.get_all_stations() for kind in ('station', 'queue')]
    await cache.populate_latest(repository, keys)
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
        async with httpx.AsyncClient(timeout=10) as routing_client:
            good_adapter = GraphHopperRoutingAdapter(client=routing_client)
            unavailable_redis = Redis(host='127.0.0.1', port=port, socket_timeout=.2, socket_connect_timeout=.2,
                                      retry=Retry(NoBackoff(), 0))
            try:
                resolver = SnapshotResolver(repository, SnapshotCache(unavailable_redis))
                result, status = await probe(RecommendationWorkflow(repository, resolver, good_adapter), (200,))
                assert result['has_recommendation'] and resolver.metrics['cache_error'] > 0
                report['redis_unavailable'] = dict(status=status, database_fallback=True, cache_metrics=dict(resolver.metrics))
            finally:
                await unavailable_redis.aclose()
            async with asyncpg.create_pool(dsn, host='127.0.0.1', port=port, min_size=0, max_size=1, timeout=.3) as bad_pool:
                bad_repository = SnapshotRepository(bad_pool, timeout_s=.5)
                result, status = await probe(RecommendationWorkflow(bad_repository,
                    SnapshotResolver(bad_repository, cache), good_adapter), (503,))
                report['postgresql_unavailable'] = dict(status=status, warm_cache_not_authoritative=True, response=result)
            bad_adapter = GraphHopperRoutingAdapter(base_url=f'http://127.0.0.1:{port}', timeout_seconds=.3, client=routing_client)
            result, status = await probe(RecommendationWorkflow(repository, SnapshotResolver(repository, cache), bad_adapter), (503, 504))
            report['graphhopper_unavailable'] = dict(status=status, response=result)
            # Configure the actual production matching adapter factory only in this
            # isolated verification process. Always restore it and remove our state.
            original_factory = map_match.get_map_matching_adapter
            driver = 'week5-gh-outage-' + uuid4().hex
            observations = []
            try:
                map_match.get_map_matching_adapter = lambda: GraphHopperMapMatchingAdapter(
                    base_url=f'http://127.0.0.1:{port}', timeout=.3, client=routing_client)
                app = create_app()
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://in-process') as api:
                    for row in rows('gps/gps_observations.csv.gz'):
                        if row['trip_id'] != request.energy_request.trip_id:
                            continue
                        observation = dict(vehicle_id=request.energy_request.vehicle_id,
                            observation_id=row['observation_id'], timestamp=row['timestamp'],
                            latitude=float(row['latitude']), longitude=float(row['longitude']))
                        result, _, status = await post(api, f'/drivers/{driver}/location', observation)
                        observations.append(dict(observation_id=row['observation_id'], status=result['status']))
                        if result['status'] == 'ENGINE_UNAVAILABLE':
                            break
                        assert len(observations) < 50, 'Source trace did not trigger matching in 50 observations'
                assert observations[-1]['status'] == 'ENGINE_UNAVAILABLE'
                assert get_state_store().get(driver).last_matched_state is None
                report['week1_graphhopper_unavailable'] = dict(status=status, observation_count=len(observations),
                    observations=observations, no_false_matched_position=True)
            finally:
                map_match.get_map_matching_adapter = original_factory
                get_state_store().remove(driver)
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8006')
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--redis-url', default='redis://127.0.0.1:6379/0')
    parser.add_argument('--cache-prefix', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'runtime/week5/verification.json')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT/'dataset_v1'):
        parser.error('Output must be inside repository and outside Dataset')
    report = dict(status='RUNNING', labels_consumed=False,
        scope='Controlled synthetic operational probes; actual routing and canonical vehicle/station identities',
        cases={}, timestamp=datetime.now(timezone.utc).isoformat())
    redis = Redis.from_url(args.redis_url, socket_timeout=.3, socket_connect_timeout=.3)
    try:
        async with asyncpg.create_pool(args.database_url.replace('postgresql+asyncpg://', 'postgresql://'), min_size=1, max_size=3) as pool:
            schema = await pool.fetchval('SELECT current_schema()')
            validate_isolation(schema, args.cache_prefix)
            assert await pool.fetchval('SELECT count(*) FROM state_snapshots') == 0, 'Use a fresh isolated verification schema'
            assert await redis.ping()
            repository, cache = SnapshotRepository(pool), SnapshotCache(redis, prefix=args.cache_prefix)
            cases = dataset_cases()
            request = next(request for group, request in cases if group == 'car')
            start = datetime(2026, 9, 4, tzinfo=timezone.utc)
            source = 'week5-verification:' + uuid4().hex
            async with httpx.AsyncClient(base_url=args.api_url, timeout=120,
                headers={'X-Ingestion-Token': args.token_file.read_text('utf-8').strip()}) as client:
                report['cases']['refresh'] = await refresh_probes(client, request, start, source)
                report['cases']['location'] = await location_probes(client, request, start + timedelta(minutes=4))
            report['cases']['one_retry'] = await conflict_retry_probe(repository, cache, request, start, source, False)
            report['cases']['second_conflict'] = await conflict_retry_probe(repository, cache, request, start, source, True)
            report['cases']['dependencies'] = await dependency_probes(repository, cache, request, args.database_url, start+timedelta(minutes=7))
            report['status'] = 'PASS'
    except Exception as exc:
        report.update(status='FAIL', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        await redis.aclose()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        print(f'Evidence: {output}', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
