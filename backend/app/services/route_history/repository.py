"""
Route History Repository
======================

PostgreSQL persistence for historical routes and route families.

Provides database operations for:
- Historical routes CRUD
- H3 index queries
- Route family management
"""

from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import execute_values
import gzip
import csv
from pathlib import Path

from .signature import H3SignatureGenerator, H3Signature


@dataclass
class HistoricalRouteRecord:
    """Database record for a historical route."""
    route_id: str
    trip_id: str
    driver_id: str
    started_at: datetime
    ended_at: datetime
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    total_distance_m: float
    segment_count: int


@dataclass
class RouteFamilyRecord:
    """Database record for a route family."""
    family_id: str
    representative_route_id: str
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    direction_bearing: float
    trip_count: int
    unique_driver_count: int
    weighted_support: float


class RouteHistoryRepository:
    """
    Repository for historical route data in PostgreSQL.

    Provides methods for:
    - Bulk insert routes from dataset
    - Query by H3 cells
    - Query by origin/destination proximity
    - Route family CRUD
    """

    def __init__(self, database_url: str):
        self.database_url = database_url

    def get_connection(self):
        """Get a new database connection."""
        return psycopg2.connect(self.database_url)

    def initialize_schema(self) -> None:
        """Initialize database schema from schema.sql."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema_sql = f.read()

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()

    def insert_route(
        self,
        route_id: str,
        trip_id: str,
        driver_id: str,
        started_at: datetime,
        ended_at: datetime,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        total_distance_m: float,
        segment_ids: List[str],
        h3_cells: List[str]
    ) -> None:
        """Insert a single route with segments and H3 cells."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Insert route
                cur.execute("""
                    INSERT INTO historical_routes
                    (route_id, trip_id, driver_id, started_at, ended_at,
                     origin_lat, origin_lng, dest_lat, dest_lng, total_distance_m, segment_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (route_id) DO UPDATE SET
                        driver_id = EXCLUDED.driver_id,
                        updated_at = NOW()
                """, (route_id, trip_id, driver_id, started_at, ended_at,
                      origin_lat, origin_lng, dest_lat, dest_lng, total_distance_m, len(segment_ids)))

                # Insert segments
                for seq, seg_id in enumerate(segment_ids):
                    cur.execute("""
                        INSERT INTO historical_route_segments (route_id, seq, segment_id, direction, length_m)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (route_id, seq) DO UPDATE SET
                            segment_id = EXCLUDED.segment_id
                    """, (route_id, seq, seg_id, "FORWARD", 100.0))  # Default length

                # Insert H3 cells
                for seq, h3_cell in enumerate(h3_cells):
                    cur.execute("""
                        INSERT INTO historical_route_h3 (route_id, seq, h3_cell_res11)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (route_id, seq) DO UPDATE SET
                            h3_cell_res11 = EXCLUDED.h3_cell_res11
                    """, (route_id, seq, h3_cell))

            conn.commit()

    def bulk_insert_routes(
        self,
        routes: List[Dict[str, Any]]
    ) -> int:
        """
        Bulk insert multiple routes.

        Args:
            routes: List of route dictionaries

        Returns:
            Number of routes inserted
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Bulk insert routes
                route_values = [
                    (r["route_id"], r["trip_id"], r["driver_id"],
                     r["started_at"], r["ended_at"],
                     r["origin_lat"], r["origin_lng"],
                     r["dest_lat"], r["dest_lng"],
                     r["total_distance_m"], len(r["segment_ids"]))
                    for r in routes
                ]

                execute_values(cur, """
                    INSERT INTO historical_routes
                    (route_id, trip_id, driver_id, started_at, ended_at,
                     origin_lat, origin_lng, dest_lat, dest_lng, total_distance_m, segment_count)
                    VALUES %s
                    ON CONFLICT (route_id) DO UPDATE SET
                        driver_id = EXCLUDED.driver_id,
                        updated_at = NOW()
                """, route_values)

                # Bulk insert segments
                segment_values = []
                for r in routes:
                    for seq, seg_id in enumerate(r["segment_ids"]):
                        segment_values.append(
                            (r["route_id"], seq, seg_id, "FORWARD", 100.0)
                        )

                if segment_values:
                    execute_values(cur, """
                        INSERT INTO historical_route_segments
                        (route_id, seq, segment_id, direction, length_m)
                        VALUES %s
                        ON CONFLICT (route_id, seq) DO UPDATE SET
                            segment_id = EXCLUDED.segment_id
                    """, segment_values)

                # Bulk insert H3 cells
                h3_values = []
                for r in routes:
                    for seq, h3_cell in enumerate(r["h3_cells"]):
                        h3_values.append((r["route_id"], seq, h3_cell))

                if h3_values:
                    execute_values(cur, """
                        INSERT INTO historical_route_h3 (route_id, seq, h3_cell_res11)
                        VALUES %s
                        ON CONFLICT (route_id, seq) DO UPDATE SET
                            h3_cell_res11 = EXCLUDED.h3_cell_res11
                    """, h3_values)

            conn.commit()

        return len(routes)

    def query_by_h3_cells(
        self,
        h3_cells: List[str],
        min_overlap: int = 1
    ) -> List[Tuple[str, int]]:
        """
        Query routes that pass through any of the given H3 cells.

        This is the inverted index lookup.

        Args:
            h3_cells: List of H3 cell IDs
            min_overlap: Minimum number of cells a route must share

        Returns:
            List of (route_id, shared_cell_count) sorted by count descending
        """
        if not h3_cells:
            return []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Use PostgreSQL array for efficient IN clause
                cur.execute("""
                    SELECT route_id, COUNT(*) as shared_count
                    FROM historical_route_h3
                    WHERE h3_cell_res11 = ANY(%s)
                    GROUP BY route_id
                    HAVING COUNT(*) >= %s
                    ORDER BY shared_count DESC
                """, (h3_cells, min_overlap))

                return [(row[0], row[1]) for row in cur.fetchall()]

    def query_routes_in_time_window(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[HistoricalRouteRecord]:
        """Query routes within a time window."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT route_id, trip_id, driver_id, started_at, ended_at,
                           origin_lat, origin_lng, dest_lat, dest_lng,
                           total_distance_m, segment_count
                    FROM historical_routes
                    WHERE started_at >= %s AND started_at <= %s
                    ORDER BY started_at
                """, (start_time, end_time))

                return [HistoricalRouteRecord(*row) for row in cur.fetchall()]

    def query_routes_by_driver(
        self,
        driver_id: str,
        limit: int = 100
    ) -> List[HistoricalRouteRecord]:
        """Query routes by driver."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT route_id, trip_id, driver_id, started_at, ended_at,
                           origin_lat, origin_lng, dest_lat, dest_lng,
                           total_distance_m, segment_count
                    FROM historical_routes
                    WHERE driver_id = %s
                    ORDER BY started_at DESC
                    LIMIT %s
                """, (driver_id, limit))

                return [HistoricalRouteRecord(*row) for row in cur.fetchall()]

    def get_route_segments(self, route_id: str) -> List[str]:
        """Get ordered segment IDs for a route."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT segment_id
                    FROM historical_route_segments
                    WHERE route_id = %s
                    ORDER BY seq
                """, (route_id,))

                return [row[0] for row in cur.fetchall()]

    def get_route_h3_cells(self, route_id: str) -> List[str]:
        """Get ordered H3 cells for a route."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT h3_cell_res11
                    FROM historical_route_h3
                    WHERE route_id = %s
                    ORDER BY seq
                """, (route_id,))

                return [row[0] for row in cur.fetchall()]

    def insert_route_family(
        self,
        family_id: str,
        representative_route_id: str,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        direction_bearing: float,
        trip_count: int,
        unique_driver_count: int,
        weighted_support: float
    ) -> None:
        """Insert or update a route family."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO route_families
                    (family_id, representative_route_id, origin_lat, origin_lng,
                     dest_lat, dest_lng, direction_bearing, trip_count,
                     unique_driver_count, weighted_support)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (family_id) DO UPDATE SET
                        representative_route_id = EXCLUDED.representative_route_id,
                        trip_count = EXCLUDED.trip_count,
                        unique_driver_count = EXCLUDED.unique_driver_count,
                        weighted_support = EXCLUDED.weighted_support,
                        updated_at = NOW()
                """, (family_id, representative_route_id, origin_lat, origin_lng,
                      dest_lat, dest_lng, direction_bearing, trip_count,
                      unique_driver_count, weighted_support))

            conn.commit()

    def get_route_families_by_context(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        max_origin_dist_km: float = 2.0,
        max_dest_dist_km: float = 2.0,
        limit: int = 10
    ) -> List[RouteFamilyRecord]:
        """
        Get route families matching origin/destination context.

        Note: This is a simplified proximity search. For production,
        use PostGIS geography functions for accurate distance calculation.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Simplified bounding box filter (approximate)
                lat_range = max_origin_dist_km / 111.0  # ~111km per degree latitude
                lng_range = max_dest_dist_km / (111.0 * abs(cos(origin_lat * 3.14159 / 180)))

                cur.execute("""
                    SELECT family_id, representative_route_id, origin_lat, origin_lng,
                           dest_lat, dest_lng, direction_bearing, trip_count,
                           unique_driver_count, weighted_support
                    FROM route_families
                    WHERE origin_lat BETWEEN %s AND %s
                      AND origin_lng BETWEEN %s AND %s
                      AND dest_lat BETWEEN %s AND %s
                      AND dest_lng BETWEEN %s AND %s
                    ORDER BY weighted_support DESC
                    LIMIT %s
                """, (
                    origin_lat - lat_range, origin_lat + lat_range,
                    origin_lng - lng_range, origin_lng + lng_range,
                    dest_lat - lat_range, dest_lat + lat_range,
                    dest_lng - lng_range, dest_lng + lng_range,
                    limit
                ))

                return [RouteFamilyRecord(*row) for row in cur.fetchall()]

    def add_family_member(
        self,
        family_id: str,
        route_id: str,
        time_weight: float = 1.0,
        recency_weight: float = 1.0
    ) -> None:
        """Add a route as member of a family."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO route_family_members (family_id, route_id, time_weight, recency_weight)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (family_id, route_id) DO UPDATE SET
                        time_weight = EXCLUDED.time_weight,
                        recency_weight = EXCLUDED.recency_weight
                """, (family_id, route_id, time_weight, recency_weight))

            conn.commit()

    def get_family_members(self, family_id: str) -> List[str]:
        """Get all route IDs in a family."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT route_id
                    FROM route_family_members
                    WHERE family_id = %s
                """, (family_id,))

                return [row[0] for row in cur.fetchall()]

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                stats = {}

                cur.execute("SELECT COUNT(*) FROM historical_routes")
                stats["total_routes"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM historical_route_segments")
                stats["total_segments"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(DISTINCT h3_cell_res11) FROM historical_route_h3")
                stats["unique_h3_cells"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM route_families")
                stats["total_families"] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM route_family_members")
                stats["total_family_members"] = cur.fetchone()[0]

                return stats

    def query_by_driver(
        self,
        driver_id: str,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        days_window: int = 7,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Query historical routes for a driver matching origin/destination context.

        Used by familiarity calculation to find driver's habitual routes.
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Bounding box filter
                lat_range = 0.02  # ~2km
                lng_range = 0.02 / abs(cos(origin_lat * 3.14159 / 180))

                # First get unique drivers count
                cur.execute("""
                    SELECT COUNT(DISTINCT r.driver_id)
                    FROM historical_routes r
                    WHERE r.driver_id = %s
                      AND r.started_at >= NOW() - INTERVAL '%s days'
                      AND r.origin_lat BETWEEN %s AND %s
                      AND r.origin_lng BETWEEN %s AND %s
                      AND r.dest_lat BETWEEN %s AND %s
                      AND r.dest_lng BETWEEN %s AND %s
                """, (
                    driver_id,
                    days_window,
                    origin_lat - lat_range, origin_lat + lat_range,
                    origin_lng - lng_range, origin_lng + lng_range,
                    dest_lat - lat_range, dest_lat + lat_range,
                    dest_lng - lat_range, dest_lng + lng_range,
                ))
                unique_drivers = cur.fetchone()[0] or 1

                # Then get routes
                cur.execute("""
                    SELECT r.route_id, r.driver_id, r.origin_lat, r.origin_lng,
                           r.dest_lat, r.dest_lng, r.started_at
                    FROM historical_routes r
                    WHERE r.driver_id = %s
                      AND r.started_at >= NOW() - INTERVAL '%s days'
                      AND r.origin_lat BETWEEN %s AND %s
                      AND r.origin_lng BETWEEN %s AND %s
                      AND r.dest_lat BETWEEN %s AND %s
                      AND r.dest_lng BETWEEN %s AND %s
                    ORDER BY r.started_at DESC
                    LIMIT %s
                """, (
                    driver_id,
                    days_window,
                    origin_lat - lat_range, origin_lat + lat_range,
                    origin_lng - lng_range, origin_lng + lng_range,
                    dest_lat - lat_range, dest_lat + lat_range,
                    dest_lng - lat_range, dest_lng + lng_range,
                    limit
                ))

                return [
                    {
                        "route_id": row[0],
                        "driver_id": row[1],
                        "origin_lat": row[2],
                        "origin_lng": row[3],
                        "dest_lat": row[4],
                        "dest_lng": row[5],
                        "started_at": row[6],
                        "unique_drivers": unique_drivers,
                    }
                    for row in cur.fetchall()
                ]

    def query_by_origin_dest(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        days_window: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query historical routes matching origin/destination context.

        Used for population-level familiarity (not driver-specific).
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                lat_range = 0.02  # ~2km
                lng_range = 0.02 / abs(cos(origin_lat * 3.14159 / 180))

                cur.execute("""
                    SELECT route_id, driver_id, origin_lat, origin_lng,
                           dest_lat, dest_lng, started_at, total_distance_m
                    FROM historical_routes
                    WHERE started_at >= NOW() - INTERVAL '%s days'
                      AND origin_lat BETWEEN %s AND %s
                      AND origin_lng BETWEEN %s AND %s
                      AND dest_lat BETWEEN %s AND %s
                      AND dest_lng BETWEEN %s AND %s
                    ORDER BY started_at DESC
                    LIMIT %s
                """, (
                    days_window,
                    origin_lat - lat_range, origin_lat + lat_range,
                    origin_lng - lng_range, origin_lng + lng_range,
                    dest_lat - lat_range, dest_lat + lat_range,
                    dest_lng - lng_range, dest_lng + lng_range,
                    limit
                ))

                return [
                    {
                        "route_id": row[0],
                        "driver_id": row[1],
                        "origin_lat": row[2],
                        "origin_lng": row[3],
                        "dest_lat": row[4],
                        "dest_lng": row[5],
                        "started_at": row[6],
                        "total_distance_m": row[7],
                    }
                    for row in cur.fetchall()
                ]


# Helper for math.cos
from math import cos
