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
            resolution_status=ResolutionStatus.ROUTE_NODE_PAIR,
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

    def test_resolution_status_enum(self):
        """Test resolution status enum values."""
        assert ResolutionStatus.ROUTE_NODE_PAIR.value == "ROUTE_NODE_PAIR"
        assert ResolutionStatus.ROUTE_SPATIAL.value == "ROUTE_SPATIAL"
        assert ResolutionStatus.GLOBAL_SPATIAL.value == "GLOBAL_SPATIAL"
        assert ResolutionStatus.AMBIGUOUS.value == "AMBIGUOUS"
        assert ResolutionStatus.UNRESOLVED.value == "UNRESOLVED"


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
            status=ResolutionStatus.ROUTE_NODE_PAIR,
        )
        assert seg.segment_id == "897474222_0_F"
        assert seg.direction == "FORWARD"
        assert seg.distance_m == 5.0
        assert seg.status == ResolutionStatus.ROUTE_NODE_PAIR

    def test_resolution_status_values(self):
        """Test ResolutionStatus enum values."""
        from backend.app.services.map_matching.segment_resolver import ResolutionStatus

        assert ResolutionStatus.ROUTE_NODE_PAIR.value == "ROUTE_NODE_PAIR"
        assert ResolutionStatus.ROUTE_SPATIAL.value == "ROUTE_SPATIAL"
        assert ResolutionStatus.GLOBAL_SPATIAL.value == "GLOBAL_SPATIAL"
        assert ResolutionStatus.AMBIGUOUS.value == "AMBIGUOUS"
        assert ResolutionStatus.UNRESOLVED.value == "UNRESOLVED"


class TestMapMatchingService:
    """Test map matching service."""

    def test_service_init_graphhopper(self):
        from backend.app.services.map_matching.service import MapMatchingService
        from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter
        adapter = GraphHopperMapMatchingAdapter("http://localhost:8989")
        assert MapMatchingService(adapter).engine is adapter
