"""Liveness and readiness of the sole production engine and segment database."""
import asyncio

import asyncpg
import httpx
from backend.app.config import settings
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from fastapi import APIRouter, HTTPException, Request
from redis.asyncio import Redis

router = APIRouter()


async def _database_ready(pool: asyncpg.Pool | None = None) -> bool:
    """Asynchronously check PostgreSQL/PostGIS connectivity."""
    try:
        if pool is not None:
            async with pool.acquire() as conn:
                return bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM road_segments LIMIT 1)"))
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn, timeout=3.0)
        try:
            return bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM road_segments LIMIT 1)"))
        finally:
            await conn.close()
    except Exception:
        return False


async def _redis_ready(redis_client: Redis | None = None) -> bool:
    """Asynchronously check Redis connectivity for driver state and snapshot cache."""
    try:
        if redis_client is not None:
            return bool(await redis_client.ping())
        r = Redis.from_url(settings.redis_url, socket_connect_timeout=3.0, socket_timeout=3.0)
        try:
            return bool(await r.ping())
        finally:
            await r.aclose()
    except Exception:
        return False


async def dependencies_ready(request: Request | None = None):
    """Check all required dependencies for recommendation service asynchronously."""
    pool = getattr(request.app.state, "db_pool", None) if request and hasattr(request, "app") else None
    redis_client = getattr(request.app.state, "redis", None) if request and hasattr(request, "app") else None

    async with httpx.AsyncClient(timeout=5) as client:
        routing, database, redis_state = await asyncio.gather(
            GraphHopperRoutingAdapter(client=client, timeout_seconds=5).is_healthy(),
            _database_ready(pool),
            _redis_ready(redis_client),
        )
    return {
        "graphhopper": routing,
        "postgis": database,
        "redis": redis_state,
    }


@router.get("/health")
async def health():
    """
    Liveness probe - returns 200 if the process is running.
    """
    return {"status": "healthy"}


@router.get("/ready")
@router.get("/readiness")
async def ready():
    """
    Readiness probe - returns 200 if all required dependencies are available.

    Required dependencies:
    - GraphHopper: routing and map matching
    - PostgreSQL/PostGIS: segment data and candidate state
    - Redis: shared driver state store (stateful driver operations)

    Degradable dependencies (service can operate in degraded mode):
    - None for core functionality
    - Snapshot cache Redis is optional because PostgreSQL fallback exists

    Note: Redis is used for both shared driver state and snapshot caching.
    For stateful driver workflows, Redis is required.
    """
    dependencies = await dependencies_ready()

    # Required: GraphHopper, PostgreSQL, and Redis for shared driver state
    required = {
        "graphhopper": dependencies["graphhopper"],
        "postgis": dependencies["postgis"],
        "redis": dependencies["redis"],  # Required for shared driver state
    }
    if not all(required.values()):
        raise HTTPException(503, detail={"status": "not_ready", **dependencies})

    return {"status": "ready", **dependencies}
