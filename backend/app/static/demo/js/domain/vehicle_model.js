/**
 * Vehicle Energy and Physics Depletion Domain Logic.
 * Testable in isolation without DOM or browser environment.
 */

export const EARTH_RADIUS_KM = 6371.0;

export function toRad(deg) {
    return deg * Math.PI / 180;
}

/**
 * Compute great-circle distance between two coordinates in kilometers.
 */
export function straightLineDistanceKm(lat1, lng1, lat2, lng2) {
    if (lat1 == null || lng1 == null || lat2 == null || lng2 == null) return 0.0;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
        + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2))
        * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return EARTH_RADIUS_KM * c;
}

/**
 * Standard vehicle models catalog with battery & consumption specifications.
 * Supports VinFast, BYD, Tesla, Hyundai, and custom EV brands.
 */
export const FALLBACK_MODEL_SPECS = {
    // --- VinFast EV Cars ---
    'VF_3': { vehicle_model: 'VF_3', brand: 'VinFast', display_name: 'VF 3', vehicle_type: 'EV_CAR', usable_kwh: 17.15, consumption_wh_km: 95.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 30.0, curb_weight_kg: 857, drag_coefficient: 0.36, frontal_area_m2: 2.15 },
    'VF_5': { vehicle_model: 'VF_5', brand: 'VinFast', display_name: 'VF 5', vehicle_type: 'EV_CAR', usable_kwh: 34.25, consumption_wh_km: 125.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 100.0, curb_weight_kg: 1360, drag_coefficient: 0.32, frontal_area_m2: 2.30 },
    'HERIO_GREEN': { vehicle_model: 'HERIO_GREEN', brand: 'VinFast', display_name: 'Herio Green', vehicle_type: 'EV_CAR', usable_kwh: 34.25, consumption_wh_km: 125.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 100.0, curb_weight_kg: 1360, drag_coefficient: 0.32, frontal_area_m2: 2.30 },
    'VF_6': { vehicle_model: 'VF_6', brand: 'VinFast', display_name: 'VF 6', vehicle_type: 'EV_CAR', usable_kwh: 54.83, consumption_wh_km: 145.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 150.0, curb_weight_kg: 1800, drag_coefficient: 0.31, frontal_area_m2: 2.40 },
    'VF_7_ECO': { vehicle_model: 'VF_7_ECO', brand: 'VinFast', display_name: 'VF 7 Eco', vehicle_type: 'EV_CAR', usable_kwh: 54.83, consumption_wh_km: 155.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 130.0, curb_weight_kg: 1950, drag_coefficient: 0.30, frontal_area_m2: 2.48 },
    'VF_7_PLUS': { vehicle_model: 'VF_7_PLUS', brand: 'VinFast', display_name: 'VF 7 Plus', vehicle_type: 'EV_CAR', usable_kwh: 69.28, consumption_wh_km: 170.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 260.0, curb_weight_kg: 2100, drag_coefficient: 0.30, frontal_area_m2: 2.48 },
    'VF_8': { vehicle_model: 'VF_8', brand: 'VinFast', display_name: 'VF 8', vehicle_type: 'EV_CAR', usable_kwh: 80.68, consumption_wh_km: 195.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 300.0, curb_weight_kg: 2600, drag_coefficient: 0.31, frontal_area_m2: 2.60 },
    'VF_9': { vehicle_model: 'VF_9', brand: 'VinFast', display_name: 'VF 9', vehicle_type: 'EV_CAR', usable_kwh: 113.16, consumption_wh_km: 235.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 300.0, curb_weight_kg: 2880, drag_coefficient: 0.32, frontal_area_m2: 2.85 },
    'VF_E34': { vehicle_model: 'VF_E34', brand: 'VinFast', display_name: 'VF e34', vehicle_type: 'EV_CAR', usable_kwh: 38.55, consumption_wh_km: 135.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 110.0, curb_weight_kg: 1490, drag_coefficient: 0.32, frontal_area_m2: 2.35 },
    'NERIO_GREEN': { vehicle_model: 'NERIO_GREEN', brand: 'VinFast', display_name: 'Nerio Green', vehicle_type: 'EV_CAR', usable_kwh: 38.55, consumption_wh_km: 135.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 110.0, curb_weight_kg: 1490, drag_coefficient: 0.32, frontal_area_m2: 2.35 },
    // --- VinFast EV Motorbikes ---
    'EVO200': { vehicle_model: 'EVO200', brand: 'VinFast', display_name: 'Evo200 [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 40.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'EVO_200': { vehicle_model: 'EVO200', brand: 'VinFast', display_name: 'Evo200 [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 40.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'EVO200_LITE': { vehicle_model: 'EVO200_LITE', brand: 'VinFast', display_name: 'Evo200 Lite [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 40.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'FELIZ_S': { vehicle_model: 'FELIZ_S', brand: 'VinFast', display_name: 'Feliz S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 42.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 3.0, curb_weight_kg: 110, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'KLARA_S_2022': { vehicle_model: 'KLARA_S_2022', brand: 'VinFast', display_name: 'Klara S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 45.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 3.0, curb_weight_kg: 112, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'KLARA_S': { vehicle_model: 'KLARA_S_2022', brand: 'VinFast', display_name: 'Klara S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 45.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 3.0, curb_weight_kg: 112, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'VENTO_S': { vehicle_model: 'VENTO_S', brand: 'VinFast', display_name: 'Vento S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 45.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 5.2, curb_weight_kg: 122, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'EVO': { vehicle_model: 'EVO', brand: 'VinFast', display_name: 'Evo [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 2.76, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'EVO_LITE': { vehicle_model: 'EVO_LITE', brand: 'VinFast', display_name: 'Evo Lite [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 1.38, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'FELIZ_II': { vehicle_model: 'FELIZ_II', brand: 'VinFast', display_name: 'Feliz II [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 2.76, consumption_wh_km: 40.0, charging_supported: true, swap_supported: true, max_motor_power_kw: 3.0, curb_weight_kg: 110, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    'VIPER': { vehicle_model: 'VIPER', brand: 'VinFast', display_name: 'Viper [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 1.38, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true, max_motor_power_kw: 2.5, curb_weight_kg: 100, drag_coefficient: 0.55, frontal_area_m2: 0.70 },
    // --- Multi-Brand EV Extensions (BYD, Tesla, Hyundai, Dat Bike) ---
    'BYD_ATTO_3': { vehicle_model: 'BYD_ATTO_3', brand: 'BYD', display_name: 'BYD Atto 3', vehicle_type: 'EV_CAR', usable_kwh: 58.00, consumption_wh_km: 156.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 150.0, curb_weight_kg: 1750, drag_coefficient: 0.29, frontal_area_m2: 2.45 },
    'TESLA_MODEL_3': { vehicle_model: 'TESLA_MODEL_3', brand: 'Tesla', display_name: 'Tesla Model 3', vehicle_type: 'EV_CAR', usable_kwh: 75.00, consumption_wh_km: 144.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 208.0, curb_weight_kg: 1760, drag_coefficient: 0.23, frontal_area_m2: 2.22 },
    'HYUNDAI_IONIQ_5': { vehicle_model: 'HYUNDAI_IONIQ_5', brand: 'Hyundai', display_name: 'Hyundai Ioniq 5', vehicle_type: 'EV_CAR', usable_kwh: 70.00, consumption_wh_km: 165.0, charging_supported: true, swap_supported: false, max_motor_power_kw: 160.0, curb_weight_kg: 1910, drag_coefficient: 0.288, frontal_area_m2: 2.55 },
    'DAT_BIKE_WEAVER': { vehicle_model: 'DAT_BIKE_WEAVER', brand: 'Dat Bike', display_name: 'Dat Bike Weaver++ [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 4.80, consumption_wh_km: 35.0, charging_supported: true, swap_supported: true, max_motor_power_kw: 7.0, curb_weight_kg: 130, drag_coefficient: 0.55, frontal_area_m2: 0.70 }
};

// Mutable catalog registry allowing dynamic additions at runtime
export const MODEL_SPECS = { ...FALLBACK_MODEL_SPECS };

// Backward compatibility alias for existing consumers
export const VINFAST_MODEL_SPECS = MODEL_SPECS;

/**
 * Register or update an EV model specification dynamically.
 */
export function registerVehicleModel(modelKey, spec) {
    if (!modelKey || !spec) return;
    const usableKwh = Number(spec.usable_kwh ?? spec.battery_kwh) || 30.0;
    const consumptionWhKm = spec.consumption_wh_km != null 
        ? Number(spec.consumption_wh_km) 
        : ((Number(spec.consumption_kwh_per_km) || 0.15) * 1000.0);
    const vehicleType = spec.vehicle_type || spec.category || 'EV_CAR';
    const brand = spec.brand || 'Other';
    const name = spec.name || spec.display_name || modelKey;

    MODEL_SPECS[modelKey] = {
        ...spec,
        max_motor_power_kw: spec.max_motor_power_kw ?? null,
        vehicle_model: modelKey,
        brand,
        name,
        display_name: name,
        vehicle_type: vehicleType,
        category: vehicleType,
        usable_kwh: usableKwh,
        battery_kwh: usableKwh,
        consumption_wh_km: consumptionWhKm,
        consumption_kwh_per_km: consumptionWhKm / 1000.0,
        charging_supported: spec.charging_supported !== false,
        swap_supported: Boolean(spec.swap_supported)
    };
}

/**
 * Get model spec with fallback.
 */
export function getVehicleModelSpec(modelKey, defaultKey = 'VF_3') {
    const spec = (modelKey && MODEL_SPECS[modelKey]) || MODEL_SPECS[defaultKey] || Object.values(MODEL_SPECS)[0];
    if (spec && !spec.name) {
        spec.name = spec.display_name || spec.vehicle_model;
        spec.battery_kwh = spec.usable_kwh;
        spec.category = spec.vehicle_type;
        spec.consumption_kwh_per_km = (spec.consumption_wh_km || 120.0) / 1000.0;
    }
    return spec;
}

/**
 * Calculate estimated remaining range in kilometers based on battery capacity, consumption, and SOC.
 * Supports:
 *   calculateEstimatedRangeKm(usableKwh, consumptionWhKm, socPct)
 *   calculateEstimatedRangeKm(socPct, modelSpec)
 */
export function calculateEstimatedRangeKm(arg1, arg2, arg3) {
    let usable, consumption, soc;
    if (typeof arg2 === 'object' && arg2 !== null) {
        soc = Number(arg1) || 0;
        usable = Number(arg2.usable_kwh ?? arg2.battery_kwh) || 30;
        consumption = Number(arg2.consumption_wh_km ?? ((arg2.consumption_kwh_per_km || 0.15) * 1000)) || 120;
    } else {
        usable = Math.max(0, Number(arg1) || 0);
        consumption = Math.max(1, Number(arg2) || 120);
        soc = Number(arg3) || 0;
    }
    const clampedSoc = Math.max(0, Math.min(100, soc));
    if (clampedSoc <= 0) return 0;
    const range = (usable * 1000.0 * (clampedSoc / 100.0)) / consumption;
    return Math.max(0, Math.round(range * 10) / 10);
}

/**
 * Calculate physics-based SOC percentage drop for a given distance traveled.
 * Supports:
 *   calculateSocDepletion(distanceKm, consumptionWhKm, usableKwh)
 *   calculateSocDepletion(distanceKm, modelSpec)
 */
export function calculateSocDepletion(arg1, arg2, arg3) {
    const dist = Math.max(0, Number(arg1) || 0);
    if (dist <= 0) return 0;
    let consumption, usable;
    if (typeof arg2 === 'object' && arg2 !== null) {
        usable = Number(arg2.usable_kwh ?? arg2.battery_kwh) || 30;
        consumption = Number(arg2.consumption_wh_km ?? ((arg2.consumption_kwh_per_km || 0.15) * 1000)) || 120;
    } else {
        consumption = Math.max(1, Number(arg2) || 120);
        usable = Math.max(0.1, Number(arg3) || 1);
    }
    const energyUsedKwh = (dist * consumption) / 1000.0;
    const socDropPct = (energyUsedKwh / usable) * 100.0;
    return Math.max(0, socDropPct);
}
