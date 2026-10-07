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
