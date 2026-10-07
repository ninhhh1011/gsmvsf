from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.app.config import settings
from backend.app.api.v1.route_familiarity import _read_bounded_body
from backend.app.services.snapshots.models import StateError


@pytest.mark.asyncio
async def test_oversized_stream_stops_before_reading_later_chunks():
    consumed_later_chunk = False

    class Request:
        async def stream(self):
            nonlocal consumed_later_chunk
            yield b"x" * 105_001
            consumed_later_chunk = True
            yield b"later"

    with pytest.raises(StateError) as error:
        await _read_bounded_body(Request(), 105_000)
    assert error.value.status == 422
    assert not consumed_later_chunk


async def test_ingestion_auth_and_payload_limits(client, app, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_ingestion_token", "trusted")
    monkeypatch.setattr(settings, "enable_route_familiarity", True)
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
    monkeypatch.setattr(settings, "enable_route_familiarity", True)
    response = await client.post("/api/v1/internal/route-familiarity/routes", json={},
                                 headers={"X-Ingestion-Token": "trusted"})
    assert response.status_code == 503

async def test_disabled_ingestion_authenticates_then_returns_disabled_without_storage(client, app, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_ingestion_token", "trusted")
    monkeypatch.setattr(settings, "enable_route_familiarity", False)
    service = AsyncMock()
    app.state.route_history_ingestion = service
    assert (await client.post("/api/v1/internal/route-familiarity/routes", json={})).status_code == 401
    response = await client.post("/api/v1/internal/route-familiarity/routes", content=b"not json",
                                 headers={"X-Ingestion-Token": "trusted"})
    assert response.status_code == 503
    assert response.json()["error_code"] == "ROUTE_FAMILIARITY_DISABLED"
    service.ingest.assert_not_awaited()


def test_compose_passes_route_familiarity_opt_in_to_both_api_services():
    from pathlib import Path
    import re

    compose = Path("docker-compose.yml").read_text()
    for service_name in ("api_1", "api_2"):
        match = re.search(rf"(?ms)^  {service_name}:\n(.*?)(?=^  [\w-]+:|\Z)", compose)
        assert match, f"missing Compose service {service_name}"
        service = match.group(1)
        assert "ENABLE_ROUTE_FAMILIARITY=${ENABLE_ROUTE_FAMILIARITY:-false}" in service
        assert "ROUTE_FAMILIARITY_IDENTITY_SECRET=${ROUTE_FAMILIARITY_IDENTITY_SECRET:-}" in service


@pytest.mark.asyncio
async def test_lifespan_skips_route_history_objects_when_disabled(monkeypatch):
    from fastapi import FastAPI
    import asyncpg
    import httpx
    from redis.asyncio import Redis

    from backend.app.core import lifespan as lifecycle
    from backend.app.services.route_familiarity import ingestion, repository

    class Resource:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(settings, "enable_route_familiarity", False)
    monkeypatch.setattr(settings, "enable_realtime_simulator", False)
    monkeypatch.setattr(asyncpg, "create_pool", lambda *args, **kwargs: Resource())
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: Resource())
    monkeypatch.setattr(Redis, "from_url", lambda *args, **kwargs: Resource())
    monkeypatch.setattr(repository, "RouteHistoryRepository",
                        lambda *args, **kwargs: pytest.fail("repository constructed while disabled"))
    monkeypatch.setattr(ingestion, "RouteHistoryIngestion",
                        lambda *args, **kwargs: pytest.fail("ingestion constructed while disabled"))
    app = FastAPI()
    async with lifecycle.lifespan(app):
        assert app.state.route_history_repository is None
        assert app.state.route_history_ingestion is None
