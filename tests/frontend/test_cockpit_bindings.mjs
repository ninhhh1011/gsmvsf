import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createCockpitBindings } from '../../backend/app/static/demo/js/ui/cockpit_bindings.js';
import { renderBatteryView, renderActiveCockpitView, renderTripActiveEta } from '../../backend/app/static/demo/js/ui/cockpit_renderer.js';
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

test('incremental active rendering preserves metric units and accessible ETA text', () => {
    const metrics = {
        'val-remaining-dist': element(), 'val-trip-eta': element(), 'val-trip-soc': element(),
        'val-trip-range': element(), 'battery-bar-fill': element(), 'label-soc-slider-val': element()
    };
    const container = { innerHTML: '', querySelector: () => element() };
    const root = { getElementById: id => id === 'driver-panel-content' ? container : metrics[id] || null, querySelectorAll: () => [], activeElement: null };

    createCockpitBindings(root).renderActive('', {
        view: renderActiveCockpitView({ distance: 12.34, eta: '8', soc: 60, range: 42.4 })
    }, {});

    assert.equal(metrics['val-remaining-dist'].innerHTML, '12.3 <small>km</small>');
    assert.equal(metrics['val-trip-eta'].innerHTML, '8 <small>phút</small><span class="sr-only">min</span>');
    assert.equal(metrics['val-trip-range'].innerHTML, '42 <small>km</small>');
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

test('cockpit controller coordinates while bindings only apply renderer output', async () => {
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
    assert.match(bindingSource, /renderAnalysis/);
    assert.doesNotMatch(controllerSource, /recommendation-panel|rec-panel-list|createElement\(/);
    assert.doesNotMatch(bindingSource, /state\.soc\s*[<>=]|\.toFixed\(|#(?:ef4444|f59e0b|10b981)|bg-(?:danger|warning|success)|text-danger/);
    assert.doesNotMatch(controllerSource, /renderRecommendationCard/);
});

test('cockpit renderer owns SOC colors, classes, and active metric formatting', () => {
    const battery = renderBatteryView({ soc: 18, range: 42.4 });
    assert.deepEqual(battery, {
        labelText: '18% (42 km)', labelColor: '#ef4444', socText: '18%',
        socClass: 'stat-value text-danger', rangeText: '42 km',
        batteryWidth: '18%', batteryClass: 'battery-bar-fill bg-danger', sliderValue: '18'
    });
    assert.deepEqual(renderActiveCockpitView({ distance: 12.34, eta: '8', soc: 18, range: 42.4 }), {
        socText: '18%',
        distanceMarkup: '12.3 <small>km</small>', etaMarkup: '8 <small>phút</small><span class="sr-only">min</span>',
        rangeMarkup: '42 <small>km</small>', maxMotorText: '— kW', powerText: '— (không khả dụng)', vehicleText: '—',
        socClass: 'stat-value text-danger', rangeText: '42 km', batteryWidth: '18%',
        batteryClass: 'battery-bar-fill bg-danger', labelText: '18% (42 km)',
        labelColor: '#ef4444', sliderValue: '18'
    });
    assert.equal(renderActiveCockpitView({ distance: 1, eta: '<img>', soc: 18, range: 2 }).etaMarkup, '&lt;img&gt; <small>phút</small><span class="sr-only">min</span>');
    assert.equal(renderTripActiveEta({ ranked_candidates: [{ eta_to_station_s: 300 }] }, 30), '—');
    assert.equal(renderTripActiveEta({ distance_m: 10000, duration_s: 1200 }, 5), '10');
    assert.equal(renderTripActiveEta({ distance_m: 10000, duration_s: 1200 }, 30), '20');
    assert.equal(renderTripActiveEta(null, 30), '—');
});

test('analysis markup survives replay and model values update incrementally', () => {
    const slot = {innerHTML: ''};
    const fields = {'driver-analysis-content': slot, 'driver-panel-content': {querySelector: () => element()}, 'hud-val-max-motor': element(), 'hud-val-instant-power': element(), 'hud-vehicle-model': element()};
    const bindings = createCockpitBindings({getElementById: id => fields[id], querySelectorAll: () => []});
    bindings.renderAnalysis('first', 'TRIP_ACTIVE'); bindings.renderAnalysis('replacement', 'TRIP_ACTIVE');
    assert.equal(slot.innerHTML, 'first');
    bindings.renderAnalysis('replacement', 'TRIP_ACTIVE', renderActiveCockpitView({distance: 3, eta: '5', soc: 50, range: 80, maxMotorPowerKw: 150, currentInstantPowerKw: null, vehicleModel: 'VF 6'}));
    assert.equal(slot.innerHTML, 'first');
    assert.equal(fields['hud-val-max-motor'].textContent, '150 kW');
    assert.equal(fields['hud-vehicle-model'].textContent, 'VF 6');
    bindings.renderActive('', {view: renderActiveCockpitView({distance: 3, eta: '5', soc: 50, range: 80, maxMotorPowerKw: 100, currentInstantPowerKw: 4.2, vehicleModel: 'VF 5'})}, {});
    assert.equal(fields['hud-val-max-motor'].textContent, '100 kW');
    assert.equal(fields['hud-val-instant-power'].textContent, '4.2 kW (ước tính)');
    assert.equal(fields['hud-vehicle-model'].textContent, 'VF 5');
    bindings.renderAnalysis('next', 'TRIP_ASSIGNED'); assert.equal(slot.innerHTML, 'next');
});

test('sheet toggle exposes its state and drawer toggles the mobile layout class', () => {
    const toggle = element({expandedLabel: 'Thu gọn', collapsedLabel: 'Mở rộng'});
    toggle.setAttribute = (name, value) => { toggle[name] = value; };
    let expanded = false;
    const panel = {classList: {toggle() { expanded = !expanded; return expanded; }}};
    const drawer = element();
    const bodyClasses = [];
    const elements = {'btn-driver-sheet-toggle': toggle, 'driver-view-container': panel, 'stations-drawer': drawer};
    const bindings = createCockpitBindings({getElementById: id => elements[id], querySelectorAll: () => [], body: {classList: {toggle: (...args) => bodyClasses.push(args)}}});
    bindings.bindGlobalControls({});
    toggle.fire('click'); assert.equal(toggle['aria-expanded'], 'true'); assert.equal(toggle.textContent, 'Thu gọn');
    toggle.fire('click'); assert.equal(toggle['aria-expanded'], 'false'); assert.equal(toggle.textContent, 'Mở rộng');
    bindings.setStationsDrawerOpen(true); assert.equal(drawer.style.display, 'flex');
    bindings.setStationsDrawerOpen(false); assert.equal(drawer.style.display, 'none');
    assert.deepEqual(bodyClasses, [['station-drawer-open', true], ['station-drawer-open', false]]);
});

test('rerendering assigned primary card does not duplicate persistent analysis slider listeners', () => {
    const slider = element();
    let subscriptions = 0;
    slider.addEventListener = () => { subscriptions++; };
    const elements = {'driver-panel-content': {innerHTML: ''}, 'slider-assigned-soc': slider};
    const bindings = createCockpitBindings({getElementById: id => elements[id], querySelectorAll: () => []});
    bindings.renderAssigned('first', {}); bindings.renderAssigned('model changed', {});
    assert.equal(subscriptions, 2);
});

test('drawer refresh preserves the expanded catalog and its scroll position', () => {
 let details={open:true};
 const list={scrollTop:80,querySelector:()=>details,querySelectorAll:()=>[],set innerHTML(value){details={open:false};this.scrollTop=0;}};
 const root={getElementById:id=>id==='stations-drawer-list'?list:null,querySelectorAll:()=>[]};
 createCockpitBindings(root).renderDrawer('new ranking',3,{});
 assert.equal(details.open,true);
 assert.equal(list.scrollTop,80);
});

test('station intent labels describe optional and completed passenger goal',()=>{
 const elements=Object.fromEntries(['tab-intent-dest','btn-clear-custom-dest','station-enroute-label','station-enroute-path'].map(id=>[id,element()]));
 const bindings=createCockpitBindings({getElementById:id=>elements[id],querySelectorAll:()=>[]});
 bindings.setAfterDestinationEnabled(false);
 assert.equal(elements['station-enroute-path'].textContent,'A ➔ Trạm');
 assert.equal(elements['btn-clear-custom-dest'].style.display,'none');
 assert.equal(elements['tab-intent-dest'].disabled,true);
 bindings.setAfterDestinationEnabled(true);
 assert.equal(elements['station-enroute-path'].textContent,'A ➔ Trạm ➔ B');
 assert.equal(elements['btn-clear-custom-dest'].style.display,'');
 assert.equal(elements['tab-intent-dest'].disabled,false);
 bindings.setAfterDestinationEnabled(false,true);
 assert.equal(elements['station-enroute-path'].textContent,'A ➔ Trạm');
 assert.equal(elements['tab-intent-dest'].disabled,true,'already passed B cannot be scheduled again');
});
