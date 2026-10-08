"""Trusted completed-route ingestion."""
from datetime import datetime

from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.signature import create_route_signature


class RouteHistoryIngestion:
    def __init__(self, repository: RouteHistoryRepository):
        self.repository = repository

    async def ingest(self, driver_id: str, trip_id: str, completed_at: datetime, polyline: str):
        signature = create_route_signature([polyline])
        return await self.repository.upsert_route(driver_id, trip_id, completed_at, signature)
