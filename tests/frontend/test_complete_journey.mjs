/**
 * Complete Journey Tests: end-to-end regression coverage for the full driver playback loop.
 *
 * Covers:
 * - Test 10: Long synthetic route maintains monotonic timestamps
 * - Test 13: COMPLETE state fires exactly once when reaching destination
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { TrajectoryReplayController, ReplayState } from '../../backend/app/static/demo/js/replay.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { DriverState } from '../../backend/app/static/demo/js/domain/driver_state.js';
import { ApiError } from '../../backend/app/static/demo/js/api.js';

function mockMap() {
    return {
        renderDriver() {},
        updateDirectRoute() {},
        renderRecommendationRoute() {},
        renderDirectRoute() {},
        renderStations() {},
        clearRecommendationRoute() {},
        fitBoundsToActive() {},
        layers: { markers: { clearLayers() {} }, driver: { clearLayers() {} } }
    };
}

test('Test 10: replaying a long route maintains strictly monotonic timestamps', async () => {
    const mockApi = {
        ingestDriverLocation: async (driverId, payload) => ({
            status: 'MATCHED',
            matched_position: { latitude: payload.latitude, longitude: payload.longitude }
        }),
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());

    // Generate a long route with 50 points (simulates ~10km journey)
    const numPoints = 50;
    const startLat = 20.9849;
    const startLng = 105.7935;
    const endLat = 21.0285;
    const endLng = 105.8542;
    const startTime = new Date('2026-09-01T07:00:00Z').getTime();

    const routePoints = [];
    for (let i = 0; i <= numPoints; i++) {
        const t = i / numPoints;
        routePoints.push([
            startLat + (endLat - startLat) * t,
            startLng + (endLng - startLng) * t
        ]);
    }

    await replay.loadFromPolyline(routePoints);

    // Verify all observation timestamps are strictly monotonic
    const timestamps = replay.observations.map(o => new Date(o.timestamp).getTime());
    for (let i = 1; i < timestamps.length; i++) {
        assert.ok(
            timestamps[i] > timestamps[i - 1],
            `Observation ${i} timestamp (${timestamps[i]}) must be > previous (${timestamps[i - 1]})`
        );
    }

    // Verify timestamps span a reasonable duration (not all the same instant)
    const span = timestamps[timestamps.length - 1] - timestamps[0];
    assert.ok(span > 0, 'Timestamps should span a non-zero duration');
    assert.ok(replay.observations.length >= numPoints, 'Should have observations for each route point');
});

test('Test 13: COMPLETE state fires exactly once when reaching destination', async () => {
    const stateChanges = [];
    const mockApi = {
        ingestDriverLocation: async () => ({
            status: 'MATCHED',
            matched_position: { latitude: 21.0285, longitude: 105.8542 }
        }),
        getRecommendation: async () => ({ has_recommendation: false }),
        resetDriverLocation: async () => ({})
    };

    const mockMapWithState = {
        ...mockMap(),
        renderDriver: () => {},
    };

    const driver = new DriverModeController(mockApi, mockMapWithState);

    // Capture every state change
    const orig = driver.onStateChange.bind(driver);
    driver.onStateChange = (newState) => {
        stateChanges.push(newState);
        orig(newState);
    };

    driver.state = DriverState.TRIP_ACTIVE;
    driver.currentVehicle = {
        vehicle_id: 'V0001',
        vehicle_type: 'EV_CAR',
        usable_capacity_kwh: 17.15,
        consumption_wh_per_km: 150
    };
    driver.currentTrip = {
        trip_id: 'T0001',
        destination: { latitude: 21.0285, longitude: 105.8542 }
    };
    driver.currentPos = { latitude: 21.01, longitude: 105.81 };
    driver.replay.observations = [
        { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:00:00Z' },
        { latitude: 21.0285, longitude: 105.8542, timestamp: '2026-09-01T07:00:05Z' }
    ];
    driver.replay.state = ReplayState.READY;

    // Drive through all observations
    await driver.replay.step(false);
    await driver.replay.step(false);

    // Verify TRIP_COMPLETE fires exactly once
    const completeCount = stateChanges.filter(s => s === DriverState.TRIP_COMPLETE).length;
    assert.equal(completeCount, 1, `TRIP_COMPLETE should fire exactly once, got ${completeCount}`);
    assert.equal(driver.state, DriverState.TRIP_COMPLETE, 'Driver should end in TRIP_COMPLETE state');
});
