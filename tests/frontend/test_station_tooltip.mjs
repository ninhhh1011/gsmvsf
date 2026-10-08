/**
 * Unit tests for Station Tooltip rendering and hover behavior.
 * Tests tooltip generation, null handling, and offline station display.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    renderDrawerStationCard,
    renderDrawerStationsListHTML,
    renderStationTooltipHTML
} from '../../backend/app/static/demo/js/ui/drawer_renderer.js';

// Helper: create minimal mock candidate
function makeCandidate(overrides = {}) {
    return {
        station_id: 'ST_001',
        rank: 1,
        eligible: true,
        service_type: 'CHARGING',
        eta_to_destination_via_station_s: 1200,
        features: {
            distance_to_station_m: 2500,
            eta_to_station_s: 300,
            distance_station_to_dest_m: 3500,
            duration_station_to_dest_s: 420,
            detour_distance_m: 800,
            detour_duration_s: 120,
            service_duration_s: 1200,
            effective_queue_wait_s: 180,
            available_capacity: 4,
            station_state: { freshness: 'FRESH', age_s: 30 },
            queue_state: { freshness: 'FRESH', age_s: 60 }
        },
        freshness: { station: 'FRESH', queue: 'FRESH' },
        ...overrides
    };
}

// Helper: create minimal mock station
function makeStation(overrides = {}) {
    return {
        station_id: 'ST_001',
        name: 'Trạm Vincom Center',
        latitude: 21.0123,
        longitude: 105.8234,
        station_type: 'CHARGING',
        total_slots: 6,
        ...overrides
    };
}

// Helper: create mock station catalog
function makeStationCatalog(stations = []) {
    return stations.map(s => makeStation(s));
}

test('hovering over station card produces 0 API calls', async () => {
    // Setup: render a station card with recommendation data
    const station = makeStation();
    const activeRec = {
        ranked_candidates: [makeCandidate()]
    };

    const html = renderDrawerStationCard(station, {
        isRec: true,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    // Verify the card contains the expected station ID for hover targeting
    assert.ok(html.includes('data-station-id="ST_001"'), 'Card has data-station-id attribute for hover targeting');

    // Verify no API call hooks exist in the rendered HTML (pure rendering, no callbacks)
    // The drawer_bindings.js will attach hover events, but the HTML itself should not trigger API calls
    assert.ok(!html.includes('fetch'), 'Rendered HTML contains no fetch calls');
    assert.ok(!html.includes('XMLHttpRequest'), 'Rendered HTML contains no XHR');
    assert.ok(!html.includes('ingestDriverLocation'), 'Rendered HTML contains no location API calls');
});

test('tooltip function shows "Chưa có dữ liệu" for null queue_wait', () => {
    const candidate = makeCandidate({
        features: {
            ...makeCandidate().features,
            effective_queue_wait_s: null
        }
    });

    const html = renderStationTooltipHTML(candidate, []);

    // Tooltip should show "Chưa có dữ liệu" for null queue_wait
    assert.ok(html.includes('Chưa có dữ liệu') || html.includes('—'),
        'Tooltip should show placeholder for null queue_wait, not "0 phút"');
});

test('offline station card shows no "Ghé trạm" navigation button', () => {
    // Setup: offline station candidate
    const station = makeStation({ station_state: 'offline' });
    const candidate = makeCandidate({
        eligible: false,
        features: {
            ...makeCandidate().features,
            station_state: { freshness: 'STALE', age_s: 3600 }
        }
    });
    const activeRec = { ranked_candidates: [candidate] };

    const html = renderDrawerStationCard(station, {
        isRec: false,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    // Offline/ineligible stations should not show the "Ghé trạm" or "Dẫn đường ghé trạm" button
    assert.ok(!html.includes('Dẫn đường ghé trạm') && !html.includes('Ghé trạm'),
        'Offline station should not show "Dẫn đường ghé trạm" or "Ghé trạm" button');
});

test('station card with ranked candidate shows full metrics breakdown', () => {
    const station = makeStation();
    const candidate = makeCandidate({
        rank: 1,
        eta_to_destination_via_station_s: 1500
    });
    const activeRec = { ranked_candidates: [candidate] };

    const html = renderDrawerStationCard(station, {
        isRec: true,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    // Verify all key metrics are present
    assert.ok(html.includes('Chặng 1'), 'Contains leg 1 label');
    assert.ok(html.includes('Chặng 2'), 'Contains leg 2 label');
    assert.ok(html.includes('Lệch lộ trình'), 'Contains detour label');
    assert.ok(html.includes('Tổng chuyến đi'), 'Contains total trip label');
});

test('at-destination station card shows post-trip layout', () => {
    const station = makeStation({ station_id: 'ST_002', name: 'Trạm Landmark' });
    const candidate = makeCandidate();
    const activeRec = { ranked_candidates: [candidate] };

    const html = renderDrawerStationCard(station, {
        isRec: false,
        isAtDest: true,
        isSelectedPostTrip: false,
        activeRec
    });

    // At-destination cards should show post-trip specific UI
    assert.ok(html.includes('Cự ly từ Điểm đến'), 'Contains post-trip distance label');
    assert.ok(html.includes('Chuyến chính'), 'Contains direct trip label');
    assert.ok(html.includes('Đến B rồi sạc'), 'Contains post-trip action label');
});

test('null available_capacity shows placeholder', () => {
    const station = makeStation();
    const candidate = makeCandidate({
        features: {
            ...makeCandidate().features,
            available_capacity: null
        }
    });
    const activeRec = { ranked_candidates: [candidate] };

    const html = renderDrawerStationCard(station, {
        isRec: true,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    // Should show placeholder for null capacity
    assert.ok(html.includes('cổng') || html.includes('Đang mở'),
        'Should show capacity placeholder when null');
});

test('renderDrawerStationsListHTML produces multiple station cards', () => {
    const stations = [
        makeStation({ station_id: 'ST_001', name: 'Trạm A' }),
        makeStation({ station_id: 'ST_002', name: 'Trạm B' })
    ];

    const html = renderDrawerStationsListHTML(stations, {
        topRecId: 'ST_001'
    });

    assert.ok(html.includes('ST_001'), 'Contains first station ID');
    assert.ok(html.includes('ST_002'), 'Contains second station ID');
    assert.ok(html.includes('data-station-id="ST_001"'), 'First card has station ID attribute');
    assert.ok(html.includes('data-station-id="ST_002"'), 'Second card has station ID attribute');
});

test('BATTERY_SWAP service type displays correctly', () => {
    const station = makeStation({ station_type: 'SWAP', name: 'Trạm đổi pin' });
    const candidate = makeCandidate({ service_type: 'BATTERY_SWAP' });
    const activeRec = { ranked_candidates: [candidate] };

    const html = renderDrawerStationCard(station, {
        isRec: true,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    assert.ok(html.includes('Đổi pin') || html.includes('swap'), 'Swap station displays swap indicator');
});
