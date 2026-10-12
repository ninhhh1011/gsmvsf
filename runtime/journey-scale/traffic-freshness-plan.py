"""Read-only EXPLAIN of fresh traffic enumeration, with no payload/secret output."""
import asyncio
import json

import asyncpg

from backend.app.config import settings
from backend.app.services.ranking.models import RankingPolicy


async def main():
    async with asyncpg.create_pool(settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'),
                                  min_size=1, max_size=1,
                                  server_settings={'search_path': 'realtime,public'}) as pool:
        plan = await pool.fetchval("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT DISTINCT entity_id FROM state_snapshots
            WHERE kind='traffic' AND timestamp >= now() - $1::double precision * interval '1 second'
                AND timestamp <= now()""", RankingPolicy().traffic_fresh_s)
        print(json.dumps(json.loads(plan), indent=2))


asyncio.run(main())
