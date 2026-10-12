import asyncio
from argparse import Namespace
import hashlib
import hmac
import json

import httpx
import pytest

import scripts.measure_virtual_driver_scale as scale

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


def test_staggered_demand_triggers_signed_recommendation_only_for_controlled_subset(monkeypatch):
    monkeypatch.setattr(scale, 'CADENCE', 0.02)  # Test scheduler only; live CLI has fixed 30s cadence.

    async def exercise():
        calls = []

        async def handler(request):
            payload = json.loads(request.content)
            calls.append((request.url.path, payload))
            if request.url.path.endswith('/location'):
                return httpx.Response(200, json={'status': 'WARMING_UP'})
            if request.url.path.endswith('/evaluate'):
                return httpx.Response(200, json={'need_service': False})
            driver = payload['context']['driver_id']
            expected = hmac.new(b'private-unit-secret', driver.encode(), hashlib.sha256).hexdigest()
            assert request.headers['X-Driver-Identity-Signature'] == expected
            assert payload['requested_service'] == 'CHARGING'
            return httpx.Response(200, json={'familiarity': {'status': 'AVAILABLE'}})

        args = Namespace(burst_size=2, intervals=3, drain_seconds=1, concurrency=2,
                         request_timeout=1, seed=7, noise_m=3, demand_every=1)
        points = [(21, 105), (21, 105.01)]
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(handler)) as client:
            result = await measure_stage(client, [(points, route_distances(points))], args,
                                         2, 'private-unit-secret', 'synthetic-scale-test')
        assert result['counters']['gps_successful'] == 6
        assert result['counters']['demand_successful'] == 2
        assert result['counters']['recommendation_successful'] == 1
        assert result['counters']['demand_without_recommendation'] == 1
        assert result['familiarity_statuses'] == {'AVAILABLE': 1}
        assert len(calls) == 9

    asyncio.run(exercise())


@pytest.mark.parametrize('request_timeout', [0.01, 10])
def test_request_deadline_reports_timeout_and_never_recommends(request_timeout):
    async def exercise():
        async def handler(request):
            await asyncio.sleep(5)
            return httpx.Response(200, json={'status': 'MATCHED'})

        args = Namespace(burst_size=3, intervals=3, drain_seconds=0, concurrency=1,
                         request_timeout=request_timeout, seed=7, noise_m=3, demand_every=1)
        points = [(21, 105), (21, 105.01)]
        async with httpx.AsyncClient(base_url='http://test', transport=httpx.MockTransport(handler)) as client:
            result = await measure_stage(client, [(points, route_distances(points))], args,
                                         100, 'private-unit-secret', 'synthetic-scale-test', burst=True)
        # At the stage boundary timeout, queued drops and cancellation race legitimately.
        assert sum(result['counters'].get(key, 0) for key in (
            'gps_transport_error:TimeoutError', 'gps_deadline_dropped',
            'completion_deadline_cancelled_events')) == 3
        assert result['achieved_successful_rates_per_second']['gps'] == 0

    asyncio.run(exercise())


def test_run_output_protection_missing_manifest_and_transport_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(scale, 'ROOT', tmp_path)
    monkeypatch.setenv('ROUTE_FAMILIARITY_IDENTITY_SECRET', 'private-unit-secret-01234567890123456789')
    existing = tmp_path / 'old.json'
    existing.write_text('original')
    for output in (existing, tmp_path / 'dataset_v1' / 'bad.json', tmp_path.parent / 'outside.json'):
        with pytest.raises(ValueError):
            scale.validate_output(output)
    assert existing.read_text() == 'original'
    args = Namespace(output=tmp_path / 'report.json', namespace='synthetic-scale-test',
                     manifest=tmp_path / 'missing.json', seed=7, api_url='http://test',
                     concurrency=1, noise_m=3, stages=[100])
    with pytest.raises(FileNotFoundError):
        asyncio.run(scale.run(args))
    assert not args.output.exists()
    args.manifest.write_text(json.dumps({'templates': [{'engine': 'graphhopper',
                                            'polyline': '_y~_C_qz_S?o}@'}]}))

    async def stage(client, *unused, **kwargs):
        assert client.timeout.read is None
        assert client.timeout.connect is None
        return {'case': 'unit-test-only'}

    monkeypatch.setattr(scale, 'measure_stage', stage)
    asyncio.run(scale.run(args))
    assert json.loads(args.output.read_text())['run_namespace'] == 'synthetic-scale-test'
