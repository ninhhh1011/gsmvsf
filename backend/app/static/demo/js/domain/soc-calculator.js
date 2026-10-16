/**
 * SOC (State of Charge) Calculator — Domain Logic.
 * Pure computation, no DOM, no browser APIs.
 * ponytail: shared formula kept here so all callers sync — pull into API if more backends need it.
 */

import { calculateEstimatedRangeKm, calculateSocDepletion } from './vehicle_model.js';

/**
 * Clamp SOC percentage to [min, max].
 */
export function clampSoc(socPct, min = 0, max = 100) {
    return Math.min(max, Math.max(min, parseFloat(socPct) || 0));
}

/**
 * Compute remaining range in km from vehicle specs + SOC.
 * Supports: (socPct, modelSpec) or (usableKwh, consumptionWhKm, socPct).
 */
export function computeRangeKm(socPct, specOrKwh, consumptionWhKm) {
    if (typeof specOrKwh === 'object' && specOrKwh !== null) {
        return calculateEstimatedRangeKm(socPct, specOrKwh);
    }
    return calculateEstimatedRangeKm(socPct, specOrKwh, consumptionWhKm);
}

/**
 * Compute SOC drop percentage for a given distance traveled.
 * Supports: (distanceKm, modelSpec) or (distanceKm, consumptionWhKm, usableKwh).
 */
export function computeSocDrop(distanceKm, specOrConsumption, usableKwh) {
    if (typeof specOrConsumption === 'object' && specOrConsumption !== null) {
        return calculateSocDepletion(distanceKm, specOrConsumption);
    }
    return calculateSocDepletion(distanceKm, specOrConsumption, usableKwh);
}

/**
 * Determine energy warning level based on estimated range and safety reserve.
 * Returns: 'CRITICAL' | 'LOW' | 'WARNING' | 'NORMAL'.
 */
export function classifyEnergyWarning(estimatedRangeKm, safetyReserveKm = 2.0) {
    const threshold = safetyReserveKm;
    if (estimatedRangeKm < threshold) return 'CRITICAL';
    if (estimatedRangeKm < threshold * 2) return 'LOW';
    if (estimatedRangeKm < 30) return 'WARNING';
    return 'NORMAL';
}

/**
 * SOC color for UI: red/yellow/green based on percentage.
 */
export function socColor(socPct) {
    if (socPct < 20) return '#ef4444';
    if (socPct < 30) return '#f59e0b';
    return '#10b981';
}
