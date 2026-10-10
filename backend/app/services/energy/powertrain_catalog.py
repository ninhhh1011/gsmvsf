"""
Project powertrain parameters with per-field provenance.

Only the VF 3 motor maximum has verified evidence in this implementation.
All other retained parameters are assumptions, not calibrated measurements.
Legacy source identifiers do not certify every parameter in a specification.
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
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
    ),
    "HERIO_GREEN": PowertrainSpec(
        vehicle_model="HERIO_GREEN",
        display_name="VinFast Herio Green (VF 5 Fleet)",
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
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
    ),
    "VF_7_ECO": PowertrainSpec(
        vehicle_model="VF_7_ECO",
        display_name="VinFast VF 7 Eco",
        vehicle_category="EV_CAR",
        max_motor_power_kw=130.0,
        nominal_motor_power_kw=100.0,
        curb_weight_kg=1950.0,
        frontal_area_m2=2.48,
        drag_coefficient=0.30,
        rolling_resistance_coeff=0.011,
        drive_efficiency=0.92,
        regen_efficiency=0.72,
        auxiliary_base_kw=2.0,
        spec_source="VINFAST_OFFICIAL_SPECS_2023",
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
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
        parameters_status="PROJECT_ASSUMPTION",
    ),
}


def get_powertrain_spec(vehicle_model: str) -> PowertrainSpec:
    """Return supported model parameters; never substitute another model."""
    clean_model = vehicle_model.upper().replace("-", "_").strip()
    if clean_model in POWERTRAIN_CATALOG:
        return POWERTRAIN_CATALOG[clean_model]
    raise ValueError(f"Unsupported powertrain model: {vehicle_model}")


PHYSICAL_PARAMETER_FIELDS = (
    "max_motor_power_kw", "nominal_motor_power_kw", "curb_weight_kg",
    "frontal_area_m2", "drag_coefficient", "rolling_resistance_coeff",
    "drive_efficiency", "regen_efficiency", "auxiliary_base_kw",
)


def get_parameter_provenance(spec: PowertrainSpec) -> dict[str, dict[str, str]]:
    """Only the VF 3 motor maximum has verified evidence for this model."""
    result = {}
    for field in PHYSICAL_PARAMETER_FIELDS:
        verified = spec.vehicle_model == "VF_3" and field == "max_motor_power_kw"
        result[field] = {
            "status": "OFFICIAL_VERIFIED" if verified else "PROJECT_ASSUMPTION",
            "source": spec.spec_source if verified else "PROJECT_PHYSICS_MODEL",
        }
    return result
