/**
 * Unit tests for Station Evaluator domain logic.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    isStationCompatibleWithVehicle,
    filterStations,
    computeTotalCandidateCostSeconds
} from '../../backend/app/static/demo/js/domain/station_evaluator.js';

test('isStationCompatibleWithVehicle enforces category and connector capabilities', () => {
    const carVehicle = {
        vehicle_type: 'EV_CAR',
        charging_supported: true,
        swap_supported: false
    };

    const bikeVehicle = {
        vehicle_type: 'EV_MOTORBIKE',
        charging_supported: false,
        swap_supported: true
    };

    // Standard DC Fast Charger (car charging)
    const dcStation = {
        connector_type: 'CCS2_DC',
        total_charging_slots: 4,
        battery_type: 'NONE',
        total_swap_slots: 0
    };

    // Swap station (motorbike battery swap)
    const swapStation = {
        connector_type: null,
        total_charging_slots: 0,
        battery_type: 'LFP_SWAP_PACK',
        total_swap_slots: 8
    };

    // Multi-service station (both car and bike)
    const comboStation = {
        connector_type: 'CCS2_DC',
        total_charging_slots: 4,
        battery_type: 'LFP_SWAP_PACK',
        total_swap_slots: 8
    };

    // Car checks: Can charge at dcStation and comboStation, cannot swap at swapStation
    assert.equal(isStationCompatibleWithVehicle(dcStation, carVehicle), true);
    assert.equal(isStationCompatibleWithVehicle(swapStation, carVehicle), false);
    assert.equal(isStationCompatibleWithVehicle(comboStation, carVehicle), true);

    // Swap-only motorbike checks: Can use swapStation and comboStation, cannot use DC car charger
    assert.equal(isStationCompatibleWithVehicle(dcStation, bikeVehicle), false);
    assert.equal(isStationCompatibleWithVehicle(swapStation, bikeVehicle), true);
    assert.equal(isStationCompatibleWithVehicle(comboStation, bikeVehicle), true);
});

test('filterStations filters by station capabilities and vehicle type', () => {
    const stations = [
        { station_id: 'S1', connector_type: 'CCS2_DC', total_charging_slots: 4, battery_type: 'NONE', total_swap_slots: 0 },
        { station_id: 'S2', connector_type: null, total_charging_slots: 0, battery_type: 'LFP', total_swap_slots: 8 },
        { station_id: 'S3', connector_type: 'CCS2_DC', total_charging_slots: 2, battery_type: 'LFP', total_swap_slots: 4 }
    ];

    const car = { vehicle_type: 'EV_CAR', charging_supported: true, swap_supported: false };
    const swapBike = { vehicle_type: 'EV_MOTORBIKE', charging_supported: false, swap_supported: true };

    // Filter by vehicle capability
    const carFiltered = filterStations(stations, 'COMPATIBLE', car);
    assert.equal(carFiltered.length, 2);
    assert.deepEqual(carFiltered.map(s => s.station_id), ['S1', 'S3']);

    const bikeFiltered = filterStations(stations, 'COMPATIBLE', swapBike);
    assert.equal(bikeFiltered.length, 2);
    assert.deepEqual(bikeFiltered.map(s => s.station_id), ['S2', 'S3']);

    // Filter by type: SWAP only
    const swapOnly = filterStations(stations, 'SWAP', null);
    assert.equal(swapOnly.length, 2);
    assert.deepEqual(swapOnly.map(s => s.station_id), ['S2', 'S3']);

    // Filter by type: CHARGING only
    const chargingOnly = filterStations(stations, 'CHARGING', null);
    assert.equal(chargingOnly.length, 2);
    assert.deepEqual(chargingOnly.map(s => s.station_id), ['S1', 'S3']);
});

test('computeTotalCandidateCostSeconds aggregates travel, queue, service, and detour time', () => {
    // 300s travel + 120s queue + 1200s service + 180s detour = 1800s
    const totalS = computeTotalCandidateCostSeconds(300, 120, 1200, 180);
    assert.equal(totalS, 1800);

    // Handles zero or null gracefully
    assert.equal(computeTotalCandidateCostSeconds(null, 0, 600, null), 600);
});
