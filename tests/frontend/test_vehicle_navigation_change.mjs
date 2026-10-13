import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { registerVehicleModel } from '../../backend/app/static/demo/js/domain/vehicle_model.js';

registerVehicleModel('TEST_SWAP_ONLY', {name:'Swap only',category:'EV_MOTORBIKE',battery_kwh:2,consumption_kwh_per_km:.04,charging_supported:false,swap_supported:true});

function fixture(computeRoute = async()=>({geometry:'??_ibE_ibE',distance_m:1000,duration_s:60})) {
 const bindings=new Proxy({}, {get:()=>()=>false});
 const map=new Proxy({}, {get:()=>()=>{}});
 const c=new DriverModeController({computeRoute},map,{bindings});
 c.renderCurrentStateUI=c.renderAvailableUI=c.renderTripAssignedUI=()=>{};
 c.replay.reset=()=>{};c.replay.pause=()=>{c.replayPaused=true;};c.replay.loadFromPolyline=async()=>{};
 c.currentVehicle={vehicle_model:'VF_3',vehicle_type:'EV_CAR'};
 c.currentPos={latitude:21,longitude:105};c.currentSocPct=34;
 c.customDestination={latitude:21.02,longitude:105.02};
 c.currentTrip={destination:c.customDestination};
 c.selectedStationPlan={station_id:'CAR_STATION',service_type:'CHARGING'};
 c._navigationLocked=true;c.fullRouteCoords=[[21,105],[21.01,105.01]];
 c.lastRecommendation={ranked_candidates:[{station_id:'CAR_STATION'}]};
 return c;
}

test('car to swap-only invalidates selected pair and replans outstanding B from current A',async()=>{
 let args;const c=fixture(async(...a)=>{args=a;return {geometry:'??_ibE_ibE',distance_m:1000,duration_s:60};});
 const a=c.currentPos,b=c.customDestination;
 await c.selectVehicleModel('TEST_SWAP_ONLY');
 assert.equal(c.selectedStationPlan,null);assert.equal(c._navigationLocked,false);
 assert.equal(c.lastRecommendation,null);assert.equal(c.currentSocPct,34);
 assert.equal(c.replayPaused,true);
 assert.equal(c.currentVehicle.charging_supported,false);
 assert.deepEqual(args,[a,b,{vehicle_category:'EV_MOTORBIKE'}]);
});

test('station-only model change keeps A and requires a fresh station choice',async()=>{
 const c=fixture(()=>{throw Error('no passenger route');});let lookup=0;
 c.customDestination=null;c.currentTrip={destination:{latitude:21.01,longitude:105.01},goal_role:'STATION'};
 c.openStationsDrawer=async()=>{lookup++;};
 await c.selectVehicleModel('TEST_SWAP_ONLY');
 assert.equal(c.passengerDestination,null);assert.equal(c.stationNavigationTarget,null);
 assert.equal(c.selectedStationPlan,null);assert.equal(c.fullRouteCoords,null);
 assert.equal(c.currentRouteTiming,null);assert.equal(lookup,1);
 assert.equal(c.currentSocPct,34);
});

test('passed B is cleared and model change opens station-only lookup',async()=>{
 const c=fixture(()=>{throw Error('must not return to B');});let lookup=0;
 c.navigationStages={passengerPassed:true};c.openStationsDrawer=async()=>{lookup++;};
 await c.selectVehicleModel('TEST_SWAP_ONLY');
 assert.equal(c.passengerDestination,null);assert.equal(c.currentTrip,null);
 assert.equal(c.selectedStationPlan,null);assert.equal(lookup,1);
 assert.deepEqual(c.currentPos,{latitude:21,longitude:105});
});

test('rapid model changes cannot commit an older routing profile',async()=>{
 const calls=[];const c=fixture((...args)=>new Promise(resolve=>calls.push({args,resolve})));
 const first=c.selectVehicleModel('TEST_SWAP_ONLY');
 const second=c.selectVehicleModel('VF_5');
 assert.equal(calls.length,2);
 calls[1].resolve({geometry:'??_ibE_ibE',distance_m:2000,duration_s:120});await second;
 calls[0].resolve({geometry:'??_ibE_ibE',distance_m:1000,duration_s:60});await first;
 assert.equal(c.currentRouteTiming.distance_m,2000);
 assert.equal(c.currentVehicle.vehicle_type,'EV_CAR');assert.equal(c.selectedStationPlan,null);
});

test('choosing the same model preserves committed navigation',async()=>{
 const c=fixture(()=>{throw Error('same model must not replan');});const plan=c.selectedStationPlan;
 await c.selectVehicleModel('VF_3');
 assert.equal(c.selectedStationPlan,plan);assert.equal(c._navigationLocked,true);
});

test('historical assignment initializes its vehicle without resetting trip identity or trajectory',async()=>{
 let routeArgs;const c=fixture(async(...args)=>{routeArgs=args;return {geometry:'??_ibE_ibE',distance_m:1000,duration_s:60};});
 const trip={trip_id:'TRJ_HISTORICAL',vehicle_id:'SWAP_V',driver_id:'HISTORICAL_DRIVER',start_time:'2026-09-01T00:00:00Z',origin:{latitude:21,longitude:105},destination:{latitude:21.02,longitude:105.02}};
 const observations=[{latitude:21,longitude:105,timestamp:trip.start_time},{latitude:21.01,longitude:105.01}];
 c.trips=[trip];c.vehicles=[{vehicle_id:'SWAP_V',vehicle_model:'TEST_SWAP_ONLY'}];
 c.userSelectedVehicleModel=null;c._tripToTrajectory=()=> 'HISTORICAL_TRAJECTORY';
 c.api.getTrajectory=async()=>observations;
 const initialGeneration=c.generation;
 await c.assignTrip(trip.trip_id);
 assert.equal(c.currentTrip,trip);assert.equal(c.generation,initialGeneration+1);
 assert.equal(c.offlineEvaluationTime,trip.start_time);
 assert.deepEqual(c.actualTrajectoryCoords,[[21,105],[21.01,105.01]]);
 assert.deepEqual(routeArgs,[trip.origin,trip.destination,{vehicle_category:'EV_MOTORBIKE'}]);
 assert.equal(c.state,'TRIP_ASSIGNED');assert.equal(c.replayPaused,undefined);
});
