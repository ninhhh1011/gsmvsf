import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { RouteFamiliarityOverlay } from '../../backend/app/static/demo/js/ui/route_familiarity_overlay.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

const context = {};
vm.runInNewContext(readFileSync('backend/app/static/demo/vendor/h3/h3-js.umd.js', 'utf8'), context);
const h3 = context.h3;

function fixture(loadHeatmap = async ({ resolution }) => ({ status: 'NO_PAIRED_EVIDENCE', resolution, cells: {} })) {
    const added = [], frames = [], handlers = {};
    let bounds = [20.8, 21.3, 105.5, 106.1];
    const map = {
        getBounds: () => ({ getSouth: () => bounds[0], getNorth: () => bounds[1], getWest: () => bounds[2], getEast: () => bounds[3] }),
        on: (event, fn) => { handlers[event] = fn; }, off() {}, removeLayer() {}
    };
    const leaflet = {
        layerGroup: () => ({ addTo() { return this; }, clearLayers() { added.length = 0; }, addLayer(x) { added.push(x); } }),
        polygon: (coords, options) => ({ coords, options, bindPopup(text) { this.popup = text; } })
    };
    const countElement = { textContent: '' }, supportElement = { textContent: '' };
    const overlay = new RouteFamiliarityOverlay({ map, leaflet, h3, countElement, supportElement,
        loadHeatmap, requestFrame: fn => { frames.push(fn); return frames.length; }, cancelFrame() {} });
    return { overlay, added, countElement, supportElement, map, handlers, setBounds: value => { bounds = value; },
        flush: () => { while (frames.length) frames.shift()(); } };
}

test('missing journey evidence never creates geographic grid cells or changes requested resolution', async () => {
    const f = fixture();
    await f.overlay.showDepartureHeatmap();
    f.flush();
    assert.equal(f.added.length, 0);
    assert.equal(f.overlay.route.resolution, 9);
    assert.deepEqual(f.overlay.route.route_cells, []);
    assert.match(f.supportElement.textContent, /Chưa có.*cặp/i);
});

test('backend departure percentages and event counts replace visit frequency and familiarity', async () => {
    const f = fixture(async ({ resolution }) => {
        const cell = h3.latLngToCell(21, 105.8, resolution);
        return { status: 'AVAILABLE', resolution, source: 'synthetic', as_of_iso: '2026-10-14T00:00:00Z',
            excluded_unpaired_trip_count: 42, cells: { [cell]: { eligible_trip_count: 100, departing_trip_count: 20,
                departure_event_count: 28, departure_pct: 20, color: '#ef4444' } } };
    });
    await f.overlay.showDepartureHeatmap(); f.flush();
    const red = f.added.find(p => p.options.fillColor === '#ef4444');
    assert.ok(red);
    assert.match(red.popup, /20%/); assert.match(red.popup, /20\/100/); assert.match(red.popup, /28/);
    assert.doesNotMatch(red.popup, /độ quen|Tần suất xe/i);
    assert.match(f.supportElement.textContent, /giả lập/i);
    assert.match(f.supportElement.textContent, /42/);
});

test('legacy journey footprints are gray and visits never appear as a departure percentage', async () => {
    const cell = h3.latLngToCell(21, 105.8, 9);
    const f = fixture(async ({ resolution }) => ({ status: 'HISTORY_ONLY', resolution, source: 'synthetic',
        excluded_unpaired_trip_count: 48535, cells: { [cell]: { status: 'HISTORY_ONLY',
            history_trip_count: 1200, departure_pct: null, eligible_trip_count: null,
            departing_trip_count: null, departure_event_count: null, color: '#94a3b8' } } }));
    await f.overlay.showDepartureHeatmap(); f.flush();
    assert.equal(f.added.length, 1);
    assert.equal(f.added[0].options.fillColor, '#94a3b8');
    assert.match(f.added[0].popup, /1200/);
    assert.match(f.added[0].popup, /Chưa đủ bằng chứng/);
    assert.doesNotMatch(f.added[0].popup, /null%|0%|1200%/);
    assert.match(f.supportElement.textContent, /chỉ hiện lịch sử/);
});

test('stale heatmap response cannot replace a newer time or revive a disabled layer', async () => {
    const pending = [];
    const f = fixture(payload => new Promise(resolve => pending.push({ payload, resolve })));
    const first = f.overlay.showDepartureHeatmap('2026-10-13T00:00:00Z');
    const second = f.overlay.showDepartureHeatmap('2026-10-14T00:00:00Z');
    pending[1].resolve({ status: 'AVAILABLE', cells: {}, as_of_iso: pending[1].payload.as_of_iso }); await second;
    pending[0].resolve({ status: 'AVAILABLE', cells: {}, as_of_iso: pending[0].payload.as_of_iso }); await first;
    assert.equal(f.overlay.heatmap.as_of_iso, '2026-10-14T00:00:00Z');
    const third = f.overlay.showDepartureHeatmap();
    f.overlay.setEnabled(false);
    pending[2].resolve({ status: 'AVAILABLE', cells: {} }); await third;
    assert.equal(f.overlay.enabled, false);
    assert.equal(f.added.length, 0);
});

test('panning only clips existing all-region evidence and outage does not manufacture cells', async () => {
    let calls = 0;
    const f = fixture(async () => { calls++; throw new Error('outage'); });
    await f.overlay.showDepartureHeatmap(); f.flush();
    assert.equal(f.added.length, 0);
    assert.match(f.supportElement.textContent, /không khả dụng/i);
    f.setBounds([21.2, 21.4, 105.3, 105.6]);
    await f.handlers.moveend(); f.flush();
    assert.equal(calls, 1);
    assert.deepEqual(f.overlay.route.route_cells, []);
});

test('wide views render only journey-supported cells at the selected resolution', async () => {
    const cells = [h3.latLngToCell(21, 105.8, 9), h3.latLngToCell(21.003, 105.8, 9)];
    const f = fixture(async ({ resolution }) => ({ status: 'AVAILABLE', resolution,
        cells: Object.fromEntries(cells.map(cell => [cell, { eligible_trip_count: 100, departing_trip_count: 20,
            departure_event_count: 28, departure_pct: 20, color: '#ef4444' }])) }));
    await f.overlay.showDepartureHeatmap(); f.flush();
    assert.equal(f.overlay.route.resolution, 9);
    assert.deepEqual(new Set(f.added.map(p => p._cellId)), new Set(cells));
    assert.ok(f.added.every(p => h3.getResolution(p._cellId) === 9));
});

test('departure mode remains citywide with an active route and uses replay observation time', async () => {
    let asOf;
    const controller = Object.assign(Object.create(DriverModeController.prototype), {
        _h3Enabled: true, h3Mode: 'DEPARTURES', h3Resolution: 9,
        currentObservation: { timestamp: '2026-10-14T01:00:00Z' },
        offlineProposedGeometry: [[21, 105.8], [21.1, 105.8]], actualTrajectoryCoords: [[21, 105.8], [21.1, 105.8]],
        _h3Overlay: { showDepartureHeatmap: async value => { asOf = value; } },
        bindings: { updateH3ComparisonBanner() {} }
    });
    await controller.refreshRouteComparison();
    assert.equal(asOf, '2026-10-14T01:00:00Z');
});

test('mode transition invalidates pending departures before comparison finishes or fails', async () => {
    let finishHeatmap, finishComparison;
    const f = fixture(() => new Promise(resolve => { finishHeatmap = resolve; }));
    const pending = f.overlay.showDepartureHeatmap();
    const controller = Object.assign(Object.create(DriverModeController.prototype), {
        _h3Enabled: true, _comparisonRequest: 0, generation: 1, h3Mode: 'DEPARTURES', h3Resolution: 9,
        _h3Overlay: f.overlay, currentVehicle: null,
        offlineProposedGeometry: [[21, 105.8], [21.1, 105.8]], actualTrajectoryCoords: [[21, 105.8], [21.1, 105.8]],
        bindings: { updateH3ComparisonBanner() {}, showH3Toast() {} },
        api: { compareRoutes: () => new Promise((resolve, reject) => { finishComparison = reject; }) }
    });
    const changing = controller.changeH3Mode('COMPARISON');
    finishHeatmap({ status: 'AVAILABLE', cells: {} }); await pending;
    assert.equal(f.overlay.heatmapMode, false);
    finishComparison(new Error('outage')); await changing;
    await f.handlers.moveend();
    assert.equal(f.overlay.heatmapMode, false);
});

test('replay steps refresh departure time without changing the frozen comparison time', async () => {
    const times = [];
    const controller = Object.assign(Object.create(DriverModeController.prototype), {
        state: 'TRIP_ACTIVE', generation: 1, _h3Enabled: true, h3Mode: 'DEPARTURES',
        offlineEvaluationTime: '2026-10-14T00:00:00Z', h3Resolution: 9,
        _h3Overlay: { showDepartureHeatmap: async time => { times.push(time); } },
        bindings: { updateH3ComparisonBanner() {} },
        _updateReplayPower: async () => {}, replay: { isReplayComplete: () => false },
        _evaluateAtCurrentPosition: async () => {}, renderTripActiveUI() {},
        lastEvalTimestamp: Date.now(), lastEvalPos: { latitude: 21, longitude: 105.8 }
    });
    await controller._onReplayStep({ observation: { timestamp: '2026-10-14T01:00:00Z', latitude: 21, longitude: 105.8 } });
    await controller._onReplayStep({ observation: { timestamp: '2026-10-14T02:00:00Z', latitude: 21, longitude: 105.8 } });
    assert.deepEqual(times, ['2026-10-14T01:00:00Z', '2026-10-14T02:00:00Z']);
    assert.equal(controller.offlineEvaluationTime, '2026-10-14T00:00:00Z');
});

test('cancelled replay cannot apply its position after a delayed heatmap', async () => {
    let finish;
    const controller = Object.assign(Object.create(DriverModeController.prototype), {
        state: 'TRIP_ACTIVE', generation: 1, _h3Enabled: true, h3Mode: 'DEPARTURES', h3Resolution: 9,
        currentPos: { latitude: 22, longitude: 106 }, bindings: { updateH3ComparisonBanner() {} },
        _h3Overlay: { showDepartureHeatmap: () => new Promise(resolve => { finish = resolve; }) },
        _updateReplayPower: async () => {}, replay: { isReplayComplete: () => false },
        _evaluateAtCurrentPosition: async () => {}, renderTripActiveUI() {}, lastEvalTimestamp: Date.now()
    });
    const old = controller._onReplayStep({ observation: { timestamp: '2026-10-14T01:00:00Z', latitude: 21, longitude: 105.8 } });
    controller.generation++;
    finish(); await old;
    assert.deepEqual(controller.currentPos, { latitude: 22, longitude: 106 });
});
