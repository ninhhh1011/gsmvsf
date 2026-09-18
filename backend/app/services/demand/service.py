"""
Unified Demand Service Orchestrator.

Converges AUTO_DETECTED demand evaluation and explicit DRIVER_REQUEST
into a single, canonical EnergyServiceRequest contract for Week 3 consumption.
"""

from datetime import datetime
from typing import Optional
import uuid
import logging

from backend.app.services.demand.auto_detector import AutoDemandDetector
from backend.app.services.demand.capability import (
    VehicleCapabilityResolver,
    get_capability_resolver,
)
from backend.app.services.demand.driver_requester import DriverRequestProcessor
from backend.app.services.demand.models import (
    DemandContext,
    EnergyServiceRequest,
    ReasonCode,
    RequestedServiceType,
    RequestSource,
    ServiceType,
    VehicleCapability,
)

logger = logging.getLogger(__name__)


class DemandService:
    """
    Central service for Week 2 Demand Detection and EnergyServiceRequest creation.
    """

    def __init__(
        self,
        capability_resolver: Optional[VehicleCapabilityResolver] = None,
        auto_detector: Optional[AutoDemandDetector] = None,
        driver_requester: Optional[DriverRequestProcessor] = None,
    ):
        self._resolver = capability_resolver or get_capability_resolver()
        self._auto_detector = auto_detector or AutoDemandDetector(self._resolver)
        self._driver_requester = driver_requester or DriverRequestProcessor(self._resolver)

    def _resolve_vehicle_capability(self, context: DemandContext) -> VehicleCapability:
        """Resolve capability from vehicle_id in context."""
        return self._resolver.resolve_by_vehicle_id(context.vehicle_id)

    def _populate_vehicle_metadata(
        self,
        capability: VehicleCapability,
        vehicle_record: Optional[dict] = None,
    ) -> dict:
        """Extract metadata for EnergyServiceRequest."""
        meta = {
            "vehicle_model": capability.vehicle_model,
            "vehicle_type": capability.vehicle_category.value,
            "battery_capacity_kwh": capability.total_battery_capacity_kwh,
            "usable_capacity_kwh": capability.usable_capacity_kwh,
            "swap_supported": capability.swap_supported,
            "charging_supported": capability.charging_supported,
            "public_swap_compatible": capability.public_swap_compatible,
        }
        if vehicle_record:
            installed = vehicle_record.get("installed_battery_modules")
            if installed is not None and str(installed).strip() != "":
                try:
                    meta["installed_battery_modules"] = int(float(installed))
                except (ValueError, TypeError):
                    pass
        return meta

    def evaluate_auto_demand(
        self,
        context: DemandContext,
        service_request_id: Optional[str] = None,
    ) -> EnergyServiceRequest:
        """
        Evaluate vehicle telemetry in AUTO_DETECTED mode and create an EnergyServiceRequest.
        """
        req_id = service_request_id or f"REQ-AUTO-{uuid.uuid4().hex[:12].upper()}"
        capability = self._resolve_vehicle_capability(context)
        vrow = self._resolver.get_vehicle_record(context.vehicle_id)
        vmeta = self._populate_vehicle_metadata(capability, vrow)

        decision = self._auto_detector.evaluate_need(context, capability)
        resolved_service = self._auto_detector.resolve_service_type(decision.need_service, capability)

        request = EnergyServiceRequest(
            service_request_id=req_id,
            driver_id=context.driver_id,
            vehicle_id=context.vehicle_id,
            trip_id=context.trip_id,
            timestamp=context.timestamp,
            request_source=RequestSource.AUTO_DETECTED,
            need_service=decision.need_service,
            requested_service_type=None,
            allowed_service_types=capability.allowed_service_types,
            resolved_service_type=resolved_service,
            request_valid=True,
            reason_code=decision.reason_code,
            current_soc_pct=context.current_soc_pct,
            estimated_remaining_range_km=context.estimated_remaining_range_km,
            remaining_trip_distance_km=decision.remaining_trip_distance_km,
            safety_reserve_km=decision.safety_reserve_km,
            vehicle_model=vmeta["vehicle_model"],
            vehicle_type=vmeta["vehicle_type"],
            battery_capacity_kwh=vmeta["battery_capacity_kwh"],
            usable_capacity_kwh=vmeta["usable_capacity_kwh"],
            installed_battery_modules=vmeta.get("installed_battery_modules"),
            swap_supported=vmeta["swap_supported"],
            charging_supported=vmeta["charging_supported"],
            public_swap_compatible=vmeta["public_swap_compatible"],
            latitude=context.raw_latitude,
            longitude=context.raw_longitude,
            road_segment_id=context.road_segment_id,
        )
        return request

    def process_driver_request(
        self,
        context: DemandContext,
        requested_service: RequestedServiceType,
        service_request_id: Optional[str] = None,
    ) -> EnergyServiceRequest:
        """
        Process explicit DRIVER_REQUEST and create an EnergyServiceRequest.
        """
        req_id = service_request_id or f"REQ-DRV-{uuid.uuid4().hex[:12].upper()}"
        capability = self._resolve_vehicle_capability(context)
        vrow = self._resolver.get_vehicle_record(context.vehicle_id)
        vmeta = self._populate_vehicle_metadata(capability, vrow)

        decision = self._driver_requester.process_request(capability, requested_service)

        # In explicit driver requests, need_service is True
        need_service = True

        safety_reserve = context.safety_reserve_km
        if safety_reserve is None and context.remaining_trip_distance_km is not None:
            safety_reserve = self._auto_detector.compute_safety_reserve_km(context.remaining_trip_distance_km)

        request = EnergyServiceRequest(
            service_request_id=req_id,
            driver_id=context.driver_id,
            vehicle_id=context.vehicle_id,
            trip_id=context.trip_id,
            timestamp=context.timestamp,
            request_source=RequestSource.DRIVER_REQUEST,
            need_service=need_service,
            requested_service_type=requested_service,
            allowed_service_types=decision.allowed_service_types,
            resolved_service_type=decision.resolved_service_type,
            request_valid=decision.request_valid,
            reason_code=decision.reason_code,
            current_soc_pct=context.current_soc_pct,
            estimated_remaining_range_km=context.estimated_remaining_range_km,
            remaining_trip_distance_km=context.remaining_trip_distance_km,
            safety_reserve_km=safety_reserve,
            vehicle_model=vmeta["vehicle_model"],
            vehicle_type=vmeta["vehicle_type"],
            battery_capacity_kwh=vmeta["battery_capacity_kwh"],
            usable_capacity_kwh=vmeta["usable_capacity_kwh"],
            installed_battery_modules=vmeta.get("installed_battery_modules"),
            swap_supported=vmeta["swap_supported"],
            charging_supported=vmeta["charging_supported"],
            public_swap_compatible=vmeta["public_swap_compatible"],
            latitude=context.raw_latitude,
            longitude=context.raw_longitude,
            road_segment_id=context.road_segment_id,
        )
        return request


# Global service instance
_global_service: Optional[DemandService] = None


def get_demand_service() -> DemandService:
    """Get global DemandService instance."""
    global _global_service
    if _global_service is None:
        _global_service = DemandService()
    return _global_service


def reset_demand_service():
    """Reset global DemandService for testing."""
    global _global_service
    _global_service = None
