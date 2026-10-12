import asyncio
from argparse import Namespace

import httpx
import pytest

from scripts.measure_virtual_driver_scale import (
    distribution, measure_stage, position, route_distances, schedule,
)


def test_schedule_has_real_cadence_and_staggered_drivers():
    events = schedule(100, 3)
    assert len(events) == 300
    assert events[-1][0] == pytest.approx(89.7)
    for driver in range(100):
        times = [time for time, identity, _ in events if identity == driver]
        assert times[1] - times[0] == pytest.approx(30)
        assert times[2] - times[1] == pytest.approx(30)


def test_interpolation_moves_along_edges_without_jumping():
    points = [(21, 105), (21, 105.01), (21.01, 105.01)]
    distances = route_distances(points)
    lat, lon, heading = position(points, distances, distances[1] / 2)
    assert lat == 21
    assert lon == pytest.approx(105.005)
    assert heading == pytest.approx(90)
    assert position(points, distances, distances[-1] * 2)[:2] == points[-1]
    with pytest.raises(ValueError):
        route_distances([(21, 105), (21, 105)])


def test_latency_distribution_reports_missing_and_tail_samples():
    assert distribution([])['p99'] is None
    assert distribution(range(1, 101)) == {'samples': 100, 'p50': 50, 'p95': 95, 'p99': 99}


def test_burst_keeps_transport_bounded_and_reports_rate_limit():
    async def exercise():
        active = peak = 0

        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            assert request.url.path.endswith('/location')
            return httpx.Response(429, json={'detail': 'rate limit'})

        args = Namespace(burst_size=6, intervals=3, drain_seconds=1, concurrency=2,
                         request_timeout=1, seed=7, noise_m=3, demand_every=2)
        points = [(21, 105), (21, 105.01)]
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(handler)) as client:
            result = await measure_stage(client, [(points, route_distances(points))], args,
                                         100, 'private-unit-test', 'synthetic-test', burst=True)
        assert peak == 2
        assert result['http_statuses'] == {'gps:429': 6}
        assert result['counters']['gps_http_errors'] == 6
        assert result['achieved_successful_rates_per_second']['gps'] == 0
        assert result['request_latency_ms']['gps']['samples'] == 6
        assert 'recommendation_sent' not in result['counters']

    asyncio.run(exercise())
