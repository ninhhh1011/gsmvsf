"""
Realtime Operational State Simulator for GSMVSF.

Generates continuous bounded Markov random-walk operational updates every ~30s
for stations (slots, queue, status) and road segments (traffic delay, speeds).
All generated snapshots strictly conform to canonical station capacities and
pass IngestionService validation rules.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any

from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.snapshots.ingestion import IngestionService
from backend.app.services.snapshots.models import (
    QueueSnapshot,
    Snapshot,
    StationStateSnapshot,
    TrafficSnapshot,
    aware_utc,
)

logger = logging.getLogger(__name__)

# Fallback known segment IDs if database segment query is unavailable
FALLBACK_SEGMENT_IDS = [
    "9963509_3_R", "9964440_2_F", "9964440_3_F", "9965723_3_F", "9965723_6_R",
    "9978719_2_F", "10230472_0_F", "10230472_2_F", "10230481_2_R", "10231816_5_F",
    "1087731719_8_R", "1087731719_9_F", "1087731719_8_F", "1087731719_9_R", "1087731719_7_F",
]


class StationSimState:
    """Tracks evolving state for a single station."""

    def __init__(self, station_id: str, charging_slots: int, swap_slots: int):
        self.station_id = station_id
        self.charging_slots = charging_slots
        self.swap_slots = swap_slots
        self.operating_status = "OPEN"

        # Initial charging state
        if charging_slots > 0:
            self.occupied_charging = random.randint(0, charging_slots)
            self.available_charging = charging_slots - self.occupied_charging
            self.charging_queue = random.randint(0, min(3, charging_slots))
        else:
            self.occupied_charging = 0
            self.available_charging = 0
            self.charging_queue = 0

        # Initial swap state
        if swap_slots > 0:
            self.occupied_swap = random.randint(0, swap_slots)
            self.available_swap = swap_slots - self.occupied_swap
            self.available_swap_batteries = max(0, self.available_swap + random.randint(0, 2))
            self.swap_queue = random.randint(0, min(2, swap_slots))
        else:
            self.occupied_swap = 0
            self.available_swap = 0
            self.available_swap_batteries = 0
            self.swap_queue = 0

    def step(self, rng: random.Random) -> tuple[dict[str, Any], dict[str, Any]]:
        """Evolve state by one bounded Markov step and return station & queue params."""
        # 98% OPEN, 2% transient OFFLINE, recovers with 80% probability
        if self.operating_status == "OPEN":
            if rng.random() < 0.02:
                self.operating_status = "OFFLINE"
        else:
            if rng.random() < 0.80:
                self.operating_status = "OPEN"

        # Evolve charging slots and queue
        if self.charging_slots > 0:
            delta_occ = rng.choice([-1, 0, 1])
            self.occupied_charging = max(0, min(self.charging_slots, self.occupied_charging + delta_occ))
            self.available_charging = self.charging_slots - self.occupied_charging

            delta_q = rng.choice([-1, 0, 0, 1, 2])
            self.charging_queue = max(0, min(2 * self.charging_slots, self.charging_queue + delta_q))
            charging_wait = round((self.charging_queue * 18.0) / max(1, self.occupied_charging), 2)
        else:
            charging_wait = 0.0

        # Evolve swap slots and queue
        if self.swap_slots > 0:
            delta_swap = rng.choice([-1, 0, 1])
            self.occupied_swap = max(0, min(self.swap_slots, self.occupied_swap + delta_swap))
            self.available_swap = self.swap_slots - self.occupied_swap
            self.available_swap_batteries = max(0, self.available_swap + rng.randint(0, 2))

            delta_sq = rng.choice([-1, 0, 1])
            self.swap_queue = max(0, min(2 * self.swap_slots, self.swap_queue + delta_sq))
            swap_wait = round((self.swap_queue * 6.0) / max(1, self.occupied_swap), 2)
        else:
            swap_wait = 0.0

        station_params = {
            "entity_id": self.station_id,
            "operating_status": self.operating_status,
            "available_charging_slots": self.available_charging,
            "occupied_charging_slots": self.occupied_charging,
            "available_swap_slots": self.available_swap,
            "occupied_swap_slots": self.occupied_swap,
            "available_swap_batteries": self.available_swap_batteries,
            "charging_service_time_min": 18.0 if self.charging_slots > 0 else 0.0,
            "swap_service_time_min": 6.0 if self.swap_slots > 0 else 0.0,
        }

        queue_params = {
            "entity_id": self.station_id,
            "charging_queue_length": self.charging_queue,
            "charging_active_service_count": self.occupied_charging,
            "charging_service_time_min": 18.0 if self.charging_slots > 0 else 0.0,
            "charging_estimated_wait_min": charging_wait,
            "swap_queue_length": self.swap_queue,
            "swap_active_service_count": self.occupied_swap,
            "swap_service_time_min": 6.0 if self.swap_slots > 0 else 0.0,
            "swap_estimated_wait_min": swap_wait,
        }

        return station_params, queue_params


class SegmentSimState:
    """Tracks evolving traffic state for a single road segment."""

    def __init__(self, segment_id: str, base_speed_kmh: float = 40.0):
        self.segment_id = segment_id
        self.base_speed = base_speed_kmh
        self.current_speed = base_speed_kmh

    def step(self, rng: random.Random) -> dict[str, Any]:
        """Evolve speed by bounded random step and compute delay factor."""
        delta = rng.choice([-3.0, -1.5, 0.0, 1.5, 3.0])
        self.current_speed = max(12.0, min(self.base_speed, self.current_speed + delta))
        self.current_speed = round(self.current_speed, 2)

        raw_df = self.base_speed / self.current_speed
        delay_factor = round(raw_df, 3)

        # Ensure delay_factor * current_speed agrees with free_flow within IngestionService tolerance
        adjusted_free_flow = round(delay_factor * self.current_speed, 2)
        if adjusted_free_flow <= 0:
            adjusted_free_flow = 30.0

        if delay_factor < 1.15:
            traffic_level = "FREE_FLOW"
        elif delay_factor < 1.6:
            traffic_level = "MODERATE"
        elif delay_factor < 2.5:
            traffic_level = "HEAVY"
        else:
            traffic_level = "INCIDENT"

        return {
            "entity_id": self.segment_id,
            "traffic_level": traffic_level,
            "free_flow_speed_kmh": adjusted_free_flow,
            "current_speed_kmh": self.current_speed,
            "delay_factor": delay_factor,
        }


class RealtimeSimulator:
    """
    Lightweight operational snapshot simulator.
    Periodically generates coherent state evolutions for demo subset.
    """

    def __init__(
        self,
        catalog=station_catalog,
        segment_ids: list[str] | None = None,
        station_limit: int | None = None,
        seed: int | None = 42,
    ):
        self.catalog = catalog
        self.rng = random.Random(seed)
        self._running = False
        self._task: asyncio.Task | None = None

        # Initialize station states
        all_stations = catalog.get_all_stations()
        selected_stations = all_stations[:station_limit] if station_limit else all_stations
        self.station_states: dict[str, StationSimState] = {
            s.station_id: StationSimState(s.station_id, s.charging_slots, s.swap_slots)
            for s in selected_stations
        }

        # Initialize segment states
        active_segments = segment_ids or FALLBACK_SEGMENT_IDS
        self.segment_states: dict[str, SegmentSimState] = {
            seg: SegmentSimState(seg, base_speed_kmh=40.0)
            for seg in active_segments
        }

    def generate_tick_snapshots(self, timestamp: datetime | None = None) -> list[Snapshot]:
        """Generate a complete set of validated snapshots for current tick."""
        ts = aware_utc(timestamp or datetime.now(UTC))
        source = "simulator"
        snapshots: list[Snapshot] = []

        # Stations and Queues
        for state in self.station_states.values():
            st_params, q_params = state.step(self.rng)
            snapshots.append(StationStateSnapshot(
                timestamp=ts,
                source=source,
                **st_params,
            ))
            snapshots.append(QueueSnapshot(
                timestamp=ts,
                source=source,
                **q_params,
            ))

        # Traffic
        for seg_state in self.segment_states.values():
            tf_params = seg_state.step(self.rng)
            snapshots.append(TrafficSnapshot(
                timestamp=ts,
                source=source,
                **tf_params,
            ))

        return snapshots

    async def tick(self, ingestion_service: IngestionService, timestamp: datetime | None = None) -> int:
        """Execute one simulation tick and ingest snapshots into database and cache."""
        snapshots = self.generate_tick_snapshots(timestamp=timestamp)
        # Ingest all snapshots via canonical ingestion pipeline
        created = await ingestion_service.ingest_many(snapshots)
        logger.info(
            "Simulated tick ingested %d operational snapshots at %s",
            created,
            (timestamp or datetime.now(UTC)).isoformat(),
        )
        return created

    async def run_loop(self, ingestion_service: IngestionService, interval_s: float = 30.0) -> None:
        """Background continuous simulation loop."""
        self._running = True
        logger.info("Starting realtime operational simulation loop (interval=%.1fs)", interval_s)
        try:
            while self._running:
                try:
                    await self.tick(ingestion_service)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("Simulation tick failed: %s", exc, exc_info=True)
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info("Realtime operational simulation loop stopped")

    def start_background(self, ingestion_service: IngestionService, interval_s: float = 30.0) -> asyncio.Task:
        """Start simulator as an asyncio background task."""
        if self._task and not self._task.done():
            return self._task
        self._task = asyncio.create_task(self.run_loop(ingestion_service, interval_s=interval_s))
        return self._task

    async def stop(self) -> None:
        """Stop simulator background task gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
