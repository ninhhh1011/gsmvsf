"""Tests for security features: simulate-tick auth and rate limiting."""
import pytest
from fastapi.testclient import TestClient

from backend.app.api.v1.ranking import router
from backend.app.config import settings
from backend.app.main import create_app


@pytest.fixture
def app():
    """Create test app with routers."""
    app = create_app()
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestSimulateTickAuth:
    """Test simulate-tick endpoint authentication."""

    def test_simulate_tick_without_auth_returns_401(self, client, monkeypatch):
        """POST /api/v1/snapshots/simulate-tick without token returns 401."""
        monkeypatch.setattr(settings, 'snapshot_ingestion_token', 'test-ingestion-token')
        response = client.post("/api/v1/snapshots/simulate-tick", json={})
        assert response.status_code == 401

    def test_simulate_tick_with_invalid_token_returns_403(self, client, monkeypatch):
        """POST /api/v1/snapshots/simulate-tick with wrong token returns 403."""
        monkeypatch.setattr(settings, 'snapshot_ingestion_token', 'test-ingestion-token')

        response = client.post(
            "/api/v1/snapshots/simulate-tick",
            json={},
            headers={"X-Ingestion-Token": "invalid-token-12345"}
        )
        assert response.status_code == 403

    def test_simulate_tick_when_token_unset_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, 'snapshot_ingestion_token', '')
        response = client.post("/api/v1/snapshots/simulate-tick", json={})
        assert response.status_code == 503

    def test_simulate_tick_with_valid_token_returns_200_or_503(self, client):
        """POST /api/v1/snapshots/simulate-tick with valid token succeeds or 503 if not initialized."""
        if not settings.snapshot_ingestion_token:
            pytest.skip("SNAPSHOT_INGESTION_TOKEN not configured")

        response = client.post(
            "/api/v1/snapshots/simulate-tick",
            json={},
            headers={"X-Ingestion-Token": settings.snapshot_ingestion_token}
        )
        # 200 = success, 503 = simulator not initialized (acceptable)
        assert response.status_code in (200, 503)


class TestRateLimiting:
    """Test rate limiting middleware."""

    def test_rate_limit_exempt_health(self, client):
        """Health endpoint should not be rate limited."""
        # Make many requests to /health - should not be rate limited
        for _ in range(150):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_applies_to_drivers_endpoint(self, client):
        """Rate limiting should apply to /api/v1/drivers/ endpoints."""
        # Make many requests to /drivers/ - should eventually be rate limited
        # Use a unique driver ID to avoid test pollution
        import uuid
        driver_id = f"TEST_{uuid.uuid4().hex[:8]}"

        rate_limited = False
        for i in range(150):
            response = client.post(
                f"/api/v1/drivers/{driver_id}/location",
                json={
                    "timestamp": "2024-01-01T00:00:00Z",
                    "latitude": 21.0 + i * 0.001,
                    "longitude": 105.8
                }
            )
            # We expect either success or rate limited
            if response.status_code == 429:
                rate_limited = True
                # Verify Retry-After header is present
                assert "Retry-After" in response.headers
                assert int(response.headers["Retry-After"]) > 0
                break

        # Rate limiting should have kicked in within 150 requests
        assert rate_limited, "Rate limiting should have applied to /drivers/ endpoint"

    def test_rate_limit_includes_retry_after_header(self, client):
        """Rate limited response should include Retry-After header."""
        import uuid
        driver_id = f"TEST_RATE_{uuid.uuid4().hex[:8]}"

        # Exhaust rate limit
        for _ in range(150):
            response = client.post(
                f"/api/v1/drivers/{driver_id}/location",
                json={
                    "timestamp": "2024-01-01T00:00:00Z",
                    "latitude": 21.0,
                    "longitude": 105.8
                }
            )
            if response.status_code == 429:
                assert "Retry-After" in response.headers
                retry_after = int(response.headers["Retry-After"])
                assert retry_after > 0
                assert retry_after <= 60
                return

        pytest.fail("Rate limiting did not trigger within 150 requests")


class TestNoDriversExemption:
    """Verify /drivers/ endpoints are NOT exempt from rate limiting."""

    def test_drivers_endpoint_not_exempt(self, client):
        """Confirm /drivers/ endpoint is subject to rate limiting."""
        import uuid
        driver_id = f"TEST_EXEMPT_{uuid.uuid4().hex[:8]}"

        # Count how many requests succeed before rate limiting
        successes = 0
        for _ in range(150):
            response = client.post(
                f"/api/v1/drivers/{driver_id}/location",
                json={
                    "timestamp": "2024-01-01T00:00:00Z",
                    "latitude": 21.0,
                    "longitude": 105.8
                }
            )
            if response.status_code == 200:
                successes += 1
            elif response.status_code == 429:
                # Rate limit hit - confirm /drivers/ is NOT exempt
                assert successes <= 100, "/drivers/ should be rate limited (not exempt)"
                return

        pytest.fail("Rate limiting did not trigger")
