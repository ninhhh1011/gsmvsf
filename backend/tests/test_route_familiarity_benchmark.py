import asyncio
from datetime import UTC, datetime

from scripts.benchmark_route_familiarity import (
    BoundedHistoryRepository,
    benchmark_database_rows,
    benchmark_cases,
    host_accessible_database_url,
)
from backend.app.services.route_familiarity.models import RouteSignature


def test_benchmark_covers_required_dataset_sizes_and_candidate_fanout():
    assert [(case.history_size, case.candidate_count) for case in benchmark_cases()] == [
        (150, 30), (10_000, 30), (100_000, 30)
    ]


def test_benchmark_default_maps_compose_database_name_to_localhost():
    assert host_accessible_database_url(
        "postgresql+asyncpg://postgres:postgres@ev_db:5432/ev_recommendation"
    ) == "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ev_recommendation"


def test_in_memory_community_fixture_models_five_routes_for_each_of_100_drivers():
    repository = BoundedHistoryRepository(10_000, RouteSignature(("cell",), (1.0,), 1.0, 11))

    rows = asyncio.run(repository.community_routes())
    per_driver = {}
    for row in rows:
        per_driver[row["driver_id"]] = per_driver.get(row["driver_id"], 0) + 1

    assert len(rows) == 500
    assert len(per_driver) == 100
    assert set(per_driver.values()) == {5}


def test_in_memory_community_fixture_preserves_sparse_history_size():
    repository = BoundedHistoryRepository(150, RouteSignature(("cell",), (1.0,), 1.0, 11))

    rows = asyncio.run(repository.community_routes())
    personal = asyncio.run(repository.personal_routes())
    per_driver = {}
    for row in rows:
        per_driver[row["driver_id"]] = per_driver.get(row["driver_id"], 0) + 1

    assert len(rows) == 100
    assert len(personal) == 50
    assert len(per_driver) == 100
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

        assert len(personal) == 50
        assert len(community) == size - 50
        assert len(per_driver) == 100
        assert min(per_driver.values()) >= 1
        if size == 150:
            assert set(per_driver.values()) == {1}
        else:
            assert min(per_driver.values()) >= 5
