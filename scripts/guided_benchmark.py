"""Frozen road-template splits and designed controls; never behavioral prevalence."""
from datetime import timedelta
import hashlib
import random

import h3

from scripts.seed_guided_hanoi import build_trip, sampled
from scripts.seed_synthetic_journeys import seed_time

SCENARIOS = ('FOLLOW', 'EXIT', 'EXIT_LATE', 'RETURN_EXIT', 'REROUTE', 'GAP', 'NOISE')


def select_templates(templates, maximum, seed):
    """Greedy marginal sampled H3-11 coverage; final length coverage needs PostGIS."""
    if not 1 <= maximum <= 240:
        raise ValueError('Template limit must be between 1 and 240')
    pending = []
    for item in templates:
        cells = {h3.latlng_to_cell(lat, lon, 11)
                 for key in ('direct', 'tail_first', 'tail_second', 'loop')
                 for lat, lon in sampled(item[key]['coordinates'])}
        pending.append((item, cells))
    covered, selected = set(), []
    while pending and len(selected) < maximum:
        pending.sort(key=lambda pair: (-len(pair[1] - covered), str(pair[0]['target']['id'])))
        item, cells = pending.pop(0)
        gain = len(cells - covered)
        if not gain:
            break
        group = h3.latlng_to_cell(*item['direct']['coordinates'][0], 7)
        bucket = int(hashlib.sha256(f'{seed}:{group}'.encode()).hexdigest(), 16) % 10
        split = 'train' if bucket < 6 else 'validation' if bucket < 8 else 'test'
        selected.append({**item, 'split_group': group, 'split': split,
                         'held_out': split != 'train', 'selection_gain_cells': gain})
        covered.update(cells)
    return selected


def benchmark_inputs(manifest, batch):
    as_of = seed_time(manifest['as_of'])
    trips, truth = [], []
    for index, item in enumerate(manifest['templates']):
        template = {key: item[key]['coordinates'] for key in ('direct', 'tail_first', 'tail_second', 'loop')}
        template.update(first_index=item['first_index'], second_index=item['second_index'])
        split = item['split']
        for scenario in SCENARIOS:
            active = dict(template)
            if scenario == 'EXIT_LATE':
                active.update(first_index=item['second_index'], second_index=item['second_index'] + 1,
                              tail_first=template['tail_second'])
            kind = 'EXIT' if scenario == 'EXIT_LATE' else scenario
            cohort = 'coverage' if scenario == 'FOLLOW' else 'stress'
            identity = f'{split}-{index}-{scenario}'
            rng = random.Random(f"{manifest['seed']}:{item['target']['id']}:{scenario}")
            started = as_of - timedelta(days={'train': 5, 'validation': 3, 'test': 1}[split],
                                       minutes=rng.randrange(60))
            gap_v2 = kind == 'GAP' and manifest.get('generator_revision', 1) >= 2
            trip = build_trip('FOLLOW' if gap_v2 else kind, active, f'h3-road-{batch}-{cohort}-{identity}',
                              f'{batch}-{identity}', started, rng)
            if gap_v2:
                if len(trip.observations) < 17:
                    raise ValueError('GAP control requires observations before and after the gap')
                middle = (len(trip.observations) - 13) // 2
                trip = trip.model_copy(update={'observations': trip.observations[:middle] + trip.observations[middle + 13:]})
            # Preserve build_trip's observation gaps and guidance revision times together.
            if trip.completed_at > as_of:
                raise ValueError('Trip extends beyond the frozen observation time')
            trips.append(trip)
            truth.append({'trip_id': trip.trip_id, 'cohort': cohort, 'scenario': scenario,
                          'held_out': split != 'train', 'split': split,
                          'split_group': item['split_group'], 'template_id': item['target']['id'],
                          'planned_departures': 2 if kind == 'RETURN_EXIT' else int(kind == 'EXIT')})
    return trips, truth


def evaluation_report(rows):
    result = {}
    for split in ('train', 'validation', 'test'):
        result[split] = {}
        for scenario in ('all', *SCENARIOS):
            subset = [r for r in rows if r['split'] == split and
                      (scenario == 'all' or r['scenario'] == scenario)]
            tp = sum(r['planned_departures'] > 0 and r['detected_events'] > 0 for r in subset)
            fp = sum(r['planned_departures'] == 0 and r['detected_events'] > 0 for r in subset)
            fn = sum(r['planned_departures'] > 0 and r['detected_events'] == 0 for r in subset)
            tn = len(subset) - tp - fp - fn
            result[split][scenario] = {
                'trips': len(subset), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
                'precision': tp / (tp + fp) if tp + fp else None,
                'recall': tp / (tp + fn) if tp + fn else None,
                'false_positive_rate': fp / (fp + tn) if fp + tn else None,
                'planned_events': sum(r['planned_departures'] for r in subset),
                'detected_events': sum(r['detected_events'] for r in subset),
                'event_count_absolute_error': sum(abs(r['detected_events'] - r['planned_departures']) for r in subset),
                'uncertain_intervals': sum(r.get('uncertain_intervals', 0) for r in subset)}
    return result
