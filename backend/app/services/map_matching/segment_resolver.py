"""Resolve real matched positions/OSM ways to frozen Dataset segment identities."""
from dataclasses import dataclass
from enum import Enum

import psycopg2


class ResolutionStatus(Enum):
    ROUTE_NODE_PAIR = "ROUTE_NODE_PAIR"  # retained output contract
    ROUTE_SPATIAL = "ROUTE_SPATIAL"
    GLOBAL_SPATIAL = "GLOBAL_SPATIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class SegmentInfo:
    segment_id: str
    from_node_id: str
    to_node_id: str
    osm_way_id: int
    direction: str
    distance_m: float
    status: ResolutionStatus


class RouteConstrainedSegmentResolver:
    def __init__(self, database_url, mapping_dir=None):
        self.database_url = database_url
        self._conn = None

    def _get_connection(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url, connect_timeout=5)
            self._conn.autocommit = True
        return self._conn

    def resolve_matched(self, lat, lon, osm_way_id=None, bearing=None, max_distance_m=100.0):
        """Use actual way identity when supplied; otherwise expose spatial ambiguity."""
        with self._get_connection().cursor() as cursor:
            cursor.execute("""
                SELECT segment_id, from_node_id, to_node_id, osm_way_id, travel_direction,
                    ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography),
                    degrees(ST_Azimuth(ST_StartPoint(geom), ST_EndPoint(geom))) +
                        CASE WHEN travel_direction = 'REVERSE' THEN 180 ELSE 0 END
                FROM road_segments
                WHERE (%s IS NULL OR osm_way_id = %s)
                  AND geom && ST_Expand(ST_SetSRID(ST_MakePoint(%s,%s),4326), %s)
                  AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)
                ORDER BY 6, segment_id LIMIT 8
            """, (lon, lat, osm_way_id, osm_way_id, lon, lat, max_distance_m / 100000,
                  lon, lat, max_distance_m))
            rows = cursor.fetchall()
        if not rows:
            return None
        # Dataset F/R rows share WKT orientation; the SQL adds 180 for reverse travel.
        near = [row for row in rows if row[5] <= rows[0][5] + 2]
        def angle(row):
            return abs((row[6] - bearing + 180) % 360 - 180) if row[6] is not None and bearing is not None else 180
        best = min(near, key=lambda row: (angle(row), row[5], row[0]))
        ambiguous = bearing is None or sum(abs(angle(row) - angle(best)) < 5 for row in near) > 1
        resolution = ResolutionStatus.AMBIGUOUS if ambiguous else (
            ResolutionStatus.ROUTE_SPATIAL if osm_way_id else ResolutionStatus.GLOBAL_SPATIAL)
        return SegmentInfo(*best[:6], resolution)

    def resolve(self, lat, lon, max_distance_m=100.0):
        return self.resolve_matched(lat, lon, max_distance_m=max_distance_m)

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
        self._conn = None


PostGISSegmentResolver = RouteConstrainedSegmentResolver
