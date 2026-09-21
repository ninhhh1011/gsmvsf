"""Initial local Week 5 HTTP performance baseline; no latency SLA or optimization."""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import httpx
from scripts.verify_week4 import summary


def validate_counts(warmup, samples):
    if warmup < 3 or samples < 20:
        raise ValueError('Baseline requires >=3 warmup and >=20 measured requests per concurrency')
    return warmup, samples


async def measure_workload(request, warmup, samples, concurrency):
    validate_counts(warmup, samples)
    warmups = [await request() for _ in range(warmup)]
    semaphore = asyncio.Semaphore(concurrency)
    async def measured():
        async with semaphore:
            return await request()
    values = await asyncio.gather(*(measured() for _ in range(samples)))
    successes = [v for v in values if v['status'] == 200]
    stages = defaultdict(list)
    for value in successes:
        for stage, latency in value['result'].get('timings_ms', {}).items():
            stages[stage].append(latency)
    return dict(concurrency=concurrency, measured_requests=samples,
        warmup_requests=warmup, warmup_success_count=sum(v['status'] == 200 for v in warmups),
        warmup_error_count=sum(v['status'] != 200 for v in warmups),
        success_count=len(successes), error_count=samples-len(successes),
        latency=summary([v['elapsed_ms'] for v in values]),
        stages={stage: summary(values) for stage, values in stages.items()},
        errors=[v for v in values if v['status'] != 200],
        eligible_counts=[v['result']['eligible_count'] for v in successes])


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8005')
    parser.add_argument('--request-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'runtime/week5/performance.json')
    parser.add_argument('--warmup', type=int, default=3)
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--cache-state', default='Natural cache after sequential warmup; TTL may expire; no forced hit claim')
    args = parser.parse_args()
    validate_counts(args.warmup, args.samples)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT/'dataset_v1'):
        parser.error('Output must be inside repository and outside Dataset')
    payload = json.loads(args.request_file.read_text(encoding='utf-8-sig'))
    report = dict(status='RUNNING', title='INITIAL LOCAL WEEK 5 PERFORMANCE BASELINE',
        timestamp=datetime.now(timezone.utc).isoformat(), api_url=args.api_url,
        workload={'endpoint': 'POST /api/v1/recommend', 'request': payload,
                  'request_file': str(args.request_file), 'concurrencies': [1, 5, 10]},
        cache_state=args.cache_state, environment={'platform': platform.platform(),
            'python': sys.version, 'logical_cpus': os.cpu_count(),
            'client': 'httpx.AsyncClient, one shared connection pool'},
        latency_scope='Client HTTP duration excludes semaphore wait; stages are server duration',
        production_sla=False, labels_consumed=False, results=[])
    try:
        async with httpx.AsyncClient(base_url=args.api_url, timeout=180) as client:
            async def request():
                began = perf_counter()
                try:
                    response = await client.post('/api/v1/recommend', json=payload)
                    item = dict(status=response.status_code, elapsed_ms=(perf_counter()-began)*1000)
                    if response.status_code == 200:
                        item['result'] = response.json()
                    else:
                        item['error'] = response.text[:1000]
                    return item
                except httpx.HTTPError as exc:
                    return dict(status=0, elapsed_ms=(perf_counter()-began)*1000, error=str(exc))
            for concurrency in (1, 5, 10):
                result = await measure_workload(request, args.warmup, args.samples, concurrency)
                report['results'].append(result)
                print(f"Concurrency {concurrency}: {result['success_count']} success / {result['error_count']} error", flush=True)
        report['status'] = 'PASS' if all(not r['error_count'] and not r['warmup_error_count'] for r in report['results']) else 'FAIL'
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
