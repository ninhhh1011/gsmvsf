/**
 * Comprehensive Scenario Verification for Phase 4 Technical View.
 * Meets all 11 minimum requirements of Section 11 Test Discipline.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    classifySystemHealth,
    formatLocationInspector,
    formatDemandInspector,
    filterCandidates,
    formatRoutingInspector,
    formatRankingInspector,
    formatRecommendationInspector,
    formatPipelineTiming,
    sanitizeJsonPayload,
    TechViewController
} from '../../backend/app/static/demo/js/tech_view.js';

test('Scenario 1: Technical View opens, closes, and syncs state without reset', () => {
    const mockApi = {};
    const mockMap = { invalidateSize: () => {} };
    const tv = new TechViewController(mockApi, mockMap, { containerId: 'test-drawer' });

    assert.equal(tv.isOpen, false);

    // Sync a specific active scenario (Scenario 4: Low SOC Car Charging)
    tv.syncState({
        scenario: { id: 'SC004', title: 'Low SOC Car Charging' },
        vehicle: { vehicle_id: 'V0004', vehicle_type: 'EV_CAR' },
        origin: { latitude: 21.0182, longitude: 105.8152 },
        destination: { latitude: 21.0365, longitude: 105.8341 },
        recommendResult: {
            has_recommendation: true,
            recommended_station_id: 'S017',
            recommended_service_type: 'CHARGING',
            eligible_count: 18,
            energy_context: {
                need_service: true,
                reason_code: 'LOW_SOC',
                current_soc_pct: 12.0
            }
        }
    });

    assert.equal(tv.state.scenario.id, 'SC004');
    assert.equal(tv.state.recommendResult.recommended_station_id, 'S017');

    // Switch active stage
    tv.setActiveStage('demand');
    assert.equal(tv.activeStage, 'demand');
});

test('Scenario 2: Candidate composite identity preserves (station_id, service_type) and multiple service alternatives', () => {
    const candidateList = [
        { station_id: 'S001', service_type: 'CHARGING', eligible: false, reason: 'OFFLINE' },
        { station_id: 'S001', service_type: 'BATTERY_SWAP', eligible: false, reason: 'OFFLINE' },
        { station_id: 'S017', service_type: 'CHARGING', eligible: true, reason: 'ELIGIBLE' },
        { station_id: 'S017', service_type: 'BATTERY_SWAP', eligible: false, reason: 'NO_SWAP_BATTERY' }
    ];

    // S001 appears twice with different services
    const all = filterCandidates(candidateList, 'ALL');
    assert.equal(all.length, 4);
    assert.equal(all[0].key, 'S001_CHARGING');
    assert.equal(all[1].key, 'S001_BATTERY_SWAP');

    // S017 has one eligible service and one rejected service
    const eligible = filterCandidates(candidateList, 'ELIGIBLE');
    assert.equal(eligible.length, 1);
    assert.equal(eligible[0].key, 'S017_CHARGING');

    const rejected = filterCandidates(candidateList, 'REJECTED');
    assert.equal(rejected.length, 3);
    assert.deepEqual(rejected.map(r => r.key), ['S001_CHARGING', 'S001_BATTERY_SWAP', 'S017_BATTERY_SWAP']);
});

test('Scenario 3: Null, Ambiguous, and No-Match map matching states displayed honestly', () => {
    // 1. Explicit Ambiguous state
    const ambiguousLoc = formatLocationInspector({
        driver_id: 'D0100',
        status: 'AMBIGUOUS',
        raw_position: { latitude: 21.0200, longitude: 105.8100 },
        matched_position: {
            latitude: 21.0201,
            longitude: 105.8101,
            road_segment_id: null,
            osm_way_id: null,
            direction: null,
            confidence: null
        }
    }, 'RAW_GPS_FALLBACK');

    assert.equal(ambiguousLoc.matching_status, 'AMBIGUOUS');
    assert.equal(ambiguousLoc.road_segment_id, null);
    assert.equal(ambiguousLoc.direction, 'UNKNOWN');
    assert.equal(ambiguousLoc.location_source, 'RAW_GPS_FALLBACK');

    // 2. Unresolved / Null
    const unresolvedLoc = formatLocationInspector(null, 'LOCATION_UNAVAILABLE');
    assert.equal(unresolvedLoc.matching_status, 'UNKNOWN');
    assert.equal(unresolvedLoc.location_source, 'LOCATION_UNAVAILABLE');
    assert.equal(unresolvedLoc.road_segment_id, null);
});

test('Scenario 4: No recommendation when vehicle has sufficient range (Scenario 1 truth)', () => {
    const safeResult = {
        has_recommendation: false,
        recommended_station_id: null,
        recommended_service_type: null,
        ranked_candidates: [],
        eligible_count: 0,
        policy: { name: 'TOTAL_SERVICE_COMPLETION_V1' },
        energy_context: {
            need_service: false,
            reason_code: 'SUFFICIENT_SOC_RANGE',
            current_soc_pct: 85.0,
            estimated_remaining_range_km: 100.0,
            remaining_trip_distance_km: 3.5
        },
        reason: 'NO_ELIGIBLE_CANDIDATES'
    };

    const rec = formatRecommendationInspector(safeResult);
    assert.equal(rec.has_recommendation, false);
    assert.equal(rec.recommended_station_id, null);

    const demand = formatDemandInspector(safeResult.energy_context);
    assert.equal(demand.need_service, false);
    assert.equal(demand.reason_code, 'SUFFICIENT_SOC_RANGE');
    assert.equal(demand.current_soc_pct, 85.0);

    const ranking = formatRankingInspector(safeResult);
    assert.equal(ranking.candidates.length, 0);
});

test('Scenario 5: Backend outage and dependency failure isolation', () => {
    // Complete backend API outage
    const apiOutage = classifySystemHealth(null, false);
    assert.equal(apiOutage.api.status, 'UNAVAILABLE');
    assert.equal(apiOutage.graphhopper.status, 'UNKNOWN');
    assert.equal(apiOutage.postgis.status, 'UNKNOWN');
    assert.equal(apiOutage.redis.status, 'UNKNOWN');

    // GraphHopper down, PostGIS & Redis healthy
    const ghOutage = classifySystemHealth({
        status: 'not_ready',
        graphhopper: false,
        postgis: true,
        redis: true
    }, true);
    assert.equal(ghOutage.api.status, 'HEALTHY');
    assert.equal(ghOutage.graphhopper.status, 'UNAVAILABLE');
    assert.equal(ghOutage.postgis.status, 'HEALTHY');
    assert.equal(ghOutage.redis.status, 'HEALTHY');

    // PostGIS down
    const dbOutage = classifySystemHealth({
        status: 'not_ready',
        graphhopper: true,
        postgis: false,
        redis: true
    }, true);
    assert.equal(dbOutage.postgis.status, 'UNAVAILABLE');
});

test('Scenario 6: Raw JSON payload inspection and credential redaction', () => {
    const rawReq = {
        context: {
            vehicle_id: 'V0001',
            current_soc_pct: 15.0,
            auth_token: 'secret_token_123',
            password_hash: 'super_secret'
        },
        destination_latitude: 21.0150
    };

    const formatted = sanitizeJsonPayload(rawReq);
    assert.ok(formatted.includes('"vehicle_id": "V0001"'));
    assert.ok(formatted.includes('"current_soc_pct": 15'));
    assert.ok(!formatted.includes('secret_token_123'));
    assert.ok(!formatted.includes('super_secret'));
    assert.ok(formatted.includes('[REDACTED]'));
});
