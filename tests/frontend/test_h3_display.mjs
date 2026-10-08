import test from 'node:test';
import assert from 'node:assert/strict';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

/**
 * H3 Display-Only Layer Tests
 *
 * These tests verify that the H3 overlay in Driver Mode:
 * - Does NOT call any API endpoints
 * - Does NOT modify selectedStationId
 * - Clears old cells when route changes
 */

// ─── Fixtures ────────────────────────────────────────────────────────────

function createOverlayFixture() {
    const added = [];
    const frames = [];
    const map = {
        getBounds: () => ({
            getWest: () => 105.7, getEast: () => 106.0,
            getSouth: () => 20.9, getNorth: () => 21.1
        }),
        on() {}, off() {}, removeLayer(layer) { layer.removed = true; }
    };
    const L = {
        layerGroup: () => ({
            addTo() { return this; },
            clearLayers() { added.length = 0; },
            addLayer(layer) { added.push(layer); },
            getLayers() { return added; }
        }),
        polygon: (coords, options) => ({ coords, options })
    };
    const h3 = {
        isValidCell: cell => typeof cell === 'string' && /^8[a-f0-9]+11$/.test(cell),
        getResolution: cell => cell?.endsWith('11') ? 11 : 10,
        latLngToCell: (lat, lng, resolution) => `8${Math.abs(Math.floor(lat * 100) + Math.floor(lng * 100))}11`,
        cellToBoundary: (cell) => {
            // Extract coords from cell ID to create a proper boundary
            const num = parseInt(cell.replace(/^8/, '').replace(/11$/, ''), 10);
            const lat = 21.0 + (num % 100) * 0.001;
            const lng = 105.8 + (num % 100) * 0.001;
            return [
                [lat, lng], [lat + 0.001, lng], [lat + 0.001, lng + 0.001], [lat, lng + 0.001]
            ];
        }
    };
    const countElement = { textContent: '' };
    const supportElement = { textContent: '' };
    const toggle = Object.assign(new EventTarget(), { checked: false, disabled: true });

    const overlay = new RouteFamiliarityOverlay({
        map, leaflet: L, h3, countElement, supportElement, toggle,
        maxCells: 500, batchSize: 10,
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

function createDriverControllerFixture() {
    const { overlay, added, frames, map, countElement, supportElement, toggle, L, h3 } = createOverlayFixture();

    const apiCalls = [];
    const api = {
        getRecommendation: async (payload) => {
            apiCalls.push({ method: 'getRecommendation', payload });
            return { has_recommendation: false, ranked_candidates: [] };
        },
        computeRoute: async (origin, dest, options) => {
            apiCalls.push({ method: 'computeRoute', origin, dest, options });
            return { geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@' };
        },
        evaluateAndSearchCandidates: async (payload) => {
            apiCalls.push({ method: 'evaluateAndSearchCandidates', payload });
            return { candidates: [] };
        }
    };

    const mockMap = {
        map,
        clearAll() {},
        renderTripEndpoints() {},
        renderDirectRoute() {},
        renderStations() {},
        fitBoundsToActive() {},
        updateDirectRoute() {},
        renderRecommendationRoute() {}
    };

    const controller = Object.assign(Object.create(DriverModeController.prototype), {
        api,
        map: mockMap,
        state: 'AVAILABLE',
        directRouteGeometry: [[21.0, 105.8], [21.01, 105.85], [21.02, 105.9]],
        fullRouteCoords: [[21.0, 105.8], [21.01, 105.85], [21.02, 105.9]],
        currentTrip: {
            origin: { latitude: 21.0, longitude: 105.8 },
            destination: { latitude: 21.02, longitude: 105.9 }
        },
        _h3Overlay: overlay,
        _h3Enabled: false,
        _h3Initialized: true,
        _selectedStationId: null,
        _navigationLocked: false,
        bindings: {
            getH3Toggle: () => toggle,
            getH3CountElement: () => countElement,
            getH3SupportElement: () => supportElement
        }
    });

    return { controller, overlay, added, frames, apiCalls, toggle, countElement, map };
}

// ─── Tests ───────────────────────────────────────────────────────────────

test('computeH3CellsFromGeometry returns empty array for invalid input', () => {
    const { overlay } = createOverlayFixture();

    // Test null/undefined
    assert.deepEqual(overlay.computeH3CellsFromGeometry(null), []);
    assert.deepEqual(overlay.computeH3CellsFromGeometry(undefined), []);
    assert.deepEqual(overlay.computeH3CellsFromGeometry([]), []);
    assert.deepEqual(overlay.computeH3CellsFromGeometry([[21.0, 105.8]]), []);

    overlay.destroy();
});

test('computeH3CellsFromGeometry samples along route segments', () => {
    const { overlay, h3 } = createOverlayFixture();

    // Simple 2-point route
    const geometry = [[21.0, 105.8], [21.01, 105.81]];
    const cells = overlay.computeH3CellsFromGeometry(geometry);

    assert.ok(Array.isArray(cells), 'should return array');
    assert.ok(cells.length > 0, 'should have cells for valid route');

    // All cells should be resolution 11
    for (const cell of cells) {
        assert.ok(h3.isValidCell(cell), `cell ${cell} should be valid`);
        assert.equal(h3.getResolution(cell), 11, `cell ${cell} should be resolution 11`);
    }

    overlay.destroy();
});

test('computeH3CellsFromGeometry caps at 500 cells', () => {
    const { overlay } = createOverlayFixture();

    // Very long route that would generate many cells
    const geometry = [];
    for (let i = 0; i < 1000; i++) {
        geometry.push([21.0 + i * 0.001, 105.8 + i * 0.001]);
    }

    const cells = overlay.computeH3CellsFromGeometry(geometry);
    assert.ok(cells.length <= 500, `should cap at 500 cells, got ${cells.length}`);

    overlay.destroy();
});

test('H3 toggle does not call any API endpoint', async () => {
    const { controller, apiCalls, toggle } = createDriverControllerFixture();

    // Toggle H3 on
    toggle.checked = true;
    toggle.dispatchEvent(new Event('change'));

    // Wait briefly for any async operations
    await new Promise(resolve => setTimeout(resolve, 50));

    // Toggle H3 off
    toggle.checked = false;
    toggle.dispatchEvent(new Event('change'));

    await new Promise(resolve => setTimeout(resolve, 50));

    // No API calls should have been made
    assert.deepEqual(apiCalls, [], 'H3 toggle should not call any API endpoint');

    controller._h3Overlay?.destroy();
});

test('H3 toggle does not modify selectedStationId', () => {
    const { controller, toggle } = createDriverControllerFixture();

    // Set initial selected station
    controller._selectedStationId = 'S001';

    // Toggle H3 on
    toggle.checked = true;
    toggle.dispatchEvent(new Event('change'));

    // selectedStationId should remain unchanged
    assert.equal(controller._selectedStationId, 'S001', 'selectedStationId should not change when H3 toggled on');

    // Toggle H3 off
    toggle.checked = false;
    toggle.dispatchEvent(new Event('change'));

    // selectedStationId should still remain unchanged
    assert.equal(controller._selectedStationId, 'S001', 'selectedStationId should not change when H3 toggled off');

    controller._h3Overlay?.destroy();
});

test('changing route removes previous H3 overlay', () => {
    const { controller, overlay, added, toggle } = createDriverControllerFixture();

    // Enable H3 and render cells
    controller._h3Enabled = true;
    overlay.setEnabled(true);

    // Simulate rendering cells
    const initialGeometry = [[21.0, 105.8], [21.01, 105.85]];
    const cells = overlay.computeH3CellsFromGeometry(initialGeometry);
    overlay.renderFromCells(cells);

    const cellsBeforeRouteChange = added.length;
    assert.ok(cellsBeforeRouteChange > 0, 'should have cells before route change');

    // Clear H3 when route changes
    controller._clearH3OnRouteChange();

    // Cells should be cleared
    assert.equal(added.length, 0, 'cells should be cleared after route change');
    assert.equal(controller._h3Enabled, false, 'H3 should be disabled after route change');
    assert.equal(toggle.checked, false, 'toggle should be unchecked after route change');

    overlay.destroy();
});

test('renderFromCells renders cells from geometry without backend calls', () => {
    const { overlay, added, countElement } = createOverlayFixture();

    // Compute cells from geometry
    const geometry = [[21.0, 105.8], [21.01, 105.85], [21.02, 105.9]];
    const cells = overlay.computeH3CellsFromGeometry(geometry);

    // Render the cells
    overlay.setEnabled(true);
    overlay.renderFromCells(cells);

    // Should have rendered cells
    assert.ok(added.length > 0, 'should render polygons');
    assert.ok(countElement.textContent.includes('route cells'), 'count element should be updated');

    overlay.destroy();
});

test('clear() removes all rendered polygons', () => {
    const { overlay, added, countElement } = createOverlayFixture();

    // Render some cells
    const geometry = [[21.0, 105.8], [21.01, 105.85]];
    const cells = overlay.computeH3CellsFromGeometry(geometry);
    overlay.setEnabled(true);
    overlay.renderFromCells(cells);

    assert.ok(added.length > 0, 'should have rendered cells');

    // Clear
    overlay.clear();

    // All cells should be removed
    assert.equal(added.length, 0, 'all cells should be cleared');
    assert.equal(countElement.textContent, 'Route cells hidden', 'count should show hidden');

    overlay.destroy();
});

test('isResolution11Cell correctly identifies H3-11 cells', () => {
    const { overlay } = createOverlayFixture();

    // Valid H3-11 cell - our mock returns 11 for cells ending in '11'
    assert.equal(overlay.isResolution11Cell('81111'), true);

    // Invalid cells
    assert.equal(overlay.isResolution11Cell('81010'), false); // wrong resolution
    assert.equal(overlay.isResolution11Cell('not-a-cell'), false);
    assert.equal(overlay.isResolution11Cell(null), false);
    assert.equal(overlay.isResolution11Cell(undefined), false);
    assert.equal(overlay.isResolution11Cell(''), false);

    overlay.destroy();
});
