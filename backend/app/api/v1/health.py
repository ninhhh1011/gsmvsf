"""Liveness and readiness probes for production deployment."""

import asyncio

import httpx
from backend.app.dependencies import get_db_pool, get_redis
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


async def _database_ready(pool) -> bool:
    """Check PostgreSQL/PostGIS connectivity via provided pool."""
    try:
        async with pool.acquire() as conn:
            return bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM road_segments LIMIT 1)"))
    except Exception:
        return False


async def _redis_ready(redis_client) -> bool:
    """Check Redis connectivity via provided client."""
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False


async def dependencies_ready(request: Request) -> dict:
    """Check all required dependencies for recommendation service asynchronously."""
    pool = get_db_pool(request)
    redis_client = get_redis(request)

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
async def ready(request: Request):
    """
    Readiness probe - returns 200 if all required dependencies are available.

    Required dependencies:
    - GraphHopper: routing and map matching
    - PostgreSQL/PostGIS: segment data and candidate state
    - Redis: shared driver state store (stateful driver operations)

    Note: Redis is used for both shared driver state and snapshot caching.
    For stateful driver workflows, Redis is required.
    """
    dependencies = await dependencies_ready(request)

    # Required: GraphHopper, PostgreSQL, and Redis for shared driver state
    required = {
        "graphhopper": dependencies["graphhopper"],
        "postgis": dependencies["postgis"],
        "redis": dependencies["redis"],
    }
    if not all(required.values()):
        raise HTTPException(503, detail={"status": "not_ready", **dependencies})

    return {"status": "ready", **dependencies}
