## Task 2: Stabilize Replay.js

**Files:**
- Modify: `backend/app/static/demo/js/replay.js`
- Test: `tests/frontend/test_replay_loop_ownership.mjs`

**Interfaces:**
- Consumes: `api.ingestDriverLocation`, `api.resetDriverLocation`
- Produces: Stable `TrajectoryReplayController` passing all Task 1 tests

**Fixes needed (read `driver-playback-investigation-2026-10-08.md` for line references):**

- [ ] **Step 1: Fix pause() — don't create a new loop token on pause**

Current: `pause()` increments `playbackToken` → new loop could start on `play()`
Fix: Remove `this.playbackToken++` from `pause()`. `play()` should only increment token when transitioning from non-PLAYING state.

```javascript
pause() {
    // Cancel sleep only — do NOT increment token
    if (this._cancelSleep) { this._cancelSleep(); }
    if (this.stepTimer) { clearTimeout(this.stepTimer); this.stepTimer = null; }
    if (this.state === ReplayState.PLAYING) { this.setState(ReplayState.PAUSED); }
}
```

- [ ] **Step 2: Fix reset() — don't set isStepInProgress=false while request is pending**

Current: `reset()` sets `isStepInProgress=false` immediately
Fix: Await any in-flight step or set a "resetting" flag that `step()` checks and exits early.

```javascript
reset() {
    // Increment generation first — this invalidates all pending operations
    this.generation++;
    this.playbackToken++;
    if (this._cancelSleep) { this._cancelSleep(); }
    if (this.stepTimer) { clearTimeout(this.stepTimer); this.stepTimer = null; }
    // isStepInProgress: let in-flight step() finish and self-clean via generation check
    this.currentIndex = 0;
    this.lastAcceptedTimestampMs = 0;
    // ... clear map markers ...
    this.setState(ReplayState.READY);
}
```

- [ ] **Step 3: Fix 10x delay — use production minimum, not test bypass**

Current: `speedMultiplier >= 10` uses `Math.max(30, 500/10) = 50ms`
Fix: Remove the `>= 10` branch. All speeds use the same minimum pacing:

```javascript
const delay = this.speedMultiplier >= 5
    ? Math.max(1500, 800)    // 5x-9x: 800ms
    : this.speedMultiplier >= 2
    ? 1000                    // 2x-4x: 1000ms
    : 1500;                  // 1x: 1500ms
```

- [ ] **Step 4: Fix STALE_OBSERVATION guard — don't advance index**

Current: `step()` increments `currentIndex` regardless of `locResp.status`
Fix: Move `currentIndex++` inside the non-error path, after the stale check:

```javascript
// After stale check throws, add:
if (locResp.status !== 'STALE_OBSERVATION') {
    this.currentIndex = targetIndex + 1;
    this.updateProgressUI();
    if (this.currentIndex >= this.observations.length) {
        this.setState(ReplayState.COMPLETE);
    }
}
```

- [ ] **Step 5: Run tests**

```bash
node --test tests/frontend/test_replay_loop_ownership.mjs
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/static/demo/js/replay.js
git commit -m "fix(replay): stabilize loop ownership, retry limits, STALE guard

- pause() no longer increments playbackToken (one loop invariant)
- reset() invalidates via generation increment (in-flight step self-cleans)
- removed >=10 speed bypass (production minimum 800ms for 5x)
- STALE_OBSERVATION does not advance currentIndex

Refs: driver-playback-investigation-2026-10-08.md"
```

---

