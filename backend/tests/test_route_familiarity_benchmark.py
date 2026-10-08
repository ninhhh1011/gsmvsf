import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.benchmark_route_familiarity import (
    BoundedHistoryRepository,
    benchmark_database_rows,
    benchmark_cases,
    database_lifecycle_report,
    host_accessible_database_url,
    raise_for_cleanup_failure,
    _postgres_measure,
)
from backend.app.services.route_familiarity.models import RouteSignature


def test_benchmark_covers_required_dataset_sizes_and_candidate_fanout():
    assert [(case.history_size, case.candidate_count) for case in benchmark_cases()] == [
        (150, 30), (10_000, 30), (100_000, 30)
    ]


def test_personal_explain_query_uses_only_route_table_columns():
    from backend.app.services.route_familiarity.repository import PERSONAL_ROUTES_QUERY
    from scripts.benchmark_route_familiarity import PERSONAL_EXPLAIN_QUERY

    assert "active_rank" not in PERSONAL_ROUTES_QUERY
    assert "driver_rank" not in PERSONAL_ROUTES_QUERY
    assert PERSONAL_EXPLAIN_QUERY == f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {PERSONAL_ROUTES_QUERY}"


def test_community_explain_wraps_the_repository_query_exactly():
    from backend.app.services.route_familiarity.repository import COMMUNITY_ROUTES_QUERY
    from scripts.benchmark_route_familiarity import COMMUNITY_EXPLAIN_QUERY

    assert COMMUNITY_EXPLAIN_QUERY == f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {COMMUNITY_ROUTES_QUERY}"


def test_union_cell_community_cap_is_global_and_explanation_only():
    spec = Path("docs/superpowers/specs/2026-10-07-route-familiarity-v2-design.md").read_text(
        encoding="utf-8").lower()
    assert "global across the union of candidate cells" in spec
    assert "may depend on other candidates in the batch" in spec
    assert "explanation-only" in spec


def test_benchmark_route_signature_has_nine_cells_and_about_304_meters():
    from scripts.benchmark_route_familiarity import benchmark_route_signature

    signature = benchmark_route_signature()
    assert len(signature.cells) == 9
    assert signature.distance_m == pytest.approx(304, abs=1)


def test_bounded_history_repository_honors_driver_time_window_and_cells():
    base = datetime(2026, 10, 8, tzinfo=UTC)
    signature = RouteSignature(("cell",), (1.0,), 1.0, 11)
    repository = BoundedHistoryRepository(150, signature, as_of=base)
    request_time = base - timedelta(minutes=10)
    window = timedelta(minutes=5)

    personal = asyncio.run(repository.personal_routes("benchmark-driver", request_time, window))
    assert personal
    assert all(row["driver_id"] == "benchmark-driver" for row in personal)
    assert all(request_time - window <= row["completed_at"] <= request_time for row in personal)

    community = asyncio.run(repository.community_routes(
        ["cell"], "benchmark-driver", base, window))
    assert community
    assert all(row["driver_id"] != "benchmark-driver" for row in community)
    assert all(base - window <= row["completed_at"] <= base for row in community)
    assert asyncio.run(repository.community_routes(
        ["cell"], "benchmark-driver", base - timedelta(seconds=1), window)) == []
    assert asyncio.run(repository.community_routes(
        ["unmatched"], "benchmark-driver", request_time, window)) == []


def test_benchmark_default_maps_compose_database_name_to_localhost():
    assert host_accessible_database_url(
        "postgresql+asyncpg://postgres:postgres@ev_db:5432/ev_recommendation"
    ) == "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ev_recommendation"


def test_benchmark_replaces_only_database_host_and_preserves_credentials_and_query():
    assert host_accessible_database_url(
        "postgresql://ev_db_user:ev_db_password@ev_db:5432/ev_db?application_name=ev_db"
    ) == "postgresql://ev_db_user:ev_db_password@127.0.0.1:5432/ev_db?application_name=ev_db"


def test_in_memory_community_fixture_models_101_drivers_and_sentinel_routes():
    repository = BoundedHistoryRepository(10_000, RouteSignature(("cell",), (1.0,), 1.0, 11))

    rows = asyncio.run(repository.community_routes(
        list(repository.signature.cells), "benchmark-driver", repository.as_of, timedelta(days=7)))
    per_driver = {}
    for row in rows:
        per_driver[row["driver_id"]] = per_driver.get(row["driver_id"], 0) + 1

    assert len(rows) == 606
    assert all(row["active_rank"] <= 101 and row["driver_rank"] <= 6 for row in rows)
    assert sum(row["driver_rank"] <= 5 and row["active_rank"] <= 100 for row in rows) == 500
    assert len(per_driver) == 101
    assert set(per_driver.values()) == {6}
    assert max(per_driver.values()) == 6
    assert any(row["active_rank"] == 101 for row in rows)
    assert rows == sorted(rows, key=lambda row: (
        -row["completed_at"].timestamp(),
        -int(row["trip_id"].rsplit("-", 1)[1]), row["driver_id"]))


def test_benchmark_active_driver_sentinel_marks_history_truncated():
    repository = BoundedHistoryRepository(10_000, RouteSignature(("cell",), (1.0,), 1.0, 11))
    from backend.app.services.route_familiarity.service import RouteFamiliarityService

    repository.community = [row for row in repository.community
                            if int(row["trip_id"].rsplit("-", 1)[1]) // 101 == 0]
    assert len(repository.community) == 101
    assessment = asyncio.run(RouteFamiliarityService(repository).assess_many(
        "benchmark-driver", {"candidate": repository.signature}, repository.as_of))
    assert assessment["candidate"].history_truncated


def test_database_lifecycle_report_keeps_created_state_after_drop():
    report = database_lifecycle_report("route_familiarity_bench_test", True, True, [])

    assert report == {
        "disposable_database_name": "route_familiarity_bench_test",
        "disposable_database_created": True,
        "disposable_database_dropped": True,
        "cleanup_succeeded": True,
        "cleanup_errors": [],
    }


def test_database_lifecycle_report_names_database_when_cleanup_fails():
    report = database_lifecycle_report(
        "route_familiarity_bench_test", True, False, ["PostgresError"]
    )

    assert report["disposable_database_name"] == "route_familiarity_bench_test"
    assert report["disposable_database_created"] is True
    assert report["cleanup_succeeded"] is False
    assert report["cleanup_errors"] == ["PostgresError"]


def test_cleanup_failure_is_actionable_cli_error():
    report = {"postgresql": database_lifecycle_report(
        "route_familiarity_bench_test", True, False, ["PostgresError"]
    )}

    try:
        raise_for_cleanup_failure(report)
    except SystemExit as error:
        assert "route_familiarity_bench_test" in str(error)
        assert "manually" in str(error)
    else:
        raise AssertionError("cleanup failure must return a nonzero CLI status")


def test_in_memory_community_fixture_preserves_sparse_history_size():
    repository = BoundedHistoryRepository(150, RouteSignature(("cell",), (1.0,), 1.0, 11))

    rows = asyncio.run(repository.community_routes(
        list(repository.signature.cells), "benchmark-driver", repository.as_of, timedelta(days=7)))
    personal = asyncio.run(repository.personal_routes("benchmark-driver", repository.as_of, timedelta(days=7)))
    per_driver = {}
    for row in rows:
        per_driver[row["driver_id"]] = per_driver.get(row["driver_id"], 0) + 1

    assert len(rows) == 99
    assert len(personal) == 51
    assert len(per_driver) == 99
    assert set(per_driver.values()) == {1}


def test_postgres_fixture_has_exact_personal_and_community_distribution():
    signature = RouteSignature(("cell",), (1.0,), 1.0, 11)
    for size in (150, 10_000, 100_000):
        rows = benchmark_database_rows(size, signature, datetime.now(UTC))
        personal = [row for row in rows if row[0] == "phase4-benchmark-personal"]
        community = [row for row in rows if row[0] != "phase4-benchmark-personal"]
        per_driver = {}
        for row in community:
            per_driver[row[0]] = per_driver.get(row[0], 0) + 1

        assert len(personal) == 51
        assert len(community) == size - 51
        assert len(per_driver) == (99 if size == 150 else 101)
        assert min(per_driver.values()) >= 1
        if size == 150:
            assert set(per_driver.values()) == {1}
        else:
            assert min(per_driver.values()) >= 5


def test_personal_sentinel_is_exposed_as_truncated_but_not_scored():
    repository = BoundedHistoryRepository(150, RouteSignature(("cell",), (1.0,), 1.0, 11))
    from backend.app.services.route_familiarity.service import RouteFamiliarityService

    result = asyncio.run(RouteFamiliarityService(repository).assess_many(
        "benchmark-driver", {"candidate": repository.signature}, repository.as_of))
    assert len(asyncio.run(repository.personal_routes(
        "benchmark-driver", repository.as_of, timedelta(days=7)))) == 51
    assessment = result["candidate"]
    assert assessment.personal_history_trip_count == 50
    assert assessment.history_truncated


@pytest.mark.asyncio
async def test_measurement_failure_after_create_cleans_database_and_reraises(monkeypatch):
    import asyncpg

    commands = []

    class FakeConnection:
        async def execute(self, sql, *args):
            if sql.startswith("TRUNCATE"):
                raise RuntimeError("measurement query failed")

        async def close(self):
            pass

    class FakeAdmin:
        async def execute(self, sql):
            commands.append(sql)

        async def close(self):
            pass

    admin = FakeAdmin()

    async def connect(dsn, timeout):
        return admin if dsn.endswith("/postgres") else FakeConnection()

    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(RuntimeError, match="measurement query failed") as error:
        await _postgres_measure("postgresql://postgres:postgres@127.0.0.1:5432/ev", RouteSignature(
            ("8b415d8c9a00fff",), (1.0,), 1.0, 11))
    assert str(error.value) == "measurement query failed"
    assert error.value.__cause__ is None
    assert any(command.startswith('DROP DATABASE IF EXISTS "route_familiarity_bench_')
               for command in commands)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_at", ["connect", "schema", "measurement"])
@pytest.mark.parametrize("drop_fails", [False, True])
async def test_cancellation_after_create_cleans_database_and_propagates(
        monkeypatch, cancel_at, drop_fails):
    import asyncpg

    commands = []
    cancellation_point = asyncio.Event()
    admin = AsyncMock()
    conn = AsyncMock()

    async def admin_execute(sql):
        commands.append(sql)
        if drop_fails and sql.startswith("DROP DATABASE"):
            raise OSError("drop failed")

    admin.execute.side_effect = admin_execute

    async def wait_for_cancellation():
        cancellation_point.set()
        await asyncio.Future()

    async def execute(sql, *args):
        if (cancel_at == "schema" and "CREATE TABLE" in sql or
                cancel_at == "measurement" and sql.startswith("TRUNCATE")):
            await wait_for_cancellation()

    async def connect(dsn, timeout):
        if dsn.endswith("/postgres"):
            return admin
        if cancel_at == "connect":
            await wait_for_cancellation()
        return conn

    conn.execute.side_effect = execute
    monkeypatch.setattr(asyncpg, "connect", connect)
    task = asyncio.create_task(_postgres_measure(
        "postgresql://postgres:postgres@127.0.0.1:5432/ev",
        RouteSignature(("8b415d8c9a00fff",), (1.0,), 1.0, 11)))
    await asyncio.wait_for(cancellation_point.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as error:
        await task

    assert commands[0].startswith('CREATE DATABASE "route_familiarity_bench_')
    assert commands[1:] == [commands[0].replace("CREATE DATABASE", "DROP DATABASE IF EXISTS")]
    admin.close.assert_awaited_once()
    assert conn.close.await_count == (0 if cancel_at == "connect" else 1)
    if drop_fails:
        assert commands[0].split('"')[1] in error.value.__notes__[0]
        assert "OSError" in error.value.__notes__[0]


@pytest.mark.asyncio
async def test_unavailable_disposable_connection_is_not_measured_and_is_cleaned(monkeypatch):
    import asyncpg

    commands = []
    admin = AsyncMock()
    admin.execute.side_effect = lambda sql: commands.append(sql)
    admin.close.return_value = None
    connect_count = 0

    async def connect(dsn, timeout):
        nonlocal connect_count
        connect_count += 1
        if connect_count == 1:
            return admin
        raise ConnectionError("disposable database unavailable")

    monkeypatch.setattr(asyncpg, "connect", connect)
    report = await _postgres_measure("postgresql://postgres:postgres@127.0.0.1:5432/ev", RouteSignature(
        ("8b415d8c9a00fff",), (1.0,), 1.0, 11))
    assert report["status"] == "not_measured"
    assert report["disposable_database_dropped"]


@pytest.mark.asyncio
async def test_failed_cleanup_names_database_and_chains_measurement_error(monkeypatch):
    import asyncpg

    class FakeConnection:
        async def execute(self, sql, *args):
            if sql.startswith("TRUNCATE"):
                raise RuntimeError("measurement query failed")

        async def close(self):
            pass

    class FakeAdmin:
        async def execute(self, sql):
            if sql.startswith("DROP DATABASE"):
                raise OSError("drop failed")

        async def close(self):
            pass

    admin = FakeAdmin()

    async def connect(dsn, timeout):
        return admin if dsn.endswith("/postgres") else FakeConnection()

    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(RuntimeError, match=r"route_familiarity_bench_.*cleanup_errors=\['OSError'\]") as error:
        await _postgres_measure("postgresql://postgres:postgres@127.0.0.1:5432/ev", RouteSignature(
            ("8b415d8c9a00fff",), (1.0,), 1.0, 11))
    assert isinstance(error.value.__cause__, RuntimeError)
    assert "measurement query failed" in str(error.value.__cause__)


@pytest.mark.asyncio
async def test_failed_setup_cleanup_names_database_and_chains_setup_error(monkeypatch):
    import asyncpg

    class FakeConnection:
        async def execute(self, sql, *args):
            if "CREATE TABLE" in sql:
                raise RuntimeError("schema install failed")

        async def close(self):
            pass

    class FakeAdmin:
        async def execute(self, sql):
            if sql.startswith("DROP DATABASE"):
                raise OSError("drop failed")

        async def close(self):
            pass

    admin = FakeAdmin()

    async def connect(dsn, timeout):
        return admin if dsn.endswith("/postgres") else FakeConnection()

    monkeypatch.setattr(asyncpg, "connect", connect)
    with pytest.raises(RuntimeError, match=r"route_familiarity_bench_.*cleanup_errors=\['OSError'\]") as error:
        await _postgres_measure("postgresql://postgres:postgres@127.0.0.1:5432/ev", RouteSignature(
            ("8b415d8c9a00fff",), (1.0,), 1.0, 11))
    assert isinstance(error.value.__cause__, RuntimeError)
    assert "schema install failed" in str(error.value.__cause__)


def test_benchmark_exact_community_cap_does_not_mark_history_truncated():
    repository = BoundedHistoryRepository(
        551, RouteSignature(("cell",), (1.0,), 1.0, 11), community_driver_count=100)
    rows = asyncio.run(repository.community_routes(
        list(repository.signature.cells), "benchmark-driver", repository.as_of, timedelta(days=7)))
    assert len(rows) == 500
    assert not any(row["driver_rank"] > 5 or row["active_rank"] > 100 for row in rows)
