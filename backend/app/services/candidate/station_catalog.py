"""
Station Catalog and State Provider for Week 3 Candidate Search.

Loads physical station infrastructure from dataset_v1/stations/stations.csv
and point-in-time station operational and queue statuses from station_status.csv.gz
and queue_status.csv.gz.
"""

from __future__ import annotations

import csv
import gzip
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from backend.app.config import settings
from backend.app.services.candidate.models import StationOperationalSnapshot
from backend.app.services.demand.models import ServiceType

logger = logging.getLogger(__name__)

CHARGING_SERVICE_TIME_MIN = 18.0
SWAP_SERVICE_TIME_MIN = 6.0


@dataclass(frozen=True)
class StationRecord:
    """Canonical physical station definition."""
    station_id: str
    access_node_id: str
    latitude: float
    longitude: float
    access_latitude: float
    access_longitude: float
    station_type: str
    connector_type: str
    battery_type: str
    supported_vehicle_type: str
    total_slots: int
    charging_slots: int
    swap_slots: int


def _parse_tokens(value: Optional[str]) -> set[str]:
    """Split comma or semicolon separated tokens into clean lowercase or stripped set."""
    if not value or pd.isna(value):
        return set()
    return {x.strip() for x in str(value).replace(",", ";").split(";") if x.strip()}


def floor_iso_timestamp(ts: Union[str, datetime], minutes: int = 10) -> str:
    """Floor ISO timestamp to N-minute intervals matching dataset snapshot granularity."""
    return pd.Timestamp(ts).floor(f"{minutes}min").isoformat()


class StationCatalog:
    """
    Catalog of charging and battery-swap stations with point-in-time status tracking.
    """

    def __init__(
        self,
        stations_csv_path: Optional[Path] = None,
        station_status_path: Optional[Path] = None,
        queue_status_path: Optional[Path] = None,
    ):
        self.stations_csv_path = stations_csv_path or (settings.dataset_path / "stations/stations.csv")
        self.station_status_path = station_status_path or (settings.dataset_path / "stations/station_status.csv.gz")
        self.queue_status_path = queue_status_path or (settings.dataset_path / "queue/queue_status.csv.gz")

        self._stations: dict[str, StationRecord] = {}
        self._status_df: Optional[pd.DataFrame] = None
        self._queue_df: Optional[pd.DataFrame] = None
        self._status_idx: Optional[pd.DataFrame] = None
        self._queue_idx: Optional[pd.DataFrame] = None

        self._load_stations()

    def _load_stations(self) -> None:
        """Load static physical station records."""
        if not self.stations_csv_path.exists():
            raise FileNotFoundError(f"Stations CSV not found at {self.stations_csv_path}")

        stations = {}
        with open(self.stations_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                s = StationRecord(
                    station_id=row["station_id"],
                    access_node_id=row["access_node_id"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    access_latitude=float(row.get("access_latitude", row["latitude"])),
                    access_longitude=float(row.get("access_longitude", row["longitude"])),
                    station_type=row["station_type"],
                    connector_type=row.get("connector_type", ""),
                    battery_type=row.get("battery_type", ""),
                    supported_vehicle_type=row.get("supported_vehicle_type", ""),
                    total_slots=int(row.get("total_slots", 0)),
                    charging_slots=int(row.get("charging_slots", 0)),
                    swap_slots=int(row.get("swap_slots", 0)),
                )
                stations[s.station_id] = s
        self._stations = stations
        logger.info("Loaded %d stations from %s", len(self._stations), self.stations_csv_path)

    def _ensure_dynamic_status_loaded(self) -> None:
        """Lazy load status and queue snapshots for point-in-time state resolution."""
        if self._status_idx is not None and self._queue_idx is not None:
            return

        if self.station_status_path.exists():
            logger.info("Loading station status index from %s...", self.station_status_path)
            sdf = pd.read_csv(self.station_status_path)
            self._status_idx = sdf.set_index(["station_id", "timestamp"])
        else:
            logger.warning("Station status path %s not found", self.station_status_path)
            self._status_idx = pd.DataFrame()

        if self.queue_status_path.exists():
            logger.info("Loading queue status index from %s...", self.queue_status_path)
            qdf = pd.read_csv(self.queue_status_path)
            self._queue_idx = qdf.set_index(["station_id", "timestamp"])
        else:
            logger.warning("Queue status path %s not found", self.queue_status_path)
            self._queue_idx = pd.DataFrame()

    def get_all_stations(self) -> list[StationRecord]:
        """Return all 30 stations in catalog order."""
        return list(self._stations.values())

    def get_station(self, station_id: str) -> Optional[StationRecord]:
        """Retrieve single station by ID."""
        return self._stations.get(station_id)

    def get_operational_snapshot(
        self,
        station_id: str,
        service_type: ServiceType,
        timestamp: Optional[Union[str, datetime]] = None,
    ) -> StationOperationalSnapshot:
        """
        Get point-in-time operational snapshot for a station and service type.
        Replicates exact column semantics from Dataset V1.3.1.
        """
        station = self._stations.get(station_id)
        if station is None:
            raise KeyError(f"Unknown station_id: {station_id}")

        self._ensure_dynamic_status_loaded()

        sr = None
        qr = None
        state_ts = None

        if timestamp is not None and self._status_idx is not None and not self._status_idx.empty:
            state_ts = floor_iso_timestamp(timestamp, 10)
            if (station_id, state_ts) in self._status_idx.index:
                sr = self._status_idx.loc[(station_id, state_ts)]
                if isinstance(sr, pd.DataFrame):
                    sr = sr.iloc[0]

            if (
                self._queue_idx is not None
                and not self._queue_idx.empty
                and (station_id, state_ts) in self._queue_idx.index
            ):
                qr = self._queue_idx.loc[(station_id, state_ts)]
                if isinstance(qr, pd.DataFrame):
                    qr = qr.iloc[0]

        if sr is not None:
            op = str(sr.get("operating_status", "OPEN"))
            if service_type == ServiceType.CHARGING:
                slots_avail = int(sr.get("available_charging_slots", 0))
                swap_batt = 0
                capacity = slots_avail
                wait = float(qr.get("charging_estimated_wait_min", 0.0)) if qr is not None else 0.0
                svc_time = float(sr.get("charging_service_time_min", CHARGING_SERVICE_TIME_MIN))
                qlen = int(qr.get("charging_queue_length", 0)) if qr is not None else 0
            else:
                slots_avail = int(sr.get("available_swap_slots", 0))
                swap_batt = int(sr.get("available_swap_batteries", 0)) if op == "OPEN" else 0
                capacity = min(slots_avail, swap_batt)
                wait = float(qr.get("swap_estimated_wait_min", 0.0)) if qr is not None else 0.0
                svc_time = float(sr.get("swap_service_time_min", SWAP_SERVICE_TIME_MIN))
                qlen = int(qr.get("swap_queue_length", 0)) if qr is not None else 0
        else:
            # Default nominal state when point-in-time status is not available (e.g., live runtime)
            op = "OPEN"
            if service_type == ServiceType.CHARGING:
                slots_avail = station.charging_slots
                swap_batt = 0
                capacity = slots_avail
                wait = 0.0
                svc_time = CHARGING_SERVICE_TIME_MIN if station.charging_slots > 0 else 0.0
                qlen = 0
            else:
                slots_avail = station.swap_slots
                swap_batt = station.swap_slots * 2 if op == "OPEN" else 0
                capacity = slots_avail
                wait = 0.0
                svc_time = SWAP_SERVICE_TIME_MIN if station.swap_slots > 0 else 0.0
                qlen = 0

        return StationOperationalSnapshot(
            operating_status=op,
            available_service_slots=slots_avail,
            available_swap_batteries=swap_batt,
            available_capacity=capacity,
            queue_length=qlen,
            estimated_wait_min=wait,
            service_time_min=svc_time,
            state_timestamp=state_ts,
        )


# Global singleton instance for convenient reuse across services
station_catalog = StationCatalog()
