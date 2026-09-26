/**
 * Unit tests for Demo UI Frontend Logic (Node.js native test runner).
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { ApiError } from '../../backend/app/static/demo/js/api.js';
import {
    decodePolyline,
    haversineDistanceMeters,
    computePolylineDistanceMeters,
    projectPointOnSegment,
    projectPointOnRoute,
    sliceRouteFromProgress,
    simplifyTrajectoryRDP
} from '../../backend/app/static/demo/js/map.js';
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

test('haversineDistanceMeters and computePolylineDistanceMeters calculate accurate distance', () => {
    // Distance between (21.0, 105.0) and (21.0, 105.01) is approx 1039 meters
    const dist = haversineDistanceMeters(21.0, 105.0, 21.0, 105.01);
    assert.ok(dist > 1000 && dist < 1100);
    assert.equal(haversineDistanceMeters(21.0, 105.0, 21.0, 105.0), 0);

    const polyDist = computePolylineDistanceMeters([
        [21.0, 105.0],
        [21.0, 105.01],
        [21.0, 105.02]
    ]);
    assert.ok(polyDist > 2000 && polyDist < 2200);
});

test('projectPointOnRoute and sliceRouteFromProgress slice route along vehicle progress', () => {
    const route = [
        [21.0, 105.0],
        [21.0, 105.01],
        [21.0, 105.02],
        [21.0, 105.03]
    ];

    // Car is near the midpoint of segment 1: (21.0001, 105.015)
    const carPos = { latitude: 21.0001, longitude: 105.015 };
    const progress = projectPointOnRoute(carPos, route, 0);

    assert.equal(progress.segmentIndex, 1);
    assert.ok(progress.distanceMeters < 25); // Close to segment
    assert.ok(Math.abs(progress.projPoint[0] - 21.0) < 0.001);
    assert.ok(Math.abs(progress.projPoint[1] - 105.015) < 0.001);

    // Slice route from progress
    const remaining = sliceRouteFromProgress(route, progress);
    assert.equal(remaining.length, 3); // projPoint, point 2, point 3
    assert.deepEqual(remaining[1], [21.0, 105.02]);
    assert.deepEqual(remaining[2], [21.0, 105.03]);

    // When progress reaches the end
    const endProgress = { segmentIndex: 3, projPoint: [21.0, 105.03], distanceMeters: 0 };
    const atEnd = sliceRouteFromProgress(route, endProgress);
    assert.equal(atEnd.length, 1);
    assert.deepEqual(atEnd[0], [21.0, 105.03]);
});

test('simplifyTrajectoryRDP reduces jitter and preserves key corridor inflection waypoints', () => {
    // 10 collinear points along a road, with 1 major turnaround point at index 5
    const pts = [
        { latitude: 21.000, longitude: 105.000 },
        { latitude: 21.001, longitude: 105.001 },
        { latitude: 21.002, longitude: 105.002 },
        { latitude: 21.003, longitude: 105.003 },
        { latitude: 21.004, longitude: 105.004 },
        { latitude: 21.010, longitude: 105.020 }, // Turnaround detour > 1km away
        { latitude: 21.004, longitude: 105.004 },
        { latitude: 21.003, longitude: 105.003 },
        { latitude: 21.002, longitude: 105.002 },
        { latitude: 21.000, longitude: 105.000 }
    ];

    const simplified = simplifyTrajectoryRDP(pts, 200);
    // Should preserve start, peak, and end
    assert.equal(simplified.length, 3);
    assert.equal(simplified[0].latitude, 21.000);
    assert.equal(simplified[1].latitude, 21.010);
    assert.equal(simplified[2].latitude, 21.000);
});
