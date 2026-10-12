"""Async PostgreSQL persistence for completed route signatures."""
from datetime import datetime, timedelta
import json

import asyncpg

from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.snapshots.models import StateError

_INSERT = """
INSERT INTO realtime.route_familiarity_routes
    (driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
ON CONFLICT (driver_id, trip_id) DO NOTHING
RETURNING driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at
"""
_SELECT_ONE = """
SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at
FROM realtime.route_familiarity_routes WHERE driver_id=$1 AND trip_id=$2
"""
_ADD_EVIDENCE = """
UPDATE realtime.route_familiarity_routes
SET geometry = COALESCE(geometry, $3::jsonb), started_at = COALESCE(started_at, $4)
WHERE driver_id=$1 AND trip_id=$2
  AND (geometry IS NULL OR $3::jsonb IS NULL OR geometry=$3::jsonb)
  AND (started_at IS NULL OR $4::timestamptz IS NULL OR started_at=$4)
RETURNING driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at
"""
PERSONAL_ROUTES_QUERY = """
SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at
FROM realtime.route_familiarity_routes
WHERE driver_id=$1 AND completed_at >= $2 AND completed_at < $3
ORDER BY completed_at DESC, trip_id DESC LIMIT 51
"""
COMMUNITY_ROUTES_QUERY = """
WITH active_drivers AS (
    SELECT driver_id, max(completed_at) AS last_completed_at
    FROM realtime.route_familiarity_routes
    WHERE driver_id <> $1 AND completed_at >= $2 AND completed_at < $3
    GROUP BY driver_id
    ORDER BY last_completed_at DESC, driver_id
    LIMIT 101
), ranked_drivers AS (
    SELECT *, row_number() OVER (ORDER BY last_completed_at DESC, driver_id) AS active_rank
    FROM active_drivers
), bounded AS (
    SELECT r.*, d.active_rank,
           row_number() OVER (PARTITION BY r.driver_id ORDER BY r.completed_at DESC, r.trip_id DESC) AS driver_rank
    FROM realtime.route_familiarity_routes r
    JOIN ranked_drivers d USING (driver_id)
    WHERE r.completed_at >= $2 AND r.completed_at < $3
)
SELECT driver_id, trip_id, completed_at, distance_m, resolution, cells, cell_distances_m, geometry, started_at,
       active_rank, driver_rank
FROM bounded WHERE driver_rank <= 6
ORDER BY completed_at DESC, trip_id DESC, driver_id LIMIT 606
"""


class RouteHistoryRepository:
    def __init__(self, pool: asyncpg.Pool, namespace: str = 'realtime'):
        if namespace not in ('realtime', 'synthetic'):
            raise ValueError('Unsupported route history namespace')
        self.pool = pool
        self.namespace = namespace

    def _query(self, sql: str) -> str:
        return sql.replace('realtime.', f'{self.namespace}.')

    async def ensure_schema(self) -> None:
        """Apply the explicit schema file; deliberately not called during app startup."""
        from pathlib import Path

        sql = self._query(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        sql = sql.replace('SCHEMA IF NOT EXISTS realtime;', f'SCHEMA IF NOT EXISTS {self.namespace};')
        async with self.pool.acquire() as conn:
            await conn.execute(sql)

    async def upsert_route(self, driver_id: str, trip_id: str, completed_at: datetime,
                           signature: RouteSignature, started_at: datetime | None = None):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._query(_INSERT), driver_id, trip_id, completed_at,
                                      signature.distance_m, signature.resolution,
                                      list(signature.cells), list(signature.cell_distances_m),
                                      json.dumps(signature.coordinates) if signature.coordinates else None,
                                      started_at)
            if row:
                return row, True
            row = await conn.fetchrow(self._query(_SELECT_ONE), driver_id, trip_id)
        same = (row and row["completed_at"] == completed_at and
                row["distance_m"] == signature.distance_m and row["resolution"] == signature.resolution and
                tuple(row["cells"]) == signature.cells and
                tuple(row["cell_distances_m"]) == signature.cell_distances_m)
        if not same:
            raise StateError("Route ingestion conflicts with an existing trip", "ROUTE_CONFLICT", 409)
        geometry = coordinates_from_row(row)
        if (geometry and signature.coordinates and geometry != signature.coordinates or
                row.get("started_at") is not None and started_at is not None and
                row["started_at"] != started_at):
            raise StateError("Route ingestion conflicts with an existing trip", "ROUTE_CONFLICT", 409)
        if (not geometry and signature.coordinates or row.get("started_at") is None and started_at is not None):
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(self._query(_ADD_EVIDENCE), driver_id, trip_id,
                    json.dumps(signature.coordinates) if signature.coordinates else None, started_at)
            if not row:
                raise StateError("Route ingestion conflicts with an existing trip", "ROUTE_CONFLICT", 409)
        return row, False

    async def personal_routes(self, driver_id: str, as_of: datetime, lookback: timedelta):
        async with self.pool.acquire() as conn:
            return await conn.fetch(self._query(PERSONAL_ROUTES_QUERY), driver_id, as_of - lookback, as_of)

    async def community_routes(self, cells: list[str], exclude_driver_id: str,
                               as_of: datetime, lookback: timedelta):
        if not cells:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                self._query(COMMUNITY_ROUTES_QUERY), exclude_driver_id, as_of - lookback, as_of)


def coordinates_from_row(row):
    geometry = row.get("geometry")
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    return tuple(tuple(point) for point in geometry) if geometry else ()
