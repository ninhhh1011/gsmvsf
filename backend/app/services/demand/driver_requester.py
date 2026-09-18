"""
Deterministic DRIVER_REQUEST Intent Resolution Engine.

Validates explicit driver service intent (CHARGING, BATTERY_SWAP, ANY)
against vehicle physical capabilities.
Enforces V1.3.1 semantics:
- Car/Charge-only bike requesting BATTERY_SWAP is rejected with UNSUPPORTED_SERVICE.
- Swap-capable vehicle requesting ANY remains resolved_service_type=None (no forced CHARGING).
- Unsupported requests are NOT silently converted.
- Explicit driver requests have need_service = True.
"""

from typing import Optional
import logging

from backend.app.services.demand.capability import (
    VehicleCapabilityResolver,
    get_capability_resolver,
)
from backend.app.services.demand.models import (
    ReasonCode,
    RequestedServiceType,
    ServiceType,
    VehicleCapability,
)

logger = logging.getLogger(__name__)


class DriverRequestDecision:
    """Result of validating an explicit driver service request."""

    def __init__(
        self,
        request_valid: bool,
        reason_code: ReasonCode,
        allowed_service_types: list[ServiceType],
        resolved_service_type: Optional[ServiceType] = None,
        details: Optional[str] = None,
    ):
        self.request_valid = request_valid
        self.reason_code = reason_code
        self.allowed_service_types = allowed_service_types
        self.resolved_service_type = resolved_service_type
        self.details = details


class DriverRequestProcessor:
    """
    Processes and validates explicit driver service intents.
    """

    def __init__(self, capability_resolver: Optional[VehicleCapabilityResolver] = None):
        self._resolver = capability_resolver or get_capability_resolver()

    def process_request(
        self,
        capability: VehicleCapability,
        requested_service: RequestedServiceType,
    ) -> DriverRequestDecision:
        """
        Validate driver requested service against vehicle capabilities.

        Rules:
        - Car + CHARGING -> valid=True, resolved=CHARGING, reason=VALID_REQUEST
        - Car + BATTERY_SWAP -> valid=False, resolved=None, reason=UNSUPPORTED_SERVICE
        - Car + ANY -> valid=False, resolved=None, reason=UNSUPPORTED_SERVICE (ANY only valid for multi-service vehicles)
        - Charge-only bike + CHARGING -> valid=True, resolved=CHARGING, reason=VALID_REQUEST
        - Charge-only bike + BATTERY_SWAP -> valid=False, resolved=None, reason=UNSUPPORTED_SERVICE
        - Charge-only bike + ANY -> valid=False, resolved=None, reason=UNSUPPORTED_SERVICE
        - Swap bike + CHARGING -> valid=True, resolved=CHARGING, reason=VALID_REQUEST
        - Swap bike + BATTERY_SWAP -> valid=True, resolved=BATTERY_SWAP, reason=VALID_REQUEST
        - Swap bike + ANY -> valid=True, allowed=[CHARGING, BATTERY_SWAP], resolved=None, reason=VALID_REQUEST
        """
        allowed = capability.allowed_service_types

        if requested_service == RequestedServiceType.CHARGING:
            if ServiceType.CHARGING in allowed:
                return DriverRequestDecision(
                    request_valid=True,
                    reason_code=ReasonCode.VALID_REQUEST,
                    allowed_service_types=allowed,
                    resolved_service_type=ServiceType.CHARGING,
                    details="Driver requested CHARGING; vehicle supports charging",
                )
            return DriverRequestDecision(
                request_valid=False,
                reason_code=ReasonCode.UNSUPPORTED_SERVICE,
                allowed_service_types=allowed,
                resolved_service_type=None,
                details="Driver requested CHARGING; vehicle does not support charging",
            )

        elif requested_service == RequestedServiceType.BATTERY_SWAP:
            if ServiceType.BATTERY_SWAP in allowed:
                return DriverRequestDecision(
                    request_valid=True,
                    reason_code=ReasonCode.VALID_REQUEST,
                    allowed_service_types=allowed,
                    resolved_service_type=ServiceType.BATTERY_SWAP,
                    details="Driver requested BATTERY_SWAP; vehicle supports battery swap",
                )
            return DriverRequestDecision(
                request_valid=False,
                reason_code=ReasonCode.UNSUPPORTED_SERVICE,
                allowed_service_types=allowed,
                resolved_service_type=None,
                details=f"Driver requested BATTERY_SWAP; vehicle model {capability.vehicle_model} does not support swap",
            )

        elif requested_service == RequestedServiceType.ANY:
            # ANY indicates driver has no preference among available services.
            # Only valid for vehicles supporting multiple services (swap-capable motorbikes).
            if len(allowed) > 1 and ServiceType.BATTERY_SWAP in allowed and ServiceType.CHARGING in allowed:
                return DriverRequestDecision(
                    request_valid=True,
                    reason_code=ReasonCode.VALID_REQUEST,
                    allowed_service_types=allowed,
                    resolved_service_type=None,  # UNRESOLVED: ranking will pick best
                    details="Driver requested ANY; vehicle supports both charging and swap",
                )
            # For single-service vehicles, ANY is not supported as an unconstrained request
            return DriverRequestDecision(
                request_valid=False,
                reason_code=ReasonCode.UNSUPPORTED_SERVICE,
                allowed_service_types=allowed,
                resolved_service_type=None,
                details=f"Driver requested ANY; vehicle model {capability.vehicle_model} supports only single service",
            )

        # Fallback for unexpected service type
        return DriverRequestDecision(
            request_valid=False,
            reason_code=ReasonCode.UNSUPPORTED_SERVICE,
            allowed_service_types=allowed,
            resolved_service_type=None,
            details=f"Unrecognized requested service type: {requested_service}",
        )
