/**
 * Unit tests for Phase 1 & Phase 2: Replay Sequential Async State Machine,
 * Generation Invalidation, and Honest Data Provenance.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

import { ReplayState, TrajectoryReplayController } from '../../backend/app/static/demo/js/replay.js';
import { DriverState, straightLineDistanceKm } from '../../backend/app/static/demo/js/driver_mode.js';

test('ReplayState enum constants are defined correctly', () => {
    assert.equal(ReplayState.IDLE, 'IDLE');
    assert.equal(ReplayState.LOADING, 'LOADING');
    assert.equal(ReplayState.READY, 'READY');
    assert.equal(ReplayState.PLAYING, 'PLAYING');
    assert.equal(ReplayState.PAUSED, 'PAUSED');
    assert.equal(ReplayState.ERROR, 'ERROR');
    assert.equal(ReplayState.COMPLETE, 'COMPLETE');
});

test('TrajectoryReplayController enforces max 1 step in flight and confirmed progress', async () => {
    let ingestCallCount = 0;
    let resolveIngest = null;

    const mockApi = {
        ingestDriverLocation: async () => {
            ingestCallCount++;
            return new Promise((resolve) => {
                resolveIngest = resolve;
            });
        },
        resetDriverLocation: async () => ({})
    };

    const mockMap = {
        renderDriver: () => {},
        layers: { markers: { clearLayers: () => {} }, driver: { clearLayers: () => {} } }
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap);
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 },
        { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:00:30Z', speed_kmh: 35, heading_deg: 95 }
    ];
    replay.state = ReplayState.READY;

    // Trigger first step (pending network)
    const step1Promise = replay.step();
    assert.equal(ingestCallCount, 1);
    assert.equal(replay.isStepInProgress, true);
    // Index should NOT have incremented yet before confirmed backend response!
    assert.equal(replay.currentIndex, 0);

    // Concurrent second step should be rejected immediately (max 1 concurrency)
    const step2Result = await replay.step();
    assert.equal(step2Result, false);
    assert.equal(ingestCallCount, 1); // No new network call was made

    // Resolve step 1
    resolveIngest({
        status: 'MATCHED',
        trigger_reason: 'MANUAL_STEP',
        total_match_calls: 1,
        raw_position: { latitude: 21.01, longitude: 105.81 },
        matched_position: {
            latitude: 21.0101,
            longitude: 105.8101,
            road_segment_id: 'seg_1',
            direction: 'FORWARD',
            confidence: 0.92
        }
    });

    const step1Result = await step1Promise;
    assert.equal(step1Result, true);
    assert.equal(replay.isStepInProgress, false);
    // Confirmed progress after success
    assert.equal(replay.currentIndex, 1);
});

test('Reset invalidates generation and drops stale in-flight responses', async () => {
    let resolveIngest = null;

    const mockApi = {
        ingestDriverLocation: async () => {
            return new Promise((resolve) => {
                resolveIngest = resolve;
            });
        },
        resetDriverLocation: async () => ({})
    };

    const mockMap = {
        renderDriver: () => {},
        layers: { markers: { clearLayers: () => {} }, driver: { clearLayers: () => {} } }
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap);
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 }
    ];
    replay.state = ReplayState.READY;

    const initialGen = replay.generation;

    // Launch step
    const stepPromise = replay.step();
    assert.equal(replay.isStepInProgress, true);

    // User clicks reset while request is in flight
    replay.reset();
    assert.ok(replay.generation > initialGen, 'Generation must increment on reset');
    assert.equal(replay.currentIndex, 0);
    assert.equal(replay.isStepInProgress, false);

    // Old in-flight network call finally resolves
    resolveIngest({
        status: 'MATCHED',
        total_match_calls: 1,
        raw_position: { latitude: 21.01, longitude: 105.81 },
        matched_position: { latitude: 21.0101, longitude: 105.8101 }
    });

    const stepResult = await stepPromise;
    // Step must return false because generation was stale
    assert.equal(stepResult, false);
    // Index must stay at 0; no stale state resurrected
    assert.equal(replay.currentIndex, 0);
});

test('Pause stops playback loop without losing progress', async () => {
    let stepCount = 0;
    const mockApi = {
        ingestDriverLocation: async () => {
            stepCount++;
            return {
                status: 'MATCHED',
                total_match_calls: stepCount,
                raw_position: { latitude: 21.0, longitude: 105.0 },
                matched_position: { latitude: 21.0, longitude: 105.0 }
            };
        },
        resetDriverLocation: async () => ({})
    };

    const mockMap = {
        renderDriver: () => {},
        layers: { markers: { clearLayers: () => {} }, driver: { clearLayers: () => {} } }
    };

    const replay = new TrajectoryReplayController(mockApi, mockMap);
    replay.observations = [
        { latitude: 21.01, longitude: 105.81, timestamp: '2026-09-01T07:00:00Z', speed_kmh: 30, heading_deg: 90 },
        { latitude: 21.02, longitude: 105.82, timestamp: '2026-09-01T07:00:30Z', speed_kmh: 35, heading_deg: 95 },
        { latitude: 21.03, longitude: 105.83, timestamp: '2026-09-01T07:01:00Z', speed_kmh: 40, heading_deg: 100 }
    ];
    replay.speedMultiplier = 100; // fast for testing

    replay.play();
    assert.equal(replay.state, ReplayState.PLAYING);

    // Wait for first step to complete
    await new Promise(r => setTimeout(r, 50));

    // Pause playback
    replay.pause();
    assert.equal(replay.state, ReplayState.PAUSED);
    const indexAtPause = replay.currentIndex;
    assert.ok(indexAtPause >= 1, 'Should have completed at least one step');

    // Wait some time to ensure no new steps are taken
    await new Promise(r => setTimeout(r, 100));
    assert.equal(replay.currentIndex, indexAtPause, 'Progress must remain frozen after pause');
});

test('straightLineDistanceKm computes accurate Haversine and is isolated from road distance', () => {
    // Distance between Hanoi Old Quarter (21.0333, 105.8500) and West Lake (21.0500, 105.8200)
    const dist = straightLineDistanceKm(21.0333, 105.8500, 21.0500, 105.8200);
    // Approximate straight-line distance is ~3.6 km
    assert.ok(dist > 3.0 && dist < 4.5, `Expected ~3.6 km, got ${dist}`);

    // Same point returns 0
    assert.equal(straightLineDistanceKm(21.0, 105.0, 21.0, 105.0), 0);
});
