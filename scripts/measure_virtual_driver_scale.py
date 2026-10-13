"""Finite real-time fleet measurement; run explicitly against the real local API.

Secrets are read only from the private process environment. No labels or Dataset
writes, rate-limit bypass, accelerated cadence, retries, or production SLA.
"""
from __future__ import annotations

import argparse
import asyncio
from bisect import bisect_right
from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import random
import re
import sys
from time import perf_counter
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.services.route_familiarity.signature import decode_polyline, _distance_m  # noqa: E402

CADENCE = 30.0
SPEED_M_S = 20 / 3.6
OBSERVATION_AGE_SECONDS = 1


def observation_timestamp():
    # Fixed transport-age assumption avoids milliseconds of client/container clock skew.
    return (datetime.now(UTC) - timedelta(seconds=OBSERVATION_AGE_SECONDS)).isoformat()


def validate_namespace(namespace):
    if not re.fullmatch(r'synthetic-scale-[a-z0-9-]{1,40}', namespace):
        raise ValueError('Load namespace must be synthetic-scale- followed by 1..40 lowercase letters/digits/hyphens')
    return namespace


def load_driver_ids(namespace, stages=(100, 500, 1000)):
    validate_namespace(namespace)
    return [f'{namespace}-{count}-{driver:04d}' for count in stages for driver in range(count)]


def validate_output(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'dataset_v1') or output.exists():
        raise ValueError('Use a new output file inside the repository, outside Dataset')
    return output


def schedule(drivers: int, intervals: int):
    """Each unique driver sends once per 30 real seconds, evenly staggered."""
    return sorted((cycle * CADENCE + driver * CADENCE / drivers, driver, cycle)
                  for cycle in range(intervals) for driver in range(drivers))


def route_distances(points):
    distances = [0.0]
    for a, b in zip(points, points[1:]):
        distances.append(distances[-1] + _distance_m(a, b))
    if distances[-1] <= 0:
        raise ValueError('Route geometry must have positive length')
    return distances


def position(points, distances, distance_m):
    """Interpolate within a road edge; stop at the route end without teleporting."""
    distance_m = max(0, min(distance_m, distances[-1]))
    index = min(bisect_right(distances, distance_m) - 1, len(points) - 2)
    length = distances[index + 1] - distances[index]
    fraction = (distance_m - distances[index]) / length if length else 0
    a, b = points[index:index + 2]
    lat, lon = (a[i] + fraction * (b[i] - a[i]) for i in range(2))
    heading = math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(lat)),
                                     b[0] - a[0])) % 360
    return lat, lon, heading


def distribution(values):
    values = sorted(values)
    if not values:
        return {'samples': 0, 'p50': None, 'p95': None, 'p99': None}
    return {'samples': len(values), **{f'p{p}': values[max(0, math.ceil(len(values) * p / 100) - 1)]
                                     for p in (50, 95, 99)}}


async def measure_stage(client, templates, args, count, secret, namespace, burst=False):
    events = [(0.0, i, 0) for i in range(min(count, args.burst_size))] if burst else schedule(count, args.intervals)
    duration = 1.0 if burst else args.intervals * CADENCE
    started = perf_counter()
    deadline = started + duration + args.drain_seconds
    semaphore = asyncio.Semaphore(args.concurrency)
    counters = Counter()
    statuses, matching, familiarity = Counter(), Counter(), Counter()
    error_samples = {}
    latency, queue_delay = {}, {}
    peak_pending = 0
    pending = set()

    async def request(kind, path, payload, due, headers=None):
        async with semaphore:
            dispatched = perf_counter()
            queue_delay.setdefault(kind, []).append((dispatched - due) * 1000)
            if dispatched >= deadline:
                counters[kind + '_deadline_dropped'] += 1
                return None
            counters[kind + '_sent'] += 1
            try:
                async with asyncio.timeout(min(args.request_timeout, deadline - dispatched)):
                    response = await client.post(path, json=payload, headers=headers)
                statuses[f'{kind}:{response.status_code}'] += 1
                counters[kind + '_completed'] += 1
                if not response.is_success:
                    counters[kind + '_http_errors'] += 1
                    samples = error_samples.setdefault(f'{kind}:{response.status_code}', [])
                    if len(samples) < 3:
                        samples.append(response.text[:1000])
                try:
                    body = response.json()
                except ValueError:
                    counters[kind + '_invalid_json'] += 1
                    return None
                if not response.is_success:
                    return None
                counters[kind + '_successful'] += 1
                if kind == 'gps':
                    matching[str(body.get('status', 'MISSING'))] += 1
                if kind == 'recommendation':
                    familiarity[str((body.get('familiarity') or {}).get('status', 'MISSING'))] += 1
                return body
            except (httpx.HTTPError, TimeoutError) as exc:
                counters[f'{kind}_transport_error:{type(exc).__name__}'] += 1
                return None
            finally:
                latency.setdefault(kind, []).append((perf_counter() - dispatched) * 1000)

    async def event(due_offset, driver, cycle):
        driver_id = f'{namespace}-{count}-{driver:04d}'
        points, distances = templates[driver % len(templates)]
        lat, lon, heading = position(points, distances, (cycle * CADENCE) * SPEED_M_S)
        noise = random.Random(args.seed + count * 10000 + driver * 100 + cycle)
        radius, angle = noise.uniform(0, args.noise_m), noise.uniform(0, math.tau)
        lat += radius * math.cos(angle) / 111195
        lon += radius * math.sin(angle) / (111195 * math.cos(math.radians(lat)))
        stamp = observation_timestamp()
        due = started + due_offset
        gps = await request('gps', f'/api/v1/drivers/{driver_id}/location', {
            'vehicle_id': 'V0001', 'vehicle_category': 'EV_CAR',
            'observation_id': f'{driver_id}-{cycle}', 'timestamp': stamp,
            'latitude': lat, 'longitude': lon, 'speed_kmh': 20,
            'heading_deg': heading, 'accuracy_m': args.noise_m}, due)
        # Separate finite demand sample; never one recommendation per GPS update.
        if burst or (not getattr(args, 'sample_every_interval', False) and cycle != args.intervals - 1) or driver % args.demand_every != 0 or gps is None:
            return
        context = {'vehicle_id': 'V0001', 'driver_id': driver_id, 'timestamp': datetime.now(UTC).isoformat(),
                   'current_soc_pct': 50, 'estimated_remaining_range_km': 50,
                   'raw_latitude': lat, 'raw_longitude': lon}
        evaluated = await request('demand', '/api/v1/demand/evaluate', context, perf_counter())
        explicit = driver % (args.demand_every * 2) == 0
        if evaluated is None or not (evaluated.get('need_service') or explicit):
            counters['demand_without_recommendation'] += 1
            return
        counters['explicit_station_intents' if explicit else 'physical_demand_triggers'] += 1
        signature = hmac.new(secret.encode(), driver_id.encode(), hashlib.sha256).hexdigest()
        await request('recommendation', '/api/v1/recommend', {
            'context': context, **({'requested_service': 'CHARGING'} if explicit else {}),
            'top_n': 3}, perf_counter(), {'X-Driver-Identity-Signature': signature})

    for offset, driver, cycle in events:
        await asyncio.sleep(max(0, started + offset - perf_counter()))
        for task in pending:
            if task.done():
                task.result()
        pending = {task for task in pending if not task.done()}
        pending.add(asyncio.create_task(event(offset, driver, cycle)))
        peak_pending = max(peak_pending, len(pending))
    await asyncio.sleep(max(0, started + duration - perf_counter()))
    if pending:
        done, unfinished = await asyncio.wait(pending, timeout=max(0, deadline - perf_counter()))
        counters['completion_deadline_cancelled_events'] = len(unfinished)
        for task in unfinished:
            task.cancel()
        await asyncio.gather(*unfinished, return_exceptions=True)
        for task in done:
            task.result()
    elapsed = perf_counter() - started
    return {'drivers': count, 'case': 'burst' if burst else 'staggered',
            'scheduled_gps': len(events), 'observed_intervals': 1 if burst else args.intervals,
            'cadence_seconds': None if burst else CADENCE, 'scheduled_window_seconds': duration,
            'elapsed_seconds': elapsed, 'completion_deadline_seconds': duration + args.drain_seconds,
            'peak_pending_events': peak_pending, 'counters': dict(counters),
            'http_statuses': dict(statuses), 'matching_statuses': dict(matching),
            'http_error_samples': error_samples,
            'familiarity_statuses': dict(familiarity),
            'achieved_successful_rates_per_second': {kind: counters[kind + '_successful'] / elapsed
                                                    for kind in ('gps', 'demand', 'recommendation')},
            'request_latency_ms': {k: distribution(v) for k, v in latency.items()},
            'client_queue_delay_ms': {k: distribution(v) for k, v in queue_delay.items()}}


async def run(args):
    secret = os.environ.get('ROUTE_FAMILIARITY_IDENTITY_SECRET', '')
    if len(secret.encode()) < 32:
        raise ValueError('Private ROUTE_FAMILIARITY_IDENTITY_SECRET environment value required (>=32 bytes)')
    output = validate_output(args.output)
    namespace = validate_namespace(args.namespace) if args.namespace else 'synthetic-scale-' + uuid4().hex[:12]
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    templates = []
    for template in manifest['templates']:
        if template.get('engine') != 'graphhopper':
            raise ValueError('Only GraphHopper route templates are accepted')
        points = decode_polyline(template['polyline'])
        templates.append((points, route_distances(points)))
    if not templates:
        raise ValueError('Seed manifest has no route templates')
    report = {'status': 'MEASURING', 'started_at': datetime.now(UTC).isoformat(),
              'run_namespace': namespace,
              'api_url': args.api_url, 'seed_manifest': str(Path(args.manifest)), 'seed': args.seed,
              'vehicle_template': {'canonical_vehicle_id': 'V0001', 'category': 'EV_CAR',
                                   'virtual_copies': True, 'unique_driver_ids': True},
              'warmup_intervals': 1, 'noise_bound_m': args.noise_m, 'speed_kmh': 20,
              'observation_age_seconds': OBSERVATION_AGE_SECONDS,
              'recommendation_sampling': 'EVERY_INTERVAL' if getattr(args, 'sample_every_interval', False) else 'FINAL_INTERVAL',
              'resource_metrics': 'not_measured', 'stages': [],
              'limitations': ['Single client IP; existing API rate limit is retained.',
                              'GPS timestamps use a fixed 1-second observation age; larger clock skew remains an error.',
                              'Synthetic geometry/model copies do not prove real driver behavior.',
                              'No production SLA; error and matching status counts are evidence.',
                              'Fixed namespace reuses GPS state unless the runtime is independently isolated.',
                              'Personal history requires matching --load-namespace seed inputs; burst identities have none.',
                              'Latency includes warmup; demand sampling cadence is reported separately.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    try:
        for count in args.stages:
            async with httpx.AsyncClient(base_url=args.api_url, timeout=None,
                                         limits=httpx.Limits(max_connections=args.concurrency)) as client:
                report['stages'].append(await measure_stage(client, templates, args, count, secret,
                                                            report['run_namespace']))
            save()
        # A timed-out stage must not leave its transport pool attached to the burst case.
        async with httpx.AsyncClient(base_url=args.api_url, timeout=None,
                                     limits=httpx.Limits(max_connections=args.concurrency)) as client:
            report['stages'].append(await measure_stage(client, templates, args, args.stages[-1], secret,
                                                        report['run_namespace'] + '-burst', burst=True))
        report['status'] = 'MEASURED'
    except BaseException as exc:
        report.update(status='INTERRUPTED', error=type(exc).__name__)
        raise
    finally:
        report['finished_at'] = datetime.now(UTC).isoformat()
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--manifest', default='runtime/synthetic-journeys-20261012/manifest.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--namespace', help='Fixed synthetic-scale- namespace matching seeded personal history')
    parser.add_argument('--stages', nargs='+', type=int, default=[100, 500, 1000])
    parser.add_argument('--intervals', type=int, default=3)
    parser.add_argument('--concurrency', type=int, default=32)
    parser.add_argument('--drain-seconds', type=float, default=30)
    parser.add_argument('--request-timeout', type=float, default=20)
    parser.add_argument('--burst-size', type=int, default=100)
    parser.add_argument('--demand-every', type=int, default=20)
    parser.add_argument('--sample-every-interval', action='store_true', help='Repeat the controlled demand subset each GPS interval for sustained-load measurement')
    parser.add_argument('--seed', type=int, default=20261012)
    parser.add_argument('--noise-m', type=float, default=3)
    args = parser.parse_args()
    if args.intervals < 3 or min(args.stages + [args.concurrency, args.burst_size, args.demand_every]) < 1:
        parser.error('Require >=3 intervals and positive stage/concurrency/sample sizes')
    if args.drain_seconds < 0 or args.request_timeout <= 0 or not 0 <= args.noise_m <= 10:
        parser.error('Require nonnegative drain, positive timeout, and noise within 0..10m')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
