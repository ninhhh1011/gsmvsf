"""Matching migration preserves actual matched positions and explicit failures."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.map_matching.engine import Matching, Tracepoint, MapMatchingEngineUnavailableError
from backend.app.services.map_matching.models import GPSObservation, MapMatchRequest
from backend.app.services.map_matching.service import MapMatchingService
from backend.app.services.map_matching.segment_resolver import RouteConstrainedSegmentResolver
from backend.app.services.realtime.state import reset_state_store


@pytest.mark.asyncio
async def test_service_resolves_actual_matched_point_and_way():
    point = Tracepoint(0, (105.8, 21), 2, "", True, 123, 90)
    engine = MagicMock()
    engine.match = AsyncMock(return_value=(Matching(.98, 100, 10, "encoded", [point, point], "car"), [point, point]))
    resolver = MagicMock()
    resolver.resolve_matched.return_value = None
    obs = [GPSObservation(observation_id=str(i), trajectory_id="x", trip_id="external", timestamp=str(i), latitude=21.01, longitude=105.81) for i in range(2)]
    response = await MapMatchingService(engine, resolver).match_trajectory(
        MapMatchRequest(trajectory_id="x", trip_id="external", vehicle_category="EV_CAR", observations=obs))
    resolver.resolve_matched.assert_called_with(21, 105.8, 123, 90)
    assert response.observations[0].matched_latitude == 21
    assert response.observations[0].osm_way_id == 123
    assert response.observations[0].road_segment_id is None
    assert response.profile == "car"


def test_resolver_uses_way_and_travel_orientation():
    resolver = RouteConstrainedSegmentResolver("unused")
    conn = MagicMock()
    resolver._conn = conn
    conn.closed = False
    cursor = conn.cursor.return_value.__enter__.return_value
    # F/R dataset geometries have the same coordinate order; reverse adds 180 degrees.
    cursor.fetchall.return_value = [
        ("way_0_F", "a", "b", 123, "FORWARD", 1., 90.),
        ("way_0_R", "b", "a", 123, "REVERSE", 1., 270.),
    ]
    result = resolver.resolve_matched(21, 105.8, 123, 270)
    assert result.segment_id == "way_0_R"
    assert 123 in cursor.execute.call_args.args[1]


@pytest.mark.asyncio
async def test_realtime_uses_matched_coordinates_and_explicit_outage(client, monkeypatch):
    from backend.app.api.v1 import realtime
    from backend.app.services.map_matching.models import MapMatchResponse, MatchedObservation
    reset_state_store()
    result = MapMatchResponse(trajectory_id="D0001", trip_id="realtime", total_observations=3, matched_count=3, unmatched_count=0,
        overall_confidence=.9, observations=[MatchedObservation(observation_id="2", timestamp="earlier", raw_latitude=21, raw_longitude=105.8, matched=True, matched_latitude=21, matched_longitude=105.8), MatchedObservation(observation_id="2", timestamp="t", raw_latitude=21.002,
        raw_longitude=105.8, matched=True, matched_latitude=21.003, matched_longitude=105.801,
        road_segment_id="123_0_F", osm_way_id=123, direction="FORWARD")])
    monkeypatch.setattr(realtime, "_call_map_match", AsyncMock(return_value=(result, 5)))
    start = datetime(2026, 9, 1)
    for i in range(3):
        r = await client.post('/api/v1/drivers/D0001/location', json={"observation_id":str(i), "latitude":21+i*.001,
            "longitude":105.8,"timestamp":(start+timedelta(seconds=i*10)).isoformat()})
    assert r.json()["matched_position"]["latitude"] == 21.003
    assert r.json()["matched_position"]["road_segment_id"] == "123_0_F"
    monkeypatch.setattr(realtime, "_call_map_match", AsyncMock(side_effect=MapMatchingEngineUnavailableError("offline")))
    r = await client.post('/api/v1/drivers/D0001/location', json={"latitude":21.004,"longitude":105.8,
        "timestamp":(start+timedelta(seconds=40)).isoformat()})
    assert r.json()["status"] == "ENGINE_UNAVAILABLE"
    reset_state_store()


@pytest.mark.asyncio
async def test_ambiguous_segment_identity_is_not_asserted():
    from backend.app.services.map_matching.segment_resolver import SegmentInfo, ResolutionStatus
    point = Tracepoint(0, (105.8,21), 2, "", True, 123, 90)
    engine = MagicMock()
    engine.match = AsyncMock(return_value=(Matching(.98,100,10,"encoded",[point,point],"car"),[point,point]))
    resolver = MagicMock()
    resolver.resolve_matched.return_value = SegmentInfo("123_0_F","a","b",123,"FORWARD",1,ResolutionStatus.AMBIGUOUS)
    obs = [GPSObservation(observation_id=str(i),trajectory_id="x",trip_id="external",timestamp=str(i),latitude=21,longitude=105.8) for i in range(2)]
    result = await MapMatchingService(engine,resolver).match_trajectory(MapMatchRequest(trajectory_id="x",trip_id="external",vehicle_category="EV_CAR",observations=obs))
    assert result.observations[0].road_segment_id is None
    assert result.observations[0].direction is None
    assert result.observations[0].osm_way_id == 123
