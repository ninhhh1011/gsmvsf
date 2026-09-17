"""Map matching service."""
import logging
from pathlib import Path
from typing import Optional

from backend.app.services.map_matching.models import (
    GPSObservation,
    MapMatchRequest,
    MapMatchResponse,
    MatchedObservation,
)
from backend.app.services.map_matching.osrm_adapter import (
    OsrmMapMatchingAdapter,
    OsrmAdapterError,
    OsrmNoMatchError,
)
from backend.app.services.map_matching.segment_resolver import CoordinateSegmentResolver

logger = logging.getLogger(__name__)


class MapMatchingService:
    """
    Service for matching GPS observations to road segments.

    Runtime flow:
    1. Receive GPS observations
    2. Call OSRM Match for the trace
    3. Resolve segment identity from matched coordinates
    4. Return normalized response
    """

    def __init__(
        self,
        osrm_adapter: OsrmMapMatchingAdapter,
        segment_resolver: Optional[CoordinateSegmentResolver] = None,
    ):
        """
        Initialize the map matching service.

        Args:
            osrm_adapter: OSRM adapter instance
            segment_resolver: Optional segment resolver (lazy-loaded if not provided)
        """
        self.osrm_adapter = osrm_adapter
        self._segment_resolver = segment_resolver

    @property
    def segment_resolver(self) -> Optional[CoordinateSegmentResolver]:
        """Lazy-load segment resolver."""
        if self._segment_resolver is None:
            # Will be set by the module or during initialization
            logger.warning("Segment resolver not configured")
        return self._segment_resolver

    def _derive_direction(
        self,
        matched_lat: float,
        matched_lon: float,
        next_lat: Optional[float],
        next_lon: Optional[float],
        segment_direction: Optional[str],
    ) -> Optional[str]:
        """
        Derive travel direction.

        Args:
            matched_lat: Current matched latitude
            matched_lon: Current matched longitude
            next_lat: Next matched latitude (if available)
            next_lon: Next matched longitude (if available)
            segment_direction: Direction from road segment data

        Returns:
            FORWARD, BACKWARD, or None if cannot determine
        """
        # If we have consecutive matched points, use movement direction
        if next_lat is not None and next_lon is not None:
            # Calculate bearing from current to next
            import math

            dlat = next_lat - matched_lat
            dlon = next_lon - matched_lon

            # If movement is negligible, use segment direction
            if abs(dlat) < 1e-6 and abs(dlon) < 1e-6:
                return segment_direction

            # Calculate approximate bearing (0-360 degrees)
            bearing = math.degrees(math.atan2(dlon, dlat))
            if bearing < 0:
                bearing += 360

            # Approximate: 0-180 is forward, 180-360 is backward
            # This is a simplification; proper derivation needs road direction
            return "FORWARD"  # Placeholder

        return segment_direction

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

        # Build response observations
        matched_observations = []
        matched_count = 0
        unmatched_count = 0

        for i, obs in enumerate(sorted_obs):
            tp = tracepoints[i] if i < len(tracepoints) else None

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

                # Resolve segment if resolver available
                road_segment_id = None
                osm_way_id = None
                direction = None

                if self.segment_resolver is not None:
                    seg = self.segment_resolver.resolve(tp.location[1], tp.location[0])
                    if seg:
                        road_segment_id = seg.segment_id
                        osm_way_id = seg.osm_way_id
                        direction = seg.direction

                # Derive direction from trajectory movement
                if i < len(tracepoints) - 1:
                    next_tp = tracepoints[i + 1]
                    if next_tp and next_tp.matched:
                        direction = self._derive_direction(
                            tp.location[1],
                            tp.location[0],
                            next_tp.location[1],
                            next_tp.location[0],
                            direction,
                        )

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
                )

            matched_observations.append(matched_obs)

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
