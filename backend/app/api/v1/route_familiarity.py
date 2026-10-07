"""Protected internal route history ingestion. No history read endpoints."""
from datetime import UTC, datetime
import json

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ConfigDict, Field, ValidationError, field_validator

from backend.app.api.v1.ranking import authorize_ingestion
from backend.app.dependencies import get_route_history_ingestion
from backend.app.services.route_familiarity.ingestion import RouteHistoryIngestion
from backend.app.services.snapshots.models import FrozenModel, StateError, aware_utc

router = APIRouter()


class CompletedRoute(FrozenModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    driver_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    trip_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    completed_at: datetime
    polyline: str = Field(min_length=1, max_length=100_000)

    _completed_at = field_validator("completed_at")(aware_utc)


@router.post("/internal/route-familiarity/routes", dependencies=[Depends(authorize_ingestion)])
async def ingest_completed_route(request: Request, response: Response,
                                 service: RouteHistoryIngestion = Depends(get_route_history_ingestion)):
    try:
        declared_size = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    if declared_size > 105_000:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422)
    try:
        body = await request.body()
        if len(body) > 105_000:
            raise ValueError
        payload = CompletedRoute.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError, ValueError):
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    try:
        _, created = await service.ingest(payload.driver_id, payload.trip_id,
                                          payload.completed_at.astimezone(UTC), payload.polyline)
    except ValueError:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    except StateError:
        raise
    except Exception:
        raise StateError("Route history ingestion unavailable", "ROUTE_HISTORY_UNAVAILABLE", 503) from None
    response.status_code = 201 if created else 200
    return {"status": "created" if created else "already_ingested"}
