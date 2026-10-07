/**
 * Navigation Progress and Corridor Tracking Domain Logic.
 * Computes route progress, remaining distances, and off-route reroute triggers.
 */

import { straightLineDistanceKm } from './vehicle_model.js';

export const DEFAULT_OFF_ROUTE_THRESHOLD_METERS = 80.0;
export const DEFAULT_CONSECUTIVE_OFF_ROUTE_LIMIT = 3;

/**
 * Check if vehicle's current position deviates beyond threshold from the planned route corridor.
 */
export function isPositionOffRoute(currentPos, routeCoords, thresholdMeters = DEFAULT_OFF_ROUTE_THRESHOLD_METERS) {
    if (!currentPos || !routeCoords || routeCoords.length === 0) return false;
    const lat = currentPos.latitude ?? currentPos[0];
    const lng = currentPos.longitude ?? currentPos[1];
    if (lat == null || lng == null) return false;

    let minDistanceM = Infinity;
    for (let i = 0; i < routeCoords.length; i++) {
        const pt = routeCoords[i];
        const pLat = pt.latitude ?? pt[0];
        const pLng = pt.longitude ?? pt[1];
        const distKm = straightLineDistanceKm(lat, lng, pLat, pLng);
        const distM = distKm * 1000.0;
        if (distM < minDistanceM) {
            minDistanceM = distM;
        }
    }
    return minDistanceM > thresholdMeters;
}

/**
 * Determine whether consecutive off-route detections warrant a route recalculation.
 */
export function shouldTriggerReroute(consecutiveOffRouteCount, limit = DEFAULT_CONSECUTIVE_OFF_ROUTE_LIMIT) {
    return (consecutiveOffRouteCount || 0) >= limit;
}

/**
 * Calculate remaining distance along a polyline from vehicle's progress index.
 */
export function calculateRemainingPolylineDistanceKm(coords, startIndex = 0) {
    if (!coords || coords.length <= 1 || startIndex >= coords.length - 1) return 0.0;
    let totalKm = 0.0;
    for (let i = Math.max(0, startIndex); i < coords.length - 1; i++) {
        const p1 = coords[i];
        const p2 = coords[i + 1];
        const lat1 = p1.latitude ?? p1[0];
        const lng1 = p1.longitude ?? p1[1];
        const lat2 = p2.latitude ?? p2[0];
        const lng2 = p2.longitude ?? p2[1];
        totalKm += straightLineDistanceKm(lat1, lng1, lat2, lng2);
    }
    return Math.round(totalKm * 10) / 10;
}
