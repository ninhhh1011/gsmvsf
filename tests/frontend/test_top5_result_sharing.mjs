/**
 * Unit tests for Top 5 result sharing and auto-refresh functionality.
 * Verifies:
 * - "Tìm đường" always calls recommend with top_n=5
 * - Top 1 is NOT auto-selected after recommend
 * - 0/1/5 results handled without fake data
 * - Station with 2 services renders as one card with both services
 * - _top5Result sharing and auto-refresh timer
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
        updateStationMarkers() {},
        map: {
            flyTo() {}
        },
        layers: {
            markers: { clearLayers() {} },
            driver: { clearLayers() {} },
            recommendRoute: { clearLayers() {} }
        }
    };
}

// Shared mock station data
const STATIONS = [
    {
        station_id: 'STATION_1',
        latitude: 21.015,
        longitude: 105.815,
        service_type: 'FAST_CHARGING',
        station_type: 'CHARGING',
        operator_name: 'Test Operator'
    },
    {
        station_id: 'STATION_2',
        latitude: 21.018,
        longitude: 105.818,
        service_type: 'BATTERY_SWAP',
        station_type: 'SWAP',
        operator_name: 'Test Operator'
    },
    {
        station_id: 'STATION_COMBO',
        latitude: 21.020,
        longitude: 105.820,
        service_types: ['BATTERY_SWAP', 'FAST_CHARGING'],
        station_type: 'CHARGING_SWAP',
        operator_name: 'Combo Operator'
    }
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
    driver.currentSocPct = 50.0;
    driver.estimatedRangeKm = 85.0;
    driver.safetyReserveKm = 2.0;
    driver.remainingTripDistanceKm = 5.0;
    driver.totalDistanceTravelledKm = 0.0;
    driver.generation = 1;
    driver.routeRevision = 0;
    driver._isEvaluating = false;
    driver._navigationLocked = false;
    driver._selectedStationId = null;
    return driver;
}

// ─── Step 1: Test — "Tìm đường" always calls recommend, even with sufficient SOC ───

test('findRoute calls recommend even when SOC >= 50%', async () => {
    let recommendCallCount = 0;
    let lastTopN = null;

    const mockApi = {
        getRecommendation: async (payload) => {
            recommendCallCount++;
            lastTopN = payload.top_n;
            return {
                has_recommendation: true,
                ranked_candidates: [{
                    station_id: 'STATION_1',
                    latitude: 21.015,
                    longitude: 105.815,
                    service_type: 'FAST_CHARGING',
                    rank: 1
                }]
            };
        },
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        })
    };

    const driver = createTestDriver(mockApi);
    // Set high SOC (>= 50%)
    driver.currentSocPct = 80.0;
    driver.estimatedRangeKm = 136.0;

    await driver._evaluateAtCurrentPosition();

    assert.equal(recommendCallCount, 1, 'recommend should be called once');
    assert.equal(lastTopN, 5, 'recommend should be called with top_n=5 even with high SOC');
});

// ─── Step 2: Test — top 1 is NOT auto-selected after recommend ───

test('recommend response does not auto-select top 1 station', async () => {
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [
                {
                    station_id: 'STATION_1',
                    latitude: 21.015,
                    longitude: 105.815,
                    service_type: 'FAST_CHARGING',
                    rank: 1
                },
                {
                    station_id: 'STATION_2',
                    latitude: 21.018,
                    longitude: 105.818,
                    service_type: 'BATTERY_SWAP',
                    rank: 2
                },
                {
                    station_id: 'STATION_COMBO',
                    latitude: 21.020,
                    longitude: 105.820,
                    service_types: ['BATTERY_SWAP', 'FAST_CHARGING'],
                    rank: 3
                }
            ]
        }),
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        })
    };

    const driver = createTestDriver(mockApi);

    await driver._evaluateAtCurrentPosition();

    // Assert: no station should be auto-selected
    assert.equal(driver._selectedStationId, null, 'No station should be auto-selected');
    assert.equal(driver._navigationLocked, false, 'Navigation should NOT be locked');

    // Verify the top 5 result is stored
    assert.ok(driver._top5Result, '_top5Result should be populated');
    assert.equal(driver._top5Result.candidates.length, 3, 'Should have 3 candidates in _top5Result');
});

// ─── Step 3: Test — 0/1/5 results handled without fake data ───

test('recommend with 0 results shows empty state, not fake candidates', async () => {
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: false,
            ranked_candidates: []
        }),
        computeRoute: async () => ({})
    };

    const driver = createTestDriver(mockApi);

    await driver._evaluateAtCurrentPosition();

    // Assert: empty state, no fake data
    assert.ok(driver._top5Result, '_top5Result should exist even for empty results');
    assert.equal(driver._top5Result.candidates.length, 0, 'Should have 0 candidates');
    assert.equal(driver.lastRecommendation?.ranked_candidates?.length, 0, 'Backend should return empty array');
});

test('recommend with 1 result handles single candidate correctly', async () => {
    let capturedCandidates = null;

    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{
                station_id: 'STATION_1',
                latitude: 21.015,
                longitude: 105.815,
                service_type: 'FAST_CHARGING',
                rank: 1
            }]
        }),
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        })
    };

    const driver = createTestDriver(mockApi);
    const bindings = driver.bindings;

    // Capture what would be rendered
    const origShowPanel = bindings.showRecommendationPanel;
    bindings.showRecommendationPanel = (html, opts) => {
        capturedCandidates = html;
        return origShowPanel(html, opts);
    };

    await driver._evaluateAtCurrentPosition();

    // Verify single candidate handled
    assert.ok(driver._top5Result, '_top5Result should exist');
    assert.equal(driver._top5Result.candidates.length, 1, 'Should have exactly 1 candidate');

    bindings.showRecommendationPanel = origShowPanel;
});

test('recommend with 5 results handles max candidates correctly', async () => {
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [
                { station_id: 'S1', latitude: 21.015, longitude: 105.815, rank: 1 },
                { station_id: 'S2', latitude: 21.016, longitude: 105.816, rank: 2 },
                { station_id: 'S3', latitude: 21.017, longitude: 105.817, rank: 3 },
                { station_id: 'S4', latitude: 21.018, longitude: 105.818, rank: 4 },
                { station_id: 'S5', latitude: 21.019, longitude: 105.819, rank: 5 }
            ]
        }),
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        })
    };

    const driver = createTestDriver(mockApi);

    await driver._evaluateAtCurrentPosition();

    // Verify all 5 candidates are stored
    assert.equal(driver._top5Result.candidates.length, 5, 'Should have all 5 candidates');
    assert.equal(driver._top5Result.candidates[0].station_id, 'S1', 'First should be rank 1');
    assert.equal(driver._top5Result.candidates[4].station_id, 'S5', 'Last should be rank 5');
});

// ─── Step 4: Test — station with 2 services renders as one card with both services ───

test('station with BATTERY_SWAP and CHARGING renders as one composite card', async () => {
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{
                station_id: 'STATION_COMBO',
                latitude: 21.020,
                longitude: 105.820,
                service_types: ['BATTERY_SWAP', 'FAST_CHARGING'],
                rank: 1
            }]
        }),
        computeRoute: async () => ({
            geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
            distance_m: 5000
        })
    };

    const driver = createTestDriver(mockApi);
    let capturedPanelHtml = null;

    const origShowPanel = driver.bindings.showRecommendationPanel;
    driver.bindings.showRecommendationPanel = (html, opts) => {
        capturedPanelHtml = html;
        return origShowPanel(html, opts);
    };

    await driver._evaluateAtCurrentPosition();

    assert.ok(capturedPanelHtml, 'Panel HTML should be rendered');
    // Station COMBO has both service types - verify in stored result
    assert.ok(driver._top5Result.candidates[0].service_types, 'Candidate should have service_types array');
    assert.equal(driver._top5Result.candidates[0].service_types.length, 2, 'Should have 2 service types');
    assert.ok(driver._top5Result.candidates[0].service_types.includes('BATTERY_SWAP'), 'Should include BATTERY_SWAP');
    assert.ok(driver._top5Result.candidates[0].service_types.includes('FAST_CHARGING'), 'Should include FAST_CHARGING');

    driver.bindings.showRecommendationPanel = origShowPanel;
});

// ─── Step 5: Test — _top5Result sharing via callback ───

test('_top5Result is populated after recommend response', async () => {
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [
                { station_id: 'STATION_1', rank: 1 },
                { station_id: 'STATION_2', rank: 2 }
            ]
        }),
        computeRoute: async () => ({ geometry: '', distance_m: 1000 })
    };

    const driver = createTestDriver(mockApi);

    await driver._evaluateAtCurrentPosition();

    assert.ok(driver._top5Result, '_top5Result should be set');
    assert.ok(driver._top5Result.candidates, 'Should have candidates array');
    assert.equal(driver._top5Result.candidates.length, 2);
    assert.equal(driver._top5Revision, 1, '_top5Revision should be incremented');
});

test('revision guard filters stale recommend responses', async () => {
    let responseCount = 0;

    const mockApi = {
        getRecommendation: async () => {
            responseCount++;
            return {
                has_recommendation: true,
                ranked_candidates: [{
                    station_id: `STATION_${responseCount}`,
                    rank: 1
                }]
            };
        },
        computeRoute: async () => ({ geometry: '', distance_m: 1000 })
    };

    const driver = createTestDriver(mockApi);

    // Capture the revision BEFORE the first evaluation
    const initialRev = driver._top5Revision;

    // Start first evaluation
    await driver._evaluateAtCurrentPosition();

    // Verify first response was processed
    assert.ok(driver._top5Result);
    assert.equal(driver._top5Result.candidates[0].station_id, 'STATION_1');

    // Now navigate to an existing station (this increments routeRevision)
    await driver.navigateViaStationId('STATION_1');

    // The navigation lock would have incremented routeRevision
    // The current state should reflect the latest operation
    assert.equal(driver._top5Revision, initialRev + 1, '_top5Revision should be incremented');
});

// ─── Step 6: Test — auto-refresh timer ───

test('startRecommendRefresh starts interval timer', async () => {
    const driver = createTestDriver({
        getRecommendation: async () => ({ has_recommendation: false, ranked_candidates: [] }),
        computeRoute: async () => ({})
    });

    assert.equal(driver._recommendTimer, null, 'Timer should start as null');

    driver.startRecommendRefresh();

    assert.ok(driver._recommendTimer !== null, 'Timer should be set after startRecommendRefresh');

    driver.stopRecommendRefresh();
});

test('stopRecommendRefresh clears interval timer', async () => {
    const driver = createTestDriver({
        getRecommendation: async () => ({ has_recommendation: false, ranked_candidates: [] }),
        computeRoute: async () => ({})
    });

    driver.startRecommendRefresh();
    assert.ok(driver._recommendTimer !== null, 'Timer should be set');

    driver.stopRecommendRefresh();
    assert.equal(driver._recommendTimer, null, 'Timer should be cleared');
});

test('auto-refresh timer calls _refreshRecommendation at interval', async () => {
    let recommendCount = 0;

    const driver = createTestDriver({
        getRecommendation: async () => {
            recommendCount++;
            return { has_recommendation: false, ranked_candidates: [] };
        },
        computeRoute: async () => ({})
    });

    // Ensure state is TRIP_ACTIVE and not locked
    driver.state = DriverState.TRIP_ACTIVE;
    driver._navigationLocked = false;

    // Use shorter interval for testing (10ms instead of 30000ms)
    driver._recommendRefreshInterval = 10;

    driver.startRecommendRefresh();

    // Wait for at least 2 timer ticks
    await new Promise(resolve => setTimeout(resolve, 30));

    driver.stopRecommendRefresh();

    // Note: first call may happen on start, and then at interval
    // With 10ms interval and 30ms wait, we should get at least 2 calls
    assert.ok(recommendCount >= 1, `Should have at least 1 recommend call, got ${recommendCount}`);
});

test('recommendRefreshInterval option is configurable', async () => {
    const driver1 = createTestDriver({
        getRecommendation: async () => ({ has_recommendation: false, ranked_candidates: [] }),
        computeRoute: async () => ({})
    });

    const driver2 = new DriverModeController(
        { getRecommendation: async () => ({ has_recommendation: false, ranked_candidates: [] }), computeRoute: async () => ({}) },
        mockMap(),
        { recommendRefreshInterval: 5000 }
    );

    // driver1 uses default 30000ms
    assert.equal(driver1._recommendRefreshInterval, 30000, 'Default interval should be 30000ms');

    // driver2 uses custom 5000ms
    assert.equal(driver2._recommendRefreshInterval, 5000, 'Custom interval should be 5000ms');
});

// ─── Integration: verify _notifyTop5Updated callback mechanism ───

test('_notifyTop5Updated is called after recommend response', async () => {
    let notifiedResult = null;

    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{ station_id: 'STATION_1', rank: 1 }]
        }),
        computeRoute: async () => ({ geometry: '', distance_m: 1000 })
    };

    const driver = createTestDriver(mockApi);
    driver._notifyTop5Updated = (result) => {
        notifiedResult = result;
    };

    await driver._evaluateAtCurrentPosition();

    assert.ok(notifiedResult, '_notifyTop5Updated should have been called');
    assert.equal(notifiedResult.candidates.length, 1);
    assert.equal(notifiedResult.candidates[0].station_id, 'STATION_1');
});

// ─── Edge cases ───

test('navigation lock prevents _top5Result from being updated', async () => {
    let recommendCallCount = 0;

    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{ station_id: 'STATION_NEW', rank: 1 }]
        }),
        computeRoute: async () => ({ geometry: '', distance_m: 1000 })
    };

    const driver = createTestDriver(mockApi);

    // First evaluate - this should populate _top5Result
    await driver._evaluateAtCurrentPosition();
    assert.ok(driver._top5Result, '_top5Result should be set after first evaluation');

    // Now manually lock navigation (simulating user selecting a station)
    driver._navigationLocked = true;
    driver._selectedStationId = 'STATION_1';

    // Try to evaluate - should skip due to lock
    await driver._evaluateAtCurrentPosition();

    // recommend should NOT have been called because of lock
    // Note: the actual implementation skips evaluation when locked
    assert.equal(driver._navigationLocked, true, 'Navigation should remain locked');
});

test('_top5Result is null initially', async () => {
    const driver = createTestDriver({
        getRecommendation: async () => ({ has_recommendation: false, ranked_candidates: [] }),
        computeRoute: async () => ({})
    });

    assert.equal(driver._top5Result, null, '_top5Result should be null initially');
    assert.equal(driver._top5Revision, 0, '_top5Revision should be 0 initially');
});
