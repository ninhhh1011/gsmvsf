"""
Deterministic Service Compatibility Engine for Week 3.

Checks physical and operational compatibility between a VinFast vehicle and a candidate
station for a specific service type (CHARGING vs BATTERY_SWAP).
Preserves exact semantics from Dataset V1.3.1 generator.
"""

from typing import Any, Optional, Union
from backend.app.services.candidate.station_catalog import StationRecord, _parse_tokens
from backend.app.services.demand.capability import VehicleCapability
from backend.app.services.demand.models import ServiceType, VehicleCategory


def check_station_service_compatibility(
    vehicle: Union[VehicleCapability, dict[str, Any], Any],
    station: StationRecord,
    service_type: Union[ServiceType, str],
) -> bool:
    """
    Evaluate if vehicle can physically receive the given service at the station.

    Matches Dataset V1.3.1 service_compatible() rule:
    1. Service slot availability (charging_slots > 0 or swap_slots > 0)
    2. Vehicle service capability (charging_supported / swap_supported)
    3. Vehicle category match (EV_CAR vs EV_MOTORBIKE in supported_vehicle_type)
    4. Connector match (CCS2_TYPE2 vs VINFAST_MOTORCYCLE_CHARGING)
    5. Swap battery family match for BATTERY_SWAP (VINFAST_SWAP_LFP_1_5_KWH in battery_type)
    """
    # Normalize service type
    svc_str = service_type.value if isinstance(service_type, ServiceType) else str(service_type)

    # Extract vehicle attributes uniformly
    if isinstance(vehicle, VehicleCapability):
        charging_supported = vehicle.charging_supported
        swap_supported = vehicle.swap_supported
        v_category = vehicle.vehicle_category.value if isinstance(vehicle.vehicle_category, VehicleCategory) else str(vehicle.vehicle_category)
        v_connector = vehicle.charging_interface_class or ("CCS2_TYPE2" if v_category == "EV_CAR" else "VINFAST_MOTORCYCLE_CHARGING")
        v_swap_family = vehicle.swap_battery_family or ""
    elif isinstance(vehicle, dict):
        charging_supported = bool(vehicle.get("charging_supported", True))
        swap_supported = bool(vehicle.get("swap_supported", False))
        v_category = str(vehicle.get("vehicle_type", vehicle.get("vehicle_category", "")))
        v_connector = str(vehicle.get("connector_type", vehicle.get("charging_interface_class", "")))
        v_swap_family = str(vehicle.get("swap_battery_family", ""))
    else:
        charging_supported = bool(getattr(vehicle, "charging_supported", True))
        swap_supported = bool(getattr(vehicle, "swap_supported", False))
        v_category = str(getattr(vehicle, "vehicle_type", getattr(vehicle, "vehicle_category", "")))
        v_connector = str(getattr(vehicle, "connector_type", getattr(vehicle, "charging_interface_class", "")))
        v_swap_family = str(getattr(vehicle, "swap_battery_family", ""))

    # 1. Service support & Station slot check
    if svc_str == "CHARGING":
        if not charging_supported:
            return False
        if station.charging_slots <= 0:
            return False
    elif svc_str == "BATTERY_SWAP":
        if not swap_supported:
            return False
        if station.swap_slots <= 0:
            return False
    else:
        return False

    # 2. Vehicle category matching
    st_categories = _parse_tokens(station.supported_vehicle_type)
    if v_category not in st_categories:
        return False

    # 3. Connector matching
    st_connectors = _parse_tokens(station.connector_type)
    if v_connector not in st_connectors:
        return False

    # 4. Swap battery family matching (BATTERY_SWAP only)
    if svc_str == "BATTERY_SWAP":
        clean_family = v_swap_family.strip()
        if not clean_family or clean_family.lower() in ("none", "nan", ""):
            return False
        st_batteries = _parse_tokens(station.battery_type)
        if clean_family not in st_batteries:
            return False

    return True
