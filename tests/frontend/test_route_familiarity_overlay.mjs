import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { SimModeController } from '../../backend/app/static/demo/js/sim_mode.js';

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
    const toggle = { checked: false, disabled: true, addEventListener() {} };
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
    return { overlay, added, frames, map, countElement, supportElement, toggle };
}

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
    globalThis.document = { getElementById: id => id === 'toggle-route-familiarity' ? toggle : countElement };
    try {
        const simulation = new SimModeController({}, { map });
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
