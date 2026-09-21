"""Real GraphHopper end-to-end candidate benchmark; no synthetic fallback."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from scripts.verify_graphhopper import (
    CountingRoutingEngine, GROUPS, dataset_cases, evidence_metadata, save_evidence, search_case,
)


def latency_summary(samples):
    ordered = sorted(samples)
    def percentile(fraction):
        index = (len(ordered) - 1) * fraction
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {"count": len(samples), "min_ms": round(ordered[0], 3),
            "median_ms": round(median(samples), 3), "p90_ms": round(percentile(.90), 3),
            "p95_ms": round(percentile(.95), 3), "max_ms": round(ordered[-1], 3)}


async def run_benchmark(iterations: int = 20):
    if iterations < 20:
        raise ValueError("At least twenty searches are required for the migration benchmark")
    cases = dataset_cases()
    report = evidence_metadata()
    report.update(iterations=iterations, warmup_searches=4, percentile_method="linear interpolation", searches=[])
    async with httpx.AsyncClient(timeout=10) as client:
        adapter = GraphHopperRoutingAdapter(client=client)
        assert await adapter.is_healthy(), "GraphHopper must route both vehicle profiles"
        engine = CountingRoutingEngine(adapter)
        service = CandidateSearchService(routing_engine=engine)
        for group in GROUPS:
            _, request = next(case for case in cases if case[0] == group)
            await search_case(service, engine, group, request)
        for index in range(iterations):
            group, request = cases[index % len(cases)]
            row = await search_case(service, engine, group, request)
            report["searches"].append(row)
            print(f"{index + 1}/{iterations} {group} {row['trip_id']}: {row['latency_ms']:.1f} ms, "
                  f"{row['route_calls']} routes, {row['alternatives']} alternatives", flush=True)
    report["latency"] = latency_summary([row["latency_ms"] for row in report["searches"]])
    report["by_case"] = {}
    for group in GROUPS:
        subset = [row for row in report["searches"] if row["case"] == group]
        report["by_case"][group] = dict(latency_summary([row["latency_ms"] for row in subset]),
            route_calls=[row["route_calls"] for row in subset], alternatives=[row["alternatives"] for row in subset])
    assert any(row["case"] == "both" and row["route_calls"] == 61 for row in report["searches"])
    report["status"] = "PASS"
    save_evidence("graphhopper-week3-benchmark.json", report)
    print(report["latency"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=20)
    asyncio.run(run_benchmark(parser.parse_args().iterations))
