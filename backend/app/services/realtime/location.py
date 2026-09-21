"""Request-time location bridge over the existing Week 1 accepted state."""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from backend.app.services.realtime.state import get_state_store
from backend.app.services.snapshots.models import StateError


@dataclass(frozen=True)
class CurrentLocation:
    latitude: float | None = None
    longitude: float | None = None
    road_segment_id: str | None = None
    source: str = 'LOCATION_UNAVAILABLE'
    timestamp: datetime | None = None


def utc(value: datetime) -> datetime:
    # Week 1 also accepts legacy naive UTC observations; this does not age state.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def valid_coordinates(latitude, longitude):
    return (latitude is not None and longitude is not None and
            isfinite(latitude) and isfinite(longitude) and
            -90 <= latitude <= 90 and -180 <= longitude <= 180)


def resolve_current_location(driver_id, latitude, longitude, road_segment_id, request_time):
    """Use explicit, matched, then accepted raw; never read future current state.

    Week 1 owns match reset/validity. last_match_time is its observation event
    time; MatchedState.matched_at is a wall-clock execution time, not event time.
    No separate freshness threshold or historical state reconstruction is added.
    """
    timestamp = utc(request_time)
    if (latitude is None) != (longitude is None):
        raise StateError('Both origin coordinates are required together', 'INVALID_LOCATION', 422)
    if latitude is not None:
        if not valid_coordinates(latitude, longitude):
            raise StateError('Invalid origin coordinates', 'INVALID_LOCATION', 422)
        return CurrentLocation(latitude, longitude, road_segment_id, 'EXPLICIT', timestamp)
    state = get_state_store().get(driver_id) if driver_id is not None else None
    if state is not None:
        matched = state.last_matched_state
        if (matched is not None and state.last_match_time is not None and
                utc(state.last_match_time) <= timestamp and
                valid_coordinates(matched.matched_latitude, matched.matched_longitude)):
            return CurrentLocation(matched.matched_latitude, matched.matched_longitude,
                                   matched.road_segment_id, 'MATCHED', utc(state.last_match_time))
        if state.observations:
            raw = state.observations[-1]
            if utc(raw.timestamp) <= timestamp and valid_coordinates(raw.latitude, raw.longitude):
                return CurrentLocation(raw.latitude, raw.longitude, None,
                                       'RAW_GPS_FALLBACK', utc(raw.timestamp))
    return CurrentLocation()
