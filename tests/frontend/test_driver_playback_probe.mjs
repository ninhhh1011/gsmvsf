/**
 * Automated probe tests for Driver Playback & Replay Reliability:
 * - Rate limit 429 retry & backoff
 * - Playback ownership token cancellation (no duplicate loops)
 * - Monotonic event-time clock and rejection of STALE_OBSERVATION
 * - Station selection revision protection (no stale async overwrites)
 * - Complete transition on final route observation
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { ReplayState, TrajectoryReplayController } from '../../backend/app/static/demo/js/replay.js';
import { ApiError } from '../../backend/app/static/demo/js/api.js';
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
        layers: { markers: { clearLayers() {} }, driver: { clearLayers() {} } }
    };
}

test('Probe 1: Transient 429 rate-limit error is retried up to 3 times with backoff without crashing to ERROR', async () => {
    let callCount = 0;
    const mockApi = {
        ingestDriverLocation: async () => {
            callCount++;
            if (callCount <= 2) {
                // Simulate HTTP 429 rate limit with retry-after header
                throw new ApiError('Rate limit exceeded', 429, 'RATE_LIMIT', null, 0.05); // 50ms cooldown for test
            }
            return {
                status: 'MATCHED',
                matched_position: { latitude: 21.01, longitude: 105.81 }
            };
        },
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 }
    ];
    replay.speedMultiplier = 100; // fast for testing

    replay.play();
    assert.equal(replay.state, ReplayState.PLAYING);

    // Wait enough for the 2 retries (each 50ms) to complete
    await new Promise(r => setTimeout(r, 200));

    // After retries succeeded, playback should complete (1 observation reached)
    assert.equal(replay.currentIndex, 1);
    assert.equal(replay.state, ReplayState.COMPLETE);
    assert.equal(callCount, 3); // 2 failed + 1 successful retry
});

test('Probe 2: Exhausted retries after 3 attempts transitions to ERROR without skipping index', async () => {
    let callCount = 0;
    const mockApi = {
        ingestDriverLocation: async () => {
            callCount++;
            throw new ApiError('Rate limit exceeded', 429, 'RATE_LIMIT', null, 0.02);
        },
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 }
    ];
    replay.speedMultiplier = 100;

    replay.play();
    await new Promise(r => setTimeout(r, 200));

    assert.equal(replay.state, ReplayState.ERROR);
    assert.equal(replay.currentIndex, 0); // Index must NOT be skipped
    assert.ok(callCount >= 3, `Expected at least 3 attempts, got ${callCount}`);
});

test('Probe 3: Rapid Play -> Pause -> Play retains exactly ONE active playback loop', async () => {
    let activeLoops = 0;
    let maxConcurrentSteps = 0;
    let currentConcurrentSteps = 0;

    const mockApi = {
        ingestDriverLocation: async () => {
            currentConcurrentSteps++;
            maxConcurrentSteps = Math.max(maxConcurrentSteps, currentConcurrentSteps);
            await new Promise(r => setTimeout(r, 20));
            currentConcurrentSteps--;
            return {
                status: 'MATCHED',
                matched_position: { latitude: 21.01, longitude: 105.81 }
            };
        },
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z' },
        { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:00:05Z' },
        { latitude: 21.03, longitude: 105.83, timestamp: '2026-09-01T07:00:10Z' },
        { latitude: 21.04, longitude: 105.84, timestamp: '2026-09-01T07:00:15Z' },
        { latitude: 21.05, longitude: 105.85, timestamp: '2026-09-01T07:00:20Z' }
    ];
    replay.speedMultiplier = 100;

    // Rapid Play -> Pause -> Play cycle
    replay.play();
    await new Promise(r => setTimeout(r, 10));
    replay.pause();
    replay.play();

    await new Promise(r => setTimeout(r, 250));

    // Concurrency must never exceed 1
    assert.equal(maxConcurrentSteps, 1);
});

test('Probe 4: STALE_OBSERVATION response from backend is rejected and does not advance progress', async () => {
    const mockApi = {
        ingestDriverLocation: async () => ({
            status: 'STALE_OBSERVATION',
            message: 'Observation timestamp precedes last known state'
        }),
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z' }
    ];

    let threw = false;
    try {
        await replay.step(false);
    } catch (e) {
        threw = true;
    }

    assert.equal(replay.state, ReplayState.ERROR);
    assert.equal(replay.currentIndex, 0); // Index must NOT increment on rejected stale observation
});

test('Probe 5: loadFromPolyline generates strictly monotonic event timestamps after accepted steps', async () => {
    const mockApi = {
        ingestDriverLocation: async (driverId, payload) => ({
            status: 'MATCHED',
            matched_position: { latitude: payload.latitude, longitude: payload.longitude }
        }),
        resetDriverLocation: async () => ({})
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap());
    const route1 = [
        [20.9849, 105.7935],
        [20.9855, 105.7940]
    ];
    await replay.loadFromPolyline(route1);
    await replay.step(false);

    const firstAcceptedTimestampMs = replay.lastAcceptedTimestampMs;
    assert.ok(firstAcceptedTimestampMs > 0, 'First accepted timestamp must be recorded');

    // Now reload with a new (much longer) route
    const route2 = [
        [20.9855, 105.7940],
        [21.0000, 105.8100],
        [21.0285, 105.8542]
    ];
    await replay.loadFromPolyline(route2);

    // All timestamps of route2 must be strictly greater than firstAcceptedTimestampMs
    for (const obs of replay.observations) {
        const obsMs = new Date(obs.timestamp).getTime();
        assert.ok(
            obsMs > firstAcceptedTimestampMs,
            `Observation timestamp ${obs.timestamp} (${obsMs}) must be > previous accepted ${firstAcceptedTimestampMs}`
        );
    }
});

test('Probe 6: Slow asynchronous evaluation response does not overwrite user-selected station', async (t) => {
    for (const name of ['log', 'group', 'groupEnd', 'warn']) t.mock.method(console, name, () => {});

    let resolveSlowLeg2 = null;
    const mockApi = {
        getRecommendation: async () => ({
            has_recommendation: true,
            ranked_candidates: [{ station_id: 'OLD_STATION', service_type: 'CHARGING' }]
        }),
        computeRoute: async (orig, dest) => {
            // If routing to OLD_STATION, delay leg2 until after user selects NEW_STATION
            return new Promise(resolve => {
                resolveSlowLeg2 = () => resolve({
                    geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                    distance_m: 5000
                });
            });
        }
    };

    const driver = new DriverModeController(mockApi, mockMap());
    driver.state = DriverState.TRIP_ACTIVE;
    driver.currentVehicle = { vehicle_id: 'V0001', vehicle_type: 'EV_CAR', usable_capacity_kwh: 17.15 };
    driver.currentTrip = { trip_id: 'T0001', destination: { latitude: 21.02, longitude: 105.82 } };
    driver.currentPos = { latitude: 21.01, longitude: 105.81 };
    driver.stations = [
        { station_id: 'OLD_STATION', latitude: 21.015, longitude: 105.815 },
        { station_id: 'NEW_STATION', latitude: 21.018, longitude: 105.818 }
    ];

    // Trigger periodic evaluation (which starts routing leg 1 and 2 for OLD_STATION)
    const evalPromise = driver._evaluateAtCurrentPosition();

    // User explicitly navigates to NEW_STATION before OLD_STATION route finishes
    driver._navigationLocked = true;
    driver._selectedStationId = 'NEW_STATION';
    driver.lastRecommendedStationId = 'NEW_STATION';
    driver.routeRevision++; // Increment revision as user explicitly selected new station

    // Now slow leg 2 for OLD_STATION resolves
    if (resolveSlowLeg2) resolveSlowLeg2();
    await evalPromise;

    // Invariant: User's selection NEW_STATION must NOT be overwritten by OLD_STATION
    assert.equal(driver._selectedStationId, 'NEW_STATION');
    assert.equal(driver.lastRecommendedStationId, 'NEW_STATION');
});

test('Probe 7: Final observation triggers TRIP_COMPLETE and isReplayComplete correctly', async () => {
    let stateAtEnd = null;
    const mockApi = {
        ingestDriverLocation: async () => ({
            status: 'MATCHED',
            matched_position: { latitude: 21.02, longitude: 105.82 }
        }),
        getRecommendation: async () => ({ has_recommendation: false })
    };

    const driver = new DriverModeController(mockApi, mockMap());
    driver.state = DriverState.TRIP_ACTIVE;
    driver.currentVehicle = { vehicle_id: 'V0001', vehicle_type: 'EV_CAR', usable_capacity_kwh: 17.15 };
    driver.currentTrip = { trip_id: 'T0001', destination: { latitude: 21.02, longitude: 105.82 } };
    driver.currentPos = { latitude: 21.01, longitude: 105.81 };
    driver.replay.observations = [
        { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:00:00Z' }
    ];
    driver.replay.state = ReplayState.READY;

    // Single step to the final observation
    await driver.replay.step(false);

    // After final step, DriverState must be TRIP_COMPLETE
    assert.equal(driver.state, DriverState.TRIP_COMPLETE);
    assert.equal(driver.replay.state, ReplayState.COMPLETE);
    assert.equal(driver.remainingTripDistanceKm, 0.0);
});
