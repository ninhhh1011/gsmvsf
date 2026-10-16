import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyEnergyWarning, renderEnergyWarningBanner } from '../../backend/app/static/demo/js/components.js';
import { DriverModeController, DriverState } from '../../backend/app/static/demo/js/ui/driver_controller.js';

test('manual station request with enough energy does not become a low-reserve warning', () => {
    const context = {need_service: true, reason_code: 'VALID_REQUEST', current_soc_pct: 84,
        energy_assessment: {need_service: false, warning_level: 'SAFE', reason_code: 'SUFFICIENT_SOC_RANGE'}};
    assert.equal(classifyEnergyWarning(context).level, 'SAFE');
    const html = renderEnergyWarningBanner(context);
    assert.doesNotMatch(html, /Dự phòng năng lượng thấp|VALID_REQUEST/);
});

test('physical danger takes priority over a valid driver request', () => {
    assert.equal(classifyEnergyWarning({need_service: true, reason_code: 'VALID_REQUEST',
        energy_assessment: {need_service: true, warning_level: 'CRITICAL', reason_code: 'LOW_SOC_AND_INSUFFICIENT_RANGE'}}).level, 'CRITICAL');
});

test('low SOC and insufficient reserve are distinct messages', () => {
    const warning = reason_code => classifyEnergyWarning({reason_code:'VALID_REQUEST',
        energy_assessment: {warning_level:'ADVISORY', reason_code}});
    assert.equal(warning('LOW_SOC').title, 'Mức pin thấp');
    assert.equal(warning('INSUFFICIENT_POST_DESTINATION_RESERVE').title, 'Dự phòng năng lượng thấp');
});

test('missing, invalid and legacy driver-intent assessments never assert a safe battery', () => {
    for (const context of [null, {need_service:true,reason_code:'VALID_REQUEST'},
        {need_service:false,reason_code:'MISSING_DATA'}, {need_service:false,reason_code:'INVALID_STATE'}]) {
        assert.equal(classifyEnergyWarning(context).level, 'UNAVAILABLE');
    }
});

function driver(api) {
    const c = new DriverModeController(api, {clearRecommendationRoute(){},renderStations(){}}, {bindings: {updateBattery(){}, isStationsDrawerOpen:()=>false}});
    c.state = DriverState.TRIP_ACTIVE;
    c.currentVehicle = {vehicle_id:'V0001',vehicle_model:'VF_3',usable_capacity_kwh:17.15,consumption_wh_per_km:95};
    c.currentTrip = {destination:{latitude:21,longitude:105}};
    c.currentPos = {latitude:21.01,longitude:105.01};
    c.remainingTripDistanceKm = 34.6;
    c.renderTripActiveUI = () => {};
    return c;
}

test('locked navigation still refreshes physical energy without reranking the selected station', async () => {
    let demands = 0;
    const energy = {energy_assessment:{warning_level:'SAFE',reason_code:'SUFFICIENT_SOC_RANGE'}};
    const c = driver({evaluateDemand:async()=>{demands++; return energy;}, getRecommendation:()=>{throw new Error('must not rerank');}});
    const ranked = [{station_id:'S001'}];
    c.lastRecommendation = {ranked_candidates:ranked,energy_context:{reason_code:'LOW_SOC'}};
    c._navigationLocked = true;
    c._selectedStationId = 'S001';
    await c._evaluateAtCurrentPosition();
    assert.equal(demands,1);
    assert.equal(c.lastRecommendation.energy_context,energy);
    assert.equal(c.lastRecommendation.ranked_candidates,ranked);
    assert.equal(c._selectedStationId,'S001');
});

test('old SOC request cannot replace energy information after the SOC changes', async () => {
    let finish;
    const c = driver({getRecommendation:()=>new Promise(resolve=>{finish=resolve;})});
    const pending = c._evaluateAtCurrentPosition();
    c.setBatterySoc(84,false);
    const latest = {has_recommendation:false,energy_context:{energy_assessment:{warning_level:'SAFE',reason_code:'SUFFICIENT_SOC_RANGE'}}};
    c.lastRecommendation = latest;
    finish({has_recommendation:false,energy_context:{reason_code:'LOW_SOC'}});
    await pending;
    assert.equal(c.lastRecommendation,latest);
});

test('failed old SOC request cannot clear a newer energy assessment', async () => {
    let fail;
    const c = driver({getRecommendation:()=>new Promise((_,reject)=>{fail=reject;})});
    const pending = c._evaluateAtCurrentPosition();
    c.setBatterySoc(84,false);
    const latest = {energy_context:{energy_assessment:{warning_level:'SAFE',reason_code:'SUFFICIENT_SOC_RANGE'}}};
    c.lastRecommendation = latest;
    fail(new Error('old request failed'));
    await pending;
    assert.equal(c.lastRecommendation,latest);
});

test('drawer reply from an old SOC cannot restore a stale warning', async () => {
    let finish;
    const c = driver({evaluateAndSearchCandidates:async()=>({candidates:[]}),
        getRecommendation:()=>new Promise(resolve=>{finish=resolve;})});
    c.renderStationsDrawer = () => {};
    const pending = c.refreshDrawerEvaluations();
    c.setBatterySoc(84,false);
    const latest = {ranked_candidates:[], energy_context:{energy_assessment:{warning_level:'SAFE',reason_code:'SUFFICIENT_SOC_RANGE'}}};
    c.lastRecommendation = latest;
    finish({ranked_candidates:[], energy_context:{reason_code:'LOW_SOC'}});
    await pending;
    assert.equal(c.lastRecommendation,latest);
});

test('overlapping drawer refreshes retain the latest reply', async () => {
    const replies = [];
    const c = driver({evaluateAndSearchCandidates:async()=>({candidates:[]}),
        getRecommendation:()=>new Promise(resolve=>{replies.push(resolve);})});
    c.renderStationsDrawer = () => {};
    const old = c.refreshDrawerEvaluations();
    const fresh = c.refreshDrawerEvaluations();
    const latest = {ranked_candidates:[],energy_context:{reason_code:'SUFFICIENT_SOC_RANGE'}};
    replies[1](latest);
    await fresh;
    replies[0]({ranked_candidates:[],energy_context:{reason_code:'LOW_SOC'}});
    await old;
    assert.equal(c.lastRecommendation,latest);
});

test('accepted replay power invalidates an outstanding energy assessment', async () => {
    let finish;
    const c = driver({evaluateDemand:()=>new Promise(resolve=>{finish=resolve;}),
        computePowerStep:async()=>({current_soc_pct:12,estimated_range_km:10,instantaneous_power_kw:1,power_status:'AVAILABLE'})});
    c._navigationLocked = true;
    const pending = c._evaluateAtCurrentPosition();
    await c._updateReplayPower({timestamp:'2026-10-12T00:00:00Z',speed_kmh:20},c.generation);
    const old = {energy_assessment:{warning_level:'SAFE',reason_code:'SUFFICIENT_SOC_RANGE'}};
    finish(old);
    await pending;
    assert.equal(c.currentSocPct,12);
    assert.notEqual(c.lastRecommendation?.energy_context,old);
});
