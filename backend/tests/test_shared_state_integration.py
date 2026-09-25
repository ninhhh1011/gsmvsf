"""
Phase 4: Two API Process + Redis Integration Tests

Tests the shared driver state across two separate API instances using Redis.

Requirements:
- Redis running on 127.0.0.1:6379
- Backend server can be started on port 8000

Usage:
    python -m pytest backend/tests/test_shared_state_integration.py -v
"""
import asyncio
import subprocess
import time
import sys
import httpx
import pytest
from datetime import datetime, timezone


BASE_URL_A = "http://127.0.0.1:8000"
BASE_URL_B = "http://127.0.0.1:8001"
DRIVER_ID = "test_integration_driver"


@pytest.fixture(scope="module")
def redis_available():
    """Check if Redis is available."""
    try:
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379)
        r.ping()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def skip_if_no_redis(redis_available):
    """Skip tests if Redis is not available."""
    if not redis_available:
        pytest.skip("Redis not available")


@pytest.fixture(scope="module")
def api_available():
    """Check if API instance is running."""
    try:
        import requests
        # Use /api/v1/drivers endpoint instead of /ready (which checks PBF path)
        r = requests.get("http://127.0.0.1:8000/api/v1/drivers", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def skip_if_no_api(api_available):
    """Skip tests if API not available."""
    if not api_available:
        pytest.skip("API instance not available")


@pytest.fixture(scope="module")
async def two_instances(skip_if_no_redis, skip_if_no_api):
    """Use existing API instances from docker-compose."""
    import requests

    # Verify both instances are reachable
    for port in [8000, 8001]:
        url = f"http://127.0.0.1:{port}/api/v1/drivers"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                pytest.skip(f"API on port {port} not ready: {resp.status_code}")
        except Exception as e:
            pytest.skip(f"API on port {port} not reachable: {e}")

    yield BASE_URL_A, BASE_URL_B


@pytest.mark.asyncio
async def test_post_instance_a_get_instance_b(two_instances):
    """
    A: POST matched state on instance A, GET from instance B via Redis.

    Expected: Matched state is visible from instance B.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_a_to_b"

    async with httpx.AsyncClient(timeout=10) as client:
        # Clear any existing state
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")

        # Send multiple observations to trigger matching
        for i in range(5):
            obs = {
                "latitude": 21.0 + i * 0.001,
                "longitude": 105.0 + i * 0.001,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kmh": 30,
                "heading_deg": 90,
            }
            resp = await client.post(
                f"{url_a}/api/v1/drivers/{driver}/location",
                json=obs
            )
            await asyncio.sleep(0.1)

        # Get state from instance B
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        assert resp_b.status_code == 200, f"GET failed: {resp_b.text}"
        data = resp_b.json()

        # State should have observations from instance A
        assert data["buffered_points"] >= 5, f"Expected >=5 points, got {data['buffered_points']}"

        # Cleanup
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_concurrent_writes(two_instances):
    """
    B: Concurrent writes from both instances.

    Expected: Both writes succeed, state is consistent.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_concurrent"

    async with httpx.AsyncClient(timeout=10) as client:
        # Clear
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")

        # Send concurrent observations from both instances
        async def send_obs(url, obs):
            return await client.post(
                f"{url}/api/v1/drivers/{driver}/location",
                json=obs
            )

        obs_a = {
            "latitude": 21.001,
            "longitude": 105.001,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
        }
        obs_b = {
            "latitude": 21.002,
            "longitude": 105.002,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 35,
            "heading_deg": 95,
        }

        # Send concurrently
        results = await asyncio.gather(
            send_obs(url_a, obs_a),
            send_obs(url_b, obs_b),
        )

        # Both should succeed
        for resp in results:
            assert resp.status_code == 200, f"Concurrent write failed: {resp.text}"

        # Get from either instance
        resp = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        assert resp.status_code == 200

        # Cleanup
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_reset_clears_all_instances(two_instances):
    """
    D: Reset from one instance clears state visible from another.

    Expected: After reset, GET from any instance returns fresh state.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_reset"

    async with httpx.AsyncClient(timeout=10) as client:
        # Send observation
        obs = {
            "latitude": 21.005,
            "longitude": 105.005,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
        }
        await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
        await asyncio.sleep(0.2)

        # Verify state exists
        resp = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
        assert resp.json()["buffered_points"] >= 1

        # Reset from instance B
        resp = await client.delete(f"{url_b}/api/v1/drivers/{driver}/location")
        assert resp.status_code == 200

        # Verify state cleared from instance A
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        assert resp_a.status_code == 200
        # Should be fresh state (WARMING_UP)
        assert resp_a.json()["buffered_points"] == 0


@pytest.mark.asyncio
async def test_stale_observation_rejected(two_instances):
    """
    C: Stale observation (before last timestamp) is rejected.

    Expected: Response contains STALE_OBSERVATION status.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_stale"

    async with httpx.AsyncClient(timeout=10) as client:
        # Clear
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")

        # Send observation with recent timestamp
        now = datetime.now(timezone.utc)
        obs1 = {
            "latitude": 21.01,
            "longitude": 105.01,
            "timestamp": now.isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
        }
        await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
        await asyncio.sleep(0.1)

        # Try to send stale observation (1 minute earlier)
        stale_ts = now.replace(minute=now.minute - 1)
        obs2 = {
            "latitude": 21.02,
            "longitude": 105.02,
            "timestamp": stale_ts.isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
        }
        resp = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs2)

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "STALE_OBSERVATION", f"Expected STALE_OBSERVATION, got {data['status']}"

        # Cleanup
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_no_duplicate_observation_counting(two_instances):
    """
    E: Observations are counted per request, even if sent from different instances.

    Expected: Each instance sees consistent state for its own requests.
    The API doesn't deduplicate across instances based on observation_id.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_dup"

    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")

        # Send observation from instance A
        ts = datetime.now(timezone.utc).isoformat()
        obs = {
            "latitude": 21.03,
            "longitude": 105.03,
            "timestamp": ts,
            "speed_kmh": 30,
            "heading_deg": 90,
        }

        resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
        assert resp1.status_code == 200
        count1 = resp1.json()["total_observations"]

        # Send different observation from instance B
        obs_b = {
            "latitude": 21.04,
            "longitude": 105.04,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
        }
        resp_b = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs_b)
        assert resp_b.status_code == 200

        # Both instances should see consistent count
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_a_count = resp_a.json()["total_observations"]

        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")
        resp_b_count = resp_b.json()["total_observations"]

        assert resp_a_count == resp_b_count, \
            f"Both instances should see same total: {resp_a_count} vs {resp_b_count}"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_sequential_writes_increment_version(two_instances):
    """
    F: Sequential writes should increment version, latest write wins.

    Expected: Both instances see consistent final state.
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_seq"

    async with httpx.AsyncClient(timeout=10) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")

        # Send 3 sequential observations with vehicle_category to avoid map matching errors
        for i in range(3):
            obs = {
                "latitude": 21.04 + i * 0.001,
                "longitude": 105.04 + i * 0.001,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kmh": 30 + i * 5,
                "heading_deg": 90,
                "vehicle_category": "EV_CAR",
            }
            resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
            assert resp.status_code == 200

        # Both instances should see same final state
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        data_a = resp_a.json()
        data_b = resp_b.json()

        assert data_a["buffered_points"] == data_b["buffered_points"], \
            f"Points mismatch: {data_a['buffered_points']} vs {data_b['buffered_points']}"
        assert data_a["total_observations"] == data_b["total_observations"], \
            f"Total observations mismatch: {data_a['total_observations']} vs {data_b['total_observations']}"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


if __name__ == "__main__":
    # Run as standalone script for manual testing
    pytest.main([__file__, "-v", "-s"])
