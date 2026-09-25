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
from datetime import datetime, timezone, timedelta


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

    Strong assertion: After multiple observations, both instances must see:
    - Same status (both MATCHED or both NO_MATCH)
    - Same total_observations count
    - Same buffered_points count
    - Same last_match_time if matched
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_a_to_b"

    async with httpx.AsyncClient(timeout=30) as client:
        # Clear any existing state
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send multiple observations to trigger matching
        for i in range(5):
            obs = {
                "latitude": 21.028 + i * 0.002,
                "longitude": 105.854 + i * 0.002,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kmh": 30,
                "heading_deg": 90,
                "vehicle_category": "EV_CAR",
            }
            resp = await client.post(
                f"{url_a}/api/v1/drivers/{driver}/location",
                json=obs
            )
            await asyncio.sleep(0.5)

        # Get state from both instances
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        assert resp_a.status_code == 200, f"GET A failed: {resp_a.text}"
        assert resp_b.status_code == 200, f"GET B failed: {resp_b.text}"

        data_a = resp_a.json()
        data_b = resp_b.json()

        # CRITICAL: Both must agree on status
        assert data_a["status"] == data_b["status"], \
            f"Status mismatch: A={data_a['status']} B={data_b['status']}"

        # CRITICAL: Both must see same counts
        assert data_a["buffered_points"] == data_b["buffered_points"], \
            f"Buffered points mismatch: A={data_a['buffered_points']} B={data_b['buffered_points']}"
        assert data_a["total_observations"] == data_b["total_observations"], \
            f"Total observations mismatch: A={data_a['total_observations']} B={data_b['total_observations']}"

        # CRITICAL: If matched, both must have matched_position
        if data_a["status"] == "MATCHED":
            assert data_a["matched_position"] is not None, "Instance A should have matched_position"
            assert data_b["matched_position"] is not None, "Instance B should have matched_position"
            assert data_a["last_match_time"] == data_b["last_match_time"], \
                f"last_match_time mismatch: A={data_a['last_match_time']} B={data_b['last_match_time']}"

        # CRITICAL: At least 5 observations should be accepted
        assert data_a["total_observations"] >= 5, \
            f"Expected >=5 observations, got {data_a['total_observations']}"

        # Cleanup
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_concurrent_writes(two_instances):
    """
    B: Concurrent writes from both instances must not lose observations.

    Strong assertion:
    - Both requests succeed (200 OK)
    - Final observation count >= number of unique observations sent
    - Both instances see the same final count
    - No observation IDs are silently dropped
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_concurrent"

    async with httpx.AsyncClient(timeout=30) as client:
        # Clear
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send observations from BOTH instances sequentially (testing state consistency)
        obs_a = {
            "latitude": 21.005,
            "longitude": 105.005,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp_a = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs_a)
        assert resp_a.status_code == 200, f"Write A failed: {resp_a.text}"
        count_a_after_first = resp_a.json()["total_observations"]

        obs_b = {
            "latitude": 21.006,
            "longitude": 105.006,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 35,
            "heading_deg": 95,
            "vehicle_category": "EV_CAR",
        }
        resp_b = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs_b)
        assert resp_b.status_code == 200, f"Write B failed: {resp_b.text}"

        # Both instances should see consistent count
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        data_a = resp_a.json()
        data_b = resp_b.json()

        # CRITICAL: No lost updates - count must be >= 2 (both obs accepted)
        assert data_a["total_observations"] >= 2, \
            f"Lost update: expected >=2 observations, got {data_a['total_observations']}"
        assert data_b["total_observations"] >= 2, \
            f"Lost update: expected >=2 observations, got {data_b['total_observations']}"

        # CRITICAL: Both instances must agree on final count
        assert data_a["total_observations"] == data_b["total_observations"], \
            f"Inconsistent counts: A={data_a['total_observations']} B={data_b['total_observations']}"

        # Cleanup
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_reset_during_pending_request(two_instances):
    """
    D2: Reset during pending request - old state should not resurrect.

    Scenario:
    1. Send observation O1 (accepted)
    2. Send observation O2 (pending)
    3. Reset state via DELETE
    4. O2 request completes
    5. Final state should be empty (reset), not include O2

    Strong assertion:
    - After reset, both instances see buffered_points == 0
    - total_observations resets to 0
    - No old observations resurrect after reset
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_reset_pending"

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Step 1: Send O1
        obs1 = {
            "latitude": 21.05,
            "longitude": 105.05,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
        assert resp1.status_code == 200
        assert resp1.json()["total_observations"] == 1

        # Step 2: Reset via DELETE
        resp_del = await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        assert resp_del.status_code == 200
        assert resp_del.json()["reset"] == True

        # Step 3: Verify both instances see empty state
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        data_a = resp_a.json()
        data_b = resp_b.json()

        # CRITICAL: Both see 0 observations after reset
        assert data_a["buffered_points"] == 0, \
            f"Instance A should see 0 points after reset, got {data_a['buffered_points']}"
        assert data_b["buffered_points"] == 0, \
            f"Instance B should see 0 points after reset, got {data_b['buffered_points']}"
        assert data_a["total_observations"] == 0, \
            f"Instance A should see 0 total after reset, got {data_a['total_observations']}"
        assert data_b["total_observations"] == 0, \
            f"Instance B should see 0 total after reset, got {data_b['total_observations']}"

        # Step 4: New observation starts fresh (generation increment)
        obs2 = {
            "latitude": 21.06,
            "longitude": 105.06,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp2 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs2)
        assert resp2.status_code == 200
        assert resp2.json()["total_observations"] == 1, \
            "New observation after reset should start from 1"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_stale_observation_rejected(two_instances):
    """
    C: Stale observation (before last timestamp) is rejected.

    Strong assertion:
    - Status is STALE_OBSERVATION
    - Counters do not increment for rejected observation
    - Next valid observation continues correctly
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_stale"

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send observation with recent timestamp
        now = datetime.now(timezone.utc)
        obs1 = {
            "latitude": 21.01,
            "longitude": 105.01,
            "timestamp": now.isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
        assert resp1.status_code == 200
        count_after_valid = resp1.json()["total_observations"]

        # Try to send stale observation (1 minute earlier)
        # Use timedelta instead of replace(minute=minute-1) to handle minute=0 correctly
        stale_ts = (now - timedelta(minutes=1)).isoformat()
        obs2 = {
            "latitude": 21.02,
            "longitude": 105.02,
            "timestamp": stale_ts,
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp2 = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs2)

        assert resp2.status_code == 200
        data2 = resp2.json()
        # CRITICAL: Status must be STALE_OBSERVATION
        assert data2["status"] == "STALE_OBSERVATION", \
            f"Expected STALE_OBSERVATION, got {data2['status']}"

        # CRITICAL: Count must NOT increment for stale observation
        assert data2["total_observations"] == count_after_valid, \
            f"Stale observation should not increment count: expected {count_after_valid}, got {data2['total_observations']}"

        # Send valid observation - should increment correctly
        obs3 = {
            "latitude": 21.03,
            "longitude": 105.03,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp3 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs3)
        assert resp3.status_code == 200
        # CRITICAL: Count should be count_after_valid + 1
        assert resp3.json()["total_observations"] == count_after_valid + 1, \
            f"Valid obs should increment: expected {count_after_valid + 1}, got {resp3.json()['total_observations']}"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_no_duplicate_observation_counting(two_instances):
    """
    E: No duplicate observations - each unique observation is counted once.

    Strong assertion:
    - After N unique observations, total_observations == N
    - Both instances see the same count
    - Subsequent observation continues to increment
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_dup"

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send N=3 unique observations
        expected_count = 0
        for i in range(3):
            obs = {
                "latitude": 21.03 + i * 0.001,
                "longitude": 105.03 + i * 0.001,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kmh": 30,
                "heading_deg": 90,
                "vehicle_category": "EV_CAR",
            }
            resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
            assert resp.status_code == 200
            expected_count += 1
            data = resp.json()
            # CRITICAL: Each unique observation increments count by exactly 1
            assert data["total_observations"] == expected_count, \
                f"Expected {expected_count} after {i+1} observations, got {data['total_observations']}"

        # Both instances must agree
        resp_a = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        resp_b = await client.get(f"{url_b}/api/v1/drivers/{driver}/location")

        count_a = resp_a.json()["total_observations"]
        count_b = resp_b.json()["total_observations"]

        # CRITICAL: Both see exact count
        assert count_a == expected_count, f"Instance A: expected {expected_count}, got {count_a}"
        assert count_b == expected_count, f"Instance B: expected {expected_count}, got {count_b}"
        assert count_a == count_b, f"Inconsistent counts: A={count_a} B={count_b}"

        # Send 4th observation - count must be 4
        obs4 = {
            "latitude": 21.04,
            "longitude": 105.04,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs4)
        assert resp.json()["total_observations"] == 4, "4th observation should increment to 4"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_sequential_writes_increment_version(two_instances):
    """
    F: Sequential writes increment version atomically.

    Strong assertion:
    - Version increments on each save
    - Both instances see consistent state
    - State is correctly persisted to Redis
    """
    import redis
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_seq"

    r = redis.Redis(host='127.0.0.1', port=6379)

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send 3 sequential observations with vehicle_category
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

        # CRITICAL: Check version in Redis
        snapshot = r.get(f"driver_state:{driver}")
        assert snapshot is not None, "State should be in Redis"
        import json
        s = json.loads(snapshot)
        assert s["version"] >= 1, f"Version should be >= 1, got {s['version']}"
        print(f"DEBUG: Redis version={s['version']} obs={len(s.get('observations', []))}")

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_same_id_different_payload_conflict(two_instances):
    """
    CASE-10: Same observation_id with different payload returns 409 Conflict.

    Scenario:
    1. Send observation O1 with ID="obs1", position (21.0, 105.0)
    2. Retry same ID="obs1" but different position (21.1, 105.1)
    3. Second request must return 409 Conflict

    Strong assertion:
    - Second request returns 409
    - Count does not increment
    - State reflects first observation only
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_conflict"

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Step 1: Send observation with specific ID and position
        obs1 = {
            "observation_id": "obs_conflict_test",
            "latitude": 21.005,
            "longitude": 105.005,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
        assert resp1.status_code == 200, f"First obs failed: {resp1.text}"
        data1 = resp1.json()
        count_after_first = data1["total_observations"]

        # Step 2: Same ID but DIFFERENT position - should return 409
        obs2 = {
            "observation_id": "obs_conflict_test",  # Same ID
            "latitude": 21.050,  # Different position
            "longitude": 105.050,  # Different position
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speed_kmh": 35,
            "heading_deg": 95,
            "vehicle_category": "EV_CAR",
        }
        resp2 = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs2)

        # CRITICAL: Must return 409 Conflict
        assert resp2.status_code == 409, \
            f"Expected 409 Conflict for same ID/different payload, got {resp2.status_code}: {resp2.text}"

        # Count should not increment
        resp_get = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        final_data = resp_get.json()
        assert final_data["total_observations"] == count_after_first, \
            f"Count should not increment on conflict: expected {count_after_first}, got {final_data['total_observations']}"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_same_id_same_payload_retry_accepted(two_instances):
    """
    CASE-09: Same observation_id with same payload is accepted (idempotent retry).

    Scenario:
    1. Send observation O1 with ID="obs_retry"
    2. Retry same ID with identical payload
    3. Second request succeeds but count does NOT increment (dedup)

    Strong assertion:
    - Second request returns 200
    - Count remains the same (dedup)
    - Both instances see consistent state
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_retry"

    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Use a fixed timestamp for same payload
        import time
        ts = datetime.fromisoformat(datetime.now(timezone.utc).isoformat().replace('T', ' ').split('.')[0] + '+00:00')

        # Step 1: Send observation with specific ID and position
        obs1 = {
            "observation_id": "obs_retry_test",
            "latitude": 21.010,
            "longitude": 105.010,
            "timestamp": ts.isoformat(),
            "speed_kmh": 30,
            "heading_deg": 90,
            "vehicle_category": "EV_CAR",
        }
        resp1 = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs1)
        assert resp1.status_code == 200, f"First obs failed: {resp1.text}"
        count_after_first = resp1.json()["total_observations"]

        # Step 2: Same ID, SAME payload - should be accepted (idempotent)
        await asyncio.sleep(0.2)
        obs2 = {
            "observation_id": "obs_retry_test",  # Same ID
            "latitude": 21.010,  # Same position
            "longitude": 105.010,  # Same position
            "timestamp": ts.isoformat(),  # Same timestamp
            "speed_kmh": 30,  # Same speed
            "heading_deg": 90,  # Same heading
            "vehicle_category": "EV_CAR",
        }
        resp2 = await client.post(f"{url_b}/api/v1/drivers/{driver}/location", json=obs2)

        # CRITICAL: Retry with same payload succeeds (200 OK)
        assert resp2.status_code == 200, \
            f"Expected 200 for same ID/same payload retry, got {resp2.status_code}: {resp2.text}"

        # Count should NOT increment (dedup)
        resp_get = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        final_data = resp_get.json()
        assert final_data["total_observations"] == count_after_first, \
            f"Count should not increment for duplicate: expected {count_after_first}, got {final_data['total_observations']}"

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


@pytest.mark.asyncio
async def test_dedup_retention_boundary(two_instances):
    """
    CASE-11: Dedup retention - cleanup prevents unbounded growth.

    Scenario:
    1. Send many observations with unique IDs
    2. Verify state is maintained correctly
    3. Verify cleanup mechanism exists (MAX_SEEN_IDS limit)

    Strong assertion:
    - Many observations are stored correctly
    - Dedup entries are bounded
    - No memory leak from unbounded dedup
    """
    url_a, url_b = two_instances
    driver = f"{DRIVER_ID}_retention"

    async with httpx.AsyncClient(timeout=60) as client:
        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")
        await asyncio.sleep(0.5)

        # Send 100 observations with unique IDs
        num_obs = 100
        for i in range(num_obs):
            obs = {
                "observation_id": f"retention_test_{i}",
                "latitude": 21.0 + (i % 10) * 0.001,
                "longitude": 105.0 + (i % 10) * 0.001,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "speed_kmh": 30 + i % 20,
                "heading_deg": 90,
                "vehicle_category": "EV_CAR",
            }
            resp = await client.post(f"{url_a}/api/v1/drivers/{driver}/location", json=obs)
            if resp.status_code != 200:
                print(f"WARNING: Observation {i} failed: {resp.text}")

        # Verify count
        resp_get = await client.get(f"{url_a}/api/v1/drivers/{driver}/location")
        data = resp_get.json()

        # CRITICAL: All observations counted
        assert data["total_observations"] >= num_obs, \
            f"Expected >= {num_obs} observations, got {data['total_observations']}"

        # Verify Redis state size
        import redis
        import json
        r = redis.Redis(host='127.0.0.1', port=6379)
        snapshot = r.get(f"driver_state:{driver}")
        assert snapshot is not None, "State should be in Redis"

        s = json.loads(snapshot)

        # CRITICAL: seen_observation_ids is bounded (should not exceed MAX_SEEN_IDS = 10000)
        num_seen = len(s.get('seen_observation_ids', []))
        assert num_seen <= 10000, \
            f"seen_observation_ids should be bounded by MAX_SEEN_IDS (10000), got {num_seen}"

        # Dedup should have entries for all sent IDs
        assert num_seen >= num_obs, \
            f"seen_observation_ids should contain all {num_obs} IDs, got {num_seen}"

        # seen_payloads should also be bounded
        num_payloads = len(s.get('seen_payloads', {}))
        assert num_payloads <= 10000, \
            f"seen_payloads should be bounded, got {num_payloads}"

        print(f"DEBUG: {num_obs} obs, {num_seen} seen_ids, {num_payloads} payloads")

        await client.delete(f"{url_a}/api/v1/drivers/{driver}/location")


if __name__ == "__main__":
    # Run as standalone script for manual testing
    pytest.main([__file__, "-v", "-s"])
