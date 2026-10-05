"""
Test Bayesian Penalty for Route Familiarity
=========================================

Verifies that the Bayesian confidence calculation correctly reduces
penalty when many drivers agree on a route.
"""

import pytest
from backend.app.services.route_history.familiarity import (
    HistoricalFamiliarity,
    FamiliarityConfig,
    FamiliarityContext,
    FamiliaritySource,
)


class TestBayesianPenalty:
    """Test cases for Bayesian penalty calculation."""

    @pytest.fixture
    def config(self):
        """Default Bayesian config."""
        return FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,  # 10%
            adherence_threshold=0.5,
            prior_strength=10.0,
            max_reduction_factor=0.3,
        )

    @pytest.fixture
    def familiarity(self, config):
        """HistoricalFamiliarity instance."""
        return HistoricalFamiliarity(config)

    def test_no_history_returns_neutral(self, familiarity):
        """No history should return neutral penalty."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=0,
            has_history=False,
        )
        penalty = familiarity.calculate_penalty(context)

        assert penalty.is_neutral
        assert penalty.penalty == 0.0
        assert penalty.confidence == 0.0

    def test_perfect_adherence_no_penalty(self, familiarity):
        """100% adherence should have minimal penalty."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=1.0,
            family_support=0.5,
            unique_driver_support=0.8,
            historical_trip_count=50,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        assert penalty.adherence == 1.0
        assert penalty.base_penalty == 0.0
        assert penalty.penalty == 0.0

    def test_poor_adherence_single_driver(self, familiarity, config):
        """1 driver with 0% adherence: high penalty, low confidence."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=1,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        # confidence = 1 / (1 + 10) = 0.091
        assert abs(penalty.confidence - 0.091) < 0.01
        # base_penalty = 0.1
        assert penalty.base_penalty == 0.1
        # bayesian_reduction = 0.091 * 0.3 = 0.027
        assert abs(penalty.bayesian_reduction - 0.027) < 0.01
        # final = 0.1 * (1 - 0.027) = 0.097
        assert abs(penalty.penalty - 0.097) < 0.01

    def test_poor_adherence_many_drivers(self, familiarity, config):
        """50 drivers with 0% adherence: high penalty but reduced by Bayesian."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.8,
            unique_driver_support=0.9,
            historical_trip_count=50,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        # confidence = 50 / (50 + 10) = 0.833
        assert abs(penalty.confidence - 0.833) < 0.01
        # bayesian_reduction = 0.833 * 0.3 = 0.25
        assert abs(penalty.bayesian_reduction - 0.25) < 0.01
        # final = 0.1 * (1 - 0.25) = 0.075
        assert abs(penalty.penalty - 0.075) < 0.01

    def test_same_adherence_different_family_size(self, familiarity, config):
        """Same adherence, different family sizes give different penalties."""
        adherence = 0.3  # 30% - poor adherence
        results = []

        for size in [1, 5, 10, 50, 100]:
            context = FamiliarityContext(
                driver_id="D001",
                route_adherence=adherence,
                family_support=0.5,
                unique_driver_support=0.5,
                historical_trip_count=size,
                has_history=True,
            )
            penalty = familiarity.calculate_penalty(context)
            results.append((size, penalty.confidence, penalty.penalty))

        # Verify penalty decreases as family size increases
        for i in range(1, len(results)):
            prev_size, prev_conf, prev_penalty = results[i - 1]
            curr_size, curr_conf, curr_penalty = results[i]

            # Confidence should increase
            assert curr_conf > prev_conf, f"Confidence should increase: {prev_conf} -> {curr_conf}"
            # Penalty should decrease (or stay same)
            assert curr_penalty <= prev_penalty, f"Penalty should decrease: {prev_penalty} -> {curr_penalty}"

        # Verify specific values
        # Size=1: confidence=0.091, penalty≈0.097
        assert abs(results[0][1] - 0.091) < 0.01
        assert abs(results[0][2] - 0.097) < 0.01

        # Size=50: confidence=0.833, penalty=0.075
        assert abs(results[3][1] - 0.833) < 0.01
        assert abs(results[3][2] - 0.075) < 0.01

    def test_bayesian_bonus_capped_at_max(self, familiarity, config):
        """Bayesian bonus should not exceed max_reduction_factor."""
        # Very large family size
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=1.0,
            unique_driver_support=1.0,
            historical_trip_count=10000,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        # confidence approaches 1.0 but never equals 1.0
        assert penalty.confidence < 1.0
        # bayesian_reduction capped at max_reduction_factor
        assert penalty.bayesian_reduction <= config.max_reduction_factor

    def test_threshold_adherence(self, familiarity, config):
        """At exactly 50% adherence, penalty should be 0."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.5,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        # At threshold: relative_penalty = 1.0
        # base_penalty = 0.1 * (1 - 1.0) = 0.0
        assert penalty.base_penalty == 0.0
        assert penalty.penalty == 0.0

    def test_penalty_never_negative(self, familiarity):
        """Penalty should never go below 0."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=1.0,  # Perfect adherence
            family_support=1.0,
            unique_driver_support=1.0,
            historical_trip_count=100,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        assert penalty.penalty >= 0.0

    def test_penalty_never_exceeds_max(self, familiarity, config):
        """Penalty should never exceed max_penalty."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,  # Worst adherence
            family_support=0.0,  # No family bonus
            unique_driver_support=0.0,
            historical_trip_count=1,  # Minimum confidence
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        assert penalty.penalty <= config.max_penalty

    def test_source_reflects_context(self, familiarity):
        """Source should reflect whether family support exists."""
        # With family support
        context1 = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.3,
            family_support=0.5,
            unique_driver_support=0.5,
            historical_trip_count=10,
            has_history=True,
        )
        penalty1 = familiarity.calculate_penalty(context1)
        assert penalty1.source == FamiliaritySource.ROUTE_FAMILY

        # Without family support
        context2 = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.3,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True,
        )
        penalty2 = familiarity.calculate_penalty(context2)
        assert penalty2.source == FamiliaritySource.INDIVIDUAL_HABITUAL

    def test_apply_to_cost(self, familiarity):
        """Test applying penalty to base cost."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True,
        )
        penalty = familiarity.calculate_penalty(context)

        base_cost = 1.0
        adjusted = familiarity.apply_to_cost(base_cost, penalty)

        assert abs(adjusted - (base_cost + penalty.penalty)) < 0.001

    def test_apply_to_cost_neutral(self, familiarity):
        """Neutral penalty should not change cost."""
        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=0,
            has_history=False,
        )
        penalty = familiarity.calculate_penalty(context)

        base_cost = 1.0
        adjusted = familiarity.apply_to_cost(base_cost, penalty)

        assert adjusted == base_cost


class TestBayesianComparison:
    """Visual comparison of Bayesian vs non-Bayesian penalty."""

    def test_bayesian_reduces_penalty(self):
        """Bayesian approach should reduce penalty for popular routes."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,
            adherence_threshold=0.5,
            prior_strength=10.0,
            max_reduction_factor=0.3,
        )
        familiarity = HistoricalFamiliarity(config)

        adherence = 0.3
        base_penalty = 0.1 * (1 - adherence)  # = 0.07

        print("\n=== Bayesian Penalty Comparison ===")
        print(f"Base penalty (non-Bayesian): {base_penalty:.4f}")
        print(f"Adherence: {adherence:.1%}")
        print()

        for size in [1, 5, 10, 50, 100]:
            context = FamiliarityContext(
                driver_id="D001",
                route_adherence=adherence,
                family_support=0.5,
                unique_driver_support=0.5,
                historical_trip_count=size,
                has_history=True,
            )
            penalty = familiarity.calculate_penalty(context)

            reduction = (base_penalty - penalty.penalty) / base_penalty * 100

            print(f"Family size={size:3d}: "
                  f"confidence={penalty.confidence:.1%}, "
                  f"penalty={penalty.penalty:.4f}, "
                  f"reduction={reduction:.0f}%")

        # Verify that larger families have more reduction
        results = []
        for size in [1, 5, 10, 50, 100]:
            context = FamiliarityContext(
                driver_id="D001",
                route_adherence=adherence,
                family_support=0.5,
                unique_driver_support=0.5,
                historical_trip_count=size,
                has_history=True,
            )
            penalty = familiarity.calculate_penalty(context)
            results.append((size, penalty.penalty))

        for i in range(1, len(results)):
            assert results[i][1] < results[i - 1][1], \
                f"Penalty should decrease: {results[i - 1]} vs {results[i]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
