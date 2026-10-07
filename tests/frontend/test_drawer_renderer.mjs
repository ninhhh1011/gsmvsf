/**
 * Unit tests for Station Drawer Card Renderer.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    renderDrawerStationCard,
    renderDrawerStationsListHTML
} from '../../backend/app/static/demo/js/ui/drawer_renderer.js';

test('renderDrawerStationCard renders en-route station card with legs and detour', () => {
    const station = {
        station_id: 'ST_001',
        name: 'Trạm Vincom Center',
        latitude: 21.0123,
        longitude: 105.8234,
        distKm: '2.5',
        station_type: 'CHARGING',
        total_slots: 6
    };

    const activeRec = {
        ranked_candidates: [
            {
                station_id: 'ST_001',
                rank: 1,
                eta_to_station_s: 300,
                score: 1.25,
                features: {
                    distance_to_station_m: 2500,
                    distance_station_to_dest_m: 3500,
                    duration_station_to_dest_s: 420,
                    detour_distance_m: 800,
                    detour_duration_s: 120,
                    observed_queue_wait_s: 0,
                    service_duration_s: 1200
                }
            }
        ]
    };

    const html = renderDrawerStationCard(station, {
        isRec: true,
        isAtDest: false,
        activeRec,
        topRecId: 'ST_001'
    });

    assert.ok(html.includes('Trạm ST_001'), 'Contains station ID');
    assert.ok(html.includes('Trạm Vincom Center'), 'Contains station name');
    assert.ok(html.includes('ĐỀ XUẤT TỐI ƯU'), 'Displays recommended badge');
    assert.ok(html.includes('Chặng 1 (Xe ➔ Trạm)'), 'Displays leg 1 label');
    assert.ok(html.includes('Chặng 2 (Trạm ➔ B)'), 'Displays leg 2 label');
    assert.ok(html.includes('Lệch lộ trình (Detour)'), 'Displays detour label');
    assert.ok(html.includes('btn-nav-drawer-station'), 'Contains navigate button');
});

test('renderDrawerStationCard renders at-destination post-trip station card layout', () => {
    const station = {
        station_id: 'ST_002',
        name: 'Trạm Đổi Pin Landmark',
        latitude: 21.025,
        longitude: 105.850,
        distKm: '1.2',
        station_type: 'SWAP',
        swap_slots: 8
    };

    const html = renderDrawerStationCard(station, {
        isRec: false,
        isAtDest: true,
        isSelectedPostTrip: false
    });

    assert.ok(html.includes('Cự ly từ Điểm đến (B) ➔ Trạm'), 'Displays post-trip destination leg');
    assert.ok(html.includes('Chuyến chính (A ➔ B thẳng)'), 'Displays direct trip label');
    assert.ok(html.includes('btn-nav-post-trip-station'), 'Contains post-trip select button');
});

test('renderDrawerStationsListHTML renders empty state when no stations match filter', () => {
    const emptyHtml = renderDrawerStationsListHTML([], {});
    assert.ok(emptyHtml.includes('Không tìm thấy trạm phù hợp với bộ lọc'), 'Renders empty state');
});

test('renderDrawerStationsListHTML maps multiple stations into cards', () => {
    const stations = [
        { station_id: 'ST_1', latitude: 21.01, longitude: 105.81, station_type: 'CHARGING' },
        { station_id: 'ST_2', latitude: 21.02, longitude: 105.82, station_type: 'SWAP' }
    ];

    const html = renderDrawerStationsListHTML(stations, { topRecId: 'ST_1' });
    assert.ok(html.includes('Trạm ST_1'));
    assert.ok(html.includes('Trạm ST_2'));
});
