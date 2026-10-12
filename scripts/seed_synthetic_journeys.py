"""Seed an isolated, reproducible history from real GraphHopper geometries."""
import argparse
import asyncio
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import random

import asyncpg
import httpx

from backend.app.config import settings
from backend.app.services.route_familiarity.ingestion import RouteHistoryIngestion
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile

PAIRS = [((20.9849, 105.7935), (21.0315, 105.7830)),
         ((20.9849, 105.7935), (21.0245, 105.8560)),
         ((21.0185, 105.7745), (21.0320, 105.8150)),
         ((20.9720, 105.8310), (21.0070, 105.8450))]
VIA = (21.0125, 105.7950)


def choice_cost(duration, queue_minutes, familiarity):
    # Behavioral inputs generate observations; runtime never reads these motives.
    return duration + queue_minutes * 60 - familiarity * 180


async def seed(args):
    as_of = datetime.fromisoformat(args.as_of.replace('Z', '+00:00'))
    if as_of.tzinfo is None:
        raise ValueError('as-of requires an explicit timezone')
    rng = random.Random(args.seed)
    output = Path(args.output)
    if output.resolve().is_relative_to(settings.dataset_path.resolve()):
        raise ValueError('Output cannot be inside Dataset V1')
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / 'manifest.json'
    if manifest.exists():
        existing = json.loads(manifest.read_text())
        if (existing['seed'], existing['as_of'], existing['drivers']) != (
                args.seed, as_of.isoformat(), args.drivers):
            raise ValueError('Use a new output directory for a different seed/time/size')
        templates = existing['templates']
    else:
        templates = []
        async with httpx.AsyncClient(timeout=60) as client:
            adapter = GraphHopperRoutingAdapter(client=client)
            for origin, destination in PAIRS:
                for via in ([], [Position(latitude=VIA[0], longitude=VIA[1])]):
                    route = await adapter.route(RouteRequest(
                        origin=Position(latitude=origin[0], longitude=origin[1]),
                        destination=Position(latitude=destination[0], longitude=destination[1]),
                        via=via, profile=VehicleRoutingProfile(vehicle_category='EV_CAR')))
                    if route.status != RouteStatus.SUCCESS or not route.geometry:
                        raise RuntimeError(f'Real routing failed: {route.status} {route.error_message}')
                    templates.append({'origin': origin, 'destination': destination,
                        'polyline': route.geometry, 'duration_s': route.duration_s,
                        'distance_m': route.distance_m, 'engine': route.engine_name})
        manifest.write_text(json.dumps({'seed': args.seed, 'as_of': as_of.isoformat(),
            'drivers': args.drivers, 'namespace': 'synthetic', 'templates': templates,
            'provenance': 'seeded behavioral choices over real GraphHopper routes',
            'limitations': 'Synthetic motivations are not evidence of real driver causality'},
            indent=2), encoding='utf8')
    batch = hashlib.sha256(manifest.read_bytes()).hexdigest()[:16]
    truth = []
    async with asyncpg.create_pool(settings.database_url.replace('postgresql+asyncpg://',
                                                               'postgresql://')) as pool:
        repo = RouteHistoryRepository(pool, namespace='synthetic')
        await repo.ensure_schema()
        ingestion = RouteHistoryIngestion(repo)
        identities = ['synthetic_sample_driver'] + [f'synthetic_{batch}_{i}' for i in range(args.drivers)]
        for index, driver in enumerate(identities):
            pair = index % len(PAIRS)
            for day in range(1, 6):
                queue = [rng.randint(0, 20), rng.randint(0, 20)]
                preference = [rng.random(), rng.random()]
                options = templates[pair * 2:pair * 2 + 2]
                costs = [choice_cost(t['duration_s'], q, f)
                         for t, q, f in zip(options, queue, preference)]
                selected = min(range(2), key=lambda i: costs[i])
                route = options[selected]
                completed = as_of - timedelta(days=day, minutes=10)
                started = completed - timedelta(seconds=route['duration_s'])
                trip = f'{batch}_{index}_{day}'
                await ingestion.ingest(driver, trip, completed, route['polyline'], started)
                truth.append({'driver_id': driver, 'trip_id': trip, 'selected_template': pair * 2 + selected,
                    'queue_input_min': queue, 'familiarity_input': preference, 'choice_cost_s': costs})
    (output / 'evaluation_truth.json').write_text(json.dumps(truth, indent=2), encoding='utf8')
    print(json.dumps({'batch': batch, 'routes': len(truth), 'namespace': 'synthetic',
                      'manifest': str(manifest), 'real_route_templates': len(templates)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261012)
    parser.add_argument('--drivers', type=int, default=100)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', default='runtime/synthetic-journeys')
    args = parser.parse_args()
    if not 5 <= args.drivers <= 1000:
        parser.error('drivers must be between5 and1000')
    asyncio.run(seed(args))


if __name__ == '__main__':
    main()
