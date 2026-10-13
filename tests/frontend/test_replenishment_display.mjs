import test from 'node:test';
import assert from 'node:assert/strict';
import { renderCostBreakdown, renderReplenishmentDetails } from '../../backend/app/static/demo/js/components.js';
import { renderDrawerStationCard } from '../../backend/app/static/demo/js/ui/drawer_renderer.js';

const plan = {status:'AVAILABLE',arrival_soc_pct:12,departure_soc_pct:80,destination_soc_pct:15,added_energy_kwh:10.25,service_duration_s:600};
test('backend predicted battery is shared by cost detail and station analysis, retaining actual service duration', () => {
 const candidate={station_id:'S',service_type:'CHARGING',eligible:true,features:{replenishment:plan,service_duration_s:600}};
 for(const html of [renderCostBreakdown(candidate),renderDrawerStationCard({station_id:'S'},{rankedCandidate:candidate})]) {
  assert.match(html,/12\.0% → 80\.0%/);assert.match(html,/15\.0%/);assert.match(html,/10\.25 kWh/);
 }
 assert.match(renderCostBreakdown(candidate),/10\.0 phút/);
});
test('swap and no destination show backend values without invented destination or 80% override', () => {
 const html=renderReplenishmentDetails({...plan,departure_soc_pct:90,destination_soc_pct:null});
 assert.match(html,/90\.0%/);assert.doesNotMatch(html,/Pin dự kiến tại B|80\.0%/);
 assert.match(renderReplenishmentDetails({...plan,arrival_soc_pct:95,departure_soc_pct:95,added_energy_kwh:0}),/0\.00 kWh/);
});
test('missing and unavailable energy never becomes zero and reason is escaped', () => {
 assert.match(renderReplenishmentDetails(null),/Chưa có dữ liệu/);
 const html=renderReplenishmentDetails({status:'UNAVAILABLE',reason:'<img src=x>',arrival_soc_pct:null});
 assert.match(html,/&lt;img src=x&gt;/);assert.doesNotMatch(html,/<img|0\.0%|0\.00 kWh/);
 const incomplete=renderReplenishmentDetails({status:'AVAILABLE',arrival_soc_pct:null,departure_soc_pct:80,added_energy_kwh:null});
 assert.match(incomplete,/Chưa có dữ liệu → 80\.0%/);assert.doesNotMatch(incomplete,/0\.00 kWh/);
 assert.match(renderReplenishmentDetails({status:'INFEASIBLE',reason:'CAPACITY_EXCEEDED'}),/không khả thi: CAPACITY_EXCEEDED/);
});
