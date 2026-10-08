import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { SimModeController } from '../../backend/app/static/demo/js/sim_mode.js';
import { DemoMap } from '../../backend/app/static/demo/js/map.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

test('Driver return clears Simulation map content and redraws its existing navigation route', () => {
    const priorLeaflet = globalThis.L;
    const group = () => ({ layers: new Set([{ simulation: true }]),
        clearLayers() { this.layers.clear(); }, addLayer(layer) { this.layers.add(layer); } });
    const map = Object.assign(Object.create(DemoMap.prototype), {
        layers: Object.fromEntries(['directRoute', 'recommendRoute', 'stations', 'driver', 'markers'].map(name => [name, group()])),
        stationMarkers: new Map(), candidateBadgeMarkers: []
    });
    globalThis.L = { polyline: coords => ({ coords, addTo(layer) { layer.addLayer(this); return this; } }) };
    const navigationRoute = [[21.02, 105.85], [21.03, 105.86]];
    const driver = Object.assign(Object.create(DriverModeController.prototype), {
        map, stations: [], currentTrip: null, customOrigin: null, customDestination: null,
        currentPos: null, matchedPos: null, fullRouteCoords: navigationRoute
    });
    try {
        driver.restoreMapState?.();
        assert.equal(map.layers.markers.layers.size, 0, 'Simulation endpoints are removed');
        assert.equal(map.layers.recommendRoute.layers.size, 0, 'Simulation diversion is removed');
        assert.equal(map.layers.directRoute.layers.size, 2);
        assert.deepEqual([...map.layers.directRoute.layers][1].coords, navigationRoute);
        driver._navigationLocked = true;
        driver.lastDiversionLeg1 = { geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@' };
        driver.lastDiversionLeg2 = { geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@' };
        driver.restoreMapState();
        assert.equal(map.layers.recommendRoute.layers.size, 0, 'locked navigation ignores stale diversion caches');
        assert.deepEqual([...map.layers.directRoute.layers][1].coords, navigationRoute);
    } finally {
        if (priorLeaflet === undefined) delete globalThis.L;
        else globalThis.L = priorLeaflet;
    }
});

test('Debug scenario and vehicle controls escape external identifiers and presentation fields', () => {
    const priorDocument = globalThis.document;
    const scenarioList = { innerHTML: '', querySelectorAll: () => [] };
    const vehicleSelect = { innerHTML: '' };
    const description = { innerHTML: '' };
    const elements = { 'sim-scenarios-container': scenarioList, 'sim-vehicle-select': vehicleSelect,
        'sim-scenario-desc': description };
    globalThis.document = { getElementById: id => elements[id] || null };
    const simulation = new SimModeController({}, {});
    const attack = '<img src=x onerror=alert(1)>';
    const identifier = '" onmouseover="alert(2)';
    simulation.setCatalogs([{ id: identifier, title: attack, tag: identifier, description: attack }],
        [{ vehicle_id: identifier, vehicle_model: attack, vehicle_type: 'EV_CAR', usable_capacity_kwh: attack }], []);
    try {
        simulation.renderScenarioQuickSelect();
        simulation.renderVehicleSelect();
        simulation.loadScenario(identifier);
        for (const html of [scenarioList.innerHTML, vehicleSelect.innerHTML, description.innerHTML]) {
            assert.doesNotMatch(html, /<img|" onmouseover="/);
            assert.match(html, /&lt;img/);
        }
        assert.match(scenarioList.innerHTML, /data-scenario-id="&quot; onmouseover=&quot;alert\(2\)"/);
        assert.match(vehicleSelect.innerHTML, /value="&quot; onmouseover=&quot;alert\(2\)"/);
    } finally {
        if (priorDocument === undefined) delete globalThis.document;
        else globalThis.document = priorDocument;
    }
});

function fixture() {
    const added = [];
    const frames = [];
    const map = {
        getBounds: () => ({ getWest: () => 0, getEast: () => 10, getSouth: () => 0, getNorth: () => 10 }),
        on() {},
        off() {},
        removeLayer(layer) { layer.removed = true; },
        getSize: () => ({ x: 100, y: 100 })
    };
    const L = {
        layerGroup: () => ({ addTo() { return this; }, clearLayers() { added.length = 0; }, addLayer(layer) { added.push(layer); } }),
        polygon: (coords, options) => ({ coords, options })
    };
    const h3 = {
        isValidCell: cell => /^8\d+11$/.test(cell),
        getResolution: cell => cell.endsWith('11') ? 11 : 10,
        cellToBoundary: () => [[1, 1], [1, 2], [2, 2], [2, 1]]
    };
    const countElement = { textContent: '' };
    const supportElement = { textContent: '' };
    const toggle = Object.assign(new EventTarget(), { checked: false, disabled: true });
    const overlay = new RouteFamiliarityOverlay({
        map, leaflet: L, h3, countElement, supportElement, toggle, maxCells: 2, batchSize: 1,
        requestFrame: callback => {
            const id = (frames.at(-1)?.id || 0) + 1;
            frames.push({ id, callback });
            return id;
        },
        cancelFrame: id => {
            const index = frames.findIndex(frame => frame.id === id);
            if (index >= 0) frames.splice(index, 1);
        }
    });
    return { overlay, added, frames, map, countElement, supportElement, toggle, L, h3 };
}

function simulationFixture() {
    const state = fixture();
    state.overlay.destroy();
    const globals = ['window', 'document', 'requestAnimationFrame', 'cancelAnimationFrame'];
    const prior = globals.map(name => globalThis[name]);
    const elements = Object.fromEntries(['btn-mode-driver', 'btn-mode-sim', 'driver-view-container',
        'driver-map-controls', 'driver-status-badge', 'sim-view-container'].map(id => [id,
        Object.assign(new EventTarget(), { hidden: false, style: {}, classList: { toggle() {} },
            setAttribute(name, value) { this[name] = value; } })]));
    Object.assign(elements, {
        'toggle-route-familiarity': state.toggle,
        'route-familiarity-count': state.countElement,
        'route-familiarity-support': state.supportElement
    });
    Object.assign(state.map, { clearAll() {}, clearRoutes() {}, renderTripEndpoints() {}, renderStations() {},
        fitBoundsToActive() {}, onMapClick() {} });
    state.map.map = state.map;
    globalThis.window = { h3: state.h3, L: state.L };
    globalThis.document = { getElementById: id => elements[id] || null };
    globalThis.requestAnimationFrame = state.overlay.requestFrame;
    globalThis.cancelAnimationFrame = state.overlay.cancelFrame;
    return { ...state, elements, restore() {
        globals.forEach((name, i) => {
            if (prior[i] === undefined) delete globalThis[name];
            else globalThis[name] = prior[i];
        });
    } };
}

test('mode buttons keep H3 cells opt-in in Debug and clear/cancel them on return to Driver', () => {
    const state = simulationFixture();
    const simulation = new SimModeController({}, state.map);
    try {
        simulation.init();
        const { elements, added, frames, toggle } = state;
        const route = { resolution: 11, route_cells: Array.from({ length: 60 }, (_, i) => `8${i}11`) };
        assert.equal(elements['sim-view-container'].hidden, true);
        assert.equal(elements['driver-view-container'].hidden, false);
        simulation.routeFamiliarityOverlay.setRoute(route);
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
        assert.equal(added.length, 0, 'even a hidden checkbox cannot draw cells in Driver');

        elements['btn-mode-sim'].dispatchEvent(new Event('click'));
        assert.equal(elements['sim-view-container'].hidden, false);
        assert.equal(elements['driver-view-container'].hidden, true);
        assert.equal(elements['driver-map-controls'].hidden, true);
        assert.equal(added.length, 0, 'entering Debug still requires opting in');
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
        assert.equal(added.length, 50);
        assert.equal(frames.length, 1);

        elements['btn-mode-driver'].dispatchEvent(new Event('click'));
        assert.equal(elements['sim-view-container'].hidden, true);
        assert.equal(elements['driver-map-controls'].hidden, false);
        assert.equal(added.length, 0);
        assert.equal(frames.length, 0, 'pending polygon batches are canceled');
        assert.equal(toggle.checked, false);
        simulation.routeFamiliarityOverlay.setRoute(route);
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
        assert.equal(added.length, 0, 'late data and hidden controls cannot redraw cells');
        elements['btn-mode-sim'].dispatchEvent(new Event('click'));
        assert.equal(added.length, 0, 'returning to Debug requires a new opt-in');
    } finally {
        simulation.routeFamiliarityOverlay.destroy();
        state.restore();
    }
});

test('leaving Debug discards a pending simulation recommendation before it can update the shared map', async () => {
    const state = simulationFixture();
    let resolveRecommendation;
    const pending = new Promise(resolve => { resolveRecommendation = resolve; });
    const simulation = new SimModeController({
        evaluateAndSearchCandidates: async () => ({ candidates: [] }),
        getRecommendation: () => pending,
        computeRoute: async () => null
    }, state.map);
    simulation.setCatalogs([], [{ vehicle_id: 'V0001', vehicle_type: 'EV_CAR' }], []);
    try {
        simulation.init();
        state.elements['btn-mode-sim'].dispatchEvent(new Event('click'));
        const running = simulation.runSimulation();
        state.elements['btn-mode-driver'].dispatchEvent(new Event('click'));
        resolveRecommendation({ has_recommendation: false, familiarity: { resolution: 11, route_cells: ['8111'] } });
        await running;
        assert.equal(simulation.lastRecommendation, null, 'stale Debug output is discarded');
        assert.equal(state.toggle.disabled, true);
        assert.equal(state.added.length, 0);
        assert.equal(state.elements['sim-view-container'].hidden, true);
    } finally {
        simulation.routeFamiliarityOverlay.destroy();
        state.restore();
    }
});

test('overlay is disabled until opted in and rejects non-resolution-11 or malformed cells', () => {
    const { overlay, added, toggle } = fixture();
    assert.equal(toggle.disabled, true);
    overlay.setRoute({ resolution: 11, route_cells: ['8111', '8bad11', '<img>'] });
    assert.equal(toggle.disabled, false);
    assert.equal(added.length, 0);
    overlay.setEnabled(true);
    assert.equal(added.length, 1);
    overlay.setRoute({ resolution: 10, route_cells: ['810'] });
    assert.equal(added.length, 0);
    assert.equal(toggle.disabled, true);
    overlay.destroy();
});

test('overlay clips to viewport, batches rendering, caps cells with honest counts, and cancels stale work', () => {
    const { overlay, added, frames, countElement, supportElement, toggle } = fixture();
    overlay.setEnabled(true);
    overlay.setRoute({ resolution: 11, route_cells: ['8111', '81211', '81311'] });
    assert.equal(toggle.disabled, false);
    overlay.setRoute({ resolution: 11, route_cells: ['8111', '81211', '81311'],
        personal_trip_count: 2, community_driver_count: 5, community_trip_count: 9 });
    assert.equal(added.length, 1);
    assert.equal(countElement.textContent, 'Showing 2 of 3 route cells (H3-11)');
    assert.equal(supportElement.textContent, 'Personal support: 2 trips · Community support: 5 drivers, 9 trips');
    frames.shift().callback();
    assert.equal(added.length, 2);
    overlay.setRoute({ resolution: 10, route_cells: ['810'] });
    assert.equal(frames.length, 0);
    overlay.destroy();
});

test('demo loads the pinned local H3 UMD and does not depend on an H3 CDN', async () => {
    const index = await readFile(new URL('../../backend/app/static/demo/index.html', import.meta.url), 'utf8');
    const bundle = await readFile(new URL('../../backend/app/static/demo/vendor/h3/h3-js.umd.js', import.meta.url), 'utf8');
    const license = await readFile(new URL('../../backend/app/static/demo/vendor/h3/LICENSE', import.meta.url), 'utf8');
    const version = await readFile(new URL('../../backend/app/static/demo/vendor/h3/VERSION', import.meta.url), 'utf8');
    assert.match(index, /\/demo\/static\/vendor\/h3\/h3-js\.umd\.js/);
    assert.doesNotMatch(index, /unpkg\.com\/h3-js/);
    assert.match(index, /id="route-familiarity-support"/);
    assert.match(bundle, /cellToBoundary/);
    assert.match(bundle, /getResolution/);
    assert.match(license, /Apache License/);
    assert.equal(version.trim(), '4.5.0');
});

test('Simulation Mode connects recommendation cells to the opt-in UI', () => {
    const priorWindow = globalThis.window;
    const priorDocument = globalThis.document;
    const toggle = { checked: false, disabled: true, addEventListener() {} };
    const countElement = { textContent: '' };
    const layers = [];
    const map = {
        getBounds: () => ({ getWest: () => 0, getEast: () => 10, getSouth: () => 0, getNorth: () => 10 }),
        on() {}, off() {}, removeLayer() {}
    };
    globalThis.window = {
        h3: { isValidCell: cell => cell === '8111', getResolution: () => 11,
            cellToBoundary: () => [[1, 1], [1, 2], [2, 2]] },
        L: {
            layerGroup: () => ({ addTo() { return this; }, clearLayers() {}, addLayer(layer) { layers.push(layer); } }),
            polygon: coords => ({ coords })
        }
    };
    globalThis.document = { getElementById: id => ({
        'toggle-route-familiarity': toggle, 'route-familiarity-count': countElement
    })[id] || null };
    try {
        const simulation = new SimModeController({}, { map });
        simulation.setActive(true);
        simulation.routeFamiliarityOverlay.setRoute({ resolution: 11, route_cells: ['8111'] });
        assert.equal(toggle.disabled, false);
        assert.equal(countElement.textContent, 'Route cells hidden');
        simulation.routeFamiliarityOverlay.setEnabled(true);
        assert.equal(countElement.textContent, 'Showing 1 of 1 route cells (H3-11)');
        assert.equal(layers.length, 1);
        simulation.routeFamiliarityOverlay.destroy();
    } finally {
        if (priorWindow === undefined) delete globalThis.window;
        else globalThis.window = priorWindow;
        if (priorDocument === undefined) delete globalThis.document;
        else globalThis.document = priorDocument;
    }
});

test('Simulation Mode sends the selected scenario identity and displays returned support safely', async () => {
    const priorWindow = globalThis.window;
    const priorDocument = globalThis.document;
    const toggle = { checked: false, disabled: true, addEventListener() {} };
    const countElement = { textContent: '' };
    const supportElement = { textContent: '' };
    const layers = [];
    const map = {
        getBounds: () => ({ getWest: () => 0, getEast: () => 10, getSouth: () => 0, getNorth: () => 10 }),
        on() {}, off() {}, removeLayer() {}, clearAll() {}, clearRoutes() {}, renderTripEndpoints() {},
        renderStations() {}, fitBoundsToActive() {}
    };
    map.map = map;
    globalThis.window = {
        h3: { isValidCell: cell => cell === '8111', getResolution: () => 11,
            cellToBoundary: () => [[1, 1], [1, 2], [2, 2]] },
        L: {
            layerGroup: () => ({ addTo() { return this; }, clearLayers() {}, addLayer(layer) { layers.push(layer); } }),
            polygon: coords => ({ coords })
        }
    };
    globalThis.document = { getElementById: id => ({
        'toggle-route-familiarity': toggle,
        'route-familiarity-count': countElement,
        'route-familiarity-support': supportElement
    })[id] || null };
    let sent;
    const scenario = { driver_id: 'D0001' };
    const result = { has_recommendation: false, familiarity: {
        resolution: 11, route_cells: ['8111'], personal_trip_count: 2,
        community_driver_count: null, community_trip_count: null
    } };
    const api = {
        evaluateAndSearchCandidates: async () => ({ candidates: [] }),
        getRecommendation: async payload => { sent = payload; return result; },
        computeRoute: async () => null
    };
    try {
        const simulation = new SimModeController(api, map, { onStateUpdate() {} });
        simulation.setActive(true);
        simulation.setCatalogs([scenario], [{ vehicle_id: 'V0001', vehicle_type: 'EV_CAR' }], []);
        simulation.activeScenario = scenario;
        await simulation.runSimulation();
        assert.equal(sent.context.driver_id, scenario.driver_id);
        assert.equal('identity_signature' in sent, false, 'the browser does not sign identities');
        assert.equal(toggle.disabled, false);
        assert.equal(supportElement.textContent,
            'Personal support: 2 trips · Community support: suppressed/unavailable');
        assert.equal(layers.length, 0, 'cells remain opt-in');
        simulation.routeFamiliarityOverlay.destroy();
    } finally {
        if (priorWindow === undefined) delete globalThis.window;
        else globalThis.window = priorWindow;
        if (priorDocument === undefined) delete globalThis.document;
        else globalThis.document = priorDocument;
    }
});
