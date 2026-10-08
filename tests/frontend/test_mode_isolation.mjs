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
        scene: 'DRIVER', renderDriver() { this.scene = 'DRIVER'; },
        renderStations(stations, recommended) { this.scene = 'DRIVER'; this.highlightedStation = recommended; },
        clearAll() { this.scene = 'EMPTY'; }, clearRecommendationRoute() { this.scene = 'DRIVER'; },
        renderRecommendationRoute() { this.scene = 'DRIVER'; }, renderDirectRoute() { this.scene = 'DRIVER'; },
        renderTripEndpoints() { this.scene = 'DRIVER'; },
        highlightStation(stationId) { this.scene = 'DRIVER'; this.highlightedStation = stationId; },
        renderPostTripRoute(geometry) { this.scene = 'DRIVER'; this.postTripGeometry = geometry; },
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

test('successful Driver station navigation completes without a dead button reference', async () => {
    const { driver } = driverFixture({ computeRoute: async () => ({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300 }) });
    driver.state = DriverState.TRIP_ASSIGNED;
    driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 }];
    await assert.doesNotReject(driver.navigateViaStationId('S001'));
    assert.equal(driver._selectedStationId, 'S001');
    assert.equal(driver.lastRecommendedStationId, 'S001');
    assert.ok(driver.fullRouteCoords.length > 1);
});

for (const entrypoint of ['_selectStationAndNavigate', 'navigateViaStationId']) {
    for (const locked of [false, true]) test(`canceling ${entrypoint} preserves ${locked ? 'locked' : 'unlocked'} committed navigation`, async () => {
        const route = deferred();
        const { driver, map, enterDebug } = driverFixture({ computeRoute: () => route.promise });
        driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 },
            { station_id: 'S002', latitude: 21.03, longitude: 105.83 }];
        const previousRoute = [[21.01, 105.81], [21.02, 105.82]];
        driver.fullRouteCoords = previousRoute;
        driver._navigationLocked = locked;
        driver._selectedStationId = locked ? 'S001' : null;
        const running = driver[entrypoint]('S002');
        enterDebug();
        assert.equal(driver._navigationLocked, locked, 'a pending choice is not a committed lock');
        assert.equal(driver._selectedStationId, locked ? 'S001' : null);
        route.resolve({ geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300 });
        await running;
        assert.equal(driver.fullRouteCoords, previousRoute);
        driver.restoreMapState();
        assert.equal(map.highlightedStation, locked ? 'S001' : undefined);
        assert.equal(driver._navigationLocked, locked, 'recommendation eligibility still follows the prior committed selection');
    });
}

test('failed station routing preserves an unlocked route and leaves recommendations enabled', async t => {
    t.mock.method(console, 'warn', () => {});
    let recommendationCalls = 0;
    const { driver } = driverFixture({
        computeRoute: async () => { throw new Error('routing unavailable'); },
        getRecommendation: async () => { recommendationCalls++; return { has_recommendation: false }; }
    });
    driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 }];
    const previousRoute = [[21.01, 105.81], [21.02, 105.82]];
    driver.fullRouteCoords = previousRoute;
    await driver.navigateViaStationId('S001');
    assert.equal(driver._navigationLocked, false);
    assert.equal(driver._selectedStationId, null);
    assert.equal(driver.fullRouteCoords, previousRoute);
    for (const name of ['log', 'group', 'groupEnd']) t.mock.method(console, name, () => {});
    await driver._evaluateAtCurrentPosition();
    assert.equal(recommendationCalls, 1);
});

for (const geometry of [null, '']) test(`station routing with ${geometry === null ? 'missing' : 'empty'} geometry does not commit a selection`, async () => {
    const { driver, map } = driverFixture({ computeRoute: async () => ({ geometry, distance_m: 0 }) });
    driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 }];
    await driver.navigateViaStationId('S001');
    assert.equal(driver._navigationLocked, false);
    assert.equal(driver._selectedStationId, null);
    assert.equal(map.highlightedStation, undefined);
});

for (const hasPreviousSelection of [false, true]) {
    for (const outcome of ['canceled', 'failed', 'missing geometry', 'empty geometry']) {
        test(`post-trip ${outcome} routing preserves ${hasPreviousSelection ? 'the committed pair' : 'no selection'}`, async t => {
            t.mock.method(console, 'warn', () => {});
            const response = deferred();
            const { driver, map, enterDebug } = driverFixture({ computeRoute: () => response.promise });
            driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 },
                { station_id: 'S002', latitude: 21.03, longitude: 105.83 }];
            const previousStation = hasPreviousSelection ? driver.stations[0] : null;
            const previousRoute = hasPreviousSelection ? { geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300 } : null;
            driver.postTripStation = previousStation;
            driver.postTripRoute = previousRoute;
            const running = driver.setPostTripStation('S002');
            assert.equal(driver.postTripStation, previousStation, 'a pending choice must not change the committed station');
            assert.equal(driver.postTripRoute, previousRoute);
            if (outcome === 'canceled') enterDebug();
            if (outcome === 'failed') response.reject(new Error('routing unavailable'));
            else response.resolve({ geometry: outcome === 'missing geometry' ? null : outcome === 'empty geometry' ? '' : '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300 });
            await running;
            assert.equal(driver.postTripStation, previousStation);
            assert.equal(driver.postTripRoute, previousRoute);
            if (outcome === 'canceled') assert.equal(map.scene, 'DEBUG');
        });
    }

    test(`successful post-trip routing commits station and route together ${hasPreviousSelection ? 'over a prior pair' : 'from no selection'}`, async () => {
        const response = deferred();
        const { driver, map } = driverFixture({ computeRoute: () => response.promise });
        driver.stations = [{ station_id: 'S001', latitude: 21.01, longitude: 105.82 },
            { station_id: 'S002', latitude: 21.03, longitude: 105.83 }];
        const previousStation = hasPreviousSelection ? driver.stations[0] : null;
        const previousRoute = hasPreviousSelection ? { geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@', distance_m: 300 } : null;
        driver.postTripStation = previousStation;
        driver.postTripRoute = previousRoute;
        const running = driver.setPostTripStation('S002');
        assert.equal(driver.postTripStation, previousStation);
        assert.equal(driver.postTripRoute, previousRoute);
        const route = { geometry: '??_ibE_ibE', distance_m: 400 };
        response.resolve(route);
        await running;
        assert.equal(driver.postTripStation, driver.stations[1]);
        assert.equal(driver.postTripRoute, route);
        assert.equal(map.highlightedStation, 'S002');
        assert.equal(map.postTripGeometry, route.geometry);
        map.layers = { recommendRoute: { clearLayers() { map.postTripGeometry = null; } } };
        driver.cancelPostTripStation();
        assert.equal(driver.postTripStation, null);
        assert.equal(driver.postTripRoute, null);
        assert.equal(map.postTripGeometry, null);
    });
}

test('a trajectory load canceled by Debug returns to idle and the Driver Play action retries loading', async t => {
    for (const name of ['log', 'group', 'groupEnd', 'warn']) t.mock.method(console, name, () => {});
    const firstLoad = deferred();
    let loadCalls = 0;
    const { driver, map, trip, enterDebug } = driverFixture({
        getTrajectory: () => ++loadCalls === 1 ? firstLoad.promise : Promise.resolve([
            { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z' },
            { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:01:00Z' }
        ]),
        ingestDriverLocation: async () => ({ status: 'GPS_ACCEPTED', raw_position: { latitude: 21.01, longitude: 105.81 } })
    });
    const starting = driver.startTrip();
    assert.equal(driver.replay.state, ReplayState.LOADING);
    const indexAtSwitch = driver.replay.currentIndex;
    enterDebug();
    assert.equal(driver.replay.state, ReplayState.IDLE, 'canceled loading is honest and retryable');
    assert.equal(driver.replay.observations.length, 0, 'no invented ready observations');
    assert.equal(driver.currentTrip, trip);
    assert.equal(driver.replay.currentIndex, indexAtSwitch);
    firstLoad.resolve([{ latitude: 22, longitude: 106, timestamp: '2026-09-01T07:00:00Z' }]);
    await starting;
    assert.equal(map.scene, 'DEBUG');
    assert.equal(driver.replay.state, ReplayState.IDLE);
    assert.equal(driver.replay.observations.length, 0);
    await driver.playTrip();
    assert.equal(loadCalls, 2);
    assert.equal(driver.currentTrip, trip);
    assert.ok(driver.replay.currentIndex >= 1, 'retry confirms progress with actual reloaded observations');
    assert.equal(driver.replay.observations[0].latitude, 21.01);
    driver.pauseTrip();
});
