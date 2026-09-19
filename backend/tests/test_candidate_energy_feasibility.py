"""
Tests for Candidate Energy Feasibility to Station.
"""

import pytest

from backend.app.services.candidate.energy_feasibility import (
    SOC_REACH_BUFFER_KM,
    check_energy_feasibility_to_station,
)


def test_reachable_candidate_with_ample_range():
    # Distance = 10,000m (10km), Range = 20km -> 10 + 0.5 <= 20 -> True
    assert check_energy_feasibility_to_station(10000.0, 20.0) is True


def test_insufficient_range_candidate():
    # Distance = 15,000m (15km), Range = 15.2km -> 15 + 0.5 = 15.5 > 15.2 -> False
    assert check_energy_feasibility_to_station(15000.0, 15.2) is False


def test_exact_buffer_boundary():
    # Distance = 10,000m (10km), Buffer = 0.5km
    # Exactly 10.5km range -> True
    assert check_energy_feasibility_to_station(10000.0, 10.5) is True
    # 10.49km range -> False
    assert check_energy_feasibility_to_station(10000.0, 10.49) is False


def test_anomalies_and_edge_cases():
    # None network distance
    assert check_energy_feasibility_to_station(None, 20.0) is False
    # Infinite network distance
    assert check_energy_feasibility_to_station(float("inf"), 20.0) is False
    # None range
    assert check_energy_feasibility_to_station(5000.0, None) is False
    # Zero range
    assert check_energy_feasibility_to_station(5000.0, 0.0) is False
    # Negative range
    assert check_energy_feasibility_to_station(5000.0, -5.0) is False
