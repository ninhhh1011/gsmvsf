# SDD ledger — plan: docs/superpowers/plans/2026-10-09-driver-only-implementation.md

## Task Map
- Task 0: Baseline Snapshot ✅ (ad42954)
- Task 1: Regression Test Contract — Replay Stability ✅ (391722f)
  - Review: clean — all 5 tests verified, spec ✅, quality ✅
- Task 2: Stabilize Replay.js — PENDING
- Task 3: Navigation Revision Guards ✅ (4e76c13) — review clean
  - Review: Approved. Minor: routeRevision vs brief naming divergence; setSimulationSpeed scope creep (not a blocker).
  - Fix: Test 8 called setState(TRIP_COMPLETE) alone; fixed to also call renderTripCompleteUI()
- Task 4: Merge Recommendation Data Flow ✅ (2b6e9f3) — Approved after fix loop
  - Review fix 1: startRecommendRefresh integrated in startTrip(); stop in returnToAvailable()
  - Review fix 2: removed updateStationMarkers dead code, replaced with no-op
  - 15/15 tests passing
- Task 5: Station Card and Tooltip UX ✅ (21ad778) — Approved (minor assertion + impl fix post-review)
  - 8/8 tests passing
  - Post-review fixes: changed || to && in offline button assertion; added eligible check in drawer_renderer
- Task 6: H3 Display-Only Layer ✅ (21ad778) — Approved (minor: scope creep from Task 5 fix in same commit)
  - 9/9 tests passing
- Task 4: Merge Recommendation Data Flow — PENDING
- Task 5: Station Card and Tooltip UX — PENDING
- Task 6: H3 Display-Only Layer — PENDING
- Task 7: Transfer Synthetic GPS Init to Driver — PENDING
- Task 8: Clean app.js Bootstrap — PENDING
- Task 9: Delete Removed Files — PENDING
- Task 10: Full Regression Suite — PENDING
- Task 11: E2E Acceptance — PENDING

## Pre-flight Scan
Tasks 2→7 are sequential (each builds on previous).
Tasks 1, 3, 4, 5, 6 can be batched in parallel (same-shape: create test + modify file, different modules).
Tasks 8+9 depend on earlier tasks being done.
Task 11 requires all others.

Interface conflicts scanned:
- Task 2 output: replay.js with fixes → Task 3+4+5+6+7 consume replay.js — clean
- Task 4 output: `_top5Result` shared state → Task 5+6 consume it — clean
- Task 5+6 output: DOM/overlay changes → Task 7+8 consume nothing new — clean
- Task 8 output: clean app.js → Task 9 deletes files → Task 10 tests → Task 11 E2E — clean

Scan: clean. No intra-plan conflicts found.

## Rulings

## Parks

## Commit History
- ad42954: docs: capture pre-implementation baseline snapshot
- 391722f: test: add replay loop ownership regression tests (5/5 passing)
- 4e76c13: test+fix: add navigation revision guards (10/10 passing)
- 5f5c692: test: add Top 5 result sharing and auto-refresh regression tests
- 63f7ed7: feat(driver): add _top5Result sharing, auto-refresh, explicit service request
- dd098a1: feat(ui): add station tooltip with full metrics, no API calls on hover
- 2b6e9f3: fix(driver): call startRecommendRefresh in startTrip and stop in returnToAvailable
- 21ad778: feat(ui): add H3 display-only overlay from route geometry (includes Task 5 fixes)
