/**
 * Unit tests for Vehicle Model domain logic and multi-brand EV specifications.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    straightLineDistanceKm,
    EARTH_RADIUS_KM,
    DEFAULT_MODEL_SPECS,
    MODEL_SPECS,
    VINFAST_MODEL_SPECS,
    registerVehicleModel,
    getVehicleModelSpec,
    calculateEstimatedRangeKm,
    calculateSocDepletion
} from '../../backend/app/static/demo/js/domain/vehicle_model.js';

test('MODEL_SPECS defines standard VinFast fleet models', () => {
    assert.ok(MODEL_SPECS.VF_3, 'VF_3 defined');
    assert.ok(MODEL_SPECS.VF_5, 'VF_5 defined');
    assert.ok(MODEL_SPECS.VF_8, 'VF_8 defined');
    assert.ok(MODEL_SPECS.VF_9, 'VF_9 defined');
    assert.ok(MODEL_SPECS.FELIZ_S, 'FELIZ_S defined');
    assert.ok(MODEL_SPECS.EVO_200, 'EVO_200 defined');
    assert.ok(MODEL_SPECS.KLARA_S, 'KLARA_S defined');

    // Backward compatibility alias
    assert.equal(VINFAST_MODEL_SPECS, MODEL_SPECS);
});

test('calculateEstimatedRangeKm scales linearly with SOC percentage', () => {
    const vf8 = MODEL_SPECS.VF_8; // 80.68 kWh, 195 Wh/km => ~413.7 km full range
    const maxRange = (vf8.usable_kwh * 1000.0) / vf8.consumption_wh_km;
    
    const range100 = calculateEstimatedRangeKm(100, vf8);
    assert.ok(Math.abs(range100 - maxRange) < 0.2, `Expected ~${maxRange}km, got ${range100}`);

    const range50 = calculateEstimatedRangeKm(50, vf8);
    assert.ok(Math.abs(range50 - (maxRange / 2)) < 0.2, `Expected ~${maxRange / 2}km, got ${range50}`);

    const range0 = calculateEstimatedRangeKm(0, vf8);
    assert.equal(range0, 0);

    // Negative SOC clamped to 0
    assert.equal(calculateEstimatedRangeKm(-10, vf8), 0);
});

test('calculateSocDepletion accurately computes battery drop over distance', () => {
    const vf3 = MODEL_SPECS.VF_3; // 17.15 kWh, 95.0 Wh/km
    // At 95 Wh/km, driving 50 km consumes 4.75 kWh
    // 4.75 / 17.15 = ~27.7% SOC drop
    const drop = calculateSocDepletion(50, vf3);
    assert.ok(drop > 27 && drop < 28, `Expected ~27.7%, got ${drop}`);

    // Driving 0 km drops 0%
    assert.equal(calculateSocDepletion(0, vf3), 0);

    // Negative distance drops 0%
    assert.equal(calculateSocDepletion(-5, vf3), 0);
});

test('registerVehicleModel extends catalog with non-VinFast EV brands', () => {
    // Register Tesla Model 3
    registerVehicleModel('TESLA_MODEL_3_PERF', {
        name: 'Tesla Model 3 Performance',
        category: 'EV_CAR',
        battery_kwh: 75.0,
        consumption_kwh_per_km: 0.15,
        brand: 'Tesla',
        connector_types: ['CCS2', 'TESLA_SUPERCHARGER']
    });

    const tesla = getVehicleModelSpec('TESLA_MODEL_3_PERF');
    assert.equal(tesla.name, 'Tesla Model 3 Performance');
    assert.equal(tesla.brand, 'Tesla');
    assert.equal(tesla.usable_kwh, 75.0);

    // Range at 100%: 75 * 1000 / 150 = 500 km
    const range = calculateEstimatedRangeKm(100, tesla);
    assert.equal(range, 500.0);

    // Register Dat Bike Weaver++ (Vietnamese electric motorbike)
    registerVehicleModel('DAT_BIKE_WEAVER_PP', {
        name: 'Dat Bike Weaver++',
        category: 'EV_MOTORBIKE',
        battery_kwh: 5.0,
        consumption_kwh_per_km: 0.025,
        brand: 'Dat Bike',
        connector_types: ['AC_STANDARD']
    });

    const datBike = getVehicleModelSpec('DAT_BIKE_WEAVER_PP');
    assert.equal(datBike.vehicle_type, 'EV_MOTORBIKE');
    // Range at 100%: 5.0 * 1000 / 25 = 200 km
    assert.equal(calculateEstimatedRangeKm(100, datBike), 200.0);
});

test('getVehicleModelSpec falls back to DEFAULT_MODEL_SPECS for unknown keys', () => {
    const unknown = getVehicleModelSpec('UNKNOWN_SPACESHIP');
    assert.equal(unknown.vehicle_model, 'VF_3');
    assert.equal(unknown.display_name, 'VF 3');
});

test('straightLineDistanceKm computes accurate Haversine distances', () => {
    // Distance between Hoan Kiem Lake (21.0285, 105.8542) and Noi Bai Airport (21.2187, 105.8042)
    // Roughly 21.7 km straight line
    const distHanoi = straightLineDistanceKm(21.0285, 105.8542, 21.2187, 105.8042);
    assert.ok(distHanoi > 20 && distHanoi < 23, `Expected ~21.7 km, got ${distHanoi}`);

    // Distance between HCMC District 1 (10.7769, 106.7009) and Tan Son Nhat Airport (10.8184, 106.6588)
    // Roughly 6.4 km straight line
    const distHcmc = straightLineDistanceKm(10.7769, 106.7009, 10.8184, 106.6588);
    assert.ok(distHcmc > 5.5 && distHcmc < 7.5, `Expected ~6.4 km, got ${distHcmc}`);

    // Same point is 0 km
    assert.equal(straightLineDistanceKm(21.0, 105.0, 21.0, 105.0), 0);
});
