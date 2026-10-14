"""Reproducible paired synthetic journeys over diverse real GraphHopper Hanoi roads."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
import random

import asyncpg
import httpx

from backend.app.config import settings
from backend.app.services.route_familiarity.deviations import GuidedTrip, analyze_guided_trip
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.route_matcher import _haversine_m, prepare_route
from backend.app.services.route_familiarity.signature import create_route_signature
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile
from scripts.seed_synthetic_journeys import output_directory, seed_time

HUBS = [(21.072, 105.792), (21.055, 105.821), (21.066, 105.861),
        (21.054, 105.882), (21.039, 105.927), (21.012, 105.884),
        (20.969, 105.853), (20.944, 105.845), (20.971, 105.777),
        (21.001, 105.793), (21.029, 105.778), (21.053, 105.754)]
KINDS = ('FOLLOW', 'EXIT', 'RETURN_EXIT', 'REROUTE', 'GAP', 'NOISE')


def sampled(coordinates):
    route = prepare_route(coordinates)
    return [piece.start for piece in route.pieces[::3]] + [tuple(coordinates[-1])]


def checked_join(*chunks):
    result = []
    for chunk in chunks:
        if not chunk:
            continue
        if result:
            if _haversine_m(result[-1], chunk[0]) > 45:
                raise ValueError('Disconnected GraphHopper chunks cannot form a synthetic road journey')
            result.extend(chunk[1:] if _haversine_m(result[-1], chunk[0]) < 0.05 else chunk)
        else:
            result.extend(chunk)
    return result


def build_trip(kind, template, driver_id, trip_id, started, rng):
    direct = sampled(template['direct'])
    first, second = len(direct) // 3, len(direct) * 2 // 3
    guidance = [{'effective_at': started, 'coordinates': template['direct']}]
    coordinates = direct
    if kind in ('EXIT', 'REROUTE'):
        coordinates = checked_join(direct[:first + 1], sampled(template['tail_first']))
        if kind == 'REROUTE':
            guidance.append({'effective_at': started + timedelta(seconds=first * 5),
                             'coordinates': template['tail_first']})
    elif kind == 'RETURN_EXIT':
        coordinates = checked_join(direct[:first + 1], sampled(template['loop']),
                                   direct[first:second + 1], sampled(template['tail_second']))
    elif kind == 'NOISE':
        coordinates = [[lat + rng.uniform(-3, 3) / 111195, lon] for lat, lon in direct]
    elif kind not in ('FOLLOW', 'GAP'):
        raise ValueError('Unsupported synthetic maneuver')
    observations = [{'at': started + timedelta(seconds=i * 5), 'coordinates': point}
                    for i, point in enumerate(coordinates)]
    if kind == 'GAP':
        middle = len(observations) // 2
        observations = observations[:middle] + observations[middle + 20:]
    return GuidedTrip.model_validate({'driver_id': driver_id, 'trip_id': trip_id,
        'started_at': started, 'completed_at': started + timedelta(seconds=(len(coordinates) - 1) * 5 + 1),
        'guidance': guidance, 'observations': observations})


async def fetch_route(adapter, origin, destination, via=()):
    def position(p):
        return Position(latitude=p[0], longitude=p[1])
    route = await adapter.route(RouteRequest(origin=position(origin), destination=position(destination),
        via=[position(p) for p in via], profile=VehicleRoutingProfile(vehicle_category='EV_CAR')))
    if route.status != RouteStatus.SUCCESS or not route.geometry or route.engine_name != 'graphhopper':
        raise RuntimeError('Real GraphHopper route required; no mock or straight-line fallback')
    return {'polyline': route.geometry, 'coordinates': create_route_signature([route.geometry]).coordinates,
            'distance_m': route.distance_m, 'engine': route.engine_name}


async def seed(args):
    as_of = seed_time(args.as_of)
    output = output_directory(args.output)
    output.mkdir(parents=True, exist_ok=True)
    hubs = HUBS
    if args.targets:
        targets = json.loads(output_directory(args.targets).read_text(encoding='utf-8'))['targets']
        hubs = [(row['latitude'], row['longitude']) for row in targets]
        if not 12 <= len(hubs) <= 48:
            raise ValueError('Gap-target seed requires 12..48 measured targets')
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not args.targets and manifest.get('hubs'):
            hubs = manifest['hubs']
        if (manifest['seed'], manifest['as_of'], manifest['drivers']) != (args.seed, as_of.isoformat(), args.drivers):
            raise ValueError('Use a different output directory for a different seed/time/driver count')
        if [list(point) for point in manifest.get('hubs', HUBS)] != [list(point) for point in hubs]:
            raise ValueError('Manifest target geometry differs; use a different output directory')
    else:
        corridors = []
        async with httpx.AsyncClient(timeout=60) as client:
            adapter = GraphHopperRoutingAdapter(client=client)
            for index, origin in enumerate(hubs):
                destination = hubs[(index + 5) % len(hubs)]
                waypoint = hubs[(index + 2) % len(hubs)]
                direct = await fetch_route(adapter, origin, destination)
                points = sampled(direct['coordinates'])
                if len(points) < 90:
                    raise ValueError('Corridor too short for confirmed return and gap scenarios')
                first, second = points[len(points) // 3], points[len(points) * 2 // 3]
                tail_first = await fetch_route(adapter, first, points[-1], [waypoint])
                tail_second = await fetch_route(adapter, second, points[-1], [waypoint])
                loop = await fetch_route(adapter, first, first, [waypoint])
                corridors.append({'origin': origin, 'destination': destination, 'via': waypoint,
                    'direct': direct, 'tail_first': tail_first, 'tail_second': tail_second, 'loop': loop})
                print(json.dumps({'prepared_corridor': index + 1, 'total': len(hubs)}), flush=True)
        manifest = {'seed': args.seed, 'as_of': as_of.isoformat(), 'drivers': args.drivers, 'hubs': hubs,
            'namespace': 'synthetic', 'corridors': corridors,
            'provenance': 'Real GraphHopper road geometry; synthetic maneuver choices and sampled GPS',
            'limitations': 'Not observed driver behavior; GPS uses the existing 10 m chord approximation'}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for corridor in manifest['corridors']:
        if any(corridor[name]['engine'] != 'graphhopper' for name in ('direct', 'tail_first', 'tail_second', 'loop')):
            raise ValueError('Manifest must contain only real GraphHopper paths')
    batch = hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:12]
    rng = random.Random(args.seed)
    inputs, truth = [], []
    for corridor_index, corridor in enumerate(manifest['corridors']):
        template = {name: corridor[name]['coordinates'] for name in ('direct', 'tail_first', 'tail_second', 'loop')}
        for driver in range(args.drivers):
            for kind in KINDS:
                identity = f'h3-road-{batch}-{driver}'
                trip_id = f'{batch}-{corridor_index}-{driver}-{kind}'
                started = as_of - timedelta(days=driver % 5 + 1, hours=6, minutes=corridor_index * 3)
                trip = build_trip(kind, template, identity, trip_id, started, rng)
                inputs.append(trip)
                truth.append({'trip_id': trip_id, 'corridor': corridor_index, 'maneuver': kind,
                    'intended_departures': 1 if kind == 'EXIT' else 2 if kind == 'RETURN_EXIT' else 0,
                    'reference_semantics': 'Declared maneuvers; projected/ambiguous event counts evaluated separately'})
    # Separate declared truth is persisted before detection and never consumed by runtime.
    (output / 'evaluation_truth.json').write_text(json.dumps(truth, indent=2), encoding='utf-8')
    report = {'status': 'RUNNING', 'batch': batch, 'namespace': 'synthetic', 'as_of': as_of.isoformat(),
              'corridors': len(manifest['corridors']), 'paired_trips': len(inputs), 'events_by_maneuver': {},
              'distinct_observed_geometries': len({hashlib.sha256(json.dumps(
                  [observation.coordinates for observation in trip.observations]).encode()).hexdigest() for trip in inputs}),
              'limitations': manifest['limitations']}
    report_path = output / 'seed-report.json'
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    async with asyncpg.create_pool(args.database_url, min_size=1, max_size=2, command_timeout=10) as pool:
        repo = RouteHistoryRepository(pool, 'synthetic')
        await repo.ensure_schema()
        for index, trip in enumerate(inputs):
            analysis = analyze_guided_trip(trip)
            events = sum(len(value['departures']) for value in analysis['cells']['9'].values())
            kind = truth[index]['maneuver']
            if kind in ('FOLLOW', 'REROUTE', 'NOISE', 'GAP') and events:
                raise AssertionError(f'False departure in {kind} control on corridor {truth[index]["corridor"]}')
            report['events_by_maneuver'][kind] = report['events_by_maneuver'].get(kind, 0) + events
            await repo.ingest_guided_trip(trip.model_dump(mode='json'), analysis)
            if (index + 1) % (args.drivers * len(KINDS)) == 0:
                print(json.dumps({'ingested_trips': index + 1, 'total': len(inputs)}), flush=True)
        aggregate = await repo.departure_heatmap(as_of, 9)
        report.update(status='PASS', all_history_cells=len(aggregate['cells']),
                      weighted_cells=sum(value['departure_pct'] is not None for value in aggregate['cells'].values()),
                      red_cells=sum((value['departure_pct'] or 0) >= 20 for value in aggregate['cells'].values()),
                      legacy_trips=aggregate['excluded_unpaired_trip_count'])
    assert report['events_by_maneuver'].get('EXIT', 0) > 0
    assert report['events_by_maneuver'].get('RETURN_EXIT', 0) >= 2
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--seed', type=int, default=20261014)
    parser.add_argument('--drivers', type=int, default=5)
    parser.add_argument('--targets', help='Gap targets from the coverage audit, inside this repository')
    parser.add_argument('--output', default='runtime/h3-road-journeys-20261014')
    parser.add_argument('--database-url', default=settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'))
    args = parser.parse_args()
    if not 1 <= args.drivers <= 20:
        parser.error('drivers must be 1..20')
    asyncio.run(seed(args))


if __name__ == '__main__':
    main()
