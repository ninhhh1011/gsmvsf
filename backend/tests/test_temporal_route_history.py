# backend/tests/test_temporal_route_history.py
"""Tests for Vietnam local-time peak hour windows, causality filtering, and trip classification."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pytest
from backend.app.services.route_familiarity.temporal import (
    get_vietnam_time_window,
    TimeWindowType,
    classify_trip_time_window,
    filter_historical_trips_by_window,
)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def test_morning_peak_window():
    # 07:30 VN Time (00:30 UTC)
    dt_utc = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.MORNING_PEAK

def test_evening_peak_window():
    # 18:15 VN Time (11:15 UTC)
    dt_utc = datetime(2026, 9, 1, 11, 15, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.EVENING_PEAK

def test_off_peak_window():
    # 13:00 VN Time (06:00 UTC)
    dt_utc = datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.OFF_PEAK

def test_boundary_handling():
    # Exactly 07:00 VN Time is Morning Peak
    dt_0700 = datetime(2026, 9, 1, 7, 0, tzinfo=VN_TZ)
    assert get_vietnam_time_window(dt_0700) == TimeWindowType.MORNING_PEAK

    # Exactly 09:00 VN Time is Off-peak (peak is 07:00 to <09:00)
    dt_0900 = datetime(2026, 9, 1, 9, 0, tzinfo=VN_TZ)
    assert get_vietnam_time_window(dt_0900) == TimeWindowType.OFF_PEAK

    # Exactly 17:00 VN Time is Evening Peak
    dt_1700 = datetime(2026, 9, 1, 17, 0, tzinfo=VN_TZ)
    assert get_vietnam_time_window(dt_1700) == TimeWindowType.EVENING_PEAK

    # Exactly 19:30 VN Time is Off-peak (peak is 17:00 to <19:30)
    dt_1930 = datetime(2026, 9, 1, 19, 30, tzinfo=VN_TZ)
    assert get_vietnam_time_window(dt_1930) == TimeWindowType.OFF_PEAK

def test_classify_trip_time_window():
    dt_morning = datetime(2026, 9, 1, 8, 15, tzinfo=VN_TZ)
    res = classify_trip_time_window(dt_morning)
    assert res["time_window"] == "MORNING_PEAK"
    assert res["is_peak"] is True
    assert "07:00 - 09:00" in res["window_label_vi"]

def test_filter_historical_trips_by_window_strict_causality():
    eval_time = datetime(2026, 9, 1, 8, 30, tzinfo=VN_TZ)  # Morning peak
    history_records = [
        # 1. Past trip, same window (Morning peak 07:45) -> INCLUDE
        {"trip_id": "T1", "driver_id": "D1", "completed_at": datetime(2026, 9, 1, 7, 45, tzinfo=VN_TZ)},
        # 2. Future trip (completed after eval_time 08:45) -> EXCLUDE (causality)
        {"trip_id": "T2", "driver_id": "D2", "completed_at": datetime(2026, 9, 1, 8, 45, tzinfo=VN_TZ)},
        # 3. Past trip, different window (Off-peak 03:00) -> RECORDED in all-hours but NOT same-window
        {"trip_id": "T3", "driver_id": "D3", "completed_at": datetime(2026, 9, 1, 3, 0, tzinfo=VN_TZ)},
    ]

    stats = filter_historical_trips_by_window(history_records, as_of=eval_time, target_window=TimeWindowType.MORNING_PEAK)
    assert stats["same_window_trip_count"] == 1
    assert stats["same_window_driver_count"] == 1
    assert stats["all_window_trip_count"] == 2  # T1 and T3 (T2 excluded due to causality)
    assert stats["history_sparse"] is True  # Only 1 supporting trip in window
    assert stats["status_label_vi"] == "Chưa đủ lịch sử khung giờ"
