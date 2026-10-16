"""Vehicle catalog and energy computation API endpoints."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.energy.physics_model import calculate_power_step
from backend.app.services.energy.powertrain_catalog import (
    PHYSICAL_PARAMETER_FIELDS,
    get_parameter_provenance,
    get_powertrain_spec,
)

router = APIRouter()


class VehicleCatalogItem(BaseModel):
    """A vehicle model in the catalog."""
    id: str = Field(..., description="Unique vehicle model identifier")
    name: str = Field(..., description="Human-readable display name")
    brand: str = Field(..., description="Vehicle manufacturer/brand")
    battery_kwh: float = Field(..., gt=0, description="Usable battery capacity in kWh")
    efficiency_kwh_per_km: float = Field(..., gt=0, description="Energy consumption in kWh/km")
    supported_services: list[str] = Field(
        default_factory=list,
        description="List of supported service types (charging, battery_swap)"
    )
    vehicle_type: Literal["EV_CAR", "EV_MOTORBIKE"] = Field(
        ..., description="Vehicle category"
    )
    max_motor_power_kw: float | None = None
    nominal_motor_power_kw: float | None = None
    curb_weight_kg: float | None = None
    frontal_area_m2: float | None = None
    drag_coefficient: float | None = None
    rolling_resistance_coeff: float | None = None
    drive_efficiency: float | None = None
    regen_efficiency: float | None = None
    auxiliary_base_kw: float | None = None
    spec_source: str | None = None
    parameters_status: str = "UNSUPPORTED_MODEL"
    parameter_provenance: dict[str, dict[str, str]] = Field(default_factory=dict)


# Canonical VinFast vehicle catalog — single source of truth for frontend
VEHICLE_CATALOG: list[VehicleCatalogItem] = [
    # --- VinFast EV Cars ---
    VehicleCatalogItem(
        id="VF_3", name="VF 3", brand="VinFast",
        battery_kwh=17.15, efficiency_kwh_per_km=0.095,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_5", name="VF 5", brand="VinFast",
        battery_kwh=34.25, efficiency_kwh_per_km=0.125,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="HERIO_GREEN", name="Herio Green", brand="VinFast",
        battery_kwh=34.25, efficiency_kwh_per_km=0.125,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_6", name="VF 6", brand="VinFast",
        battery_kwh=54.83, efficiency_kwh_per_km=0.145,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_7_ECO", name="VF 7 Eco", brand="VinFast",
        battery_kwh=54.83, efficiency_kwh_per_km=0.155,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_7_PLUS", name="VF 7 Plus", brand="VinFast",
        battery_kwh=69.28, efficiency_kwh_per_km=0.170,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_8", name="VF 8", brand="VinFast",
        battery_kwh=80.68, efficiency_kwh_per_km=0.195,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_9", name="VF 9", brand="VinFast",
        battery_kwh=113.16, efficiency_kwh_per_km=0.235,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VF_E34", name="VF e34", brand="VinFast",
        battery_kwh=38.55, efficiency_kwh_per_km=0.135,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="NERIO_GREEN", name="Nerio Green", brand="VinFast",
        battery_kwh=38.55, efficiency_kwh_per_km=0.135,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    # --- VinFast EV Motorbikes ---
    VehicleCatalogItem(
        id="EVO200", name="Evo200", brand="VinFast",
        battery_kwh=3.22, efficiency_kwh_per_km=0.040,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="FELIZ_S", name="Feliz S", brand="VinFast",
        battery_kwh=3.22, efficiency_kwh_per_km=0.042,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="KLARA_S", name="Klara S", brand="VinFast",
        battery_kwh=3.22, efficiency_kwh_per_km=0.045,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="VENTO_S", name="Vento S", brand="VinFast",
        battery_kwh=3.22, efficiency_kwh_per_km=0.045,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="EVO", name="Evo (Swap)", brand="VinFast",
        battery_kwh=2.76, efficiency_kwh_per_km=0.038,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging", "battery_swap"]
    ),
    VehicleCatalogItem(
        id="EVO_LITE", name="Evo Lite (Swap)", brand="VinFast",
        battery_kwh=1.38, efficiency_kwh_per_km=0.038,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging", "battery_swap"]
    ),
    VehicleCatalogItem(
        id="FELIZ_II", name="Feliz II (Swap)", brand="VinFast",
        battery_kwh=2.76, efficiency_kwh_per_km=0.040,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging", "battery_swap"]
    ),
    VehicleCatalogItem(
        id="VIPER", name="Viper (Swap)", brand="VinFast",
        battery_kwh=1.38, efficiency_kwh_per_km=0.038,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging", "battery_swap"]
    ),
    # --- Multi-Brand EVs ---
    VehicleCatalogItem(
        id="BYD_ATTO_3", name="BYD Atto 3", brand="BYD",
        battery_kwh=58.00, efficiency_kwh_per_km=0.156,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="TESLA_MODEL_3", name="Tesla Model 3", brand="Tesla",
        battery_kwh=75.00, efficiency_kwh_per_km=0.144,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="HYUNDAI_IONIQ_5", name="Hyundai Ioniq 5", brand="Hyundai",
        battery_kwh=70.00, efficiency_kwh_per_km=0.165,
        vehicle_type="EV_CAR", supported_services=["charging"]
    ),
    VehicleCatalogItem(
        id="DAT_BIKE_WEAVER", name="Dat Bike Weaver++", brand="Dat Bike",
        battery_kwh=4.80, efficiency_kwh_per_km=0.035,
        vehicle_type="EV_MOTORBIKE", supported_services=["charging", "battery_swap"]
    ),
]


for item in VEHICLE_CATALOG:
    item.parameter_provenance = {
        field: {"status": "UNAVAILABLE", "source": "UNAVAILABLE"}
        for field in PHYSICAL_PARAMETER_FIELDS
    }
    item.parameter_provenance.update({
        "battery_kwh": {"status": "CATALOG_VALUE", "source": "VEHICLE_CATALOG"},
        "efficiency_kwh_per_km": {"status": "PROJECT_ESTIMATE", "source": "VEHICLE_CATALOG"},
    })
    try:
        spec = get_powertrain_spec(item.id)
    except ValueError:
        continue
    for field in PHYSICAL_PARAMETER_FIELDS:
        setattr(item, field, getattr(spec, field))
    item.spec_source = "PROJECT_PHYSICS_MODEL"
    item.parameters_status = spec.parameters_status
    item.parameter_provenance.update(get_parameter_provenance(spec))


class PowerStepRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    vehicle_model: str = Field(min_length=1, max_length=100)
    speed_kmh: float = Field(ge=0, le=1000)
    previous_speed_kmh: float | None = Field(default=None, ge=0, le=1000)
    dt_seconds: float = Field(ge=0, le=3600)
    current_soc_pct: float = Field(ge=0, le=100)


class PowerStepResponse(BaseModel):
    instantaneous_power_kw: float | None
    energy_delta_kwh: float | None
    current_soc_pct: float
    estimated_range_km: float
    power_status: Literal["MODEL_ESTIMATE", "KINEMATICS_EXCEED_CAPABILITY", "UNSUPPORTED_MODEL"]
    power_provenance: dict
    max_motor_power_kw: float | None


@router.post("/vehicles/power-step", response_model=PowerStepResponse)
async def power_step(payload: PowerStepRequest) -> PowerStepResponse:
    """Estimate battery power and interval energy; this is not measured telemetry."""
    model = payload.vehicle_model.upper().replace("-", "_").strip()
    vehicle = next((item for item in VEHICLE_CATALOG if item.id == model), None)
    if vehicle is None:
        raise HTTPException(status_code=422, detail="Unknown vehicle model")
    power = None
    energy_delta = None
    soc = payload.current_soc_pct
    status = "UNSUPPORTED_MODEL"
    if vehicle.parameters_status != "UNSUPPORTED_MODEL":
        spec = get_powertrain_spec(model)
        try:
            power, energy_delta = calculate_power_step(
                spec, payload.speed_kmh, payload.previous_speed_kmh, payload.dt_seconds
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        soc = max(0.0, min(100.0, soc - energy_delta / vehicle.battery_kwh * 100))
        status = power.power_status
    return PowerStepResponse(
        instantaneous_power_kw=power.total_power_kw if power else None,
        energy_delta_kwh=energy_delta,
        current_soc_pct=soc,
        estimated_range_km=vehicle.battery_kwh * soc / 100 / vehicle.efficiency_kwh_per_km,
        power_status=status,
        power_provenance={
            "source": "PROJECT_PHYSICS_MODEL" if power else "UNAVAILABLE",
            "parameters": vehicle.parameter_provenance,
            "integration": "LINEAR_SPEED_MIDPOINT" if power else "UNAVAILABLE",
            "regen_limit": "PROJECT_ASSUMPTION_HALF_MOTOR_MAX" if power else "UNAVAILABLE",
            "range_source": "PROJECT_ESTIMATE",
        },
        max_motor_power_kw=vehicle.max_motor_power_kw,
    )


@router.get("/vehicles/catalog", response_model=list[VehicleCatalogItem])
async def get_vehicle_catalog() -> list[VehicleCatalogItem]:
    """Return the canonical vehicle catalog as JSON array.

    Schema: { id, name, brand, battery_kwh, efficiency_kwh_per_km, supported_services[], vehicle_type }
    This is the SINGLE source of truth for the frontend vehicle catalog.
    """
    return VEHICLE_CATALOG
