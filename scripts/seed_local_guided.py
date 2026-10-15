"""Measured synthetic coverage/stress cohorts; held-out journey records never enter runtime."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import random

import asyncpg
import httpx

from backend.app.config import settings
from backend.app.services.route_familiarity.deviations import analyze_guided_trip, _project
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.route_matcher import _haversine_m, prepare_route
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from scripts.seed_guided_hanoi import build_trip, fetch_route, sampled
from scripts.seed_synthetic_journeys import output_directory, seed_time


def departure_indices(size, rng):
    if size < 35:
        raise ValueError('Local route too short for confirmed maneuvers')
    first = rng.randint(5, min(size - 16, max(6, int(size * 0.6))))
    second = rng.randint(first + 6, size - 5)
    return first, second


def validate_route(route, origin, destination, maximum, vias=(), bbox=None):
    if not 100 <= route['distance_m'] <= maximum:
        raise ValueError('Local route length outside limit')
    coordinates = route['coordinates']
    if bbox is not None:
        west, south, east, north = bbox
        if any(not (south <= lat <= north and west <= lon <= east) for lat, lon in coordinates):
            raise ValueError('Route geometry outside available map scope')
    if max(_haversine_m(origin, coordinates[0]), _haversine_m(destination, coordinates[-1])) > 35:
        raise ValueError('Requested endpoint snap exceeds 35 m')
    if vias:
        pieces = prepare_route(coordinates).pieces
        if any(min(_project(via, piece)[0] for piece in pieces) > 35 for via in vias):
            raise ValueError('Requested via snap exceeds 35 m')


def nearby_points(origin, points, minimum, maximum):
    ranked = sorted((_haversine_m(origin, (row['latitude'], row['longitude'])), index, row)
                    for index, row in enumerate(points))
    return [row for distance, _, row in ranked if minimum <= distance <= maximum]


def position(row):
    return [row['latitude'], row['longitude']]


async def local_route(adapter, origin, destination, maximum, vias=(), bbox=None):
    route = await fetch_route(adapter, origin, destination, vias)
    validate_route(route, origin, destination, maximum, vias, bbox)
    return route


async def prepare_template(adapter, target, targets, vias, rng, bbox):
    origin = position(target)
    destinations = nearby_points(origin, targets, 700, 4500)[:8]
    if not destinations:
        raise ValueError('No nearby destination in measured targets')
    destination = position(rng.choice(destinations))
    direct = await local_route(adapter, origin, destination, 9000, bbox=bbox)
    points = sampled(direct['coordinates'])
    first, second = departure_indices(len(points), rng)
    pieces = prepare_route(direct['coordinates']).pieces
    chosen = []
    for anchor in (points[first], points[second]):
        candidates = nearby_points(anchor, vias, 150, 1800)[:50]
        off_corridor = [row for row in candidates if min(_project(position(row), piece)[0] for piece in pieces) > 80]
        if not off_corridor:
            raise ValueError('No nearby off-corridor branch target')
        chosen.append(position(rng.choice(off_corridor[:8])))
    tail_first = await local_route(adapter, points[first], points[-1], 12000, [chosen[0]], bbox)
    tail_second = await local_route(adapter, points[second], points[-1], 12000, [chosen[1]], bbox)
    loop = await local_route(adapter, points[first], points[first], 6000, [chosen[0]], bbox)
    return {'target': target, 'destination': destination, 'vias': chosen,
            'first_index': first, 'second_index': second, 'direct': direct,
            'tail_first': tail_first, 'tail_second': tail_second, 'loop': loop}


def make_inputs(manifest, batch):
    rng = random.Random(manifest['seed'])
    as_of = seed_time(manifest['as_of'])
    inputs, declarations, next_start = [], [], {}
    for index, item in enumerate(manifest['templates']):
        template = {key: item[key]['coordinates'] for key in ('direct', 'tail_first', 'tail_second', 'loop')}
        template.update(first_index=item['first_index'], second_index=item['second_index'])
        held_out = item['held_out']
        cases = [('coverage', 'FOLLOW', index % 30), ('stress', 'FOLLOW', 30 + index % 20),
                 ('stress', 'EXIT', 50 + index % 20), ('stress', 'EXIT_LATE', 70 + index % 20),
                 ('stress', 'RETURN_EXIT', 90 + index % 20)]
        for cohort, scenario, driver in cases:
            active = dict(template)
            if scenario == 'EXIT_LATE':
                active.update(first_index=item['second_index'], second_index=item['second_index'] + 1,
                              tail_first=template['tail_second'])
            kind = 'EXIT' if scenario == 'EXIT_LATE' else scenario
            driver_key = cohort, driver
            started = next_start.get(driver_key, as_of - timedelta(days=6 - driver % 5, minutes=rng.randrange(60)))
            trip = build_trip(kind, active, f'h3-road-{batch}-{cohort}-{driver}',
                              f'{batch}-{index}-{driver}-{scenario}_{cohort.upper()}', started, rng)
            # Vary observed cadence while preserving chronology and plausible local movement.
            elapsed = 0
            observations = []
            for observation in trip.observations:
                observations.append(observation.model_copy(update={'at': started + timedelta(seconds=elapsed)}))
                elapsed += rng.randint(3, 7)
            trip = trip.model_copy(update={'observations': observations,
                'completed_at': observations[-1].at + timedelta(seconds=1)})
            if trip.completed_at > as_of:
                raise ValueError('Driver schedule exceeds the causal seed window')
            next_start[driver_key] = trip.completed_at + timedelta(minutes=rng.randint(5, 20))
            inputs.append(trip)
            declarations.append({'trip_id': trip.trip_id, 'cohort': cohort, 'scenario': scenario,
                'held_out': held_out, 'target_id': item['target']['id'],
                'planned_departures': 2 if kind == 'RETURN_EXIT' else int(kind == 'EXIT'),
                'first_fraction': active['first_index'] / len(sampled(item['direct']['coordinates']))})
    return inputs, declarations


async def seed(args):
    output = output_directory(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source_path = output_directory(args.targets)
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    as_of = seed_time(args.as_of)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if (manifest['seed'], manifest['as_of'], manifest['source_sha256']) != (args.seed, as_of.isoformat(), source_hash):
            raise ValueError('Frozen manifest differs from requested seed/time/source')
    else:
        rng, templates, rejected = random.Random(args.seed), [], []
        async with httpx.AsyncClient(timeout=30) as client:
            adapter = GraphHopperRoutingAdapter(client=client)
            for index, target in enumerate(source['targets']):
                try:
                    item = await prepare_template(adapter, target, source['targets'], source['via_points'], rng,
                                                  source['scope']['available_bbox_wsen'])
                    item['held_out'] = index % 6 == 5
                    templates.append(item)
                except ValueError as exc:
                    rejected.append({'target_id': target['id'], 'reason': str(exc)})
                # Engine errors propagate; an outage is never an unroutable-target skip.
                progress = {'processed': index + 1, 'total': len(source['targets']),
                            'prepared': len(templates), 'rejected': len(rejected)}
                print(json.dumps(progress), flush=True)
                (output / 'preparation.json').write_text(json.dumps({**progress, 'rejections': rejected}, indent=2), encoding='utf-8')
        if len(templates) < 12 or not any(item['held_out'] for item in templates):
            raise ValueError('Insufficient routable local/held-out templates; inspect rejected targets')
        manifest = {'seed': args.seed, 'as_of': as_of.isoformat(), 'source_sha256': source_hash,
                    'scope': source['scope'], 'templates': templates, 'rejected': rejected,
                    'provenance': 'Real GraphHopper local roads; designed synthetic cohorts, not driver prevalence'}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for item in manifest['templates']:
        for key in ('direct', 'tail_first', 'tail_second', 'loop'):
            route = item[key]
            validate_route(route, route['coordinates'][0], route['coordinates'][-1],
                           12000, bbox=manifest['scope']['available_bbox_wsen'])
    (output / 'source-targets.json').write_bytes(source_bytes)
    batch = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:12]
    inputs, declarations = make_inputs(manifest, batch)
    (output / 'evaluation_truth.json').write_text(json.dumps(declarations, indent=2), encoding='utf-8')
    for cohort in ('coverage', 'stress', 'held_out'):
        selected = [trip.model_dump(mode='json') for trip, item in zip(inputs, declarations)
                    if (item['held_out'] if cohort == 'held_out' else not item['held_out'] and item['cohort'] == cohort)]
        (output / f'{cohort}-inputs.json').write_text(json.dumps(selected), encoding='utf-8')
    analyses, rows = [], []
    for trip, declaration in zip(inputs, declarations):
        analysis = analyze_guided_trip(trip)
        events = sum(len(value['departures']) for value in analysis['cells']['9'].values())
        if declaration['scenario'] == 'FOLLOW' and events:
            raise AssertionError('False departure in following control; no batch writes performed')
        analyses.append(analysis)
        rows.append({**declaration, 'detected_events': events, 'driver_id': trip.driver_id,
                     'detected_departing_trip': events > 0})
    report = {'status': 'VALIDATED', 'batch': batch, 'scope': manifest['scope'],
              'prepared_corridors': len(manifest['templates']), 'rejected_targets': len(manifest['rejected']),
              'held_out_trips': sum(row['held_out'] for row in rows),
              'rows': rows, 'limitations': 'Stress ratio is designed. Maneuver intentions are not exact event truth.'}
    (output / 'seed-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    async with asyncpg.create_pool(args.database_url, min_size=1, max_size=2) as pool:
        repo = RouteHistoryRepository(pool, 'synthetic')
        await repo.ensure_schema()
        for trip, declaration, analysis in zip(inputs, declarations, analyses):
            if not declaration['held_out']:
                await repo.ingest_guided_trip(trip.model_dump(mode='json'), analysis)
    report['status'] = 'PASS'
    report['cohorts'] = {}
    for cohort in ('coverage', 'stress'):
        values = [row for row in rows if row['cohort'] == cohort and not row['held_out']]
        report['cohorts'][cohort] = {'trips': len(values), 'drivers': len({row['driver_id'] for row in values}),
            'planned_departing_trips': sum(row['planned_departures'] > 0 for row in values),
            'detected_departing_trips': sum(row['detected_departing_trip'] for row in values),
            'detected_departing_drivers': len({row['driver_id'] for row in values if row['detected_departing_trip']}),
            'detected_events': sum(row['detected_events'] for row in values)}
    (output / 'seed-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'rows'}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--seed', type=int, default=20261015)
    parser.add_argument('--output', default='runtime/h3-local-20261015/seed')
    parser.add_argument('--database-url', default=settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'))
    asyncio.run(seed(parser.parse_args()))


if __name__ == '__main__':
    main()
