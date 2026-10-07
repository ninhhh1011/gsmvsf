/**
 * Station Compatibility and Evaluation Domain Logic.
 * Filters, sorts, and checks capability match for stations and services.
 */

/**
 * Check whether a station is compatible with a vehicle's charging and battery swap capabilities.
 */
export function isStationCompatibleWithVehicle(station, vehicleSpec) {
    if (!station || !vehicleSpec) return false;
    const isMotorbike = vehicleSpec.vehicle_type === 'EV_MOTORBIKE';
    const isCar = vehicleSpec.vehicle_type === 'EV_CAR';

    const hasSwap = Boolean(station.battery_type && station.battery_type !== 'NONE' && (station.total_swap_slots || 0) > 0);
    const hasCharging = Boolean(station.connector_type && (station.total_charging_slots || 0) > 0);

    // If car, it only charges (no VinFast cars currently support battery swap)
    if (isCar) {
        if (!vehicleSpec.charging_supported || !hasCharging) return false;
        // Check connector compatibility
        const connStr = (station.connector_type || '').toUpperCase();
        return connStr.includes('CCS2') || connStr.includes('TYPE2') || connStr.includes('DC');
    }

    // If motorbike: check swap capability vs vehicle spec
    if (isMotorbike) {
        if (vehicleSpec.swap_supported && hasSwap) return true;
        if (vehicleSpec.charging_supported && hasCharging) return true;
        return false;
    }

    return hasCharging || hasSwap;
}

/**
 * Filter a list of stations according to selected filter criteria and vehicle capabilities.
 */
export function filterStations(stations, filter = 'ALL', vehicleSpec = null) {
    if (!Array.isArray(stations)) return [];
    const normalizedFilter = (filter || 'ALL').toUpperCase();

    return stations.filter(station => {
        if (vehicleSpec && !isStationCompatibleWithVehicle(station, vehicleSpec)) {
            if (normalizedFilter === 'COMPATIBLE') return false;
        }

        if (normalizedFilter === 'ALL' || normalizedFilter === 'COMPATIBLE') {
            return true;
        }

        if (normalizedFilter === 'CHARGING') {
            return (station.total_charging_slots || 0) > 0;
        }

        if (normalizedFilter === 'BATTERY_SWAP' || normalizedFilter === 'SWAP') {
            return (station.total_swap_slots || 0) > 0 && station.battery_type !== 'NONE';
        }

        return true;
    });
}

/**
 * Calculate total estimated trip detour cost for an en-route candidate.
 */
export function computeTotalCandidateCostSeconds(etaToStationS, queueWaitS, serviceDurationS, detourDurationS) {
    const travel = Math.max(0, Number(etaToStationS) || 0);
    const queue = Math.max(0, Number(queueWaitS) || 0);
    const service = Math.max(0, Number(serviceDurationS) || 0);
    const detour = Math.max(0, Number(detourDurationS) || 0);
    return Math.round(travel + queue + service + detour);
}
