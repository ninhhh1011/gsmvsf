/**
 * Unit tests for Vehicle Catalog domain logic.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    fetchVehicleCatalog,
    getCachedCatalog,
    clearCatalogCache
} from '../../backend/app/static/demo/js/domain/vehicle-catalog.js';
import { MODEL_SPECS } from '../../backend/app/static/demo/js/domain/vehicle_model.js';

test('fetchVehicleCatalog fetches and registers catalog from backend', async () => {
    clearCatalogCache();
    // Mock global fetch for this test
    const catalogPayload = [
        {
            id: 'VF_3',
            name: 'VF 3',
            brand: 'VinFast',
            battery_kwh: 17.15,
            efficiency_kwh_per_km: 0.095,
            vehicle_type: 'EV_CAR',
            supported_services: ['charging']
        },
        {
            id: 'EVO200',
            name: 'Evo200',
            brand: 'VinFast',
            battery_kwh: 3.22,
            efficiency_kwh_per_km: 0.040,
            vehicle_type: 'EV_MOTORBIKE',
            supported_services: ['charging', 'battery_swap']
        }
    ];

    const origFetch = globalThis.fetch;
    let called = false;
    globalThis.fetch = async (url) => {
        called = true;
        assert.ok(url.includes('/api/v1/vehicles/catalog'));
        return {
            ok: true,
            json: async () => catalogPayload
        };
    };

    try {
        const result = await fetchVehicleCatalog({});
        assert.equal(called, true, 'fetch was called');
        assert.equal(Array.isArray(result), true);
        assert.equal(result.length, 2);
        assert.equal(result[0].id, 'VF_3');
        assert.equal(result[1].id, 'EVO200');

        // Catalog is cached
        assert.equal(getCachedCatalog(), result);

        // Catalog entries registered in MODEL_SPECS
        const vf3 = MODEL_SPECS['VF_3'];
        assert.ok(vf3, 'VF_3 registered in MODEL_SPECS');
        assert.equal(vf3.usable_kwh, 17.15);
        assert.equal(vf3.consumption_wh_km, 95.0);
        assert.equal(vf3.vehicle_type, 'EV_CAR');

        const evo = MODEL_SPECS['EVO200'];
        assert.ok(evo, 'EVO200 registered in MODEL_SPECS');
        assert.equal(evo.swap_supported, true, 'battery_swap supported');
    } finally {
        globalThis.fetch = origFetch;
        clearCatalogCache();
    }
});

test('fetchVehicleCatalog throws on non-ok response', async () => {
    clearCatalogCache();
    const origFetch = globalThis.fetch;
    globalThis.fetch = async () => ({ ok: false, status: 500 });

    try {
        await assert.rejects(
            fetchVehicleCatalog({}),
            /Vehicle catalog fetch failed: HTTP 500/
        );
    } finally {
        globalThis.fetch = origFetch;
        clearCatalogCache();
    }
});

test('fetchVehicleCatalog throws on non-array response', async () => {
    clearCatalogCache();
    const origFetch = globalThis.fetch;
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ error: 'not an array' }) });

    try {
        await assert.rejects(
            fetchVehicleCatalog({}),
            /Vehicle catalog did not return an array/
        );
    } finally {
        globalThis.fetch = origFetch;
        clearCatalogCache();
    }
});

test('clearCatalogCache resets the cached catalog', async () => {
    clearCatalogCache();
    assert.equal(getCachedCatalog(), null);
});
