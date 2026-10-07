/**
 * Route Display Helpers — Domain Logic.
 * Pure computation, no DOM, no browser APIs.
 */

import { straightLineDistanceKm } from './vehicle_model.js';

/**
 * Escape a string for safe HTML insertion via textContent.
 * Use this before setting innerText/textContent.
 */
export function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

/**
 * Format a distance in km for display.
 */
export function formatDistanceKm(distKm, decimals = 1) {
    if (distKm == null) return '—';
    if (distKm < 1) {
        return `${Math.round(distKm * 1000)} m`;
    }
    return `${distKm.toFixed(decimals)} km`;
}

/**
 * Format a duration in seconds to human-readable string.
 */
export function formatDuration(s, decimals = 0) {
    if (s == null || s < 0) return '—';
    const mins = Math.floor(s / 60);
    const secs = Math.round(s % 60);
    if (mins >= 60) {
        const hrs = Math.floor(mins / 60);
        const remMins = mins % 60;
        return `${hrs}h ${remMins}m`;
    }
    if (decimals > 0 && secs > 0) {
        return `${mins}.${Math.round(secs / (60 / Math.pow(10, decimals)))}m`;
    }
    return secs > 0 && mins === 0 ? `${secs}s` : `${mins}m`;
}

/**
 * Compute straight-line distance from current position to a station.
 * Returns distance in km.
 */
export function distanceToStationKm(currentPos, station) {
    if (!currentPos || !station) return 0;
    return straightLineDistanceKm(
        currentPos.latitude, currentPos.longitude,
        station.latitude, station.longitude
    );
}

/**
 * Format coordinates for display.
 */
export function formatCoords(lat, lng, decimals = 4) {
    if (lat == null || lng == null) return '—';
    return `${lat.toFixed(decimals)}, ${lng.toFixed(decimals)}`;
}

/**
 * Format ETA in minutes from seconds.
 */
export function formatEtaMin(etaSeconds) {
    if (etaSeconds == null) return '—';
    return `${(etaSeconds / 60).toFixed(0)} phút`;
}
