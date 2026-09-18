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
from typing import Optional
from fastapi import APIRouter, HTTPException, Path as FPath, status
from pydantic import BaseModel, Field

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
from backend.app.services.realtime.state import get_state_store

router = APIRouter()


class EvaluateDemandApiRequest(BaseModel):
    """Payload to evaluate auto demand."""
    vehicle_id: str
    driver_id: Optional[str] = None
    trip_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    current_soc_pct: Optional[float] = Field(None, description="Battery SOC percentage (0-100)")
    estimated_remaining_range_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    distance_travelled_km: Optional[float] = None
    planned_trip_distance_km: Optional[float] = None
    safety_reserve_km: Optional[float] = None
    consumption_wh_per_km: Optional[float] = None
    minimum_safe_soc_pct: Optional[float] = None
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    road_segment_id: Optional[str] = None


class DriverIntentApiRequest(BaseModel):
    """Payload to submit explicit driver intent."""
    vehicle_id: str
    requested_service_type: RequestedServiceType
    driver_id: Optional[str] = None
    trip_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    current_soc_pct: Optional[float] = None
    estimated_remaining_range_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    road_segment_id: Optional[str] = None


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
    store = get_state_store()
    driver_state = store.get(driver_id)

    # Extract location from Week 1 realtime state if not provided in payload
    lat = payload.raw_latitude
    lon = payload.raw_longitude
    seg_id = payload.road_segment_id

    if driver_state:
        if driver_state.last_matched_state:
            lat = lat or driver_state.last_matched_state.matched_latitude
            lon = lon or driver_state.last_matched_state.matched_longitude
            seg_id = seg_id or driver_state.last_matched_state.road_segment_id
        elif driver_state.observations:
            latest_obs = driver_state.observations[-1]
            lat = lat or latest_obs.latitude
            lon = lon or latest_obs.longitude

    # Construct context
    ctx = DemandContext(
        vehicle_id=payload.vehicle_id,
        driver_id=driver_id,
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
        raw_latitude=lat,
        raw_longitude=lon,
        road_segment_id=seg_id,
    )

    demand_service = get_demand_service()
    return demand_service.evaluate_auto_demand(ctx)
