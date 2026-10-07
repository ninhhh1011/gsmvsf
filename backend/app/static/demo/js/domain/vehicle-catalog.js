/**
 * Vehicle Catalog Client — Domain Logic.
 * Fetches catalog from backend API. Pure fetch logic, no DOM.
 */

import { MODEL_SPECS, registerVehicleModel } from './vehicle_model.js';

/** @type {Array|null} Cached catalog response */
let _catalogCache = null;

/**
 * Fetch vehicle catalog from GET /api/v1/vehicles/catalog.
 * Returns the JSON array or throws on failure.
 */
export async function fetchVehicleCatalog() {
    const response = await fetch('/api/v1/vehicles/catalog');
    if (!response.ok) throw new Error(`Vehicle catalog fetch failed: HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data)) {
        throw new Error('Vehicle catalog did not return an array');
    }
    _catalogCache = data;
    for (const key of Object.keys(MODEL_SPECS)) delete MODEL_SPECS[key];

    // Auto-register each catalog entry into MODEL_SPECS for consistency
    for (const item of data) {
        registerVehicleModel(item.id, {
            name: item.name,
            brand: item.brand,
            battery_kwh: item.battery_kwh,
            consumption_kwh_per_km: item.efficiency_kwh_per_km,
            vehicle_type: item.vehicle_type,
            charging_supported: item.supported_services?.includes('charging'),
            swap_supported: item.supported_services?.includes('battery_swap'),
        });
    }

    return data;
}

/**
 * Get the cached catalog (must call fetchVehicleCatalog first).
 */
export function getCachedCatalog() {
    return _catalogCache;
}

/**
 * Clear the catalog cache (for testing).
 */
export function clearCatalogCache() {
    _catalogCache = null;
}
