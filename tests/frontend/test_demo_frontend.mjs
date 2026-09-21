/**
 * Unit tests for Demo UI Frontend Logic (Node.js native test runner).
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { ApiError } from '../../backend/app/static/demo/js/api.js';
import { decodePolyline } from '../../backend/app/static/demo/js/map.js';
import { classifyEnergyWarning } from '../../backend/app/static/demo/js/components.js';
import { DriverState } from '../../backend/app/static/demo/js/driver_mode.js';

test('ApiError sets flags correctly', () => {
    const err409 = new ApiError('Conflict', 409, 'CANDIDATE_STATE_CHANGED', { detail: 'state changed' });
    assert.equal(err409.isConflict, true);
    assert.equal(err409.status, 409);
    assert.equal(err409.code, 'CANDIDATE_STATE_CHANGED');

    const err503 = new ApiError('Outage', 503, 'ENGINE_UNAVAILABLE');
    assert.equal(err503.isEngineUnavailable, true);
    assert.equal(err503.isConflict, false);

    const err422 = new ApiError('No pos', 422, 'LOCATION_UNAVAILABLE');
    assert.equal(err422.isLocationUnavailable, true);
});

test('decodePolyline decodes standard encoded polylines', () => {
    // Standard Google polyline test vector:
    // Points: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    const encoded = '_p~iF~ps|U_ulLnnqC_mqNvxq`@';
    const coords = decodePolyline(encoded);

    assert.equal(coords.length, 3);
    assert.ok(Math.abs(coords[0][0] - 38.5) < 0.0001);
    assert.ok(Math.abs(coords[0][1] - (-120.2)) < 0.0001);
    assert.ok(Math.abs(coords[1][0] - 40.7) < 0.0001);
    assert.ok(Math.abs(coords[1][1] - (-120.95)) < 0.0001);
    assert.ok(Math.abs(coords[2][0] - 43.252) < 0.0001);
    assert.ok(Math.abs(coords[2][1] - (-126.453)) < 0.0001);

    // Empty or invalid input
    assert.deepEqual(decodePolyline(''), []);
    assert.deepEqual(decodePolyline(null), []);
});

test('classifyEnergyWarning maps backend reason codes to UX warning levels', () => {
    // 1. SAFE
    const safeResult = classifyEnergyWarning({
        need_service: false,
        reason_code: 'SUFFICIENT_SOC_RANGE'
    });
    assert.equal(safeResult.level, 'SAFE');

    // 2. CRITICAL - Destination not reachable
    const critResult1 = classifyEnergyWarning({
        need_service: true,
        reason_code: 'DESTINATION_NOT_REACHABLE',
        estimated_remaining_range_km: 8.0,
        remaining_trip_distance_km: 15.0
    });
    assert.equal(critResult1.level, 'CRITICAL');

    // 2b. CRITICAL - Range strictly less than trip distance
    const critResult2 = classifyEnergyWarning({
        need_service: true,
        reason_code: 'LOW_SOC_AND_INSUFFICIENT_RANGE',
        estimated_remaining_range_km: 5.0,
        remaining_trip_distance_km: 10.0
    });
    assert.equal(critResult2.level, 'CRITICAL');

    // 3. ADVISORY - Destination reachable, but reserve insufficient
    const advResult = classifyEnergyWarning({
        need_service: true,
        reason_code: 'INSUFFICIENT_POST_DESTINATION_RESERVE',
        estimated_remaining_range_km: 14.0,
        remaining_trip_distance_km: 10.0,
        safety_reserve_km: 5.0
    });
    assert.equal(advResult.level, 'ADVISORY');
});

test('DriverState constants are defined correctly', () => {
    assert.equal(DriverState.OFFLINE, 'OFFLINE');
    assert.equal(DriverState.AVAILABLE, 'AVAILABLE');
    assert.equal(DriverState.TRIP_ASSIGNED, 'TRIP_ASSIGNED');
    assert.equal(DriverState.TO_PICKUP, 'TO_PICKUP');
    assert.equal(DriverState.ON_TRIP, 'ON_TRIP');
    assert.equal(DriverState.TRIP_COMPLETE, 'TRIP_COMPLETE');
});
