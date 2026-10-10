"""Offline whole-trip comparison with optional protected causal history evidence."""
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal

import h3
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from backend.app.api.v1.ranking import verify_driver_identity
from backend.app.config import settings
from backend.app.services.energy.powertrain_catalog import get_powertrain_spec
from backend.app.services.route_familiarity.constants import MAX_ROUTE_VERTICES
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.route_matcher import prepare_route, compare_prepared_routes, _lerp
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.similarity import SimilarityWorkLimitExceeded
from backend.app.services.route_familiarity.temporal import classify_trip_time_window
from backend.app.services.snapshots.models import aware_utc

router = APIRouter()


class CompareRoutesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    proposed_coordinates: list[list[float]] = Field(min_length=2, max_length=MAX_ROUTE_VERTICES)
    actual_coordinates: list[list[float]] = Field(min_length=2, max_length=MAX_ROUTE_VERTICES)
    resolution: Literal[8, 9, 10] = 9
    lookback_days: Literal[7, 30] = 7
    vehicle_model: str = Field(default="VF_3", min_length=1, max_length=100)
    as_of_iso: datetime | None = None
    driver_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")

    @field_validator("proposed_coordinates", "actual_coordinates")
    @classmethod
    def validate_coords(cls, points):
        for point in points:
            if len(point) != 2 or not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180:
                raise ValueError("Each point must be valid [latitude, longitude]")
        return points

    @field_validator("as_of_iso")
    @classmethod
    def validate_time(cls, value):
        return aware_utc(value) if value is not None else None


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
    proposed_cells: list[str]
    actual_cells: list[str]
    powertrain_spec: dict | None
    time_window_info: dict
    history_stats: dict
    comparison_mode: Literal["OFFLINE_WHOLE_TRIP"] = "OFFLINE_WHOLE_TRIP"
    geometry_source: str = "CALLER_SUPPLIED_OBSERVED_GEOMETRY"
    approximation_step_m: float = 10.0
    max_lateral_m: float = 45.0
    max_heading_diff_deg: float = 60.0


def _compare(payload):
    proposed = prepare_route(payload.proposed_coordinates, payload.resolution)
    actual = prepare_route(payload.actual_coordinates, payload.resolution)
    metrics = compare_prepared_routes(proposed, actual)
    # Keep the resolution-11 persistence index separate from comparison resolution.
    cells, weights = [], []
    for piece in proposed.pieces:
        midpoint = _lerp(piece.start, piece.end, 0.5)
        cell = h3.latlng_to_cell(*midpoint, 11)
        if cells and cells[-1] == cell:
            weights[-1] += piece.length_m
        else:
            cells.append(cell)
            weights.append(piece.length_m)
    signature = RouteSignature(tuple(cells), tuple(weights), proposed.distance_m, 11,
                               tuple(tuple(point) for point in payload.proposed_coordinates))
    return metrics, signature


@router.post("/routing/compare-routes", response_model=CompareRoutesResponse)
async def compare_routes_endpoint(payload: CompareRoutesRequest, request: Request):
    if payload.driver_id and settings.enable_route_familiarity:
        signed = request.headers.get("x-driver-identity-signature")
        if not signed:
            raise HTTPException(401, "Driver identity signature required")
        if not verify_driver_identity(payload.driver_id, signed, settings.route_familiarity_identity_secret):
            raise HTTPException(403, "Invalid driver identity signature")
    try:
        metrics, signature = await run_in_threadpool(_compare, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except SimilarityWorkLimitExceeded:
        raise HTTPException(422, {"error_code": "SIMILARITY_WORK_LIMIT"}) from None
    try:
        spec = asdict(get_powertrain_spec(payload.vehicle_model))
    except ValueError:
        spec = None
    evaluation_time = payload.as_of_iso or datetime.now(UTC)
    time_info = classify_trip_time_window(evaluation_time)
    stats = {"status": "NOT_REQUESTED", "target_window": time_info["time_window"],
             "lookback_days": payload.lookback_days, "same_window_trip_count": None,
             "same_window_driver_count": None, "all_window_trip_count": None,
             "all_window_driver_count": None, "history_sparse": None}
    if payload.driver_id:
        repo = getattr(request.app.state, "route_history_repository", None)
        stats["status"] = "DISABLED" if not settings.enable_route_familiarity else "UNAVAILABLE"
        if settings.enable_route_familiarity and repo is not None:
            try:
                assessment = (await RouteFamiliarityService(repo, lookback_days=payload.lookback_days).assess_many(
                    payload.driver_id, {("offline", "ROUTE"): signature}, evaluation_time))["offline", "ROUTE"]
                stats.update(status=assessment.status,
                             personal_supporting_trip_count=assessment.personal_trip_count,
                             personal_history_trip_count=assessment.personal_history_trip_count,
                             community_supporting_trip_count=assessment.community_trip_count,
                             community_supporting_driver_count=assessment.community_driver_count,
                             personal_adherence=assessment.personal_adherence,
                             familiarity_penalty_s=assessment.penalty_s,
                             history_truncated=assessment.history_truncated,
                             degraded_reason=assessment.degraded_reason)
            except Exception:
                # No route or driver identifiers are logged on history failure.
                stats["status"] = "UNAVAILABLE"
    return CompareRoutesResponse(**asdict(metrics), powertrain_spec=spec,
                                 time_window_info=time_info, history_stats=stats)
