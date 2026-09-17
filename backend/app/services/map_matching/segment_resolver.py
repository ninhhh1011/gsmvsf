"""Segment resolver using PostGIS spatial queries."""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class ResolutionStatus(Enum):
    """Status of segment resolution."""
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class SegmentInfo:
    """Information about a road segment."""
    segment_id: str
    from_node_id: str
    to_node_id: str
    osm_way_id: int
    direction: str  # FORWARD or REVERSE
    distance_m: float
    status: ResolutionStatus


class PostGISSegmentResolver:
    """
    Resolves road segment identity using PostGIS spatial queries.

    Uses the road_segments table in PostgreSQL with PostGIS extension
    for efficient nearest-neighbor lookups.
    """

    def __init__(self, database_url: str):
        """
        Initialize the resolver.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self._conn = None

    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
        return self._conn

    def resolve(
        self,
        lat: float,
        lon: float,
        max_distance_m: float = 100.0,
    ) -> Optional[SegmentInfo]:
        """
        Find the nearest segment to a coordinate.

        Args:
            lat: Latitude
            lon: Longitude
            max_distance_m: Maximum distance to consider (filters outliers)

        Returns:
            SegmentInfo or None if no segment found within max_distance
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Query for nearest segment using KNN distance operator <#>
            # This uses the spatial index for efficient lookup
            cursor.execute("""
                SELECT
                    segment_id,
                    from_node_id,
                    to_node_id,
                    osm_way_id,
                    travel_direction,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) as dist_m
                FROM road_segments
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                ORDER BY geom <#> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                LIMIT 3
            """, (lon, lat, lon, lat, max_distance_m, lon, lat))

            rows = cursor.fetchall()

            if not rows:
                return None

            # Check if we have a clear winner
            if len(rows) == 1:
                row = rows[0]
                return SegmentInfo(
                    segment_id=row[0],
                    from_node_id=row[1],
                    to_node_id=row[2],
                    osm_way_id=row[3],
                    direction=row[4],
                    distance_m=row[5],
                    status=ResolutionStatus.RESOLVED,
                )

            # Multiple candidates - check if distances are similar
            # If the best match is significantly better, use it
            best_dist = rows[0][5]
            second_dist = rows[1][5]

            # If second best is more than 50% farther, use best
            if second_dist > best_dist * 1.5:
                row = rows[0]
                return SegmentInfo(
                    segment_id=row[0],
                    from_node_id=row[1],
                    to_node_id=row[2],
                    osm_way_id=row[3],
                    direction=row[4],
                    distance_m=row[5],
                    status=ResolutionStatus.RESOLVED,
                )

            # Ambiguous - multiple similar candidates
            # Return the closest one but mark as ambiguous
            row = rows[0]
            return SegmentInfo(
                segment_id=row[0],
                from_node_id=row[1],
                to_node_id=row[2],
                osm_way_id=row[3],
                direction=row[4],
                distance_m=row[5],
                status=ResolutionStatus.AMBIGUOUS,
            )

        except Exception as e:
            logger.error(f"Error resolving segment at ({lat}, {lon}): {e}")
            return None
        finally:
            cursor.close()

    def resolve_batch(
        self,
        coordinates: list[tuple[float, float]],
        max_distance_m: float = 100.0,
    ) -> list[Optional[SegmentInfo]]:
        """
        Resolve multiple coordinates efficiently using batch query.

        Args:
            coordinates: List of (lat, lon) tuples
            max_distance_m: Maximum distance to consider

        Returns:
            List of SegmentInfo or None
        """
        if not coordinates:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build batch query using LATERAL join
            # This runs a nearest-neighbor search for each input point
            query = """
                WITH points AS (
                    SELECT unnest(%s) as lat, unnest(%s) as lon, generate_series(1, %s) as idx
                )
                SELECT
                    p.idx,
                    r.segment_id,
                    r.from_node_id,
                    r.to_node_id,
                    r.osm_way_id,
                    r.travel_direction,
                    ST_Distance(
                        r.geom::geography,
                        ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography
                    ) as dist_m
                FROM points p
                CROSS JOIN LATERAL (
                    SELECT *
                    FROM road_segments
                    WHERE ST_DWithin(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
                        %s
                    )
                    ORDER BY geom <#> ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)
                    LIMIT 1
                ) r
            """

            lats = [c[0] for c in coordinates]
            lons = [c[1] for c in coordinates]

            cursor.execute(query, (lats, lons, len(coordinates), max_distance_m))
            rows = cursor.fetchall()

            # Build results in order
            results = [None] * len(coordinates)
            for row in rows:
                idx = row[0] - 1  # PostgreSQL arrays are 1-indexed
                results[idx] = SegmentInfo(
                    segment_id=row[1],
                    from_node_id=row[2],
                    to_node_id=row[3],
                    osm_way_id=row[4],
                    direction=row[5],
                    distance_m=row[6],
                    status=ResolutionStatus.RESOLVED,
                )

            return results

        except Exception as e:
            logger.error(f"Error in batch resolution: {e}")
            # Fall back to individual queries
            return [self.resolve(lat, lon, max_distance_m) for lat, lon in coordinates]
        finally:
            cursor.close()

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None
