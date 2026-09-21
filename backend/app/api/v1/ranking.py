"""Synchronous Week 4 APIs; operational writes use a separate internal token."""
import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import ConfigDict, Field, field_validator, model_validator

from backend.app.config import settings
from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.demand.models import DemandContext, RequestedServiceType
from backend.app.services.demand.service import get_demand_service
from backend.app.services.ranking.models import CandidateSearchEvidence, RecommendationResult
from backend.app.services.snapshots.models import (
    FrozenModel, QueueSnapshot, StateError, StationStateSnapshot, TrafficSnapshot, aware_utc,
)

router = APIRouter()


def get_workflow(request: Request):
    workflow = getattr(request.app.state, 'recommendation_workflow', None)
    if workflow is None:
        raise StateError('Snapshot backend not initialized')
    return workflow


def get_ingestion(request: Request):
    service = getattr(request.app.state, 'snapshot_ingestion', None)
    if service is None:
        raise StateError('Snapshot backend not initialized')
    return service


def authorize_ingestion(x_ingestion_token: str | None = Header(None)):
    if not settings.snapshot_ingestion_token:
        raise StateError('Internal snapshot ingestion is disabled until a token is configured',
                         'INGESTION_DISABLED', 503)
    if not x_ingestion_token:
        raise HTTPException(401, 'Ingestion token required')
    if not hmac.compare_digest(x_ingestion_token.encode(), settings.snapshot_ingestion_token.encode()):
        raise HTTPException(403, 'Invalid ingestion token')


class RankRequest(FrozenModel):
    candidate_search_id: str = Field(min_length=1, max_length=100)
    request_time: datetime | None = None
    top_n: int | None = Field(None, ge=1, le=1000)

    @field_validator('request_time')
    @classmethod
    def validate_time(cls, value):
        return aware_utc(value) if value is not None else None


class RecommendationTelemetry(DemandContext):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    timestamp: datetime
    current_soc_pct: float | None = Field(None, ge=0, le=100)
    estimated_remaining_range_km: float | None = Field(None, ge=0)
    remaining_trip_distance_km: float | None = Field(None, ge=0)
    safety_reserve_km: float | None = Field(None, ge=0)
    raw_latitude: float | None = Field(None, ge=-90, le=90)
    raw_longitude: float | None = Field(None, ge=-180, le=180)
    _time = field_validator('timestamp')(aware_utc)


class RecommendRequest(FrozenModel):
    context: RecommendationTelemetry
    requested_service: RequestedServiceType | None = None
    destination_latitude: float | None = Field(None, ge=-90, le=90)
    destination_longitude: float | None = Field(None, ge=-180, le=180)
    destination_node_id: str | None = None
    top_n: int | None = Field(None, ge=1, le=1000)

    @model_validator(mode='after')
    def destination_pair(self):
        if (self.destination_latitude is None) != (self.destination_longitude is None):
            raise ValueError('Both destination coordinates are required together')
        return self


@router.post('/ranking/candidates', response_model=CandidateSearchEvidence)
async def search_for_ranking(request: CandidateSearchRequest, workflow=Depends(get_workflow)):
    try:
        return await workflow.search(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/ranking', response_model=RecommendationResult)
async def rank(request: RankRequest, workflow=Depends(get_workflow)):
    evidence = await workflow.repository.get_search(request.candidate_search_id)
    return await workflow.ranking.recommend(evidence, request.request_time, request.top_n)


@router.post('/recommend', response_model=RecommendationResult)
async def recommend(request: RecommendRequest, workflow=Depends(get_workflow)):
    try:
        demand = get_demand_service()
        energy = (demand.process_driver_request(request.context, request.requested_service)
                  if request.requested_service else demand.evaluate_auto_demand(request.context))
        search = CandidateSearchRequest(energy_request=energy,
            destination_latitude=request.destination_latitude,
            destination_longitude=request.destination_longitude,
            destination_node_id=request.destination_node_id)
        return await workflow.recommend(search, top_n=request.top_n)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


async def ingest_snapshot(snapshot, response, service):
    saved, created = await service.ingest(snapshot)
    response.status_code = 201 if created else 200
    return {'snapshot_id': saved.snapshot_id, 'created': created,
            'timestamp': saved.timestamp, 'source': saved.source}


@router.post('/internal/snapshots/traffic', dependencies=[Depends(authorize_ingestion)])
async def ingest_traffic(snapshot: TrafficSnapshot, response: Response, service=Depends(get_ingestion)):
    return await ingest_snapshot(snapshot, response, service)


@router.post('/internal/snapshots/station', dependencies=[Depends(authorize_ingestion)])
async def ingest_station(snapshot: StationStateSnapshot, response: Response, service=Depends(get_ingestion)):
    return await ingest_snapshot(snapshot, response, service)


@router.post('/internal/snapshots/queue', dependencies=[Depends(authorize_ingestion)])
async def ingest_queue(snapshot: QueueSnapshot, response: Response, service=Depends(get_ingestion)):
    return await ingest_snapshot(snapshot, response, service)
