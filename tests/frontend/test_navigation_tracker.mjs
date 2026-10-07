/**
 * Unit tests for Navigation Tracker domain logic.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    isPositionOffRoute,
    shouldTriggerReroute,
    calculateRemainingPolylineDistanceKm,
    DEFAULT_OFF_ROUTE_THRESHOLD_METERS,
    DEFAULT_CONSECUTIVE_OFF_ROUTE_LIMIT
} from '../../backend/app/static/demo/js/domain/navigation_tracker.js';

test('isPositionOffRoute correctly distinguishes on-route vs off-route positions', () => {
    // Corridor along longitude 105.80
    const routeCoords = [
        [21.000, 105.800],
        [21.010, 105.800],
        [21.020, 105.800]
    ];

    // Point exactly on corridor: distance 0m => false (not off route)
    assert.equal(isPositionOffRoute({ latitude: 21.010, longitude: 105.800 }, routeCoords), false);

    // Point slightly shifted by ~20m (< 80m threshold) => false
    assert.equal(isPositionOffRoute({ latitude: 21.010, longitude: 105.8002 }, routeCoords), false);

    // Point far away (> 500m) => true (is off route)
    assert.equal(isPositionOffRoute({ latitude: 21.010, longitude: 105.810 }, routeCoords), true);

    // Empty route returns false
    assert.equal(isPositionOffRoute({ latitude: 21.0, longitude: 105.0 }, []), false);
});

test('shouldTriggerReroute enforces sample count hysteresis limit', () => {
    // Default limit is 3 consecutive off-route detections
    assert.equal(DEFAULT_CONSECUTIVE_OFF_ROUTE_LIMIT, 3);

    // 1 detection does not trigger
    assert.equal(shouldTriggerReroute(1), false);

    // 2 detections do not trigger
    assert.equal(shouldTriggerReroute(2), false);

    // 3 detections trigger reroute
    assert.equal(shouldTriggerReroute(3), true);

    // 4 detections trigger reroute
    assert.equal(shouldTriggerReroute(4), true);

    // Custom limit
    assert.equal(shouldTriggerReroute(2, 2), true);
});

test('calculateRemainingPolylineDistanceKm correctly computes remaining distance from sliced path', () => {
    // 3 points in a line: each leg is ~111 km (1 degree latitude)
    const coords = [
        [21.0, 105.0],
        [22.0, 105.0],
        [23.0, 105.0]
    ];

    const dist = calculateRemainingPolylineDistanceKm(coords, 0);
    assert.ok(dist > 200, `Expected remaining distance > 200 km, got ${dist}`);

    // From middle point (index 1), remaining is 1 degree (~111 km)
    const distMiddle = calculateRemainingPolylineDistanceKm(coords, 1);
    assert.ok(distMiddle > 100 && distMiddle < 120, `Expected ~111 km, got ${distMiddle}`);

    // If at last point (index 2), remaining is 0
    assert.equal(calculateRemainingPolylineDistanceKm(coords, 2), 0);

    // Empty or single coordinate returns 0
    assert.equal(calculateRemainingPolylineDistanceKm([], 0), 0);
    assert.equal(calculateRemainingPolylineDistanceKm([[21.0, 105.0]], 0), 0);
});
