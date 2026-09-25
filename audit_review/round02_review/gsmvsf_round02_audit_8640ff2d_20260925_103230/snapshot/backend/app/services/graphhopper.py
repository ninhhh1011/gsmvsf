"""Shared vehicle-to-GraphHopper profile mapping. No engine selection."""
import csv
import httpx
from functools import lru_cache

from backend.app.config import settings

# One event-loop-local client owned by application lifespan.
http_client: httpx.AsyncClient | None = None


def profile_for_vehicle(category: str | None) -> str:
    try:
        return {"EV_CAR": "car", "EV_MOTORBIKE": "motorcycle"}[category]
    except KeyError:
        raise ValueError("A supported vehicle category (EV_CAR or EV_MOTORBIKE) is required") from None


@lru_cache(maxsize=1)
def _vehicle_metadata():
    # Canonical runtime metadata only; never evaluation labels.
    with (settings.dataset_path / "vehicles/vehicles.csv").open(encoding="utf-8") as f:
        vehicles = {row["vehicle_id"]: row for row in csv.DictReader(f)}
    with (settings.dataset_path / "trips/trips.csv").open(encoding="utf-8") as f:
        trips = {row["trip_id"]: row["vehicle_id"] for row in csv.DictReader(f)}
    drivers = {row["driver_id"]: row["vehicle_id"] for row in vehicles.values()}
    return vehicles, trips, drivers


def resolve_vehicle_category(category=None, vehicle_id=None, trip_id=None, driver_id=None):
    """Resolve existing callers' metadata; reject conflicting explicit category."""
    vehicles, trips, drivers = _vehicle_metadata()
    ids = {v for v in (vehicle_id, trips.get(trip_id), drivers.get(driver_id)) if v}
    if len(ids) > 1:
        raise ValueError("Conflicting trip/driver/vehicle identity")
    resolved = None
    if ids:
        identity = ids.pop()
        if identity not in vehicles:
            raise ValueError(f"Unknown vehicle: {identity}")
        resolved = vehicles[identity]["vehicle_type"]
    if category and resolved and category != resolved:
        raise ValueError("Vehicle category conflicts with canonical vehicle metadata")
    result = category or resolved
    profile_for_vehicle(result)
    return result
