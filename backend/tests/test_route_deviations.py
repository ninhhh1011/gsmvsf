from datetime import UTC, datetime, timedelta

import h3
import pytest
from pydantic import ValidationError

from backend.app.services.route_familiarity.deviations import GuidedTrip, analyze_guided_trip

BASE = datetime(2026, 10, 14, 0, tzinfo=UTC)


def point(north, east=0):
    return [21 + north / 111195, 105.8 + east / 103810]


def evidence(points, *, guidance=None, times=None):
    times = times or [i * 5 for i in range(len(points))]
    return GuidedTrip.model_validate({
        'driver_id': 'fake-driver', 'trip_id': 'fake-trip',
        'started_at': BASE, 'completed_at': BASE + timedelta(seconds=times[-1] + 1),
        'guidance': guidance or [{'effective_at': BASE, 'coordinates': [point(0), point(1500)]}],
        'observations': [{'at': BASE + timedelta(seconds=t), 'coordinates': p}
                         for t, p in zip(times, points)],
    })


def events(result, resolution=9):
    return sum(len(value['departures']) for value in result['cells'][str(resolution)].values())


def test_noisy_following_is_not_departure():
    result = analyze_guided_trip(evidence([point(i * 20, (-1) ** i * 8) for i in range(20)]))
    assert events(result) == 0
    assert result['comparable']


def test_one_long_departure_is_one_event_at_last_guided_location():
    points = [point(i * 20) for i in range(6)] + [point(120 + i * 20, 100) for i in range(12)]
    result = analyze_guided_trip(evidence(points))
    assert events(result) == 1
    origin = h3.latlng_to_cell(*point(100), 9)
    assert len(result['cells']['9'][origin]['departures']) == 1
    assert result['cells']['9'][origin]['reached']
    off_cell = h3.latlng_to_cell(*points[-1], 10)
    assert result['cells']['10'][off_cell]['observed']


def test_return_rearms_and_counts_every_departure_even_in_same_cell():
    points = ([point(i * 15) for i in range(4)] +
              [point(60 + i * 15, 70) for i in range(4)] +
              [point(120 + i * 15) for i in range(4)] +
              [point(180 + i * 15, 70) for i in range(4)])
    result = analyze_guided_trip(evidence(points))
    assert events(result) == 2
    assert events(result, 5) == 2


def test_confirmed_return_to_earlier_route_progress_rearms():
    points = ([point(i * 20) for i in range(11)] +
              [point(200 + i * 20, 100) for i in range(4)] +
              [point(240 - i * 20, 100) for i in range(13)] +
              [point(i * 15) for i in range(5)] +
              [point(80 + i * 15, 100) for i in range(6)])
    assert events(analyze_guided_trip(evidence(points))) == 2


def test_isolated_outlier_and_short_unconfirmed_exit_do_not_count():
    points = [point(i * 20) for i in range(6)] + [point(120, 70)] + [point(i * 20) for i in range(7, 15)]
    assert events(analyze_guided_trip(evidence(points))) == 0
    assert events(analyze_guided_trip(evidence([point(i * 20) for i in range(6)] + [point(120, 70)]))) == 0


def test_guidance_update_is_not_departure():
    points = [point(i * 20) for i in range(6)] + [point(120 + i * 20, 100) for i in range(6)]
    guidance = [{'effective_at': BASE, 'coordinates': [point(0), point(1500)]},
                {'effective_at': BASE + timedelta(seconds=30), 'coordinates': [point(100, 100), point(1500, 100)]}]
    assert events(analyze_guided_trip(evidence(points, guidance=guidance))) == 0


def test_gap_does_not_invent_departure_and_trip_starting_off_route_is_unknown():
    points = [point(i * 20) for i in range(6)] + [point(120 + i * 20, 100) for i in range(6)]
    result = analyze_guided_trip(evidence(points, times=list(range(0, 30, 5)) + list(range(100, 130, 5))))
    assert events(result) == 0
    assert result['uncertain_intervals'] > 0
    origin = h3.latlng_to_cell(*point(100), 9)
    assert result['cells']['9'][origin]['uncertain']
    result = analyze_guided_trip(evidence([point(i * 20, 100) for i in range(10)]))
    assert not result['comparable']
    assert events(result) == 0


def test_unobserved_trip_tail_is_uncertain_instead_of_zero_departures():
    data = evidence([point(i * 20) for i in range(6)]).model_dump()
    data['completed_at'] += timedelta(hours=1)
    result = analyze_guided_trip(GuidedTrip.model_validate(data))
    origin = h3.latlng_to_cell(*point(100), 9)
    assert result['cells']['9'][origin]['uncertain']
    assert result['uncertain_intervals'] > 0


@pytest.mark.parametrize('mutation', ['naive', 'reversed', 'future', 'duplicate', 'nonfinite', 'unissued'])
def test_invalid_evidence_is_rejected(mutation):
    data = evidence([point(i * 20) for i in range(6)]).model_dump(mode='json')
    if mutation == 'naive':
        data['observations'][0]['at'] = '2026-10-14T00:00:00'
    elif mutation == 'reversed':
        data['observations'].reverse()
    elif mutation == 'future':
        data['observations'][-1]['at'] = (BASE + timedelta(days=1)).isoformat()
    elif mutation == 'duplicate':
        data['guidance'].append(data['guidance'][0])
    elif mutation == 'unissued':
        data['guidance'][0]['effective_at'] = (BASE + timedelta(seconds=5)).isoformat()
    else:
        data['observations'][0]['coordinates'][0] = float('nan')
    with pytest.raises(ValidationError):
        GuidedTrip.model_validate(data)
