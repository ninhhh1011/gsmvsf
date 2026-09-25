"""
Realtime GPS ingestion and map matching API endpoints.

POST /api/v1/drivers/{driver_id}/location - Ingest single GPS observation
GET /api/v1/drivers/{driver_id}/location - Get current driver state
GET /api/v1/drivers/{driver_id}/history - Get recent matched history
"""

import logging
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from backend.app.config import settings
from backend.app.services.realtime.state import (
    DriverStateStore,
    DriverTraceState,
    GPSObservation,
    MatchedState,
    get_state_store,
    reset_state_store,
)
from backend.app.services.realtime.trigger import HybridTrigger, get_default_policy
from backend.app.services.map_matching.models import MapMatchRequest, MapMatchResponse, GPSObservation as ServiceGPSObservation
from backend.app.services.map_matching.engine import MapMatchingEngineError, MapMatchingNoMatchError
from backend.app.services.graphhopper import resolve_vehicle_category
from backend.app.api.v1.map_match import get_map_matching_service
from backend.app.services.realtime.driver_state_manager import (
    get_driver_state_manager,
    DriverStateManager,
    DriverStateUnavailableError,
)
import psycopg2


logger = logging.getLogger(__name__)

router = APIRouter()


class MatchingStatus(str, Enum):
    """Status of the matching operation."""
    WARMING_UP = "WARMING_UP"
    GPS_ACCEPTED = "GPS_ACCEPTED"
    MATCHED = "MATCHED"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    NO_MATCH = "NO_MATCH"
    INVALID_GPS = "INVALID_GPS"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"
    GAP_RESET = "GAP_RESET"


# Request/Response Models
class LocationIngestionRequest(BaseModel):
    """Request to ingest a GPS observation."""
    vehicle_id: Optional[str] = None
    vehicle_category: Optional[Literal["EV_CAR", "EV_MOTORBIKE"]] = None
    observation_id: Optional[str] = None
    timestamp: datetime
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    speed_kmh: Optional[float] = Field(None, ge=0)
    heading_deg: Optional[float] = Field(None, ge=0, lt=360)
    accuracy_m: Optional[float] = Field(None, ge=0)


class LocationResponse(BaseModel):
    """Response with current driver state."""
    driver_id: str
    status: MatchingStatus
    trigger_reason: Optional[str] = None
    raw_position: Optional[dict] = None
    matched_position: Optional[dict] = None
    last_match_time: Optional[str] = None
    last_match_latency_ms: Optional[float] = None
    total_observations: int = 0
    total_match_calls: int = 0
    buffered_points: int = 0
    movement_since_match_m: float = 0.0
    is_stationary: bool = False
    message: Optional[str] = None


def _validate_observation(req: LocationIngestionRequest) -> tuple[bool, Optional[str]]:
    """Validate GPS observation."""
    # Check coordinates
    if not (-90 <= req.latitude <= 90):
        return False, "Invalid latitude"
    if not (-180 <= req.longitude <= 180):
        return False, "Invalid longitude"

    # Check timestamp is not in the future
    # Handle both naive and aware datetimes
    now = datetime.utcnow()
    ts = req.timestamp
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    if ts > now:
        return False, "Timestamp in the future"

    return True, None


async def _call_map_match(observations, vehicle_category=None, vehicle_id=None):
    if len(observations) < 2:
        return None, 0.0
    category = resolve_vehicle_category(vehicle_category, vehicle_id, driver_id=observations[0].driver_id)
    request = MapMatchRequest(
        trajectory_id=observations[0].driver_id, trip_id="realtime", vehicle_category=category,
        observations=[ServiceGPSObservation(
            observation_id=o.observation_id, trajectory_id=o.driver_id, trip_id="realtime",
            timestamp=o.timestamp.isoformat(), latitude=o.latitude, longitude=o.longitude,
            speed_kmh=o.speed_kmh, heading_deg=o.heading_deg, accuracy_m=o.accuracy_m,
        ) for o in observations],
    )
    start = time.perf_counter()
    try:
        result = await get_map_matching_service().match_trajectory(request)
        return result, (time.perf_counter() - start) * 1000
    except MapMatchingNoMatchError:
        return None, (time.perf_counter() - start) * 1000


async def _persist_state(driver_id: str, state: DriverTraceState):
    """Persist driver state to shared store. Raises error if unavailable."""
    state_manager = get_driver_state_manager()
    await state_manager.save(state)


async def _persist_state_with_retry(driver_id: str, state: DriverTraceState):
    """Persist driver state with CAS retry. Raises error if unavailable or retries exhausted."""
    state_manager = get_driver_state_manager()
    await state_manager.save_with_retry(state)


async def _add_observation_with_cas(
    driver_id: str,
    obs: GPSObservation,
    max_retries: int = 3,
) -> tuple[DriverTraceState, bool, bool, str]:
    """
    Add observation to driver state using CAS to prevent lost updates.

    This function:
    1. Reads current state from Redis
    2. Checks for stale observation
    3. Checks generation for reset detection
    4. Adds observation to state
    5. Attempts CAS save
    6. On conflict, re-reads and retries

    Returns:
        (state, stale, gap_reset, gap_reason): The final state and flags

    Raises:
        DriverStateUnavailableError: When Redis unavailable or retries exhausted
    """
    state_manager = get_driver_state_manager()

    # Normalize observation timestamp for comparison
    obs_ts = obs.timestamp
    if obs_ts.tzinfo is not None:
        obs_ts = obs_ts.replace(tzinfo=None)

    expected_generation = None  # Track generation to detect resets

    for attempt in range(max_retries):
        # Read current state
        state = await state_manager.get_or_create(driver_id)

        # Check generation - if reset occurred, start fresh
        if expected_generation is not None and state.generation != expected_generation:
            # Reset occurred during processing - start with fresh state
            logger.debug(
                f"Driver {driver_id}: generation changed from {expected_generation} to {state.generation}, "
                f"reset detected, starting fresh"
            )
            state = DriverTraceState(driver_id=driver_id)
            state.generation = state.generation  # Keep current generation

        expected_generation = state.generation

        # Check stale
        last_ts = state.last_observation_timestamp
        if last_ts and last_ts.tzinfo is not None:
            last_ts = last_ts.replace(tzinfo=None)

        if last_ts and obs_ts < last_ts:
            # Stale observation - return current state without modification
            return state, True, False, ""

        # Add observation
        gap_reset, gap_reason = state.add_observation(obs)

        # Try to persist with CAS
        try:
            await state_manager.save_with_retry(state)
            return state, False, gap_reset, gap_reason
        except DriverStateUnavailableError:
            raise
        except Exception:
            if attempt < max_retries - 1:
                # Retry - state may have changed
                continue
            raise

    raise DriverStateUnavailableError(
        f"Failed to add observation after {max_retries} retries"
    )


@router.post("/drivers/{driver_id}/location", response_model=LocationResponse)
async def ingest_location(
    driver_id: str,
    request: LocationIngestionRequest,
) -> LocationResponse:
    """
    Ingest a single GPS observation for a driver.

    This endpoint:
    1. Validates the observation
    2. Appends to driver's trace state
    3. Evaluates trigger policy
    4. Calls map matching if triggered
    5. Returns current state
    """
    # Validate
    valid, error = _validate_observation(request)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid GPS observation: {error}",
        )

    # Create observation
    obs = GPSObservation(
        observation_id=request.observation_id or f"{driver_id}_{int(time.time()*1000)}",
        driver_id=driver_id,
        timestamp=request.timestamp,
        latitude=request.latitude,
        longitude=request.longitude,
        speed_kmh=request.speed_kmh,
        heading_deg=request.heading_deg,
        accuracy_m=request.accuracy_m,
    )

    # Add observation with CAS to prevent lost updates
    state_manager = get_driver_state_manager()
    try:
        state, is_stale, gap_reset, gap_reason = await _add_observation_with_cas(driver_id, obs)
    except DriverStateUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Driver state store unavailable: {str(e)}",
        )

    # Check stale observation result
    if is_stale:
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.STALE_OBSERVATION,
            message=f"Observation timestamp {obs.timestamp} is before last {state.last_observation_timestamp}",
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
        )

    if gap_reset:
        state.current_status = MatchingStatus.GAP_RESET.value

    # Check warm-up
    if state.is_warming_up():
        state.current_status = MatchingStatus.WARMING_UP.value
        # Persist state (in case it was modified by gap reset)
        try:
            await _persist_state_with_retry(driver_id, state)
        except DriverStateUnavailableError:
            pass
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.WARMING_UP,
            message=f"Warming up: {len(state.observations)} observations (need 3+)",
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
            movement_since_match_m=state.movement_since_match,
        )

    # Check stationary suppression
    if state.is_stationary() and state.last_matched_state is not None:
        state.current_status = MatchingStatus.GPS_ACCEPTED.value
        state.last_trigger_reason = "STATIONARY_SUPPRESSED"
        # Persist state
        try:
            await _persist_state_with_retry(driver_id, state)
        except DriverStateUnavailableError:
            pass
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.GPS_ACCEPTED,
            trigger_reason="STATIONARY_SUPPRESSED",
            raw_position={
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "timestamp": obs.timestamp.isoformat(),
            },
            matched_position={
                "latitude": state.last_matched_state.matched_latitude,
                "longitude": state.last_matched_state.matched_longitude,
                "road_segment_id": state.last_matched_state.road_segment_id,
                "osm_way_id": state.last_matched_state.osm_way_id,
                "direction": state.last_matched_state.direction,
            },
            last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
            last_match_latency_ms=state.last_match_latency_ms,
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
            movement_since_match_m=state.movement_since_match,
            is_stationary=True,
            message="Stationary suppressed: no match triggered",
        )

    # Get trigger policy
    policy = get_default_policy()

    # Check trigger
    should_trigger, reason = policy.should_trigger(obs.timestamp, state)
    state.last_trigger_reason = reason

    if not should_trigger:
        state.current_status = MatchingStatus.GPS_ACCEPTED.value
        # Persist state
        try:
            await _persist_state_with_retry(driver_id, state)
        except DriverStateUnavailableError:
            pass
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.GPS_ACCEPTED,
            trigger_reason=reason,
            raw_position={
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "timestamp": obs.timestamp.isoformat(),
            },
            last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
            last_match_latency_ms=state.last_match_latency_ms,
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
            movement_since_match_m=state.movement_since_match,
            is_stationary=state.is_stationary(),
        )

    # Trigger map matching
    context = state.get_context()
    if len(context) < 2:
        state.current_status = MatchingStatus.WARMING_UP.value
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.WARMING_UP,
            message=f"Not enough context: {len(context)} observations",
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
        )

    # Call map matching
    try:
        response, latency_ms = await _call_map_match(context, request.vehicle_category, request.vehicle_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (MapMatchingEngineError, psycopg2.Error) as exc:
        state.current_status = MatchingStatus.ENGINE_UNAVAILABLE.value
        # Try to persist ENGINE_UNAVAILABLE state, but return even if fails
        try:
            await _persist_state_with_retry(driver_id, state)
        except DriverStateUnavailableError:
            pass  # Best effort
        return LocationResponse(
            driver_id=driver_id, status=MatchingStatus.ENGINE_UNAVAILABLE,
            trigger_reason=reason, message=str(exc),
            raw_position={"latitude": obs.latitude, "longitude": obs.longitude, "timestamp": obs.timestamp.isoformat()},
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls, buffered_points=len(state.observations),
        )
    state.last_match_latency_ms = latency_ms

    latest_match = next((o for o in reversed(response.observations) if o.observation_id == context[-1].observation_id), None) if response else None
    if latest_match is None or not latest_match.matched:
        state.current_status = MatchingStatus.NO_MATCH.value
        state.last_trigger_reason = f"NO_MATCH({reason})"
        # Persist NO_MATCH state to maintain observation continuity
        try:
            await _persist_state_with_retry(driver_id, state)
        except DriverStateUnavailableError:
            pass  # Best effort
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.NO_MATCH,
            trigger_reason=reason,
            raw_position={
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "timestamp": obs.timestamp.isoformat(),
            },
            last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
            last_match_latency_ms=latency_ms,
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
            movement_since_match_m=state.movement_since_match,
            is_stationary=state.is_stationary(),
            message="No matched position for the latest observation",
        )

    # Parse response and update state
    match_resp = response
    state.current_status = MatchingStatus.MATCHED.value

    matched_state = MatchedState(
        matched_latitude=latest_match.matched_latitude,
        matched_longitude=latest_match.matched_longitude,
        road_segment_id=latest_match.road_segment_id,
        osm_way_id=latest_match.osm_way_id,
        direction=latest_match.direction,
        confidence=latest_match.confidence if latest_match.confidence is not None else match_resp.overall_confidence,
        route_geometry=match_resp.trace_geometry,
    )

    state.reset_after_match(matched_state)

    # Persist the matched state to shared store
    try:
        await _persist_state_with_retry(driver_id, state)
    except DriverStateUnavailableError:
        pass  # Best effort - return response anyway

    return LocationResponse(
        driver_id=driver_id,
        status=MatchingStatus.MATCHED,
        trigger_reason=reason,
        raw_position={
            "latitude": obs.latitude,
            "longitude": obs.longitude,
            "timestamp": obs.timestamp.isoformat(),
        },
        matched_position={
            "latitude": matched_state.matched_latitude,
            "longitude": matched_state.matched_longitude,
            "road_segment_id": matched_state.road_segment_id,
            "osm_way_id": matched_state.osm_way_id,
            "direction": matched_state.direction,
            "confidence": matched_state.confidence,
        },
        last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
        last_match_latency_ms=latency_ms,
        total_observations=state.total_observations_received,
        total_match_calls=state.total_match_calls,
        buffered_points=len(state.observations),
        movement_since_match_m=state.movement_since_match,
        is_stationary=state.is_stationary(),
        message=f"Matched: {len(context)} points, confidence {matched_state.confidence:.4f}",
    )


@router.get("/drivers/{driver_id}/location", response_model=LocationResponse)
async def get_driver_location(
    driver_id: str,
) -> LocationResponse:
    """
    Get current state for a driver.
    """
    state_manager = get_driver_state_manager()
    try:
        state = await state_manager.get_or_create(driver_id)
    except DriverStateUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Driver state store unavailable: {str(e)}",
        )

    raw_pos = state.get_current_raw_position()

    return LocationResponse(
        driver_id=driver_id,
        status=MatchingStatus(state.current_status),
        trigger_reason=state.last_trigger_reason,
        raw_position={
            "latitude": raw_pos[0] if raw_pos else None,
            "longitude": raw_pos[1] if raw_pos else None,
        } if raw_pos else None,
        matched_position={
            "latitude": state.last_matched_state.matched_latitude if state.last_matched_state else None,
            "longitude": state.last_matched_state.matched_longitude if state.last_matched_state else None,
            "road_segment_id": state.last_matched_state.road_segment_id if state.last_matched_state else None,
            "osm_way_id": state.last_matched_state.osm_way_id if state.last_matched_state else None,
            "direction": state.last_matched_state.direction if state.last_matched_state else None,
        } if state.last_matched_state else None,
        last_match_time=state.last_match_time.isoformat() if state.last_match_time else None,
        last_match_latency_ms=state.last_match_latency_ms,
        total_observations=state.total_observations_received,
        total_match_calls=state.total_match_calls,
        buffered_points=len(state.observations),
        movement_since_match_m=state.movement_since_match,
        is_stationary=state.is_stationary(),
    )


@router.delete("/drivers/{driver_id}/location")
async def reset_driver_state(driver_id: str) -> dict:
    """Reset driver's trace state."""
    state_manager = get_driver_state_manager()
    try:
        await state_manager.delete(driver_id)
        removed = True
    except DriverStateUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Driver state store unavailable",
        )
    return {"driver_id": driver_id, "reset": removed}


@router.get("/drivers")
async def list_drivers() -> dict:
    """List all active drivers."""
    state_manager = get_driver_state_manager()
    try:
        drivers = await state_manager.list_drivers()
    except DriverStateUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Driver state store unavailable",
        )
    return {
        "active_drivers": drivers,
        "count": len(drivers),
    }


@router.get("/debug/trajectories/{trajectory_id}")
async def get_trajectory_observations(trajectory_id: str) -> list[dict]:
    """
    Get observations for a trajectory from Dataset V1.
    Debug endpoint for UI replay.
    """
    import gzip
    import csv
    from pathlib import Path

    gps_file = Path("dataset_v1/gps/gps_observations.csv.gz")
    if not gps_file.exists():
        raise HTTPException(status_code=404, detail="Dataset not found")

    observations = []
    with gzip.open(gps_file, 'rt', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['trajectory_id'] != trajectory_id:
                continue
            try:
                obs = {
                    "observation_id": row['observation_id'],
                    "timestamp": row['timestamp'],
                    "latitude": float(row['latitude']),
                    "longitude": float(row['longitude']),
                }
                if row.get('speed_kmh'):
                    obs["speed_kmh"] = float(row['speed_kmh'])
                if row.get('heading_deg'):
                    obs["heading_deg"] = float(row['heading_deg'])
                observations.append(obs)
            except Exception:
                continue

    if not observations:
        raise HTTPException(status_code=404, detail=f"Trajectory {trajectory_id} not found")

    return observations
