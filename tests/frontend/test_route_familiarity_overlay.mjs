import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { DemoMap } from '../../backend/app/static/demo/js/map.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

test('Driver restoration clears prior map content and redraws its existing navigation route', () => {
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
    assert.match(index, /id="h3-comparison-banner"/);
    assert.match(bundle, /cellToBoundary/);
    assert.match(bundle, /getResolution/);
    assert.match(license, /Apache License/);
    assert.equal(version.trim(), '4.5.0');
});
