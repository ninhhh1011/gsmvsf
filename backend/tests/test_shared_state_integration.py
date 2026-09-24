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
async def two_instances(skip_if_no_redis):
    """Start two API instances and yield their URLs."""
    # Check if backend server is already running
    proc_a = None
    proc_b = None

    try:
        # Check if port 8000 is already listening
        try:
            async with httpx.AsyncClient() as client:
                await client.get(f"{BASE_URL_A}/ready", timeout=2)
            port_8000_active = True
        except:
            port_8000_active = False

        # Start second instance on port 8001
        proc_b = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "backend.app.main:app",
             "--port", "8001",
             "--host", "127.0.0.1"],
            cwd="e:/build6week",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for second instance to start
        max_wait = 30
        started = False
        for _ in range(max_wait):
            try:
                async with httpx.AsyncClient() as client:
                    await client.get(f"{BASE_URL_B}/ready", timeout=1)
                    started = True
                    break
            except:
                await asyncio.sleep(1)

        if not started:
            raise RuntimeError("Could not start second API instance")

        yield BASE_URL_A, BASE_URL_B

    finally:
        if proc_b:
            proc_b.terminate()
            proc_b.wait(timeout=5)


@pytest.mark.asyncio
@pytest.mark.skipif(True, reason="Requires two running API instances - manual test")
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
@pytest.mark.skipif(True, reason="Requires two running API instances - manual test")
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
@pytest.mark.skipif(True, reason="Requires two running API instances - manual test")
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
@pytest.mark.skipif(True, reason="Requires two running API instances - manual test")
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


if __name__ == "__main__":
    # Run as standalone script for manual testing
    pytest.main([__file__, "-v", "-s"])
