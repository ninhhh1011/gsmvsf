import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createCockpitBindings } from '../../backend/app/static/demo/js/ui/cockpit_bindings.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

function element(dataset = {}) {
    const listeners = {};
    return {
        dataset, style: {}, classList: { add() {}, remove() {}, toggle() {} },
        addEventListener(type, callback) { listeners[type] = callback; },
        fire(type, event = {}) { listeners[type]?.({ currentTarget: this, target: this, preventDefault() {}, stopPropagation() {}, ...event }); }
    };
}

test('cockpit bindings translate browser events into semantic callbacks', () => {
    const vehicle = element();
    const origin = element();
    const intent = element({ intent: 'AT_DESTINATION' });
    const filter = element({ filter: 'CHARGING' });
    const elements = {
        'cockpit-vehicle-select': vehicle,
        'btn-pick-custom-origin': origin
    };
    const selectors = {
        '.charging-intent-selector .intent-tab': [intent],
        '.drawer-filters .filter-tab': [filter]
    };
    const root = {
        getElementById: id => elements[id] || null,
        querySelectorAll: selector => selectors[selector] || []
    };
    const events = [];
    const bindings = createCockpitBindings(root);
    bindings.bindGlobalControls({
        selectVehicle: value => events.push(['vehicle', value]),
        pickOrigin: () => events.push(['origin']),
        changeIntent: value => events.push(['intent', value]),
        changeFilter: value => events.push(['filter', value])
    });

    vehicle.value = 'MODEL_X'; vehicle.fire('change');
    origin.fire('click');
    intent.fire('click');
    filter.fire('click');
    assert.deepEqual(events, [['vehicle', 'MODEL_X'], ['origin'], ['intent', 'AT_DESTINATION'], ['filter', 'CHARGING']]);
});

test('active cockpit binds change station to the semantic unlock callback', () => {
    const button = element();
    const container = { innerHTML: '', querySelector: () => null };
    const root = {
        getElementById: id => id === 'driver-panel-content' ? container : id === 'btn-change-station' ? button : null,
        querySelectorAll: () => []
    };
    let unlocks = 0;
    createCockpitBindings(root).renderActive('<button id="btn-change-station"></button>', {}, {
        unlockNavigation: () => { unlocks += 1; }
    });
    button.fire('click');
    assert.equal(unlocks, 1);
});

test('controller delegates recommendation panel rendering and selection to bindings', () => {
    const calls = [];
    const controller = Object.create(DriverModeController.prototype);
    Object.assign(controller, {
        _navigationLocked: false,
        stations: [],
        bindings: {
            hideRecommendationPanel() {},
            showRecommendationPanel(html, callbacks) {
                calls.push(['show', html]);
                callbacks.selectStation('ST_1');
            }
        },
        _selectStationAndNavigate: id => calls.push(['select', id])
    });
    const candidates = [{ station_id: 'ST_1' }];
    controller._showRecommendationPanel(candidates);
    assert.equal(calls[0][0], 'show');
    assert.match(calls[0][1], /rec-panel-list/);
    assert.deepEqual(calls[1], ['select', 'ST_1']);
});

test('controller escapes externally supplied road identity before handing position markup to bindings', () => {
    let positionMarkup = '';
    const controller = Object.create(DriverModeController.prototype);
    Object.assign(controller, {
        lastRecommendation: null, remainingTripDistanceKm: 0,
        matchedPos: { road_segment_id: '<img src=x onerror=alert(1)>' }, currentPos: null,
        replay: { getProgressText: () => '', isPlaying: false, currentIndex: 0 },
        currentSocPct: 60, estimatedRangeKm: 120, _navigationLocked: false,
        bindings: { renderActive(html, state) { positionMarkup = state.posStatus; } }
    });
    controller.renderTripActiveUI();
    assert.match(positionMarkup, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(positionMarkup, /<img src=x/);
});

test('cockpit controller stays a coordinator and recommendation panel presentation stays in bindings', async () => {
    const controllerSource = await readFile(new URL('../../backend/app/static/demo/js/ui/driver_controller.js', import.meta.url), 'utf8');
    const bindingSource = await readFile(new URL('../../backend/app/static/demo/js/ui/cockpit_bindings.js', import.meta.url), 'utf8');
    const entrypointSource = await readFile(new URL('../../backend/app/static/demo/js/driver_mode.js', import.meta.url), 'utf8');
    const domainFiles = (await readdir(new URL('../../backend/app/static/demo/js/domain/', import.meta.url)))
        .filter(name => name.endsWith('.js'));
    const domainSources = await Promise.all(domainFiles.map(name => readFile(new URL(`../../backend/app/static/demo/js/domain/${name}`, import.meta.url), 'utf8')));
    assert.ok(controllerSource.split('\n').length <= 1600, 'controller remains below the stable cockpit coordination ceiling');
    assert.doesNotMatch(controllerSource, /\b(?:document|window)\b|getElementById|querySelector|addEventListener/);
    assert.doesNotMatch(controllerSource, /<\s*(?:div|span|button|strong)\b|post-trip-banner|text-success/);
    assert.doesNotMatch(domainSources.join('\n'), /\b(?:document|window)\b|getElementById|querySelector|addEventListener/);
    assert.ok(entrypointSource.split('\n').length <= 400, 'driver_mode remains a thin entry point');
    assert.doesNotMatch(entrypointSource, /recommendation-panel|rec-panel-list|renderDriverRecommendation/);
    assert.match(bindingSource, /showRecommendationPanel/);
    assert.doesNotMatch(controllerSource, /recommendation-panel|rec-panel-list|createElement\(/);
});
