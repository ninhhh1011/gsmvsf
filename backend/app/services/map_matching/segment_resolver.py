"""Segment resolver using OSM route annotations and PostGIS spatial fallback."""
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import psycopg2

logger = logging.getLogger(__name__)


class ResolutionStatus(Enum):
    """Status of segment resolution."""
    ROUTE_NODE_PAIR = "ROUTE_NODE_PAIR"
    ROUTE_SPATIAL = "ROUTE_SPATIAL"
    GLOBAL_SPATIAL = "GLOBAL_SPATIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class SegmentInfo:
    """Information about a resolved road segment."""
    segment_id: str
    from_node_id: str
    to_node_id: str
    osm_way_id: int
    direction: str  # FORWARD or REVERSE
    distance_m: float
    status: ResolutionStatus


class RouteConstrainedSegmentResolver:
    """
    Resolves road segment identity using OSRM route annotations.

    Primary method: Use OSRM node annotations to constrain the segment search
    to the actual matched route path.

    Fallback: Use PostGIS spatial lookup when route information is insufficient.
    """

    def __init__(self, database_url: str, mapping_dir: Path):
        """
        Initialize the resolver.

        Args:
            database_url: PostgreSQL connection URL
            mapping_dir: Directory containing OSM mappings
        """
        self.database_url = database_url
        self.mapping_dir = mapping_dir
        self._conn = None

        # Load OSM mappings
        self._load_mappings()

    def _load_mappings(self):
        """Load OSM ↔ Dataset V1 mappings."""
        logger.info("Loading OSM mappings...")

        # Load node mapping
        node_mapping_path = self.mapping_dir / "node_mapping.json"
        if node_mapping_path.exists():
            with open(node_mapping_path) as f:
                node_data = json.load(f)
                self.internal_to_osm = node_data.get("internal_to_osm", {})
                self.osm_to_internal = node_data.get("osm_to_internal", {})
                logger.info(f"Loaded {len(self.internal_to_osm)} node mappings")
        else:
            self.internal_to_osm = {}
            self.osm_to_internal = {}
            logger.warning(f"Node mapping not found: {node_mapping_path}")

        # Load segment mapping
        segment_mapping_path = self.mapping_dir / "segment_mapping.json"
        if segment_mapping_path.exists():
            with open(segment_mapping_path) as f:
                seg_data = json.load(f)
                self.segment_osm = seg_data.get("segment_osm", {})
                # Convert string keys back to tuples
                self.osm_pair_to_segment = {}
                for key_str, seg_ids in seg_data.get("osm_pair_to_segment", {}).items():
                    # Parse key like "(123, 456, 789)"
                    key_parts = key_str.strip("()").split(",")
                    key = (int(key_parts[0]), int(key_parts[1]), int(key_parts[2]))
                    self.osm_pair_to_segment[key] = seg_ids
                logger.info(f"Loaded {len(self.segment_osm)} segment OSM mappings")
        else:
            self.segment_osm = {}
            self.osm_pair_to_segment = {}
            logger.warning(f"Segment mapping not found: {segment_mapping_path}")

        # Load OSM way node lists
        way_nodes_path = self.mapping_dir / "osm_way_nodes.json"
        if way_nodes_path.exists():
            with open(way_nodes_path) as f:
                raw = json.load(f)
                self.osm_way_nodes = {int(k): v for k, v in raw.items()}
                logger.info(f"Loaded {len(self.osm_way_nodes)} OSM ways")
        else:
            self.osm_way_nodes = {}
            logger.warning(f"OSM way nodes not found: {way_nodes_path}")

    def _get_connection(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
        return self._conn

    def resolve_with_route(
        self,
        osm_node_sequence: list[int],
        matched_coords: list[tuple[float, float]],
        observation_indices: list[int],
    ) -> dict[int, Optional[SegmentInfo]]:
        """
        Resolve segments using OSRM route node annotations.

        Args:
            osm_node_sequence: Ordered list of OSM node IDs from route annotations
            matched_coords: Matched GPS coordinates (lat, lon) for each observation
            observation_indices: Indices of observations to resolve

        Returns:
            Dict mapping observation_index -> SegmentInfo or None
        """
        results = {}

        if not osm_node_sequence or not matched_coords:
            # No route info, fall back to spatial
            for idx in observation_indices:
                results[idx] = self._resolve_spatial(matched_coords[idx][0], matched_coords[idx][1])
            return results

        # Map OSM nodes to internal nodes
        internal_sequence = []
        for osm_id in osm_node_sequence:
            internal_id = self.osm_to_internal.get(str(osm_id))
            if internal_id:
                internal_sequence.append((osm_id, internal_id))

        if len(internal_sequence) < 2:
            # Not enough mapped nodes, fall back to spatial
            for idx in observation_indices:
                results[idx] = self._resolve_spatial(matched_coords[idx][0], matched_coords[idx][1])
            return results

        # Build OSM node pair → segment lookup
        # For each consecutive pair in the route, find matching segments
        route_pairs = set()
        for i in range(len(internal_sequence) - 1):
            osm_a, int_a = internal_sequence[i]
            osm_b, int_b = internal_sequence[i + 1]

            # Forward pair: a -> b
            key_fwd = (osm_a, osm_b)
            route_pairs.add((key_fwd, "FORWARD", int_a, int_b))

            # Reverse pair: b -> a
            key_rev = (osm_b, osm_a)
            route_pairs.add((key_rev, "REVERSE", int_b, int_a))

        # Query segments by internal node IDs
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get all internal node IDs from route
            route_node_ids = [int_a for _, int_a in internal_sequence]

            cursor.execute("""
                SELECT segment_id, from_node_id, to_node_id, osm_way_id, travel_direction,
                    ST_Distance(
                        geom::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) as dist_m
                FROM road_segments
                WHERE from_node_id = ANY(%s) OR to_node_id = ANY(%s)
            """, (matched_coords[0][1], matched_coords[0][0], route_node_ids, route_node_ids))

            all_segments = cursor.fetchall()

            # Group segments by node pair
            segments_by_pair = {}
            for row in all_segments:
                seg_id, from_n, to_n, osm_way, direction, dist = row
                # Use internal node IDs as key
                key = (from_n, to_n)
                if key not in segments_by_pair:
                    segments_by_pair[key] = []
                segments_by_pair[key].append(row)

        finally:
            cursor.close()

        # For each observation, find the segment based on route position
        for idx in observation_indices:
            if idx >= len(matched_coords):
                results[idx] = self._resolve_spatial(matched_coords[idx][0], matched_coords[idx][1])
                continue

            lat, lon = matched_coords[idx]

            # Find the nearest route segment for this observation
            # Check if any segment's from/to nodes are in the route
            best_segment = None
            best_dist = float('inf')

            for seg in all_segments:
                seg_id, from_n, to_n, osm_way, direction, dist = seg
                if dist < best_dist:
                    best_dist = dist
                    best_segment = seg

            if best_segment and best_dist < 100:
                seg_id, from_n, to_n, osm_way, direction, dist = best_segment

                # Determine direction based on route context
                resolved_direction = direction
                if (from_n, to_n) in segments_by_pair:
                    # Check if route traverses this segment
                    # This is a simplification - in reality we'd trace the exact route
                    resolved_direction = direction

                results[idx] = SegmentInfo(
                    segment_id=seg_id,
                    from_node_id=from_n,
                    to_node_id=to_n,
                    osm_way_id=osm_way,
                    direction=resolved_direction,
                    distance_m=dist,
                    status=ResolutionStatus.ROUTE_NODE_PAIR,
                )
            else:
                # Fall back to spatial
                results[idx] = self._resolve_spatial(lat, lon)

        return results

    def _resolve_spatial(
        self,
        lat: float,
        lon: float,
        max_distance_m: float = 100.0,
    ) -> Optional[SegmentInfo]:
        """Resolve using PostGIS spatial lookup (fallback only)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
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

            if len(rows) == 1:
                row = rows[0]
                return SegmentInfo(
                    segment_id=row[0],
                    from_node_id=row[1],
                    to_node_id=row[2],
                    osm_way_id=row[3],
                    direction=row[4],
                    distance_m=row[5],
                    status=ResolutionStatus.GLOBAL_SPATIAL,
                )

            # Check if we have a clear winner
            best_dist = rows[0][5]
            second_dist = rows[1][5]

            if second_dist > best_dist * 1.5:
                row = rows[0]
                return SegmentInfo(
                    segment_id=row[0],
                    from_node_id=row[1],
                    to_node_id=row[2],
                    osm_way_id=row[3],
                    direction=row[4],
                    distance_m=row[5],
                    status=ResolutionStatus.GLOBAL_SPATIAL,
                )

            # Ambiguous
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

    def resolve(
        self,
        lat: float,
        lon: float,
        max_distance_m: float = 100.0,
    ) -> Optional[SegmentInfo]:
        """
        Find the nearest segment to a coordinate (legacy interface).

        For new code, use resolve_with_route() instead.
        """
        return self._resolve_spatial(lat, lon, max_distance_m)

    def resolve_batch(
        self,
        coordinates: list[tuple[float, float]],
        max_distance_m: float = 100.0,
    ) -> list[Optional[SegmentInfo]]:
        """Resolve multiple coordinates using spatial lookup (legacy interface)."""
        return [self._resolve_spatial(lat, lon, max_distance_m) for lat, lon in coordinates]

    def close(self):
        """Close database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# Backward compatibility alias
PostGISSegmentResolver = RouteConstrainedSegmentResolver
