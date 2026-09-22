from unittest.mock import AsyncMock
import pytest
from backend.app.api.v1 import health

@pytest.mark.asyncio
@pytest.mark.parametrize("routing,database,redis,expected", [
    (True, True, True, 200),
    (False, True, True, 503),
    (True, False, True, 503),
    (True, True, False, 503),  # Redis now required
])
async def test_readiness_requires_dependencies(client, monkeypatch, routing, database, redis, expected):
    monkeypatch.setattr(health, "dependencies_ready", AsyncMock(
        return_value={"graphhopper": routing, "postgis": database, "redis": redis}
    ))
    assert (await client.get("/readiness")).status_code == expected
    assert (await client.get("/health")).status_code == 200
