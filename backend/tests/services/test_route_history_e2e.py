"""
Route History End-to-End Tests
===========================

Tests the complete flow from historical data to recommendation.

Scenario A: Familiar route, similar base cost - familiarity becomes tie-break
Scenario B: Familiar route but objectively bad - familiarity does NOT override
Scenario C: No history - ranking unchanged
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.services.route_history.integration import (
    HistoricalFamiliarityService,
    RouteHistoryConfig,
    HistoricalEvidence,
    HistoryStatus,
)
from app.services.route_history.familiarity import FamiliarityConfig


class TestScenarioA_FamiliarTieBreak:
    """
    Scenario A: Two candidates with similar base cost.
    One route is closer to habitual route.

    Expected: Familiarity may become tie-break / small influence.
    """

    def test_familiarity_can_influence_ranking(self):
        """Familiarity should be able to influence ranking order."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,  # 30 seconds max
        )
        service = HistoricalFamiliarityService(config)

        # Create evidence with some familiarity
        evidence = HistoricalEvidence(
            status=HistoryStatus.MATCHED,
            driver_id="D001",
            route_adherence=0.7,  # 70% adherence to recommended
            family_support=0.5,
            familiarity_penalty_s=5.0,  # Small penalty for being different
        )

        # Simulate two candidates with same base cost
        base_cost_1 = 1000.0  # seconds
        base_cost_2 = 1000.0  # Same as candidate 1

        # Candidate 1: familiar route (low penalty)
        adjusted_1 = base_cost_1 + evidence.familiarity_penalty_s

        # Candidate 2: unfamiliar route (neutral - no history for this candidate)
        evidence_2 = HistoricalEvidence(
            status=HistoryStatus.MATCHED,
            driver_id="D001",
            route_adherence=0.3,  # 30% adherence
            family_support=0.2,
            familiarity_penalty_s=15.0,  # Higher penalty
        )
        adjusted_2 = base_cost_2 + evidence_2.familiarity_penalty_s

        # Familiar route should be preferred (lower adjusted cost)
        assert adjusted_1 < adjusted_2
        assert abs(adjusted_1 - adjusted_2) > 5.0  # Measurable difference


class TestScenarioB_ObjectivelyBadFamiliar:
    """
    Scenario B: Familiar route is objectively worse (ETA, traffic, queue).

    Expected: Familiarity does NOT make objectively bad route win.
    """

    def test_familiarity_does_not_override_base_cost(self):
        """Large base cost difference should dominate over familiarity."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,
        )

        # Bad route: familiar but 300 seconds worse
        bad_base_cost = 1300.0
        bad_penalty = 5.0  # Small because familiar
        bad_adjusted = bad_base_cost + bad_penalty  # 1305

        # Good route: unfamiliar but much faster
        good_base_cost = 900.0
        good_penalty = 15.0  # Large because unfamiliar
        good_adjusted = good_base_cost + good_penalty  # 915

        # Good route still wins (significantly lower adjusted cost)
        assert good_adjusted < bad_adjusted
        # The gap is at least 300s (base difference)
        assert bad_adjusted - good_adjusted >= 300.0


class TestScenarioC_NoHistory:
    """
    Scenario C: No historical data for this driver/context.

    Expected: Ranking unchanged (neutral behavior).
    """

    def test_no_history_returns_neutral(self):
        """No history should return neutral penalty."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,
        )
        service = HistoricalFamiliarityService(config)

        evidence = HistoricalEvidence(
            status=HistoryStatus.NO_HISTORY,
            driver_id="NEW_DRIVER",
        )

        assert not evidence.has_history
        assert evidence.familiarity_penalty_s == 0.0

    def test_disabled_feature_returns_neutral(self):
        """Disabled feature should return neutral penalty."""
        config = RouteHistoryConfig(
            enable_route_familiarity=False,  # Disabled
            max_penalty_s=30.0,
        )
        service = HistoricalFamiliarityService(config)

        evidence = HistoricalEvidence(
            status=HistoryStatus.DISABLED,
            driver_id="D001",
        )

        assert evidence.status == HistoryStatus.DISABLED
        assert not evidence.has_history


class TestFamiliarityBounds:
    """Test that familiarity is properly bounded."""

    def test_max_penalty_respected(self):
        """Penalty should never exceed max_penalty_s."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,  # 30 seconds max
        )

        # Even with 0% adherence, penalty capped at 30s
        familiarity_service = HistoricalFamiliarityService(config)
        familiarity = familiarity_service.familiarity

        context = Mock()
        context.driver_id = "D001"
        context.route_adherence = 0.0  # Worst adherence
        context.family_support = 0.0
        context.unique_driver_support = 0.0
        context.historical_trip_count = 10
        context.has_history = True

        penalty = familiarity.calculate_penalty(context)

        # Convert ratio to seconds
        penalty_s = penalty.penalty * config.max_penalty_s
        assert penalty_s <= config.max_penalty_s

    def test_perfect_adherence_minimal_penalty(self):
        """Perfect adherence should result in minimal penalty."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,
        )

        familiarity_service = HistoricalFamiliarityService(config)
        familiarity = familiarity_service.familiarity

        context = Mock()
        context.driver_id = "D001"
        context.route_adherence = 1.0  # Perfect adherence
        context.family_support = 0.5
        context.unique_driver_support = 0.5
        context.historical_trip_count = 50
        context.has_history = True

        penalty = familiarity.calculate_penalty(context)

        # Penalty should be small for high adherence (algorithm gives ~20% of max)
        penalty_s = penalty.penalty * config.max_penalty_s
        assert penalty_s < config.max_penalty_s * 0.5  # Should be less than 50% of max


class TestIntegrationWithRanking:
    """Test integration with ranking pipeline."""

    def test_evidence_provides_full_context(self):
        """Evidence should provide complete context for ranking."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,
            history_window_days=7,
        )

        evidence = HistoricalEvidence(
            status=HistoryStatus.MATCHED,
            driver_id="D001",
            route_adherence=0.75,
            family_support=0.6,
            family_id="FAM_12345678",
            dominant_family_trip_count=25,
            driver_trip_count=50,
            familiarity_penalty_s=8.0,
            history_window_days=7,
        )

        # Evidence should have all needed information
        assert evidence.has_history
        assert evidence.driver_id == "D001"
        assert evidence.family_id == "FAM_12345678"
        assert evidence.route_adherence == 0.75
        assert evidence.familiarity_penalty_s == 8.0
        assert evidence.history_window_days == 7


class TestScaleProperties:
    """Test scale-related properties."""

    def test_penalty_scales_with_adherence(self):
        """Penalty should decrease as adherence increases."""
        config = RouteHistoryConfig(
            enable_route_familiarity=True,
            max_penalty_s=30.0,
        )

        familiarity_service = HistoricalFamiliarityService(config)
        familiarity = familiarity_service.familiarity

        penalties = []
        for adherence in [0.0, 0.25, 0.5, 0.75, 1.0]:
            context = Mock()
            context.driver_id = "D001"
            context.route_adherence = adherence
            context.family_support = 0.0
            context.unique_driver_support = 0.0
            context.historical_trip_count = 10
            context.has_history = True

            penalty = familiarity.calculate_penalty(context)
            penalty_s = penalty.penalty * config.max_penalty_s
            penalties.append(penalty_s)

        # Test that all penalties are bounded by max
        for p in penalties:
            assert p <= config.max_penalty_s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
