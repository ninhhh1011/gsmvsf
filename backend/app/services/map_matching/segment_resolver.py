"""Segment resolver using road network data."""
import gzip
import logging
from pathlib import Path
from typing import Optional
import math

logger = logging.getLogger(__name__)


class SegmentInfo:
    """Information about a road segment."""

    def __init__(
        self,
        segment_id: str,
        from_node_id: str,
        to_node_id: str,
        osm_way_id: int,
        direction: str,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
    ):
        self.segment_id = segment_id
        self.from_node_id = from_node_id
        self.to_node_id = to_node_id
        self.osm_way_id = osm_way_id
        self.direction = direction
        self.from_lat = from_lat
        self.from_lon = from_lon
        self.to_lat = to_lat
        self.to_lon = to_lon

    @property
    def center_lat(self) -> float:
        return (self.from_lat + self.to_lat) / 2

    @property
    def center_lon(self) -> float:
        return (self.from_lon + self.to_lon) / 2


class CoordinateSegmentResolver:
    """
    Resolves road segment identity based on coordinates.

    This resolver loads road segments from Dataset V1 and finds the nearest
    segment to matched GPS coordinates using a simple spatial index.
    """

    def __init__(self, segments_path: Path, nodes_path: Path):
        """
        Initialize the resolver.

        Args:
            segments_path: Path to road_segments.csv.gz
            nodes_path: Path to road_nodes.csv.gz
        """
        self.segments_path = segments_path
        self.nodes_path = nodes_path
        self._segments: dict[str, SegmentInfo] = {}
        self._spatial_index: list[tuple[float, float, str]] = []  # (lat, lon, segment_id)
        self._loaded = False

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate haversine distance between two points in meters."""
        R = 6371000  # Earth's radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _point_to_segment_distance(
        self, lat: float, lon: float, seg: SegmentInfo
    ) -> float:
        """Calculate perpendicular distance from point to segment."""
        # Simple approach: distance to nearest endpoint or midpoint
        d_from = self._haversine_distance(lat, lon, seg.from_lat, seg.from_lon)
        d_to = self._haversine_distance(lat, lon, seg.to_lat, seg.to_lon)
        d_center = self._haversine_distance(lat, lon, seg.center_lat, seg.center_lon)
        return min(d_from, d_to, d_center)

    def load(self) -> None:
        """Load road network data into memory."""
        if self._loaded:
            return

        logger.info(f"Loading road segments from {self.segments_path}")
        logger.info(f"Loading road nodes from {self.nodes_path}")

        # Load nodes first
        nodes = {}
        try:
            with gzip.open(self.nodes_path, "rt", encoding="utf-8", errors="replace") as f:
                header = f.readline().strip().split(",")
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 3:
                        node_id = parts[0]
                        lat = float(parts[1])
                        lon = float(parts[2])
                        nodes[node_id] = (lat, lon)
        except Exception as e:
            logger.error(f"Error loading nodes: {e}")
            raise

        logger.info(f"Loaded {len(nodes)} road nodes")

        # Load segments
        count = 0
        try:
            with gzip.open(self.segments_path, "rt", encoding="utf-8", errors="replace") as f:
                header = f.readline().strip().split(",")
                # Expected: segment_id,from_node_id,to_node_id,travel_direction,base_segment_id,
                #           osm_way_id,geometry,length_m,road_type,road_name,oneway,
                #           maxspeed_kmh,lanes,bridge,tunnel,access

                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) >= 6:
                        segment_id = parts[0]
                        from_node_id = parts[1]
                        to_node_id = parts[2]
                        direction = parts[3]
                        osm_way_id = int(parts[5])

                        from_coords = nodes.get(from_node_id)
                        to_coords = nodes.get(to_node_id)

                        if from_coords and to_coords:
                            seg = SegmentInfo(
                                segment_id=segment_id,
                                from_node_id=from_node_id,
                                to_node_id=to_node_id,
                                osm_way_id=osm_way_id,
                                direction=direction,
                                from_lat=from_coords[0],
                                from_lon=from_coords[1],
                                to_lat=to_coords[0],
                                to_lon=to_coords[1],
                            )
                            self._segments[segment_id] = seg

                            # Add to spatial index (use center point)
                            self._spatial_index.append(
                                (seg.center_lat, seg.center_lon, segment_id)
                            )
                            count += 1

        except Exception as e:
            logger.error(f"Error loading segments: {e}")
            raise

        logger.info(f"Loaded {count} road segments")
        self._loaded = True

    def resolve(
        self, lat: float, lon: float, k: int = 10
    ) -> Optional[SegmentInfo]:
        """
        Find the nearest segment to a coordinate.

        Uses a simple grid-based spatial index for efficiency.

        Args:
            lat: Latitude
            lon: Longitude
            k: Number of nearest candidates to consider (not used in simple impl)

        Returns:
            Nearest SegmentInfo or None if no segments loaded
        """
        if not self._loaded:
            self.load()

        if not self._segments:
            return None

        # Simple brute-force approach for now
        # TODO: Implement spatial index for better performance
        best_segment = None
        best_distance = float("inf")

        for seg in self._segments.values():
            dist = self._point_to_segment_distance(lat, lon, seg)
            if dist < best_distance:
                best_distance = dist
                best_segment = seg

        return best_segment

    def resolve_batch(
        self, coordinates: list[tuple[float, float]]
    ) -> list[Optional[SegmentInfo]]:
        """
        Resolve multiple coordinates.

        Args:
            coordinates: List of (lat, lon) tuples

        Returns:
            List of SegmentInfo or None
        """
        if not self._loaded:
            self.load()

        return [self.resolve(lat, lon) for lat, lon in coordinates]

    @property
    def segment_count(self) -> int:
        """Return number of loaded segments."""
        return len(self._segments)
