"""
Load tests for EV Recommendation System.
"""
import pytest
import asyncio
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://localhost:8000/api/v1"

class TestLoad:
    """Load testing scenarios."""

    @pytest.fixture
    def session(self):
        """Create aiohttp session."""
        return aiohttp.ClientSession()

    @pytest.mark.asyncio
    async def test_concurrent_recommendations(self, session):
        """Test 50 concurrent recommendation requests."""
        async def make_request():
            payload = {
                "driver_id": f"D{np.random.randint(1, 100)}",
                "latitude": 21.0285,
                "longitude": 105.8542,
                "destination_lat": 21.0350,
                "destination_lng": 105.8620,
                "soc_percent": 25.0
            }
            start = time.time()
            async with session.post(
                f"{BASE_URL}/recommendation",
                json=payload
            ) as resp:
                await resp.json()
                return time.time() - start

        # Run 50 concurrent requests
        tasks = [make_request() for _ in range(50)]
        latencies = await asyncio.gather(*tasks)

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        print(f"Average latency: {avg_latency:.3f}s")
        print(f"P95 latency: {p95_latency:.3f}s")

        assert avg_latency < 2.0, "Average latency should be under 2s"

    @pytest.mark.asyncio
    async def test_route_comparison_load(self, session):
        """Test 20 concurrent route comparisons."""
        async def make_comparison():
            payload = {
                "route_a": {
                    "route_id": "ROUTE_A",
                    "coordinates": [
                        [21.028, 105.854],
                        [21.030, 105.856],
                        [21.032, 105.858]
                    ]
                },
                "route_b": {
                    "route_id": "ROUTE_B",
                    "coordinates": [
                        [21.028, 105.854],
                        [21.031, 105.857],
                        [21.033, 105.859]
                    ]
                },
                "resolution": 10
            }
            start = time.time()
            async with session.post(
                f"{BASE_URL}/routes/compare",
                json=payload
            ) as resp:
                await resp.json()
                return time.time() - start

        # Run 20 concurrent requests
        tasks = [make_comparison() for _ in range(20)]
        latencies = await asyncio.gather(*tasks)

        avg_latency = sum(latencies) / len(latencies)
        print(f"Average route comparison latency: {avg_latency:.3f}s")

        assert avg_latency < 0.5, "Route comparison should be fast"

@pytest.fixture
def np():
    import numpy as np
    return np

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
