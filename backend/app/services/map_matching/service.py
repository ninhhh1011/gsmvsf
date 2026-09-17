"""Map matching service with route-constrained segment resolution."""
import logging
import math
from pathlib import Path
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
    Tracepoint,
    Matching,
)
from backend.app.services.map_matching.segment_resolver import (
    RouteConstrainedSegmentResolver,
    SegmentInfo,
    ResolutionStatus as ResolverStatus,
)

logger = logging.getLogger(__name__)


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2."""
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

    Uses route-constrained segment resolution to leverage OSRM's matched path
    for accurate segment identification.
    """

    def __init__(
        self,
        osrm_adapter: OsrmMapMatchingAdapter,
        segment_resolver: Optional[RouteConstrainedSegmentResolver] = None,
    ):
        """
        Initialize the map matching service.

        Args:
            osrm_adapter: OSRM adapter instance
            segment_resolver: Route-constrained segment resolver
        """
        self.osrm_adapter = osrm_adapter
        self._segment_resolver = segment_resolver

    def _derive_direction_from_route(
        self,
        osm_from_node: int,
        osm_to_node: int,
        segment: SegmentInfo,
    ) -> str:
        """
        Derive direction from OSRM route traversal.

        Compares OSRM's node traversal with the Dataset segment orientation
        to determine if the vehicle is moving FORWARD or REVERSE along the segment.
        """
        # Get segment's OSM node mapping
        seg_osm = getattr(segment, '_osm_from', None), getattr(segment, '_osm_to', None)

        if seg_osm[0] is None or seg_osm[1] is None:
            # No OSM mapping, fall back to segment direction
            return segment.direction

        # Check if OSRM's traversal matches segment orientation
        if osm_from_node == seg_osm[0] and osm_to_node == seg_osm[1]:
            # OSRM traversal matches FORWARD direction
            return "FORWARD"
        elif osm_from_node == seg_osm[1] and osm_to_node == seg_osm[0]:
            # OSRM traversal matches REVERSE direction
            return "REVERSE"
        else:
            # Traversal doesn't match segment endpoints exactly
            # Use segment's native direction
            return segment.direction

    async def match_trajectory(
        self, request: MapMatchRequest
    ) -> MapMatchResponse:
        """
        Match a trajectory to the road network.

        Uses route-constrained segment resolution when possible.

        Args:
            request: Map matching request with observations

        Returns:
            Map matching response with matched observations
        """
        if not request.observations:
            raise ValueError("No observations provided")

        # Sort observations by timestamp
        sorted_obs = sorted(
            request.observations, key=lambda x: x.timestamp if x.timestamp else ""
        )

        # Extract coordinates for OSRM (lon, lat)
        coordinates = [(o.longitude, o.latitude) for o in sorted_obs]

        # Call OSRM Match with node annotations
        matching, tracepoints = await self.osrm_adapter.match(
            coordinates,
            annotations=True,  # Enable node annotations for route resolution
        )

        # Get route nodes from matching
        route_nodes = matching.get_route_nodes()

        # Resolve segments using route context
        segment_results: list[Optional[SegmentInfo]] = [None] * len(tracepoints)

        if self._segment_resolver is not None and route_nodes:
            # Get matched coordinates for observations
            matched_coords = []
            for tp in tracepoints:
                if tp.matched:
                    matched_coords.append((tp.location[1], tp.location[0]))  # (lat, lon)
                else:
                    matched_coords.append((0.0, 0.0))

            # Resolve using route-constrained method
            observation_indices = [i for i, tp in enumerate(tracepoints) if tp.matched]
            results = self._segment_resolver.resolve_with_route(
                route_nodes,
                matched_coords,
                observation_indices,
            )

            for idx, seg in results.items():
                segment_results[idx] = seg

        # Fill in unmatched with spatial fallback
        for i, tp in enumerate(tracepoints):
            if not tp.matched and segment_results[i] is None:
                segment_results[i] = self._segment_resolver._resolve_spatial(
                    sorted_obs[i].latitude,
                    sorted_obs[i].longitude,
                ) if self._segment_resolver else None

        # Build response observations
        matched_observations = []
        matched_count = 0
        unmatched_count = 0
        resolution_stats = {}

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

                # Get resolution status
                resolution_status = None
                if segment:
                    status_str = segment.status.value if hasattr(segment.status, 'value') else str(segment.status)
                    resolution_stats[status_str] = resolution_stats.get(status_str, 0) + 1

                    if segment.status == ResolverStatus.ROUTE_NODE_PAIR:
                        resolution_status = ResolutionStatus.ROUTE_NODE_PAIR
                    elif segment.status == ResolverStatus.ROUTE_SPATIAL:
                        resolution_status = ResolutionStatus.ROUTE_SPATIAL
                    elif segment.status == ResolverStatus.GLOBAL_SPATIAL:
                        resolution_status = ResolutionStatus.GLOBAL_SPATIAL
                    elif segment.status == ResolverStatus.AMBIGUOUS:
                        resolution_status = ResolutionStatus.AMBIGUOUS
                    elif segment.status == ResolverStatus.UNRESOLVED:
                        resolution_status = ResolutionStatus.UNRESOLVED

                matched_obs = MatchedObservation(
                    observation_id=obs.observation_id,
                    timestamp=obs.timestamp,
                    raw_latitude=obs.latitude,
                    raw_longitude=obs.longitude,
                    matched=True,
                    matched_latitude=tp.location[1],
                    matched_longitude=tp.location[0],
                    road_segment_id=segment.segment_id if segment else None,
                    osm_way_id=segment.osm_way_id if segment else None,
                    direction=segment.direction if segment else None,
                    confidence=matching.confidence if i == 0 else None,
                    distance_to_road_m=tp.distance,
                    resolution_status=resolution_status,
                )

            matched_observations.append(matched_obs)

        # Log statistics
        if matched_count > 0:
            logger.info(
                f"Matched {matched_count}/{len(sorted_obs)} observations, "
                f"resolution: {resolution_stats}"
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
