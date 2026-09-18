"""
Deterministic AUTO_DETECTED Energy Service Need Detection Engine.

Implements the physical energy feasibility baseline:
- Evaluates battery SOC against safety threshold
- Computes remaining usable energy (kWh) and estimated range (km)
- Evaluates estimated range against remaining trip distance + safety reserve (km)
- Computes energy margin (km) = estimated_range - required_safe_range
- Distinguishes physical energy states:
  * STATE A: SAFE (estimated_range >= remaining_trip + safety_reserve) -> SUFFICIENT_SOC_RANGE
  * STATE B: DESTINATION REACHABLE BUT RESERVE INSUFFICIENT -> INSUFFICIENT_POST_DESTINATION_RESERVE
  * STATE C: DESTINATION NOT SAFELY REACHABLE -> DESTINATION_NOT_REACHABLE
  * Combined with LOW_SOC / LOW_SOC_AND_INSUFFICIENT_RANGE when SOC is below safety guard.
- Enforces V1.3.1 semantics: swap-capable vehicles with need_service=True leave
  resolved_service_type=None (no forced swap).
"""

from typing import Optional
from dataclasses import dataclass
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
DEFAULT_SAFETY_RESERVE_RATIO = 0.15          # 15% of remaining trip distance
DEFAULT_MIN_SAFETY_RESERVE_KM = 1.0          # Minimum 1.0 km buffer
DEFAULT_LOW_SOC_WARNING_MARGIN_PCT = 5.0     # 5.0% dispatch warning buffer above minimum_safe_soc_pct
DEFAULT_MINIMUM_SAFE_SOC_PCT = 15.0          # Default 15% safe SOC threshold floor


@dataclass(frozen=True)
class SafetyReservePolicy:
    """
    Configurable domain policy for safety and service-access reserve.
    Ensures reserve buffers and low-SOC guards are explicit, documented domain policies,
    not unexplained magic constants.

    Fields:
    - safety_reserve_ratio: Ratio of remaining trip distance kept as safety buffer (default 0.15 = 15%).
    - min_safety_reserve_km: Absolute minimum safety reserve in km (default 1.0 km).
    - fixed_safety_reserve_km: If set, overrides ratio calculation with a fixed buffer (e.g. 20.0 km).
    - low_soc_warning_margin_pct: Percentage points above minimum_safe_soc_pct at which the low-battery
      guard triggers (default 5.0%, representing a dispatch warning buffer to prevent deep discharge).
    - default_minimum_safe_soc_pct: Baseline minimum safe battery SOC percentage (default 15.0%).
    """
    safety_reserve_ratio: float = DEFAULT_SAFETY_RESERVE_RATIO
    min_safety_reserve_km: float = DEFAULT_MIN_SAFETY_RESERVE_KM
    fixed_safety_reserve_km: Optional[float] = None
    low_soc_warning_margin_pct: float = DEFAULT_LOW_SOC_WARNING_MARGIN_PCT
    default_minimum_safe_soc_pct: float = DEFAULT_MINIMUM_SAFE_SOC_PCT

    @property
    def safe_soc_buffer_pct(self) -> float:
        """Backward-compatible alias for low_soc_warning_margin_pct."""
        return self.low_soc_warning_margin_pct

    def compute_safety_reserve_km(
        self,
        remaining_trip_distance_km: Optional[float],
        vehicle_model: Optional[str] = None,
    ) -> float:
        """
        Compute required safety reserve buffer in km.
        If fixed_safety_reserve_km is explicitly set, use it.
        Otherwise formula: max(min_safety_reserve_km, remaining_trip_km * safety_reserve_ratio).
        """
        if self.fixed_safety_reserve_km is not None and self.fixed_safety_reserve_km > 0.0:
            return self.fixed_safety_reserve_km

        if remaining_trip_distance_km is None or remaining_trip_distance_km <= 0.0:
            return self.min_safety_reserve_km

        return max(self.min_safety_reserve_km, remaining_trip_distance_km * self.safety_reserve_ratio)


class AutoDemandDetector:
    """
    Evaluates vehicle telemetry and trip context to detect energy service demand.
    """

    def __init__(
        self,
        capability_resolver: Optional[VehicleCapabilityResolver] = None,
        policy: Optional[SafetyReservePolicy] = None,
        safety_reserve_ratio: float = DEFAULT_SAFETY_RESERVE_RATIO,
        min_safety_reserve_km: float = DEFAULT_MIN_SAFETY_RESERVE_KM,
        low_soc_warning_margin_pct: float = DEFAULT_LOW_SOC_WARNING_MARGIN_PCT,
    ):
        self._resolver = capability_resolver or get_capability_resolver()
        if policy is not None:
            self._policy = policy
        else:
            self._policy = SafetyReservePolicy(
                safety_reserve_ratio=safety_reserve_ratio,
                min_safety_reserve_km=min_safety_reserve_km,
                low_soc_warning_margin_pct=low_soc_warning_margin_pct,
            )

    @property
    def policy(self) -> SafetyReservePolicy:
        """Return the current safety reserve policy."""
        return self._policy

    def compute_safety_reserve_km(self, remaining_trip_distance_km: Optional[float]) -> float:
        """Compute required safety reserve buffer in km via policy."""
        return self._policy.compute_safety_reserve_km(remaining_trip_distance_km)

    def calculate_remaining_energy_kwh(
        self,
        soc_pct: float,
        usable_capacity_kwh: Optional[float],
    ) -> Optional[float]:
        """
        Calculate remaining energy in battery in kWh.
        remaining_energy_kwh = usable_capacity_kwh * (soc_pct / 100.0)
        """
        if usable_capacity_kwh is None or usable_capacity_kwh <= 0.0:
            return None
        return usable_capacity_kwh * (soc_pct / 100.0)

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
        if usable_capacity_kwh is None or consumption_wh_per_km is None or consumption_wh_per_km <= 0.0:
            return None
        usable_wh = (usable_capacity_kwh * 1000.0) * (soc_pct / 100.0)
        return usable_wh / consumption_wh_per_km

    def evaluate_need(
        self,
        context: DemandContext,
        capability: Optional[VehicleCapability] = None,
    ) -> NeedServiceDecision:
        """
        Evaluate whether the driver currently needs an energy service based on:
        - Battery SOC safety threshold
        - Post-destination energy feasibility and safety reserve
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

        if context.remaining_trip_distance_km is not None and context.remaining_trip_distance_km < 0.0:
            return NeedServiceDecision(
                need_service=False,
                reason_code=ReasonCode.INVALID_STATE,
                details=f"Invalid remaining_trip_distance_km {context.remaining_trip_distance_km}: cannot be negative",
            )

        if context.consumption_wh_per_km is not None and context.consumption_wh_per_km <= 0.0:
            return NeedServiceDecision(
                need_service=False,
                reason_code=ReasonCode.INVALID_STATE,
                details=f"Invalid consumption_wh_per_km {context.consumption_wh_per_km}: must be > 0",
            )

        soc_pct = float(context.current_soc_pct)

        # Usable capacity
        usable_cap_kwh = None
        if capability is not None:
            usable_cap_kwh = capability.usable_capacity_kwh or capability.total_battery_capacity_kwh

        # Calculate remaining energy in kWh
        remaining_energy_kwh = context.remaining_energy_kwh
        if remaining_energy_kwh is None and usable_cap_kwh is not None:
            remaining_energy_kwh = self.calculate_remaining_energy_kwh(soc_pct, usable_cap_kwh)

        # Determine minimum safe SOC threshold
        min_safe_soc = (
            float(context.minimum_safe_soc_pct)
            if context.minimum_safe_soc_pct is not None
            else self._policy.default_minimum_safe_soc_pct
        )
        safe_threshold = min_safe_soc + self._policy.low_soc_warning_margin_pct
        below_safe = soc_pct <= safe_threshold

        # Determine remaining trip distance
        remaining_trip_km = context.remaining_trip_distance_km
        if remaining_trip_km is None and context.planned_trip_distance_km is not None:
            distance_travelled = context.distance_travelled_km or 0.0
            remaining_trip_km = max(0.0, context.planned_trip_distance_km - distance_travelled)

        # Compute safety reserve
        safety_reserve_km = context.safety_reserve_km
        if safety_reserve_km is None:
            safety_reserve_km = self._policy.compute_safety_reserve_km(
                remaining_trip_km,
                vehicle_model=capability.vehicle_model if capability else None,
            )

        # Determine remaining range
        remaining_range_km = context.estimated_remaining_range_km
        if remaining_range_km is None and usable_cap_kwh is not None:
            remaining_range_km = self.estimate_remaining_range_km(
                soc_pct=soc_pct,
                usable_capacity_kwh=usable_cap_kwh,
                consumption_wh_per_km=context.consumption_wh_per_km,
            )

        # Check range feasibility and compute energy margin
        insufficient_range = False
        destination_unreachable = False
        destination_reachable_reserve_insufficient = False
        energy_margin_km = None

        if remaining_range_km is not None and remaining_trip_km is not None:
            required_safe_range_km = remaining_trip_km + safety_reserve_km
            energy_margin_km = remaining_range_km - required_safe_range_km
            insufficient_range = remaining_range_km < required_safe_range_km

            if remaining_range_km < remaining_trip_km:
                destination_unreachable = True
            elif remaining_range_km < required_safe_range_km:
                destination_reachable_reserve_insufficient = True

        need = bool(below_safe or insufficient_range)

        # Classify reason code based on exact energy state
        if not need:
            # STATE A: SAFE
            reason = ReasonCode.SUFFICIENT_SOC_RANGE
        elif below_safe and insufficient_range:
            reason = ReasonCode.LOW_SOC_AND_INSUFFICIENT_RANGE
        elif below_safe:
            reason = ReasonCode.LOW_SOC
        else:
            # not below_safe, but insufficient range
            if destination_unreachable:
                # STATE C: Destination not reachable
                reason = ReasonCode.DESTINATION_NOT_REACHABLE
            elif destination_reachable_reserve_insufficient:
                # STATE B: Destination reachable, but reserve insufficient
                reason = ReasonCode.INSUFFICIENT_POST_DESTINATION_RESERVE
            else:
                reason = ReasonCode.INSUFFICIENT_RANGE

        return NeedServiceDecision(
            need_service=need,
            reason_code=reason,
            safety_reserve_km=round(safety_reserve_km, 3) if safety_reserve_km is not None else None,
            remaining_trip_distance_km=round(remaining_trip_km, 3) if remaining_trip_km is not None else None,
            remaining_energy_kwh=round(remaining_energy_kwh, 3) if remaining_energy_kwh is not None else None,
            estimated_remaining_range_km=round(remaining_range_km, 3) if remaining_range_km is not None else None,
            energy_margin_km=round(energy_margin_km, 3) if energy_margin_km is not None else None,
            details=(
                f"below_safe={below_safe}, insufficient_range={insufficient_range}, "
                f"margin={round(energy_margin_km, 2) if energy_margin_km is not None else 'N/A'}km"
            ),
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

        # Swap capable (both charging and swap)
        if capability.swap_supported and capability.charging_supported:
            # UNRESOLVED: Candidate generation & ranking will evaluate both services
            return None

        # Charge-only vehicle
        if capability.charging_supported and not capability.swap_supported:
            return ServiceType.CHARGING

        # Fallback (hypothetical swap-only)
        if capability.swap_supported and not capability.charging_supported:
            return ServiceType.BATTERY_SWAP

        return None
