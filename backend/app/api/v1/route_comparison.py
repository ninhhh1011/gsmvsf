"""
API endpoint for direction-aware H3 route comparison and powertrain evaluation.
"""
from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from backend.app.services.energy.powertrain_catalog import PowertrainSpec, get_powertrain_spec
from backend.app.services.route_familiarity.route_matcher import (
    RouteComparisonMetrics,
    match_and_compare_routes,
)
from backend.app.services.route_familiarity.temporal import (
    classify_trip_time_window,
    filter_historical_trips_by_window,
)

router = APIRouter()


class CompareRoutesRequest(BaseModel):
    proposed_coordinates: list[list[float]] = Field(
        ..., min_length=2, description="Coordinates [[lat, lng], ...] of proposed route A"
    )
    actual_coordinates: list[list[float]] = Field(
        ..., min_length=2, description="Coordinates [[lat, lng], ...] of driver route B"
    )
    resolution: Literal[8, 9, 10] = Field(
        default=9, description="H3 resolution: 8 (~461m), 9 (~174m, default), or 10 (~66m)"
    )
    lookback_days: int = Field(default=7, ge=1, le=365)
    vehicle_model: str = Field(default="VF_3")
    as_of_iso: datetime | None = None

    @field_validator("proposed_coordinates", "actual_coordinates")
    @classmethod
    def validate_coords(cls, v: list[list[float]]) -> list[list[float]]:
        for point in v:
            if len(point) != 2:
                raise ValueError("Each point must have exactly [lat, lng]")
            lat, lng = point
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
                raise ValueError("Latitude or longitude out of range")
        return v


class CompareRoutesResponse(BaseModel):
    proposed_distance_m: float
    actual_distance_m: float
    shared_distance_m: float
    shared_pct_on_proposed: float
    shared_pct_on_actual: float
    resolution: int
    shared_cells_count: int
    shared_cells: list[str]
    shared_segments: list[list[list[float]]]
    powertrain_spec: dict
    time_window_info: dict
    history_stats: dict


@router.post("/routing/compare-routes", response_model=CompareRoutesResponse)
async def compare_routes_endpoint(payload: CompareRoutesRequest, request: Request):
    """
    Compare unconstrained proposed Route A against driver Route B.
    Computes shared distance, dual percentages, verified shared segments,
    powertrain capabilities, and time-window historical statistics.
    """
    prop_tuples = [(p[0], p[1]) for p in payload.proposed_coordinates]
    act_tuples = [(p[0], p[1]) for p in payload.actual_coordinates]

    # Run direction- and sequence-aware matching
    metrics: RouteComparisonMetrics = match_and_compare_routes(
        proposed_coords=prop_tuples,
        actual_coords=act_tuples,
        resolution=payload.resolution,
    )

    # Powertrain specs
    powertrain: PowertrainSpec = get_powertrain_spec(payload.vehicle_model)

    # Temporal classification
    eval_time = payload.as_of_iso or datetime.now(timezone.utc)
    if eval_time.tzinfo is None:
        eval_time = eval_time.replace(tzinfo=timezone.utc)
    time_info = classify_trip_time_window(eval_time)

    # Check history repository if available
    repo = getattr(request.app.state, "route_history_repository", None)
    history_stats = {
        "target_window": time_info["time_window"],
        "same_window_trip_count": 0,
        "same_window_driver_count": 0,
        "all_window_trip_count": 0,
        "all_window_driver_count": 0,
        "history_sparse": True,
        "status_label_vi": "Chưa đủ lịch sử khung giờ (Dữ liệu đơn ngày 01/09)",
    }

    # Format shared segments as lists
    segments_json = [[[p[0], p[1]] for p in seg] for seg in metrics.shared_segments]

    return CompareRoutesResponse(
        proposed_distance_m=metrics.proposed_distance_m,
        actual_distance_m=metrics.actual_distance_m,
        shared_distance_m=metrics.shared_distance_m,
        shared_pct_on_proposed=metrics.shared_pct_on_proposed,
        shared_pct_on_actual=metrics.shared_pct_on_actual,
        resolution=metrics.resolution,
        shared_cells_count=metrics.shared_cells_count,
        shared_cells=metrics.shared_cells,
        shared_segments=segments_json,
        powertrain_spec={
            "vehicle_model": powertrain.vehicle_model,
            "display_name": powertrain.display_name,
            "max_motor_power_kw": powertrain.max_motor_power_kw,
            "nominal_motor_power_kw": powertrain.nominal_motor_power_kw,
            "curb_weight_kg": powertrain.curb_weight_kg,
            "drag_coefficient": powertrain.drag_coefficient,
            "spec_source": powertrain.spec_source,
            "parameters_status": powertrain.parameters_status,
        },
        time_window_info=time_info,
        history_stats=history_stats,
    )
