/**
 * Unit tests for SOC Calculator and Route Display domain logic.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    clampSoc,
    computeRangeKm,
    computeSocDrop,
    classifyEnergyWarning,
    socColor
} from '../../backend/app/static/demo/js/domain/soc-calculator.js';

import {
    escapeHtml,
    formatDistanceKm,
    formatDuration,
    formatCoords,
    formatEtaMin,
    distanceToStationKm
} from '../../backend/app/static/demo/js/domain/route-display.js';

test('clampSoc clamps values to [0, 100] by default', () => {
    assert.equal(clampSoc(50), 50);
    assert.equal(clampSoc(150), 100);
    assert.equal(clampSoc(-10), 0);
    assert.equal(clampSoc('85'), 85);
    assert.equal(clampSoc(null), 0);
});

test('classifyEnergyWarning returns correct level based on range and reserve', () => {
    assert.equal(classifyEnergyWarning(1.0, 2.0), 'CRITICAL');
    assert.equal(classifyEnergyWarning(2.5, 2.0), 'LOW');
    assert.equal(classifyEnergyWarning(15, 2.0), 'WARNING');
    assert.equal(classifyEnergyWarning(50, 2.0), 'NORMAL');
    // Default reserve is 2.0
    assert.equal(classifyEnergyWarning(1.5), 'CRITICAL');
    assert.equal(classifyEnergyWarning(50), 'NORMAL');
});

test('socColor returns red/yellow/green based on percentage', () => {
    assert.equal(socColor(10), '#ef4444');  // < 20
    assert.equal(socColor(19), '#ef4444');
    assert.equal(socColor(20), '#f59e0b'); // >= 20, < 30
    assert.equal(socColor(25), '#f59e0b');
    assert.equal(socColor(30), '#10b981');  // >= 30
    assert.equal(socColor(85), '#10b981');
});

test('computeRangeKm delegates to vehicle_model.js', () => {
    const spec = { usable_kwh: 17.15, consumption_wh_km: 95.0 };
    const range = computeRangeKm(100, spec);
    assert.ok(range > 170 && range < 190, `Expected ~180 km, got ${range}`);
    assert.equal(computeRangeKm(0, spec), 0);
});

test('computeSocDrop delegates to vehicle_model.js', () => {
    const spec = { usable_kwh: 17.15, consumption_wh_km: 95.0 };
    const drop = computeSocDrop(50, spec);
    assert.ok(drop > 27 && drop < 28, `Expected ~27.7%, got ${drop}`);
    assert.equal(computeSocDrop(0, spec), 0);
});

test('escapeHtml prevents XSS injection', () => {
    assert.equal(escapeHtml('<script>alert(1)</script>'), '&lt;script&gt;alert(1)&lt;/script&gt;');
    assert.equal(escapeHtml('"double" and \'single\''), '&quot;double&quot; and &#039;single&#039;');
    assert.equal(escapeHtml('A & B'), 'A &amp; B');
    assert.equal(escapeHtml(null), '');
    assert.equal(escapeHtml(123), '123');
});

test('formatDistanceKm formats meters for < 1km, km otherwise', () => {
    assert.equal(formatDistanceKm(0.5), '500 m');
    assert.equal(formatDistanceKm(1.5), '1.5 km');
    assert.equal(formatDistanceKm(0.123), '123 m');
    assert.equal(formatDistanceKm(10.999, 0), '11 km');
    assert.equal(formatDistanceKm(null), '—');
});

test('formatDuration converts seconds to human-readable duration', () => {
    assert.equal(formatDuration(30), '30s');
    assert.equal(formatDuration(60), '1m');
    assert.equal(formatDuration(90), '1m');
    assert.equal(formatDuration(120), '2m');
    assert.equal(formatDuration(3661), '1h 1m');
    assert.equal(formatDuration(null), '—');
    assert.equal(formatDuration(-1), '—');
});

test('formatCoords formats lat/lng to 4 decimals', () => {
    assert.equal(formatCoords(21.0285, 105.8542), '21.0285, 105.8542');
    assert.equal(formatCoords(21.0285123, 105.8542678, 6), '21.028512, 105.854268');
    assert.equal(formatCoords(null, 105.85), '—');
    assert.equal(formatCoords(21.0, null), '—');
    assert.equal(formatCoords(21.0, 105.0, 2), '21.00, 105.00');
});

test('formatEtaMin converts seconds to Vietnamese minutes string', () => {
    assert.equal(formatEtaMin(120), '2 phút');
    assert.equal(formatEtaMin(90), '2 phút');
    assert.equal(formatEtaMin(null), '—');
});

test('distanceToStationKm returns 0 for null inputs', () => {
    assert.equal(distanceToStationKm(null, { latitude: 21.0, longitude: 105.0 }), 0);
    assert.equal(distanceToStationKm({ latitude: 21.0, longitude: 105.0 }, null), 0);
    const dist = distanceToStationKm(
        { latitude: 21.0285, longitude: 105.8542 },
        { latitude: 21.0285, longitude: 105.8542 }
    );
    assert.equal(dist, 0);
});
