"""Explicit route familiarity schema migration; --rollback drops its table."""
import argparse
import asyncio
from pathlib import Path

import asyncpg

from backend.app.config import settings


async def migrate(database_url: str, rollback: bool) -> None:
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    async with asyncpg.create_pool(dsn, min_size=1, max_size=2, timeout=settings.snapshot_db_timeout_s,
                                   command_timeout=settings.snapshot_db_timeout_s,
                                   server_settings={"search_path": "realtime,public"}) as pool:
        async with pool.acquire() as conn:
            if rollback:
                await conn.execute("DROP TABLE IF EXISTS realtime.route_familiarity_routes")
            else:
                await conn.execute(Path("backend/app/services/route_familiarity/schema.sql")
                                   .read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--rollback", action="store_true", help="drop route familiarity history table")
    args = parser.parse_args()
    asyncio.run(migrate(args.database_url, args.rollback))


if __name__ == "__main__":
    main()
