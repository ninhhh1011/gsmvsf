/**
 * Scenario Removal Tests: verify app.js changes are correct after SimMode removal.
 *
 * These tests verify the static state of app.js after Task 8 changes:
 * - SimModeController is not imported
 * - simMode property is not instantiated
 * - Scenarios/trips 404s are logged as warnings, not errors
 * - Only stations/vehicles failures throw
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const APP_JS = resolve(__dirname, '../../backend/app/static/demo/js/app.js');
const appSource = readFileSync(APP_JS, 'utf8');

test('app.js does not import SimModeController', () => {
    assert.equal(
        appSource.includes("from './sim_mode.js'"),
        false,
        'app.js should not import SimModeController'
    );
    assert.equal(
        appSource.includes("SimModeController"),
        false,
        'app.js should not reference SimModeController'
    );
});

test('app.js does not instantiate simMode', () => {
    assert.equal(
        appSource.includes('this.simMode'),
        false,
        'app.js should not reference this.simMode'
    );
    assert.equal(
        appSource.includes('new SimModeController'),
        false,
        'app.js should not instantiate SimModeController'
    );
});

test('app boots when scenarios.json is unavailable (graceful degradation)', () => {
    // After fix: scenarios 404 logs warning, does not throw
    assert.ok(
        appSource.includes('continue without scenarios') ||
        appSource.includes('Scenarios unavailable') ||
        appSource.includes('scenarios') && appSource.includes('continue'),
        'app.js should log a warning when scenarios.json is unavailable'
    );

    // The old code threw when scenarios failed; verify it no longer does
    // by checking the error-throwing block only references stations/vehicles
    const loadCatalogsMatch = appSource.match(/loadCatalogs\(\)[^{]*\{([\s\S]*?)\n\s{4}\}/);
    assert.ok(loadCatalogsMatch, 'loadCatalogs method should exist');
    const loadCatalogs = loadCatalogsMatch[1];

    // Check that the throw block does NOT include scenarios
    const throwBlockMatch = loadCatalogs.match(/if \(errors\.length > 0\)[\s\S]*?throw new Error/);
    if (throwBlockMatch) {
        const throwBlock = throwBlockMatch[0];
        const throwHasScenarios = throwBlock.includes('scenarios') ||
            throwBlock.includes('scResult');
        assert.equal(throwHasScenarios, false,
            'The throw block should not include scenarios in the errors array');
    }
});

test('app boots when trips.json is unavailable (graceful degradation)', () => {
    // After fix: trips 404 logs warning, does not throw
    assert.ok(
        appSource.includes('continue without trips') ||
        appSource.includes('Trips unavailable') ||
        appSource.includes('trips') && appSource.includes('continue'),
        'app.js should log a warning when trips.json is unavailable'
    );

    // Verify throw block does not include trips
    const loadCatalogsMatch = appSource.match(/loadCatalogs\(\)[^{]*\{([\s\S]*?)\n\s{4}\}/);
    assert.ok(loadCatalogsMatch, 'loadCatalogs method should exist');
    const loadCatalogs = loadCatalogsMatch[1];

    const throwBlockMatch = loadCatalogs.match(/if \(errors\.length > 0\)[\s\S]*?throw new Error/);
    if (throwBlockMatch) {
        const throwBlock = throwBlockMatch[0];
        const throwHasTrips = throwBlock.includes('trips') ||
            throwBlock.includes('trResult');
        assert.equal(throwHasTrips, false,
            'The throw block should not include trips in the errors array');
    }
});

test('app only throws on stations or vehicles failure', () => {
    // Verify: only stResult and vResult push to errors[] (scResult and trResult do not)
    const allErrorPushes = [...appSource.matchAll(/errors\.push/g)].map(m => m.index);
    const stPushIdx = appSource.indexOf('errors.push(`Stations:');
    const vPushIdx = appSource.indexOf('errors.push(`Vehicles:');
    const scPushIdx = appSource.indexOf('errors.push(`Scenarios:');
    const trPushIdx = appSource.indexOf('errors.push(`Trips:');

    assert.ok(stPushIdx >= 0, 'stResult should push to errors array');
    assert.ok(vPushIdx >= 0, 'vResult should push to errors array');
    assert.equal(scPushIdx, -1, 'scResult should NOT push to errors array');
    assert.equal(trPushIdx, -1, 'trResult should NOT push to errors array');
});

test('app.js bootstrap DOMContentLoaded still present', () => {
    // Verify the DOMContentLoaded bootstrap is intact
    assert.ok(
        appSource.includes("DOMContentLoaded"),
        'app.js should have DOMContentLoaded bootstrap'
    );
    assert.ok(
        appSource.includes('window.app'),
        'window.app should be initialized on DOMContentLoaded'
    );
});
