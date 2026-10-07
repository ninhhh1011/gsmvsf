"""Vehicle catalog and energy computation API endpoints."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

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


@router.get("/vehicles/catalog", response_model=list[VehicleCatalogItem])
async def get_vehicle_catalog() -> list[VehicleCatalogItem]:
    """Return the canonical vehicle catalog as JSON array.

    Schema: { id, name, brand, battery_kwh, efficiency_kwh_per_km, supported_services[], vehicle_type }
    This is the SINGLE source of truth for the frontend vehicle catalog.
    """
    return VEHICLE_CATALOG
