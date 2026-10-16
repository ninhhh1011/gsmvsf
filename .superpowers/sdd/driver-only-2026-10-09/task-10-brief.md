## Task 10: Full Regression Suite

**Files:**
- Update: `tests/frontend/test_driver_playback_probe.mjs`
- Create: `tests/frontend/test_complete_journey.mjs`

**Tests from handoff section 10 not yet covered:**

- [ ] **Test 5: Rapid B changes, responses out of order**

Add to `test_navigation_revision.mjs` — already covered in Task 3.

- [ ] **Test 8: Pause/Play/reset during ingest**

Add to `test_replay_loop_ownership.mjs` — already covered in Task 1.

- [ ] **Test 10: Long synthetic route, many reroutes**

```javascript
it('replaying a long route maintains monotonic timestamps', async () => {
    // Setup: route with 500+ synthetic observations
    // Action: play() full route
    // Assert: every observation timestamp > previous timestamp
});
```

- [ ] **Test 13: Drive to B fires COMPLETE exactly once**

```javascript
it('COMPLETE state fires exactly once when reaching destination', async () => {
    // Setup: 10 synthetic observations
    // Action: play() all steps
    // Assert: onStateChange called with COMPLETE exactly once
});
```

- [ ] **Test 14: Scenario removal**

Add to `test_scenario_removal.mjs` — already covered in Task 8.

- [ ] **Run full suite**

```bash
node --test \
  tests/frontend/test_replay_state_machine.mjs \
  tests/frontend/test_mode_isolation.mjs \
  tests/frontend/test_replay_loop_ownership.mjs \
  tests/frontend/test_navigation_revision.mjs \
  tests/frontend/test_top5_result_sharing.mjs \
  tests/frontend/test_station_tooltip.mjs \
  tests/frontend/test_h3_display.mjs \
  tests/frontend/test_scenario_removal.mjs
```

- [ ] **Commit**

```bash
git add tests/frontend/
git commit -m "test: complete regression suite for single Driver Mode"
```

---

