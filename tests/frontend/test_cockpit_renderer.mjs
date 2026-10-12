/**
 * Unit tests for Cockpit UI Card Renderer (Available, Offline, Trip Complete).
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

import {
    renderAvailableCardHTML,
    renderDriverAnalysisHTML,
    renderOfflineCardHTML,
    renderTripCompleteCardHTML,
    renderPositionStatusHTML,
    renderPostTripBannerHTML,
    renderStatusBadge,
    renderReplayControls
} from '../../backend/app/static/demo/js/ui/cockpit_renderer.js';
import { renderEnergyWarningBanner } from '../../backend/app/static/demo/js/components.js';

test('cockpit renderer owns driver-state labels and replay presentation', () => {
    assert.equal(renderStatusBadge('TRIP_ACTIVE').label, '\u0110ANG DI CHUY\u1ec2N');
    assert.equal(renderStatusBadge('UNKNOWN').label, 'UNKNOWN');
    const initial = renderReplayControls({ isPlaying: false, currentIndex: 0 });
    const resumed = renderReplayControls({ isPlaying: false, currentIndex: 2 });
    const playing = renderReplayControls({ isPlaying: true, currentIndex: 2 });
    assert.equal(initial.playText, '\u25b6 B\u1eaft \u0111\u1ea7u');
    assert.equal(resumed.playText, '\u25b6 Ti\u1ebfp t\u1ee5c');
    assert.equal(playing.playText, '\u25b6 \u0110ang ch\u1ea1y...');
    assert.equal(initial.playClass, 'btn btn-primary btn-sm flex-1');
    assert.equal(initial.pauseClass, 'btn btn-outline btn-sm flex-1');
    assert.equal(playing.playClass, 'btn btn-outline btn-sm flex-1');
    assert.equal(playing.pauseClass, 'btn btn-primary btn-sm flex-1');
});

test('driver controller coordinates replay facts without owning labels or button presentation', async () => {
    const source = await readFile(new URL('../../backend/app/static/demo/js/ui/driver_controller.js', import.meta.url), 'utf8');
    assert.doesNotMatch(source, /SẴN SÀNG|ĐÃ NHẬN CHUYẾN|ĐANG DI CHUYỂN|HOÀN THÀNH|NGOẠI TUYẾN/);
    assert.doesNotMatch(source, /▶ (?:Đang chạy|Tiếp tục|Bắt đầu)|btn-(?:outline|primary) btn-sm flex-1/);
});

test('energy warning renderer treats unknown external reasons as unavailable', () => {
    const html = renderEnergyWarningBanner({
        need_service: true,
        reason_code: '<img src=x onerror=alert(1)>',
        estimated_remaining_range_km: 10,
        remaining_trip_distance_km: 20
    });
    assert.match(html, /Chưa có đánh giá năng lượng/);
    assert.doesNotMatch(html, /<img src=x/);
});

test('position renderer escapes external road IDs and preserves raw GPS presentation', () => {
    assert.match(renderPositionStatusHTML({ road_segment_id: '<img src=x>' }, null), /&lt;img src=x&gt;/);
    assert.doesNotMatch(renderPositionStatusHTML({ road_segment_id: '<img src=x>' }, null), /<img src=x>/);
    assert.match(renderPositionStatusHTML(null, { latitude: 0, longitude: 1 }), /0\.0000, 1\.0000/);
});

test('post trip banner renderer escapes station supplied markup', () => {
    const html = renderPostTripBannerHTML({ station_id: '<script>x</script>' }, { distance_m: 1200 });
    assert.match(html, /&lt;script&gt;x&lt;\/script&gt;/);
    assert.doesNotMatch(html, /<script>/);
    assert.match(html, /1\.2 km/);
});

test('ready primary card keeps action while analysis contains coordinates', () => {
    const html = renderAvailableCardHTML();
    assert.match(html, /btn-accept-trip/); assert.doesNotMatch(html, /text-origin-coords|btn-pick-origin-map/);
    const analysis = renderDriverAnalysisHTML({state: 'AVAILABLE', currentSocPct: 50, estimatedRangeKm: 80, customOrigin: {latitude: 0, longitude: 1}, customDestination: {latitude: 2, longitude: 3}});
    assert.match(analysis, /0\.0000, 1\.0000/); assert.match(analysis, /2\.0000, 3\.0000/);
});

test('renderOfflineCardHTML renders offline cockpit state with reconnect button', () => {
    const html = renderOfflineCardHTML();

    assert.ok(html.includes('Tài xế đang ngoại tuyến'), 'Contains offline title');
    assert.ok(html.includes('Bật trực tuyến để nhận phân phối chuyến đi'), 'Contains offline message');
    assert.ok(html.includes('btn-go-online'), 'Contains go online button');
});

test('renderTripCompleteCardHTML renders completion state with post-trip option', () => {
    const lastRec = {
        has_recommendation: true,
        ranked_candidates: [
            {
                station_id: 'ST_001',
                rank: 1,
                eta_to_station_s: 300,
                features: {
                    base_travel_duration_s: 300,
                    detour_duration_s: 60,
                    detour_distance_m: 500,
                    service_duration_s: 1200,
                    effective_queue_wait_s: 0
                }
            }
        ]
    };
    const postTripStation = {
        station_id: 'ST_001',
        name: 'Trạm Sạc VinFast Big C'
    };

    const html = renderTripCompleteCardHTML(lastRec, postTripStation);

    assert.ok(html.includes('Chuyến đi hoàn tất'), 'Contains completion title');
    assert.ok(html.includes('BƯỚC TIẾP THEO: ĐI SẠC PIN'), 'Displays post-trip banner');
    assert.ok(html.includes('Trạm Sạc VinFast Big C'), 'Contains post-trip station name');
    assert.ok(html.includes('btn-start-post-trip-nav'), 'Contains start post-trip navigation button');
    assert.ok(html.includes('btn-back-available'), 'Contains back to available button');
});

test('renderTripCompleteCardHTML handles trip without scheduled post-trip station', () => {
    const html = renderTripCompleteCardHTML(null, null);

    assert.ok(html.includes('Chuyến đi hoàn tất'), 'Contains completion title');
    assert.ok(html.includes('Hành khách đã xuống xe an toàn'), 'Contains safe dropoff text');
    assert.ok(!html.includes('btn-start-post-trip-nav'), 'Does not render post-trip nav button');
    assert.ok(html.includes('btn-back-available'), 'Contains back to available button');
});
