from datetime import UTC, datetime
from unittest.mock import AsyncMock

from backend.app.config import settings


async def test_ingestion_auth_and_payload_limits(client, app, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_ingestion_token", "trusted")
    service = AsyncMock()
    service.ingest.return_value = (object(), True)
    app.state.route_history_ingestion = service
    body = {"driver_id": "d", "trip_id": "t", "completed_at": datetime.now(UTC).isoformat(),
            "polyline": "???S"}
    assert (await client.post("/api/v1/internal/route-familiarity/routes", json=body)).status_code == 401
    assert (await client.post("/api/v1/internal/route-familiarity/routes", json=body,
                              headers={"X-Ingestion-Token": "wrong"})).status_code == 403
    response = await client.post("/api/v1/internal/route-familiarity/routes", json=body,
                                 headers={"X-Ingestion-Token": "trusted"})
    assert response.status_code == 201
    oversized = await client.post("/api/v1/internal/route-familiarity/routes",
                                  json={**body, "polyline": "x" * 100001},
                                  headers={"X-Ingestion-Token": "trusted"})
    assert oversized.status_code == 422


async def test_ingestion_returns_503_without_service(client, app, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_ingestion_token", "trusted")
    response = await client.post("/api/v1/internal/route-familiarity/routes", json={},
                                 headers={"X-Ingestion-Token": "trusted"})
    assert response.status_code == 503
