import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController, DriverState } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { ApiClient } from '../../backend/app/static/demo/js/api.js';
import { registerVehicleModel, MODEL_SPECS } from '../../backend/app/static/demo/js/domain/vehicle_model.js';
const A = [[21,105],[21.01,105.01]];
function fixture(api = {}) {
 const renders = [], banners = [], powers = [];
 const toggle = {checked:true};
 const bindings = {getH3Toggle:()=>toggle,updateH3ComparisonBanner:x=>banners.push(x),setH3Checked:x=>toggle.checked=x,updateInstantaneousPower:x=>powers.push(x)};
 const c = new DriverModeController(api, {}, {bindings});
 c.h3Mode = 'COMPARISON';
 c.offlineProposedGeometry = A; c.directRouteGeometry = [[21.005,105.005],[21.01,105.01]];
 c.actualTrajectoryCoords = A; c._h3Enabled = true;
 c._h3Overlay = {renderFromCells:(...x)=>renders.push(x),setEnabled(){},clear(){},setResolution(){}};
 c.currentVehicle={vehicle_model:'VF_3'}; c.currentTrip={start_time:'2026-09-01T00:00:00Z'};
 return {c,renders,banners,toggle,powers};
}
const response = {shared_pct_on_proposed:82.5,shared_pct_on_actual:78,shared_distance_m:4500,shared_cells:['a'],proposed_cells:['a','b'],actual_cells:['a','c'],shared_segments:[]};
test('offline comparison sends canonical fields, frozen A and backend cell union once', async()=>{
 const payloads=[]; const {c,renders,banners}=fixture({compareRoutes:async p=>{payloads.push(p);return response;}});
 await c.refreshRouteComparison(); await c.refreshRouteComparison();
 assert.deepEqual(payloads,[{proposed_coordinates:A,actual_coordinates:A,resolution:9,as_of_iso:'2026-09-01T00:00:00Z',vehicle_model:'VF_3'}]);
 assert.deepEqual(renders[0], [['a','b','c'],['a'],true]);
 assert.equal(banners[0].sharedDistText,'Chung: 4.5 km');
});
test('comparison never redraws after disabling during await', async()=>{
 let resolve; const {c,renders,toggle}=fixture({compareRoutes:()=>new Promise(r=>resolve=r)});
 const pending=c.refreshRouteComparison(); toggle.checked=false;await c.onToggleH3();resolve(response);await pending;
 assert.equal(renders.length,0);assert.equal(c.latestRouteComparison,null);assert.equal(toggle.checked,false);
});
test('catalog retains physical metadata and nullable unknown capability',()=>{
 registerVehicleModel('CUSTOM',{usable_kwh:20,consumption_wh_km:100,max_motor_power_kw:75,curb_weight_kg:1400,parameter_provenance:{curb_weight_kg:'estimated'}});
 assert.equal(MODEL_SPECS.CUSTOM.max_motor_power_kw,75);assert.equal(MODEL_SPECS.CUSTOM.curb_weight_kg,1400);
 registerVehicleModel('UNKNOWN',{usable_kwh:20,consumption_wh_km:100});assert.equal(MODEL_SPECS.UNKNOWN.max_motor_power_kw,null);
});
test('power-step API sends canonical request',async()=>{
 const api=new ApiClient();let request;api._request=async(...args)=>{request=args;return response;};
 const payload={vehicle_model:'VF_3',speed_kmh:0,dt_seconds:60,current_soc_pct:80};await api.computePowerStep(payload);
 assert.equal(request[0],'/api/v1/vehicles/power-step');assert.deepEqual(JSON.parse(request[1].body),payload);
});
test('power uses accepted intervals, zero and negative estimates without clipping',async()=>{
 const requests=[];const {c,powers}=fixture({computePowerStep:async p=>{requests.push(p);return {instantaneous_power_kw:requests.length===1?0:-3,energy_delta_kwh:-0.1,current_soc_pct:81,estimated_range_km:120,power_status:'MODEL_ESTIMATE',max_motor_power_kw:null};}});
 await c._updateReplayPower({timestamp:'2026-09-01T00:00:00Z',speed_kmh:40},c.generation);
 await c._updateReplayPower({timestamp:'2026-09-01T00:01:00Z',speed_kmh:0},c.generation);
 assert.equal(requests[0].dt_seconds,0);assert.equal(requests[1].dt_seconds,60);assert.equal(requests[1].previous_speed_kmh,40);
 assert.equal(c.currentSocPct,81);assert.match(powers[0],/^0.0 kW/);assert.match(powers[1],/^-3.0 kW/);
});
test('unsupported power remains unavailable with unchanged SOC and stale power ignored',async()=>{
 const {c,powers}=fixture({computePowerStep:async()=>({instantaneous_power_kw:null,energy_delta_kwh:null,current_soc_pct:85,estimated_range_km:100,power_status:'UNSUPPORTED_MODEL',max_motor_power_kw:null})});
 await c._updateReplayPower({timestamp:'2026-09-01T00:00:00Z'},c.generation);
 assert.equal(c.instantaneousPowerKw,null);assert.match(powers[0],/không khả dụng/);
 let resolve;c.api.computePowerStep=()=>new Promise(r=>resolve=r);
 const pending=c._updateReplayPower({timestamp:'2026-09-01T00:01:00Z'},c.generation);c.generation++;resolve({current_soc_pct:0});await pending;assert.equal(c.currentSocPct,85);
});
test('frozen proposed geometry survives navigation slicing and external mutation',()=>{
 const {c}=fixture();const coords=A.map(p=>[...p]);c._captureOfflineProposedGeometry(coords);coords[0][0]=0;c.directRouteGeometry=[];
 assert.deepEqual(c.offlineProposedGeometry,A);assert.equal(Object.isFrozen(c.offlineProposedGeometry[0]),true);
});
test('resolution cycling rejects older comparison results',async()=>{
 const resolvers=[];const {c,renders}=fixture({compareRoutes:p=>new Promise(r=>resolvers.push([p.resolution,r]))});
 const old=c.refreshRouteComparison();const newer=c.cycleH3Resolution();resolvers[0][1](response);await old;assert.equal(renders.length,0);
 resolvers[1][1](response);await newer;assert.equal(renders.length,1);assert.equal(resolvers[1][0],10);
});
test('valid zero overlap remains divergent even beside a station',async()=>{
 const {RouteFamiliarityOverlay}=await import('../../backend/app/static/demo/js/ui/route_familiarity_overlay.js');
 const overlay=Object.assign(Object.create(RouteFamiliarityOverlay.prototype),{active:true,resolution:9,h3:{getResolution:()=>9,cellToLatLng:()=>[21,105]},stations:[{latitude:21,longitude:105}],cellMetadata:new Map(),render(){}});
 overlay.renderFromCells(['a'],[],true);assert.equal(overlay.cellMetadata.get('a').tier,'DIVERGENT');
 overlay.renderFromCells(['a'],overlay.stations);assert.equal(overlay.cellMetadata.get('a').tier,'SAFE');
});
test('disable then enable cannot accept the earlier pending comparison',async()=>{
 const resolvers=[];const {c,renders,toggle}=fixture({compareRoutes:()=>new Promise(r=>resolvers.push(r))});
 const old=c.refreshRouteComparison();toggle.checked=false;await c.onToggleH3();toggle.checked=true;const current=c.onToggleH3();
 resolvers[0](response);await old;assert.equal(renders.length,0);resolvers[1](response);await current;assert.equal(renders.length,1);
});
test('comparison response reused when toggling with unchanged offline inputs',async()=>{
 let calls=0;const {c,toggle,renders}=fixture({compareRoutes:async()=>{calls++;return response;}});
 await c.refreshRouteComparison();toggle.checked=false;await c.onToggleH3();toggle.checked=true;await c.onToggleH3();
 assert.equal(calls,1);assert.equal(renders.length,2);
});
test('assignment clears previous offline evidence and energy before async loading',async()=>{
 let resolve;const {c}=fixture({getTrajectory:()=>new Promise(r=>resolve=r),computeRoute:async()=>null});
 c._lastPowerObservation={timestamp:999,speed:40};c.latestRouteComparison=response;c.userSelectedVehicleModel='VF_3';
 c.trips=[{trip_id:'TRJ_NEW',origin:{},destination:{}}];c.map={clearAll(){},fitBoundsToActive(){}};
 c._renderEndpointsWithDrag=()=>{};c.updateEstimatedRange=()=>{};c.setState=()=>{};c.renderTripAssignedUI=()=>{};
 const pending=c.assignTrip('TRJ_NEW');assert.equal(c._lastPowerObservation,null);assert.equal(c.offlineProposedGeometry,null);assert.equal(c.actualTrajectoryCoords,null);assert.equal(c.latestRouteComparison,null);
 resolve([]);await pending;assert.equal(c.offlineProposedGeometry,null);
});
test('start resets interval history even with the same vehicle model',async()=>{
 let resolve;const {c}=fixture();c._lastPowerObservation={timestamp:999,speed:40};c.currentTrip.trip_id='TRJ_NEW';
 c.setState=()=>{};c.replay.loadTrajectory=()=>new Promise(r=>resolve=r);
 const pending=c.startTrip();assert.equal(c._lastPowerObservation,null);c.generation++;resolve();await pending;
});
test('return clears geometry, comparison and previous power interval',()=>{
 const {c}=fixture();c._lastPowerObservation={timestamp:999,speed:40};c.latestRouteComparison=response;
 c.replay.clearSession=()=>{};c.replay.reset=()=>{};c.map.clearAll=()=>{};c._hideRecommendationPanel=()=>{};c.setState=()=>{};c.renderAvailableUI=()=>{};
 c.returnToAvailable();assert.equal(c.offlineProposedGeometry,null);assert.equal(c.actualTrajectoryCoords,null);assert.equal(c.latestRouteComparison,null);assert.equal(c._lastPowerObservation,null);
});
test('recommendation revision does not discard unchanged offline comparison',async()=>{
 let resolve;const {c,renders}=fixture({compareRoutes:()=>new Promise(r=>resolve=r)});const pending=c.refreshRouteComparison();c.routeRevision++;resolve(response);await pending;assert.equal(renders.length,1);
});
test('SOC editing invalidates pending interval energy response',async()=>{
 let resolve;const {c}=fixture({computePowerStep:()=>new Promise(r=>resolve=r)});c.updateEstimatedRange=()=>{};c.bindings.updateBattery=()=>{};
 const pending=c._updateReplayPower({timestamp:'2026-09-01T00:00:00Z'},c.generation);c.setBatterySoc(60,false);resolve({current_soc_pct:10,estimated_range_km:20,instantaneous_power_kw:2});await pending;
 assert.equal(c.currentSocPct,60);assert.equal(c._lastPowerObservation,null);
});
test('model switch round trip invalidates pending interval energy response',async()=>{
 let resolve;const {c}=fixture({computePowerStep:()=>new Promise(r=>resolve=r)});c.updateEstimatedRange=()=>{};c.renderCurrentStateUI=()=>{};c.bindings.setVehicleSelection=()=>{};c.bindings.isStationsDrawerOpen=()=>false;
 c.currentTrip=null;
 const pending=c._updateReplayPower({timestamp:'2026-09-01T00:00:00Z'},c.generation);c.selectVehicleModel('VF_5');c.selectVehicleModel('VF_3');resolve({current_soc_pct:10,estimated_range_km:20,instantaneous_power_kw:2});await pending;
 assert.equal(c.currentSocPct,85);assert.equal(c._lastPowerObservation,null);
});
test('offline comparison freezes first observed trip time despite later replay observations',async()=>{
 const payloads=[];const {c}=fixture({getTrajectory:async()=>[{latitude:21,longitude:105,timestamp:'2026-09-01T00:00:00Z'},{latitude:21.01,longitude:105.01,timestamp:'2026-09-01T00:01:00Z'}],computeRoute:async()=>null,compareRoutes:async p=>{payloads.push(p);return response;}});
 c.userSelectedVehicleModel='VF_3';c.trips=[{trip_id:'TRJ_NEW',origin:{},destination:{}}];c.map={clearAll(){},fitBoundsToActive(){}};
 c._renderEndpointsWithDrag=()=>{};c.updateEstimatedRange=()=>{};c.setState=()=>{};c.renderTripAssignedUI=()=>{};
 await c.assignTrip('TRJ_NEW');c._captureOfflineProposedGeometry(A);c._h3Enabled=true;
 c.currentObservation={timestamp:'2026-09-01T00:30:00Z'};await c.refreshRouteComparison();
 c.currentObservation={timestamp:'2026-09-01T01:00:00Z'};await c.refreshRouteComparison();
 assert.equal(payloads.length,1);assert.equal(payloads[0].as_of_iso,'2026-09-01T00:00:00Z');
});
test('comparison omits unavailable vehicle model rather than sending null',async()=>{
 let payload;const {c}=fixture({compareRoutes:async p=>{payload=p;return response;}});c.currentVehicle=null;await c.refreshRouteComparison();assert.equal(Object.hasOwn(payload,'vehicle_model'),false);
});
for (const change of ['soc','model']) test(`rejected stale power request after ${change} change cannot publish state`,async()=>{
 let reject;const {c,powers}=fixture({computePowerStep:()=>new Promise((_,r)=>reject=r)});
 c.currentTrip=null;
 c.updateEstimatedRange=()=>{};c.renderCurrentStateUI=()=>{};c.bindings.updateBattery=()=>{};c.bindings.setVehicleSelection=()=>{};c.bindings.isStationsDrawerOpen=()=>false;
 const pending=c._updateReplayPower({timestamp:'2026-09-01T00:00:00Z'},c.generation);
 if(change==='soc')c.setBatterySoc(60,false);else {c.selectVehicleModel('VF_5');c.selectVehicleModel('VF_3');}
 c.powerStatus='MODEL_ESTIMATE';c.instantaneousPowerKw=4;
 reject(new Error('old request failed'));await pending;
 assert.equal(c._lastPowerObservation,null);assert.equal(c.powerStatus,'MODEL_ESTIMATE');assert.equal(c.instantaneousPowerKw,4);assert.equal(powers.length,0);
});
