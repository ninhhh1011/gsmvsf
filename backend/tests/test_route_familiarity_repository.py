from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.snapshots.models import StateError


class Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return self

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_idempotent_insert_and_conflicting_retry():
    conn = AsyncMock()
    row = dict(driver_id="d", trip_id="t", completed_at=datetime.now(UTC),
               distance_m=10.0, resolution=11, cells=["abc"], cell_distances_m=[10.0])
    conn.fetchrow.side_effect = [row, None, row, None, {**row, "distance_m": 12.0}]
    repo = RouteHistoryRepository(Pool(conn))
    sig = RouteSignature(("abc",), (10.0,), 10.0, 11)
    first, created = await repo.upsert_route("d", "t", row["completed_at"], sig)
    assert created and first["distance_m"] == 10.0
    retry, created = await repo.upsert_route("d", "t", row["completed_at"], sig)
    assert not created and retry["distance_m"] == 10.0
    with pytest.raises(StateError) as err:
        await repo.upsert_route("d", "t", row["completed_at"], sig)
    assert err.value.status == 409


@pytest.mark.asyncio
async def test_history_queries_are_as_of_and_bounded():
    conn = AsyncMock()
    conn.fetch.return_value = []
    repo = RouteHistoryRepository(Pool(conn))
    as_of = datetime.now(UTC)
    await repo.personal_routes("d", as_of, timedelta(days=7))
    await repo.community_routes(["abc"], "d", as_of, timedelta(days=7))
    calls = [call.args[0] for call in conn.fetch.await_args_list]
    assert all("completed_at <=" in sql for sql in calls)
    assert "LIMIT 50" in calls[0]
    assert "LIMIT 500" in calls[1]
    assert "ORDER BY last_completed_at DESC, driver_id" in calls[1]
    assert "PARTITION BY r.driver_id ORDER BY r.completed_at DESC" in calls[1]


def test_migration_has_constraints_indexes_and_rollback():
    sql = Path("backend/app/services/route_familiarity/schema.sql").read_text().lower()
    assert "create table if not exists realtime.route_familiarity_routes" in sql
    assert "unique (driver_id, trip_id)" in sql
    assert "using gin (cells)" in sql
    assert "using btree (driver_id, completed_at desc)" in sql
    script = Path("scripts/migrate_route_familiarity.py").read_text().lower()
    assert "rollback" in script and "drop table" in script
