"""Audit old histories; verify independent synthetic departure cases against real PostgreSQL/API.

Default uses a disposable database. --seed-demo additionally installs only paired
synthetic cases into the application's synthetic namespace for branch UI review.
Never interprets existing visit counts as departure labels.
"""
import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import uuid

import asyncpg
import h3
import httpx

from backend.app.config import settings
from backend.app.main import create_app
from backend.app.services.route_familiarity.deviations import GuidedTrip, analyze_guided_trip
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.route_matcher import prepare_route
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile


def point(north, east=0):
    return [21 + north / 111195, 105.8 + east / 103810]


def cases(as_of):
    base = as_of - timedelta(hours=1)
    common = [point(i * 20) for i in range(6)]
    # Truth is authored from these maneuvers, before invoking the detector.
    definitions = [
        ('noise', [point(i * 20, (-1) ** i * 8) for i in range(20)], [], None),
        ('one_exit', common + [point(120 + i * 20, 100) for i in range(12)], [point(100)], None),
        ('two_exits', [point(i * 15) for i in range(4)] + [point(60 + i * 15, 70) for i in range(4)] +
         [point(120 + i * 15) for i in range(4)] + [point(180 + i * 15, 70) for i in range(4)],
         [point(45), point(165)], None),
        ('guidance_change', common + [point(120 + i * 20, 100) for i in range(6)], [], 'change'),
        ('gap', common + [point(120 + i * 20, 100) for i in range(6)], [], 'gap'),
        ('starts_off', [point(i * 20, 100) for i in range(10)], [], None),
    ]
    result, truth = [], []
    for name, coordinates, origins, special in definitions:
        times = [i * 5 for i in range(len(coordinates))]
        if special == 'gap':
            times = list(range(0, 30, 5)) + list(range(100, 130, 5))
        guidance = [{'effective_at': base, 'coordinates': [point(0), point(1500)]}]
        if special == 'change':
            guidance.append({'effective_at': base + timedelta(seconds=30),
                             'coordinates': [point(100, 100), point(1500, 100)]})
        result.append(GuidedTrip.model_validate({
            'driver_id': 'h3-verification-driver', 'trip_id': name,
            'started_at': base, 'completed_at': base + timedelta(seconds=times[-1] + 1),
            'guidance': guidance, 'observations': [{'at': base + timedelta(seconds=t), 'coordinates': p}
                                                 for t, p in zip(times, coordinates)]}))
        truth.append({'case': name, 'departure_origins': origins, 'expected_events': len(origins),
                      'comparable': name != 'starts_off'})
    return result, truth


async def verify(args):
    output = Path(args.output).resolve()
    if not output.is_relative_to(Path.cwd().resolve()) or output.is_relative_to(Path('dataset_v1').resolve()):
        raise ValueError('Evidence must be inside this repository and outside Dataset V1')
    output.mkdir(parents=True, exist_ok=True)
    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00')) if args.as_of else datetime.now(UTC)
    if as_of.tzinfo is None:
        raise ValueError('as-of requires a timezone')
    trips, truth = cases(as_of)
    (output / 'evaluation_truth.json').write_text(json.dumps(truth, indent=2), encoding='utf-8')
    report = {'status': 'RUNNING', 'as_of_iso': as_of.isoformat(), 'synthetic_only': True, 'checks': [], 'audit': {}}
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    with (output / 'paired-inputs.json').open('w', encoding='utf-8') as stream:
        json.dump([trip.model_dump(mode='json') for trip in trips], stream, indent=2)
    analyses = []
    for trip, expected in zip(trips, truth):
        analysis = analyze_guided_trip(trip)
        for resolution in range(5, 11):
            observed = {cell: len(value['departures']) for cell, value in analysis['cells'][str(resolution)].items()
                        if value['departures']}
            reference = {}
            for origin in expected['departure_origins']:
                cell = h3.latlng_to_cell(*origin, resolution)
                reference[cell] = reference.get(cell, 0) + 1
            assert observed == reference, (trip.trip_id, resolution, observed, reference)
        assert analysis['comparable'] == expected['comparable']
        analyses.append(analysis)
        report['checks'].append({'case': trip.trip_id, 'resolutions': '5-10', 'pass': True})

    async with httpx.AsyncClient(timeout=30) as client:
        route = await GraphHopperRoutingAdapter(client=client).route(RouteRequest(
            origin=Position(latitude=21.0015, longitude=105.82),
            destination=Position(latitude=21.03, longitude=105.85),
            profile=VehicleRoutingProfile(vehicle_category='EV_CAR')))
        assert route.status == RouteStatus.SUCCESS and route.geometry
    from backend.app.services.route_familiarity.signature import create_route_signature
    coordinates = create_route_signature([route.geometry]).coordinates
    prepared = prepare_route(coordinates)
    observations = [{'at': as_of - timedelta(hours=2) + timedelta(seconds=i * 5), 'coordinates': p.start}
                    for i, p in enumerate(prepared.pieces[::2])]
    real_trip = GuidedTrip.model_validate({'driver_id': 'h3-real-network', 'trip_id': 'same-route',
        'started_at': observations[0]['at'], 'completed_at': observations[-1]['at'] + timedelta(seconds=1),
        'guidance': [{'effective_at': observations[0]['at'], 'coordinates': coordinates}], 'observations': observations})
    real_analysis = analyze_guided_trip(real_trip)
    assert sum(len(v['departures']) for v in real_analysis['cells']['9'].values()) == 0
    report['checks'].append({'case': 'real-graphhopper-identical-route', 'pass': True,
                             'distance_m': route.distance_m})

    admin = await asyncpg.connect(args.database_url)
    temporary = 'h3_departure_verify_' + uuid.uuid4().hex
    from urllib.parse import urlsplit, urlunsplit
    url = urlsplit(args.database_url)
    temporary_url = urlunsplit(url._replace(path='/' + temporary))
    try:
        for namespace in ('realtime', 'synthetic'):
            count = await admin.fetchrow(f'SELECT count(*) AS trips,min(completed_at) AS first,max(completed_at) AS last FROM {namespace}.route_familiarity_routes')
            paired_table = await admin.fetchval('SELECT to_regclass($1)', f'{namespace}.route_deviation_trips')
            paired_count = await admin.fetchval(f'SELECT count(*) FROM {namespace}.route_deviation_trips') if paired_table else 0
            unpaired_count = await admin.fetchval(f'''SELECT count(*) FROM {namespace}.route_familiarity_routes h
                WHERE NOT EXISTS (SELECT 1 FROM {namespace}.route_deviation_trips d
                WHERE d.driver_id=h.driver_id AND d.trip_id=h.trip_id)''') if paired_table else count['trips']
            report['audit'][namespace] = {'trips': count['trips'], 'first': str(count['first']), 'last': str(count['last']),
                'paired_evidence_table_exists': bool(paired_table), 'paired_trip_count': paired_count,
                'legacy_unpaired_trip_count': unpaired_count}
        await admin.execute(f'CREATE DATABASE "{temporary}"')
        async with asyncpg.create_pool(temporary_url, min_size=1, max_size=2, command_timeout=10) as pool:
            repo = RouteHistoryRepository(pool, 'synthetic')
            await repo.ensure_schema()
            app = create_app()
            app.state.route_history_repository = repo
            settings.enable_route_familiarity = True
            settings.snapshot_ingestion_token = 'isolated-h3-verification'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://verification') as client:
                headers = {'X-Ingestion-Token': settings.snapshot_ingestion_token}
                for driver in range(5):
                    for trip in trips:
                        payload = trip.model_dump(mode='json')
                        payload['driver_id'] = f'h3-verify-{driver}'
                        response = await client.post('/api/v1/internal/route-deviations/trips', json=payload, headers=headers)
                        assert response.status_code == 201, response.text
                        assert (await client.post('/api/v1/internal/route-deviations/trips', json=payload, headers=headers)).status_code == 200
                response = await client.get('/api/v1/routing/departure-heatmap', params={'resolution': 5, 'as_of_iso': as_of.isoformat()})
                assert response.status_code == 200, response.text
                aggregate = response.json()
                assert sum(c['departure_event_count'] for c in aggregate['cells'].values()) == 15
                origin_cell = h3.latlng_to_cell(*point(0), 5)
                assert aggregate['cells'][origin_cell]['eligible_trip_count'] == 20
                assert aggregate['cells'][origin_cell]['departing_trip_count'] == 10
                assert all(c['departing_trip_count'] <= c['eligible_trip_count'] for c in aggregate['cells'].values())
                assert aggregate['paired_trip_count'] == 30 and aggregate['unknown_trip_count'] == 5
                (output / 'api-aggregate.json').write_text(json.dumps(aggregate, indent=2), encoding='utf-8')
                earlier = await client.get('/api/v1/routing/departure-heatmap', params={
                    'as_of_iso': (as_of - timedelta(days=2)).isoformat()})
                assert earlier.json()['paired_trip_count'] == 0
                # An overlapping future paired identity must not erase replay-visible legacy evidence.
                legacy_cell = h3.latlng_to_cell(21.1, 105.9, 11)
                async with pool.acquire() as conn:
                    await conn.execute('''INSERT INTO synthetic.route_familiarity_routes
                        (driver_id,trip_id,completed_at,distance_m,resolution,cells,cell_distances_m)
                        VALUES ('future-pair','legacy',$1,100,11,$2,$3)''',
                        as_of - timedelta(hours=1), [legacy_cell], [100.0])
                future = trips[0].model_copy(update={'driver_id': 'future-pair', 'trip_id': 'legacy',
                    'completed_at': as_of + timedelta(hours=1)})
                await repo.ingest_guided_trip(future.model_dump(mode='json'), analyze_guided_trip(future))
                combined = await repo.departure_heatmap(as_of, 5)
                assert combined['excluded_unpaired_trip_count'] == 1
                legacy_stats = combined['cells'][h3.latlng_to_cell(21.1, 105.9, 5)]
                assert legacy_stats['history_trip_count'] == 1 and legacy_stats['departure_pct'] is None
                assert combined['cells'][origin_cell]['eligible_trip_count'] == 20
                assert combined['cells'][origin_cell]['departing_trip_count'] == 10
                report['checks'].append({'case': 'legacy-footprint-causal-antijoin-no-inferred-weights', 'pass': True})
                real_repo = RouteHistoryRepository(pool, 'realtime')
                await real_repo.ensure_schema()
                await real_repo.ingest_guided_trip(trips[1].model_dump(mode='json'), analyses[1])
                private = await real_repo.departure_heatmap(as_of, 9)
                assert not private['cells']
                report['checks'].append({'case': 'real-postgres-api-idempotency-window-privacy', 'pass': True})
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{temporary}" WITH (FORCE)')
        await admin.close()

    if args.seed_demo:
        async with asyncpg.create_pool(args.database_url, min_size=1, max_size=2, command_timeout=10) as pool:
            repo = RouteHistoryRepository(pool, 'synthetic')
            await repo.ensure_schema()
            batch = hashlib.sha256(json.dumps([t.model_dump(mode='json') for t in trips]).encode()).hexdigest()[:12]
            for driver in range(5):
                for trip, analysis in zip(trips, analyses):
                    payload = trip.model_dump(mode='json')
                    payload.update(driver_id=f'h3-demo-{batch}-{driver}', trip_id=f'{batch}-{trip.trip_id}')
                    await repo.ingest_guided_trip(payload, analysis)
            report['demo_seed'] = {'batch': batch, 'namespace': 'synthetic', 'paired_trips': 30}
    report['limitations'] = 'Synthetic maneuvers verify event counting, not real motivations or citywide behavioral coverage'
    report['status'] = 'PASS'
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'checks_passed': len(report['checks']), 'output': str(output), 'demo_seed': report.get('demo_seed')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'))
    parser.add_argument('--output', default='runtime/h3-departures')
    parser.add_argument('--as-of')
    parser.add_argument('--seed-demo', action='store_true')
    asyncio.run(verify(parser.parse_args()))


if __name__ == '__main__':
    main()
