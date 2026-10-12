import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { renderDrawerStationCard } from '../../backend/app/static/demo/js/ui/drawer_renderer.js';
test('destination starts optional and station target never becomes passenger goal', () => {
 const c = new DriverModeController({}, {}, {bindings:{}});
 assert.equal(c.customDestination, null);
 assert.equal(c.passengerDestination, null);
});
test('unknown queue uses effective estimate and unknown eligibility cannot navigate', () => {
 const html = renderDrawerStationCard({station_id:'S',latitude:21,longitude:105},{activeRec:{ranked_candidates:[{station_id:'S',service_type:'CHARGING',features:{observed_queue_wait_s:null,effective_queue_wait_s:5400}}]}});
 assert.ok(html.includes('90'));
 const unknown = renderDrawerStationCard({station_id:'S',latitude:21,longitude:105});
 assert.ok(!unknown.includes('btn-nav-drawer-station'));
});

function fixture(api = {}) {
 const map = {clearAll(){},renderTripEndpoints(){},renderDirectRoute(){},renderStations(){},fitBoundsToActive(){}};
 const bindings = {setNavigationButtonState(){},setStationsDrawerOpen(){},renderAnalysis(){},renderAssigned(){},setStatusBadge(){},updateBattery(){},showRouteUnavailable(){}};
 const c = new DriverModeController(api,map,{bindings});
 c.currentVehicle={vehicle_id:'V',vehicle_type:'EV_CAR'};
 c.currentPos={latitude:21,longitude:105};
 c.stations=[{station_id:'S',latitude:21.01,longitude:105.01,service_type:'CHARGING'}];
 c.replay.loadFromPolyline=async()=>{};
 return c;
}
test('station-only uses confirmed geometry and preserves optional B when changing stations', async()=>{
 let request;
 const c=fixture({getStationPlan:async payload=>{request=payload;return {station_id:'S',service_type:'CHARGING',goal_role:'STATION',route:{geometry:[[105,21],[105.01,21.01]],distance_m:1234,duration_s:90}};},computeRoute(){throw new Error('must not reroute unrestricted');}});
 assert.equal(await c.navigateViaStationId('S','CHARGING'),true);
 assert.deepEqual(c.fullRouteCoords,[[21,105],[21.01,105.01]]);
 assert.equal(request.destination_latitude,null);
 assert.equal(c.passengerDestination,null);
 assert.equal(c.currentTrip.goal_role,'STATION');
 assert.equal(await c.navigateViaStationId('S','CHARGING'),true);
 assert.equal(request.destination_latitude,null);
});
test('new telemetry invalidates a pending station selection',async()=>{
 let resolve;
 const c=fixture({getStationPlan:()=>new Promise(r=>resolve=r)});
 const pending=c.navigateViaStationId('S','CHARGING');
 c._powerRevision++;
 resolve({station_id:'S',service_type:'CHARGING',route:{geometry:[[105,21],[105.01,21.01]],distance_m:1000,duration_s:60}});
 assert.equal(await pending,false);
 assert.equal(c._navigationLocked,false);
 assert.equal(c.selectedStationPlan,null);
});
test('after-B sends original telemetry for backend feasibility instead of positive floors',async()=>{
 let request;
 const c=fixture({getRecommendation:async payload=>{request=payload;return {ranked_candidates:[]};}});
 c.bindings.renderDrawer=()=>{};
 c.customDestination={latitude:21.02,longitude:105.02};
 c.chargingIntent='AT_DESTINATION';c.currentSocPct=0;c.estimatedRangeKm=0;
 await c.refreshDrawerEvaluations();
 assert.equal(request.plan_mode,'AFTER_DESTINATION');
 assert.equal(request.context.current_soc_pct,0);
 assert.equal(request.context.estimated_remaining_range_km,0);
 assert.equal(request.context.raw_latitude,21);
 assert.equal(request.destination_latitude,21.02);
});

test('after-B card subtracts prior leg exactly once while total stays backend physical total',()=>{
 const html=renderDrawerStationCard({station_id:'S'}, {isAtDest:true,activeRec:{ranked_candidates:[{station_id:'S',service_type:'CHARGING',eta_to_station_s:900,total_completion_time_s:1200,ranking_score:.87,features:{prior_travel_duration_s:600,prior_travel_distance_m:5000,distance_to_station_m:7000,effective_queue_wait_s:60,service_duration_s:240}}]}});
 assert.ok(html.includes('2.0 km'));
 assert.ok(html.includes('(5 phút)'));
 assert.ok(html.includes('20 phút'));
 assert.ok(html.includes('0.870'));
});
test('station-only completion never claims a passenger drop-off or charging completion',async()=>{
 const {renderTripCompleteCardHTML}=await import('../../backend/app/static/demo/js/ui/cockpit_renderer.js');
 const html=renderTripCompleteCardHTML(null,null,'STATION');
 assert.ok(html.includes('Đã đến trạm'));
 assert.ok(!html.includes('Hành khách đã xuống xe an toàn'));
});
test('scoped profile read signature is forwarded without a signing secret',async()=>{
 const {ApiClient}=await import('../../backend/app/static/demo/js/api.js');
 const client=new ApiClient();
 client.driverIdentity={driver_id:'synthetic_sample_driver',signature:'abc'};
 let options;
 client._request=async(_endpoint,args)=>{options=args;return {};};
 await client.getStationPlan({station_id:'S'});
 assert.deepEqual(options.headers,{'x-driver-identity-signature':'abc'});
 assert.ok(!JSON.stringify(options).includes('secret'));
});

test('mixed station exposes both ranked service actions',async()=>{
 const {renderDrawerStationsListHTML}=await import('../../backend/app/static/demo/js/ui/drawer_renderer.js');
 const html=renderDrawerStationsListHTML([{station_id:'S',station_type:'CHARGING_SWAP'}],{activeRec:{ranked_candidates:[{station_id:'S',service_type:'CHARGING',rank:1},{station_id:'S',service_type:'BATTERY_SWAP',rank:2}]}});
 assert.ok(html.includes('data-service-type="CHARGING"'));
 assert.ok(html.includes('data-service-type="BATTERY_SWAP"'));
});
test('connected recommendation card uses journey total and missing queue stays unknown',async()=>{
 const {renderRecommendationCard}=await import('../../backend/app/static/demo/js/components.js');
 const html=renderRecommendationCard({has_recommendation:true,ranked_candidates:[{station_id:'S',eta_to_service_complete_s:60,total_completion_time_s:660,features:{effective_queue_wait_s:null}}]});
 assert.ok(html.includes('11.0'));
 assert.ok(!html.includes('(còn trống)'));
});
test('locked reroute revalidates same plan instead of dropping the station',async()=>{
 let request;
 const c=fixture({getStationPlan:async payload=>{request=payload;return {station_id:'S',service_type:'CHARGING',goal_role:'STATION',route:{geometry:[[105,21],[105.01,21.01]],distance_m:1000,duration_s:60}};},computeRoute(){throw Error('unrestricted route');}});
 c.currentTrip={destination:{latitude:21.01,longitude:105.01},goal_role:'STATION'};
 c.selectedStationPlan={station_id:'S',service_type:'CHARGING',plan_mode:'BEFORE_DESTINATION'};c._navigationLocked=true;
 await c._triggerReroute(c.currentPos);
 assert.equal(request?.station_id,'S');
});

test('selected pair evidence drives active cost while ranking list stays separate',async()=>{
 const c=fixture({});
 c.lastRecommendation={has_recommendation:true,ranked_candidates:[{station_id:'TOP'}]};
 c.selectedStationPlan={station_id:'S',service_type:'BATTERY_SWAP',ranked_candidate:{station_id:'S',service_type:'BATTERY_SWAP',total_completion_time_s:700}};
 assert.equal(c.displayedRecommendation.ranked_candidates[0].station_id,'S');
 assert.equal(c.displayedRecommendation.ranked_candidates[0].total_completion_time_s,700);
 assert.equal(c.lastRecommendation.ranked_candidates[0].station_id,'TOP');
});
test('destination wording uses goal role instead of retained trip identifier',async()=>{
 const {renderTripActiveCardHTML}=await import('../../backend/app/static/demo/js/ui/cockpit_renderer.js');
 const c=fixture({});c.currentTrip={trip_id:'CUSTOM_TRIP',goal_role:'STATION'};
 const html=renderTripActiveCardHTML(c,{replayControls:{}});
 assert.ok(html.includes('Trạm đã chọn'));
 assert.ok(!html.includes('Passenger Drop-off'));
 c.currentTrip={trip_id:'NAVI_S',goal_role:'PASSENGER_DESTINATION'};
 const passenger=renderTripActiveCardHTML(c,{replayControls:{}});
 assert.ok(passenger.includes('Điểm trả khách'));
});
test('unlocked reroute rejects a route superseded by station selection revision',async()=>{
 let resolve;
 const c=fixture({computeRoute:()=>new Promise(r=>resolve=r)});
 c.currentTrip={destination:{latitude:21.02,longitude:105.02}};
 const previous=[[21,105],[21.01,105.01]];c.fullRouteCoords=previous;
 const pending=c._triggerReroute(c.currentPos);c.routeRevision++;
 resolve({geometry:'??_ibE_ibE',distance_m:1000,duration_s:60});
 await pending;assert.equal(c.fullRouteCoords,previous);
});
