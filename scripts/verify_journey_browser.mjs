import {chromium} from 'playwright';
import {mkdirSync,writeFileSync} from 'node:fs';

const output='runtime/journey-scale/browser'; mkdirSync(output,{recursive:true});
const results=[];
const check=(name,ok,evidence)=>{results.push({name,ok,evidence});writeFileSync(`${output}/results.json`,JSON.stringify(results,null,2));if(!ok)throw new Error(name+': '+JSON.stringify(evidence));};
const browser=await chromium.launch({headless:true});
try {
 for(const [name,viewport] of [['desktop',{width:1440,height:900}],['mobile',{width:390,height:844}]]) {
  const page=await browser.newPage({viewport});page.setDefaultTimeout(120000);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('http://127.0.0.1:3000',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>!!window.driverMode?.currentVehicle);
  check(name+' starts without fabricated A/B',await page.evaluate(()=>!driverMode.planningOrigin&&!driverMode.passengerDestination));
  check(name+' public scoped profile',await page.evaluate(()=>driverMode.api.driverIdentity?.driver_id==='synthetic_sample_driver'));
  await page.locator('#btn-pick-custom-origin').click();
  await page.evaluate(()=>driverMode.map.map.fire('click',{latlng:L.latLng(20.9849,105.7935)}));
  await page.waitForFunction(()=>!!driverMode.customOrigin);
  await page.locator('#btn-open-stations-drawer').click();
  await page.waitForFunction(()=>!!driverMode.lastRecommendation?.ranked_candidates?.length,null,{timeout:180000});
  check(name+' station-only recommendation without B',await page.evaluate(()=>!driverMode.passengerDestination&&driverMode.lastRecommendation.has_recommendation));
  const button=page.locator('#stations-drawer .btn-nav-drawer-station').first();
  await button.click();
  await page.waitForFunction(()=>!!driverMode.selectedStationPlan,null,{timeout:180000});
  check(name+' station-only target stays separate',await page.evaluate(()=>driverMode.currentTrip.goal_role==='STATION'&&!driverMode.passengerDestination&&driverMode.fullRouteCoords.length>1));
  await page.screenshot({path:`${output}/${name}-station-only.png`});
  await page.evaluate(()=>driverMode.replay.pause());
  await page.locator('#btn-clear-custom-dest').click();
  await page.locator('#btn-pick-custom-dest').click();
  await page.evaluate(()=>driverMode.map.map.fire('click',{latlng:L.latLng(21.0315,105.7830)}));
  await page.waitForFunction(()=>driverMode.passengerDestination&&driverMode.currentRouteTiming);
  await page.locator('#btn-open-stations-drawer').click();
  await page.waitForFunction(()=>!!driverMode.lastRecommendation?.ranked_candidates?.length,null,{timeout:180000});
  const snapshot=await page.evaluate(()=>{const c=driverMode.lastRecommendation.ranked_candidates[0];return {total:c.total_completion_time_s,complete:c.eta_to_service_complete_s,onward:c.features.duration_station_to_dest_s,score:c.ranking_score,components:c.score_components};});
  check(name+' complete physical time and separate score',Math.abs(snapshot.total-snapshot.complete-snapshot.onward)<1e-6&&Math.abs(snapshot.score-Object.values(snapshot.components).reduce((a,b)=>a+b,0))<1e-8,snapshot);
  const choices=page.locator('#stations-drawer .btn-nav-drawer-station');
  await choices.nth(Math.min(1,await choices.count()-1)).click();
  await page.waitForFunction(()=>driverMode.selectedStationPlan?.goal_role==='PASSENGER_DESTINATION',null,{timeout:180000});
  check(name+' confirmed constrained plan',await page.evaluate(()=>driverMode.selectedStationPlan.waypoints?.length===2&&driverMode.currentTrip.goal_role==='PASSENGER_DESTINATION'));
  await page.locator('#btn-start-driving').click();
  await page.locator('#btn-driver-replay-pause').click();
  await page.waitForFunction(()=>!driverMode.replay.isStepInProgress);
  if(name==='mobile')await page.locator('#btn-driver-sheet-toggle').click();
  await page.locator('#driver-analysis-tools > summary').click();
  await page.locator('.btn-quick-soc[data-soc="85"]').click();
  await page.waitForFunction(()=>!driverMode._isEvaluating);
  check(name+' high SOC no false low reserve',!(await page.locator('#hud-warning-container').innerText()).includes('Dự phòng năng lượng thấp'));
  await page.locator('.btn-quick-soc[data-soc="12"]').click();
  await page.waitForFunction(()=>!driverMode._isEvaluating);
  check(name+' critical SOC evidence',await page.evaluate(()=>driverMode.lastEnergyRequest?.energy_assessment?.warning_level==='CRITICAL'));
  await page.locator('.btn-quick-soc[data-soc="85"]').click();await page.waitForFunction(()=>!driverMode._isEvaluating);
  await page.locator('#toggle-route-familiarity').check();await page.locator('#btn-h3-res-badge').click();
  check(name+' H3 controls retained',await page.locator('#btn-h3-res-badge').innerText()==='⬡ Res 10');
  await page.screenshot({path:`${output}/${name}-active.png`});
  check(name+' no browser exceptions',errors.length===0,errors);
  await page.close();
 }
} finally {await browser.close();writeFileSync(`${output}/results.json`,JSON.stringify(results,null,2));}
console.log(JSON.stringify({passed:results.filter(x=>x.ok).length,total:results.length}));
