from datetime import UTC, datetime
import random

import pytest

from scripts.seed_guided_hanoi import build_trip, checked_join, sampled


def test_seed_rejects_disconnected_road_chunks_instead_of_drawing_a_fake_bridge():
    with pytest.raises(ValueError, match='Disconnected'):
        checked_join([[21, 105.8]], [[21.1, 105.9]])


def test_follow_and_updated_guidance_have_causal_times_and_no_future_observations():
    points = [[21 + i * 0.0003, 105.8] for i in range(120)]
    template = {'direct': points, 'tail_first': points[40:], 'tail_second': points[80:],
                'loop': [points[40], [points[40][0], 105.801], points[40]]}
    started = datetime(2026, 10, 13, tzinfo=UTC)
    for kind in ('FOLLOW', 'REROUTE', 'NOISE', 'GAP'):
        trip = build_trip(kind, template, 'd', kind, started, random.Random(7))
        assert trip.observations[-1].at < trip.completed_at
        assert trip.observations[0].at == started
        assert all(a.at < b.at for a, b in zip(trip.observations, trip.observations[1:]))
        if kind == 'REROUTE':
            assert len(trip.guidance) == 2
            assert trip.guidance[1].effective_at == trip.observations[len(sampled(points)) // 3].at
        if kind == 'GAP':
            assert max((b.at - a.at).total_seconds() for a, b in zip(trip.observations, trip.observations[1:])) > 60
