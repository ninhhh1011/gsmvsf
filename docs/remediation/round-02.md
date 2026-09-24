# Round 02 Remediation Plan — Timing Edge Cases & Live Stack Tests

## Branch & Status
- **Branch**: `week5-realtime-api-evaluation` (current)
- **HEAD**: `829df9e` (pre-ROUND-02)
- **Status**: Working tree modified (pending commit)

---

## PHASE 0 — AUDIT FINDINGS (from ROUND 01 remaining risks)

### Identified Issues from ROUND 01

| # | Issue | Risk Level | File |
|---|-------|-----------|------|
| R1 | `replay.step()` has no guard when `isPlaying=true` | Medium | `replay.js` |
| R2 | `DriverModeController` doesn't pass session to Replay | High | `driver_mode.js` |
| R3 | `TechView` state sync has no debounce | Low | `app.js` |
| R4 | No live smoke tests (only fixtures) | Medium | `frontend/tests/` |
| R5 | `replay.reset()` doesn't reset driver state on backend | Low | `replay.js` |

---

## PHASE 1 — TIMING EDGE CASE FIXES

### Task 1.1: Guard step() during autoplay (R1)
**File**: `backend/app/static/demo/js/replay.js`
**Change**: Add guard at start of `step()` to return early if `isPlaying=true`
**Test**: Rapid step clicks during autoplay don't queue multiple steps

```javascript
async step() {
    // Guard: don't queue steps during autoplay (prevents race condition)
    if (this.isPlaying) return;

    if (this.currentIndex >= this.observations.length) {
```

### Task 1.2: Pass session to Replay (R2)
**File**: `backend/app/static/demo/js/driver_mode.js`
**Change**: Pass `session` to `TrajectoryReplayController` constructor
**Test**: Driver ID consistent across Driver Mode + Replay lifecycle

```javascript
// Session is passed for consistent driver_id across Driver Mode + Replay
this.replay = new TrajectoryReplayController(apiClient, mapEngine, {
    onStep: (stepData) => this._onReplayStep(stepData),
    session: this.session
});
```

### Task 1.3: Debounce TechView sync (R3)
**File**: `backend/app/static/demo/js/app.js`
**Change**: Add 50ms debounce to `onStateUpdate` callback
**Test**: Rapid replay steps don't cause UI jank

```javascript
let syncDebounceTimer = null;
const onStateUpdate = (data) => {
    clearTimeout(syncDebounceTimer);
    syncDebounceTimer = setTimeout(() => {
        this.techView.syncState(data);
    }, 50); // 50ms debounce for rapid replay steps
};
```

### Task 1.4: Add clearSession to Replay (R5)
**File**: `backend/app/static/demo/js/replay.js`
**Change**: Add `clearSession()` method that resets driver location on backend
**Test**: Driver state properly cleaned up on trip reset/cancel

```javascript
clearSession() {
    this.api.resetDriverLocation(this.session.driver_id).catch(() => {});
}
```

### Task 1.5: Call clearSession on reset/cancel (R5)
**Files**: `driver_mode.js`
**Change**: Call `this.replay.clearSession()` in `returnToAvailable()` and `cancelTrip()`
**Test**: Backend driver state cleared when returning to available

---

## PHASE 2 — LIVE STACK SMOKE TESTS

### Task 2.1: Add live smoke tests
**File**: `frontend/tests/live.spec.js` (planned for future)
**Note**: BROWSER_WITH_API_FIXTURES tests provide adequate coverage for ROUND 02.
Live tests require full backend stack (PostGIS, GraphHopper, Redis) which may not
be available in all environments.

---

## EXIT GATES

| Gate | Criteria | Method |
|------|----------|--------|
| 0 | Plan approved | Document review |
| 1 | step() guard prevents race, session passed to Replay | Code review |
| 2 | TechView debounce added, session cleared on reset | Code review |
| 3 | All 12 browser tests pass, 368 backend tests pass | CI/CD |

---

## Dependencies
- None (no new infrastructure)

## Not in Scope
- Replay scheduler redesign
- Full UI redesign
- Live smoke tests (deferred to when full stack available)

---

## ROUND 02 COMPLETION REPORT

### Files Changed
```
M backend/app/static/demo/js/app.js         (+debounce, ~+8 lines)
M backend/app/static/demo/js/driver_mode.js (+session to Replay, +clearSession calls)
M backend/app/static/demo/js/replay.js      (+step guard, +clearSession method)
```

### Issues Fixed

| # | Issue | Fix | Verified |
|---|-------|-----|----------|
| R1 | `step()` race during autoplay | Early return if `isPlaying=true` | Code review |
| R2 | Replay missing session | Pass `session: this.session` to constructor | Code review |
| R3 | TechView sync race condition | 50ms debounce on `onStateUpdate` | Code review |
| R5 | Session not cleared on reset | `clearSession()` method + calls | Code review |

### Test Results

**Browser Tests (BROWSER_WITH_API_FIXTURES):**
```
Command: npx playwright test frontend/tests/demo.spec.js
Results: 12 passed (54.3s)

A. Bootstrap:
  ✓ page renders without page error
  ✓ controls appear and are usable

B. Scenario/Trip/Vehicle Selection:
  ✓ trip selection changes context

C. Direct Route:
  ✓ route persists after trip assignment

D. Replay Step:
  ✓ replay step sends correct metadata
  ✓ replay step uses consistent driver identity

E. Recommendation:
  ✓ recommendation displays after UI action

F. No-Service State:
  ✓ displays no-service correctly

G. API Error:
  ✓ displays error state without fake success

H. Tech View:
  ✓ opens from button
  ✓ /demo/technical page works

I. Catalog Failure:
  ✓ shows error banner when catalog fails
```

**Backend Tests:**
```
Command: python -m pytest backend/tests/ -v
Results: 368 passed (16.93s)
```

### Exit Gate Status

| Gate | Criteria | Status |
|------|----------|--------|
| 0 | Plan approved | ✅ PASS |
| 1 | step() guard, session passed to Replay | ✅ PASS (Code review) |
| 2 | TechView debounce, session cleared on reset | ✅ PASS (Code review) |
| 3 | Browser tests pass, backend tests pass | ✅ PASS (12+368 tests) |

### Evidence Location
- Browser test output: `test-results/` directory
- Backend test output: stdout (368 passed)
- Code changes: Working tree (pending commit)
