"""
Candidate Service Expansion Engine for Week 3.

Expands EnergyServiceRequest into candidate station/service alternatives.
Preserves candidate identity as (station_id, service_type).
Specifically handles unresolved multi-service requests:
- AUTO_DETECTED with need_service=True for swap-capable vehicles -> evaluates BOTH CHARGING and BATTERY_SWAP
- DRIVER_REQUEST with requested_service_type=ANY -> evaluates all vehicle-allowed service types
"""

from typing import Iterable
from backend.app.services.candidate.station_catalog import StationRecord
from backend.app.services.demand.models import (
    EnergyServiceRequest,
    RequestSource,
    RequestedServiceType,
    ServiceType,
)


def determine_evaluable_services(request: EnergyServiceRequest) -> list[ServiceType]:
    """
    Determine which service types must be evaluated for this request.
    """
    # 1. If resolved_service_type is explicitly set, only evaluate that service
    if request.resolved_service_type is not None:
        return [request.resolved_service_type]

    # 2. If unresolved AUTO_DETECTED with need_service=True
    if request.request_source == RequestSource.AUTO_DETECTED:
        if request.need_service:
            # Swap-capable vehicles have resolved_service_type=None and evaluate both
            if request.swap_supported and ServiceType.BATTERY_SWAP in request.allowed_service_types:
                return [ServiceType.CHARGING, ServiceType.BATTERY_SWAP]
            return [ServiceType.CHARGING]
        return []

    # 3. If DRIVER_REQUEST
    if request.request_source == RequestSource.DRIVER_REQUEST:
        if request.requested_service_type == RequestedServiceType.ANY:
            return list(request.allowed_service_types)
        elif request.requested_service_type == RequestedServiceType.BATTERY_SWAP:
            return [ServiceType.BATTERY_SWAP]
        elif request.requested_service_type == RequestedServiceType.CHARGING:
            return [ServiceType.CHARGING]

    # Fallback to allowed service types
    return list(request.allowed_service_types)


def expand_candidate_pairs(
    request: EnergyServiceRequest,
    stations: Iterable[StationRecord],
) -> list[tuple[StationRecord, ServiceType]]:
    """
    Expand request across all stations and evaluable service types.
    Returns list of (StationRecord, ServiceType) tuples.
    """
    services = determine_evaluable_services(request)
    pairs: list[tuple[StationRecord, ServiceType]] = []

    for station in stations:
        for service in services:
            # Skip if service is not in vehicle's allowed services (safety guardrail)
            if service in request.allowed_service_types:
                pairs.append((station, service))

    return pairs
