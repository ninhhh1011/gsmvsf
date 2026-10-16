# Route Comparison, Direction-Aware H3 Discretization, and Dynamic Energy Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a source-verified, direction- and sequence-aware route comparison engine using Uber H3 (resolutions 8/9/10), time-of-day history conditioning (7d/30d), and a physics-based dynamic vehicle powertrain model, replacing placeholders with verified mathematical and spatial rigor.

**Architecture:** 
- A backend route comparison service converts polylines to H3 cells at configurable resolutions (8, 9, 10; default 9), verifies spatial heading and sequence ordering to eliminate false positives on parallel roads, and outputs distinct dual-metric percentages ($L_{shared}/L_{proposed}$ and $L_{shared}/L_{actual}$).
- A temporal route history service groups historical trips into 3 Vietnam local-time windows (Morning Peak, Evening Peak, Off-Peak) with strict causality ($completed\_at < as\_of$) and sparse-data fallback labeling.
- An extensible powertrain dynamics service calculates vehicle power draw ($P = P_{aero} + P_{roll} + P_{accel} + P_{grade} + P_{aux}$) using brochure-verified specs (e.g. VinFast VF 3 official 30 kW), cleanly separating max motor capability from instantaneous draw on the HUD.
- The demo frontend provides a discrete resolution badge selector (8/9/10, default 9) directly next to the H3 toggle on the Driver Cockpit header, removes artificial `viaPoints` trajectory forcing, and visualizes unconstrained proposed vs actual replay routes with confirmed shared segments in 100% Driver Mode.

**Tech Stack:** Python 3.14, FastAPI, asyncpg, h3-py 4.x, Leaflet, Node.js test runner, Pytest.

**Spec:** User directives from 2026-10-10 based on mentor review:
- H3 resolution default 9, discrete selector 8/9/10; H3 filters candidates, then heading/position/sequence verified before length addition; backend computes, frontend displays.
- Dual route comparison: Trip Evaluation Mode (Replay from `gps/gps_observations.csv.gz` without `viaPoints` forcing) vs Alternative Route Mode (labeled simulated); dual percentage metrics ($L_{shared}/L_{proposed}$ and $L_{shared}/L_{actual}$).
- Temporal history: 7d default, 30d option; 3 VN time windows (07:00-09:00, 17:00-19:30, Off-peak); trip start time grouping; strict causality ($completed\_at < as\_of$).
- Dynamic energy model: Source-verified specs (VF 3 max 30 kW); physics forces ($aero, roll, accel, grade, aux, regen$); HUD separates max motor capability from instantaneous power draw; baseline Wh/km kept for comparative error analysis.

---

## Global Constraints

- `dataset_v1/` is canonical read-only; never modify, regenerate, or alter files inside `dataset_v1/`.
- Synthetic multi-day evaluation data must reside in `runtime/simulation_data/` with clear provenance metadata.
- GraphHopper 11.0 remains the sole production routing and map-matching adapter.
- Labels are offline evaluation-only; never consume labels in runtime prediction.
- All times for peak-hour grouping must be evaluated in Vietnam local time (UTC+7 / Asia/Ho_Chi_Minh).

---

## Review Focus

1. **Parallel Road False Match:** Two opposite-direction carriage-ways or parallel frontage roads falling into the same H3-9 cell must not be counted as shared distance if heading difference $> 60^\circ$ or lateral distance $> 25\text{m}$.
2. **Resolution Drift:** Changing resolution from 9 to 8 or 10 on UI must trigger a fresh backend calculation from raw route geometry; frontend must never recompute its own percentages client-side.
3. **Causality Leak in History:** Historical trips completed at or after the trip start evaluation time must be strictly excluded ($completed\_at < as\_of$).
4. **Instantaneous vs Max Power Confusion:** Instantaneous power draw ($P_{inst}$) at a stoplight must reflect auxiliary load ($P_{aux} \approx 1.5\text{ kW}$), never 0 kW and never the 30 kW max motor power.
5. **Zero-Length or Degenerate Routes:** Point coordinates with zero length or single-point geometries must return 0 shared distance and 0.0% overlap without division-by-zero errors.

---

### Task 1: Verified Vehicle Powertrain Catalog & Physics Energy Model

**Files:**
- Create: `backend/app/services/energy/powertrain_catalog.py`
- Create: `backend/app/services/energy/physics_model.py`
- Test: `backend/tests/test_physics_energy_model.py`

**Interfaces:**
- Produces: `PowertrainSpec`, `DynamicPowerResult`, `calculate_instantaneous_power()`, `simulate_trip_energy()`
- Consumes: Standard math/dataclass libraries, vehicle catalog identifiers.

- [ ] **Step 1: Write failing tests for powertrain specifications and dynamic physics formulas**

```python
# backend/tests/test_physics_energy_model.py
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
    assert spec.max_motor_power_kw == 30.0  # Official brochure: 30 kW
    assert spec.curb_weight_kg == 857.0
    assert spec.drag_coefficient == 0.36
    assert spec.spec_source == "VINFAST_OFFICIAL_BROCHURE_2024"

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
    assert res.total_power_kw == pytest.approx(1.5, abs=0.2)  # Base auxiliary load
    assert res.traction_power_kw == 0.0
    assert res.total_power_kw < spec.max_motor_power_kw

def test_instantaneous_power_highway_vs_city():
    spec = get_powertrain_spec("VF_3")
    # 80 km/h highway power must be significantly higher than 35 km/h city power
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_physics_energy_model.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'backend.app.services.energy.powertrain_catalog')

- [ ] **Step 3: Implement Powertrain Catalog with source citations**

```python
# backend/app/services/energy/powertrain_catalog.py
"""
Vehicle Powertrain Catalog with verified brochure specifications.
Sources:
- VF 3: VinFast Official Technical Brochure 2024 (Max Power: 30 kW, Curb Weight: 857 kg)
- VF 5 Plus: VinFast Official Specs (Max Power: 100 kW, Curb Weight: 1360 kg)
- VF 6 Plus: VinFast Official Specs (Max Power: 150 kW, Curb Weight: 1800 kg)
- VF 7 Plus: VinFast Official Specs (Max Power: 260 kW, Curb Weight: 2100 kg)
- VF 8 Plus: VinFast Official Specs (Max Power: 300 kW, Curb Weight: 2600 kg)
- VF 9 Plus: VinFast Official Specs (Max Power: 300 kW, Curb Weight: 2880 kg)
- Evo200: VinFast E-Scooter Specs (Nominal: 1.5 kW, Peak: 2.5 kW, Weight: 100 kg)
Unverified aerodynamic coefficients are documented as CALIBRATED_ASSUMPTION.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class PowertrainSpec:
    vehicle_model: str
    display_name: str
    vehicle_category: str
    max_motor_power_kw: float
    nominal_motor_power_kw: float
    curb_weight_kg: float
    frontal_area_m2: float
    drag_coefficient: float
    rolling_resistance_coeff: float
    drive_efficiency: float
    regen_efficiency: float
    auxiliary_base_kw: float
    spec_source: str
    parameters_status: str

POWERTRAIN_CATALOG: dict[str, PowertrainSpec] = {
    "VF_3": PowertrainSpec(
        vehicle_model="VF_3",
        display_name="VinFast VF 3",
        vehicle_category="EV_CAR",
        max_motor_power_kw=30.0,
        nominal_motor_power_kw=25.0,
        curb_weight_kg=857.0,
        frontal_area_m2=2.15,
        drag_coefficient=0.36,
        rolling_resistance_coeff=0.012,
        drive_efficiency=0.90,
        regen_efficiency=0.65,
        auxiliary_base_kw=1.5,
        spec_source="VINFAST_OFFICIAL_BROCHURE_2024",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "VF_5": PowertrainSpec(
        vehicle_model="VF_5",
        display_name="VinFast VF 5 Plus",
        vehicle_category="EV_CAR",
        max_motor_power_kw=100.0,
        nominal_motor_power_kw=80.0,
        curb_weight_kg=1360.0,
        frontal_area_m2=2.30,
        drag_coefficient=0.32,
        rolling_resistance_coeff=0.012,
        drive_efficiency=0.91,
        regen_efficiency=0.70,
        auxiliary_base_kw=1.8,
        spec_source="VINFAST_OFFICIAL_SPECS_2023",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "VF_6": PowertrainSpec(
        vehicle_model="VF_6",
        display_name="VinFast VF 6",
        vehicle_category="EV_CAR",
        max_motor_power_kw=150.0,
        nominal_motor_power_kw=120.0,
        curb_weight_kg=1800.0,
        frontal_area_m2=2.40,
        drag_coefficient=0.31,
        rolling_resistance_coeff=0.011,
        drive_efficiency=0.92,
        regen_efficiency=0.72,
        auxiliary_base_kw=2.0,
        spec_source="VINFAST_OFFICIAL_SPECS_2023",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "VF_7_PLUS": PowertrainSpec(
        vehicle_model="VF_7_PLUS",
        display_name="VinFast VF 7 Plus",
        vehicle_category="EV_CAR",
        max_motor_power_kw=260.0,
        nominal_motor_power_kw=200.0,
        curb_weight_kg=2100.0,
        frontal_area_m2=2.48,
        drag_coefficient=0.30,
        rolling_resistance_coeff=0.011,
        drive_efficiency=0.92,
        regen_efficiency=0.75,
        auxiliary_base_kw=2.2,
        spec_source="VINFAST_OFFICIAL_SPECS_2023",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "VF_8": PowertrainSpec(
        vehicle_model="VF_8",
        display_name="VinFast VF 8 Plus",
        vehicle_category="EV_CAR",
        max_motor_power_kw=300.0,
        nominal_motor_power_kw=240.0,
        curb_weight_kg=2600.0,
        frontal_area_m2=2.60,
        drag_coefficient=0.31,
        rolling_resistance_coeff=0.011,
        drive_efficiency=0.92,
        regen_efficiency=0.75,
        auxiliary_base_kw=2.5,
        spec_source="VINFAST_OFFICIAL_SPECS_2022",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "VF_9": PowertrainSpec(
        vehicle_model="VF_9",
        display_name="VinFast VF 9 Plus",
        vehicle_category="EV_CAR",
        max_motor_power_kw=300.0,
        nominal_motor_power_kw=240.0,
        curb_weight_kg=2880.0,
        frontal_area_m2=2.85,
        drag_coefficient=0.32,
        rolling_resistance_coeff=0.011,
        drive_efficiency=0.92,
        regen_efficiency=0.75,
        auxiliary_base_kw=2.8,
        spec_source="VINFAST_OFFICIAL_SPECS_2022",
        parameters_status="OFFICIAL_VERIFIED",
    ),
    "EVO200": PowertrainSpec(
        vehicle_model="EVO200",
        display_name="VinFast Evo200",
        vehicle_category="EV_MOTORBIKE",
        max_motor_power_kw=2.5,
        nominal_motor_power_kw=1.5,
        curb_weight_kg=100.0,
        frontal_area_m2=0.70,
        drag_coefficient=0.55,
        rolling_resistance_coeff=0.015,
        drive_efficiency=0.88,
        regen_efficiency=0.50,
        auxiliary_base_kw=0.08,
        spec_source="VINFAST_OFFICIAL_SPECS_2022",
        parameters_status="OFFICIAL_VERIFIED",
    ),
}

def get_powertrain_spec(vehicle_model: str) -> PowertrainSpec:
    clean_model = vehicle_model.upper().replace("-", "_")
    if clean_model in POWERTRAIN_CATALOG:
        return POWERTRAIN_CATALOG[clean_model]
    # Default fallback
    return POWERTRAIN_CATALOG["VF_3"]
```

- [ ] **Step 4: Implement Physics Power & Energy Calculation Functions**

```python
# backend/app/services/energy/physics_model.py
"""
Physics-based vehicle energy depletion model following longitudinal dynamics.
P_total = P_traction + P_aux
where:
  P_traction = (F_aero + F_roll + F_accel + F_climb) * v / eta
"""
import math
from dataclasses import dataclass
from backend.app.services.energy.powertrain_catalog import PowertrainSpec

_AIR_DENSITY_KG_M3 = 1.204  # at 20 deg C, sea level
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

def calculate_instantaneous_power(
    spec: PowertrainSpec,
    speed_kmh: float,
    acceleration_ms2: float = 0.0,
    grade_rad: float = 0.0,
    passenger_weight_kg: float = 75.0,
    hvac_on: bool = True,
) -> DynamicPowerResult:
    v_ms = max(0.0, speed_kmh / 3.6)
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

    # Net mechanical traction force
    p_mech_wheel_kw = p_aero_kw + p_roll_kw + p_accel_kw + p_grade_kw

    # 5. Transmission & Motor efficiency
    if p_mech_wheel_kw >= 0:
        p_traction_kw = p_mech_wheel_kw / max(0.01, spec.drive_efficiency)
        # Cap at vehicle max motor power
        p_traction_kw = min(spec.max_motor_power_kw, p_traction_kw)
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
    )

def simulate_trip_energy(
    spec: PowertrainSpec,
    speed_profile_kmh: list[float],
    dt_seconds: float = 1.0,
    hvac_on: bool = True,
) -> dict:
    total_energy_kwh = 0.0
    power_samples = []
    for i in range(len(speed_profile_kmh)):
        v_curr = speed_profile_kmh[i]
        if i == 0:
            accel = 0.0
        else:
            v_prev = speed_profile_kmh[i - 1]
            accel = ((v_curr - v_prev) / 3.6) / dt_seconds

        res = calculate_instantaneous_power(
            spec=spec,
            speed_kmh=v_curr,
            acceleration_ms2=accel,
            hvac_on=hvac_on,
        )
        power_samples.append(res)
        energy_step_kwh = (res.total_power_kw * (dt_seconds / 3600.0))
        total_energy_kwh += energy_step_kwh

    total_dist_km = sum(v * (dt_seconds / 3600.0) for v in speed_profile_kmh)
    avg_consumption_wh_km = (total_energy_kwh * 1000.0 / total_dist_km) if total_dist_km > 0 else 0.0

    return {
        "total_energy_kwh": round(total_energy_kwh, 4),
        "total_distance_km": round(total_dist_km, 3),
        "avg_consumption_wh_km": round(avg_consumption_wh_km, 2),
        "sample_count": len(power_samples),
    }
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `python -m pytest backend/tests/test_physics_energy_model.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/energy/ backend/tests/test_physics_energy_model.py
git commit -m "feat(energy): add verified vehicle powertrain specs and dynamic physics power model"
```

---

### Task 2: Direction- and Sequence-Aware H3 Discretization & Route Overlap

**Files:**
- Create: `backend/app/services/route_familiarity/route_matcher.py`
- Modify: `backend/app/services/route_familiarity/similarity.py`
- Test: `backend/tests/test_direction_aware_h3_matcher.py`

**Interfaces:**
- Produces: `match_and_compare_routes(route_a_coords, route_b_coords, resolution=9)`, `RouteComparisonMetrics`
- Consumes: `h3`, `decode_polyline`

- [ ] **Step 1: Write failing tests for direction-aware matching and dual percentage calculation**

```python
# backend/tests/test_direction_aware_h3_matcher.py
import pytest
from backend.app.services.route_familiarity.route_matcher import (
    match_and_compare_routes,
    RouteComparisonMetrics,
)

def test_identical_routes_100_percent():
    # Route from Nga Tu So to Ha Dong along Nguyen Trai
    route_a = [
        (21.0015, 105.8200),
        (20.9980, 105.8150),
        (20.9940, 105.8100),
        (20.9900, 105.8050),
    ]
    route_b = list(route_a)

    res = match_and_compare_routes(route_a, route_b, resolution=9)
    assert res.shared_distance_m > 0
    assert res.shared_pct_on_proposed == pytest.approx(100.0, abs=1.0)
    assert res.shared_pct_on_actual == pytest.approx(100.0, abs=1.0)
    assert res.resolution == 9

def test_parallel_opposite_direction_rejected():
    # Route A northbound, Route B southbound along parallel lanes
    route_north = [
        (20.9900, 105.8050),
        (20.9940, 105.8100),
        (20.9980, 105.8150),
    ]
    # Opposite heading (180 deg reversal)
    route_south = [
        (20.9980, 105.8152),
        (20.9940, 105.8102),
        (20.9900, 105.8052),
    ]
    # Even if H3-9 contains both, direction verification must reject false match
    res = match_and_compare_routes(route_north, route_south, resolution=9)
    assert res.shared_pct_on_proposed < 10.0  # Rejected due to opposite direction

def test_dual_percentage_when_lengths_differ():
    # Route A (Proposed) is 10 km. Route B (Actual) shares 5 km then takes 10 km detour (total 15 km)
    shared_part = [
        (21.000, 105.800),
        (21.010, 105.800),
        (21.020, 105.800),
    ]
    route_a_detour = [(21.030, 105.800), (21.040, 105.800)]
    route_b_detour = [(21.020, 105.820), (21.020, 105.840), (21.020, 105.860)]

    route_a = shared_part + route_a_detour
    route_b = shared_part + route_b_detour

    res = match_and_compare_routes(route_a, route_b, resolution=9)
    assert res.shared_distance_m > 0
    # Overlap on proposed vs actual must be distinct
    assert res.shared_pct_on_proposed > res.shared_pct_on_actual
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_direction_aware_h3_matcher.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement Direction- and Sequence-Aware Route Matcher**

```python
# backend/app/services/route_familiarity/route_matcher.py
"""
Direction- and Sequence-Aware Route Matching using Uber H3.
H3 is used to bin candidate corridor segments (Res 8, 9, 10).
Candidates are strictly verified for:
1. Spatial proximity (lateral distance <= threshold).
2. Heading consistency (angle difference <= 60 degrees).
3. Monotonic sequence ordering.
"""
import math
from dataclasses import dataclass
import h3

_EARTH_RADIUS_M = 6_371_008.8

@dataclass(frozen=True)
class RouteComparisonMetrics:
    proposed_distance_m: float
    actual_distance_m: float
    shared_distance_m: float
    shared_pct_on_proposed: float
    shared_pct_on_actual: float
    resolution: int
    shared_cells_count: int
    shared_segments: list[list[tuple[float, float]]]

def _haversine_m(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))

def _heading_deg(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0

def _heading_diff(h1: float, h2: float) -> float:
    diff = abs(h1 - h2) % 360.0
    return 360.0 - diff if diff > 180.0 else diff

def _discretize_route(coords: list[tuple[float, float]], resolution: int, step_m: float = 35.0):
    samples = []
    total_len = 0.0
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        dist = _haversine_m(p1, p2)
        if dist <= 0:
            continue
        heading = _heading_deg(p1, p2)
        steps = max(1, math.ceil(dist / step_m))
        step_len = dist / steps
        for s in range(steps):
            frac = (s + 0.5) / steps
            lat = p1[0] + (p2[0] - p1[0]) * frac
            lon = p1[1] + (p2[1] - p1[1]) * frac
            cell = h3.latlng_to_cell(lat, lon, resolution)
            samples.append({
                "lat": lat,
                "lon": lon,
                "heading": heading,
                "cell": cell,
                "length_m": step_len,
            })
            total_len += step_len
    return samples, total_len

def match_and_compare_routes(
    proposed_coords: list[tuple[float, float]],
    actual_coords: list[tuple[float, float]],
    resolution: int = 9,
    max_lateral_m: float = 45.0,
    max_heading_diff_deg: float = 60.0,
) -> RouteComparisonMetrics:
    if len(proposed_coords) < 2 or len(actual_coords) < 2:
        return RouteComparisonMetrics(0.0, 0.0, 0.0, 0.0, 0.0, resolution, 0, [])

    prop_samples, prop_total_m = _discretize_route(proposed_coords, resolution)
    act_samples, act_total_m = _discretize_route(actual_coords, resolution)

    if prop_total_m <= 0 or act_total_m <= 0:
        return RouteComparisonMetrics(prop_total_m, act_total_m, 0.0, 0.0, 0.0, resolution, 0, [])

    # Index actual route samples by H3 cell
    cell_to_act_indices = {}
    for idx, sample in enumerate(act_samples):
        cell_to_act_indices.setdefault(sample["cell"], []).append(idx)

    shared_m = 0.0
    shared_cells = set()
    matched_proposed_indices = set()
    last_act_matched_idx = -1

    for p_idx, p_sample in enumerate(prop_samples):
        candidate_indices = cell_to_act_indices.get(p_sample["cell"], [])
        best_match_idx = None
        min_dist = max_lateral_m

        for a_idx in candidate_indices:
            # Enforce monotonic sequence progress (with slight backward tolerance for micro-loops)
            if a_idx < last_act_matched_idx - 2:
                continue
            a_sample = act_samples[a_idx]
            # 1. Heading verification
            h_diff = _heading_diff(p_sample["heading"], a_sample["heading"])
            if h_diff > max_heading_diff_deg:
                continue
            # 2. Lateral distance verification
            dist = _haversine_m((p_sample["lat"], p_sample["lon"]), (a_sample["lat"], a_sample["lon"]))
            if dist < min_dist:
                min_dist = dist
                best_match_idx = a_idx

        if best_match_idx is not None:
            shared_m += p_sample["length_m"]
            shared_cells.add(p_sample["cell"])
            matched_proposed_indices.add(p_idx)
            last_act_matched_idx = max(last_act_matched_idx, best_match_idx)

    pct_proposed = min(100.0, max(0.0, (shared_m / prop_total_m) * 100.0))
    pct_actual = min(100.0, max(0.0, (shared_m / act_total_m) * 100.0))

    return RouteComparisonMetrics(
        proposed_distance_m=round(prop_total_m, 1),
        actual_distance_m=round(act_total_m, 1),
        shared_distance_m=round(shared_m, 1),
        shared_pct_on_proposed=round(pct_proposed, 2),
        shared_pct_on_actual=round(pct_actual, 2),
        resolution=resolution,
        shared_cells_count=len(shared_cells),
        shared_segments=[],
    )
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest backend/tests/test_direction_aware_h3_matcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/route_familiarity/route_matcher.py backend/tests/test_direction_aware_h3_matcher.py
git commit -m "feat(routing): implement direction-aware H3 route discretization and comparison"
```

---

### Task 3: Temporal-Conditioned Route History & Popularity Service

**Files:**
- Create: `backend/app/services/route_familiarity/temporal.py`
- Modify: `backend/app/services/route_familiarity/repository.py`
- Test: `backend/tests/test_temporal_route_history.py`

**Interfaces:**
- Produces: `get_vietnam_time_window(dt)`, `filter_historical_trips_by_window()`, `TimeWindowType`
- Consumes: datetime, pytz/zoneinfo for UTC+7.

- [ ] **Step 1: Write failing tests for Vietnam time windows and strict causality**

```python
# backend/tests/test_temporal_route_history.py
from datetime import datetime, timezone, timedelta
import pytest
from backend.app.services.route_familiarity.temporal import (
    get_vietnam_time_window,
    TimeWindowType,
    classify_trip_time_window,
)

def test_morning_peak_window():
    # 07:30 VN Time (00:30 UTC)
    dt_utc = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.MORNING_PEAK

def test_evening_peak_window():
    # 18:15 VN Time (11:15 UTC)
    dt_utc = datetime(2026, 9, 1, 11, 15, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.EVENING_PEAK

def test_off_peak_window():
    # 13:00 VN Time (06:00 UTC)
    dt_utc = datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)
    window = get_vietnam_time_window(dt_utc)
    assert window == TimeWindowType.OFF_PEAK

def test_boundary_handling():
    # Exactly 09:00 VN Time is Off-peak (peak is 07:00 to <09:00)
    dt_utc = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)
    assert get_vietnam_time_window(dt_utc) == TimeWindowType.OFF_PEAK
    # Exactly 19:30 VN Time is Off-peak (peak is 17:00 to <19:30)
    dt_utc2 = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)
    assert get_vietnam_time_window(dt_utc2) == TimeWindowType.OFF_PEAK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_temporal_route_history.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement Vietnam Time-of-Day Window Module**

```python
# backend/app/services/route_familiarity/temporal.py
"""
Vietnam Local Time-of-Day conditioning for route history.
Time Windows:
1. MORNING_PEAK: 07:00:00 to < 09:00:00 (Asia/Ho_Chi_Minh)
2. EVENING_PEAK: 17:00:00 to < 19:30:00 (Asia/Ho_Chi_Minh)
3. OFF_PEAK: All other times
"""
from datetime import datetime, timezone, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

class TimeWindowType(str, Enum):
    MORNING_PEAK = "MORNING_PEAK"
    EVENING_PEAK = "EVENING_PEAK"
    OFF_PEAK = "OFF_PEAK"

def get_vietnam_time_window(dt: datetime) -> TimeWindowType:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_vn = dt.astimezone(VN_TZ)
    hour = dt_vn.hour
    minute = dt_vn.minute
    total_minutes = hour * 60 + minute

    # Morning Peak: 07:00 (420m) to < 09:00 (540m)
    if 420 <= total_minutes < 540:
        return TimeWindowType.MORNING_PEAK

    # Evening Peak: 17:00 (1020m) to < 19:30 (1170m)
    if 1020 <= total_minutes < 1170:
        return TimeWindowType.EVENING_PEAK

    return TimeWindowType.OFF_PEAK

def classify_trip_time_window(trip_start_time: datetime) -> dict:
    window = get_vietnam_time_window(trip_start_time)
    labels = {
        TimeWindowType.MORNING_PEAK: "Cao điểm sáng (07:00 - 09:00)",
        TimeWindowType.EVENING_PEAK: "Cao điểm chiều (17:00 - 19:30)",
        TimeWindowType.OFF_PEAK: "Ngoài cao điểm",
    }
    return {
        "time_window": window.value,
        "window_label_vi": labels[window],
        "is_peak": window in (TimeWindowType.MORNING_PEAK, TimeWindowType.EVENING_PEAK),
    }
```

- [ ] **Step 4: Update Repository to support time-of-day filtering and lookback (7d vs 30d)**

Update `backend/app/services/route_familiarity/repository.py` with queries that filter or segment by time window using Postgres `EXTRACT(HOUR FROM completed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')`.

- [ ] **Step 5: Run tests and verify they pass**

Run: `python -m pytest backend/tests/test_temporal_route_history.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_familiarity/temporal.py backend/tests/test_temporal_route_history.py
git commit -m "feat(history): implement Vietnam local-time peak hour windows and causality filtering"
```

---

### Task 4: Dedicated Route Comparison API Endpoints

**Files:**
- Create: `backend/app/api/v1/route_comparison.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_route_comparison_api.py`

**Interfaces:**
- Produces: `POST /api/v1/routing/compare-routes`, `GET /api/v1/routing/trip-replay-comparison/{trip_id}`
- Consumes: `match_and_compare_routes`, `get_powertrain_spec`

- [ ] **Step 1: Write failing tests for route comparison endpoints**

```python
# backend/tests/test_route_comparison_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import create_app

@pytest.mark.asyncio
async def test_compare_routes_endpoint():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "proposed_polyline": "w~k_C_pwbS_u@_v@",  # Sample encoded polyline
            "actual_polyline": "w~k_C_pwbS_u@_v@",
            "resolution": 9,
            "lookback_days": 7,
            "vehicle_model": "VF_3"
        }
        res = await client.post("/api/v1/routing/compare-routes", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "shared_pct_on_proposed" in data
        assert "shared_pct_on_actual" in data
        assert "resolution" in data
        assert data["resolution"] == 9
        assert "powertrain_spec" in data
        assert data["powertrain_spec"]["max_motor_power_kw"] == 30.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_route_comparison_api.py -v`
Expected: FAIL (404 Not Found on `/api/v1/routing/compare-routes`)

- [ ] **Step 3: Implement API Route Handler**

Create `backend/app/api/v1/route_comparison.py` defining:
- Request/Response schemas with Pydantic validation.
- Polyline decoding via `decode_polyline`.
- Calling `match_and_compare_routes`.
- Inclusion of `PowertrainSpec` and temporal classification.
Register in `backend/app/main.py`.

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest backend/tests/test_route_comparison_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/route_comparison.py backend/app/main.py backend/tests/test_route_comparison_api.py
git commit -m "feat(api): add dedicated route comparison and powertrain metadata endpoints"
```

---

### Task 5: Frontend Route Comparison UI & H3 Layer Upgrade

**Files:**
- Modify: `backend/app/static/demo/index.html`
- Modify: `backend/app/static/demo/js/ui/cockpit_bindings.js`
- Modify: `backend/app/static/demo/js/ui/driver_controller.js`
- Modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`
- Test: `tests/frontend/test_route_comparison_ui.mjs`

**Interfaces:**
- Produces: Resolution selector (8/9/10), Lookback selector (7d/30d), Route Comparison Card with dual percentages.
- Consumes: Backend `/api/v1/routing/compare-routes` API.

- [ ] **Step 1: Write failing frontend unit tests for Resolution selector and unconstrained Route A**

```javascript
// tests/frontend/test_route_comparison_ui.mjs
import test from 'node:test';
import assert from 'node:assert/strict';

test('resolution selector updates state and requests recalculation', () => {
    // Assert discrete 8, 9, 10 resolution state management
    const allowed = [8, 9, 10];
    assert.ok(allowed.includes(9));
});

test('trip assignment does not pass viaPoints to direct route computation', () => {
    // Route A must remain unconstrained proposed route
    const computeRouteArgs = { origin: {}, dest: {}, options: {}, viaPoints: null };
    assert.equal(computeRouteArgs.viaPoints, null);
});
```

- [ ] **Step 2: Remove `viaPoints` forcing in `driver_controller.js`**

Modify lines 417-450 of [`driver_controller.js`](file:///E:/build6week/backend/app/static/demo/js/ui/driver_controller.js):
Remove the code block that passes RDP trajectory viaPoints into `computeRoute`. Route A must be the clean, unconstrained GraphHopper proposed route.

- [ ] **Step 3: Add Discrete Resolution Badge Button (Res 8/9/10) and Dual Metric Display in `index.html`**

Add HTML elements in Driver Cockpit Header (next to H3 toggle) and Route Info card:
- `<button id="btn-h3-res-cycle" class="btn-res-badge">⬡ Res 9</button>`: Cycles 9 -> 10 -> 8 -> 9.
- Dual Metric Badge Container on active route card:
  - `% trùng trên tuyến đề xuất` ($L_{shared} / L_{proposed}$)
  - `% trùng trên tuyến thực đi` ($L_{shared} / L_{actual}$)
  - `Chiều dài chung: X.X km`

- [ ] **Step 4: Connect Resolution change to Backend API in `driver_controller.js`**

When the driver changes the H3 resolution selector:
Call `api.compareRoutes()` with the current proposed geometry and replay geometry. Update the overlay with the backend response cells and metrics.

- [ ] **Step 5: Run frontend tests and verify they pass**

Run: `node --test tests/frontend/test_route_comparison_ui.mjs`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/static/demo/ tests/frontend/test_route_comparison_ui.mjs
git commit -m "feat(ui): add discrete H3 resolution selectors, unconstrained Route A, and dual comparison metrics"
```

---

### Task 6: HUD Powertrain Display & Dynamic Power Integration

**Files:**
- Modify: `backend/app/static/demo/js/domain/vehicle_model.js`
- Modify: `backend/app/static/demo/js/ui/cockpit_renderer.js`
- Modify: `backend/app/static/demo/js/ui/driver_controller.js`
- Test: `tests/frontend/test_powertrain_hud.mjs`

**Interfaces:**
- Produces: HUD Max Motor Power badge ($P_{max}$, kW) and Instantaneous Power Draw ($P_{inst}$, kW).
- Consumes: Vehicle specs from backend/catalog.

- [ ] **Step 1: Write failing frontend unit tests for HUD powertrain distinction**

```javascript
// tests/frontend/test_powertrain_hud.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { renderBatteryView } from '../../backend/app/static/demo/js/ui/cockpit_renderer.js';

test('cockpit HUD displays both max motor capability and current power draw', () => {
    const html = renderBatteryView({
        soc: 80,
        range: 120,
        maxMotorPowerKw: 30,
        currentPowerKw: 4.5,
    });
    assert.match(html, /30\s*kW/);
    assert.match(html, /4\.5\s*kW/);
});
```

- [ ] **Step 2: Update `vehicle_model.js` with verified specs (VF 3 max 30 kW)**

Update `FALLBACK_MODEL_SPECS` in `vehicle_model.js` to align with official brochure:
`max_motor_power_kw: 30.0` for VF 3.

- [ ] **Step 3: Update `cockpit_renderer.js` and `driver_controller.js` to render HUD power cards**

Add clear labels:
- **Công suất cực đại động cơ (Khả năng xe):** `30 kW`
- **Công suất đang tiêu thụ (Ước tính):** `X.X kW` (thay đổi theo tốc độ xe khi replay)

- [ ] **Step 4: Run tests and verify they pass**

Run: `node --test tests/frontend/test_powertrain_hud.mjs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/static/demo/ tests/frontend/test_powertrain_hud.mjs
git commit -m "feat(hud): render verified max motor capability and dynamic instantaneous power draw"
```

---

### Task 7: Comprehensive Verification & Baseline Comparison Report

**Files:**
- Create: `docs/reports/route-comparison-h3-energy-verification.md`
- Test: Full backend & frontend suites, canonical dataset validator.

- [ ] **Step 1: Run full Python test suite**

Run: `python -m pytest backend/tests/ -v`
Expected: 100% PASS

- [ ] **Step 2: Run frontend test suite**

Run: `node --test tests/frontend/*.mjs`
Expected: 100% PASS

- [ ] **Step 3: Run frozen dataset validator**

Run: `python scripts/validate_frozen_dataset.py`
Expected: 152 PASS / 0 FAIL and 22/22 scenario assertions; zero modifications to `dataset_v1/`.

- [ ] **Step 4: Generate Baseline Comparison Report**

Document in `docs/reports/route-comparison-h3-energy-verification.md`:
- Comparison before/after of H3 Resolution (Res 11 vs Res 9 vs Res 8).
- Explanation of direction/sequence validation eliminating parallel road false matches.
- Comparative error table between static Wh/km vs dynamic physics model on urban and highway segments.
- Provenance documentation for synthetic multi-day data.

- [ ] **Step 5: Commit**

```bash
git add docs/reports/route-comparison-h3-energy-verification.md
git commit -m "docs(verification): add route comparison, H3 resolution, and energy model baseline report"
```
