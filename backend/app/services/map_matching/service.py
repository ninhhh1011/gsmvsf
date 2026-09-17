"""Map matching service."""
import logging
import math
from typing import Optional

from backend.app.services.map_matching.models import (
    GPSObservation,
    MapMatchRequest,
    MapMatchResponse,
    MatchedObservation,
    ResolutionStatus,
)
from backend.app.services.map_matching.osrm_adapter import (
    OsrmMapMatchingAdapter,
)
from backend.app.services.map_matching.segment_resolver import (
    PostGISSegmentResolver,
    SegmentInfo,
    ResolutionStatus as ResolverStatus,
)

logger = logging.getLogger(__name__)


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing from point 1 to point 2.

    Args:
        lat1, lon1: Starting point
        lat2, lon2: Ending point

    Returns:
        Bearing in degrees (0-360, where 0=North, 90=East)
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


class MapMatchingService:
    """
    Service for matching GPS observations to road segments.

    Runtime flow:
    1. Receive GPS observations
    2. Call OSRM Match for the trace
    3. Resolve segment identity from matched coordinates (PostGIS)
    4. Derive direction from movement + segment geometry
    5. Return normalized response
    """

    def __init__(
        self,
        osrm_adapter: OsrmMapMatchingAdapter,
        segment_resolver: Optional[PostGISSegmentResolver] = None,
    ):
        """
        Initialize the map matching service.

        Args:
            osrm_adapter: OSRM adapter instance
            segment_resolver: PostGIS-based segment resolver
        """
        self.osrm_adapter = osrm_adapter
        self._segment_resolver = segment_resolver

    def _derive_direction(
        self,
        prev_lat: Optional[float],
        prev_lon: Optional[float],
        curr_lat: float,
        curr_lon: float,
        next_lat: Optional[float],
        next_lon: Optional[float],
        segment: Optional[SegmentInfo],
    ) -> Optional[str]:
        """
        Derive travel direction from movement and segment geometry.

        Strategy:
        1. If we have consecutive matched points, calculate movement bearing
        2. Compare movement bearing with segment direction
        3. If segment exists, use segment bearing as reference

        Args:
            prev_lat, prev_lon: Previous point (if available)
            curr_lat, curr_lon: Current point
            next_lat, next_lon: Next point (if available)
            segment: Resolved segment info (if available)

        Returns:
            FORWARD, REVERSE, or None if direction cannot be determined
        """
        # Calculate movement bearing
        movement_bearing = None

        # Prefer forward movement (current to next)
        if next_lat is not None and next_lon is not None:
            movement_bearing = calculate_bearing(curr_lat, curr_lon, next_lat, next_lon)
        # Fall back to previous movement
        elif prev_lat is not None and prev_lon is not None:
            movement_bearing = calculate_bearing(prev_lat, prev_lon, curr_lat, curr_lon)

        if movement_bearing is None:
            # Cannot determine direction without movement
            return None

        # If we have a segment, use it to determine direction
        if segment is not None:
            # The segment has a direction: FORWARD means from_node -> to_node
            # We need to determine if the movement matches FORWARD or REVERSE

            # For now, just return the segment's native direction
            # A more sophisticated approach would compare bearings
            return segment.direction

        # Without segment info, we cannot definitively determine direction
        # Return None to indicate UNKNOWN
        return None

    async def match_trajectory(
        self, request: MapMatchRequest
    ) -> MapMatchResponse:
        """
        Match a trajectory to the road network.

        Args:
            request: Map matching request with observations

        Returns:
            Map matching response with matched observations

        Raises:
            OsrmAdapterError: If OSRM call fails
            ValueError: If request is invalid
        """
        if not request.observations:
            raise ValueError("No observations provided")

        # Sort observations by timestamp
        sorted_obs = sorted(
            request.observations, key=lambda x: x.timestamp if x.timestamp else ""
        )

        # Extract coordinates for OSRM (lon, lat)
        coordinates = [(o.longitude, o.latitude) for o in sorted_obs]

        # Call OSRM Match
        matching, tracepoints = await self.osrm_adapter.match(coordinates)

        # Resolve segments for all matched points
        segment_results: list[Optional[SegmentInfo]] = [None] * len(tracepoints)

        if self._segment_resolver is not None:
            # Collect matched coordinates
            matched_coords = []
            matched_indices = []

            for i, tp in enumerate(tracepoints):
                if tp is not None and tp.matched:
                    matched_coords.append((tp.location[1], tp.location[0]))  # (lat, lon)
                    matched_indices.append(i)

            if matched_coords:
                # Batch resolve
                segments = self._segment_resolver.resolve_batch(matched_coords)
                for j, (idx, seg) in enumerate(zip(matched_indices, segments)):
                    segment_results[idx] = seg

        # Build response observations
        matched_observations = []
        matched_count = 0
        unmatched_count = 0
        resolved_count = 0
        resolved_direction_count = 0

        for i, obs in enumerate(sorted_obs):
            tp = tracepoints[i] if i < len(tracepoints) else None
            segment = segment_results[i] if i < len(segment_results) else None

            if tp is None or not tp.matched:
                unmatched_count += 1
                matched_obs = MatchedObservation(
                    observation_id=obs.observation_id,
                    timestamp=obs.timestamp,
                    raw_latitude=obs.latitude,
                    raw_longitude=obs.longitude,
                    matched=False,
                    null_reason="tracepoint_null",
                )
            else:
                matched_count += 1

                # Get segment info
                road_segment_id = segment.segment_id if segment else None
                osm_way_id = segment.osm_way_id if segment else None
                resolution_status = None

                if segment:
                    resolved_count += 1
                    if segment.status == ResolverStatus.RESOLVED:
                        resolution_status = ResolutionStatus.RESOLVED
                    elif segment.status == ResolverStatus.AMBIGUOUS:
                        resolution_status = ResolutionStatus.AMBIGUOUS
                    else:
                        resolution_status = ResolutionStatus.UNRESOLVED

                # Get previous/next tracepoints for direction derivation
                prev_tp = tracepoints[i - 1] if i > 0 else None
                next_tp = tracepoints[i + 1] if i < len(tracepoints) - 1 else None

                prev_lat = prev_tp.location[1] if prev_tp and prev_tp.matched else None
                prev_lon = prev_tp.location[0] if prev_tp and prev_tp.matched else None
                next_lat = next_tp.location[1] if next_tp and next_tp.matched else None
                next_lon = next_tp.location[0] if next_tp and next_tp.matched else None

                # Derive direction
                direction = self._derive_direction(
                    prev_lat, prev_lon,
                    tp.location[1], tp.location[0],
                    next_lat, next_lon,
                    segment,
                )

                if direction is not None:
                    resolved_direction_count += 1

                matched_obs = MatchedObservation(
                    observation_id=obs.observation_id,
                    timestamp=obs.timestamp,
                    raw_latitude=obs.latitude,
                    raw_longitude=obs.longitude,
                    matched=True,
                    matched_latitude=tp.location[1],
                    matched_longitude=tp.location[0],
                    road_segment_id=road_segment_id,
                    osm_way_id=osm_way_id,
                    direction=direction,
                    confidence=matching.confidence if i == 0 else None,
                    distance_to_road_m=tp.distance,
                    resolution_status=resolution_status,
                )

            matched_observations.append(matched_obs)

        # Log statistics
        if matched_count > 0:
            logger.info(
                f"Matched {matched_count}/{len(sorted_obs)} observations, "
                f"resolved {resolved_count} segments, "
                f"resolved {resolved_direction_count} directions"
            )

        return MapMatchResponse(
            trajectory_id=request.trajectory_id,
            trip_id=request.trip_id,
            total_observations=len(sorted_obs),
            matched_count=matched_count,
            unmatched_count=unmatched_count,
            observations=matched_observations,
            overall_confidence=matching.confidence,
            trace_geometry=matching.geometry,
        )
