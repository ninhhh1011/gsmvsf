# VINFAST VEHICLE CAPABILITY SOURCES

**Status:** Domain Correction Patch — Dataset V1.3

This document distinguishes official VinFast specifications from project simulation assumptions.

## Official VinFast Specifications (from domain data)

| vehicle_model | vehicle_category | charging_supported | swap_supported | battery_capacity_kwh | battery_module_kwh | max_modules | source |
|---|---|---|---|---|---|---|---|
| VF_3 | EV_CAR | true | false | 18.64 | — | — | VINFAST_OFFICIAL |
| VF_5 | EV_CAR | true | false | 37.23 | — | — | VINFAST_OFFICIAL |
| HERIO_GREEN | EV_CAR | true | false | 37.23 | — | — | VINFAST_OFFICIAL |
| VF_6 | EV_CAR | true | false | 59.60 | — | — | VINFAST_OFFICIAL |
| VF_7_ECO | EV_CAR | true | false | 59.60 | — | — | VINFAST_OFFICIAL |
| VF_7_PLUS | EV_CAR | true | false | 75.30 | — | — | VINFAST_OFFICIAL |
| VF_8 | EV_CAR | true | false | 87.70 | — | — | VINFAST_OFFICIAL |
| VF_9 | EV_CAR | true | false | 123.00 | — | — | VINFAST_OFFICIAL |
| VF_E34 | EV_CAR | true | false | 41.90 | — | — | VINFAST_OFFICIAL |
| NERIO_GREEN | EV_CAR | true | false | 41.90 | — | — | VINFAST_OFFICIAL |
| EVO200 | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| EVO200_LITE | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| FELIZ_S | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| KLARA_S_2022 | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| VENTO_S | EV_MOTORBIKE | true | false | 3.50 | — | — | VINFAST_OFFICIAL |
| EVO | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| EVO_LITE | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| FELIZ_II | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |
| VIPER | EV_MOTORBIKE | true | true | 1.5 or 3.0 | 1.50 | 2 | VINFAST_OFFICIAL |

**Important:** swap_supported=true models (EVO, EVO_LITE, FELIZ_II, VIPER) have a REMOVABLE_SWAP_MODULE
battery architecture. Their total nominal capacity depends on `installed_battery_modules` (1 or 2).
The vehicle does NOT always have 2 modules installed.

## Project Simulation Assumptions

The following values are PROJECT SIMULATION ASSUMPTIONS. They are NOT official VinFast specifications.

| Field | Value | Rationale |
|---|---|---|
| usable_capacity_ratio | 0.92 (92%) | Applied uniformly to all models. Deterministic synthetic assumption. |
| consumption_wh_per_km (cars) | 150 Wh/km | Consistent with V1.2; plausible for VinFast EV fleet. |
| consumption_wh_per_km (bikes) | 45 Wh/km | Consistent with V1.2; plausible for VinFast electric motorcycles. |
| minimum_safe_soc_pct | 15% | Consistent with V1.2; safety reserve threshold. |
| charging_interface_class (cars) | CCS2_TYPE2 | Standard European CCS2 / Type 2 AC. |
| charging_interface_class (bikes) | VINFAST_MOTORCYCLE_CHARGING | Project-internal normalized name for VinFast motorcycle AC charging. |
| swap_battery_family | VINFAST_SWAP_LFP_1_5_KWH | Project-internal normalized name. Not an official VinFast product name. |
| battery_architecture categories | FIXED_TRACTION_PACK / FIXED_OR_INTEGRATED_LFP / REMOVABLE_SWAP_MODULE | Project-internal taxonomy for modeling battery types. |

## Key Modeling Rules (V1.3)

1. **charging_supported ≠ swap_supported.** A vehicle can support charging without supporting swap.
2. **battery_removable ≠ public_swap_compatible.** Physical battery removability is not modeled separately here.
   The `public_swap_compatible` flag specifically means the vehicle is compatible with the VinFast public battery-swap network.
3. **swap_capable vehicles support CHARGING.** EVO/EVO_LITE/FELIZ_II/VIPER can also charge normally.
4. **Battery capacity for swap models:** `nominal_kwh = installed_battery_modules × 1.5 kWh`
   - 1 module: 1.5 kWh nominal → ~1.38 kWh usable
   - 2 modules: 3.0 kWh nominal → ~2.76 kWh usable
5. **No vehicle in the fleet is swap-only.** All VinFast vehicles that support swap also support charging.
