"""Integration tests for Week 5.5 Demo UI serving and static assets."""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app


@pytest.mark.asyncio
async def test_demo_page_serving():
    """Verify /demo and /demo/ return HTML response."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/demo")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "VinFast" in resp.text
        assert 'id="map"' in resp.text

        resp_slash = await client.get("/demo/")
        assert resp_slash.status_code == 200


@pytest.mark.asyncio
async def test_demo_static_assets():
    """Verify static stylesheets and javascript modules are served correctly."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Stylesheet
        css_resp = await client.get("/demo/static/style.css")
        assert css_resp.status_code == 200
        assert "--brand-teal" in css_resp.text

        # JS modules
        for mod in ["api.js", "map.js", "components.js", "driver_mode.js", "sim_mode.js", "replay.js", "app.js"]:
            js_resp = await client.get(f"/demo/static/js/{mod}")
            assert js_resp.status_code == 200, f"Failed to fetch {mod}"


@pytest.mark.asyncio
async def test_demo_catalogs():
    """Verify demo data presets match canonical Dataset V1 counts."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Stations catalog
        st_resp = await client.get("/demo/static/data/stations.json")
        assert st_resp.status_code == 200
        stations = st_resp.json()
        assert len(stations) == 30
        assert any(s["station_id"] == "S001" for s in stations)

        # Vehicles catalog
        v_resp = await client.get("/demo/static/data/vehicles.json")
        assert v_resp.status_code == 200
        vehicles = v_resp.json()
        assert len(vehicles) == 60
        assert any(v["vehicle_id"] == "V0001" for v in vehicles)

        # Scenarios
        sc_resp = await client.get("/demo/static/data/scenarios.json")
        assert sc_resp.status_code == 200
        scenarios = sc_resp.json()
        assert len(scenarios) == 8

        # Trips
        tr_resp = await client.get("/demo/static/data/trips.json")
        assert tr_resp.status_code == 200
        trips = tr_resp.json()
        assert len(trips) == 10
