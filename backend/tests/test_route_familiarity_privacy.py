import hashlib
import hmac

import pytest

from backend.app.api.v1.ranking import verify_driver_identity
from backend.app.services.ranking.models import FamiliarityExplanation, RecommendationResult


def test_driver_identity_signature_binds_exact_driver_id_and_requires_lowercase_hex():
    secret = "s" * 32
    signature = hmac.new(secret.encode(), b"driver-1", hashlib.sha256).hexdigest()

    assert verify_driver_identity("driver-1", signature, secret)
    assert not verify_driver_identity("driver-2", signature, secret)
    assert not verify_driver_identity("driver-1", signature.upper(), secret)
    assert not verify_driver_identity("driver-1", "", secret)


def test_familiarity_explanation_has_explicit_private_safe_fields():
    explanation = FamiliarityExplanation(
        status="AVAILABLE", resolution=11, personal_adherence=0.75,
        personal_adherence_pct=75.0, personal_trip_count=2,
        personal_history_trip_count=3, community_adherence=None,
        community_trip_count=None, community_driver_count=None,
        confidence=0.5, recommended_distance_m=1200, shared_distance_m=900,
        penalty_s=3.75, history_truncated=False, route_cells=["8b..."],
    )
    dumped = explanation.model_dump(mode="json")
    assert dumped["resolution"] == 11
    assert dumped["community_driver_count"] is None
    assert "driver_id" not in dumped and "trip_id" not in dumped


@pytest.mark.parametrize("signature", [None, "0" * 64])
def test_invalid_identity_signature_is_not_accepted(signature):
    assert not verify_driver_identity("driver-1", signature, "s" * 32)


@pytest.mark.asyncio
async def test_recommend_requires_hmac_only_when_feature_is_enabled(client, app, monkeypatch):
    from backend.app.config import settings

    app.state.recommendation_workflow = object()
    monkeypatch.setattr(settings, "route_familiarity_identity_secret", "s" * 32)
    monkeypatch.setattr(settings, "enable_route_familiarity", True)
    body = {"context": {"vehicle_id": "vehicle", "driver_id": "driver-1",
                        "timestamp": "2026-10-07T00:00:00Z"}}
    assert (await client.post("/api/v1/recommend", json=body)).status_code == 401
    wrong = hmac.new(b"s" * 32, b"driver-2", hashlib.sha256).hexdigest()
    assert (await client.post("/api/v1/recommend", json=body,
                              headers={"X-Driver-Identity-Signature": wrong})).status_code == 403
    monkeypatch.setattr(settings, "enable_route_familiarity", False)
    # The request proceeds past identity verification with the feature disabled.
    response = await client.post("/api/v1/recommend", json=body)
    assert response.status_code != 401 and response.status_code != 403


@pytest.mark.asyncio
async def test_staged_rank_response_omits_familiarity(client, app):
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.app.services.demand.models import EnergyServiceRequest
    from backend.app.services.ranking.models import RankingPolicy

    result = RecommendationResult(
        candidate_search_id="search", request_time=datetime.now(UTC), has_recommendation=False,
        recommended_station_id=None, recommended_service_type=None, ranked_candidates=[],
        eligible_count=0, policy=RankingPolicy(),
        energy_context=EnergyServiceRequest(service_request_id="s", vehicle_id="v",
            timestamp=datetime.now(UTC), need_service=False, request_valid=True,
            request_source="AUTO_DETECTED", allowed_service_types=[],
            reason_code="SUFFICIENT_SOC_RANGE"),
        degraded=False, degraded_reasons=[], reason="NO_ELIGIBLE_CANDIDATES",
    )
    workflow = SimpleNamespace(repository=SimpleNamespace(get_search=AsyncMock(return_value=object())),
                               ranking=SimpleNamespace(recommend=AsyncMock(return_value=result)))
    app.state.recommendation_workflow = workflow
    response = await client.post("/api/v1/ranking", json={"candidate_search_id": "search"})
    assert response.status_code == 200
    assert "familiarity" not in response.json()


@pytest.mark.asyncio
async def test_recommend_returns_private_safe_explanation_and_selected_route_cells(client, app, monkeypatch):
    from types import SimpleNamespace

    from backend.app.config import settings
    from backend.app.services.ranking.service import RankingService
    from backend.app.services.route_familiarity.service import FamiliarityAssessment
    from backend.tests.test_week4_ranking import HistoryResolver, candidate, evidence, queue, station, traffic

    driver_id = "private-driver-246"
    trip_id = "private-trip-810"
    secret = "s" * 32
    signature = hmac.new(secret.encode(), driver_id.encode(), hashlib.sha256).hexdigest()
    monkeypatch.setattr(settings, "route_familiarity_identity_secret", secret)
    monkeypatch.setattr(settings, "enable_route_familiarity", True)

    class Evaluator:
        lookback = SimpleNamespace(days=7)

        async def assess_many(self, _driver_id, signatures, _as_of):
            assert _driver_id == driver_id
            return {key: FamiliarityAssessment(
                "AVAILABLE", personal_adherence=0.75, personal_trip_count=2,
                personal_history_trip_count=3, community_adherence=None,
                community_trip_count=None, community_driver_count=None,
                confidence=0.5, recommended_distance_m=1200,
                shared_distance_m=900, penalty_s=3.75, history_truncated=False)
                for key in signatures}

    signatures = {("S001", "CHARGING"): SimpleNamespace(cells=("cell-a", "cell-b")),
                  ("S002", "CHARGING"): SimpleNamespace(cells=("cell-c",))}
    ranker = RankingService(HistoryResolver(station(), queue(), station("S002"), queue("S002"), traffic()),
                            familiarity_evaluator=Evaluator())
    saved = evidence([candidate(), candidate("S002", duration=150)])
    saved = saved.model_copy(update={"energy_request": saved.energy_request.model_copy(
        update={"driver_id": driver_id, "trip_id": trip_id})})

    async def recommend(*_args, **_kwargs):
        return await ranker.recommend(saved,
            candidate_signatures=signatures, include_familiarity=True)

    app.state.recommendation_workflow = SimpleNamespace(repository=None, recommend=recommend)
    response = await client.post("/api/v1/recommend", json={
        "requested_service": "CHARGING",
        "context": {"vehicle_id": "V0001", "driver_id": driver_id,
                    "trip_id": trip_id, "timestamp": "2026-10-07T00:00:00Z",
                    "current_soc_pct": 20, "estimated_remaining_range_km": 50,
                    "raw_latitude": 21.03, "raw_longitude": 105.85},
    }, headers={"X-Driver-Identity-Signature": signature})

    assert response.status_code == 200, response.text
    body = response.json()
    explanation = body["familiarity"]
    assert explanation["status"] == "AVAILABLE"
    assert explanation["personal_adherence_pct"] == 75.0
    assert explanation["personal_history_trip_count"] == 3
    assert explanation["penalty_s"] == 3.75
    assert explanation["route_cells"] == ["cell-a", "cell-b"]
    assert explanation["community_adherence"] is None
    assert explanation["community_trip_count"] is None
    assert explanation["community_driver_count"] is None
    assert body["ranked_candidates"][0]["familiarity"]["route_cells"] == []
    assert body["ranked_candidates"][1]["familiarity"]["route_cells"] == []
    serialized_explanation = str([explanation, *(c["familiarity"] for c in body["ranked_candidates"])])
    assert driver_id not in serialized_explanation
    assert trip_id not in serialized_explanation
    assert signature not in response.text
