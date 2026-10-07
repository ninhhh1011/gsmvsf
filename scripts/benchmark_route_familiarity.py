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
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from backend.app.config import settings
from backend.app.services.route_familiarity.constants import H3_ROUTE_RESOLUTION
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.repository import (
    COMMUNITY_ROUTES_QUERY,
    PERSONAL_ROUTES_QUERY,
    RouteHistoryRepository,
)
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.signature import create_route_signature
from backend.app.services.route_familiarity.similarity import weighted_ordered_overlap

HISTORY_SIZES = (150, 10_000, 100_000)
CANDIDATE_COUNT = 30
SAMPLES = 5
WARMUPS = 1
PERSONAL_EXPLAIN_QUERY = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {PERSONAL_ROUTES_QUERY}"
COMMUNITY_EXPLAIN_QUERY = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {COMMUNITY_ROUTES_QUERY}"


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
    authority_start = parsed.netloc.rfind("@") + 1
    host_start = authority_start
    host_end = host_start + len(parsed.hostname)
    netloc = parsed.netloc[:host_start] + "127.0.0.1" + parsed.netloc[host_end:]
    return urlunsplit(parsed._replace(netloc=netloc))


def database_lifecycle_report(database_name, created, dropped, cleanup_errors):
    return {
        "disposable_database_name": database_name,
        "disposable_database_created": created,
        "disposable_database_dropped": dropped,
        "cleanup_succeeded": not cleanup_errors and (not created or dropped),
        "cleanup_errors": cleanup_errors,
    }


def raise_for_cleanup_failure(report):
    postgres = report["postgresql"]
    if postgres.get("cleanup_succeeded") is False:
        database_name = postgres["disposable_database_name"]
        raise SystemExit(
            f"route familiarity benchmark cleanup failed for {database_name}; "
            "inspect PostgreSQL and remove the disposable database manually"
        )


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


def benchmark_route_points():
    return tuple((21.0285 + index * 0.00265 / 4,
                  105.8542 + (-1) ** index * 0.00009) for index in range(5))


def benchmark_route_signature():
    return create_route_signature([_polyline(benchmark_route_points())])


class BoundedHistoryRepository:
    """Production harness; sentinel rows appear only when history exceeds a cap."""
    def __init__(self, history_size, signature, community_driver_count=101, as_of=None):
        self.history_size = history_size
        self.signature = signature
        self.as_of = as_of or datetime.now(UTC)
        self.personal = [{
            "driver_id": "benchmark-driver", "trip_id": f"personal-trip-{index:03d}",
            "completed_at": self.as_of - timedelta(minutes=index),
            "cells": signature.cells, "cell_distances_m": signature.cell_distances_m,
            "distance_m": signature.distance_m, "resolution": signature.resolution,
        } for index in range(min(history_size, 51))]
        community_count = max(history_size - 51, 0)
        self.community = [{
             "driver_id": f"synthetic-driver-{index % community_driver_count:03d}",
             "trip_id": f"synthetic-trip-{index:06d}",
             "completed_at": self.as_of - timedelta(minutes=index // community_driver_count),
             "cells": signature.cells, "cell_distances_m": signature.cell_distances_m,
             "distance_m": signature.distance_m, "resolution": signature.resolution,
        } for index in range(min(community_count, community_driver_count * 6))]

    async def personal_routes(self, driver_id, as_of, lookback):
        lower_bound = as_of - lookback
        rows = [row for row in self.personal if row["driver_id"] == driver_id and
                lower_bound <= row["completed_at"] <= as_of]
        rows.sort(key=lambda row: (row["completed_at"], row["trip_id"]), reverse=True)
        return rows[:51]

    async def community_routes(self, cells, exclude_driver_id, as_of, lookback):
        wanted_cells = set(cells)
        if not wanted_cells:
            return []
        lower_bound = as_of - lookback
        rows = [row for row in self.community if row["driver_id"] != exclude_driver_id and
                lower_bound <= row["completed_at"] <= as_of and wanted_cells.intersection(row["cells"])]
        latest = {}
        for row in rows:
            latest[row["driver_id"]] = max(latest.get(row["driver_id"], row["completed_at"]), row["completed_at"])
        drivers = sorted(latest, key=lambda driver: (-latest[driver].timestamp(), driver))[:101]
        bounded = []
        for active_rank, driver in enumerate(drivers, 1):
            history = [row for row in rows if row["driver_id"] == driver]
            history.sort(key=lambda row: (row["completed_at"], row["trip_id"]), reverse=True)
            bounded.extend({**row, "active_rank": active_rank, "driver_rank": driver_rank}
                           for driver_rank, row in enumerate(history[:6], 1))
        bounded.sort(key=lambda row: (
            -row["completed_at"].timestamp(),
            -int(row["trip_id"].rsplit("-", 1)[1]), row["driver_id"]))
        return bounded[:606]


def benchmark_database_rows(size, signature, as_of):
    """Build 51 personal rows and distribute community history across up to 101 drivers."""
    rows = []
    for index in range(size):
        personal = index < 51
        community_index = index - 51
        driver_id = ("phase4-benchmark-personal" if personal else
                     f"phase4-benchmark-community-{community_index % 101:03d}")
        age_minutes = 0 if personal else community_index // 101
        rows.append((driver_id, f"phase4-benchmark-trip-{index:06d}",
                     as_of - timedelta(minutes=age_minutes), signature.distance_m,
                     signature.resolution, list(signature.cells), list(signature.cell_distances_m)))
    return rows


async def _measure_evaluation(case, signature):
    as_of = datetime.now(UTC)
    service = RouteFamiliarityService(
        BoundedHistoryRepository(case.history_size, signature, as_of=as_of))
    candidates = {str(i): signature for i in range(case.candidate_count)}
    async def evaluate():
        await service.assess_many("benchmark-driver", candidates, as_of)
    for _ in range(WARMUPS):
        await evaluate()
    results = []
    for _ in range(SAMPLES):
        started = perf_counter()
        await evaluate()
        results.append((perf_counter() - started) * 1000)
    repository = service.repository
    personal_rows = await repository.personal_routes("benchmark-driver", as_of, service.lookback)
    community_rows = await repository.community_routes(
        sorted({cell for route in candidates.values() for cell in route.cells}),
        "benchmark-driver", as_of, service.lookback)
    return {"samples": SAMPLES, "warmups": WARMUPS,
            "p50_ms": round(statistics.median(results), 3),
            "p95_ms": round(percentile(results, 0.95), 3),
            "personal_rows_returned_per_candidate": len(personal_rows),
            "personal_rows_scored_per_candidate": min(case.history_size, 50),
            "personal_history_truncated": len(personal_rows) > 50,
            "community_rows_returned_per_candidate": len(community_rows),
            "community_rows_scored_per_candidate": min(len(community_rows), 500),
            "community_distinct_drivers_returned": len({row["driver_id"] for row in community_rows}),
            "community_history_truncated": (len(community_rows) > 500 or any(
                row["active_rank"] > 100 or row["driver_rank"] > 5 for row in community_rows))}


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
        connected = conn is not None
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
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
        if admin:
            try:
                await admin.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            admin = None
        if created and connected:
            if cleanup_errors:
                raise RuntimeError(
                    f"route familiarity benchmark failed for {database_name}; "
                    f"setup_error={type(error).__name__}: {error}; cleanup_errors={cleanup_errors}"
                ) from error
            raise
        return {"status": "not_measured", "reason": type(error).__name__,
                **database_lifecycle_report(database_name, created, dropped, cleanup_errors)}
    try:
        repository = RouteHistoryRepository(_BorrowedConnectionPool(conn))
        as_of = datetime.now(UTC)
        db_signature = signature
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
            community_scored = [row for row in community_rows
                                if row["active_rank"] <= 100 and row["driver_rank"] <= 5][:500]
            community_truncated = (len(community_rows) > 500 or any(
                row["active_rank"] > 100 or row["driver_rank"] > 5 for row in community_rows))
            service = RouteFamiliarityService(repository)
            candidates = {str(i): db_signature for i in range(CANDIDATE_COUNT)}
            async def evaluate():
                await service.assess_many("phase4-benchmark-personal", candidates, as_of)
            evaluation = await _measure_async(evaluate)
            personal_plan = await conn.fetch(PERSONAL_EXPLAIN_QUERY,
                        "phase4-benchmark-personal", as_of - timedelta(days=7), as_of)
            community_plan = await conn.fetch(COMMUNITY_EXPLAIN_QUERY,
                        "phase4-benchmark-personal", as_of - timedelta(days=7), as_of, list(db_signature.cells))
            per_size.append({"history_rows": actual, "repository_query_pair": timings,
                "repository_rows_returned": {"personal": len(personal_rows),
                    "community": len(community_rows),
                    "community_distinct_drivers": len(community_per_driver),
                    "community_max_rows_per_driver": max(community_per_driver.values(), default=0)},
                "repository_rows_scored": {"personal": min(len(personal_rows), 50),
                    "community": len(community_scored)},
                "history_truncated": {"personal": len(personal_rows) > 50,
                    "community": community_truncated},
                "database_backed_full_evaluation_30_candidates": evaluation,
                "personal_explain_analyze_buffers": [r["QUERY PLAN"] for r in personal_plan],
                "community_explain_analyze_buffers": [r["QUERY PLAN"] for r in community_plan]})
        await conn.close()
        conn = None
        await admin.execute(f'DROP DATABASE "{database_name}"')
        dropped = True
        await admin.close()
        admin = None
        return {"status": "measured", "per_size": per_size,
                "application_database_written": False,
                "disposable_database_writes_committed": True,
                **database_lifecycle_report(database_name, created, dropped, [])}
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
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
        if admin:
            try:
                await admin.close()
            except Exception as cleanup_error:
                cleanup_errors.append(type(cleanup_error).__name__)
            admin = None
        if cleanup_errors:
            raise RuntimeError(
                f"route familiarity benchmark failed for {database_name}; "
                f"measurement_error={type(error).__name__}: {error}; cleanup_errors={cleanup_errors}"
            ) from error
        raise
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
    polyline = _polyline(benchmark_route_points())
    signature = create_route_signature([polyline])
    same_route = RouteSignature(signature.cells, signature.cell_distances_m,
                                 signature.distance_m, H3_ROUTE_RESOLUTION)
    report = {"resolution": H3_ROUTE_RESOLUTION,
              "benchmark_route": {"cell_count": len(signature.cells),
                                  "distance_m": round(signature.distance_m, 3)},
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
    report = asyncio.run(run(args.database_url))
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    raise_for_cleanup_failure(report)


if __name__ == "__main__":
    main()
