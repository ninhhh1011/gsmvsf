/**
 * Unit tests for Phase 4 Technical / Debug View Logic (Node.js native test runner).
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
    sanitizeJsonPayload
} from '../../backend/app/static/demo/js/tech_view.js';

test('classifySystemHealth handles healthy, degraded, unavailable, and unknown', () => {
    // 1. All healthy
    const healthy = classifySystemHealth({
        status: 'ready',
        graphhopper: true,
        postgis: true,
        redis: true
    }, true);
    assert.equal(healthy.api.status, 'HEALTHY');
    assert.equal(healthy.graphhopper.status, 'HEALTHY');
    assert.equal(healthy.postgis.status, 'HEALTHY');
    assert.equal(healthy.redis.status, 'HEALTHY');

    // 2. GraphHopper down
    const ghDown = classifySystemHealth({
        status: 'not_ready',
        graphhopper: false,
        postgis: true,
        redis: true
    }, true);
    assert.equal(ghDown.api.status, 'HEALTHY');
    assert.equal(ghDown.graphhopper.status, 'UNAVAILABLE');
    assert.equal(ghDown.postgis.status, 'HEALTHY');
    assert.equal(ghDown.redis.status, 'HEALTHY');

    // 3. API completely unreachable (network error or timeout)
    const apiDown = classifySystemHealth(null, false);
    assert.equal(apiDown.api.status, 'UNAVAILABLE');
    assert.equal(apiDown.graphhopper.status, 'UNKNOWN');
    assert.equal(apiDown.postgis.status, 'UNKNOWN');
    assert.equal(apiDown.redis.status, 'UNKNOWN');

    // 4. Redis down (degraded for snapshot cache fallback, unavailable for driver state)
    const redisDown = classifySystemHealth({
        status: 'not_ready',
        graphhopper: true,
        postgis: true,
        redis: false
    }, true);
    assert.equal(redisDown.redis.status, 'UNAVAILABLE');
});

test('formatLocationInspector truthfully displays raw GPS vs matched road point and ambiguous states', () => {
    // Normal matched observation
    const matched = formatLocationInspector({
        driver_id: 'D0001',
        status: 'MATCHED',
        trigger_reason: 'TIME_INTERVAL',
        raw_position: { latitude: 21.0285, longitude: 105.8542, speed_kmh: 30.5, heading_deg: 90 },
        matched_position: {
            latitude: 21.0286,
            longitude: 105.8543,
            road_segment_id: 'seg_123',
            osm_way_id: 998877,
            direction: 'FORWARD',
            confidence: 0.95
        }
    }, 'MATCHED');

    assert.equal(matched.driver_id, 'D0001');
    assert.equal(matched.matching_status, 'MATCHED');
    assert.equal(matched.road_segment_id, 'seg_123');
    assert.equal(matched.osm_way_id, 998877);
    assert.equal(matched.direction, 'FORWARD');
    assert.equal(matched.location_source, 'MATCHED');
    assert.ok(matched.raw_position != null);
    assert.ok(matched.matched_position != null);

    // Ambiguous / Unresolved match
    const ambiguous = formatLocationInspector({
        driver_id: 'D0002',
        status: 'AMBIGUOUS',
        trigger_reason: 'DISTANCE_DELTA',
        raw_position: { latitude: 21.0100, longitude: 105.8000 },
        matched_position: {
            latitude: 21.0101,
            longitude: 105.8001,
            road_segment_id: null,
            osm_way_id: null,
            direction: null,
            confidence: 0.40
        }
    }, 'RAW_GPS_FALLBACK');

    assert.equal(ambiguous.matching_status, 'AMBIGUOUS');
    assert.equal(ambiguous.road_segment_id, null);
    assert.equal(ambiguous.osm_way_id, null);
    assert.equal(ambiguous.direction, 'UNKNOWN');
    assert.equal(ambiguous.location_source, 'RAW_GPS_FALLBACK');

    // No Match
    const noMatch = formatLocationInspector({
        driver_id: 'D0003',
        status: 'NO_MATCH',
        raw_position: { latitude: 21.0000, longitude: 105.7000 },
        matched_position: null
    }, 'RAW_GPS_FALLBACK');
    assert.equal(noMatch.matching_status, 'NO_MATCH');
    assert.equal(noMatch.matched_position, null);
});

test('formatDemandInspector extracts backend demand parameters without recalculation', () => {
    const demand = formatDemandInspector({
        need_service: true,
        reason_code: 'DESTINATION_NOT_REACHABLE',
        current_soc_pct: 12.0,
        estimated_remaining_range_km: 20.0,
        remaining_trip_distance_km: 35.0,
        safety_reserve_km: 5.0,
        energy_margin_km: -20.0,
        allowed_service_types: ['CHARGING', 'BATTERY_SWAP'],
        resolved_service_type: 'CHARGING',
        request_valid: true
    });

    assert.equal(demand.need_service, true);
    assert.equal(demand.reason_code, 'DESTINATION_NOT_REACHABLE');
    assert.equal(demand.current_soc_pct, 12.0);
    assert.equal(demand.energy_margin_km, -20.0);
    assert.equal(demand.resolved_service_type, 'CHARGING');
    assert.deepEqual(demand.allowed_service_types, ['CHARGING', 'BATTERY_SWAP']);
});

test('filterCandidates preserves (station_id, service_type) composite identity and supports filters', () => {
    const candidates = [
        { station_id: 'S001', service_type: 'CHARGING', eligible: true, reason: 'ELIGIBLE' },
        { station_id: 'S001', service_type: 'BATTERY_SWAP', eligible: false, reason: 'NO_SWAP_BATTERY' },
        { station_id: 'S002', service_type: 'CHARGING', eligible: false, reason: 'OFFLINE' },
        { station_id: 'S003', service_type: 'BATTERY_SWAP', eligible: true, reason: 'ELIGIBLE' }
    ];

    // Filter ALL: All 4 candidates preserved, S001 appears twice
    const all = filterCandidates(candidates, 'ALL');
    assert.equal(all.length, 4);
    assert.equal(all[0].key, 'S001_CHARGING');
    assert.equal(all[1].key, 'S001_BATTERY_SWAP');

    // Filter ELIGIBLE: S001 CHARGING and S003 BATTERY_SWAP
    const eligible = filterCandidates(candidates, 'ELIGIBLE');
    assert.equal(eligible.length, 2);
    assert.equal(eligible[0].station_id, 'S001');
    assert.equal(eligible[0].service_type, 'CHARGING');
    assert.equal(eligible[1].station_id, 'S003');

    // Filter REJECTED: S001 BATTERY_SWAP and S002 CHARGING
    const rejected = filterCandidates(candidates, 'REJECTED');
    assert.equal(rejected.length, 2);
    assert.equal(rejected[0].reason, 'NO_SWAP_BATTERY');
    assert.equal(rejected[1].reason, 'OFFLINE');
});

test('formatRoutingInspector accurately exposes route legs, detour, and GraphHopper metadata', () => {
    const routing = formatRoutingInspector({
        directRoute: { distance_m: 10000, duration_s: 800, status: 'SUCCESS', engine: 'graphhopper', profile: 'car' },
        stationRouteLeg1: { distance_m: 4000, duration_s: 350, status: 'SUCCESS' },
        stationRouteLeg2: { distance_m: 7000, duration_s: 550, status: 'SUCCESS' },
        vehicleCategory: 'EV_CAR'
    });

    assert.equal(routing.direct_distance_km, '10.00');
    assert.equal(routing.direct_duration_min, '13.3');
    assert.equal(routing.via_total_distance_km, '11.00');
    assert.equal(routing.via_total_duration_min, '15.0');
    assert.equal(routing.detour_distance_km, '1.00');
    assert.equal(routing.detour_duration_min, '1.7');
    assert.equal(routing.engine, 'GraphHopper 11.0');
    assert.equal(routing.profile, 'car');
    assert.equal(routing.status, 'SUCCESS');
});

test('formatRankingInspector exposes true policy semantics without fake AI confidence', () => {
    const ranking = formatRankingInspector({
        policy: { name: 'TOTAL_SERVICE_COMPLETION_V1' },
        ranked_candidates: [
            {
                rank: 1,
                station_id: 'S017',
                service_type: 'CHARGING',
                eta_to_station_s: 480.0,
                eta_to_service_start_s: 480.0,
                eta_to_service_complete_s: 1440.0,
                final_cost_s: 1440.0,
                features: {
                    base_travel_duration_s: 480.0,
                    adjusted_travel_duration_s: 480.0,
                    observed_queue_wait_s: 0.0,
                    effective_queue_wait_s: 0.0,
                    service_duration_s: 960.0,
                    detour_duration_s: 120.0,
                    detour_distance_m: 800.0,
                    available_capacity: 4,
                    station_state: { is_fresh: true, age_s: 45.0 },
                    queue_state: { is_fresh: true, age_s: 45.0 }
                }
            }
        ]
    });

    assert.equal(ranking.policy_name, 'TOTAL_SERVICE_COMPLETION_V1');
    assert.equal(ranking.candidates.length, 1);
    assert.equal(ranking.candidates[0].rank, 1);
    assert.equal(ranking.candidates[0].station_id, 'S017');
    assert.equal(ranking.candidates[0].service_type, 'CHARGING');
    assert.equal(ranking.candidates[0].eta_to_station_min, '8.0');
    assert.equal(ranking.candidates[0].queue_wait_min, '0.0');
    assert.equal(ranking.candidates[0].service_duration_min, '16.0');
    assert.equal(ranking.candidates[0].final_cost_min, '24.0');
    assert.equal(ranking.candidates[0].station_fresh, true);
    // Explicitly verify no synthetic "confidence_pct" exists
    assert.equal(ranking.candidates[0].confidence_pct, undefined);
});

test('formatRecommendationInspector exposes final outcome and workflow metadata', () => {
    const rec = formatRecommendationInspector({
        has_recommendation: true,
        recommended_station_id: 'S017',
        recommended_service_type: 'CHARGING',
        eligible_count: 18,
        location_source: 'MATCHED',
        degraded: false,
        degraded_reasons: [],
        reason: 'SUCCESS',
        workflow_attempts: 1,
        candidate_search_calls: 1,
        ranking_calls: 1,
        candidate_state_conflicts: 0
    });

    assert.equal(rec.has_recommendation, true);
    assert.equal(rec.recommended_station_id, 'S017');
    assert.equal(rec.recommended_service_type, 'CHARGING');
    assert.equal(rec.eligible_count, 18);
    assert.equal(rec.location_source, 'MATCHED');
    assert.equal(rec.degraded, false);
    assert.equal(rec.workflow_attempts, 1);
});

test('formatPipelineTiming and sanitizeJsonPayload format cleanly', () => {
    // With real timings
    const timing = formatPipelineTiming({
        location_resolution: 1.25,
        demand: 0.85,
        candidate_search: 12.4,
        ranking: 3.1,
        total: 17.6
    });
    assert.equal(timing.location_ms, '1.25 ms');
    assert.equal(timing.demand_ms, '0.85 ms');
    assert.equal(timing.candidate_search_ms, '12.40 ms');
    assert.equal(timing.ranking_ms, '3.10 ms');
    assert.equal(timing.total_ms, '17.60 ms');

    // Missing timing returns N/A (truthful, no fabrication)
    const missingTiming = formatPipelineTiming(null);
    assert.equal(missingTiming.location_ms, 'N/A');
    assert.equal(missingTiming.total_ms, 'N/A');

    // JSON payload serialization
    const sanitized = sanitizeJsonPayload({ key: 'val', password: 'secret', nested: { number: 42 } });
    assert.ok(sanitized.includes('"number": 42'));
    assert.ok(!sanitized.includes('secret'));
});
