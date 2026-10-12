"""Read-only timing of the production congestion DAO against existing snapshots."""
import asyncio
import json
from time import perf_counter

import asyncpg

from backend.app.config import settings
from backend.app.services.snapshots.repository import SnapshotRepository


async def main():
    async with asyncpg.create_pool(settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'),
                                  min_size=1, max_size=1,
                                  server_settings={'search_path': 'realtime,public'}) as pool:
        repository = SnapshotRepository(pool, timeout_s=15)
        measurements = []
        for _ in range(3):
            started = perf_counter()
            polygons = await repository.get_congested_polygons()
            measurements.append({'duration_s': round(perf_counter() - started, 3), 'polygon_count': len(polygons)})
        print(json.dumps(measurements))


asyncio.run(main())
