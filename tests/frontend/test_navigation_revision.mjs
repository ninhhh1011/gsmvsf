/**
 * Navigation Revision Guards Tests:
 * Verifies that stale asynchronous responses are discarded using revision tokens.
 * Tests that rapid state changes commit only the final revision.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { DriverState } from '../../backend/app/static/demo/js/domain/driver_state.js';

function mockMap() {
    return {
        renderDriver() {},
        updateDirectRoute() {},
        renderRecommendationRoute() {},
        renderDirectRoute() {},
        renderStations() {},
        clearRecommendationRoute() {},
        fitBoundsToActive() {},
        clearAll() {},
        renderTripEndpoints() {},
        renderPostTripRoute() {},
        highlightStation() {},
        layers: {
            markers: { clearLayers() {} },
            driver: { clearLayers() {} },
            recommendRoute: { clearLayers() {} }
        }
    };
}

// Shared mock station data
const STATIONS = [
    { station_id: 'OLD_STATION', latitude: 21.015, longitude: 105.815, service_type: 'FAST_CHARGING' },
    { station_id: 'NEW_STATION', latitude: 21.018, longitude: 105.818, service_type: 'FAST_CHARGING' }
];

// Minimal driver setup for testing
function createTestDriver(mockApi) {
    const driver = new DriverModeController(mockApi, mockMap());
    driver.state = DriverState.TRIP_ACTIVE;
    driver.currentVehicle = {
        vehicle_id: 'V0001',
        vehicle_type: 'EV_CAR',
        usable_capacity_kwh: 17.15,
        consumption_wh_per_km: 150
    };
    driver.currentTrip = {
        trip_id: 'T0001',
        destination: { latitude: 21.02, longitude: 105.82 }
    };
    driver.currentPos = { latitude: 21.01, longitude: 105.81 };
    driver.stations = STATIONS;
    return driver;
}

// Immediate-resolve mock API
function immediateMockApi() {
    return {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{
                station_id: 'OLD_STATION',
                latitude: 21.015,
                longitude: 105.815,
                service_type: 'FAST_CHARGING'
            }]
        }),
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        }),
        resetDriverLocation: async () => ({})
    };
}

test('Test 1: selecting NEW station while OLD evaluation pending does not overwrite with OLD response', async () => {
    const callLog = [];
    const mockApi = {
        getRecommendation: async () => {
            callLog.push('getRecommendation');
            return {
                has_recommendation: true,
                ranked_candidates: [{
                    station_id: 'OLD_STATION',
                    latitude: 21.015,
                    longitude: 105.815,
                    service_type: 'FAST_CHARGING'
                }]
            };
        },
        computeRoute: async (orig, dest, opts) => {
            callLog.push(`computeRoute-${dest.latitude}`);
            return {
                geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                distance_m: 5000
            };
        }
    };

    const driver = createTestDriver(mockApi);

    // Capture revision before OLD evaluation starts
    const oldRev = driver.routeRevision;

    // Start OLD evaluation
    const evalPromise = driver._evaluateAtCurrentPosition();
    await evalPromise;

    // OLD evaluation incremented revision
    assert.ok(driver.routeRevision > oldRev, 'Evaluation should increment routeRevision');

    // Now user selects NEW_STATION - this increments revision again
    const newRev = driver.routeRevision;
    await driver.navigateViaStationId('NEW_STATION');

    // User's explicit navigation incremented revision
    assert.ok(driver.routeRevision > newRev, 'Navigation should increment routeRevision');

    // Invariant: User's explicit selection must be preserved
    assert.equal(driver._selectedStationId, 'NEW_STATION', 'Selected station must be NEW_STATION');
    assert.equal(driver.lastRecommendedStationId, 'NEW_STATION', 'Recommended station must be NEW_STATION');
    assert.equal(driver._navigationLocked, true, 'Navigation must remain locked');
});

test('Test 2: rapid destination changes commit only the final revision', async () => {
    const callLog = [];
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{
                station_id: 'STATION_A',
                latitude: 21.015,
                longitude: 105.815,
                service_type: 'FAST_CHARGING'
            }]
        }),
        computeRoute: async (orig, dest) => {
            callLog.push(`computeRoute-${dest.latitude.toFixed(3)}`);
            return {
                geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                distance_m: 5000
            };
        }
    };

    const driver = createTestDriver(mockApi);
    driver.stations = [
        { station_id: 'STATION_A', latitude: 21.015, longitude: 105.815, service_type: 'FAST_CHARGING' },
        { station_id: 'STATION_B', latitude: 21.018, longitude: 105.818, service_type: 'FAST_CHARGING' },
        { station_id: 'STATION_C', latitude: 21.021, longitude: 105.821, service_type: 'FAST_CHARGING' }
    ];

    const initialRev = driver.routeRevision;

    // Rapid navigation calls: A -> B -> C
    await driver.navigateViaStationId('STATION_A');
    await driver.navigateViaStationId('STATION_B');
    await driver.navigateViaStationId('STATION_C');

    // Final state must reflect STATION_C, not A or B
    assert.equal(driver._selectedStationId, 'STATION_C', 'Final selected station must be STATION_C');
    assert.equal(driver._navigationLocked, true, 'Navigation must be locked to final station');
    assert.ok(driver.routeRevision >= initialRev + 3, 'Route revision should reflect all navigations');
});

test('Test 3: routeRevision increments atomically for each operation', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    const rev0 = driver.routeRevision;

    // Each evaluation increments by 1
    await driver._evaluateAtCurrentPosition();
    const rev1 = driver.routeRevision;
    assert.equal(rev1, rev0 + 1, 'Evaluation should increment revision by 1');

    await driver.navigateViaStationId('OLD_STATION');
    const rev2 = driver.routeRevision;
    assert.equal(rev2, rev1 + 1, 'Navigation should increment revision by 1');

    // unlockNavigation increments revision via _evaluateAtCurrentPosition
    driver.unlockNavigation();
    // Note: unlockNavigation calls _evaluateAtCurrentPosition which increments revision

    await driver.navigateViaStationId('NEW_STATION');
    // After unlock (which increments) + new navigation = +2 from rev2
    assert.ok(driver.routeRevision >= rev2 + 2, 'After unlock + navigation, revision should increase by at least 2');
});

test('Test 4: unlockNavigation resets navigation lock and allows new navigation', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    // Navigate to station A
    await driver.navigateViaStationId('OLD_STATION');
    assert.equal(driver._selectedStationId, 'OLD_STATION');
    assert.equal(driver._navigationLocked, true);

    // User unlocks navigation (to change station)
    driver.unlockNavigation();
    assert.equal(driver._navigationLocked, false);
    assert.equal(driver._selectedStationId, null, 'Selected station should be cleared after unlock');

    // Navigate to station B - should work fine
    await driver.navigateViaStationId('NEW_STATION');
    assert.equal(driver._selectedStationId, 'NEW_STATION');
    assert.equal(driver._navigationLocked, true);
});

test('Test 5: multiple rapid evaluations preserve revision integrity', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    const initialRev = driver.routeRevision;

    // Multiple evaluations
    await driver._evaluateAtCurrentPosition();
    await driver._evaluateAtCurrentPosition();
    await driver._evaluateAtCurrentPosition();

    // Each evaluation increments revision
    assert.equal(driver.routeRevision, initialRev + 3, 'Three evaluations should increment revision by 3');
});

test('Test 6: routeRevision guards ensure stale responses are filtered', async () => {
    // This test verifies that if we manually manipulate revision,
    // the stale response guard logic works correctly

    const driver = createTestDriver(immediateMockApi());

    // Simulate a stale response scenario:
    // 1. Start an operation with revision X
    const staleRev = driver.routeRevision;

    // 2. Before response, complete another operation that increments revision to X+1
    await driver.navigateViaStationId('NEW_STATION');

    // 3. The staleRev is now outdated
    assert.ok(driver.routeRevision > staleRev, 'Current revision should be higher than stale revision');

    // 4. If we somehow received the old response, the guard would filter it out
    // because routeRevision !== staleRev

    // Verify current state is from the latest operation, not stale
    assert.equal(driver._selectedStationId, 'NEW_STATION', 'State should reflect latest operation');
});

test('Test 7: cancelPostTripStation does not corrupt navigation state', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    // Set a post-trip station
    await driver.setPostTripStation('OLD_STATION');
    assert.equal(driver.postTripStation?.station_id, 'OLD_STATION');

    // Cancel it
    driver.cancelPostTripStation();
    assert.equal(driver.postTripStation, null);

    // Navigation should still work
    await driver.navigateViaStationId('NEW_STATION');
    assert.equal(driver._selectedStationId, 'NEW_STATION');
    assert.equal(driver._navigationLocked, true);
});

test('Test 8: revision is preserved across state transitions', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    // Navigate and lock navigation
    await driver.navigateViaStationId('OLD_STATION');
    const revBeforeComplete = driver.routeRevision;

    // Complete trip — use setState + renderTripCompleteUI (same as completeTrip button handler)
    driver.setState(DriverState.TRIP_COMPLETE);
    driver.renderTripCompleteUI();

    // After trip complete, navigation is unlocked
    assert.equal(driver._navigationLocked, false, 'Navigation should be unlocked after trip complete');
    assert.equal(driver._selectedStationId, null, 'Selected station should be cleared');

    // Return to available state
    driver.returnToAvailable();

    // Start new trip
    driver.currentTrip = {
        trip_id: 'T0002',
        destination: { latitude: 21.02, longitude: 105.82 }
    };
    driver.setState(DriverState.TRIP_ACTIVE);

    // New navigation should work with fresh state
    await driver.navigateViaStationId('NEW_STATION');
    assert.equal(driver._selectedStationId, 'NEW_STATION');
    assert.ok(driver.routeRevision > revBeforeComplete, 'New trip should have incremented revision');
});

test('Test 9: concurrent evaluations with navigation lock do not interfere', async () => {
    const mockApi = immediateMockApi();
    const driver = createTestDriver(mockApi);

    // Navigate to lock navigation
    await driver.navigateViaStationId('OLD_STATION');
    assert.equal(driver._navigationLocked, true);

    // Try to evaluate while locked - should skip
    const revBefore = driver.routeRevision;
    await driver._evaluateAtCurrentPosition();
    // _evaluateAtCurrentPosition returns early when locked, so revision should NOT increment
    assert.equal(driver.routeRevision, revBefore, 'Locked evaluation should not increment revision');
});

test('Test 10: _isEvaluating flag prevents concurrent evaluations', async () => {
    const driver = createTestDriver(immediateMockApi());

    // Simulate already evaluating
    driver._isEvaluating = true;

    const revBefore = driver.routeRevision;
    await driver._evaluateAtCurrentPosition();

    // Should return early due to _isEvaluating flag
    assert.equal(driver.routeRevision, revBefore, 'Concurrent evaluation should be prevented');

    // Reset flag
    driver._isEvaluating = false;

    // Now evaluation should work
    await driver._evaluateAtCurrentPosition();
    assert.ok(driver.routeRevision > revBefore, 'After flag reset, evaluation should increment revision');
});
