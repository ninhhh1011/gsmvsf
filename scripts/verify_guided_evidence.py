"""Held-out finite inspection controls; no writes to journey history or Dataset V1."""
import argparse
import asyncio
from datetime import timedelta
import json

import httpx

from backend.app.services.route_familiarity.deviations import GuidedTrip, inspect_guided_trip
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from scripts.seed_guided_hanoi import fetch_route, sampled
from scripts.seed_synthetic_journeys import output_directory, seed_time


async def verify(args):
    output = output_directory(args.output)
    output.mkdir(parents=True, exist_ok=True)
    base = seed_time(args.as_of)
    fixtures, truth = [], []
    for index, origin in enumerate([(20.98, 105.82), (21.08, 105.78), (21.12, 105.84), (21.02, 105.93)]):
        def point(north, east=0):
            return [origin[0] + north / 111195, origin[1] + east / 103810]
        for mode in ('FOLLOW', 'EXIT', 'GAP'):
            points = [point(i * 20) for i in range(16)]
            if mode != 'FOLLOW':
                points = points[:8] + [point(i * 20, 100) for i in range(8, 16)]
            observations = [{'at': base + timedelta(seconds=i * 5 + (100 if mode == 'GAP' and i >= 8 else 0)),
                             'coordinates': p} for i, p in enumerate(points)]
            fixtures.append(GuidedTrip.model_validate({'driver_id': 'held-out', 'trip_id': f'{index}-{mode}',
                'started_at': base, 'completed_at': observations[-1]['at'] + timedelta(seconds=1),
                'guidance': [{'effective_at': base, 'coordinates': [point(0), point(3000)]}], 'observations': observations}))
            truth.append({'mode': mode, 'departure_events': int(mode == 'EXIT'),
                          'off_distance_m': 140 if mode != 'FOLLOW' else 0, 'comparison_available': mode != 'GAP'})
    # Independent maneuver truth precedes detector execution and stays offline.
    (output / 'evaluation_truth.json').write_text(json.dumps(truth, indent=2), encoding='utf-8')
    results = []
    for trip, expected in zip(fixtures, truth):
        result = inspect_guided_trip(trip)
        assert result['summary']['departure_events'] == expected['departure_events']
        assert abs(result['summary']['off_route_distance_m'] - expected['off_distance_m']) < 1
        assert (result['whole_trip_comparison']['status'] == 'AVAILABLE') == expected['comparison_available']
        if expected['mode'] == 'GAP':
            assert result['summary']['unknown_seconds'] >= 105
        results.append({'case': trip.trip_id, 'summary': result['summary'], 'pass': True})
    road_geometries = []
    async with httpx.AsyncClient(timeout=60) as client:
        adapter = GraphHopperRoutingAdapter(client=client)
        for index, (first, last) in enumerate([
            ((20.975, 105.814), (21.026, 105.864)), ((21.084, 105.774), (21.116, 105.851)),
            ((21.117, 105.846), (21.056, 105.925)), ((21.018, 105.936), (20.947, 105.872))]):
            route = await fetch_route(adapter, first, last)
            road_geometries.append(route)
            points = sampled(route['coordinates'])
            observations = [{'at': base + timedelta(seconds=i * 5), 'coordinates': p} for i, p in enumerate(points)]
            trip = GuidedTrip.model_validate({'driver_id': 'held-out-road', 'trip_id': f'road-{index}',
                'started_at': base, 'completed_at': observations[-1]['at'] + timedelta(seconds=1),
                'guidance': [{'effective_at': base, 'coordinates': route['coordinates']}], 'observations': observations})
            result = inspect_guided_trip(trip)
            assert result['summary']['departure_events'] == 0 and result['summary']['off_route_distance_m'] == 0
            results.append({'case': trip.trip_id, 'pass': True, 'summary': result['summary']})
    (output / 'road-geometries.json').write_text(json.dumps(road_geometries), encoding='utf-8')
    report = {'status': 'PASS', 'checks': results, 'stored_runtime_trips': 0,
              'limitations': 'Held-out controls do not establish driver motivations or calibrated field accuracy'}
    (output / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'checks_passed': len(results), 'stored_runtime_trips': 0}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', default='runtime/h3-evidence-evaluation')
    asyncio.run(verify(parser.parse_args()))


if __name__ == '__main__':
    main()
