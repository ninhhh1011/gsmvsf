import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { DriverState } from '../../backend/app/static/demo/js/domain/driver_state.js';
import { renderRecommendationCard } from '../../backend/app/static/demo/js/components.js';
import { renderDriverRecommendation } from '../../backend/app/static/demo/js/ui/driver_recommendation_renderer.js';
function fixture(getStationPlan) {
 const api={getStationPlan,evaluateDemand:async()=>({energy_assessment:{warning_level:'CRITICAL'}})};
 const map={clearAll(){},renderTripEndpoints(){},renderDirectRoute(){},renderStations(){},fitBoundsToActive(){},updateDirectRoute(){}};
 const bindings={updateBattery(){},setNavigationButtonState(){},setStationsDrawerOpen(){},showRouteUnavailable(){},isStationsDrawerOpen(){return false;}};
 const c=new DriverModeController(api,map,{bindings});c.renderCurrentStateUI=()=>{};c.renderTripActiveUI=()=>{};c.renderTripAssignedUI=()=>{};
 c.currentVehicle={vehicle_id:'V0001',usable_capacity_kwh:17.1,consumption_wh_per_km:100};c.currentPos={latitude:21,longitude:105};c.state=DriverState.TRIP_ASSIGNED;
 c.customDestination={latitude:21.02,longitude:105.02};c.currentTrip={destination:c.passengerDestination};c.stations=[{station_id:'S',latitude:21.01,longitude:105.01}];
 c._navigationLocked=true;c.selectedStationPlan={station_id:'S',service_type:'CHARGING',plan_mode:'BEFORE_DESTINATION',ranked_candidate:{features:{replenishment:{arrival_soc_pct:84},service_duration_s:0},total_completion_time_s:100}};
 c.navigationStages={originalMode:'BEFORE_DESTINATION',passengerPassed:false,stationPassed:false};c.fullRouteCoords=[[21,105],[21.02,105.02]];c.lastRecommendation={};
 c.replay.loadFromPolyline=()=>{throw Error('must not reset replay');};return c;
}
const reply=()=>({station_id:'S',service_type:'CHARGING',plan_mode:'BEFORE_DESTINATION',route:{geometry:[[105,21],[105.01,21.01],[105.02,21.02]],distance_m:2000,duration_s:120},ranked_candidate:{features:{replenishment:{arrival_soc_pct:4},service_duration_s:600},total_completion_time_s:720}});
test('manual input immediately invalidates old selected estimate and assigned commit refreshes same pair',async()=>{
 let resolve,payload;const c=fixture(p=>{payload=p;return new Promise(r=>resolve=r);});const stages=c.navigationStages;
 c.setBatterySoc(5,false);assert.equal(c.displayedRecommendation.ranked_candidates[0].features.service_duration_s,undefined);
 assert.match(renderRecommendationCard(c.displayedRecommendation),/cần xác nhận lại/);
 assert.match(renderDriverRecommendation(c.displayedRecommendation),/cần xác nhận lại/);
 const pending=c.setBatterySoc(5,true);assert.equal(payload.context.current_soc_pct,5);assert.equal(payload.station_id,'S');
 resolve(reply());await pending;assert.equal(c.navigationStages,stages);assert.equal(c.displayedRecommendation.ranked_candidates[0].features.service_duration_s,600);
});
test('after passing B confirmation is station-only and retains passenger progress',async()=>{
 let payload;const c=fixture(async p=>{payload=p;return reply();});
 c.navigationStages={originalMode:'AFTER_DESTINATION',passengerPassed:true,stationPassed:false};
 c.selectedStationPlan.plan_mode='AFTER_DESTINATION';const stages=c.navigationStages;
 await c.setBatterySoc(5,true);assert.equal(payload.plan_mode,'BEFORE_DESTINATION');assert.equal(payload.destination_latitude,null);
 assert.equal(c.navigationStages,stages);assert.equal(c.navigationStages.passengerPassed,true);
});
test('failed confirmation keeps geometry and selection with unknown estimates',async()=>{
 const c=fixture(async()=>{throw Error('unreachable');});const geometry=c.fullRouteCoords;await c.setBatterySoc(5,true);
 assert.equal(c.fullRouteCoords,geometry);assert.equal(c.selectedStationPlan.station_id,'S');assert.equal(c.displayedRecommendation.ranked_candidates[0].estimate_unavailable,true);
});
test('assigned historical origin refreshes selected plan before first GPS observation',async()=>{
 let payload;const c=fixture(async p=>{payload=p;return reply();});
 c.currentTrip.origin={latitude:21,longitude:105};c.currentPos=null;
 await c.setBatterySoc(5,true);
 assert.equal(payload.context.raw_latitude,21);assert.equal(payload.context.raw_longitude,105);
 assert.equal(c.displayedRecommendation.ranked_candidates[0].features.service_duration_s,600);
});
test('late replies cannot restore old estimates after another SOC input or unlock',async()=>{
 for(const unlock of [false,true]) {let resolve;const c=fixture(()=>new Promise(r=>resolve=r));const pending=c.setBatterySoc(5,true);
 if(unlock){c._navigationLocked=false;c.selectedStationPlan=null;}else c.setBatterySoc(12,false);
 resolve(reply());await pending;assert.equal(c.selectedStationPlan?.ranked_candidate?.features.service_duration_s,undefined);}
});
test('passed station reroutes directly to B without recharging or resetting waypoints',async()=>{
 const c=fixture(()=>{throw Error('must not revisit station');});c.navigationStages.stationPassed=true;
 c.api.computeRoute=async()=>({geometry:'??_ibE_ibE',distance_m:1000,duration_s:60});const stages=c.navigationStages;
 await c.setBatterySoc(5,true);assert.equal(c.navigationStages,stages);assert.equal(c.currentSocPct,5);assert.equal(c.displayedRecommendation.ranked_candidates[0].estimate_unavailable,true);
});


