"""
Domain models and contracts for Week 2 Energy Service Need / Demand Detection.

Contains:
- Core enums (ServiceType, RequestedServiceType, RequestSource, ReasonCode)
- Vehicle capability contracts
- Demand telemetry context
- NeedServiceDecision
- Common EnergyServiceRequest contract for Week 3 convergence
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServiceType(str, Enum):
    """Concrete physical energy services provided by the infrastructure."""
    CHARGING = "CHARGING"
    BATTERY_SWAP = "BATTERY_SWAP"


class RequestedServiceType(str, Enum):
    """
    Explicit service intent requested by the driver.
    Includes ANY when the driver has no preference and allows any compatible service.
    """
    CHARGING = "CHARGING"
    BATTERY_SWAP = "BATTERY_SWAP"
    ANY = "ANY"


class RequestSource(str, Enum):
    """Origin of the energy service request."""
    AUTO_DETECTED = "AUTO_DETECTED"
    DRIVER_REQUEST = "DRIVER_REQUEST"


class ReasonCode(str, Enum):
    """Explainable reason code for energy service decisions and validity."""
    # AUTO_DETECTED reasons
    SUFFICIENT_SOC_RANGE = "SUFFICIENT_SOC_RANGE"
    LOW_SOC = "LOW_SOC"
    INSUFFICIENT_RANGE = "INSUFFICIENT_RANGE"
    LOW_SOC_AND_INSUFFICIENT_RANGE = "LOW_SOC_AND_INSUFFICIENT_RANGE"
    INSUFFICIENT_POST_DESTINATION_RESERVE = "INSUFFICIENT_POST_DESTINATION_RESERVE"
    DESTINATION_NOT_REACHABLE = "DESTINATION_NOT_REACHABLE"

    # DRIVER_REQUEST reasons
    VALID_REQUEST = "VALID_REQUEST"
    UNSUPPORTED_SERVICE = "UNSUPPORTED_SERVICE"

    # Anomaly / Validation reasons
    MISSING_DATA = "MISSING_DATA"
    INVALID_STATE = "INVALID_STATE"
    STALE_STATE = "STALE_STATE"


class VehicleCategory(str, Enum):
    """Broad vehicle category classification."""
    EV_CAR = "EV_CAR"
    EV_MOTORBIKE = "EV_MOTORBIKE"


class VehicleCapability(BaseModel):
    """
    Deterministic physical capabilities of a specific vehicle model.
    Derived from vehicle_model_catalog.csv.
    """
    model_config = ConfigDict(frozen=True)

    vehicle_model: str
    vehicle_category: VehicleCategory
    battery_architecture: str = "FIXED_TRACTION_PACK"
    battery_capacity_kwh: Optional[float] = None
    usable_capacity_kwh: Optional[float] = None
    battery_module_capacity_kwh: Optional[float] = None
    max_battery_modules: Optional[float] = None
    charging_supported: bool = True
    swap_supported: bool = False
    public_swap_compatible: bool = False
    charging_interface_class: Optional[str] = None
    swap_battery_family: Optional[str] = None
    capability_source_class: str = "VINFAST_OFFICIAL_BATTERY_SPEC"

    @property
    def total_battery_capacity_kwh(self) -> float:
        """Return explicit battery capacity or compute from module spec."""
        if self.battery_capacity_kwh is not None:
            return self.battery_capacity_kwh
        if self.battery_module_capacity_kwh is not None and self.max_battery_modules is not None:
            return self.battery_module_capacity_kwh * self.max_battery_modules
        return 0.0

    @property
    def allowed_service_types(self) -> list[ServiceType]:
        """Return deterministic list of supported services for this vehicle model."""
        services: list[ServiceType] = []
        if self.charging_supported:
            services.append(ServiceType.CHARGING)
        if self.swap_supported:
            services.append(ServiceType.BATTERY_SWAP)
        return services

    def is_service_supported(self, service: ServiceType) -> bool:
        """Check if vehicle physically supports a specific service."""
        return service in self.allowed_service_types


class DemandContext(BaseModel):
    """
    Realtime telemetry and trip context required to evaluate energy service need.
    """
    model_config = ConfigDict(extra="ignore")

    vehicle_id: str
    driver_id: Optional[str] = None
    trip_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    current_soc_pct: Optional[float] = None
    estimated_remaining_range_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    distance_travelled_km: Optional[float] = None
    planned_trip_distance_km: Optional[float] = None
    safety_reserve_km: Optional[float] = None
    remaining_energy_kwh: Optional[float] = None
    energy_margin_km: Optional[float] = None
    consumption_wh_per_km: Optional[float] = None
    minimum_safe_soc_pct: Optional[float] = None

    # Realtime location / map-matching state from Week 1 (if available)
    raw_latitude: Optional[float] = None
    raw_longitude: Optional[float] = None
    road_segment_id: Optional[str] = None


class NeedServiceDecision(BaseModel):
    """
    Result of evaluating whether a driver requires energy service.
    """
    need_service: bool
    reason_code: ReasonCode
    safety_reserve_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    remaining_energy_kwh: Optional[float] = None
    energy_margin_km: Optional[float] = None
    details: Optional[str] = None


class EnergyServiceRequest(BaseModel):
    """
    Canonical converged contract for Week 2 output / Week 3 input.

    Normalizes both AUTO_DETECTED and DRIVER_REQUEST into one schema.
    Contains NO station candidates, NO ranking metrics, and NO routing geometry.
    """
    model_config = ConfigDict(extra="forbid")

    service_request_id: str
    driver_id: Optional[str] = None
    vehicle_id: str
    trip_id: Optional[str] = None
    timestamp: datetime

    request_source: RequestSource
    need_service: bool

    # Requested service (from driver if DRIVER_REQUEST, None if AUTO_DETECTED)
    requested_service_type: Optional[RequestedServiceType] = None

    # Services allowed by vehicle capability
    allowed_service_types: list[ServiceType]

    # Concrete resolved service if deterministic, None if unresolved (e.g. swap-capable AUTO or ANY)
    resolved_service_type: Optional[ServiceType] = None

    request_valid: bool = True
    reason_code: ReasonCode

    # Energy and trip metrics
    current_soc_pct: Optional[float] = None
    remaining_energy_kwh: Optional[float] = None
    estimated_remaining_range_km: Optional[float] = None
    remaining_trip_distance_km: Optional[float] = None
    safety_reserve_km: Optional[float] = None
    energy_margin_km: Optional[float] = None

    # Vehicle metadata
    vehicle_model: Optional[str] = None
    vehicle_type: Optional[str] = None
    battery_capacity_kwh: Optional[float] = None
    usable_capacity_kwh: Optional[float] = None
    installed_battery_modules: Optional[int] = None
    swap_supported: bool = False
    charging_supported: bool = True
    public_swap_compatible: bool = False

    # Location context (from Week 1 state if provided)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    road_segment_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_semantic_invariants(self) -> "EnergyServiceRequest":
        """
        Verify Week 2 semantic invariants:
        1. If need_service is False, resolved_service_type must be None.
        2. If request_valid is False, resolved_service_type must be None and reason_code is UNSUPPORTED_SERVICE.
        3. If AUTO_DETECTED and need_service is True, swap-capable vehicles (both services allowed) must have resolved_service_type=None.
        4. If DRIVER_REQUEST with requested_service_type=ANY, resolved_service_type must be None.
        5. resolved_service_type, if present, must be in allowed_service_types.
        """
        if not self.need_service:
            if self.resolved_service_type is not None:
                raise ValueError("resolved_service_type must be None when need_service is False")

        if not self.request_valid:
            if self.resolved_service_type is not None:
                raise ValueError("resolved_service_type must be None when request_valid is False")
            if self.reason_code != ReasonCode.UNSUPPORTED_SERVICE:
                # Unless specified as another invalid reason
                pass

        if (
            self.request_source == RequestSource.AUTO_DETECTED
            and self.need_service
            and len(self.allowed_service_types) > 1
        ):
            if self.resolved_service_type is not None:
                raise ValueError(
                    "AUTO_DETECTED request for multi-service capable vehicle must NOT force a resolved service (must be None)"
                )

        if self.requested_service_type == RequestedServiceType.ANY:
            if self.resolved_service_type is not None:
                raise ValueError(
                    "DRIVER_REQUEST with requested_service_type=ANY must NOT resolve to a concrete service (must be None)"
                )

        if self.resolved_service_type is not None:
            if self.resolved_service_type not in self.allowed_service_types:
                raise ValueError(
                    f"resolved_service_type {self.resolved_service_type} not in allowed_service_types {self.allowed_service_types}"
                )

        return self
