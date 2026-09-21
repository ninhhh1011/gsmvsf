"""Shared batch/realtime matching pipeline; no engine-specific business branching."""
from backend.app.services.graphhopper import resolve_vehicle_category
from backend.app.services.map_matching.engine import MapMatchingEngine, MapMatchingEngineError
from backend.app.services.map_matching.models import MapMatchResponse, MatchedObservation, ResolutionStatus


class MapMatchingService:
    def __init__(self, engine: MapMatchingEngine, segment_resolver=None):
        self.engine = engine
        self._segment_resolver = segment_resolver

    async def match_trajectory(self, request):
        category = resolve_vehicle_category(request.vehicle_category, request.vehicle_id, request.trip_id)
        observations = sorted(request.observations, key=lambda obs: obs.timestamp)
        matching, points = await self.engine.match(
            [(obs.longitude, obs.latitude) for obs in observations], vehicle_category=category)
        if len(points) != len(observations):
            raise MapMatchingEngineError("Engine observation count mismatch")
        results = []
        for obs, point in zip(observations, points):
            segment = None
            if point.matched and self._segment_resolver is not None:
                segment = self._segment_resolver.resolve_matched(
                    point.location[1], point.location[0], point.osm_way_id, point.bearing)
            ambiguous = point.matched and (point.bearing is None or
                (segment is not None and segment.status.value == "AMBIGUOUS"))
            results.append(MatchedObservation(
                observation_id=obs.observation_id, timestamp=obs.timestamp,
                raw_latitude=obs.latitude, raw_longitude=obs.longitude, matched=point.matched,
                matched_latitude=point.location[1] if point.matched else None,
                matched_longitude=point.location[0] if point.matched else None,
                road_segment_id=segment.segment_id if segment and not ambiguous else None,
                osm_way_id=point.osm_way_id if ambiguous else (segment.osm_way_id if segment else point.osm_way_id),
                direction=segment.direction if segment and not ambiguous else None,
                confidence=max(0, 1 - point.distance / 100) if point.matched else None,
                distance_to_road_m=point.distance if point.matched else None,
                resolution_status=ResolutionStatus.AMBIGUOUS if ambiguous else (ResolutionStatus(segment.status.value) if segment else ResolutionStatus.UNRESOLVED),
                null_reason=point.null_reason,
            ))
        count = sum(result.matched for result in results)
        return MapMatchResponse(trajectory_id=request.trajectory_id, trip_id=request.trip_id,
            total_observations=len(results), matched_count=count, unmatched_count=len(results)-count,
            observations=results, overall_confidence=matching.confidence,
            trace_geometry=matching.geometry, profile=matching.profile)
