"""Synchronous Week 4 APIs; operational writes use a separate internal token."""
import hmac
import hashlib
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from backend.app.config import settings
from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.demand.models import DemandContext, RequestedServiceType, ServiceType
from backend.app.dependencies import get_demand_service
from backend.app.services.ranking.models import CandidateSearchEvidence, RecommendationResult
from backend.app.services.realtime.location import resolve_shared_current_location
from backend.app.services.snapshots.models import (
    FrozenModel,
    QueueSnapshot,
    StateError,
    StationStateSnapshot,
    TrafficSnapshot,
    aware_utc,
)
from pydantic import ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_driver_identity(driver_id: str, signature: str | None, secret: str) -> bool:
    """Verify the trusted gateway's lowercase HMAC-SHA256 over the exact driver ID."""
    if signature is None or len(signature) != 64 or any(c not in '0123456789abcdef' for c in signature):
        return False
    expected = hmac.new(secret.encode(), driver_id.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


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
    distance_travelled_km: float | None = Field(None, ge=0)
    planned_trip_distance_km: float | None = Field(None, ge=0)
    remaining_energy_kwh: float | None = Field(None, ge=0)
    consumption_wh_per_km: float | None = Field(None, gt=0)
    minimum_safe_soc_pct: float | None = Field(None, ge=0, le=100)
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
    avoid_congestion: bool = True
    plan_mode: Literal['BEFORE_DESTINATION', 'AFTER_DESTINATION'] = 'BEFORE_DESTINATION'

    @model_validator(mode='after')
    def destination_pair(self):
        if (self.destination_latitude is None) != (self.destination_longitude is None):
            raise ValueError('Both destination coordinates are required together')
        if self.plan_mode == 'AFTER_DESTINATION' and self.destination_latitude is None:
            raise ValueError('After-destination planning requires a destination')
        return self


@router.post('/ranking/candidates', response_model=CandidateSearchEvidence)
async def search_for_ranking(request: CandidateSearchRequest, workflow=Depends(get_workflow)):
    try:
        return await workflow.search(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/ranking', response_model=RecommendationResult,
             response_model_exclude={'familiarity': True,
                                     'ranked_candidates': {'__all__': {'familiarity'}}})
async def rank(request: RankRequest, workflow=Depends(get_workflow)):
    evidence = await workflow.repository.get_search(request.candidate_search_id)
    return await workflow.ranking.recommend(evidence, request.request_time, request.top_n)


@router.post('/recommend', response_model=RecommendationResult)
async def recommend(request: RecommendRequest, request_obj: Request,
                    x_driver_identity_signature: str | None = Header(None),
                    workflow=Depends(get_workflow)):
    started = perf_counter()
    try:
        context = request.context
        if settings.enable_route_familiarity:
            if not context.driver_id or x_driver_identity_signature is None:
                raise HTTPException(401, 'Driver identity signature required')
            if not verify_driver_identity(context.driver_id, x_driver_identity_signature,
                                          settings.route_familiarity_identity_secret):
                raise HTTPException(403, 'Invalid driver identity signature')

        location = await resolve_shared_current_location(context.driver_id, context.raw_latitude,
            context.raw_longitude, context.road_segment_id, context.timestamp,
            getattr(request_obj.app.state, 'driver_state_manager', None))

        repo = getattr(workflow, 'repository', None)
        road_seg = location.road_segment_id
        if road_seg is None and location.latitude is not None and repo is not None and hasattr(repo, 'get_nearest_segment'):
            try:
                road_seg = await repo.get_nearest_segment(location.latitude, location.longitude)
            except Exception:
                pass

        context = context.model_copy(update={'raw_latitude': location.latitude,
            'raw_longitude': location.longitude, 'road_segment_id': road_seg})
        location_ms = (perf_counter() - started) * 1000
        demand_started = perf_counter()
        demand = get_demand_service(request_obj)
        energy = (demand.process_driver_request(context, request.requested_service)
                  if request.requested_service is not None else demand.evaluate_auto_demand(context))
        demand_ms = (perf_counter() - demand_started) * 1000
        # Invalid energy requests retain Week 4 validation; no-service needs no position.
        if (energy.need_service and energy.request_valid and energy.reason_code not in
                ('MISSING_DATA', 'INVALID_STATE', 'STALE_STATE') and location.latitude is None):
            raise StateError('No current location available at request time', 'LOCATION_UNAVAILABLE', 422)

        constraints = None
        repo = getattr(workflow, 'repository', None)
        if request.avoid_congestion and repo is not None and hasattr(repo, 'get_congested_polygons'):
            avoid_areas = await repo.get_congested_polygons(min_delay=1.6, as_of=context.timestamp,
                traffic_fresh_s=workflow.ranking.policy.traffic_fresh_s)
            if avoid_areas:
                from backend.app.services.routing.models import RouteConstraints
                constraints = RouteConstraints(custom={"avoid_areas": avoid_areas, "congestion_priority": 0.05})

        search = CandidateSearchRequest(energy_request=energy,
            destination_latitude=request.destination_latitude,
            destination_longitude=request.destination_longitude,
            destination_node_id=request.destination_node_id,
            constraints=constraints)
        if request.plan_mode == 'AFTER_DESTINATION':
            from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile
            from backend.app.services.routing.engine import raise_for_routing_failure
            prefix = await workflow.routing_engine.route(RouteRequest(
                origin=Position(latitude=location.latitude, longitude=location.longitude),
                destination=Position(latitude=request.destination_latitude, longitude=request.destination_longitude),
                profile=VehicleRoutingProfile(vehicle_id=context.vehicle_id, vehicle_model=energy.vehicle_model,
                                              vehicle_category=energy.vehicle_type), constraints=constraints))
            raise_for_routing_failure(prefix)
            remaining = energy.estimated_remaining_range_km
            if (prefix.status != RouteStatus.SUCCESS or remaining is None or
                    remaining < prefix.distance_m / 1000 + (energy.safety_reserve_km or 0)):
                raise StateError('Destination cannot be reached with current energy', 'DESTINATION_ENERGY_INFEASIBLE', 409)
            energy = energy.model_copy(update={'latitude': request.destination_latitude,
                'longitude': request.destination_longitude, 'road_segment_id': None,
                'estimated_remaining_range_km': remaining - prefix.distance_m / 1000,
                'remaining_trip_distance_km': 0})
            search = CandidateSearchRequest(energy_request=energy, constraints=constraints,
                prefix_duration_s=prefix.duration_s, prefix_distance_m=prefix.distance_m,
                prefix_geometry=prefix.geometry, prefix_traffic_segment_id=location.road_segment_id or road_seg)
        metrics = {}
        result = await workflow.recommend(search, top_n=request.top_n, metrics=metrics)
        metrics.setdefault('timings_ms', {}).update(location_resolution=location_ms, demand=demand_ms,
                                                    total=(perf_counter() - started) * 1000)
        return result.model_copy(update=metrics | {'location_source': location.source,
                                                 'location_timestamp': location.timestamp})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        from backend.app.core.metrics import observe_recommendation
        observe_recommendation('request', perf_counter() - started)


class StationPlanRequest(RecommendRequest):
    station_id: str = Field(min_length=1, max_length=100)
    service_type: ServiceType


@router.post('/station-plan')
async def station_plan(request: StationPlanRequest, request_obj: Request,
                       x_driver_identity_signature: str | None = Header(None),
                       workflow=Depends(get_workflow)):
    """Confirm the selected pair against current backend eligibility and routing policy."""
    from backend.app.services.routing.models import Position, RouteRequest, RouteStatus, VehicleRoutingProfile
    from backend.app.services.routing.engine import raise_for_routing_failure
    from backend.app.services.route_familiarity.signature import decode_polyline
    recommendation_request = RecommendRequest.model_validate(
        request.model_dump(exclude={'station_id', 'service_type', 'top_n'}) | {'top_n': None})
    result = await recommend(recommendation_request, request_obj, x_driver_identity_signature, workflow)
    evidence = await workflow.repository.get_search(result.candidate_search_id)
    selected = next((row for row in result.ranked_candidates
                     if row.station_id == request.station_id and row.service_type == request.service_type), None)
    if selected is None:
        rejected = next((row for row in evidence.result.candidates if row.station_id == request.station_id
                         and row.service_type == request.service_type), None)
        error = StateError('Selected station/service is no longer eligible', 'STATION_PLAN_UNAVAILABLE', 409)
        error.detail['eligibility_reason'] = rejected.reason.value if rejected else 'PAIR_NOT_FOUND'
        raise error
    energy = evidence.energy_request
    station = workflow.catalog.get_station(request.station_id)
    profile = VehicleRoutingProfile(vehicle_id=energy.vehicle_id, vehicle_model=energy.vehicle_model,
                                    vehicle_category=energy.vehicle_type)
    station_position = Position(latitude=station.latitude, longitude=station.longitude)
    positions = [Position(latitude=energy.latitude, longitude=energy.longitude), station_position]
    if request.plan_mode == 'AFTER_DESTINATION':
        location = await resolve_shared_current_location(request.context.driver_id, request.context.raw_latitude,
            request.context.raw_longitude, request.context.road_segment_id, request.context.timestamp,
            getattr(request_obj.app.state, 'driver_state_manager', None))
        positions.insert(0, Position(latitude=location.latitude, longitude=location.longitude))
    elif request.destination_latitude is not None:
        positions.append(Position(latitude=request.destination_latitude, longitude=request.destination_longitude))
    geometry, waypoints, distance, duration = [], [], 0.0, 0.0
    roles = (['PASSENGER_DESTINATION', 'STATION'] if request.plan_mode == 'AFTER_DESTINATION' else
             ['STATION', 'PASSENGER_DESTINATION'] if request.destination_latitude is not None else ['STATION'])
    for role, origin, destination in zip(roles, positions, positions[1:]):
        leg = await workflow.routing_engine.route(RouteRequest(origin=origin, destination=destination,
            profile=profile, constraints=evidence.constraints))
        raise_for_routing_failure(leg)
        if leg.status != RouteStatus.SUCCESS or not leg.geometry:
            raise StateError('Selected navigation geometry is unavailable', 'STATION_PLAN_UNAVAILABLE', 409)
        points = [[lon, lat] for lat, lon in decode_polyline(leg.geometry)]
        geometry.extend(points[1:] if geometry and points[0] == geometry[-1] else points)
        waypoints.append({'role': role, 'geometry_index': len(geometry) - 1,
                          'longitude': geometry[-1][0], 'latitude': geometry[-1][1]})
        distance += leg.distance_m
        duration += leg.duration_s
    if abs(distance - selected.features.distance_to_station_m -
           (selected.features.distance_station_to_dest_m or 0)) > max(5, distance * 0.001):
        raise StateError('Route changed during selection', 'STATION_PLAN_UNAVAILABLE', 409)
    expected_duration = (selected.features.base_travel_duration_s + evidence.prefix_duration_s +
                         (selected.features.duration_station_to_dest_s or 0))
    if abs(duration - expected_duration) > max(0.3, duration * 0.001):
        raise StateError('Route timing changed during selection', 'STATION_PLAN_UNAVAILABLE', 409)
    chosen = [row for row in evidence.result.candidates
              if row.station_id == request.station_id and row.service_type == request.service_type]
    selected_evidence = evidence.model_copy(update={'result': evidence.result.model_copy(update={
        'candidates': chosen, 'eligible_count': 1, 'total_candidates_evaluated': 1})})
    confirmed = await workflow.ranking.recommend(selected_evidence, request_time=datetime.now(UTC))
    from backend.app.services.ranking.service import rank_features
    from backend.app.services.route_familiarity.service import FamiliarityAssessment
    assessments = {}
    for row in result.ranked_candidates:
        if row.familiarity is not None and row.familiarity.status != 'DISABLED':
            values = row.familiarity.model_dump()
            assessments[(row.station_id, row.service_type.value)] = FamiliarityAssessment(**{
                key: value for key, value in values.items() if key in FamiliarityAssessment.__dataclass_fields__})
    refreshed = rank_features([row.features for row in confirmed.ranked_candidates], assessments,
                              include_familiarity=True, time_reference_s=selected.time_reference_s)
    original_rank = selected.rank
    selected = next(row for row in refreshed
                    if row.station_id == request.station_id and row.service_type == request.service_type
                    ).model_copy(update={'rank': original_rank})
    return {'station_id': request.station_id, 'service_type': request.service_type,
            'plan_mode': request.plan_mode,
            'goal_role': 'PASSENGER_DESTINATION' if request.destination_latitude is not None and request.plan_mode != 'AFTER_DESTINATION' else 'STATION',
            'route': {'geometry': geometry, 'distance_m': distance, 'duration_s': duration},
            'waypoints': waypoints,
            'ranked_candidate': selected,
            'projected_station_range_km': (energy.estimated_remaining_range_km -
                (selected.features.distance_to_station_m - evidence.prefix_distance_m) / 1000
                if energy.estimated_remaining_range_km is not None else None),
            'constraints': evidence.constraints}


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


@router.post('/snapshots/simulate-tick', dependencies=[Depends(authorize_ingestion)])
async def trigger_simulation_tick(request: Request):
    """Trigger an on-demand simulation tick (Problem D)."""
    simulator = getattr(request.app.state, 'realtime_simulator', None)
    ingestion = getattr(request.app.state, 'snapshot_ingestion', None)
    if simulator is None or ingestion is None:
        raise HTTPException(503, 'Snapshot simulator or ingestion service not initialized')
    try:
        now = datetime.now(UTC)
        count = await simulator.tick(ingestion, timestamp=now)
        return {
            'status': 'ok',
            'snapshots_ingested': count,
            'timestamp': now.isoformat(),
        }
    except Exception as exc:
        logger.warning('Simulation tick failed: %s', exc, exc_info=True)
        raise HTTPException(500, f'Simulation tick failed: {exc}')
