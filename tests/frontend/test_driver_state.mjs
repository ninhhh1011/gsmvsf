/**
 * Unit tests for Driver State machine, transition validation, and UI badges.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    DriverState,
    isValidStateTransition,
    getDriverStateLabel,
    getDriverStateBadgeClass
} from '../../backend/app/static/demo/js/domain/driver_state.js';

test('DriverState defines all canonical driver workflow states', () => {
    assert.equal(DriverState.AVAILABLE, 'AVAILABLE');
    assert.equal(DriverState.OFFLINE, 'OFFLINE');
    assert.equal(DriverState.TRIP_ASSIGNED, 'TRIP_ASSIGNED');
    assert.equal(DriverState.TO_PICKUP, 'TO_PICKUP');
    assert.equal(DriverState.ON_TRIP, 'ON_TRIP');
    assert.equal(DriverState.TRIP_ACTIVE, 'TRIP_ACTIVE');
    assert.equal(DriverState.TRIP_COMPLETE, 'TRIP_COMPLETE');
});

test('isValidStateTransition permits legitimate workflow progressions', () => {
    // Normal trip lifecycle
    assert.ok(isValidStateTransition(DriverState.AVAILABLE, DriverState.TRIP_ASSIGNED));
    assert.ok(isValidStateTransition(DriverState.TRIP_ASSIGNED, DriverState.TRIP_ACTIVE));
    assert.ok(isValidStateTransition(DriverState.TRIP_ACTIVE, DriverState.TRIP_COMPLETE));
    assert.ok(isValidStateTransition(DriverState.TRIP_COMPLETE, DriverState.AVAILABLE));

    // Online / Offline transitions
    assert.ok(isValidStateTransition(DriverState.AVAILABLE, DriverState.OFFLINE));
    assert.ok(isValidStateTransition(DriverState.OFFLINE, DriverState.AVAILABLE));

    // Pickup / On-trip transitions
    assert.ok(isValidStateTransition(DriverState.TRIP_ASSIGNED, DriverState.TO_PICKUP));
    assert.ok(isValidStateTransition(DriverState.TO_PICKUP, DriverState.ON_TRIP));
    assert.ok(isValidStateTransition(DriverState.ON_TRIP, DriverState.TRIP_COMPLETE));

    // Direct trip cancellations
    assert.ok(isValidStateTransition(DriverState.TRIP_ASSIGNED, DriverState.AVAILABLE));
    assert.ok(isValidStateTransition(DriverState.TRIP_ACTIVE, DriverState.AVAILABLE));
});

test('isValidStateTransition rejects invalid or unsafe transitions', () => {
    // Cannot start a trip when OFFLINE
    assert.equal(isValidStateTransition(DriverState.OFFLINE, DriverState.TRIP_ACTIVE), false);
    assert.equal(isValidStateTransition(DriverState.OFFLINE, DriverState.TRIP_ASSIGNED), false);

    // Cannot jump from OFFLINE directly to TRIP_COMPLETE
    assert.equal(isValidStateTransition(DriverState.OFFLINE, DriverState.TRIP_COMPLETE), false);

    // Cannot re-assign a trip without completing or returning to AVAILABLE
    assert.equal(isValidStateTransition(DriverState.TRIP_COMPLETE, DriverState.TRIP_ASSIGNED), false);

    // Invalid source or target states
    assert.equal(isValidStateTransition('INVALID_STATE', DriverState.AVAILABLE), false);
    assert.equal(isValidStateTransition(DriverState.AVAILABLE, 'NONEXISTENT'), false);
});

test('getDriverStateLabel returns meaningful human-readable labels', () => {
    assert.equal(getDriverStateLabel(DriverState.AVAILABLE), 'Sẵn sàng');
    assert.equal(getDriverStateLabel(DriverState.OFFLINE), 'Ngoại tuyến');
    assert.equal(getDriverStateLabel(DriverState.TRIP_ACTIVE), 'Đang di chuyển');
    assert.equal(getDriverStateLabel(DriverState.TRIP_COMPLETE), 'Hoàn thành');
    assert.equal(getDriverStateLabel('UNKNOWN_STATE'), 'UNKNOWN_STATE');
});

test('getDriverStateBadgeClass maps state to standard CSS badge styles', () => {
    assert.equal(getDriverStateBadgeClass(DriverState.AVAILABLE), 'badge-success');
    assert.equal(getDriverStateBadgeClass(DriverState.OFFLINE), 'badge-neutral');
    assert.equal(getDriverStateBadgeClass(DriverState.TRIP_ACTIVE), 'badge-info');
    assert.equal(getDriverStateBadgeClass(DriverState.TO_PICKUP), 'badge-warning');
    assert.equal(getDriverStateBadgeClass(DriverState.TRIP_COMPLETE), 'badge-teal');
    assert.equal(getDriverStateBadgeClass('UNKNOWN'), 'badge-neutral');
});
