"""
Physics-based vehicle energy depletion model following longitudinal dynamics.

Forces acting on vehicle:
1. Aerodynamic drag: F_aero = 0.5 * rho * C_d * A * v^2
2. Rolling resistance: F_roll = C_rr * m * g * cos(theta)
3. Acceleration inertia: F_accel = m * a
4. Grade resistance: F_climb = m * g * sin(theta)

Total Power:
P_total = P_traction + P_aux
where:
- Traction: P_traction = (F_aero + F_roll + F_accel + F_climb) * v / eta_drive  (if >= 0)
- Regenerative braking: P_traction = P_mech * eta_regen  (if < 0, capped by motor regen limit)
- Auxiliary: P_aux represents HVAC, infotainment, lighting, and low-voltage electronics.
"""
import math
from dataclasses import dataclass

from backend.app.services.energy.powertrain_catalog import PowertrainSpec

_AIR_DENSITY_KG_M3 = 1.204  # standard air density at 20 deg C, sea level
_GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class DynamicPowerResult:
    speed_kmh: float
    total_power_kw: float
    traction_power_kw: float
    aero_power_kw: float
    rolling_power_kw: float
    accel_power_kw: float
    grade_power_kw: float
    auxiliary_power_kw: float
    is_regenerating: bool
    power_status: str


def calculate_instantaneous_power(
    spec: PowertrainSpec,
    speed_kmh: float,
    acceleration_ms2: float = 0.0,
    grade_rad: float = 0.0,
    passenger_weight_kg: float = 75.0,
    hvac_on: bool = True,
) -> DynamicPowerResult:
    """Calculate instantaneous battery power draw (kW) from vehicle kinematics."""
    if not all(math.isfinite(value) for value in (speed_kmh, acceleration_ms2, grade_rad, passenger_weight_kg)):
        raise ValueError("Kinematics must be finite")
    if speed_kmh < 0 or passenger_weight_kg < 0:
        raise ValueError("Speed and passenger weight must be nonnegative")
    v_ms = speed_kmh / 3.6
    total_mass_kg = spec.curb_weight_kg + passenger_weight_kg

    # 1. Aerodynamic drag force: F_aero = 0.5 * rho * C_d * A * v^2
    f_aero = 0.5 * _AIR_DENSITY_KG_M3 * spec.drag_coefficient * spec.frontal_area_m2 * (v_ms ** 2)
    p_aero_kw = (f_aero * v_ms) / 1000.0

    # 2. Rolling resistance: F_roll = C_rr * m * g * cos(theta)
    f_roll = spec.rolling_resistance_coeff * total_mass_kg * _GRAVITY_M_S2 * math.cos(grade_rad)
    p_roll_kw = (f_roll * v_ms) / 1000.0

    # 3. Acceleration inertia: F_accel = m * a
    f_accel = total_mass_kg * acceleration_ms2
    p_accel_kw = (f_accel * v_ms) / 1000.0

    # 4. Grade resistance: F_grade = m * g * sin(theta)
    f_grade = total_mass_kg * _GRAVITY_M_S2 * math.sin(grade_rad)
    p_grade_kw = (f_grade * v_ms) / 1000.0

    # Net mechanical power at wheels
    p_mech_wheel_kw = p_aero_kw + p_roll_kw + p_accel_kw + p_grade_kw

    # 5. Transmission & Motor conversion
    if p_mech_wheel_kw >= 0:
        p_traction_kw = p_mech_wheel_kw / max(0.01, spec.drive_efficiency)
        is_regen = False
    else:
        # Regenerative braking
        p_traction_kw = p_mech_wheel_kw * spec.regen_efficiency
        # Limit max regen power (typically 40-50% of motor capacity)
        max_regen_kw = spec.max_motor_power_kw * 0.5
        p_traction_kw = max(-max_regen_kw, p_traction_kw)
        is_regen = True

    # 6. Auxiliary power (HVAC, lights, electronics)
    p_aux_kw = spec.auxiliary_base_kw if hvac_on else (spec.auxiliary_base_kw * 0.3)

    p_total_kw = p_traction_kw + p_aux_kw
    if not all(math.isfinite(value) for value in (p_total_kw, p_aero_kw, p_roll_kw, p_accel_kw, p_grade_kw)):
        raise ValueError("Kinematics exceed numeric model bounds")

    return DynamicPowerResult(
        speed_kmh=speed_kmh,
        total_power_kw=round(p_total_kw, 3),
        traction_power_kw=round(p_traction_kw, 3),
        aero_power_kw=round(p_aero_kw, 3),
        rolling_power_kw=round(p_roll_kw, 3),
        accel_power_kw=round(p_accel_kw, 3),
        grade_power_kw=round(p_grade_kw, 3),
        auxiliary_power_kw=round(p_aux_kw, 3),
        is_regenerating=is_regen,
        power_status="KINEMATICS_EXCEED_CAPABILITY" if p_mech_wheel_kw > spec.max_motor_power_kw else "MODEL_ESTIMATE",
    )


def calculate_power_step(
    spec: PowertrainSpec,
    speed_kmh: float,
    previous_speed_kmh: float | None,
    dt_seconds: float,
    hvac_on: bool = True,
) -> tuple[DynamicPowerResult, float]:
    """End-point power and midpoint energy for an observed linear speed change."""
    if not math.isfinite(dt_seconds) or not 0 <= dt_seconds <= 3600:
        raise ValueError("Interval must be finite and between 0 and 3600 seconds")
    previous_speed = speed_kmh if previous_speed_kmh is None else previous_speed_kmh
    if not math.isfinite(previous_speed) or previous_speed < 0:
        raise ValueError("Previous speed must be finite and nonnegative")
    acceleration = (speed_kmh - previous_speed) / 3.6 / dt_seconds if dt_seconds else 0.0
    power = calculate_instantaneous_power(spec, speed_kmh, acceleration, hvac_on=hvac_on)
    interval_power = calculate_instantaneous_power(
        spec, (speed_kmh + previous_speed) / 2, acceleration, hvac_on=hvac_on
    )
    return power, interval_power.total_power_kw * dt_seconds / 3600


def simulate_trip_energy(
    spec: PowertrainSpec,
    speed_profile_kmh: list[float],
    dt_seconds: float = 1.0,
    hvac_on: bool = True,
) -> dict:
    """Simulate complete driving profile and calculate energy consumption."""
    total_energy_kwh = 0.0
    power_samples = []
    for i in range(len(speed_profile_kmh)):
        v_curr = speed_profile_kmh[i]
        res, energy_step_kwh = calculate_power_step(
            spec, v_curr, speed_profile_kmh[i - 1] if i else None, dt_seconds, hvac_on
        )
        power_samples.append(res)
        total_energy_kwh += energy_step_kwh

    total_dist_km = sum(v * (dt_seconds / 3600.0) for v in speed_profile_kmh)
    avg_consumption_wh_km = (total_energy_kwh * 1000.0 / total_dist_km) if total_dist_km > 0 else 0.0

    return {
        "total_energy_kwh": round(total_energy_kwh, 4),
        "total_distance_km": round(total_dist_km, 3),
        "avg_consumption_wh_km": round(avg_consumption_wh_km, 2),
        "sample_count": len(power_samples),
    }
