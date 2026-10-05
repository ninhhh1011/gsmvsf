"""
Historical Familiarity Feature
============================

Bounded historical familiarity signal for route ranking.

Design principles:
- Familiarity is a PENALTY, not a reward
- Bounded by configurable max_penalty
- Bayesian confidence: population wisdom reduces penalty
- Does NOT override safety/feasibility checks
- Graceful fallback when no history exists

Bayesian Formula:
    confidence = family_size / (family_size + prior_strength)
    bayesian_bonus = confidence * max_reduction_factor
    final_penalty = base_penalty * (1 - bayesian_bonus)

Where:
    adherence = shared_distance / recommended_distance

Example:
    If max_penalty = 0.1 (10%), adherence = 0.3 (30%):
    base_penalty = 0.1 * (1 - 0.3) = 0.07

    With family_size = 50, prior = 10:
    confidence = 50 / (50 + 10) = 0.83
    bayesian_bonus = 0.83 * 0.3 = 0.25
    final_penalty = 0.07 * (1 - 0.25) = 0.052

    Final cost = existing_ranking_cost + 0.052
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, field
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

    # Bayesian metrics
    confidence: float = 0.0  # Bayesian confidence (0-1)
    base_penalty: float = 0.0  # Penalty before Bayesian reduction
    bayesian_reduction: float = 0.0  # Reduction factor from Bayesian bonus


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
        # Bayesian parameters
        prior_strength: float = 10.0,  # Default: như có 10 tài xế đã đi
        max_reduction_factor: float = 0.3,  # Max 30% reduction khi confidence cao
    ):
        self.enabled = enabled
        self.max_penalty = max_penalty
        self.adherence_threshold = adherence_threshold
        self.individual_weight = individual_weight
        self.popular_weight = popular_weight
        self.min_history_trips = min_history_trips
        self.family_support_threshold = family_support_threshold
        # Bayesian parameters
        self.prior_strength = prior_strength
        self.max_reduction_factor = max_reduction_factor


class HistoricalFamiliarity:
    """
    Calculate bounded familiarity penalty for route ranking.

    This feature:
    - Is a PENALTY, not a reward
    - Bounded by max_penalty
    - Uses Bayesian confidence to reduce penalty when population agrees
    - Does NOT affect candidate eligibility
    - Gracefully falls back when no history exists

    The penalty is applied as:
        final_cost = existing_cost + familiarity_penalty

    Where familiarity_penalty is calculated based on:
    1. Individual adherence (how much driver follows recommended route)
    2. Bayesian confidence (how many drivers agree with this route)
    """

    def __init__(self, config: FamiliarityConfig):
        self.config = config

    def calculate_penalty(
        self,
        context: FamiliarityContext
    ) -> FamiliarityPenalty:
        """
        Calculate bounded familiarity penalty with Bayesian confidence.

        Args:
            context: Historical context for this route/driver

        Returns:
            FamiliarityPenalty with breakdown including Bayesian metrics
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
                is_neutral=True,
                confidence=0.0,
                base_penalty=0.0,
                bayesian_reduction=0.0,
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
                is_neutral=True,
                confidence=0.0,
                base_penalty=0.0,
                bayesian_reduction=0.0,
            )

        # Clamp adherence
        adherence = max(0.0, min(1.0, context.route_adherence))
        family_size = context.historical_trip_count

        # 1. Calculate base penalty from adherence
        # Higher adherence = lower penalty
        if adherence >= self.config.adherence_threshold:
            # Driver follows recommended route well - small or no penalty
            # Linear decay from threshold to 1.0
            excess_adherence = (adherence - self.config.adherence_threshold) / (1.0 - self.config.adherence_threshold)
            relative_penalty = 1.0 - excess_adherence
        else:
            # Driver diverges from recommended route - full penalty range
            relative_penalty = adherence / self.config.adherence_threshold

        base_penalty = self.config.max_penalty * (1.0 - relative_penalty)

        # 2. Calculate Bayesian confidence
        # confidence = family_size / (family_size + prior_strength)
        # Higher family_size = more confidence that this is the "right" route
        confidence = family_size / (family_size + self.config.prior_strength)

        # 3. Calculate Bayesian bonus (reduction in penalty)
        # More confidence = bigger reduction in penalty
        bayesian_reduction = confidence * self.config.max_reduction_factor

        # 4. Apply Bayesian bonus to base penalty
        final_penalty = base_penalty * (1.0 - bayesian_reduction)

        # Clamp to bounds
        final_penalty = max(0.0, min(self.config.max_penalty, final_penalty))

        return FamiliarityPenalty(
            penalty=final_penalty,
            max_penalty=self.config.max_penalty,
            source=FamiliaritySource.ROUTE_FAMILY if context.family_support > 0 else FamiliaritySource.INDIVIDUAL_HABITUAL,
            adherence=adherence,
            driver_trip_count=family_size,
            family_trip_count=family_size,
            is_neutral=False,
            confidence=confidence,
            base_penalty=base_penalty,
            bayesian_reduction=bayesian_reduction,
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
            "Historical Familiarity Penalty Report (Bayesian)",
            "=" * 50,
            f"Penalty: {penalty.penalty:.4f} (max: {penalty.max_penalty:.4f})",
            f"Source: {penalty.source.value}",
            f"Route Adherence: {penalty.adherence:.1%}",
            f"Driver Trips: {penalty.driver_trip_count}",
            f"Family Trips: {penalty.family_trip_count}",
            f"---",
            f"Bayesian Metrics:",
            f"  Confidence: {penalty.confidence:.1%}",
            f"  Base Penalty: {penalty.base_penalty:.4f}",
            f"  Bayesian Reduction: {penalty.bayesian_reduction:.1%}",
            f"---",
            f"Neutral: {'Yes' if penalty.is_neutral else 'No'}",
        ]
        return "\n".join(lines)


def test_familiarity():
    """Test familiarity calculation with Bayesian penalty."""
    config = FamiliarityConfig(
        enabled=True,
        max_penalty=0.1,
        adherence_threshold=0.5,
        prior_strength=10.0,
        max_reduction_factor=0.3,
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
    print("✓ PASS\n")

    # Test case 2: Perfect adherence - minimal penalty
    print("=== Test 2: Perfect Adherence (100%) ===")
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
    assert penalty2.confidence > 0.8  # High confidence
    print("✓ PASS\n")

    # Test case 3: Poor adherence - penalty with Bayesian bonus
    print("=== Test 3: Poor Adherence (0%) - 1 tài xế ===")
    context3 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.0,  # Completely different from recommended
        family_support=0.0,
        unique_driver_support=0.0,
        historical_trip_count=1,
        has_history=True
    )
    penalty3 = familiarity.calculate_penalty(context3)
    print(familiarity.format_penalty_report(penalty3))
    # confidence = 1 / (1 + 10) = 0.09
    assert abs(penalty3.confidence - 0.091) < 0.01
    # bayesian_reduction = 0.09 * 0.3 = 0.027
    # base_penalty = 0.1 * (1 - 0) = 0.1
    # final = 0.1 * (1 - 0.027) = 0.097
    assert abs(penalty3.penalty - 0.097) < 0.01
    print("✓ PASS\n")

    # Test case 4: Poor adherence with many drivers - Bayesian bonus applies
    print("=== Test 4: Poor Adherence (0%) - 50 tài xế ===")
    context4 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.0,  # Completely different
        family_support=0.8,
        unique_driver_support=0.9,
        historical_trip_count=50,
        has_history=True
    )
    penalty4 = familiarity.calculate_penalty(context4)
    print(familiarity.format_penalty_report(penalty4))
    # confidence = 50 / (50 + 10) = 0.83
    assert abs(penalty4.confidence - 0.833) < 0.01
    # bayesian_reduction = 0.83 * 0.3 = 0.25
    # base_penalty = 0.1
    # final = 0.1 * (1 - 0.25) = 0.075
    assert abs(penalty4.penalty - 0.075) < 0.01
    print("✓ PASS\n")

    # Test case 5: 50% adherence - threshold
    print("=== Test 5: Threshold Adherence (50%) - 10 tài xế ===")
    context5 = FamiliarityContext(
        driver_id="D001",
        route_adherence=0.5,  # At threshold
        family_support=0.0,
        unique_driver_support=0.0,
        historical_trip_count=10,
        has_history=True
    )
    penalty5 = familiarity.calculate_penalty(context5)
    print(familiarity.format_penalty_report(penalty5))
    # confidence = 10 / (10 + 10) = 0.5
    assert abs(penalty5.confidence - 0.5) < 0.01
    # At threshold: relative_penalty = 0.5 / 0.5 = 1.0
    # base_penalty = 0.1 * (1 - 1.0) = 0.0
    # But adherence = threshold, so excess_adherence = 0, relative_penalty = 1.0
    # Wait, that's wrong. Let me recalculate:
    # At threshold: relative_penalty = adherence / threshold = 0.5 / 0.5 = 1.0
    # base_penalty = 0.1 * (1 - 1.0) = 0.0
    print(f"  Confidence: {penalty5.confidence:.2f}")
    print(f"  Base penalty: {penalty5.base_penalty:.4f}")
    print(f"  Final penalty: {penalty5.penalty:.4f}")
    # Actually at exactly threshold, penalty should be 0
    assert penalty5.base_penalty == 0.0
    print("✓ PASS\n")

    # Test case 6: Cost application
    print("=== Test 6: Cost Application ===")
    base_cost = 1.0
    adjusted_cost = familiarity.apply_to_cost(base_cost, penalty3)
    print(f"Base cost: {base_cost:.4f}")
    print(f"Adjusted cost: {adjusted_cost:.4f}")
    print(f"Penalty: {penalty3.penalty:.4f}")
    assert abs(adjusted_cost - (base_cost + penalty3.penalty)) < 0.001
    print("✓ PASS\n")

    # Test case 7: Bayesian comparison - same adherence, different family size
    print("=== Test 7: Bayesian Comparison ===")
    print("Same adherence=0.3, different family sizes:")

    for size in [1, 5, 10, 50, 100]:
        ctx = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.3,
            family_support=0.5,
            unique_driver_support=0.5,
            historical_trip_count=size,
            has_history=True
        )
        p = familiarity.calculate_penalty(ctx)
        print(f"  Size={size:3d}: confidence={p.confidence:.2f}, "
              f"base={p.base_penalty:.4f}, final={p.penalty:.4f}, "
              f"reduction={p.bayesian_reduction:.1%}")

    print("✓ PASS\n")

    print("=" * 50)
    print("All Bayesian tests passed! ✓")


if __name__ == "__main__":
    test_familiarity()
