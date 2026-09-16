"""Health check endpoints."""
import httpx
from fastapi import APIRouter, HTTPException, status

from backend.app.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Basic health check. Returns 200 if the application is running."""
    return {"status": "healthy"}


@router.get("/ready")
async def ready() -> dict[str, str | bool]:
    """
    Readiness check. Verifies OSRM is reachable.
    Database readiness is checked in later milestones.
    """
    osrm_ready = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.osrm_base_url}/route/v1/driving/0,0")
            osrm_ready = response.status_code in (200, 400, 422)
    except Exception:
        pass

    if not osrm_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"osrm": "not reachable"},
        )

    return {
        "status": "ready",
        "osrm": osrm_ready,
        "dataset_path": str(settings.dataset_path),
    }
