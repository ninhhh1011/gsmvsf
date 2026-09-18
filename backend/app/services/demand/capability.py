"""
Deterministic Vehicle Capability Resolution for VinFast Fleet.

Resolves vehicle model capabilities strictly according to the official
vehicle catalog (dataset_v1/vehicles/vehicle_model_catalog.csv).
Does NOT use ML. Does NOT use category-level shortcuts (e.g. EV_MOTORBIKE != swap capable).
"""

from pathlib import Path
from typing import Optional
import csv
import logging

from backend.app.config import settings
from backend.app.services.demand.models import (
    ServiceType,
    VehicleCapability,
    VehicleCategory,
)

logger = logging.getLogger(__name__)


class UnknownVehicleModelError(ValueError):
    """Raised when an unrecognized vehicle model is encountered."""
    pass


class UnknownVehicleError(ValueError):
    """Raised when an unrecognized vehicle ID is queried."""
    pass


# Static canonical model registry for all 19 official VinFast models
# Defined byte-for-byte consistent with dataset_v1/vehicles/vehicle_model_catalog.csv
CANONICAL_MODEL_CATALOG: dict[str, VehicleCapability] = {
    # --- EV Cars (10 models: CHARGING only) ---
    "VF_3": VehicleCapability(
        vehicle_model="VF_3",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=18.64,
        usable_capacity_kwh=17.15,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_5": VehicleCapability(
        vehicle_model="VF_5",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=37.23,
        usable_capacity_kwh=34.25,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "HERIO_GREEN": VehicleCapability(
        vehicle_model="HERIO_GREEN",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=37.23,
        usable_capacity_kwh=34.25,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_6": VehicleCapability(
        vehicle_model="VF_6",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=59.6,
        usable_capacity_kwh=54.83,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_7_ECO": VehicleCapability(
        vehicle_model="VF_7_ECO",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=59.6,
        usable_capacity_kwh=54.83,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_7_PLUS": VehicleCapability(
        vehicle_model="VF_7_PLUS",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=75.3,
        usable_capacity_kwh=69.28,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_8": VehicleCapability(
        vehicle_model="VF_8",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=87.7,
        usable_capacity_kwh=80.68,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_9": VehicleCapability(
        vehicle_model="VF_9",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=123.0,
        usable_capacity_kwh=113.16,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "VF_E34": VehicleCapability(
        vehicle_model="VF_E34",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=41.9,
        usable_capacity_kwh=38.55,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    "NERIO_GREEN": VehicleCapability(
        vehicle_model="NERIO_GREEN",
        vehicle_category=VehicleCategory.EV_CAR,
        battery_architecture="FIXED_TRACTION_PACK",
        battery_capacity_kwh=41.9,
        usable_capacity_kwh=38.55,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="CCS2_TYPE2",
    ),
    # --- EV Motorbikes (Charge-only: 5 models: CHARGING only) ---
    "EVO200": VehicleCapability(
        vehicle_model="EVO200",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="FIXED_OR_INTEGRATED_LFP",
        battery_capacity_kwh=3.5,
        usable_capacity_kwh=3.22,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
    ),
    "EVO200_LITE": VehicleCapability(
        vehicle_model="EVO200_LITE",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="FIXED_OR_INTEGRATED_LFP",
        battery_capacity_kwh=3.5,
        usable_capacity_kwh=3.22,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
    ),
    "FELIZ_S": VehicleCapability(
        vehicle_model="FELIZ_S",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="FIXED_OR_INTEGRATED_LFP",
        battery_capacity_kwh=3.5,
        usable_capacity_kwh=3.22,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
    ),
    "KLARA_S_2022": VehicleCapability(
        vehicle_model="KLARA_S_2022",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="FIXED_OR_INTEGRATED_LFP",
        battery_capacity_kwh=3.5,
        usable_capacity_kwh=3.22,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
    ),
    "VENTO_S": VehicleCapability(
        vehicle_model="VENTO_S",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="FIXED_OR_INTEGRATED_LFP",
        battery_capacity_kwh=3.5,
        usable_capacity_kwh=3.22,
        charging_supported=True,
        swap_supported=False,
        public_swap_compatible=False,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
    ),
    # --- EV Motorbikes (Swap-capable: 4 models: CHARGING + BATTERY_SWAP) ---
    "EVO": VehicleCapability(
        vehicle_model="EVO",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="REMOVABLE_SWAP_MODULE",
        battery_capacity_kwh=3.0,
        usable_capacity_kwh=2.76,
        battery_module_capacity_kwh=1.5,
        max_battery_modules=2.0,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
        swap_battery_family="VINFAST_SWAP_LFP_1_5_KWH",
    ),
    "EVO_LITE": VehicleCapability(
        vehicle_model="EVO_LITE",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="REMOVABLE_SWAP_MODULE",
        battery_capacity_kwh=1.5,
        usable_capacity_kwh=1.38,
        battery_module_capacity_kwh=1.5,
        max_battery_modules=2.0,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
        swap_battery_family="VINFAST_SWAP_LFP_1_5_KWH",
    ),
    "FELIZ_II": VehicleCapability(
        vehicle_model="FELIZ_II",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="REMOVABLE_SWAP_MODULE",
        battery_capacity_kwh=3.0,
        usable_capacity_kwh=2.76,
        battery_module_capacity_kwh=1.5,
        max_battery_modules=2.0,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
        swap_battery_family="VINFAST_SWAP_LFP_1_5_KWH",
    ),
    "VIPER": VehicleCapability(
        vehicle_model="VIPER",
        vehicle_category=VehicleCategory.EV_MOTORBIKE,
        battery_architecture="REMOVABLE_SWAP_MODULE",
        battery_capacity_kwh=1.5,
        usable_capacity_kwh=1.38,
        battery_module_capacity_kwh=1.5,
        max_battery_modules=2.0,
        charging_supported=True,
        swap_supported=True,
        public_swap_compatible=True,
        charging_interface_class="VINFAST_MOTORCYCLE_CHARGING",
        swap_battery_family="VINFAST_SWAP_LFP_1_5_KWH",
    ),
}


class VehicleCapabilityResolver:
    """
    Resolver for vehicle models and fleet vehicle instances.
    """

    def __init__(self, dataset_path: Optional[Path] = None):
        self._dataset_path = dataset_path or settings.dataset_path
        self._models = dict(CANONICAL_MODEL_CATALOG)
        self._vehicles: dict[str, dict] = {}
        self._load_vehicles()

    def _load_vehicles(self):
        """Load fleet vehicle mapping from vehicles.csv if available."""
        vehicles_csv = self._dataset_path / "vehicles" / "vehicles.csv"
        if not vehicles_csv.exists():
            return

        try:
            with open(vehicles_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vid = row.get("vehicle_id")
                    if vid:
                        self._vehicles[vid] = row
        except Exception as e:
            logger.warning("Could not load vehicles.csv: %s", e)

    def resolve_by_model(self, vehicle_model: str) -> VehicleCapability:
        """
        Resolve capability by VinFast vehicle model name.

        Raises:
            UnknownVehicleModelError: If model is not recognized in the catalog.
        """
        model_normalized = vehicle_model.strip().upper()
        if model_normalized not in self._models:
            raise UnknownVehicleModelError(
                f"Unknown vehicle model '{vehicle_model}'. Must be one of: {sorted(self._models.keys())}"
            )
        return self._models[model_normalized]

    def resolve_by_vehicle_id(self, vehicle_id: str) -> VehicleCapability:
        """
        Resolve capability by fleet vehicle_id (e.g. 'V0001').

        Raises:
            UnknownVehicleError: If vehicle_id is not found.
            UnknownVehicleModelError: If vehicle's model is not recognized.
        """
        vrow = self.get_vehicle_record(vehicle_id)
        if not vrow:
            raise UnknownVehicleError(f"Unknown vehicle ID '{vehicle_id}'")

        model_name = vrow.get("vehicle_model")
        if not model_name:
            raise UnknownVehicleModelError(f"Vehicle '{vehicle_id}' has missing vehicle_model attribute")

        return self.resolve_by_model(model_name)

    def get_vehicle_record(self, vehicle_id: str) -> Optional[dict]:
        """Return raw vehicle record dict for a given vehicle_id, if known."""
        return self._vehicles.get(vehicle_id)

    def is_swap_capable_model(self, vehicle_model: str) -> bool:
        """Check whether a model supports battery swapping."""
        cap = self.resolve_by_model(vehicle_model)
        return cap.swap_supported

    def list_all_models(self) -> list[str]:
        """Return list of all registered models."""
        return sorted(self._models.keys())


# Global singleton instance
_global_resolver: Optional[VehicleCapabilityResolver] = None


def get_capability_resolver() -> VehicleCapabilityResolver:
    """Get or create singleton VehicleCapabilityResolver."""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = VehicleCapabilityResolver()
    return _global_resolver


def reset_capability_resolver():
    """Reset singleton for tests."""
    global _global_resolver
    _global_resolver = None
