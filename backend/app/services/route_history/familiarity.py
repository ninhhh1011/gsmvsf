"""
Historical Familiarity Feature
============================

Bounded historical familiarity signal for route ranking.

Design principles:
- Familiarity is a PENALTY, not a reward
- Bounded by configurable max_penalty
- Does NOT override safety/feasibility checks
- Graceful fallback when no history exists

Formula:
    familiarity_penalty = min(max_penalty, max_penalty * (1 - adherence))

Where:
    adherence = shared_distance / recommended_distance

Example:
    If max_penalty = 0.1 (10%) and adherence = 0.8 (80%):
    penalty = min(0.1, 0.1 * 0.2) = 0.02

    Final cost = existing_ranking_cost + 0.02
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class FamiliaritySource(Enum):
    """Source of historical familiarity signal."""
    INDIVIDUAL_HABITUAL = "individual_habitual"  # Driver's own history
    POPULAR_ROUTE = "popular_route"  # Population-level history
    ROUTE_FAMILY = "route_family"  # From route family support


@dataclass
class FamiliarityContext:
    """Context for familiarity calculation."""
    driver_id: str
    route_adherence: float  # 0-1, how much driver follows recommended route
    family_support: float  # 0-1, route family weighted support
    unique_driver_support: float  # 0-1, how many drivers use this route
    historical_trip_count: int  # Number of historical trips
    has_history: bool  # Whether historical data exists


@dataclass
class FamiliarityPenalty:
    """Result of familiarity penalty calculation."""
    penalty: float  # The penalty value (0 to max_penalty)
    max_penalty: float  # The configured maximum penalty
    source: FamiliaritySource  # Where the signal came from
    adherence: float  # Route adherence used
    driver_trip_count: int  # Trips in driver's history
    family_trip_count: int  # Trips in route family
    is_neutral: bool  # True if no history (neutral behavior)


class FamiliarityConfig:
    """Configuration for familiarity feature."""

    def __init__(
        self,
        enabled: bool = True,
        max_penalty: float = 0.1,  # Max 10% penalty
        adherence_threshold: float = 0.5,  # Below this, full penalty
        individual_weight: float = 0.7,  # Weight for individual history
        popular_weight: float = 0.3,  # Weight for population history
        min_history_trips: int = 3,  # Min trips for individual signal
        family_support_threshold: float = 0.05,  # Min family support
    ):
        self.enabled = enabled
        self.max_penalty = max_penalty
        self.adherence_threshold = adherence_threshold
        self.individual_weight = individual_weight
        self.popular_weight = popular_weight
        self.min_history_trips = min_history_trips
        self.family_support_threshold = family_support_threshold


class HistoricalFamiliarity:
    """
    Calculate bounded familiarity penalty for route ranking.

    This feature:
    - Is a PENALTY, not a reward
    - Bounded by max_penalty
    - Does NOT affect candidate eligibility
    - Gracefully falls back when no history exists

    The penalty is applied as:
        final_cost = existing_cost + familiarity_penalty

    Where familiarity_penalty is calculated based on:
    1. Individual habitual route (driver's own history)
    2. Popular route (population-level history)
    3. Route family support
    """

    def __init__(self, config: FamiliarityConfig):
        self.config = config

    def calculate_penalty(
        self,
        context: FamiliarityContext
    ) -> FamiliarityPenalty:
        """
        Calculate bounded familiarity penalty.

        Args:
            context: Historical context for this route/driver

        Returns:
            FamiliarityPenalty with breakdown
        """
        # If feature disabled, return neutral
        if not self.config.enabled:
            return FamiliarityPenalty(
                penalty=0.0,
                max_penalty=self.config.max_penalty,
                source=FamiliaritySource.INDIVIDUAL_HABITUAL,
                adherence=0.0,
                driver_trip_count=0,
                family_trip_count=0,
                is_neutral=True
            )

        # If no history, return neutral
        if not context.has_history or context.historical_trip_count == 0:
            return FamiliarityPenalty(
                penalty=0.0,
                max_penalty=self.config.max_penalty,
                source=FamiliaritySource.INDIVIDUAL_HABITUAL,
                adherence=0.0,
                driver_trip_count=0,
                family_trip_count=0,
                is_neutral=True
            )

        # Calculate penalty based on adherence
        # Higher adherence = lower penalty
        adherence = max(0.0, min(1.0, context.route_adherence))

        if adherence >= self.config.adherence_threshold:
            # Driver follows recommended route well - small or no penalty
            # Linear decay from threshold to 1.0
            excess_adherence = (adherence - self.config.adherence_threshold) / (1.0 - self.config.adherence_threshold)
            relative_penalty = 1.0 - excess_adherence
        else:
            # Driver diverges from recommended route - full penalty range
            relative_penalty = adherence / self.config.adherence_threshold

        # Calculate raw penalty
        raw_penalty = self.config.max_penalty * (1.0 - relative_penalty)

        # Apply family support bonus (reduces penalty slightly)
        family_bonus = min(0.1, context.family_support * 0.2)  # Up to 10% reduction
        final_penalty = max(0.0, raw_penalty - family_bonus)

        # Clamp to max
        final_penalty = min(self.config.max_penalty, final_penalty)

        return FamiliarityPenalty(
            penalty=final_penalty,
            max_penalty=self.config.max_penalty,
            source=FamiliaritySource.ROUTE_FAMILY if context.family_support > 0 else FamiliaritySource.INDIVIDUAL_HABITUAL,
            adherence=adherence,
            driver_trip_count=context.historical_trip_count,
            family_trip_count=0,
            is_neutral=False
        )

    def apply_to_cost(
        self,
        base_cost: float,
        penalty: FamiliarityPenalty
    ) -> float:
        """
        Apply familiarity penalty to a ranking cost.

        The penalty is ADDED to the cost (making unfamiliar routes slightly
        less preferred), but the penalty is bounded so it cannot
        override strong ranking signals.

        Args:
            base_cost: The existing ranking cost
            penalty: The calculated familiarity penalty

        Returns:
            Adjusted cost with familiarity penalty
        """
        if penalty.is_neutral:
            return base_cost

        return base_cost + penalty.penalty

    def format_penalty_report(self, penalty: FamiliarityPenalty) -> str:
        """Format penalty as human-readable report."""
        lines = [
            "Historical Familiarity Penalty Report",
            "=" * 40,
            f"Penalty: {penalty.penalty:.4f} (max: {penalty.max_penalty:.4f})",
            f"Source: {penalty.source.value}",
            f"Route Adherence: {penalty.adherence:.1%}",
            f"Driver Trips: {penalty.driver_trip_count}",
            f"Family Trips: {penalty.family_trip_count}",
            f"Neutral: {'Yes' if penalty.is_neutral else 'No'}",
        ]
        return "\n".join(lines)


def test_familiarity():
    """Test familiarity calculation."""
    config = FamiliarityConfig(
        enabled=True,
        max_penalty=0.1,
        adherence_threshold=0.5
    )

    familiarity = HistoricalFamiliarity(config)

    # Test case 1: No history - neutral
    print("=== Test 1: No History ===")
    context1 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.0,
        family_support=0.0,
        unique_driver_support=0.0,
        historical_trip_count=0,
        has_history=False
    )
    penalty1 = familiarity.calculate_penalty(context1)
    print(familiarity.format_penalty_report(penalty1))
    assert penalty1.is_neutral
    assert penalty1.penalty == 0.0

    # Test case 2: Perfect adherence - minimal penalty
    print("\n=== Test 2: Perfect Adherence (100%) ===")
    context2 = FamiliarityContext(
        driver_id="D001",
        route_adherence=1.0,  # Follows recommended route perfectly
        family_support=0.5,
        unique_driver_support=0.8,
        historical_trip_count=50,
        has_history=True
    )
    penalty2 = familiarity.calculate_penalty(context2)
    print(familiarity.format_penalty_report(penalty2))
    assert penalty2.penalty < 0.02  # Very small penalty

    # Test case 3: Poor adherence - max penalty
    print("\n=== Test 3: Poor Adherence (0%) ===")
    context3 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.0,  # Completely different from recommended
        family_support=0.0,
        unique_driver_support=0.0,
        historical_trip_count=10,
        has_history=True
    )
    penalty3 = familiarity.calculate_penalty(context3)
    print(familiarity.format_penalty_report(penalty3))
    assert penalty3.penalty == config.max_penalty  # Full penalty

    # Test case 4: 50% adherence - threshold
    print("\n=== Test 4: Threshold Adherence (50%) ===")
    context4 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.5,  # At threshold
        family_support=0.0,
        unique_driver_support=0.0,
        historical_trip_count=10,
        has_history=True
    )
    penalty4 = familiarity.calculate_penalty(context4)
    print(familiarity.format_penalty_report(penalty4))
    # At threshold, penalty should be moderate
    assert 0.03 < penalty4.penalty < 0.07

    # Test case 5: Cost application
    print("\n=== Test 5: Cost Application ===")
    base_cost = 1.0
    adjusted_cost = familiarity.apply_to_cost(base_cost, penalty3)
    print(f"Base cost: {base_cost:.4f}")
    print(f"Adjusted cost: {adjusted_cost:.4f}")
    print(f"Penalty: {penalty3.penalty:.4f}")
    assert abs(adjusted_cost - (base_cost + penalty3.penalty)) < 0.001

    print("\n=== All tests passed! ===")


if __name__ == "__main__":
    test_familiarity()
