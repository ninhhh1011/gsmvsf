"""Tests for health endpoints."""
import pytest


@pytest.mark.asyncio
async def test_health(client):
    """Test GET /api/v1/health returns healthy."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    """Test GET / returns app info."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "app" in data
    assert "version" in data
