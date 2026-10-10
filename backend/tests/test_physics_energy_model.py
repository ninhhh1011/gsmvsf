# backend/tests/test_physics_energy_model.py
"""Tests for verified vehicle powertrain specifications and dynamic longitudinal physics."""
import pytest
from backend.app.services.energy.powertrain_catalog import get_powertrain_spec, PowertrainSpec
from backend.app.services.energy.physics_model import (
    calculate_instantaneous_power,
    simulate_trip_energy,
    DynamicPowerResult,
)

def test_vf3_official_specs():
    spec = get_powertrain_spec("VF_3")
    assert spec.vehicle_model == "VF_3"
    assert spec.max_motor_power_kw == 30.0  # Official VinFast brochure: 30 kW
    assert spec.curb_weight_kg == 857.0
    assert spec.drag_coefficient == 0.36
    assert spec.spec_source == "VINFAST_OFFICIAL_BROCHURE_2024"
    assert spec.parameters_status == "OFFICIAL_VERIFIED"

def test_instantaneous_power_stopped_traffic():
    spec = get_powertrain_spec("VF_3")
    # Vehicle stationary at 0 km/h with AC running (HVAC)
    res = calculate_instantaneous_power(
        spec=spec,
        speed_kmh=0.0,
        acceleration_ms2=0.0,
        grade_rad=0.0,
        hvac_on=True,
    )
    assert res.total_power_kw == pytest.approx(1.5, abs=0.2)  # Base auxiliary HVAC load
    assert res.traction_power_kw == 0.0
    assert res.total_power_kw < spec.max_motor_power_kw
    assert res.is_regenerating is False

def test_instantaneous_power_highway_vs_city():
    spec = get_powertrain_spec("VF_3")
    # 80 km/h highway power must be significantly higher than 35 km/h city power due to aero drag (v^3)
    power_city = calculate_instantaneous_power(spec, speed_kmh=35.0, acceleration_ms2=0.0)
    power_hwy = calculate_instantaneous_power(spec, speed_kmh=80.0, acceleration_ms2=0.0)
    assert power_hwy.aero_power_kw > power_city.aero_power_kw * 8.0  # (80/35)^3 ~= 11.9
    assert power_hwy.total_power_kw <= spec.max_motor_power_kw

def test_regenerative_braking():
    spec = get_powertrain_spec("VF_3")
    # Decelerating (-1.5 m/s^2) from 50 km/h
    res = calculate_instantaneous_power(spec, speed_kmh=50.0, acceleration_ms2=-1.5)
    assert res.traction_power_kw < 0.0  # Power flowing back into battery
    assert res.is_regenerating is True

def test_simulate_trip_energy():
    spec = get_powertrain_spec("VF_3")
    # 60 seconds at constant 40 km/h
    speed_profile = [40.0] * 60
    summary = simulate_trip_energy(spec, speed_profile, dt_seconds=1.0)
    assert summary["total_energy_kwh"] > 0
    assert summary["total_distance_km"] == pytest.approx(40.0 * (60.0 / 3600.0), rel=1e-2)
    assert 50.0 < summary["avg_consumption_wh_km"] < 200.0
