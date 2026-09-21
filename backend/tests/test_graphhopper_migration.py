"""Migration contracts: actual OSS wire format and fail-closed configuration."""
import xml.etree.ElementTree as ET

import httpx
import pytest

from backend.app.config import Settings
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter


def test_no_engine_selection_settings():
    fields = Settings.model_fields
    assert not {"routing_engine", "map_matching_engine", "osrm_base_url", "osrm_data_path", "graphhopper_profile"} & fields.keys()


@pytest.mark.asyncio
@pytest.mark.parametrize("category,profile", [("EV_CAR", "car"), ("EV_MOTORBIKE", "motorcycle")])
async def test_matching_uses_gpx_profile_and_real_geometry(category, profile):
    def respond(request):
        assert request.url.params["profile"] == profile
        assert request.headers["content-type"] == "application/gpx+xml"
        assert len(ET.fromstring(request.content).findall(".//{*}trkpt")) == 3
        return httpx.Response(200, json={"paths": [{
            "distance": 104, "time": 12000,
            "points": {"type": "LineString", "coordinates": [[105, 21], [105.001, 21]]},
            "details": {"osm_way_id": [[0, 1, 123]]},
        }], "map_matching": {"distance": 104, "time": 12000}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        matching, points = await GraphHopperMapMatchingAdapter(client=client).match(
            [(105.0001, 21.00001), (105.0005, 21), (106, 22)], vehicle_category=category)
        assert [p.matched for p in points] == [True, True, False]
        assert points[0].location[1] == pytest.approx(21)
        assert points[0].osm_way_id == 123
        assert points[0].distance > 0
        assert matching.duration == 12
        assert 0 < matching.confidence < 1


@pytest.mark.asyncio
async def test_matching_rejects_malformed_success():
    from backend.app.services.map_matching.engine import MapMatchingEngineError
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"paths": [{"points": "invalid"}]}))) as client:
        with pytest.raises(MapMatchingEngineError):
            await GraphHopperMapMatchingAdapter(client=client).match([(105, 21), (105.001, 21)], vehicle_category="EV_CAR")


@pytest.mark.asyncio
async def test_revisited_path_does_not_invent_travel_direction():
    payload = {"paths": [{"distance":2000,"time":200000,
        "points":{"coordinates":[[105.8,21],[105.81,21],[105.8,21]]},
        "details":{"osm_way_id":[[0,2,123]]}}]}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200,json=payload))) as client:
        _, points = await GraphHopperMapMatchingAdapter(client=client).match(
            [(105.8,21),(105.805,21),(105.81,21),(105.805,21),(105.8,21)], vehicle_category="EV_CAR")
        assert points[-2].bearing is None
        assert points[-2].osm_way_id == 123
        assert points[-2].null_reason == "ambiguous_path_projection"
