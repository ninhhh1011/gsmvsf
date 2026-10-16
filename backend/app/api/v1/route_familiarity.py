"""Protected ingestion, caller inspection, aggregates and gated synthetic evidence."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from backend.app.api.v1.ranking import authorize_ingestion
from backend.app.config import settings
from backend.app.services.snapshots.models import FrozenModel, StateError, aware_utc
from backend.app.services.route_familiarity.deviations import GuidedTrip, analyze_guided_trip, inspect_guided_trip
from backend.app.services.route_familiarity.similarity import SimilarityWorkLimitExceeded

router = APIRouter()


@router.post('/routing/inspect-guided-trip')
async def inspect_trip(request: Request):
    try:
        body = await _read_bounded_body(request, 2_000_000)
        payload = GuidedTrip.model_validate(json.loads(body))
        return await run_in_threadpool(inspect_guided_trip, payload)
    except (ValueError, ValidationError, UnicodeDecodeError, SimilarityWorkLimitExceeded):
        raise StateError('Invalid or excessive guided evidence', 'INVALID_GUIDED_EVIDENCE', 422) from None


@router.get('/routing/guided-examples')
async def guided_examples(request: Request):
    repository = getattr(request.app.state, 'route_history_repository', None)
    if (not settings.enable_route_familiarity or not settings.public_synthetic_sample or
            repository is None or repository.namespace != 'synthetic'):
        raise StateError('Public synthetic examples disabled', 'SYNTHETIC_EXAMPLES_DISABLED', 403)
    try:
        return {'source': 'synthetic', 'examples': await repository.guided_examples()}
    except Exception:
        raise StateError('Synthetic examples unavailable', 'SYNTHETIC_EXAMPLES_UNAVAILABLE', 503) from None


@router.get('/routing/coverage-report')
async def coverage_report():
    if not settings.enable_route_familiarity or not settings.public_synthetic_sample or settings.route_history_namespace != 'synthetic':
        raise StateError('Public synthetic report disabled', 'SYNTHETIC_EXAMPLES_DISABLED', 403)
    path = Path(__file__).resolve().parents[4] / 'runtime/h3-coverage/coverage-summary.json'
    try:
        if path.stat().st_size > 500_000:
            raise ValueError('Report size exceeded')
        report = json.loads(path.read_text(encoding='utf-8'))
        if report.get('status') != 'PASS' or report.get('source') != 'synthetic':
            raise ValueError('Invalid report provenance')
        return report
    except (OSError, ValueError):
        raise StateError('Coverage report unavailable', 'COVERAGE_REPORT_UNAVAILABLE', 503) from None


async def _read_bounded_body(request: Request, limit: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise StateError("Invalid completed route", "INVALID_ROUTE", 422)
        body.extend(chunk)
    return bytes(body)


class CompletedRoute(FrozenModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    driver_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    trip_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    completed_at: datetime
    started_at: datetime | None = None
    polyline: str = Field(min_length=1, max_length=100_000)

    _completed_at = field_validator("completed_at")(aware_utc)

    @field_validator("started_at")
    @classmethod
    def validate_start(cls, value):
        return aware_utc(value) if value is not None else None


@router.post("/internal/route-familiarity/routes", dependencies=[Depends(authorize_ingestion)])
async def ingest_completed_route(request: Request, response: Response):
    if not settings.enable_route_familiarity:
        raise StateError("Route familiarity ingestion is disabled", "ROUTE_FAMILIARITY_DISABLED", 503)
    service = getattr(request.app.state, "route_history_ingestion", None)
    if service is None:
        raise StateError("Route history ingestion unavailable", "ROUTE_HISTORY_UNAVAILABLE", 503)
    try:
        declared_size = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    if declared_size > 105_000:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422)
    try:
        body = await _read_bounded_body(request, 105_000)
        payload = CompletedRoute.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError, ValueError):
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    try:
        args = (payload.driver_id, payload.trip_id, payload.completed_at.astimezone(UTC), payload.polyline)
        _, created = (await service.ingest(*args, started_at=payload.started_at)
                      if payload.started_at is not None else await service.ingest(*args))
    except ValueError:
        raise StateError("Invalid completed route", "INVALID_ROUTE", 422) from None
    except StateError:
        raise
    except Exception:
        raise StateError("Route history ingestion unavailable", "ROUTE_HISTORY_UNAVAILABLE", 503) from None
    response.status_code = 201 if created else 200
    return {"status": "created" if created else "already_ingested"}


@router.post('/internal/route-deviations/trips', dependencies=[Depends(authorize_ingestion)])
async def ingest_guided_trip(request: Request, response: Response):
    repository = getattr(request.app.state, 'route_history_repository', None)
    if not settings.enable_route_familiarity or repository is None:
        raise StateError('Guided history ingestion unavailable', 'GUIDED_HISTORY_UNAVAILABLE', 503)
    try:
        body = await _read_bounded_body(request, 2_000_000)
        payload = GuidedTrip.model_validate(json.loads(body))
        analysis = await run_in_threadpool(analyze_guided_trip, payload)
    except (ValueError, ValidationError, UnicodeDecodeError, SimilarityWorkLimitExceeded):
        raise StateError('Invalid or excessive guided evidence', 'INVALID_GUIDED_EVIDENCE', 422) from None
    try:
        created = await repository.ingest_guided_trip(payload.model_dump(mode='json'), analysis)
    except StateError:
        raise
    except Exception:
        raise StateError('Guided evidence storage unavailable', 'GUIDED_HISTORY_UNAVAILABLE', 503) from None
    response.status_code = 201 if created else 200
    return {'status': 'created' if created else 'already_ingested', 'comparable': analysis['comparable'],
            'uncertain_intervals': analysis['uncertain_intervals']}


@router.get('/routing/departure-heatmap')
async def departure_heatmap(request: Request, resolution: int = Query(default=9, ge=5, le=10),
                            as_of_iso: datetime | None = None, cohort: Literal['all', 'coverage', 'stress'] = 'all'):
    as_of = as_of_iso or datetime.now(UTC)
    if as_of.tzinfo is None:
        raise StateError('As-of time requires a timezone', 'INVALID_AS_OF', 422)
    metadata = {'resolution': resolution, 'lookback_days': 7, 'as_of_iso': as_of.isoformat(),
                'window_start_iso': (as_of - timedelta(days=7)).isoformat(),
                'origin_semantics': 'LAST_UNAMBIGUOUS_GUIDED_LOCATION_BEFORE_CONFIRMED_DEPARTURE'}
    if not settings.enable_route_familiarity:
        return {**metadata, 'status': 'DISABLED', 'cells': {}}
    repository = getattr(request.app.state, 'route_history_repository', None)
    if repository is None:
        raise StateError('Departure statistics unavailable', 'DEPARTURE_HISTORY_UNAVAILABLE', 503)
    try:
        result = (await repository.departure_heatmap(as_of, resolution) if cohort == 'all' else
                  await repository.departure_heatmap(as_of, resolution, cohort))
        return {**metadata, **result}
    except StateError:
        raise
    except Exception:
        raise StateError('Departure statistics unavailable', 'DEPARTURE_HISTORY_UNAVAILABLE', 503) from None
