"""Tests for driver state repository."""
import pytest
from datetime import datetime

from backend.app.services.realtime.driver_state_repository import (
    InMemoryDriverStateRepository,
    DriverTraceStateSnapshot,
    GPSObservation,
    MatchedState,
)


@pytest.mark.asyncio
async def test_in_memory_repository_save_and_get():
    repo = InMemoryDriverStateRepository()

    snapshot = DriverTraceStateSnapshot(
        driver_id="D001",
        observations=[
            {
                "observation_id": "obs1",
                "driver_id": "D001",
                "timestamp": datetime.utcnow().isoformat(),
                "latitude": 21.0,
                "longitude": 105.8,
            }
        ],
        last_match_time=datetime.utcnow().isoformat(),
        last_matched_state={
            "matched_latitude": 21.001,
            "matched_longitude": 105.801,
            "road_segment_id": "seg_1",
            "osm_way_id": 123,
        },
        movement_since_match=0.0,
        observations_since_match=0,
        consecutive_stationary=0,
        total_observations_received=1,
        total_match_calls=1,
        last_trigger_reason="DISTANCE",
        last_match_latency_ms=5.0,
        current_status="MATCHED",
    )

    assert await repo.save(snapshot) is True
    loaded = await repo.get("D001")

    assert loaded is not None
    assert loaded.driver_id == "D001"
    assert len(loaded.observations) == 1
    assert loaded.current_status == "MATCHED"
    assert loaded.last_matched_state is not None


@pytest.mark.asyncio
async def test_in_memory_repository_delete():
    repo = InMemoryDriverStateRepository()

    snapshot = DriverTraceStateSnapshot(driver_id="D001")
    await repo.save(snapshot)

    assert await repo.get("D001") is not None
    await repo.delete("D001")
    assert await repo.get("D001") is None


@pytest.mark.asyncio
async def test_in_memory_repository_list_drivers():
    repo = InMemoryDriverStateRepository()

    for i in range(3):
        await repo.save(DriverTraceStateSnapshot(driver_id=f"D00{i}"))

    drivers = await repo.list_drivers()
    assert len(drivers) == 3
    assert "D001" in drivers


@pytest.mark.asyncio
async def test_in_memory_repository_health():
    repo = InMemoryDriverStateRepository()
    assert await repo.health_check() is True


@pytest.mark.asyncio
async def test_snapshot_json_roundtrip():
    snapshot = DriverTraceStateSnapshot(
        driver_id="D001",
        observations=[],
        movement_since_match=100.5,
        observations_since_match=10,
        total_observations_received=50,
        version=3,
    )

    json_str = snapshot.to_json()
    loaded = DriverTraceStateSnapshot.from_json(json_str)

    assert loaded.driver_id == snapshot.driver_id
    assert loaded.movement_since_match == snapshot.movement_since_match
    assert loaded.version == snapshot.version


@pytest.mark.asyncio
async def test_gps_observation_roundtrip():
    obs = GPSObservation(
        observation_id="obs1",
        driver_id="D001",
        timestamp=datetime.utcnow(),
        latitude=21.0,
        longitude=105.8,
        speed_kmh=30.0,
        heading_deg=90.0,
    )

    obs_dict = obs.to_dict()
    loaded = GPSObservation.from_dict(obs_dict)

    assert loaded.observation_id == obs.observation_id
    assert loaded.latitude == obs.latitude
    assert loaded.speed_kmh == obs.speed_kmh


@pytest.mark.asyncio
async def test_matched_state_roundtrip():
    state = MatchedState(
        matched_latitude=21.001,
        matched_longitude=105.801,
        road_segment_id="seg_1",
        osm_way_id=123,
        direction="FORWARD",
        confidence=0.95,
    )

    state_dict = state.to_dict()
    loaded = MatchedState.from_dict(state_dict)

    assert loaded.matched_latitude == state.matched_latitude
    assert loaded.direction == state.direction
    assert loaded.confidence == state.confidence
