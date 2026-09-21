"""Replay frozen GPS through the real matching service; labels are joined afterwards.

Run from the repository root. No engines are started and no Dataset files are written.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DEBUG"] = "false"

import httpx
from backend.app.services.map_matching.engine import MapMatchingNoMatchError
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter
from backend.app.services.map_matching.models import GPSObservation, MapMatchRequest
from backend.app.services.map_matching.segment_resolver import RouteConstrainedSegmentResolver
from backend.app.services.map_matching.service import MapMatchingService


def rows(relative):
    with gzip.open(ROOT / "dataset_v1" / relative, "rt", encoding="utf-8") as stream:
        yield from csv.DictReader(stream)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    lower = int(rank)
    return ordered[lower] + (ordered[math.ceil(rank)] - ordered[lower]) * (rank - lower)


def distribution(values):
    return {"count": len(values), "mean": statistics.mean(values) if values else None,
            "median": percentile(values, .5), "p90": percentile(values, .9),
            "p95": percentile(values, .95), "max": max(values) if values else None}


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(a)))


def score(predictions, labels, segments):
    counts = Counter()
    errors, mismatches = [], []
    for observation_id, prediction in predictions.items():
        truth = labels.get(observation_id)
        if truth is None:
            continue
        counts["labeled"] += 1
        if not prediction["matched"]:
            continue
        counts["matched"] += 1
        expected = segments[truth["true_segment_id"]]
        actual = segments.get(prediction["road_segment_id"])
        counts["resolved"] += actual is not None
        correct = {
            "directed_segment": prediction["road_segment_id"] == truth["true_segment_id"],
            "base_segment": actual is not None and actual["base_segment_id"] == expected["base_segment_id"],
            "osm_way": prediction["osm_way_id"] == int(expected["osm_way_id"]),
            "direction": prediction["direction"] == truth["true_direction"],
        }
        counts.update({key: int(value) for key, value in correct.items()})
        error = distance_m(prediction["matched_latitude"], prediction["matched_longitude"],
                           float(truth["true_latitude"]), float(truth["true_longitude"]))
        errors.append(error)
        if not correct["directed_segment"]:
            mismatches.append({"observation_id": observation_id, "position_error_m": error,
                               "expected_segment": truth["true_segment_id"],
                               "actual_segment": prediction["road_segment_id"],
                               "expected_way": int(expected["osm_way_id"]),
                               "actual_way": prediction["osm_way_id"],
                               "expected_direction": truth["true_direction"],
                               "actual_direction": prediction["direction"],
                               "same_base": correct["base_segment"], "same_way": correct["osm_way"],
                               "resolution_status": prediction["resolution_status"]})
    return {"counts": dict(counts), "match_rate": counts["matched"] / counts["labeled"] if counts["labeled"] else None,
            "accuracy_among_matched": {key: counts[key] / counts["matched"] if counts["matched"] else None
                                       for key in ("directed_segment", "base_segment", "osm_way", "direction")},
            "accuracy_among_all_labeled": {key: counts[key] / counts["labeled"] if counts["labeled"] else None
                                           for key in ("directed_segment", "base_segment", "osm_way", "direction")},
            "position_error_m_among_matched": distribution(errors),
            "mismatch_categories": dict(Counter("unresolved_segment" if row["actual_segment"] is None else
                                                 "wrong_direction_same_base" if row["same_base"] else
                                                 "different_segment_same_way" if row["same_way"] else
                                                 "different_way" for row in mismatches)),
            "largest_error_mismatches": sorted(mismatches, key=lambda row: row["position_error_m"], reverse=True)[:10],
            "first_mismatches": mismatches[:10]}


def self_check():
    """Check evaluation denominators independently of any live engine."""
    predictions = {"ok": {"matched": True, "road_segment_id": "s_F", "osm_way_id": 1,
                          "direction": "FORWARD", "matched_latitude": 21., "matched_longitude": 105.},
                   "miss": {"matched": False}}
    labels = {key: {"true_segment_id": "s_F", "true_direction": "FORWARD",
                    "true_latitude": "21", "true_longitude": "105"} for key in predictions}
    result = score(predictions, labels, {"s_F": {"base_segment_id": "s", "osm_way_id": "1"}})
    assert result["match_rate"] == .5
    assert result["accuracy_among_matched"]["directed_segment"] == 1
    assert result["accuracy_among_all_labeled"]["directed_segment"] == .5
    assert result["position_error_m_among_matched"]["mean"] == 0
    assert percentile([0, 10], .95) == 9.5


async def evaluate(args):
    output = (ROOT / args.output).resolve()
    evidence_root = (ROOT / "runtime/migration").resolve()
    if output.parent != evidence_root or not output.name.startswith("matching-quality") or output.suffix != ".json":
        raise ValueError("Output must be runtime/migration/matching-quality*.json")
    grouped = defaultdict(list)
    for row in rows("gps/gps_observations.csv.gz"):
        grouped[row["trajectory_id"]].append(row)
    ids = sorted(grouped)
    if args.max_trajectories:
        # Evenly spread across the frozen trajectories, rather than a prefix-only sample.
        ids = sorted({ids[round(i * (len(ids) - 1) / max(1, args.max_trajectories - 1))]
                      for i in range(min(args.max_trajectories, len(ids)))})
    source_paths = ["backend/app/services/map_matching/graphhopper_adapter.py",
                    "backend/app/services/map_matching/service.py",
                    "backend/app/services/map_matching/segment_resolver.py",
                    "backend/app/services/map_matching/models.py",
                    "backend/app/services/graphhopper.py",
                    "scripts/evaluate_graphhopper_matching.py"]
    evidence = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "engine": "GraphHopper 11.0",
                "method": "Complete GPS trajectories; native service + PostGIS; evaluation truth joined after all predictions",
                "trajectory_ids": ids, "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths},
                "requests": [], "predictions": {}, "complete": False}
    resolver = RouteConstrainedSegmentResolver(args.database_url)
    raw_latency = []

    async def started(request):
        request.extensions["evaluation_start"] = time.perf_counter()

    async def completed(response):
        await response.aread()
        raw_latency.append((time.perf_counter() - response.request.extensions["evaluation_start"]) * 1000)

    try:
        async with httpx.AsyncClient(timeout=args.timeout, event_hooks={"request": [started], "response": [completed]}) as client:
            info = await client.get(args.base_url.rstrip("/") + "/info")
            info.raise_for_status()
            evidence["engine_info"] = info.json()
            raw_latency.clear()
            service = MapMatchingService(GraphHopperMapMatchingAdapter(base_url=args.base_url, client=client), resolver)
            for index, trajectory_id in enumerate(ids):
                observations = sorted(grouped[trajectory_id], key=lambda row: row["timestamp"])
                request = MapMatchRequest(trajectory_id=trajectory_id, trip_id=observations[0]["trip_id"],
                                          observations=[GPSObservation(**row) for row in observations])
                started_at = time.perf_counter()
                raw_before = len(raw_latency)
                record = {"trajectory_id": trajectory_id, "observation_count": len(observations)}
                try:
                    result = await service.match_trajectory(request)
                    record.update(status="SUCCESS", profile=result.profile, matched=result.matched_count)
                    evidence["predictions"].update({obs.observation_id: obs.model_dump(mode="json") for obs in result.observations})
                except MapMatchingNoMatchError as exc:
                    record.update(status="NO_MATCH", error=str(exc), matched=0)
                    evidence["predictions"].update({obs["observation_id"]: {"matched": False} for obs in observations})
                record["service_latency_ms"] = (time.perf_counter() - started_at) * 1000
                record["http_latency_ms"] = raw_latency[-1] if len(raw_latency) > raw_before else None
                evidence["requests"].append(record)
                print(f'{index + 1}/{len(ids)} {trajectory_id}: {record["status"]} {record["matched"]}/{len(observations)}, {record["service_latency_ms"]:.0f} ms', flush=True)
        # Evaluation-only data is loaded after inference has finished.
        labels = {row["observation_id"]: row for row in rows("labels/map_matching_labels.csv.gz")}
        selected = {row["observation_id"] for row in rows("training/map_matching_candidates.csv.gz")}
        segments = {row["segment_id"]: {key: row[key] for key in ("base_segment_id", "osm_way_id")}
                    for row in rows("map/processed/road_segments.csv.gz")}
        evidence["all_observations"] = score(evidence["predictions"], labels, segments)
        evidence["selected_observations"] = score({k: v for k, v in evidence["predictions"].items() if k in selected}, labels, segments)
        evidence["selected_population_size"] = len(selected)
        evidence["request_statuses"] = dict(Counter(row["status"] for row in evidence["requests"]))
        evidence["latency_ms"] = {}
        for bucket, low, high in [("all", 0, math.inf), ("2_to_250", 2, 250), ("251_to_500", 251, 500), ("501_plus", 501, math.inf)]:
            records = [row for row in evidence["requests"] if low <= row["observation_count"] <= high]
            evidence["latency_ms"][bucket] = {field: distribution([row[field] for row in records if row[field] is not None])
                                               for field in ("http_latency_ms", "service_latency_ms")}
        evidence["source_unchanged_during_run"] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == sha
                                                       for p, sha in evidence["source_sha256"].items())
        evidence["complete"] = True
    except Exception as exc:
        evidence["fatal_error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        resolver.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")
        print(f"Evidence: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8989")
    parser.add_argument("--database-url", default="postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation")
    parser.add_argument("--max-trajectories", type=int, default=0, help="0: all; otherwise evenly spread deterministic sample")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", default="runtime/migration/matching-quality.json")
    parser.add_argument("--self-check", action="store_true", help="Check metric arithmetic without contacting services")
    args = parser.parse_args()
    if args.max_trajectories < 0:
        parser.error("--max-trajectories must be nonnegative")
    self_check()
    if args.self_check:
        print("Evaluation arithmetic checks PASS")
    else:
        asyncio.run(evaluate(args))
