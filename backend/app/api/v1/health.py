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

async def dependencies_ready():
    async with httpx.AsyncClient(timeout=5) as client:
        routing, database = await asyncio.gather(
            GraphHopperRoutingAdapter(client=client, timeout_seconds=5).is_healthy(),
            asyncio.to_thread(_database_ready),
        )
    return {"graphhopper": routing, "postgis": database}

@router.get("/health")
async def health():
    return {"status": "healthy"}

@router.get("/ready")
@router.get("/readiness")
async def ready():
    dependencies = await dependencies_ready()
    if not all(dependencies.values()):
        raise HTTPException(503, detail={"status": "not_ready", **dependencies})
    return {"status": "ready", **dependencies}
