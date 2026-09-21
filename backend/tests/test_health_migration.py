from unittest.mock import AsyncMock
import pytest
from backend.app.api.v1 import health

@pytest.mark.asyncio
@pytest.mark.parametrize("routing,database,expected", [(True,True,200),(False,True,503),(True,False,503)])
async def test_readiness_requires_both_dependencies(client, monkeypatch, routing, database, expected):
    monkeypatch.setattr(health, "dependencies_ready", AsyncMock(return_value={"graphhopper":routing,"postgis":database}))
    assert (await client.get("/readiness")).status_code == expected
    assert (await client.get("/health")).status_code == 200
