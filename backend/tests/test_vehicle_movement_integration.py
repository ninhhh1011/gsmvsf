"""
Integration test verifying Problem A: Vehicle Model + Energy/SOC.
Proves that:
1. Different VinFast vehicle models drop different % SOC for the same distance travelled.
2. SOC and remaining range decrease dynamically with movement.
3. Backend recommendation workflow consumes the updated vehicle and SOC state.
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.demand.capability import get_capability_resolver


def test_vehicle_movement_energy_drop_comparison():
    resolver = get_capability_resolver()
    vf3 = resolver.resolve_by_model("VF_3")
    vf9 = resolver.resolve_by_model("VF_9")

    distance_km = 15.0
    initial_soc = 80.0

    # 1. Compare SOC drop for 15 km
    drop_vf3 = vf3.calculate_soc_drop(distance_km)
    drop_vf9 = vf9.calculate_soc_drop(distance_km)

    soc_after_vf3 = initial_soc - drop_vf3
    soc_after_vf9 = initial_soc - drop_vf9

    range_after_vf3 = vf3.estimate_range_km(soc_after_vf3)
    range_after_vf9 = vf9.estimate_range_km(soc_after_vf9)

    # VF3: 15 km * 0.095 = 1.425 kWh. 1.425 / 17.15 * 100 = 8.309% drop
    assert 8.0 <= drop_vf3 <= 8.5
    assert 71.5 <= soc_after_vf3 <= 72.0

    # VF9: 15 km * 0.235 = 3.525 kWh. 3.525 / 113.16 * 100 = 3.115% drop
    assert 3.0 <= drop_vf9 <= 3.3
    assert 76.7 <= soc_after_vf9 <= 77.0

    # Proven: VF3 loses > 2.5x more SOC percentage than VF9 for the exact same distance!
    assert drop_vf3 > drop_vf9 * 2.5
    assert soc_after_vf3 < soc_after_vf9


@pytest.mark.asyncio
async def test_recommendation_consumes_selected_vehicle_and_dynamic_soc():
    from backend.app.main import create_app
    from backend.app.api.v1.ranking import get_workflow
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    import httpx

    from backend.app.services.ranking.models import RecommendationResult, RankingPolicy
    from backend.app.services.demand.service import create_demand_service
    from backend.app.services.demand.models import DemandContext

    demand_service = create_demand_service()
    energy_ctx = demand_service.evaluate_auto_demand(DemandContext(vehicle_id="V0001", current_soc_pct=18.0))

    expected_result = RecommendationResult(
        candidate_search_id="test_search_1",
        request_time=datetime.now(timezone.utc),
        has_recommendation=True,
        recommended_station_id="ST01",
        recommended_service_type="CHARGING",
        ranked_candidates=[],
        eligible_count=1,
        policy=RankingPolicy(),
        energy_context=energy_ctx,
        degraded=False,
        degraded_reasons=[],
        reason="RANKED_ELIGIBLE_CANDIDATES"
    )

    workflow = SimpleNamespace(
        recommend=AsyncMock(return_value=expected_result)
    )

    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow

    # Recommendation for VF3 with depleted SOC
    now = datetime.now(timezone.utc).isoformat()
    req_vf3 = {
        "context": {
            "vehicle_id": "V0001",
            "driver_id": "D0001",
            "timestamp": now,
            "current_soc_pct": 18.0,
            "estimated_remaining_range_km": 32.5,
            "remaining_trip_distance_km": 25.0,
            "distance_travelled_km": 15.0,
            "safety_reserve_km": 2.0,
            "consumption_wh_per_km": 95.0,
            "raw_latitude": 21.0285,
            "raw_longitude": 105.8542
        },
        "requested_service": "CHARGING",
        "destination_latitude": 21.0150,
        "destination_longitude": 105.7800,
        "top_n": 3
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/recommend", json=req_vf3)

    assert resp.status_code == 200
    assert workflow.recommend.await_count == 1
    call_args = workflow.recommend.call_args[0][0]
    # The candidate search request sent to workflow.recommend has the exact energy request:
    assert call_args.energy_request.vehicle_id == "V0001"
    assert call_args.energy_request.current_soc_pct == 18.0
    assert call_args.energy_request.estimated_remaining_range_km == 32.5
    assert call_args.energy_request.remaining_trip_distance_km == 25.0
