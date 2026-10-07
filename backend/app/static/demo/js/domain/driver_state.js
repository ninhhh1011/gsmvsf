/**
 * Driver Cockpit State Machine Domain Logic.
 * Deterministic, testable state definitions and transition validation.
 */

export const DriverState = {
    OFFLINE: 'OFFLINE',
    AVAILABLE: 'AVAILABLE',
    TRIP_ASSIGNED: 'TRIP_ASSIGNED',
    TO_PICKUP: 'TO_PICKUP',
    ON_TRIP: 'ON_TRIP',
    TRIP_ACTIVE: 'TRIP_ACTIVE',
    TRIP_COMPLETE: 'TRIP_COMPLETE'
};

const VALID_TRANSITIONS = {
    [DriverState.OFFLINE]: [DriverState.AVAILABLE],
    [DriverState.AVAILABLE]: [DriverState.OFFLINE, DriverState.TRIP_ASSIGNED],
    [DriverState.TRIP_ASSIGNED]: [DriverState.AVAILABLE, DriverState.TRIP_ACTIVE, DriverState.TO_PICKUP, DriverState.OFFLINE],
    [DriverState.TO_PICKUP]: [DriverState.AVAILABLE, DriverState.ON_TRIP, DriverState.TRIP_ACTIVE],
    [DriverState.ON_TRIP]: [DriverState.AVAILABLE, DriverState.TRIP_COMPLETE],
    [DriverState.TRIP_ACTIVE]: [DriverState.AVAILABLE, DriverState.TRIP_COMPLETE],
    [DriverState.TRIP_COMPLETE]: [DriverState.AVAILABLE, DriverState.OFFLINE]
};

/**
 * Validate whether a state transition from currentState to targetState is permitted.
 */
export function isValidStateTransition(currentState, targetState) {
    if (!currentState || !targetState) return false;
    if (currentState === targetState) return true;
    const allowed = VALID_TRANSITIONS[currentState];
    return Array.isArray(allowed) && allowed.includes(targetState);
}

/**
 * Get human-readable localized label for driver state badge.
 */
export function getDriverStateLabel(state) {
    switch (state) {
        case DriverState.OFFLINE: return 'Ngoại tuyến';
        case DriverState.AVAILABLE: return 'Sẵn sàng';
        case DriverState.TRIP_ASSIGNED: return 'Đã nhận cuốc';
        case DriverState.TO_PICKUP: return 'Đón khách';
        case DriverState.ON_TRIP: return 'Đang chở khách';
        case DriverState.TRIP_ACTIVE: return 'Đang di chuyển';
        case DriverState.TRIP_COMPLETE: return 'Hoàn thành';
        default: return state || 'Không xác định';
    }
}

/**
 * Get CSS badge styling class for state.
 */
export function getDriverStateBadgeClass(state) {
    switch (state) {
        case DriverState.OFFLINE: return 'badge-neutral';
        case DriverState.AVAILABLE: return 'badge-success';
        case DriverState.TRIP_ASSIGNED: return 'badge-purple';
        case DriverState.TO_PICKUP: return 'badge-warning';
        case DriverState.ON_TRIP:
        case DriverState.TRIP_ACTIVE: return 'badge-info';
        case DriverState.TRIP_COMPLETE: return 'badge-teal';
        default: return 'badge-neutral';
    }
}
