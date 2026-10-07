"""
FastAPI router for Week 2 Demand Detection and Energy Service Requests.

Provides:
- POST /api/v1/demand/evaluate: Evaluate telemetry for auto-detected demand
- POST /api/v1/demand/request: Submit explicit driver service request
- GET  /api/v1/vehicles/{vehicle_id}/capability: Query vehicle capability
- GET  /api/v1/vehicles/models/{model_name}/capability: Query model capability
- POST /api/v1/drivers/{driver_id}/demand/evaluate: Evaluate driver demand using Week 1 state
"""

from datetime import datetime

from backend.app.services.demand.capability import (
    UnknownVehicleError,
    UnknownVehicleModelError,
    get_capability_resolver,
)
from backend.app.services.demand.models import (
    DemandContext,
    EnergyServiceRequest,
    RequestedServiceType,
    VehicleCapability,
)
from backend.app.services.demand.service import get_demand_service
from backend.app.services.realtime.location import resolve_current_location
from fastapi import APIRouter, HTTPException, status
from fastapi import Path as FPath
from pydantic import BaseModel, Field

router = APIRouter()


class EvaluateDemandApiRequest(BaseModel):
    """Payload to evaluate auto demand."""
    vehicle_id: str
    driver_id: str | None = None
    trip_id: str | None = None
    timestamp: datetime | None = None
    current_soc_pct: float | None = Field(None, description="Battery SOC percentage (0-100)")
    estimated_remaining_range_km: float | None = None
    remaining_trip_distance_km: float | None = None
    distance_travelled_km: float | None = None
    planned_trip_distance_km: float | None = None
    safety_reserve_km: float | None = None
    consumption_wh_per_km: float | None = None
    minimum_safe_soc_pct: float | None = None
    raw_latitude: float | None = None
    raw_longitude: float | None = None
    road_segment_id: str | None = None


class DriverIntentApiRequest(BaseModel):
    """Payload to submit explicit driver intent."""
    vehicle_id: str
    requested_service_type: RequestedServiceType
    driver_id: str | None = None
    trip_id: str | None = None
    timestamp: datetime | None = None
    current_soc_pct: float | None = None
    estimated_remaining_range_km: float | None = None
    remaining_trip_distance_km: float | None = None
    raw_latitude: float | None = None
    raw_longitude: float | None = None
    road_segment_id: str | None = None


@router.post(
    "/demand/evaluate",
    response_model=EnergyServiceRequest,
    summary="Evaluate auto-detected energy service demand",
)
async def evaluate_demand(payload: EvaluateDemandApiRequest) -> EnergyServiceRequest:
    """
    Evaluate vehicle telemetry to determine if an energy service is needed.
    Returns canonical EnergyServiceRequest.
    """
    resolver = get_capability_resolver()
    try:
        resolver.resolve_by_vehicle_id(payload.vehicle_id)
    except UnknownVehicleError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnknownVehicleModelError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    ctx = DemandContext(
        vehicle_id=payload.vehicle_id,
        driver_id=payload.driver_id,
        trip_id=payload.trip_id,
        timestamp=payload.timestamp or datetime.utcnow(),
        current_soc_pct=payload.current_soc_pct,
        estimated_remaining_range_km=payload.estimated_remaining_range_km,
        remaining_trip_distance_km=payload.remaining_trip_distance_km,
        distance_travelled_km=payload.distance_travelled_km,
        planned_trip_distance_km=payload.planned_trip_distance_km,
        safety_reserve_km=payload.safety_reserve_km,
        consumption_wh_per_km=payload.consumption_wh_per_km,
        minimum_safe_soc_pct=payload.minimum_safe_soc_pct,
        raw_latitude=payload.raw_latitude,
        raw_longitude=payload.raw_longitude,
        road_segment_id=payload.road_segment_id,
    )

    demand_service = get_demand_service()
    return demand_service.evaluate_auto_demand(ctx)


@router.post(
    "/demand/request",
    response_model=EnergyServiceRequest,
    summary="Process explicit driver service request",
)
async def submit_driver_request(payload: DriverIntentApiRequest) -> EnergyServiceRequest:
    """
    Process an explicit energy service request from the driver (CHARGING, BATTERY_SWAP, ANY).
    Validates capability and returns canonical EnergyServiceRequest.
    """
    resolver = get_capability_resolver()
    try:
        resolver.resolve_by_vehicle_id(payload.vehicle_id)
    except UnknownVehicleError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnknownVehicleModelError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    ctx = DemandContext(
        vehicle_id=payload.vehicle_id,
        driver_id=payload.driver_id,
        trip_id=payload.trip_id,
        timestamp=payload.timestamp or datetime.utcnow(),
        current_soc_pct=payload.current_soc_pct,
        estimated_remaining_range_km=payload.estimated_remaining_range_km,
        remaining_trip_distance_km=payload.remaining_trip_distance_km,
        raw_latitude=payload.raw_latitude,
        raw_longitude=payload.raw_longitude,
        road_segment_id=payload.road_segment_id,
    )

    demand_service = get_demand_service()
    return demand_service.process_driver_request(ctx, payload.requested_service_type)


@router.get(
    "/vehicles/{vehicle_id}/capability",
    response_model=VehicleCapability,
    summary="Get vehicle capability by fleet vehicle_id",
)
async def get_vehicle_capability(
    vehicle_id: str = FPath(..., description="Vehicle ID (e.g. V0001)"),
) -> VehicleCapability:
    """Query capability for a specific fleet vehicle ID."""
    resolver = get_capability_resolver()
    try:
        return resolver.resolve_by_vehicle_id(vehicle_id)
    except UnknownVehicleError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnknownVehicleModelError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get(
    "/vehicles",
    response_model=list[VehicleCapability],
    summary="List all registered VinFast vehicle models with battery & consumption specs",
)
async def list_vehicle_models() -> list[VehicleCapability]:
    """List all registered VinFast vehicle models."""
    resolver = get_capability_resolver()
    return [resolver.resolve_by_model(m) for m in resolver.list_all_models()]


class EnergyStepRequest(BaseModel):
    vehicle_model: str = Field(..., description="VinFast model name (e.g. VF_3, VF_8, EVO)")
    distance_km: float = Field(..., ge=0, description="Distance traveled in km")
    current_soc_pct: float = Field(..., ge=0, le=100, description="Current SOC percentage")
    consumption_wh_per_km: float | None = Field(None, gt=0, description="Optional override consumption")


class EnergyStepResponse(BaseModel):
    vehicle_model: str
    distance_km: float
    previous_soc_pct: float
    current_soc_pct: float
    soc_drop_pct: float
    energy_consumed_kwh: float
    estimated_remaining_range_km: float
    usable_capacity_kwh: float
    consumption_wh_per_km: float


@router.post(
    "/vehicles/energy-step",
    response_model=EnergyStepResponse,
    summary="Authoritative energy & SOC depletion calculation for vehicle movement",
)
async def calculate_energy_step(payload: EnergyStepRequest) -> EnergyStepResponse:
    """Calculate battery depletion and new SOC when vehicle moves."""
    resolver = get_capability_resolver()
    try:
        cap = resolver.resolve_by_model(payload.vehicle_model)
    except UnknownVehicleModelError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    effective_cons = payload.consumption_wh_per_km or cap.get_effective_consumption_wh_per_km()
    soc_drop = cap.calculate_soc_drop(payload.distance_km, effective_cons)
    new_soc = max(0.0, payload.current_soc_pct - soc_drop)
    new_range = cap.estimate_range_km(new_soc, effective_cons)
    energy_kwh = payload.distance_km * (effective_cons / 1000.0)

    return EnergyStepResponse(
        vehicle_model=cap.vehicle_model,
        distance_km=round(payload.distance_km, 3),
        previous_soc_pct=round(payload.current_soc_pct, 2),
        current_soc_pct=round(new_soc, 2),
        soc_drop_pct=round(soc_drop, 2),
        energy_consumed_kwh=round(energy_kwh, 4),
        estimated_remaining_range_km=round(new_range, 2),
        usable_capacity_kwh=cap.usable_capacity_kwh or cap.total_battery_capacity_kwh,
        consumption_wh_per_km=round(effective_cons, 1),
    )


@router.get(
    "/vehicles/models/{model_name}/capability",
    response_model=VehicleCapability,
    summary="Get vehicle capability by model name",
)
async def get_model_capability(
    model_name: str = FPath(..., description="Model name (e.g. VF_5, EVO)"),
) -> VehicleCapability:
    """Query capability for a specific VinFast vehicle model."""
    resolver = get_capability_resolver()
    try:
        return resolver.resolve_by_model(model_name)
    except UnknownVehicleModelError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/drivers/{driver_id}/demand/evaluate",
    response_model=EnergyServiceRequest,
    summary="Evaluate demand for driver incorporating Week 1 realtime tracking state",
)
async def evaluate_driver_demand_with_realtime_state(
    driver_id: str = FPath(..., description="Driver ID (e.g. D0001)"),
    payload: EvaluateDemandApiRequest = ...,
) -> EnergyServiceRequest:
    """
    Evaluate demand for an active driver, automatically incorporating Week 1
    realtime map-matching state (matched coordinates, road segment ID) if active.
    """
    request_time = payload.timestamp if payload.timestamp is not None else datetime.utcnow()
    location = resolve_current_location(driver_id, payload.raw_latitude,
                                        payload.raw_longitude, payload.road_segment_id, request_time)

    # Construct context
    ctx = DemandContext(
        vehicle_id=payload.vehicle_id,
        driver_id=driver_id,
        trip_id=payload.trip_id,
        timestamp=request_time,
        current_soc_pct=payload.current_soc_pct,
        estimated_remaining_range_km=payload.estimated_remaining_range_km,
        remaining_trip_distance_km=payload.remaining_trip_distance_km,
        distance_travelled_km=payload.distance_travelled_km,
        planned_trip_distance_km=payload.planned_trip_distance_km,
        safety_reserve_km=payload.safety_reserve_km,
        consumption_wh_per_km=payload.consumption_wh_per_km,
        minimum_safe_soc_pct=payload.minimum_safe_soc_pct,
        raw_latitude=location.latitude,
        raw_longitude=location.longitude,
        road_segment_id=location.road_segment_id,
    )

    demand_service = get_demand_service()
    return demand_service.evaluate_auto_demand(ctx)
