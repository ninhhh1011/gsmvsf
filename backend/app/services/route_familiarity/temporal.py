"""
Vietnam Local Time-of-Day conditioning for route history.

Time Windows (Project-specific grouping based on Hanoi urban peak hours):
1. MORNING_PEAK: 07:00:00 to < 09:00:00 (Asia/Ho_Chi_Minh)
2. EVENING_PEAK: 17:00:00 to < 19:30:00 (Asia/Ho_Chi_Minh)
3. OFF_PEAK: All other times

Strict Causality:
Only historical trips with completed_at < as_of are considered.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SPARSE_HISTORY_THRESHOLD = 3  # fewer than 3 trips is classified as sparse


class TimeWindowType(str, Enum):
    MORNING_PEAK = "MORNING_PEAK"
    EVENING_PEAK = "EVENING_PEAK"
    OFF_PEAK = "OFF_PEAK"


def get_vietnam_time_window(dt: datetime) -> TimeWindowType:
    """Classify datetime into one of three Vietnam local time windows."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_vn = dt.astimezone(VN_TZ)
    total_minutes = dt_vn.hour * 60 + dt_vn.minute

    # Morning Peak: 07:00 (420m) to < 09:00 (540m)
    if 420 <= total_minutes < 540:
        return TimeWindowType.MORNING_PEAK

    # Evening Peak: 17:00 (1020m) to < 19:30 (1170m)
    if 1020 <= total_minutes < 1170:
        return TimeWindowType.EVENING_PEAK

    return TimeWindowType.OFF_PEAK


def classify_trip_time_window(trip_start_time: datetime) -> dict:
    """Return structured time window metadata for trip start time."""
    window = get_vietnam_time_window(trip_start_time)
    labels = {
        TimeWindowType.MORNING_PEAK: "Cao điểm sáng (07:00 - 09:00)",
        TimeWindowType.EVENING_PEAK: "Cao điểm chiều (17:00 - 19:30)",
        TimeWindowType.OFF_PEAK: "Ngoài cao điểm",
    }
    return {
        "time_window": window.value,
        "window_label_vi": labels[window],
        "is_peak": window in (TimeWindowType.MORNING_PEAK, TimeWindowType.EVENING_PEAK),
    }


def filter_historical_trips_by_window(
    historical_trips: Sequence[dict],
    as_of: datetime,
    target_window: TimeWindowType | None = None,
) -> dict:
    """
    Filter historical completed trips enforcing strict causality (completed_at < as_of).
    Returns statistics for target time window and all-window fallback.
    """
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    if target_window is None:
        target_window = get_vietnam_time_window(as_of)

    valid_causal_trips = []
    for trip in historical_trips:
        completed_at = trip.get("completed_at")
        if not completed_at:
            continue
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        if completed_at < as_of:
            valid_causal_trips.append({
                **trip,
                "completed_at": completed_at,
                "window": get_vietnam_time_window(completed_at),
            })

    same_window_trips = [t for t in valid_causal_trips if t["window"] == target_window]
    same_window_drivers = {t["driver_id"] for t in same_window_trips if t.get("driver_id")}
    all_window_drivers = {t["driver_id"] for t in valid_causal_trips if t.get("driver_id")}

    is_sparse = len(same_window_trips) < SPARSE_HISTORY_THRESHOLD
    status_label = "Chưa đủ lịch sử khung giờ" if is_sparse else "Đủ dữ liệu lịch sử"

    return {
        "target_window": target_window.value,
        "same_window_trip_count": len(same_window_trips),
        "same_window_driver_count": len(same_window_drivers),
        "all_window_trip_count": len(valid_causal_trips),
        "all_window_driver_count": len(all_window_drivers),
        "history_sparse": is_sparse,
        "status_label_vi": status_label,
    }
