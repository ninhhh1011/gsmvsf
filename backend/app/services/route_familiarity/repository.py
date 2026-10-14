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
SELECT driver_id, trip_id, completed_at, geometry, started_at
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
SELECT driver_id, trip_id, completed_at, geometry, started_at,
       active_rank, driver_rank
FROM bounded WHERE driver_rank <= 6
ORDER BY completed_at DESC, trip_id DESC, driver_id LIMIT 606
"""

DEPARTURE_CELLS_QUERY = """
WITH cells AS (
    SELECT driver_id, trip_id, c.key AS cell,
           EXISTS (SELECT 1 FROM jsonb_array_elements_text(c.value->'reached') AS reached_at
                   WHERE reached_at::float8 >= extract(epoch FROM $1::timestamptz)
                     AND reached_at::float8 <= extract(epoch FROM $2::timestamptz)) AS reached,
           EXISTS (SELECT 1 FROM jsonb_array_elements_text(coalesce(c.value->'uncertain', '[]'::jsonb)) AS uncertain_at
                   WHERE uncertain_at::float8 >= extract(epoch FROM $1::timestamptz)
                     AND uncertain_at::float8 <= extract(epoch FROM $2::timestamptz)) AS uncertain,
           (SELECT count(*) FROM jsonb_array_elements_text(c.value->'departures') AS departure_at
            WHERE departure_at::float8 >= extract(epoch FROM $1::timestamptz)
              AND departure_at::float8 <= extract(epoch FROM $2::timestamptz)) AS events
    FROM realtime.route_deviation_trips t,
         LATERAL jsonb_each(t.analysis->'cells'->$3::text) c
    WHERE completed_at >= $1 AND completed_at <= $2
), counts AS (
    SELECT cell, count(DISTINCT (driver_id, trip_id)) AS eligible_trip_count,
           count(DISTINCT (driver_id, trip_id)) FILTER (WHERE events > 0) AS departing_trip_count,
           sum(events) AS departure_event_count,
           count(DISTINCT driver_id) AS reached_drivers,
           count(DISTINCT driver_id) FILTER (WHERE events > 0) AS departing_drivers
    FROM cells WHERE reached AND (events > 0 OR NOT uncertain) GROUP BY cell
)
SELECT cell, eligible_trip_count, departing_trip_count, departure_event_count
FROM counts WHERE reached_drivers >= $4 AND (departing_drivers = 0 OR departing_drivers >= $4)
ORDER BY cell
"""

DEPARTURE_METADATA_QUERY = """
SELECT (SELECT count(*) FROM realtime.route_deviation_trips WHERE completed_at >= $1 AND completed_at <= $2)
           AS paired_trip_count,
       (SELECT count(*) FROM realtime.route_familiarity_routes h
        WHERE completed_at >= $1 AND completed_at <= $2
          AND NOT EXISTS (SELECT 1 FROM realtime.route_deviation_trips d
                          WHERE d.driver_id=h.driver_id AND d.trip_id=h.trip_id)) AS excluded_unpaired_trip_count,
       count(*) FILTER (WHERE NOT (analysis->>'comparable')::boolean) AS unknown_trip_count,
       coalesce(sum((analysis->>'uncertain_intervals')::int), 0) AS uncertain_intervals
FROM realtime.route_deviation_trips WHERE completed_at >= $1 AND completed_at <= $2
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

    async def ingest_guided_trip(self, evidence: dict, analysis: dict) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._query("""
                INSERT INTO realtime.route_deviation_trips
                    (driver_id, trip_id, started_at, completed_at, evidence, analysis)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
                ON CONFLICT (driver_id, trip_id) DO NOTHING RETURNING trip_id
                """), evidence['driver_id'], evidence['trip_id'],
                datetime.fromisoformat(evidence['started_at']), datetime.fromisoformat(evidence['completed_at']),
                json.dumps(evidence), json.dumps(analysis))
            if row:
                return True
            row = await conn.fetchrow(self._query("""
                SELECT evidence FROM realtime.route_deviation_trips WHERE driver_id=$1 AND trip_id=$2
                """), evidence['driver_id'], evidence['trip_id'])
        existing = row['evidence'] if row else None
        if isinstance(existing, str):
            existing = json.loads(existing)
        if existing != evidence:
            raise StateError('Guided trip conflicts with existing evidence', 'ROUTE_CONFLICT', 409)
        # Raw evidence is immutable; retries refresh derived analysis after detector fixes.
        async with self.pool.acquire() as conn:
            await conn.execute(self._query("""
                UPDATE realtime.route_deviation_trips SET analysis=$4::jsonb
                WHERE driver_id=$1 AND trip_id=$2 AND evidence=$3::jsonb
                """), evidence['driver_id'], evidence['trip_id'], json.dumps(evidence), json.dumps(analysis))
        return False

    async def departure_heatmap(self, as_of: datetime, resolution: int):
        if not 5 <= resolution <= 10 or as_of.tzinfo is None:
            raise ValueError('Invalid aggregate resolution or time')
        lower = as_of - timedelta(days=7)
        minimum_drivers = 1 if self.namespace == 'synthetic' else 5
        async with self.pool.acquire() as conn:
            # One snapshot keeps denominator/metadata consistent with concurrent ingestion.
            async with conn.transaction(isolation='repeatable_read', readonly=True):
                await conn.execute("SELECT set_config('statement_timeout', '5000', true)")
                metadata = dict(await conn.fetchrow(self._query(DEPARTURE_METADATA_QUERY), lower, as_of))
                if metadata['paired_trip_count'] > 10000:
                    raise StateError('Departure aggregate work limit exceeded', 'DEPARTURE_WORK_LIMIT', 503)
                rows = await conn.fetch(self._query(DEPARTURE_CELLS_QUERY), lower, as_of, str(resolution), minimum_drivers)
        cells = {}
        for row in rows:
            eligible, departing = row['eligible_trip_count'], row['departing_trip_count']
            percentage = round(100 * departing / eligible, 2)
            color = '#059669' if not departing else '#f59e0b' if percentage < 20 else '#ef4444' if percentage < 50 else '#991b1b'
            cells[row['cell']] = {'eligible_trip_count': eligible, 'departing_trip_count': departing,
                                 'departure_event_count': row['departure_event_count'],
                                 'departure_pct': percentage, 'color': color}
        return {'status': 'AVAILABLE' if cells else 'NO_PAIRED_EVIDENCE' if not metadata['paired_trip_count'] else 'INSUFFICIENT_EVIDENCE',
                'source': self.namespace, 'minimum_drivers': minimum_drivers, 'cells': cells, **metadata,
                'limitations': 'Geometric departure origins; synthetic data does not establish real driver behavior'}


def coordinates_from_row(row):
    geometry = row.get("geometry")
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    return tuple(tuple(point) for point in geometry) if geometry else ()
