"""
Tests for StationCatalog and station operational state provider.
"""

from datetime import datetime
import pytest

from backend.app.services.candidate.station_catalog import StationCatalog, StationRecord
from backend.app.services.demand.models import ServiceType


def test_station_catalog_loads_all_30_stations():
    catalog = StationCatalog()
    stations = catalog.get_all_stations()
    assert len(stations) == 30
    ids = {s.station_id for s in stations}
    assert "S001" in ids
    assert "S030" in ids


def test_station_types_and_dual_service():
    catalog = StationCatalog()
    s1 = catalog.get_station("S001")
    assert s1 is not None
    assert s1.station_type == "CHARGING"
    assert s1.charging_slots == 6
    assert s1.swap_slots == 0

    s3 = catalog.get_station("S003")
    assert s3 is not None
    assert s3.station_type == "SWAP"
    assert s3.charging_slots == 0
    assert s3.swap_slots == 10

    # Dual service stations (S005, S010, S020, S025)
    s5 = catalog.get_station("S005")
    assert s5 is not None
    assert s5.station_type == "CHARGING_SWAP"
    assert s5.charging_slots == 3
    assert s5.swap_slots == 3


def test_get_operational_snapshot():
    catalog = StationCatalog()
    # Test point-in-time lookup matching dataset timestamps
    ts = "2026-09-01T06:10:00+07:00"
    snap = catalog.get_operational_snapshot("S001", ServiceType.CHARGING, timestamp=ts)
    assert snap.operating_status in ("OPEN", "OFFLINE")
    assert snap.service_time_min == 18.0

    # Test default fallback without timestamp
    snap_default = catalog.get_operational_snapshot("S005", ServiceType.BATTERY_SWAP)
    assert snap_default.operating_status == "OPEN"
    assert snap_default.available_service_slots == 3
