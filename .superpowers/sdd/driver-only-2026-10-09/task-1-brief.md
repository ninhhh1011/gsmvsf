## Task 1: Regression Test Contract — Replay Stability

**Files:**
- Create: `tests/frontend/test_replay_loop_ownership.mjs`
- Read: `backend/app/static/demo/js/replay.js`

**Interfaces:**
- Consumes: `TrajectoryReplayController`, `ReplayState` from `replay.js`
- Produces: Tests that assert loop ownership, retry limits, and stale guards

**Tests to write (each in its own `it()` block):**

- [ ] **Step 1: Test — exactly one loop after Pause→Play**

```javascript
it('pause then play leaves exactly one active loop', async () => {
    // Setup: controller with mock API, 10 observations
    // Action: play() → pause() → play()
    // Assert: only one playback token is active (verify _runPlaybackLoop guard)
    // Fail if: two loops both calling step() simultaneously
});
```

- [ ] **Step 2: Test — STALE_OBSERVATION does not increment index**

```javascript
it('STALE_OBSERVATION response does not advance currentIndex', async () => {
    // Setup: mock ingestDriverLocation returns { status: 'STALE_OBSERVATION' }
    // Action: step()
    // Assert: currentIndex === 0, isStepInProgress === false
    // Fail if: index advances on stale response
});
```

- [ ] **Step 3: Test — retry exhausts after exactly 3 attempts**

```javascript
it('transient error retries at most 3 times', async () => {
    // Setup: mock API throws 429 three times, succeeds on 4th
    // Action: play() with speed >= 10
    // Assert: step() was called 4 times (1 original + 3 retries), then state === ERROR
    // Fail if: more than 4 calls, or succeeds after 3 retries
});
```

- [ ] **Step 4: Test — reset() cancels in-flight step**

```javascript
it('reset() cancels in-flight request and sets isStepInProgress=false', async () => {
    // Setup: mock API has 200ms delay
    // Action: step(true) → immediately reset()
    // Assert: generation incremented, isStepInProgress === false, no downstream called
});
```

- [ ] **Step 5: Test — 10x speed has minimum delay guard**

```javascript
it('speed 10x respects minimum delay of 50ms', async () => {
    // Setup: speedMultiplier = 10, 60 observations
    // Action: measure wall time for 10 steps
    // Assert: total time >= 10 * 50ms = 500ms
    // Fail if: 10x completes 10 steps in < 500ms (bypassing production rate)
});
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_replay_loop_ownership.mjs
```

Expected: All FAIL (stubs, no implementation yet) — this is the TDD red phase.

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_replay_loop_ownership.mjs
git commit -m "test: add replay loop ownership regression tests"
```

---

