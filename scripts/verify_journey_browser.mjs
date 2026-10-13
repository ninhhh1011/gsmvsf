import {chromium} from 'playwright';
import {mkdirSync,writeFileSync} from 'node:fs';

const output='runtime/journey-scale/browser'; mkdirSync(output,{recursive:true});
const results=[];
const check=(name,ok,evidence)=>{results.push({name,ok,evidence});writeFileSync(`${output}/results.json`,JSON.stringify(results,null,2));if(!ok)throw new Error(name+': '+JSON.stringify(evidence));};
const browser=await chromium.launch({headless:true});
let activePage;
async function chooseStation(page,selector,index=0) {
 for(let attempt=0;attempt<3;attempt++) {
  const choices=page.locator(selector);
  const reply=page.waitForResponse(response=>response.url().endsWith('/station-plan'));
  await choices.nth(Math.min(index,await choices.count()-1)).click();
  const response=await reply;
  if(response.status()===200)return;
  if(response.status()!==409||attempt===2)throw new Error('station selection '+response.status()+': '+await response.text());
  console.log('Explicit reselection after safe station invalidation');
  await page.locator('#btn-close-stations-drawer').click();await page.locator('#btn-open-stations-drawer').click();
  await page.waitForFunction(after=>!!(after?driverMode.postTripRecommendation:driverMode.lastRecommendation)?.ranked_candidates?.length,selector.includes('post-trip'));
 }
}
async function clickMapPoint(page, latitude, longitude) {
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 await page.waitForFunction(()=>!driverMode.map.map._animatingZoom);
 const point=await page.evaluate(([latitude,longitude])=>{
  const map=driverMode.map.map;map.stop();map.invalidateSize({animate:false});map.setView([latitude,longitude],14,{animate:false});
  let point=map.latLngToContainerPoint([latitude,longitude]);
  if(innerWidth<600){map.panBy([0,point.y-140],{animate:false});point=map.latLngToContainerPoint([latitude,longitude]);}
  const box=map.getContainer().getBoundingClientRect();const x=box.x+point.x,y=box.y+point.y;return {x,y,element:document.elementFromPoint(x,y)?.outerHTML.slice(0,250),center:map.getCenter()};
 },[latitude,longitude]);
 console.log('map click '+JSON.stringify(point));
 await page.mouse.click(point.x,point.y);
}
try {
 for(const [name,viewport] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]) {
  if(process.env.BROWSER_VIEWPORT&&process.env.BROWSER_VIEWPORT!==name)continue;
  const page=await browser.newPage({viewport});activePage=page;page.setDefaultTimeout(120000);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  page.on('response',async response=>{if(response.url().endsWith('/station-plan'))console.log(name+' station-plan '+response.status()+' '+(await response.text()).slice(0,600));});
  await page.goto('http://127.0.0.1:3000',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!!window.driverMode?.currentVehicle);
  check(name+' starts without fabricated A/B',await page.evaluate(()=>!driverMode.planningOrigin&&!driverMode.passengerDestination));
  check(name+' public scoped profile',await page.evaluate(()=>driverMode.api.driverIdentity?.driver_id==='synthetic_sample_driver'));
  await page.locator('#btn-pick-custom-origin').click();
  await page.waitForFunction(()=>driverMode.map.map._events.click?.some(event=>event.fn===driverMode.mapPicker._onClickHandler));
  await clickMapPoint(page,20.9849,105.7935);
  await page.waitForFunction(()=>!!driverMode.customOrigin);
  await page.locator('#btn-open-stations-drawer').click();
  check(name+' no-B clear action hidden',!await page.locator('#btn-clear-custom-dest').isVisible());
  await page.waitForFunction(()=>!!driverMode.lastRecommendation?.ranked_candidates?.length,null,{timeout:180000});
  check(name+' station-only recommendation without B',await page.evaluate(()=>!driverMode.passengerDestination&&driverMode.lastRecommendation.has_recommendation));
  await chooseStation(page,'#stations-drawer .btn-nav-drawer-station');
  await page.waitForFunction(()=>!!driverMode.selectedStationPlan,null,{timeout:180000});
  check(name+' station-only target stays separate',await page.evaluate(()=>driverMode.currentTrip.goal_role==='STATION'&&!driverMode.passengerDestination&&driverMode.fullRouteCoords.length>1));
  await page.screenshot({path:`${output}/${name}-station-only.png`});
  await page.evaluate(()=>driverMode.replay.pause());
  await page.locator('#btn-pick-custom-dest').click();
  await page.waitForFunction(()=>driverMode.map.map._events.click?.some(event=>event.fn===driverMode.mapPicker._onClickHandler));
  await clickMapPoint(page,21.0315,105.7830);
  await page.waitForFunction(()=>driverMode.passengerDestination&&driverMode.currentRouteTiming);
  await page.locator('#btn-open-stations-drawer').click();
  await page.waitForFunction(()=>!!driverMode.lastRecommendation?.ranked_candidates?.length,null,{timeout:180000});
  const snapshot=await page.evaluate(()=>{const c=driverMode.lastRecommendation.ranked_candidates[0];return {total:c.total_completion_time_s,complete:c.eta_to_service_complete_s,onward:c.features.duration_station_to_dest_s,score:c.ranking_score,components:c.score_components};});
  check(name+' complete physical time and separate score',Math.abs(snapshot.total-snapshot.complete-snapshot.onward)<1e-6&&Math.abs(snapshot.score-Object.values(snapshot.components).reduce((a,b)=>a+b,0))<1e-8,snapshot);
  await chooseStation(page,'#stations-drawer .btn-nav-drawer-station',1);
  await page.waitForFunction(()=>driverMode.selectedStationPlan?.goal_role==='PASSENGER_DESTINATION',null,{timeout:180000});
  check(name+' confirmed constrained plan',await page.evaluate(()=>driverMode.selectedStationPlan.waypoints?.length===2&&driverMode.currentTrip.goal_role==='PASSENGER_DESTINATION'));
  await page.locator('#btn-start-driving').click();
  await page.locator('#btn-driver-replay-pause').click();
  await page.waitForFunction(()=>!driverMode.replay.isStepInProgress);
  if(name==='mobile')await page.locator('#btn-driver-sheet-toggle').click();
  await page.locator('#btn-view-cost-breakdown').click();
  check(name+' cost modal opens with computed details',await page.locator('#cost-breakdown-modal').isVisible()&&(await page.locator('#cost-modal-body').innerText()).length>100);
  await page.locator('#btn-close-cost-modal').click();
  await page.locator('#driver-analysis-tools > summary').click();
  await page.locator('.btn-quick-soc[data-soc="85"]').click();
  await page.waitForFunction(()=>!driverMode._isEvaluating && driverMode.lastRecommendation?.energy_context?.current_soc_pct===85);
  check(name+' high SOC no false low reserve',!(await page.locator('#hud-warning-container').innerText()).includes('Dự phòng năng lượng thấp'));
  await page.locator('.btn-quick-soc[data-soc="12"]').click();
  await page.waitForFunction(()=>!driverMode._isEvaluating && driverMode.lastRecommendation?.energy_context?.current_soc_pct===12);
  const lowWarning=await page.evaluate(()=>driverMode.lastRecommendation?.energy_context?.energy_assessment?.warning_level);
  check(name+' low SOC advisory or critical evidence',['ADVISORY','CRITICAL'].includes(lowWarning),lowWarning);
  await page.locator('.btn-quick-soc[data-soc="85"]').click();await page.waitForFunction(()=>!driverMode._isEvaluating && driverMode.lastRecommendation?.energy_context?.current_soc_pct===85);
  await page.locator('#toggle-route-familiarity').check();await page.locator('#btn-h3-res-badge').click();
  check(name+' H3 controls retained',await page.locator('#btn-h3-res-badge').innerText()==='⬡ Res 10');
  await page.screenshot({path:`${output}/${name}-active.png`});
  await page.locator('#btn-open-stations-drawer').click();
  await page.locator('#tab-intent-dest').click();
  await page.waitForFunction(()=>!!driverMode.postTripRecommendation?.ranked_candidates?.length,null,{timeout:180000});
  await chooseStation(page,'#stations-drawer .btn-nav-post-trip-station');
  await page.waitForFunction(()=>driverMode.selectedStationPlan?.plan_mode==='AFTER_DESTINATION',null,{timeout:180000});
  check(name+' after-B target and waypoint order',await page.evaluate(()=>driverMode.currentTrip.goal_role==='STATION'&&driverMode.selectedStationPlan.waypoints.map(x=>x.role).join(',')==='PASSENGER_DESTINATION,STATION'));
  await page.screenshot({path:`${output}/${name}-after-B.png`});
  await page.locator('#btn-open-stations-drawer').click();await page.locator('#btn-clear-custom-dest').click();
  check(name+' B can be cleared during plan',await page.evaluate(()=>!driverMode.passengerDestination&&!driverMode.selectedStationPlan&&driverMode.state==='AVAILABLE'));
  await page.locator('#btn-pick-custom-dest').click();
  await page.waitForFunction(()=>driverMode.map.map._events.click?.some(event=>event.fn===driverMode.mapPicker._onClickHandler));
  await clickMapPoint(page,21.0360,105.8300);
  await page.waitForFunction(()=>driverMode.passengerDestination&&driverMode.currentRouteTiming);
  await page.locator('#btn-start-driving').click();
  await page.locator('#btn-driver-replay-pause').click();
  await page.waitForFunction(()=>!driverMode.replay.isStepInProgress);
  if(name==='mobile'&&!await page.locator('#driver-analysis-tools').isVisible())await page.locator('#btn-driver-sheet-toggle').click();
  if(!await page.locator('#slider-cockpit-soc').isVisible())await page.locator('#driver-analysis-tools > summary').click();
  await page.locator('#slider-cockpit-soc').focus();await page.keyboard.press('Home');await page.keyboard.press('Tab');
  await page.waitForFunction(()=>!driverMode._isEvaluating&&driverMode.lastRecommendation?.energy_context?.current_soc_pct===5);
  const critical=await page.evaluate(()=>driverMode.lastRecommendation.energy_context.energy_assessment.warning_level);
  check(name+' low reserve follows backend assessment',['ADVISORY','CRITICAL'].includes(critical),critical);
  await page.locator('#cockpit-vehicle-select').selectOption('EVO200');
  await page.waitForFunction(()=>driverMode.currentVehicle?.vehicle_model==='EVO200'&&driverMode.currentRouteTiming);
  const vehiclePlan=await page.evaluate(()=>({destination:driverMode.passengerDestination,tripDestination:driverMode.currentTrip?.destination,goal:driverMode.currentTrip?.goal_role,selected:!!driverMode.selectedStationPlan,category:driverMode.session.vehicle_category}));
  check(name+' vehicle change replans outstanding B',!!vehiclePlan.destination&&!vehiclePlan.selected&&vehiclePlan.goal!=='STATION'&&vehiclePlan.category==='EV_MOTORBIKE'&&JSON.stringify(vehiclePlan.destination)===JSON.stringify(vehiclePlan.tripDestination),vehiclePlan);
  check(name+' no browser exceptions',errors.length===0,errors);
  await page.close();
 }
} catch(error) {if(activePage&&!activePage.isClosed()){await activePage.screenshot({path:`${output}/failure.png`});console.log(await activePage.evaluate(()=>({state:driverMode.state,soc:driverMode.currentSocPct,energy:driverMode.lastRecommendation?.energy_context,picking:driverMode.mapPicker.isPickingDestination})));}throw error;
} finally {await browser.close();writeFileSync(`${output}/results.json`,JSON.stringify(results,null,2));}
console.log(JSON.stringify({passed:results.filter(x=>x.ok).length,total:results.length}));
