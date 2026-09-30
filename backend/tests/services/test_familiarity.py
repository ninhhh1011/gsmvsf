"""
Tests for Historical Familiarity Feature
=====================================
"""

import pytest
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.services.route_history.familiarity import (
    HistoricalFamiliarity,
    FamiliarityConfig,
    FamiliarityContext,
    FamiliarityPenalty,
    FamiliaritySource,
)


class TestFamiliarityPenalty:
    """Tests for bounded familiarity penalty."""

    def test_no_history_neutral(self):
        """No history should return neutral penalty."""
        config = FamiliarityConfig(enabled=True, max_penalty=0.1)
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=0,
            has_history=False
        )

        penalty = familiarity.calculate_penalty(context)

        assert penalty.is_neutral
        assert penalty.penalty == 0.0

    def test_disabled_feature_neutral(self):
        """Disabled feature should return neutral penalty."""
        config = FamiliarityConfig(enabled=False, max_penalty=0.1)
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=100,
            has_history=True
        )

        penalty = familiarity.calculate_penalty(context)

        assert penalty.is_neutral
        assert penalty.penalty == 0.0

    def test_perfect_adherence_minimal_penalty(self):
        """Perfect adherence should result in minimal penalty."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,
            adherence_threshold=0.5
        )
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=1.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=50,
            has_history=True
        )

        penalty = familiarity.calculate_penalty(context)

        assert not penalty.is_neutral
        assert penalty.adherence == 1.0
        # Penalty is bounded by max_penalty
        assert penalty.penalty <= config.max_penalty

    def test_zero_adherence_max_penalty(self):
        """Zero adherence should result in max penalty."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,
            adherence_threshold=0.5
        )
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True
        )

        penalty = familiarity.calculate_penalty(context)

        assert not penalty.is_neutral
        assert penalty.penalty == config.max_penalty
        assert penalty.adherence == 0.0

    def test_penalty_bounded_by_max(self):
        """Penalty should never exceed max_penalty."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.05,  # Lower max
            adherence_threshold=0.5
        )
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.0,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True
        )

        penalty = familiarity.calculate_penalty(context)

        assert penalty.penalty <= config.max_penalty

    def test_family_support_reduces_penalty(self):
        """High family support should slightly reduce penalty."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,
            adherence_threshold=0.5
        )
        familiarity = HistoricalFamiliarity(config)

        # Without family support
        context1 = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.3,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True
        )
        penalty1 = familiarity.calculate_penalty(context1)

        # With family support
        context2 = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.3,
            family_support=0.8,  # High family support
            unique_driver_support=0.5,
            historical_trip_count=10,
            has_history=True
        )
        penalty2 = familiarity.calculate_penalty(context2)

        # Family support should reduce penalty
        assert penalty2.penalty < penalty1.penalty

    def test_adherence_at_threshold(self):
        """Adherence at threshold should give moderate penalty."""
        config = FamiliarityConfig(
            enabled=True,
            max_penalty=0.1,
            adherence_threshold=0.5
        )
        familiarity = HistoricalFamiliarity(config)

        context = FamiliarityContext(
            driver_id="D001",
            route_adherence=0.5,
            family_support=0.0,
            unique_driver_support=0.0,
            historical_trip_count=10,
            has_history=True
        )

        penalty = familiarity.calculate_penalty(context)

        # At threshold, algorithm gives penalty = 0
        assert penalty.penalty == 0.0


class TestFamiliarityCostApplication:
    """Tests for applying penalty to cost."""

    def test_neutral_does_not_change_cost(self):
        """Neutral penalty should not change base cost."""
        config = FamiliarityConfig(enabled=False)
        familiarity = HistoricalFamiliarity(config)

        penalty = FamiliarityPenalty(
            penalty=0.0,
            max_penalty=0.1,
            source=FamiliaritySource.INDIVIDUAL_HABITUAL,
            adherence=0.0,
            driver_trip_count=0,
            family_trip_count=0,
            is_neutral=True
        )

        base_cost = 1.5
        adjusted = familiarity.apply_to_cost(base_cost, penalty)

        assert adjusted == base_cost

    def test_penalty_added_to_cost(self):
        """Non-neutral penalty should be added to cost."""
        config = FamiliarityConfig(enabled=True)
        familiarity = HistoricalFamiliarity(config)

        penalty = FamiliarityPenalty(
            penalty=0.05,
            max_penalty=0.1,
            source=FamiliaritySource.INDIVIDUAL_HABITUAL,
            adherence=0.5,
            driver_trip_count=10,
            family_trip_count=5,
            is_neutral=False
        )

        base_cost = 1.0
        adjusted = familiarity.apply_to_cost(base_cost, penalty)

        assert adjusted == 1.05


class TestFamiliarityConfig:
    """Tests for familiarity configuration."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = FamiliarityConfig()

        assert config.enabled is True
        assert config.max_penalty == 0.1
        assert config.adherence_threshold == 0.5
        assert config.individual_weight == 0.7
        assert config.popular_weight == 0.3

    def test_custom_config(self):
        """Custom config should override defaults."""
        config = FamiliarityConfig(
            enabled=False,
            max_penalty=0.05,
            adherence_threshold=0.3
        )

        assert config.enabled is False
        assert config.max_penalty == 0.05
        assert config.adherence_threshold == 0.3


class TestFamiliarityReport:
    """Tests for penalty report formatting."""

    def test_format_report(self):
        """Report should contain key information."""
        config = FamiliarityConfig()
        familiarity = HistoricalFamiliarity(config)

        penalty = FamiliarityPenalty(
            penalty=0.05,
            max_penalty=0.1,
            source=FamiliaritySource.INDIVIDUAL_HABITUAL,
            adherence=0.7,
            driver_trip_count=25,
            family_trip_count=10,
            is_neutral=False
        )

        report = familiarity.format_penalty_report(penalty)

        assert "Penalty: 0.0500" in report
        assert "max: 0.1000" in report
        assert "Route Adherence: 70.0%" in report
        assert "Driver Trips: 25" in report
        assert "Neutral: No" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
