"""Tests for map matching service."""
import pytest
from backend.app.services.map_matching.models import (
    GPSObservation,
    MapMatchRequest,
    MapMatchResponse,
    MatchedObservation,
    ResolutionStatus,
)


class TestModels:
    """Test Pydantic models."""

    def test_gps_observation_valid(self):
        """Test valid GPS observation."""
        obs = GPSObservation(
            observation_id="O00000001",
            trajectory_id="TRJ0001",
            trip_id="T0001",
            timestamp="2026-09-01T06:06:00+07:00",
            latitude=21.10379375096377,
            longitude=106.00239808563495,
            speed_kmh=21.46,
            heading_deg=29.48,
            accuracy_m=8.4,
        )
        assert obs.observation_id == "O00000001"
        assert obs.latitude == 21.10379375096377

    def test_gps_observation_optional_fields(self):
        """Test GPS observation with optional fields missing."""
        obs = GPSObservation(
            observation_id="O00000001",
            trajectory_id="TRJ0001",
            trip_id="T0001",
            timestamp="2026-09-01T06:06:00+07:00",
            latitude=21.10379375096377,
            longitude=106.00239808563495,
        )
        assert obs.speed_kmh is None
        assert obs.heading_deg is None
        assert obs.accuracy_m is None

    def test_map_match_request_valid(self):
        """Test valid map match request."""
        obs = GPSObservation(
            observation_id="O00000001",
            trajectory_id="TRJ0001",
            trip_id="T0001",
            timestamp="2026-09-01T06:06:00+07:00",
            latitude=21.10379375096377,
            longitude=106.00239808563495,
        )
        request = MapMatchRequest(
            trajectory_id="TRJ0001",
            trip_id="T0001",
            observations=[obs],
        )
        assert request.trajectory_id == "TRJ0001"
        assert len(request.observations) == 1

    def test_map_match_response(self):
        """Test map match response."""
        matched_obs = MatchedObservation(
            observation_id="O00000001",
            timestamp="2026-09-01T06:06:00+07:00",
            raw_latitude=21.10379375096377,
            raw_longitude=106.00239808563495,
            matched=True,
            matched_latitude=21.103802,
            matched_longitude=106.002381,
            road_segment_id="897474222_0_F",
            osm_way_id=897474222,
            direction="FORWARD",
            confidence=0.94,
            distance_to_road_m=1.97,
            resolution_status=ResolutionStatus.RESOLVED,
        )
        response = MapMatchResponse(
            trajectory_id="TRJ0001",
            trip_id="T0001",
            total_observations=1,
            matched_count=1,
            unmatched_count=0,
            observations=[matched_obs],
            overall_confidence=0.94,
        )
        assert response.matched_count == 1
        assert response.unmatched_count == 0
        assert response.observations[0].matched is True

    def test_unmatched_observation(self):
        """Test unmatched observation."""
        unmatched_obs = MatchedObservation(
            observation_id="O00000001",
            timestamp="2026-09-01T06:06:00+07:00",
            raw_latitude=21.10379375096377,
            raw_longitude=106.00239808563495,
            matched=False,
            null_reason="tracepoint_null",
        )
        assert unmatched_obs.matched is False
        assert unmatched_obs.null_reason == "tracepoint_null"
        assert unmatched_obs.matched_latitude is None


class TestOSRMAdapter:
    """Test OSRM adapter."""

    def test_tracepoint_from_osrm_null(self):
        """Test creating tracepoint from null OSRM data."""
        from backend.app.services.map_matching.osrm_adapter import Tracepoint

        tp = Tracepoint.from_osrm(None, index=0)
        assert tp.matched is False
        assert tp.null_reason == "null_tracepoint"
        assert tp.location == (0.0, 0.0)

    def test_tracepoint_from_osrm_valid(self):
        """Test creating tracepoint from valid OSRM data."""
        from backend.app.services.map_matching.osrm_adapter import Tracepoint

        data = {
            "waypoint_index": 0,
            "location": [106.002381, 21.103802],
            "distance": 1.975703,
            "name": "Test Street",
            "alternatives_count": 0,
        }
        tp = Tracepoint.from_osrm(data, index=0)
        assert tp.matched is True
        assert tp.location == (106.002381, 21.103802)
        assert tp.distance == 1.975703
        assert tp.name == "Test Street"

    def test_matching_from_osrm(self):
        """Test creating matching from OSRM data."""
        from backend.app.services.map_matching.osrm_adapter import Matching, Tracepoint

        data = {
            "confidence": 0.94,
            "distance": 140.1,
            "duration": 27.3,
            "geometry": "test_geometry",
        }
        tracepoints = [
            Tracepoint(0, (106.002381, 21.103802), 1.97, "", True),
        ]
        matching = Matching.from_osrm(data, tracepoints)
        assert matching.confidence == 0.94
        assert matching.distance == 140.1
        assert matching.duration == 27.3
        assert matching.geometry == "test_geometry"


class TestSegmentResolver:
    """Test segment resolver."""

    def test_segment_info(self):
        """Test SegmentInfo dataclass."""
        from backend.app.services.map_matching.segment_resolver import SegmentInfo, ResolutionStatus

        seg = SegmentInfo(
            segment_id="897474222_0_F",
            from_node_id="N0000001",
            to_node_id="N0000002",
            osm_way_id=897474222,
            direction="FORWARD",
            distance_m=5.0,
            status=ResolutionStatus.RESOLVED,
        )
        assert seg.segment_id == "897474222_0_F"
        assert seg.direction == "FORWARD"
        assert seg.distance_m == 5.0
        assert seg.status == ResolutionStatus.RESOLVED


class TestMapMatchingService:
    """Test map matching service."""

    def test_derive_direction_no_movement(self):
        """Test direction derivation with no movement data."""
        from backend.app.services.map_matching.service import MapMatchingService
        from backend.app.services.map_matching.osrm_adapter import OsrmMapMatchingAdapter

        adapter = OsrmMapMatchingAdapter("http://localhost:5000")
        service = MapMatchingService(adapter)

        # No movement data, use segment direction
        direction = service._derive_direction(
            prev_lat=None, prev_lon=None,
            curr_lat=21.103, curr_lon=106.002,
            next_lat=None, next_lon=None,
            segment=None,
        )
        assert direction is None  # No segment, no direction

    def test_service_init(self):
        """Test service initialization."""
        from backend.app.services.map_matching.service import MapMatchingService
        from backend.app.services.map_matching.osrm_adapter import OsrmMapMatchingAdapter

        adapter = OsrmMapMatchingAdapter("http://localhost:5000")
        service = MapMatchingService(adapter)
        assert service.osrm_adapter is adapter
