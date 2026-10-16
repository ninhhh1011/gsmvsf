import test from 'node:test';
import assert from 'node:assert/strict';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

function createMockH3() {
    return {
        latLngToCell(lat, lng, res) {
            const r = res ?? 9;
            const x = Math.round(lat * 100);
            const y = Math.round(lng * 100);
            return `cell_${r}_${x}_${y}`;
        },
        cellToBoundary(cell) {
            return [[21.0, 105.8], [21.01, 105.8], [21.01, 105.81], [21.0, 105.81]];
        },
        isValidCell(cell) {
            return typeof cell === 'string' && cell.startsWith('cell_');
        },
        getResolution(cell) {
            const parts = cell.split('_');
            return parseInt(parts[1], 10) || 9;
        }
    };
}

function createMockLeaflet() {
    return {
        layerGroup: () => {
            const layers = [];
            return {
                layers,
                addTo: function() { return this; },
                clearLayers: function() { layers.length = 0; },
                addLayer: function(l) { layers.push(l); }
            };
        },
        polygon: (coords, options) => {
            return {
                coords,
                options,
                popup: null,
                bindPopup: function(html) { this.popup = html; return this; }
            };
        }
    };
}

function createMockMap() {
    return {
        getBounds: () => ({
            getWest: () => 105.0,
            getEast: () => 106.0,
            getSouth: () => 20.0,
            getNorth: () => 22.0
        }),
        on: () => {},
        off: () => {},
        removeLayer: () => {}
    };
}

test('RouteFamiliarityOverlay supports dynamic resolutions 8, 9, 10 and shared styling', () => {
    const mockH3 = createMockH3();
    const mockLeaflet = createMockLeaflet();
    const mockMap = createMockMap();

    const overlay = new RouteFamiliarityOverlay({
        map: mockMap,
        leaflet: mockLeaflet,
        h3: mockH3,
        stations: [],
        resolution: 9
    });

    const routeCoords = [[21.02, 105.84], [21.03, 105.85], [21.04, 105.86]];
    const cellsRes9 = overlay.computeH3CellsFromGeometry(routeCoords, 9);
    assert.ok(cellsRes9.length > 0);
    assert.ok(cellsRes9[0].startsWith('cell_9_'));

    const cellsRes8 = overlay.computeH3CellsFromGeometry(routeCoords, 8);
    assert.ok(cellsRes8.length > 0);
    assert.ok(cellsRes8[0].startsWith('cell_8_'));

    const cellsRes10 = overlay.computeH3CellsFromGeometry(routeCoords, 10);
    assert.ok(cellsRes10.length > 0);
    assert.ok(cellsRes10[0].startsWith('cell_10_'));

    overlay.setResolution(10);
    assert.equal(overlay.resolution, 10);

    // Test renderFromCells with shared cells
    const sharedSet = [cellsRes9[0]];
    overlay.renderFromCells(cellsRes9, sharedSet);
    assert.equal(overlay.sharedCellsSet.has(cellsRes9[0]), true);

    const metaShared = overlay.cellMetadata.get(cellsRes9[0]);
    assert.equal(metaShared.tier, 'SHARED');
    assert.equal(metaShared.color, '#10b981');

    if (cellsRes9.length > 1) {
        const metaDivergent = overlay.cellMetadata.get(cellsRes9[1]);
        assert.equal(metaDivergent.tier, 'DIVERGENT');
        assert.equal(metaDivergent.color, '#f59e0b');
    }
});

test('DriverModeController cycles H3 resolution 9 -> 10 -> 8 -> 9', async () => {
    let badgeText = '';
    const bindings = {
        getH3Toggle: () => ({ checked: false }),
        bindH3Toggle: () => {},
        bindH3ResCycle: () => {},
        setH3ResBadgeText: (txt) => { badgeText = txt; },
        setH3ResBadgeVisible: () => {},
        updateH3ComparisonBanner: () => {}
    };

    const controller = new DriverModeController({}, {}, { bindings });
    assert.equal(controller.h3Resolution, 9);

    await controller.cycleH3Resolution();
    assert.equal(controller.h3Resolution, 10);
    assert.equal(badgeText, '⬡ Res 10');

    await controller.cycleH3Resolution();
    assert.equal(controller.h3Resolution, 8);
    assert.equal(badgeText, '⬡ Res 8');

    await controller.cycleH3Resolution();
    assert.equal(controller.h3Resolution, 9);
    assert.equal(badgeText, '⬡ Res 9');
});

import { createCockpitBindings } from '../../backend/app/static/demo/js/ui/cockpit_bindings.js';

test('assignTrip does NOT force viaPoints on Route A and captures actual trajectory coords', async () => {
    let computedRouteWithVia = false;
    let computedRouteOptions = null;
    const mockApiClient = {
        getTrajectory: async (trajId) => [
            { latitude: 21.02, longitude: 105.85, timestamp: '2026-09-01T08:00:00Z', speed_kmh: 30 },
            { latitude: 21.03, longitude: 105.86, timestamp: '2026-09-01T08:01:00Z', speed_kmh: 35 }
        ],
        computeRoute: async (origin, dest, opts, via) => {
            if (via && via.length > 0) computedRouteWithVia = true;
            computedRouteOptions = opts;
            return {
                geometry: '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                distance_m: 5000,
                duration_s: 600
            };
        }
    };

    const mockMapEngine = {
        clearAll: () => {},
        renderDirectRoute: () => {},
        fitBoundsToActive: () => {},
        renderStations: () => {},
        renderTripEndpoints: () => {}
    };

    const bindings = {
        ...createCockpitBindings(),
        setVehicleCatalog: () => {},
        setVehicleSelection: () => {},
        setStatusBadge: () => {},
        updateBattery: () => {},
        renderAvailable: () => {},
        renderTripAssigned: () => {},
        isStationsDrawerOpen: () => false
    };

    const controller = new DriverModeController(mockApiClient, mockMapEngine, { bindings });
    controller.trips = [
        {
            trip_id: 'TRJ0001',
            origin: { latitude: 21.01, longitude: 105.80 },
            destination: { latitude: 21.05, longitude: 105.88 },
            vehicle_id: 'V0001'
        }
    ];

    await controller.assignTrip('TRJ0001');

    assert.equal(computedRouteWithVia, false, 'Route A must be unconstrained without viaPoints');
    assert.ok(controller.actualTrajectoryCoords, 'actualTrajectoryCoords must be populated from GPS dataset');
    assert.equal(controller.actualTrajectoryCoords.length, 2);
    assert.deepEqual(controller.actualTrajectoryCoords[0], [21.02, 105.85]);
});
