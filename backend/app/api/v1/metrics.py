"""Prometheus metrics endpoint."""
from fastapi import APIRouter
from backend.app.core.metrics import metrics_endpoint

router = APIRouter()


@router.get("/metrics")
async def metrics():
    """
    Prometheus-compatible metrics endpoint.

    Exposes operational metrics for monitoring:
    - Recommendation request counts and latency
    - GraphHopper route call counts and latency
    - Candidate state conflicts
    - Database fallbacks
    - Active driver count
    """
    return metrics_endpoint()
