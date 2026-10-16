# SDD ledger — plan: docs/superpowers/plans/2026-10-09-driver-only-implementation.md

## Task Map
- Task 0: Baseline Snapshot ✅ (ad42954)
- Task 1: Regression Test Contract ✅ (391722f) — Approved. 5/5 tests.
- Task 2: Stabilize Replay.js ✅ (pre-existing — no separate commit needed)
- Task 3: Navigation Revision Guards ✅ (4e76c13) — Approved.
  - Bug fix: Test 8 called setState(TRIP_COMPLETE) alone; fixed to also call renderTripCompleteUI()
- Task 4: Merge Recommendation Data Flow ✅ (2b6e9f3) — Approved after fix loop.
  - Fix 1: startRecommendRefresh integrated in startTrip(); stop in returnToAvailable()
  - Fix 2: removed updateStationMarkers dead code, replaced with no-op
  - 15/15 tests passing
- Task 5: Station Card and Tooltip UX ✅ (21ad778) — Approved.
  - Post-review fixes: ||→&& in offline button assertion; eligible check in drawer_renderer
  - 8/8 tests passing
- Task 6: H3 Display-Only Layer ✅ (21ad778) — Approved. Minor scope creep (not a blocker)
  - 9/9 tests passing
- Task 7: Transfer Synthetic GPS Init to Driver ✅ (57313dc)
  - 8/8 tests passing
- Task 8: Clean app.js Bootstrap ✅ (0eff268)
  - 6/6 tests passing
- Task 9: Delete Removed Files ✅ (4e0879a)
  - 4 files deleted; graceful degradation confirmed
- Task 10: Full Regression Suite ✅ (68dc36a)
  - Test 10: long route monotonic timestamps ✅
  - Test 13: COMPLETE fires exactly once ✅
  - Probe 1-7 already covered in test_driver_playback_probe.mjs
- Task 11: E2E Acceptance — MANUAL (requires Docker backend + browser)

## Commits (13 total)
- ad42954: docs: capture pre-implementation baseline snapshot
- 391722f: test: add replay loop ownership regression tests (5/5 passing)
- 4e76c13: test+fix: add navigation revision guards (10/10 passing)
- 5f5c692: test: add Top 5 result sharing and auto-refresh regression tests
- 63f7ed7: feat(driver): add _top5Result sharing, auto-refresh, explicit service request
- 21ad778: feat(ui): add H3 display-only overlay from route geometry
- 2b6e9f3: fix(driver): call startRecommendRefresh in startTrip and stop in returnToAvailable
- 57313dc: feat(driver): integrate synthetic GPS from GraphHopper geometry into replay
- 0eff268: refactor(app): remove SimModeController and graceful scenario degradation
- 4e0879a: chore: delete sim_mode.js, tech_view.js, scenarios.json, trips.json
- 68dc36a: test: add complete journey regression tests

## Known Issues
- test_mode_isolation.mjs: pre-existing test, hangs on driver_controller import — unrelated to this plan
- test_cockpit_bindings.mjs: pre-existing test, line ceiling warning — unrelated to this plan
