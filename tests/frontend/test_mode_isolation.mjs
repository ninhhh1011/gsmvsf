import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { DriverState } from '../../backend/app/static/demo/js/domain/driver_state.js';
import { ReplayState } from '../../backend/app/static/demo/js/replay.js';

function deferred() {
    let resolve, reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

function driverFixture(api) {
    const map = {
        scene: 'DRIVER', renderDriver() { this.scene = 'DRIVER'; }, renderStations() { this.scene = 'DRIVER'; },
        clearAll() { this.scene = 'EMPTY'; }, clearRecommendationRoute() { this.scene = 'DRIVER'; },
        renderRecommendationRoute() { this.scene = 'DRIVER'; }, renderDirectRoute() { this.scene = 'DRIVER'; },
        renderTripEndpoints() { this.scene = 'DRIVER'; }, highlightStation() { this.scene = 'DRIVER'; },
        fitBoundsToActive() { this.scene = 'DRIVER'; }, onMapClick() {}
    };
    const driver = new DriverModeController({ getRecommendation: async () => ({ has_recommendation: false }), ...api }, map);
    driver.state = DriverState.TRIP_ACTIVE;
    driver.currentVehicle = { vehicle_id: 'V0001', vehicle_type: 'EV_CAR', usable_capacity_kwh: 17.15, consumption_wh_per_km: 150 };
    driver.currentTrip = { trip_id: 'T0001', destination: { latitude: 21.02, longitude: 105.82 } };
    driver.currentPos = { latitude: 21.01, longitude: 105.81 };
    driver.replay.observations = [{ latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z' }];
    driver.replay.state = ReplayState.READY;
    const trip = driver.currentTrip;
    function enterDebug() {
        if (driver.suspendForDebug) driver.suspendForDebug();
        else driver.pauseTrip();
        map.scene = 'DEBUG';
    }
    return { driver, map, trip, enterDebug };
}

test('Debug suspension rejects late Driver ingestion and preserves loaded trip and confirmed progress', async t => {
    for (const name of ['log', 'group', 'groupEnd', 'warn']) t.mock.method(console, name, () => {});
    const ingestion = deferred();
    const { driver, map, trip, enterDebug } = driverFixture({ ingestDriverLocation: () => ingestion.promise });
    driver.replay.currentIndex = 1;
    driver.replay.observations.push({ latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:01:00Z' });
    const step = driver.replay.step();
    enterDebug();
    ingestion.resolve({ status: 'GPS_ACCEPTED', raw_position: { latitude: 21.02, longitude: 105.82 } });
    assert.equal(await step, false);
    assert.equal(map.scene, 'DEBUG');
    assert.equal(driver.currentTrip, trip);
    assert.equal(driver.state, DriverState.TRIP_ACTIVE);
    assert.equal(driver.replay.observations.length, 2);
    assert.equal(driver.replay.currentIndex, 1);
});

test('Debug suspension rejects a Driver recommendation already pending inside a replay step', async t => {
    for (const name of ['log', 'group', 'groupEnd']) t.mock.method(console, name, () => {});
    const recommendation = deferred();
    const started = deferred();
    const { driver, map, trip, enterDebug } = driverFixture({
        ingestDriverLocation: async () => ({ status: 'GPS_ACCEPTED', raw_position: { latitude: 21.01, longitude: 105.81 } }),
        getRecommendation: () => { started.resolve(); return recommendation.promise; }
    });
    const step = driver.replay.step();
    await started.promise;
    enterDebug();
    recommendation.resolve({ has_recommendation: false });
    assert.equal(await step, false);
    assert.equal(map.scene, 'DEBUG');
    assert.equal(driver.lastRecommendation, null);
    assert.equal(driver.currentTrip, trip);
    assert.equal(driver.replay.currentIndex, 0);
});

for (const outcome of ['rejected', 'resolved']) test(`Debug suspension rejects ${outcome} late Driver diversion without republishing state`, async t => {
    for (const name of ['log', 'group', 'groupEnd', 'warn']) t.mock.method(console, name, () => {});
    const diversion = deferred();
    const started = deferred();
    const { driver, map, enterDebug } = driverFixture({
        getRecommendation: async () => ({ has_recommendation: true, ranked_candidates: [{ station_id: 'S001' }] }),
        computeRoute: (() => {
            let calls = 0;
            return () => {
                if (outcome === 'resolved' && ++calls === 1) return Promise.resolve({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@' });
                started.resolve();
                return diversion.promise;
            };
        })()
    });
    driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 }];
    const updates = [];
    driver.options.onStateUpdate = state => updates.push(state);
    const evaluation = driver._evaluateAtCurrentPosition();
    await started.promise;
    enterDebug();
    if (outcome === 'rejected') diversion.reject(new Error('routing unavailable'));
    else diversion.resolve({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@' });
    await evaluation;
    assert.equal(map.scene, 'DEBUG');
    assert.equal(updates.length, 0);
});

test('ordinary Driver pause still allows its accepted in-flight step to finish', async t => {
    for (const name of ['log', 'group', 'groupEnd']) t.mock.method(console, name, () => {});
    const ingestion = deferred();
    const { driver } = driverFixture({ ingestDriverLocation: () => ingestion.promise });
    driver.replay.state = ReplayState.PLAYING;
    const step = driver.replay.step();
    driver.pauseTrip();
    ingestion.resolve({ status: 'GPS_ACCEPTED', raw_position: driver.currentPos });
    assert.equal(await step, true);
    assert.equal(driver.replay.currentIndex, 1);
});

for (const action of ['navigateViaStationId', 'setPostTripStation', '_updateCustomRoute', 'refreshDrawerEvaluations']) {
    test(`Debug suspension rejects pending Driver ${action} output`, async t => {
        for (const name of ['log', 'group', 'groupEnd', 'warn']) t.mock.method(console, name, () => {});
        const response = deferred();
        const { driver, map, trip, enterDebug } = driverFixture({
            computeRoute: () => response.promise,
            evaluateAndSearchCandidates: async () => ({ candidates: [] }),
            ...(action === 'refreshDrawerEvaluations' ? { getRecommendation: () => response.promise } : {})
        });
        driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 }];
        const running = action === '_updateCustomRoute'
            ? driver._updateCustomRoute(driver.currentPos, trip.destination) : driver[action]('S001');
        enterDebug();
        response.resolve({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300,
            has_recommendation: false, ranked_candidates: [] });
        await running;
        assert.equal(map.scene, 'DEBUG');
        assert.equal(driver.currentTrip, trip);
        assert.equal(driver.lastRecommendation, null);
        assert.equal(driver.postTripRoute, null);
    });
}

test('Debug suspension rejects a late failed custom Driver route without drawing fallback endpoints', async t => {
    t.mock.method(console, 'warn', () => {});
    const route = deferred();
    const { driver, map, trip, enterDebug } = driverFixture({ computeRoute: () => route.promise });
    const running = driver._updateCustomRoute(driver.currentPos, trip.destination);
    enterDebug();
    route.reject(new Error('routing unavailable'));
    await running;
    assert.equal(map.scene, 'DEBUG');
});
