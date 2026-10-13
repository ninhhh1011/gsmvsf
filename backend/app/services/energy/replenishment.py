"""Predicted replenishment; never evidence that a live battery was charged."""
from math import isclose, isfinite
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.app.config import settings
from backend.app.services.demand.models import ServiceType


Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Soc = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class ReplenishmentEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    status: Literal['AVAILABLE', 'UNAVAILABLE', 'INFEASIBLE']
    reason: str | None = None
    arrival_energy_kwh: Nonnegative | None = None
    arrival_soc_pct: Soc | None = None
    target_energy_kwh: Nonnegative | None = None
    target_soc_pct: Soc | None = None
    added_energy_kwh: Nonnegative | None = None
    departure_energy_kwh: Nonnegative | None = None
    departure_soc_pct: Soc | None = None
    destination_energy_kwh: Nonnegative | None = None
    destination_soc_pct: Soc | None = None
    consumption_kwh_per_km: Nonnegative | None = None
    effective_capacity_kwh: Nonnegative | None = None
    safety_reserve_km: Nonnegative | None = None
    effective_charge_power_kw: Nonnegative | None = None
    charge_efficiency: float | None = None
    taper_power_factor: float | None = None
    setup_duration_s: Nonnegative | None = None
    service_duration_s: Nonnegative | None = None
    provenance: str = 'PROJECT_CONFIGURABLE_REPLENISHMENT_ASSUMPTION_V1'
    source_reference: str = 'docs/CHARGING_POWER_REFERENCES.md'
    energy_source: str | None = None
    range_source: str | None = None


def energy_basis(energy, capability):
    """Use current energy/range telemetry together, otherwise catalog consumption."""
    if capability is None:
        raise ValueError('Vehicle capability unavailable')
    capacity = capability.usable_capacity_kwh or capability.total_battery_capacity_kwh
    if capability.battery_module_capacity_kwh is not None:
        installed = energy.installed_battery_modules
        if installed is None or not 0 < installed <= (capability.max_battery_modules or 0):
            raise ValueError('Installed battery modules unavailable')
        nominal = capability.battery_module_capacity_kwh * installed
        ratio = (capability.usable_capacity_kwh or capability.total_battery_capacity_kwh) / capability.total_battery_capacity_kwh
        capacity = nominal * ratio
    if energy.usable_capacity_kwh is not None and not isclose(energy.usable_capacity_kwh, capacity, rel_tol=1e-6):
        raise ValueError('Battery capacity conflicts with canonical installed capability')
    soc = energy.current_soc_pct
    if soc is None or not isfinite(soc) or not 0 <= soc <= 100 or not isfinite(capacity) or capacity <= 0:
        raise ValueError('Battery capacity or SOC unavailable')
    current = energy.remaining_energy_kwh
    if current is None:
        current = capacity * soc / 100
    if not isfinite(current) or not 0 <= current <= capacity:
        raise ValueError('Remaining battery energy invalid')
    remaining = energy.estimated_remaining_range_km
    if remaining is not None:
        if not isfinite(remaining) or remaining < 0:
            raise ValueError('Remaining range invalid')
        if remaining == 0:
            if current > 0:
                raise ValueError('Energy and range disagree')
            consumption = capability.get_effective_consumption_wh_per_km() / 1000
        else:
            consumption = current / remaining
    else:
        consumption = capability.get_effective_consumption_wh_per_km() / 1000
    if getattr(energy, 'range_source', None) == 'ENERGY_AND_CATALOG_CONSUMPTION':
        consumption = (getattr(energy, 'consumption_wh_per_km', None) or capability.get_effective_consumption_wh_per_km()) / 1000
    if not isfinite(consumption) or consumption <= 0:
        raise ValueError('Consumption unavailable')
    return capacity, current, consumption


def estimate_replenishment(energy, capability, service_type, distance_to_station_m,
                           distance_station_to_dest_m, snapshot_service_time_min):
    try:
        capacity, current, consumption = energy_basis(energy, capability)
        reserve = energy.safety_reserve_km
        if reserve is None:
            from backend.app.services.demand.auto_detector import SafetyReservePolicy
            reserve = SafetyReservePolicy().compute_safety_reserve_km(
                distance_station_to_dest_m / 1000 if distance_station_to_dest_m is not None else None)
        distances = [distance_to_station_m, reserve]
        if distance_station_to_dest_m is not None:
            distances.append(distance_station_to_dest_m)
        if any(v is None or not isfinite(v) or v < 0 for v in distances):
            raise ValueError('Route energy evidence invalid')
        arrival = current - distance_to_station_m / 1000 * consumption
        if arrival < -1e-9:
            return ReplenishmentEstimate(status='INFEASIBLE', reason='INSUFFICIENT_SOC_TO_REACH')
        arrival = max(0, arrival)
        required = ((distance_station_to_dest_m / 1000 + reserve) * consumption
                    if distance_station_to_dest_m is not None else capacity * settings.charge_no_destination_soc_pct / 100)
        swap = service_type == ServiceType.BATTERY_SWAP
        target = capacity * settings.swap_departure_soc_pct / 100 if swap else max(arrival, required)
        if required > capacity + 1e-9 or (swap and distance_station_to_dest_m is not None and target < required - 1e-9):
            return ReplenishmentEstimate(status='INFEASIBLE', reason='INSUFFICIENT_DEPARTURE_ENERGY')
        target = min(capacity, target)
        added = max(0, target - arrival)
        power = None
        if swap:
            if not isfinite(snapshot_service_time_min) or snapshot_service_time_min < 0:
                raise ValueError('Swap service duration unavailable')
            duration = snapshot_service_time_min * 60
        elif added == 0:
            duration = 0
        else:
            car = capability.vehicle_category.value == 'EV_CAR'
            power = min(settings.charge_car_station_kw, settings.charge_car_vehicle_kw) if car else min(settings.charge_bike_station_kw, settings.charge_bike_vehicle_kw)
            # Official VF 3 DC peak is an upper bound, not a measured charge curve.
            if capability.vehicle_model == 'VF_3':
                power = min(power, 24)
            fast = max(0, min(target, capacity * .8) - min(arrival, capacity * .8))
            slow = added - fast
            duration = settings.charge_setup_s + 3600 * (fast + slow / settings.charge_taper_power_factor) / (power * settings.charge_efficiency)
        departure = target if swap else max(arrival, target)
        destination = max(0, departure - distance_station_to_dest_m / 1000 * consumption) if distance_station_to_dest_m is not None else None
        return ReplenishmentEstimate(status='AVAILABLE', arrival_energy_kwh=arrival, arrival_soc_pct=arrival / capacity * 100,
            energy_source=getattr(energy, 'energy_source', None) or ('EXPLICIT_REMAINING_ENERGY' if energy.remaining_energy_kwh is not None else 'SOC_DERIVED'),
            range_source=getattr(energy, 'range_source', None) or ('EXPLICIT_REMAINING_RANGE' if energy.estimated_remaining_range_km is not None else 'ENERGY_AND_CATALOG_CONSUMPTION'),
            target_energy_kwh=target, target_soc_pct=target / capacity * 100, added_energy_kwh=added,
            departure_energy_kwh=departure, departure_soc_pct=departure / capacity * 100,
            destination_energy_kwh=destination, destination_soc_pct=destination / capacity * 100 if destination is not None else None,
            consumption_kwh_per_km=consumption, effective_capacity_kwh=capacity, safety_reserve_km=reserve,
            effective_charge_power_kw=power,
            charge_efficiency=settings.charge_efficiency if not swap else None,
            taper_power_factor=settings.charge_taper_power_factor if not swap else None,
            setup_duration_s=settings.charge_setup_s if not swap and added > 0 else 0,
            service_duration_s=duration)
    except (ValueError, TypeError, AttributeError) as exc:
        return ReplenishmentEstimate(status='UNAVAILABLE', reason=str(exc))


def refresh_replenishment(estimate, service_type, snapshot_service_time_min):
    """Keep pinned charging evidence; only swap duration comes from live state."""
    if estimate.status != 'AVAILABLE' or estimate.service_duration_s is None:
        raise ValueError('Replenishment evidence unavailable during confirmation')
    if service_type == ServiceType.BATTERY_SWAP:
        if not isfinite(snapshot_service_time_min) or snapshot_service_time_min < 0:
            raise ValueError('Swap service duration unavailable')
        return estimate.model_copy(update={'service_duration_s': snapshot_service_time_min * 60})
    return estimate
