import test from 'node:test';
import assert from 'node:assert/strict';

import { renderDriverRecommendation, renderRecommendationPanelHTML } from '../../backend/app/static/demo/js/ui/driver_recommendation_renderer.js';
import { DriverModeController } from '../../backend/app/static/demo/js/ui/driver_controller.js';

test('renders the top station summary and escapes station supplied markup', () => {
    const html = renderDriverRecommendation({
        has_recommendation: true,
        ranked_candidates: [{
            station_id: '<img src=x onerror=alert(1)>',
            service_type: 'BATTERY_SWAP',
            eta_to_station_s: 300,
            eta_to_service_complete_s: 900,
            eta_to_destination_via_station_s: 1800,
            distance_vehicle_to_station_m: 2000,
            queue_wait_s: 120,
            score: 0.75,
            features: { service_duration_s: 600, available_capacity: 2 }
        }]
    });

    assert.match(html, /border-swap/);
    assert.match(html, /btn-nav-station/);
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(html, /<img src=x/);
});

test('renders no recommendation as an empty snippet', () => {
    assert.equal(renderDriverRecommendation({ has_recommendation: false }), '');
    assert.equal(renderDriverRecommendation(null), '');
});

test('recommendation panel renderer escapes station IDs and names', () => {
    const html = renderRecommendationPanelHTML([{ station_id: '<img src=x>', score: 0.5 }], [{ station_id: '<img src=x>', name: '<script>bad</script>' }]);
    assert.match(html, /&lt;script&gt;bad&lt;\/script&gt;/);
    assert.match(html, /data-station-id="&lt;img src=x&gt;"/);
    assert.doesNotMatch(html, /<script>|data-station-id="<img/);
});

test('controller puts the extracted recommendation renderer output in the active HUD', () => {
    const rec = {
        has_recommendation: true,
        ranked_candidates: [{
            station_id: 'ST<42>', service_type: 'CHARGING', eta_to_station_s: 60,
            eta_to_service_complete_s: 120, final_cost_s: 120, score: 0.2, features: {}
        }]
    };
    let renderedHtml = '';
    const controller = Object.create(DriverModeController.prototype);
    Object.assign(controller, {
        lastRecommendation: rec, remainingTripDistanceKm: 0, matchedPos: null, currentPos: null,
        replay: { getProgressText: () => '', isPlaying: false, currentIndex: 0 },
        currentSocPct: 50, estimatedRangeKm: 100, _navigationLocked: false,
        bindings: { renderActive(html, state) { renderedHtml = state.recommendation; assert.match(html, /driver-active-hud/); assert.match(html, /id="btn-change-station"/); assert.doesNotMatch(html, /onclick=/); } }
    });
    controller.renderTripActiveUI();
    assert.equal(renderedHtml, renderDriverRecommendation(rec));
    assert.match(renderedHtml, /ST&lt;42&gt;/);
});

test('escapes nonnumeric available capacity instead of inserting it as markup', () => {
    const html = renderDriverRecommendation({
        has_recommendation: true,
        ranked_candidates: [{
            station_id: 'ST_1', service_type: 'CHARGING', eta_to_station_s: 60,
            eta_to_service_complete_s: 120, final_cost_s: 120, score: 0.2,
            features: { available_capacity: '<img src=x onerror=alert(1)>' }
        }]
    });
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(html, /<img src=x/);
});
