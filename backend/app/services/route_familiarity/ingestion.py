"""Trusted completed-route ingestion."""
from datetime import datetime

from backend.app.services.route_familiarity.repository import RouteHistoryRepository
from backend.app.services.route_familiarity.signature import create_route_signature


class RouteHistoryIngestion:
    def __init__(self, repository: RouteHistoryRepository):
        self.repository = repository

    async def ingest(self, driver_id: str, trip_id: str, completed_at: datetime, polyline: str,
                     started_at: datetime | None = None):
        if started_at is not None and started_at > completed_at:
            raise ValueError("trip start cannot follow completion")
        signature = create_route_signature([polyline])
        if started_at is None:
            return await self.repository.upsert_route(driver_id, trip_id, completed_at, signature)
        return await self.repository.upsert_route(driver_id, trip_id, completed_at, signature, started_at)
