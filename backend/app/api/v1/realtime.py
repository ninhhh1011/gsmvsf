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
from typing import Optional

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


async def _call_map_match(
    observations: list[GPSObservation],
) -> tuple[Optional[MapMatchResponse], float]:
    """
    Call map matching service.

    Returns:
        Tuple of (response, latency_ms)
    """
    import httpx

    if len(observations) < 2:
        return None, 0.0

    # Build coordinates
    coords = [(o.longitude, o.latitude) for o in observations]

    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords)
    url = f"{settings.osrm_base_url}/match/v1/driving/{coords_str}"

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                params={"overview": "simplified"},
            )
            latency_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "Ok":
                    # Parse response into MapMatchResponse
                    # For realtime, we return a simplified matched state
                    matchings = data.get("matchings", [])
                    if matchings:
                        matching = matchings[0]
                        tracepoints = data.get("tracepoints", [])

                        # Get last matched point
                        last_matched_tp = None
                        for tp in reversed(tracepoints):
                            if tp and tp.get("matchings_index") is not None:
                                last_matched_tp = tp
                                break

                        if last_matched_tp:
                            location = last_matched_tp.get("location", [])
                            return MapMatchResponse(
                                trajectory_id=observations[0].driver_id,
                                trip_id="realtime",
                                total_observations=len(observations),
                                matched_count=len(observations),
                                unmatched_count=0,
                                observations=[],
                                overall_confidence=matching.get("confidence", 0),
                                trace_geometry=matching.get("geometry"),
                            ), latency_ms

                    return None, latency_ms

            return None, latency_ms

    except Exception as e:
        logger.error(f"Map matching error: {e}")
        return None, (time.time() - start) * 1000


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

    # Get driver state
    store = get_state_store()
    state = store.get_or_create(driver_id)

    # Check for stale observation (before last observation timestamp)
    if (state.last_observation_timestamp and
        obs.timestamp < state.last_observation_timestamp):
        return LocationResponse(
            driver_id=driver_id,
            status=MatchingStatus.STALE_OBSERVATION,
            message=f"Observation timestamp {obs.timestamp} is before last {state.last_observation_timestamp}",
            total_observations=state.total_observations_received,
            total_match_calls=state.total_match_calls,
            buffered_points=len(state.observations),
        )

    # Add observation
    gap_reset, gap_reason = state.add_observation(obs)

    if gap_reset:
        state.current_status = MatchingStatus.GAP_RESET.value

    # Check warm-up
    if state.is_warming_up():
        state.current_status = MatchingStatus.WARMING_UP.value
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
    response, latency_ms = await _call_map_match(context)
    state.last_match_latency_ms = latency_ms

    if response is None:
        state.current_status = MatchingStatus.NO_MATCH.value
        state.last_trigger_reason = f"NO_MATCH({reason})"
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
            message="No match returned from OSRM",
        )

    # Parse response and update state
    match_resp = response
    state.current_status = MatchingStatus.MATCHED.value

    # Get last matched position from geometry
    # For simplicity, use the last context observation's matched position
    # In production, would parse geometry to get road-snapped position
    last_obs = context[-1]
    matched_state = MatchedState(
        matched_latitude=last_obs.latitude,  # Would be from parsed geometry
        matched_longitude=last_obs.longitude,
        confidence=match_resp.overall_confidence,
        route_geometry=match_resp.trace_geometry,
    )

    state.reset_after_match(matched_state)

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
    store = get_state_store()
    state = store.get(driver_id)

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Driver {driver_id} not found",
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
    store = get_state_store()
    removed = store.remove(driver_id)
    return {"driver_id": driver_id, "reset": removed}


@router.get("/drivers")
async def list_drivers() -> dict:
    """List all active drivers."""
    store = get_state_store()
    return {
        "active_drivers": store.list_drivers(),
        "count": len(store),
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
