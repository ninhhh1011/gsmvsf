"""Source-only AUTO replay through real Week 4 services; labels open after inference.

Run with python -B. Operational snapshots must already be imported. A pilot uses
evenly spaced source events, independent of labels. Each run requires a fresh
output path; predictions are flushed before any evaluation labels are opened.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def reconstruct_contexts(dataset: Path) -> list[dict]:
    """Reproduce generator 07's event schedule using runtime sources only."""
    trips = pd.read_csv(dataset / 'trips/trips.csv')
    vehicles = pd.read_csv(dataset / 'vehicles/vehicles.csv').set_index('vehicle_id')
    battery = {key: rows.reset_index(drop=True) for key, rows in
               pd.read_csv(dataset / 'battery/soc_history.csv.gz').groupby('trip_id', sort=False)}
    gps = pd.read_csv(dataset / 'gps/gps_observations.csv.gz')
    gps['observed_time'] = pd.to_datetime(gps.timestamp, format='mixed')
    gps = {key: rows.sort_values(['observed_time', 'observation_id']).reset_index(drop=True)
           for key, rows in gps.groupby('trip_id', sort=False)}
    nodes = pd.read_csv(dataset / 'map/processed/road_nodes.csv.gz').set_index('node_id')
    contexts, counter = [], 1
    for trip in trips.itertuples(index=False):
        history, observations = battery[trip.trip_id], gps[trip.trip_id]
        vehicle, destination = vehicles.loc[trip.vehicle_id], nodes.loc[trip.destination_node_id]
        n = len(history)
        positions = sorted(set(int(round(x)) for x in
                               np.linspace(max(1, n * .08), max(1, n * .92), 8)))
        while len(positions) < 8:
            candidate = min(n - 1, positions[-1] + 1 if positions else 1)
            if candidate in positions:
                break
            positions.append(candidate)
        for snapshot_index, position in enumerate(positions[:8], 1):
            soc = history.iloc[min(position, n - 1)]
            stamp = pd.Timestamp(soc.timestamp)
            # Select before datetime conversion: Dataset timestamps contain nanoseconds.
            gps_index = observations.observed_time.searchsorted(stamp, side='right') - 1
            if gps_index < 0:
                raise ValueError(f'No causal GPS for {trip.trip_id} at {soc.timestamp}')
            observation = observations.iloc[gps_index]
            remaining = max(0., float(trip.planned_network_distance_m) / 1000
                            - float(soc.distance_travelled_km))
            contexts.append(dict(event_id=f'DE{counter:06d}', snapshot_index=snapshot_index,
                event_timestamp=str(soc.timestamp), observation_id=observation.observation_id,
                gps_timestamp=str(observation.timestamp),
                gps_age_s=(stamp - observation.observed_time).total_seconds(),
                origin_method='CAUSAL_RAW_GPS_NO_MATCHED_SEGMENT',
                context=dict(vehicle_id=trip.vehicle_id, driver_id=trip.driver_id,
                    trip_id=trip.trip_id, timestamp=str(soc.timestamp),
                    current_soc_pct=float(soc.soc_pct),
                    estimated_remaining_range_km=float(soc.estimated_remaining_range_km),
                    remaining_trip_distance_km=remaining, safety_reserve_km=max(1., remaining * .15),
                    consumption_wh_per_km=float(vehicle.consumption_wh_per_km),
                    minimum_safe_soc_pct=float(vehicle.minimum_safe_soc_pct),
                    raw_latitude=float(observation.latitude), raw_longitude=float(observation.longitude),
                    road_segment_id=None),
                destination_latitude=float(destination.latitude),
                destination_longitude=float(destination.longitude), destination_node_id=trip.destination_node_id))
            counter += 4 if bool(vehicle.swap_supported) else 3
    if len(contexts) != len(trips) * 8 or len({row['event_id'] for row in contexts}) != len(contexts):
        raise ValueError('Source event schedule must contain eight unique AUTO contexts per trip')
    return contexts


def identity(row):
    return (row['station_id'], row['service_type'])


def compare_order(predicted, reference):
    common = set(predicted) & set(reference)
    pred, ref = [key for key in predicted if key in common], [key for key in reference if key in common]
    positions = {key: index for index, key in enumerate(pred)}
    pairs = list(combinations(ref, 2))
    return dict(common_count=len(common),
        common_top1_station_match=pred[0][0] == ref[0][0] if common else None,
        common_top1_identity_match=pred[0] == ref[0] if common else None,
        pairwise_agree=sum(positions[a] < positions[b] for a, b in pairs), pairwise_total=len(pairs))


def baseline_orders(row):
    ranked = row['ranked']
    return {
        'nearest_eligible': [identity(c) for c in sorted(ranked,
            key=lambda c: (c['distance_to_station_m'], *identity(c)))],
        'minimum_station_eta': [identity(c) for c in sorted(ranked,
            key=lambda c: (c['eta_to_station_s'], *identity(c)))],
        'total_service_completion': [identity(c) for c in ranked],
    }


def rate(matches=0, total=0):
    return dict(matches=int(matches), total=int(total), rate=matches / total if total else None)


def group_size(count):
    return 'zero' if count == 0 else 'single' if count == 1 else 'multiple'


def summarize_counts(count):
    return dict(
        recommendation_presence=rate(count['presence_match'], count['presence_total']),
        overall_station_agreement=rate(count['station_match'] + count['empty_match'], count['presence_total']),
        overall_composite_agreement=rate(count['identity_match'] + count['empty_match'], count['presence_total']),
        station_top1=rate(count['station_match'], count['station_total']),
        composite_top1=rate(count['identity_match'], count['identity_total']),
        service_type_top1=rate(count['service_match'], count['service_total']),
        reference_best_in_runtime_pool=rate(count['reference_best_in_pool'], count['identity_total']),
        common_pool_station_top1=rate(count['common_station_match'], count['common_events']),
        common_pool_composite_top1=rate(count['common_identity_match'], count['common_events']),
        pairwise_common_pool=rate(count['pairwise_match'], count['pairwise_total']),
        pairwise_comparable_events=count['pairwise_events'])


def evaluate_predictions(predictions, recommendations, ranking):
    """Offline comparisons only. Inputs are finished predictions and evaluation tables."""
    recs = recommendations.set_index('event_id').to_dict('index')
    groups = {key: frame.sort_values('reference_rank').to_dict('records')
              for key, frame in ranking.groupby('event_id', sort=False)}
    report = dict(prediction_count=len(predictions), reference_events=0,
        runtime_group_sizes=dict(zero=0, single=0, multiple=0),
        reference_group_sizes=dict(zero=0, single=0, multiple=0),
        baselines={}, mismatch_examples=[], mismatch_causes={})
    names = ('nearest_eligible', 'minimum_station_eta', 'total_service_completion')
    counters = {name: Counter() for name in names}
    by_group = {name: {size: Counter() for size in ('zero', 'single', 'multiple')} for name in names}
    causes = Counter()
    sampled_causes = Counter()
    for row in predictions:
        report['runtime_group_sizes'][group_size(len(row['ranked']))] += 1
        event_id = row['event_id']
        if event_id not in recs:
            continue
        reference, ref_rows = recs[event_id], groups.get(event_id, [])
        ref_order = [identity(c) for c in ref_rows]
        ref_best = ref_order[0] if ref_order else None
        expected = bool(reference['has_recommendation'])
        report['reference_events'] += 1
        report['reference_group_sizes'][group_size(len(ref_rows))] += 1
        orders = baseline_orders(row)
        for name, order in orders.items():
            count = counters[name]
            before = count.copy()
            count['presence_total'] += 1
            count['presence_match'] += bool(order) == expected
            count['empty_match'] += not order and not expected
            if expected:
                count['station_total'] += 1
                count['station_match'] += bool(order) and order[0][0] == reference['reference_station_id']
            if ref_best:
                count['identity_total'] += 1
                count['identity_match'] += bool(order) and order[0] == ref_best
                count['service_total'] += 1
                count['service_match'] += bool(order) and order[0][1] == ref_best[1]
                count['reference_best_in_pool'] += ref_best in set(order)
            common = compare_order(order, ref_order)
            count['common_events'] += common['common_count'] > 0
            count['common_station_match'] += common['common_top1_station_match'] is True
            count['common_identity_match'] += common['common_top1_identity_match'] is True
            count['pairwise_match'] += common['pairwise_agree']
            count['pairwise_total'] += common['pairwise_total']
            count['pairwise_events'] += common['pairwise_total'] > 0
            by_group[name][group_size(len(ref_rows))].update(
                {key: value - before[key] for key, value in count.items()})
        order = orders['total_service_completion']
        best = order[0] if order else None
        if best == ref_best and bool(order) == expected:
            continue
        event_causes = []
        if bool(order) != expected:
            event_causes.append('RECOMMENDATION_PRESENCE_DIFFERS')
        if ref_best and ref_best not in order:
            event_causes.append('REFERENCE_BEST_NOT_RUNTIME_ELIGIBLE')
        if best and best not in ref_order:
            event_causes.append('RUNTIME_BEST_OUTSIDE_REFERENCE_POOL')
        if best and ref_best and best in ref_order and ref_best in order:
            event_causes.append('ORDER_DIFFERS_WITHIN_COMMON_POOL')
        causes.update(event_causes)
        if len(report['mismatch_examples']) < 20 and any(sampled_causes[cause] < 3 for cause in event_causes):
            sampled_causes.update(event_causes)
            reference_candidate = next((c for c in row['candidates'] if identity(c) == ref_best), None)
            live_ref = next((c for c in row['ranked'] if identity(c) == ref_best), None)
            report['mismatch_examples'].append(dict(event_id=event_id,
                runtime_best=best, reference_best=ref_best, causes=event_causes,
                runtime_eligible_count=len(order), reference_pool_count=len(ref_order),
                reference_eligible_count=int(reference['eligible_candidate_count']),
                runtime_best_metrics=row['ranked'][0] if order else None,
                reference_best_runtime_eligibility=reference_candidate,
                reference_best_runtime_metrics=live_ref,
                reference_best_frozen_metrics=ref_rows[0] if ref_rows else None,
                policy_difference='Runtime minimizes station arrival + queue + service; reference includes '
                    'onward travel, detour penalties and capacity credit. Route/profile/origin and traffic '
                    'inputs also differ; this comparison does not isolate their causal contributions.'))
    report['mismatch_causes'] = dict(causes)
    for name, count in counters.items():
        report['baselines'][name] = summarize_counts(count)
        report['baselines'][name]['by_reference_group'] = {
            size: summarize_counts(values) for size, values in by_group[name].items()}
    report['eligible_count_distribution'] = {}
    for name, values in (
        ('all_predictions', [len(row['ranked']) for row in predictions]),
        ('joined_reference_events', [len(row['ranked']) for row in predictions if row['event_id'] in recs]),
    ):
        report['eligible_count_distribution'][name] = dict(count=len(values),
            min=min(values) if values else None, median=float(np.median(values)) if values else None,
            max=max(values) if values else None,
            histogram={str(size): count for size, count in sorted(Counter(values).items())})
    return report


def fingerprint(contexts, dataset, settings):
    files = [Path(__file__), *sorted((ROOT / 'backend/app').rglob('*.py')),
             *[dataset / name for name in ('stations/stations.csv', 'vehicles/vehicles.csv',
                'vehicles/vehicle_model_catalog.csv',
                'stations/station_status.csv.gz', 'queue/queue_status.csv.gz', 'traffic/traffic_snapshots.csv.gz')]]
    digest = sha256(json.dumps(contexts, sort_keys=True).encode())
    for path in files:
        digest.update(path.read_bytes())
    # Hash backend settings (including connection identity); never expose credentials.
    digest.update(settings.model_dump_json().encode())
    return digest.hexdigest()


async def predict(contexts, prediction_path, dataset):
    from backend.app.config import settings
    from backend.app.main import create_app
    from backend.app.services.candidate.models import CandidateSearchRequest
    from backend.app.services.demand.models import DemandContext
    from backend.app.services.demand.service import get_demand_service

    manifest = dict(kind='manifest', schema_version=1, fingerprint=fingerprint(contexts, dataset, settings),
                    event_ids=[c['event_id'] for c in contexts], location_method='CAUSAL_RAW_GPS',
                    traffic_method='MISSING_NO_MATCHED_SEGMENT', engine='graphhopper', labels_consumed=False)
    predictions = []
    if prediction_path.exists():
        raise FileExistsError(f'{prediction_path} exists; use a new --output')
    prediction_path.write_text(json.dumps(manifest) + '\n', encoding='utf-8')

    app = create_app()
    demand = get_demand_service()
    async with app.router.lifespan_context(app):
        workflow = app.state.recommendation_workflow
        if not await workflow.routing_engine.is_healthy():
            raise RuntimeError('GraphHopper must route both profiles; evaluation aborted')
        await workflow.resolver.cache.client.ping()
        async with workflow.repository.connection() as connection:
            snapshot_counts = {r['kind']: r['count'] for r in await connection.fetch(
                'SELECT kind,count(*) AS count FROM state_snapshots GROUP BY kind')}
        if any(not snapshot_counts.get(kind) for kind in ('station', 'queue', 'traffic')):
            raise RuntimeError('Import canonical Week 4 station/queue/traffic snapshots before evaluation')
        with prediction_path.open('a', encoding='utf-8') as handle:
            for index, source in enumerate(contexts, 1):
                energy = demand.evaluate_auto_demand(DemandContext.model_validate(source['context']),
                                                     service_request_id=source['event_id'])
                request = CandidateSearchRequest(energy_request=energy,
                    **{key: source[key] for key in ('destination_latitude', 'destination_longitude',
                                                   'destination_node_id')})
                started = perf_counter()
                result = await workflow.recommend(request)
                latency_ms = (perf_counter() - started) * 1000
                evidence = await workflow.repository.get_search(result.candidate_search_id)
                ranked = [dict(station_id=c.station_id, service_type=c.service_type.value,
                    distance_to_station_m=c.features.distance_to_station_m,
                    eta_to_station_s=c.eta_to_station_s, eta_to_service_start_s=c.eta_to_service_start_s,
                    eta_to_service_complete_s=c.eta_to_service_complete_s, final_cost_s=c.final_cost_s,
                    queue_wait_s=c.features.effective_queue_wait_s, service_duration_s=c.features.service_duration_s,
                    traffic_method=c.features.traffic_method, traffic_freshness=c.features.traffic_state.freshness,
                    available_capacity=c.features.available_capacity,
                    detour_duration_s=c.features.detour_duration_s, detour_distance_m=c.features.detour_distance_m,
                    station_snapshot_id=c.features.station_state.snapshot_id,
                    queue_snapshot_id=c.features.queue_state.snapshot_id) for c in result.ranked_candidates]
                row = dict(event_id=source['event_id'], source=source,
                    candidate_search_id=result.candidate_search_id, need_service=energy.need_service,
                    policy=result.policy.model_dump(mode='json'), degraded_reasons=result.degraded_reasons,
                    latency_ms=latency_ms, ranked=ranked,
                    candidates=[dict(station_id=c.station_id, service_type=c.service_type.value,
                        eligible=c.eligible, reason=c.reason.value,
                        route_metrics=c.route_metrics.model_dump(mode='json') if c.route_metrics else None)
                        for c in evidence.result.candidates])
                handle.write(json.dumps(row, allow_nan=False) + '\n')
                handle.flush()
                predictions.append(row)
                print(f'{index}/{len(contexts)} {source["event_id"]}: '
                      f'{len(ranked)} eligible, {latency_ms:.1f} ms', flush=True)
        metadata = dict(snapshot_counts=snapshot_counts, snapshot_resolver_metrics=dict(workflow.resolver.metrics))
    return predictions, manifest, metadata


async def run(args):
    from backend.app.config import settings
    output = Path(args.output).resolve()
    runtime = (ROOT / 'runtime/week4').resolve()
    if not output.is_relative_to(runtime) or output.suffix != '.json':
        raise ValueError('--output must be a .json file inside runtime/week4')
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset = settings.dataset_path.resolve()
    contexts = reconstruct_contexts(dataset)
    total_contexts = len(contexts)
    if args.limit is not None:
        if not 1 <= args.limit <= total_contexts:
            raise ValueError(f'--limit must be between 1 and {total_contexts}')
        contexts = [contexts[i] for i in np.linspace(0, total_contexts - 1, args.limit, dtype=int)]
    prediction_path = output.with_suffix('.predictions.jsonl')
    predictions, manifest, metadata = await predict(contexts, prediction_path, dataset)
    # This is the first evaluation-label read. A failed/incomplete inference never reaches it.
    recommendations = pd.read_csv(dataset / 'labels/recommendation_labels.csv')
    ranking = pd.read_csv(dataset / 'training/ranking_reference.csv')
    report = evaluate_predictions(predictions, recommendations, ranking)
    report.update(status='COMPLETE' if args.limit is None else 'PILOT_COMPLETE',
        total_source_contexts=total_contexts, manifest=manifest, backend=metadata,
        prediction_file=str(prediction_path.relative_to(ROOT)),
        demand_counts=dict(Counter('need_service' if p['need_service'] else 'no_service' for p in predictions)),
        degraded_reasons=dict(Counter(reason for p in predictions for reason in p['degraded_reasons'])),
        gps_age_max_s=max(p['source']['gps_age_s'] for p in predictions),
        latency_ms=dict(zip(('median', 'p90', 'p95', 'max'),
                           [float(x) for x in np.percentile([p['latency_ms'] for p in predictions], [50, 90, 95, 100])])),
        limitations=[
            'Raw causal GPS replay excludes map matching; no truth segment is consumed. Traffic is explicitly MISSING.',
            'All runtime eligible alternatives are ranked; reference ranks at most nearest eight.',
            'Reference minimizes both travel legs plus queue/service and detour/capacity terms; runtime minimizes service completion.',
            'Reference uses true-segment origins, separate shortest-time/distance matrices, future trip-end direct ETA and synthetic traffic factors.',
            'Top1 positive denominators exclude empty references; presence compares all joined recommendation events.',
            'Overall station/composite agreement counts matching no-recommendation outcomes across all joined reference events.',
            'Common-pool metrics restrict both orders to identical station/service pairs; empty intersections and singletons do not create pairwise accuracy.',
            'Service-only top1 can match at different stations; composite top1 requires both station and service.',
            'Latency is sequential service-workflow time including persisted state, not HTTP load or production capacity.',
        ])
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'prediction_count', 'reference_events',
                                                'runtime_group_sizes', 'baselines')}, indent=2))
    print(f'Report: {output}')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', default=str(ROOT / 'runtime/week4/evaluation.json'))
    asyncio.run(run(parser.parse_args()))
