"""Measure route-familiarity primitives, bounded evaluation, and optional PostgreSQL lookups.

Run with ``python -B -m scripts.benchmark_route_familiarity``. Output is JSON;
the script never writes route history or modifies Dataset V1.
"""
import argparse
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import json
import statistics
import h3
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from backend.app.config import settings
from backend.app.services.route_familiarity.constants import H3_ROUTE_RESOLUTION
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.signature import create_route_signature
from backend.app.services.route_familiarity.similarity import weighted_ordered_overlap

HISTORY_SIZES = (150, 10_000, 100_000)
CANDIDATE_COUNT = 30
SAMPLES = 5
WARMUPS = 1


@dataclass(frozen=True)
class BenchmarkCase:
    history_size: int
    candidate_count: int = CANDIDATE_COUNT


def benchmark_cases():
    return tuple(BenchmarkCase(size) for size in HISTORY_SIZES)


def host_accessible_database_url(database_url):
    parsed = urlsplit(database_url)
    if parsed.hostname != "ev_db":
        return database_url
    credentials, separator, host_port = parsed.netloc.rpartition("@")
    host_port = host_port.replace(parsed.hostname, "127.0.0.1", 1)
    netloc = f"{credentials}{separator}{host_port}" if separator else host_port
    return urlunsplit(parsed._replace(netloc=netloc))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.999999)))]


def measure(operation, *, samples=SAMPLES, warmups=WARMUPS):
    for _ in range(warmups):
        operation()
    elapsed = []
    for _ in range(samples):
        started = perf_counter()
        operation()
        elapsed.append((perf_counter() - started) * 1000)
    return {"samples": samples, "warmups": warmups,
            "p50_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(percentile(elapsed, 0.95), 3)}


def _polyline(points):
    lat = lon = 0
    output = []
    for point in points:
        for axis, value in enumerate(point):
            current = round(value * 100_000)
            delta = current - (lat if axis == 0 else lon)
            if axis == 0:
                lat = current
            else:
                lon = current
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 0x20:
                output.append(chr((0x20 | (encoded & 0x1f)) + 63))
                encoded >>= 5
            output.append(chr(encoded + 63))
    return "".join(output)


class BoundedHistoryRepository:
    """Production-service harness matching the repository's documented query caps."""
    def __init__(self, history_size, signature):
        self.history_size = history_size
        self.signature = signature
        self.row = {"driver_id": "synthetic-driver", "cells": signature.cells,
                    "cell_distances_m": signature.cell_distances_m,
                    "distance_m": signature.distance_m, "resolution": signature.resolution}
        self.community = [
            {**self.row, "driver_id": f"synthetic-driver-{index % 100:03d}"}
            for index in range(min(max(history_size - 50, 0), 500))
        ]

    async def personal_routes(self, *_):
        return [self.row] * min(self.history_size, 50)

    async def community_routes(self, *_):
        return self.community


def benchmark_database_rows(size, signature, as_of):
    """Build 50 personal rows and history for exactly 100 community drivers."""
    rows = []
    for index in range(size):
        personal = index < 50
        community_index = index - 50
        driver_id = ("phase4-benchmark-personal" if personal else
                     f"phase4-benchmark-community-{community_index % 100:03d}")
        age_minutes = 0 if personal else community_index // 100
        rows.append((driver_id, f"phase4-benchmark-trip-{index:06d}",
                     as_of - timedelta(minutes=age_minutes), signature.distance_m,
                     signature.resolution, list(signature.cells), list(signature.cell_distances_m)))
    return rows


async def _measure_evaluation(case, signature):
    service = RouteFamiliarityService(BoundedHistoryRepository(case.history_size, signature))
    candidates = {str(i): signature for i in range(case.candidate_count)}
    async def evaluate():
        await service.assess_many("benchmark-driver", candidates, datetime.now(UTC))
    for _ in range(WARMUPS):
        await evaluate()
    results = []
    for _ in range(SAMPLES):
        started = perf_counter()
        await evaluate()
        results.append((perf_counter() - started) * 1000)
    repository = service.repository
    community_rows = repository.community
    return {"samples": SAMPLES, "warmups": WARMUPS,
            "p50_ms": round(statistics.median(results), 3),
            "p95_ms": round(percentile(results, 0.95), 3),
            "personal_rows_returned_per_candidate": min(case.history_size, 50),
            "community_rows_returned_per_candidate": len(community_rows),
            "community_distinct_drivers_returned": len({row["driver_id"] for row in community_rows}),
            "community_history_truncated": len(community_rows) >= 500}


async def _postgres_measure(database_url, signature):
    if not database_url:
        return {"status": "not_measured", "reason": "DATABASE_URL is empty"}
    database_name = f"route_familiarity_bench_{uuid4().hex}"
    admin = conn = None
    created = dropped = False
    try:
        import asyncpg
        parsed = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://"))
        admin_dsn = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, ""))
        admin = await asyncpg.connect(admin_dsn, timeout=3)
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        created = True
        dsn = urlunsplit((parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, ""))
        conn = await asyncpg.connect(dsn, timeout=3)
        schema = (Path(__file__).resolve().parents[1] /
                  "backend/app/services/route_familiarity/schema.sql").read_text(encoding="utf-8")
        await conn.execute(schema)
    except Exception as error:  # External database availability is optional for the local harness.
        cleanup_errors = []
        if conn:
            try:
                await conn.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            conn = None
        if created and admin:
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
                dropped = True
                created = False
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
        if admin:
            try:
                await admin.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            admin = None
        return {"status": "not_measured", "reason": type(error).__name__,
                "disposable_database_created": created, "disposable_database_dropped": dropped,
                "cleanup_succeeded": not cleanup_errors and (not created or dropped),
                "cleanup_errors": cleanup_errors}
    try:
        repository = RouteHistoryRepository(_BorrowedConnectionPool(conn))
        as_of = datetime.now(UTC)
        center = h3.cell_to_latlng(signature.cells[0])
        db_signature = create_route_signature([_polyline([
            (center[0] - 0.00001, center[1]), (center[0] + 0.00001, center[1])])])
        per_size = []
        for size in HISTORY_SIZES:
            await conn.execute("TRUNCATE realtime.route_familiarity_routes")
            await conn.executemany("""INSERT INTO realtime.route_familiarity_routes
                        (driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                        benchmark_database_rows(size, db_signature, as_of))
            actual = await conn.fetchval("SELECT count(*) FROM realtime.route_familiarity_routes")
            await conn.execute("ANALYZE realtime.route_familiarity_routes")
            async def lookup():
                await repository.personal_routes("phase4-benchmark-personal", as_of, timedelta(days=7))
                await repository.community_routes(list(db_signature.cells), "phase4-benchmark-personal",
                                                  as_of, timedelta(days=7))
            timings = await _measure_async(lookup)
            personal_rows = await repository.personal_routes(
                "phase4-benchmark-personal", as_of, timedelta(days=7))
            community_rows = await repository.community_routes(
                list(db_signature.cells), "phase4-benchmark-personal", as_of, timedelta(days=7))
            community_per_driver = Counter(row["driver_id"] for row in community_rows)
            service = RouteFamiliarityService(repository)
            candidates = {str(i): db_signature for i in range(CANDIDATE_COUNT)}
            async def evaluate():
                await service.assess_many("phase4-benchmark-personal", candidates, as_of)
            evaluation = await _measure_async(evaluate)
            personal_plan = await conn.fetch("""EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                        SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
                        FROM realtime.route_familiarity_routes
                        WHERE driver_id=$1 AND completed_at >= $2 AND completed_at <= $3
                        ORDER BY completed_at DESC LIMIT 50""",
                        "phase4-benchmark-personal", as_of - timedelta(days=7), as_of)
            community_plan = await conn.fetch("""EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
                        WITH active_drivers AS (
                            SELECT driver_id, max(completed_at) AS last_completed_at
                            FROM realtime.route_familiarity_routes
                            WHERE driver_id <> $1 AND completed_at >= $2 AND completed_at <= $3
                              AND cells && $4::text[]
                            GROUP BY driver_id ORDER BY last_completed_at DESC, driver_id LIMIT 100
                        ), bounded AS (
                            SELECT r.*, row_number() OVER (PARTITION BY r.driver_id ORDER BY r.completed_at DESC) AS driver_rank
                            FROM realtime.route_familiarity_routes r JOIN active_drivers d USING (driver_id)
                            WHERE r.completed_at >= $2 AND r.completed_at <= $3 AND r.cells && $4::text[]
                        )
                        SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
                        FROM bounded WHERE driver_rank <= 5 ORDER BY completed_at DESC, driver_id LIMIT 500""",
                        "phase4-benchmark-personal", as_of - timedelta(days=7), as_of, list(db_signature.cells))
            per_size.append({"history_rows": actual, "repository_query_pair": timings,
                "repository_rows_returned": {"personal": len(personal_rows),
                    "community": len(community_rows),
                    "community_distinct_drivers": len(community_per_driver),
                    "community_max_rows_per_driver": max(community_per_driver.values(), default=0)},
                "database_backed_full_evaluation_30_candidates": evaluation,
                "personal_explain_analyze_buffers": [r["QUERY PLAN"] for r in personal_plan],
                "community_explain_analyze_buffers": [r["QUERY PLAN"] for r in community_plan]})
        await conn.close()
        conn = None
        await admin.execute(f'DROP DATABASE "{database_name}"')
        dropped = True
        created = False
        return {"status": "measured", "per_size": per_size,
                "application_database_written": False,
                "disposable_database_writes_committed": True,
                "disposable_database_dropped": dropped}
    except Exception as error:
        cleanup_errors = []
        if conn:
            try:
                await conn.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            conn = None
        if created and admin:
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
                dropped = True
                created = False
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
        if admin:
            try:
                await admin.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            admin = None
        return {"status": "not_measured", "reason": type(error).__name__,
                "disposable_database_created": created, "disposable_database_dropped": dropped,
                "cleanup_succeeded": not cleanup_errors and (not created or dropped),
                "cleanup_errors": cleanup_errors}
    finally:
        if conn:
            await conn.close()
        if admin:
            await admin.close()


class _BorrowedConnectionPool:
    """Adapt one transaction-scoped asyncpg connection to the repository acquire protocol."""
    def __init__(self, connection):
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


async def _measure_async(operation):
    for _ in range(WARMUPS):
        await operation()
    elapsed = []
    for _ in range(SAMPLES):
        started = perf_counter()
        await operation()
        elapsed.append((perf_counter() - started) * 1000)
    return {"samples": SAMPLES, "warmups": WARMUPS,
            "p50_ms": round(statistics.median(elapsed), 3),
            "p95_ms": round(percentile(elapsed, 0.95), 3)}


async def run(database_url):
    polyline = _polyline([(21.0, 105.0), (21.001, 105.001), (21.002, 105.0)])
    signature = create_route_signature([polyline])
    same_route = RouteSignature(signature.cells, signature.cell_distances_m,
                                 signature.distance_m, H3_ROUTE_RESOLUTION)
    report = {"resolution": H3_ROUTE_RESOLUTION,
              "candidate_fanout": CANDIDATE_COUNT,
              "dataset_sizes": list(HISTORY_SIZES),
              "route_signature": measure(lambda: create_route_signature([polyline])),
              "similarity": measure(lambda: weighted_ordered_overlap(signature, same_route)),
              "cases": []}
    for case in benchmark_cases():
        report["cases"].append({"history_size": case.history_size,
            "candidate_count": case.candidate_count,
            "bounded_full_evaluation": await _measure_evaluation(case, signature)})
    report["postgresql"] = await _postgres_measure(database_url, signature)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=host_accessible_database_url(settings.database_url))
    parser.add_argument("--output", type=Path, help="also write the full JSON report to this path")
    args = parser.parse_args()
    output = json.dumps(asyncio.run(run(args.database_url)), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
