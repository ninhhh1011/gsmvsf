"""Async PostgreSQL persistence for completed route signatures."""
from datetime import datetime, timedelta

import asyncpg

from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.snapshots.models import StateError

_INSERT = """
INSERT INTO realtime.route_familiarity_routes
    (driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (driver_id, trip_id) DO NOTHING
RETURNING driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
"""
_SELECT_ONE = """
SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
FROM realtime.route_familiarity_routes WHERE driver_id=$1 AND trip_id=$2
"""


class RouteHistoryRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_schema(self) -> None:
        """Apply the explicit schema file; deliberately not called during app startup."""
        from pathlib import Path

        sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        async with self.pool.acquire() as conn:
            await conn.execute(sql)

    async def upsert_route(self, driver_id: str, trip_id: str, completed_at: datetime,
                           signature: RouteSignature):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(_INSERT, driver_id, trip_id, completed_at,
                                      signature.distance_m, signature.resolution,
                                      list(signature.cells), list(signature.cell_distances_m))
            if row:
                return row, True
            row = await conn.fetchrow(_SELECT_ONE, driver_id, trip_id)
        same = (row and row["completed_at"] == completed_at and
                row["distance_m"] == signature.distance_m and row["resolution"] == signature.resolution and
                tuple(row["cells"]) == signature.cells and
                tuple(row["cell_distances_m"]) == signature.cell_distances_m)
        if not same:
            raise StateError("Route ingestion conflicts with an existing trip", "ROUTE_CONFLICT", 409)
        return row, False

    async def personal_routes(self, driver_id: str, as_of: datetime, lookback: timedelta):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
                FROM realtime.route_familiarity_routes
                WHERE driver_id=$1 AND completed_at >= $2 AND completed_at <= $3
                ORDER BY completed_at DESC LIMIT 50
            """, driver_id, as_of - lookback, as_of)

    async def community_routes(self, cells: list[str], exclude_driver_id: str,
                               as_of: datetime, lookback: timedelta):
        if not cells:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                WITH active_drivers AS (
                    SELECT driver_id, max(completed_at) AS last_completed_at
                    FROM realtime.route_familiarity_routes
                    WHERE driver_id <> $1 AND completed_at >= $2 AND completed_at <= $3
                      AND cells && $4::text[]
                    GROUP BY driver_id
                    ORDER BY last_completed_at DESC, driver_id
                    LIMIT 100
                ), bounded AS (
                    SELECT r.*, row_number() OVER (PARTITION BY r.driver_id ORDER BY r.completed_at DESC) AS driver_rank
                    FROM realtime.route_familiarity_routes r
                    JOIN active_drivers d USING (driver_id)
                    WHERE r.completed_at >= $2 AND r.completed_at <= $3 AND r.cells && $4::text[]
                )
                SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m
                FROM bounded WHERE driver_rank <= 5
                ORDER BY completed_at DESC, driver_id LIMIT 500
            """, exclude_driver_id, as_of - lookback, as_of, cells)
