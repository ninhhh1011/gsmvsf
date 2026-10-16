"""Exercise the actual Driver serializer against the actual FastAPI response."""
import json
import shutil
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app


DRIVER_PROBE = """
import fs from 'node:fs';
import { DriverModeController } from './backend/app/static/demo/js/ui/driver_controller.js';
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let payload, banner;
const controller = new DriverModeController({compareRoutes: async body => {
    payload = body; return input.response;
}}, {}, {bindings: {updateH3ComparisonBanner: data => {banner = data;}}});
controller._h3Enabled = true;
controller.h3Mode = 'COMPARISON';
controller.offlineProposedGeometry = input.coordinates;
controller.actualTrajectoryCoords = input.coordinates;
controller.currentVehicle = {vehicle_model: 'VF_3'};
await controller.refreshRouteComparison();
console.log(JSON.stringify({payload, banner}));
"""


def driver_call(coordinates, response):
    process = subprocess.run(["node", "--input-type=module", "-e", DRIVER_PROBE],
                             input=json.dumps(dict(coordinates=coordinates, response=response)),
                             capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(process.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required for cross-language contract")
@pytest.mark.asyncio
async def test_driver_payload_and_banner_round_trip_through_real_api():
    coordinates = [[21, 105.8], [21.002, 105.8]]
    neutral = dict(shared_pct_on_proposed=0, shared_pct_on_actual=0, shared_distance_m=0,
                   shared_cells=[], proposed_cells=[], actual_cells=[])
    outgoing = driver_call(coordinates, neutral)["payload"]
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        response = await client.post("/api/v1/routing/compare-routes", json=outgoing)
    assert response.status_code == 200, response.text
    rendered = driver_call(coordinates, response.json())["banner"]
    assert rendered["visible"] is True
    assert rendered["proposedText"] == "Đề xuất: 100.0%"
    assert rendered["actualText"] == "GPS quan sát: 100.0%"
    assert rendered["sharedDistText"] == "Chung: 0.2 km"
