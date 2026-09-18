"""
Deterministic AUTO_DETECTED Energy Service Need Detection Engine.

Implements the physical energy feasibility baseline:
- Evaluates battery SOC against safety threshold
- Evaluates estimated remaining range against remaining trip distance + safety reserve
- Determines need_service = below_safe or insufficient_range
- Assigns explainable reason codes
- Enforces V1.3.1 semantics: swap-capable vehicles with need_service=True leave
  resolved_service_type=None (no forced swap).
"""

from typing import Optional
import logging

from backend.app.services.demand.capability import (
    VehicleCapabilityResolver,
    get_capability_resolver,
)
from backend.app.services.demand.models import (
    DemandContext,
    NeedServiceDecision,
    ReasonCode,
    ServiceType,
    VehicleCapability,
)

logger = logging.getLogger(__name__)

# Default safety margin parameters consistent with Dataset V1.3.1
DEFAULT_SAFETY_RESERVE_RATIO = 0.15  # 15% of remaining trip distance
DEFAULT_MIN_SAFETY_RESERVE_KM = 1.0  # Minimum 1.0 km buffer
DEFAULT_SAFE_SOC_BUFFER_PCT = 5.0    # 5.0% buffer above minimum_safe_soc_pct
DEFAULT_MINIMUM_SAFE_SOC_PCT = 15.0  # Default 15% safe SOC threshold


class AutoDemandDetector:
    """
    Evaluates vehicle telemetry and trip context to detect energy service demand.
    """

    def __init__(
        self,
        capability_resolver: Optional[VehicleCapabilityResolver] = None,
        safety_reserve_ratio: float = DEFAULT_SAFETY_RESERVE_RATIO,
        min_safety_reserve_km: float = DEFAULT_MIN_SAFETY_RESERVE_KM,
        safe_soc_buffer_pct: float = DEFAULT_SAFE_SOC_BUFFER_PCT,
    ):
        self._resolver = capability_resolver or get_capability_resolver()
        self._safety_reserve_ratio = safety_reserve_ratio
        self._min_safety_reserve_km = min_safety_reserve_km
        self._safe_soc_buffer_pct = safe_soc_buffer_pct

    def compute_safety_reserve_km(self, remaining_trip_distance_km: Optional[float]) -> float:
        """
        Compute required safety reserve buffer in km.
        Formula: max(min_safety_reserve_km, remaining_trip_km * safety_reserve_ratio).
        """
        if remaining_trip_distance_km is None or remaining_trip_distance_km <= 0.0:
            return self._min_safety_reserve_km
        return max(self._min_safety_reserve_km, remaining_trip_distance_km * self._safety_reserve_ratio)

    def estimate_remaining_range_km(
        self,
        soc_pct: float,
        usable_capacity_kwh: Optional[float],
        consumption_wh_per_km: Optional[float],
    ) -> Optional[float]:
        """
        Estimate remaining vehicle range in km based on usable capacity and consumption.
        Range (km) = (usable_capacity_kwh * 1000 * (soc_pct / 100)) / consumption_wh_per_km
        """
        if usable_capacity_kwh is None or consumption_wh_per_km is None or consumption_wh_per_km <= 0:
            return None
        usable_wh = (usable_capacity_kwh * 1000.0) * (soc_pct / 100.0)
        return usable_wh / consumption_wh_per_km

    def evaluate_need(
        self,
        context: DemandContext,
        capability: Optional[VehicleCapability] = None,
    ) -> NeedServiceDecision:
        """
        Evaluate whether the driver currently needs an energy service.

        Returns:
            NeedServiceDecision with need_service (bool), reason_code (ReasonCode),
            and computed safety metrics.
        """
        # Validate critical state
        if context.current_soc_pct is None:
            return NeedServiceDecision(
                need_service=False,
                reason_code=ReasonCode.MISSING_DATA,
                details="Missing current_soc_pct in telemetry context",
            )

        if context.current_soc_pct < 0.0 or context.current_soc_pct > 100.0:
            return NeedServiceDecision(
                need_service=False,
                reason_code=ReasonCode.INVALID_STATE,
                details=f"Invalid current_soc_pct {context.current_soc_pct}: must be 0-100",
            )

        soc_pct = float(context.current_soc_pct)

        # Determine minimum safe SOC threshold
        min_safe_soc = (
            float(context.minimum_safe_soc_pct)
            if context.minimum_safe_soc_pct is not None
            else DEFAULT_MINIMUM_SAFE_SOC_PCT
        )
        safe_threshold = min_safe_soc + self._safe_soc_buffer_pct
        below_safe = soc_pct <= safe_threshold

        # Determine trip distance and safety reserve
        remaining_trip_km = context.remaining_trip_distance_km
        if remaining_trip_km is None and context.planned_trip_distance_km is not None:
            distance_travelled = context.distance_travelled_km or 0.0
            remaining_trip_km = max(0.0, context.planned_trip_distance_km - distance_travelled)

        safety_reserve_km = context.safety_reserve_km
        if safety_reserve_km is None:
            safety_reserve_km = self.compute_safety_reserve_km(remaining_trip_km)

        # Determine remaining range
        remaining_range_km = context.estimated_remaining_range_km
        if remaining_range_km is None and capability is not None:
            remaining_range_km = self.estimate_remaining_range_km(
                soc_pct=soc_pct,
                usable_capacity_kwh=capability.usable_capacity_kwh or capability.total_battery_capacity_kwh,
                consumption_wh_per_km=context.consumption_wh_per_km,
            )

        # Check range feasibility
        insufficient_range = False
        if remaining_range_km is not None and remaining_trip_km is not None:
            required_range_km = remaining_trip_km + safety_reserve_km
            insufficient_range = remaining_range_km < required_range_km

        need = bool(below_safe or insufficient_range)

        if not need:
            return NeedServiceDecision(
                need_service=False,
                reason_code=ReasonCode.SUFFICIENT_SOC_RANGE,
                safety_reserve_km=safety_reserve_km,
                remaining_trip_distance_km=remaining_trip_km,
                details=f"SOC {soc_pct:.1f}% > {safe_threshold:.1f}%, range sufficient",
            )

        if below_safe and insufficient_range:
            reason = ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE
        elif below_safe:
            reason = ReasonCode.LOW_SOC
        else:
            reason = ReasonCode.INSUFFICIENT_RANGE

        return NeedServiceDecision(
            need_service=True,
            reason_code=reason,
            safety_reserve_km=safety_reserve_km,
            remaining_trip_distance_km=remaining_trip_km,
            details=f"below_safe={below_safe}, insufficient_range={insufficient_range}",
        )

    def resolve_service_type(
        self,
        need_service: bool,
        capability: VehicleCapability,
    ) -> Optional[ServiceType]:
        """
        Determine resolved service type for AUTO_DETECTED request according to V1.3.1 semantics:
        - If need_service is False: None
        - If vehicle supports only CHARGING: ServiceType.CHARGING
        - If vehicle supports both CHARGING and BATTERY_SWAP: None (unresolved, no forced swap)
        """
        if not need_service:
            return None

        # If vehicle is swap capable (has both charging and swap)
        if capability.swap_supported and capability.charging_supported:
            # UNRESOLVED: Candidate generation & ranking will evaluate both services
            return None

        # Charge-only vehicle
        if capability.charging_supported and not capability.swap_supported:
            return ServiceType.CHARGING

        # Fallback (e.g. hypothetical swap-only)
        if capability.swap_supported and not capability.charging_supported:
            return ServiceType.BATTERY_SWAP

        return None
