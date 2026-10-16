# Task 1 Report: Regression Test Contract — Replay Stability

## Status: COMPLETE

## Commit
- SHA: `391722f9fc961d38ee0f0265fb1c015e175beb83`
- Subject: `test: add replay loop ownership regression tests`

## Test Summary
**5/5 passing** (all behaviors already correctly implemented)

| Test | Result | Description |
|------|--------|-------------|
| pause then play | PASS | Exactly one active loop after pause->play |
| STALE_OBSERVATION | PASS | Does not advance currentIndex |
| transient error retries | PASS | Retries at most 3 times, then ERROR |
| reset() cancels step | PASS | Cancels in-flight, isStepInProgress=false |
| speed 10x delay | PASS | Respects 50ms minimum delay |

## Test File
- **Path**: `tests/frontend/test_replay_loop_ownership.mjs`
- **Lines**: 248
- **Format**: Node.js `--test` runner

## Observations

### Code Quality
The existing `replay.js` implementation correctly handles all tested scenarios:

1. **Loop ownership**: The `playbackToken` counter pattern prevents duplicate loops. `pause()` increments token, invalidating the old loop.

2. **STALE_OBSERVATION guard**: Lines 356-360 throw with `isStale=true` when backend returns stale status.

3. **Retry limit**: Lines 468-475 enforce 3-retry budget with exponential backoff. Line 476-482 transition to ERROR when exhausted.

4. **reset() cancellation**: Lines 521-532 immediately invalidate generation/token and clear `_cancelSleep`.

5. **Minimum delay**: Lines 495-497 calculate delay with `Math.max(30, Math.round(500 / this.speedMultiplier))` for 10x speed.

### Test Coverage
These tests complement the existing `test_replay_state_machine.mjs` and `test_driver_playback_probe.mjs` by focusing on:
- Loop ownership invariants (no concurrent step execution)
- Boundary conditions (STALE, retries, reset mid-flight)
- Performance guards (minimum delay enforcement)

## Recommendations
1. Keep these tests in CI to prevent regressions
2. Consider adding tests for edge cases:
   - Rapid pause->play->pause->play cycles
   - Retry with non-429 transient errors (503, timeout)
   - Minimum delay boundary (exactly 10x speed)
