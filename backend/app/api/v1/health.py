"""Liveness and readiness of the sole production engine and segment database."""
import asyncio
from contextlib import closing
import httpx
import psycopg2
from fastapi import APIRouter, HTTPException
from backend.app.config import settings
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter

router = APIRouter()

def _database_ready():
    try:
        with closing(psycopg2.connect(settings.database_url_sync, connect_timeout=3)) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS(SELECT 1 FROM road_segments LIMIT 1)")
                return cur.fetchone()[0]
    except psycopg2.Error:
        return False


def _redis_ready():
    """Check Redis connectivity for driver state and snapshot cache."""
    try:
        import redis
        r = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


async def dependencies_ready():
    """Check all required dependencies for recommendation service."""
    async with httpx.AsyncClient(timeout=5) as client:
        routing, database, redis_state = await asyncio.gather(
            GraphHopperRoutingAdapter(client=client, timeout_seconds=5).is_healthy(),
            asyncio.to_thread(_database_ready),
            asyncio.to_thread(_redis_ready),
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
