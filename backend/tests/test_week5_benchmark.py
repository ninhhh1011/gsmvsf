import pytest
from scripts.benchmark_week5 import measure_workload, validate_counts


def test_benchmark_minimums():
    assert validate_counts(3, 20) == (3, 20)
    for warmup, samples in [(2, 20), (3, 19)]:
        with pytest.raises(ValueError):
            validate_counts(warmup, samples)


@pytest.mark.asyncio
async def test_benchmark_counts_errors_and_stage_distributions():
    calls = []
    async def request():
        calls.append(1)
        if len(calls) == 4:
            return {'status': 503, 'elapsed_ms': 4, 'error': 'unavailable'}
        return {'status': 200, 'elapsed_ms': 2, 'result': {
            'eligible_count': 1, 'timings_ms': {'demand': 0.5, 'total': 1.5}}}
    result = await measure_workload(request, 3, 20, 5)
    assert len(calls) == 23
    assert result['success_count'] == 19 and result['error_count'] == 1
    assert result['latency']['samples'] == 20
    assert result['stages']['demand']['samples'] == 19
    assert result['stages']['demand']['median_ms'] == 0.5
    assert result['warmup_success_count'] == 3
