import test from 'node:test';
import assert from 'node:assert/strict';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';

function createH3OverlayFixture() {
    const added = [];
    const frames = [];
    const map = {
        getBounds: () => ({
            getWest: () => 105.70,
            getEast: () => 105.90,
            getSouth: () => 20.95,
            getNorth: () => 21.10
        }),
        on() {},
        off() {},
        removeLayer(l) { l.removed = true; },
        getSize: () => ({ x: 1000, y: 800 })
    };
    const L = {
        layerGroup: () => ({
            addTo() { return this; },
            clearLayers() { added.length = 0; },
            addLayer(layer) { added.push(layer); }
        }),
        polygon: (coords, options) => ({ coords, options, bindPopup(fn) { this.popup = fn; } })
    };
    const h3 = {
        isValidCell: cell => typeof cell === 'string' && cell.startsWith('8'),
        getResolution: cell => parseInt(cell[1], 10) || 9,
        cellToBoundary: cell => [[21.0, 105.8], [21.01, 105.8], [21.01, 105.81], [21.0, 105.81]],
        cellToLatLng: cell => [21.005, 105.805],
        latLngToCell: (lat, lng, res) => `8${res}_${lat.toFixed(3)}_${lng.toFixed(3)}`,
        polygonToCells: (coords, res) => [`8${res}_hanoi_1`, `8${res}_hanoi_2`, `8${res}_hanoi_3`]
    };
    const countElement = { textContent: '' };
    const supportElement = { textContent: '' };
    const toggle = Object.assign(new EventTarget(), { checked: false, disabled: false });
    const overlay = new RouteFamiliarityOverlay({
        map, leaflet: L, h3, countElement, supportElement, toggle,
        resolution: 9, maxCells: 100, batchSize: 50,
        requestFrame: cb => { frames.push(cb); return frames.length; },
        cancelFrame: () => {}
    });
    return { overlay, added, frames, map, countElement, supportElement, toggle, L, h3 };
}

test('H3 toggle is enabled on startup without requiring route A or B', () => {
    const { overlay, toggle } = createH3OverlayFixture();
    assert.equal(toggle.disabled, false, 'Toggle should be clickable immediately without route A or B');
    overlay.setEnabled(true);
    assert.equal(overlay.enabled, true, 'Overlay should be enabled');
});

test('H3 without route or history does not generate cells over empty geography', () => {
    const { overlay, added, frames } = createH3OverlayFixture();
    overlay.setEnabled(true);
    // Flush batch rendering
    while (frames.length > 0) frames.shift()();
    assert.equal(added.length, 0, 'No journey evidence means no cells');
});

test('Route deviation calculation colors deviated cells red based on distance', () => {
    const { overlay } = createH3OverlayFixture();
    const proposed = [[21.000, 105.800], [21.050, 105.800]]; // Vertical line along lng 105.800
    
    // Cell 1: very close (< 50m) -> Green
    const metaClose = overlay.computeDeviationCellMetadata('89_close', [21.020, 105.8001], proposed);
    assert.equal(metaClose.tier, 'ON_TRACK');
    assert.equal(metaClose.color, '#10b981'); // Green

    // Cell 2: slight deviation (100m) -> Amber
    const metaSlight = overlay.computeDeviationCellMetadata('89_slight', [21.020, 105.8010], proposed);
    assert.equal(metaSlight.tier, 'DEVIATION_SLIGHT');
    assert.equal(metaSlight.color, '#f59e0b'); // Amber

    // Cell 3: moderate deviation (300m) -> Red
    const metaMod = overlay.computeDeviationCellMetadata('89_mod', [21.020, 105.8030], proposed);
    assert.equal(metaMod.tier, 'DEVIATION_MODERATE');
    assert.equal(metaMod.color, '#ef4444'); // Red

    // Cell 4: severe deviation (800m) -> Deep Crimson
    const metaSevere = overlay.computeDeviationCellMetadata('89_severe', [21.020, 105.8080], proposed);
    assert.equal(metaSevere.tier, 'DEVIATION_SEVERE');
    assert.equal(metaSevere.color, '#991b1b'); // Deep Crimson
});
