import asyncio

from scripts.benchmark_route_familiarity import (
    BoundedHistoryRepository,
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
    per_driver = {}
    for row in rows:
        per_driver[row["driver_id"]] = per_driver.get(row["driver_id"], 0) + 1

    assert len(rows) == 150
    assert len(per_driver) == 30
    assert max(per_driver.values()) == 5
