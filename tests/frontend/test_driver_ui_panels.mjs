import test from 'node:test';
import assert from 'node:assert/strict';
import { DriverModeController, DriverState } from '../../backend/app/static/demo/js/ui/driver_controller.js';
import { renderDrawerStationsListHTML } from '../../backend/app/static/demo/js/ui/drawer_renderer.js';

test('drawer groups unique backend-ranked stations before the remaining catalog', () => {
 const stations = ['C','B','A'].map(station_id => ({station_id,latitude:21,longitude:105,distKm:'1'}));
 const html = renderDrawerStationsListHTML(stations,{activeRec:{ranked_candidates:[{station_id:'A',rank:1},{station_id:'A',rank:2},{station_id:'B',rank:3}]}});
 assert.match(html, /drawer-top-five/);
 assert.match(html, /drawer-other-stations/);
 assert.ok(html.indexOf('data-station-id="A"') < html.indexOf('data-station-id="B"'));
 assert.equal((html.match(/class="station-drawer-card/g)||[]).length,3);
});

test('recommendation refresh updates only an already-open drawer', () => {
 let open = false, renders = 0;
 const c = new DriverModeController({}, {}, {bindings:{isStationsDrawerOpen:()=>open}});
 c.renderStationsDrawer = () => renders++;
 c._notifyTop5Updated({}); assert.equal(renders,0);
 open = true; c._notifyTop5Updated({}); assert.equal(renders,1);
});

for (const locked of [false,true]) test(`remaining distance follows the road bend (navigation locked=${locked})`, async () => {
 const c = new DriverModeController({}, {updateDirectRoute(){} });
 c.state = DriverState.TRIP_ACTIVE;
 c.fullRouteCoords = [[21,105],[21.001,105],[21.001,105.001]];
 c.currentTrip = {destination:{latitude:21.001,longitude:105.001}};
 c._navigationLocked = locked;
 c.replay.isReplayComplete = () => false;
 c._updateReplayPower = async () => {};
 await c._onReplayStep({observation:{latitude:21,longitude:105}});
 assert.ok(c.remainingTripDistanceKm > 0.20 && c.remainingTripDistanceKm < 0.23, 'road bend is about 215m; diagonal is only 152m');
});

test('rerouting stores the new engine timing and redraws the road', async () => {
 const route={geometry:'_p~iF~ps|U_ulLnnqC_mqNvxq`@',distance_m:1000,duration_s:120};
 let redraws=0;
 const c=new DriverModeController({computeRoute:async()=>route},{updateDirectRoute(){redraws++;}});
 c.currentTrip={destination:{latitude:21,longitude:105}};
 c._clearH3OnRouteChange=()=>{};
 await c._triggerReroute({latitude:21.001,longitude:105});
 assert.equal(c.currentRouteTiming,route);
 assert.equal(redraws,1);
});

test('reroute reprojects progress before measuring the replacement road', async () => {
 const c=new DriverModeController({}, {updateDirectRoute(){}});
 c.state=DriverState.TRIP_ACTIVE;
 c.currentTrip={destination:{latitude:21.011,longitude:105.009}};
 c.fullRouteCoords=Array.from({length:10},(_,i)=>[21,105+i*.001]);
 c.lastPassedSegmentIndex=8;
 c.offRouteConsecutiveSamples=2;
 c._triggerReroute=async()=>{c.fullRouteCoords=[[21.01,105.008],[21.011,105.008],[21.011,105.009]];c.lastPassedSegmentIndex=0;};
 c._updateReplayPower=async()=>{};
 c.replay.isReplayComplete=()=>false;
 await c._onReplayStep({observation:{latitude:21.01,longitude:105.008}});
 assert.equal(c.lastPassedSegmentIndex,0);
 assert.ok(c.remainingTripDistanceKm>.20 && c.remainingTripDistanceKm<.23);
});

test('after-arrival drawer preserves zero road distance and engine driving ETA', () => {
 const html=renderDrawerStationsListHTML([{station_id:'ZERO',latitude:21,longitude:105,distKm:'0'}],{activeRec:{ranked_candidates:[{station_id:'ZERO',features:{distance_to_station_m:0,prior_travel_duration_s:0},eta_to_station_s:0,total_completion_time_s:0}]},isAtDest:true,remainingTripDistanceKm:0,directDrivingEtaMinutes:0,dest:{latitude:21,longitude:105}});
 assert.match(html,/0\.0 km/);
 assert.doesNotMatch(html,/5\.0 km|10 phút/);
});
