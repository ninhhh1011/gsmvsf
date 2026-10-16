from datetime import UTC, datetime

from scripts.guided_benchmark import select_templates, benchmark_inputs, evaluation_report
from scripts.seed_guided_hanoi import sampled


def template(index=0):
    lat = 20.85 + index * .006
    coordinates = [[lat + i * .0003, 105.8] for i in range(60)]
    points = sampled(coordinates)
    return {'direct': {'coordinates': coordinates}, 'first_index': 8, 'second_index': 30,
            'tail_first': {'coordinates': points[8:]}, 'tail_second': {'coordinates': points[30:]},
            'loop': {'coordinates': [points[8], [points[8][0], 105.801], points[8]]},
            'target': {'id': str(index), 'latitude': lat, 'longitude': 105.8}}


def test_selection_is_order_independent_and_ignores_duplicate_footprints():
    rows = [template(i) for i in range(40)]
    rows.append({**rows[0], 'target': {**rows[0]['target'], 'id': 'duplicate'}})
    a = select_templates(rows, 30, 17)
    b = select_templates(list(reversed(rows)), 30, 17)
    assert a == b
    assert len(a) == 30
    assert len({str(row['direct']['coordinates']) for row in a}) == 30
    groups = {}
    for row in a:
        groups.setdefault(row['split_group'], set()).add(row['split'])
    assert all(len(splits) == 1 for splits in groups.values())
    assert {row['split'] for row in a} == {'train', 'validation', 'test'}


def test_cases_have_disjoint_drivers_and_preserve_gaps_and_guidance_updates():
    selected = select_templates([template(i) for i in range(40)], 30, 17)
    manifest = {'seed': 17, 'as_of': datetime(2026, 10, 15, tzinfo=UTC).isoformat(),
                'templates': selected}
    trips, truth = benchmark_inputs(manifest, 'example')
    assert len(trips) == 7 * len(selected)
    drivers = {}
    for trip, declaration in zip(trips, truth):
        drivers.setdefault(declaration['split'], set()).add(trip.driver_id)
        assert trip.completed_at <= datetime(2026, 10, 15, tzinfo=UTC)
        if declaration['scenario'] == 'GAP':
            assert max((b.at-a.at).total_seconds() for a,b in zip(trip.observations,trip.observations[1:])) > 60
        if declaration['scenario'] == 'REROUTE':
            assert len(trip.guidance) == 2
            assert trip.guidance[1].effective_at in {p.at for p in trip.observations}
    assert not drivers['train'] & drivers['test']
    assert not drivers['train'] & drivers['validation']
    assert not drivers['test'] & drivers['validation']
    assert {row['scenario'] for row in truth} == {
        'FOLLOW','EXIT','EXIT_LATE','RETURN_EXIT','REROUTE','GAP','NOISE'}


def test_metrics_count_errors_instead_of_rejecting_bad_cases():
    rows = [{'split': 'test', 'scenario': s, 'planned_departures': expected,
             'detected_events': actual} for s,expected,actual in
            [('FOLLOW',0,1),('EXIT',1,0),('EXIT_LATE',1,1),('GAP',0,0)]]
    report = evaluation_report(rows)['test']['all']
    assert (report['tp'],report['fp'],report['fn'],report['tn']) == (1,1,1,1)
    assert report['precision'] == report['recall'] == .5
    empty = evaluation_report([])['test']['all']
    assert empty['precision'] is None and empty['recall'] is None


def test_short_gap_control_keeps_observations_on_both_sides():
    item = template()
    direct = [[21 + i * .0001, 105.8] for i in range(60)]
    points = sampled(direct)
    item.update(direct={'coordinates': direct}, first_index=3, second_index=10,
                tail_first={'coordinates': points[3:]}, tail_second={'coordinates': points[10:]},
                loop={'coordinates': [points[3], [points[3][0],105.801], points[3]]},
                split='train', split_group='group')
    trips, truth = benchmark_inputs({'seed':17,'as_of':'2026-10-15T09:00:00Z','templates':[item],
                                    'generator_revision':2}, 'small')
    gap = next(t for t,r in zip(trips,truth) if r['scenario']=='GAP')
    assert max((b.at-a.at).total_seconds() for a,b in zip(gap.observations,gap.observations[1:])) > 60
    assert gap.observations[-1].coordinates == tuple(direct[-1])
