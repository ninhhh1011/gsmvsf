import test from 'node:test';
import assert from 'node:assert/strict';
import { renderVehicleOptions } from '../../backend/app/static/demo/js/ui/cockpit_renderer.js';
test('Driver catalog prepares options for bindings without injecting markup', () => {
 const options=renderVehicleOptions([{id:'CUSTOM',name:'Custom EV',battery_kwh:20}]);
 assert.deepEqual(options,[{id:'CUSTOM',label:'Custom EV (20.0 kWh)'}]);
});
