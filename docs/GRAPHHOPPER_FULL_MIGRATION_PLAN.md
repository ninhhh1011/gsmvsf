# GraphHopper Full Migration Implementation Plan

**Goal:** OSM is canonical data; GraphHopper is the sole production routing and map-matching runtime. Mock engines are test-only. No Week 4 work.

**Architecture:** Preserve RoutingEngine, RouteRequest, RouteResult and MapMatchingEngine. Use deterministic domain vehicle mapping in adapters; one shared matching service for batch/realtime. PostGIS resolves Dataset segment identities.

**Tech stack:** Existing Python/FastAPI/httpx/PostGIS; GraphHopper 11.0 official JAR on pinned Java 21 image. No additional application dependency.

**Execution:** Inline, automatically authorized by the user. Every phase contains one bounded task; within each task: test first where behavior changes, implement, task test, relevant regression, git diff, self-review, fix, re-test, task exit, phase exit. Never advance a failed phase. Infrastructure and disconnection tasks may leave dead files until Phase 15 but cannot leave active legacy selection. Phase 5 early readiness rewiring is completed with thorough health tests in Phase 11.

**Working-tree policy:** Inherited draft preserved in the working tree; edit in place on a migration branch. Stage explicit paths only. Preserve user memory files. Do not rewrite historical tags.

## Phase 0 ? Repository audit

### Task GH-00

- **TASK ID:** GH-00
- **OBJECTIVE:** Inventory active engine dependencies and preserve inherited work.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Audit completed; 195 baseline tests pass.
- **DEPENDENCIES:** None.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_MIGRATION_AUDIT.md; docs/GRAPHHOPPER_OSRM_INVENTORY.md.
- **IMPLEMENTATION STEPS:** pwd; git status --short; git log --oneline -30; git tag --list.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Audit completed; 195 baseline tests pass.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS.
- **PHASE EXIT GATE:** PASS.

## Phase 1 ? Current upstream research

### Task GH-01

- **TASK ID:** GH-01
- **OBJECTIVE:** Pin maintained release and confirm APIs and motorcycle semantics.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** 11.0 and Java 17+ confirmed; GPX matching; supported motorcycle custom model limitations explicit.
- **DEPENDENCIES:** Phase 0 exit gate PASS.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_MIGRATION_RESEARCH.md.
- **IMPLEMENTATION STEPS:** Read release-tag README, MapMatchingResource, RouteResource, motorcycle model; verify Maven JAR SHA-256.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** 11.0 and Java 17+ confirmed; GPX matching; supported motorcycle custom model limitations explicit.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS.
- **PHASE EXIT GATE:** PASS.

## Phase 2 ? Implementation plan

### Task GH-02

- **TASK ID:** GH-02
- **OBJECTIVE:** Review all migration requirements and create sequential task gates.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** GraphHopper only; no fallback; all live gates covered.
- **DEPENDENCIES:** Phase 1 exit gate PASS.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_FULL_MIGRATION_PLAN.md.
- **IMPLEMENTATION STEPS:** Validate every task has required fields; review scope and dependency order.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** GraphHopper only; no fallback; all live gates covered.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS.
- **PHASE EXIT GATE:** PASS.

## Phase 3 ? Pinned infrastructure

### Task GH-03

- **TASK ID:** GH-03
- **OBJECTIVE:** Import patched Hanoi with two profiles and immutable runtime inputs.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Both profiles return real routes; patched PBF SHA verified.
- **DEPENDENCIES:** Phase 2 exit gate PASS.
- **FILES TO CHANGE:** runtime/graphhopper/Dockerfile; runtime/graphhopper/config.yml; runtime/graphhopper/custom_models/motorcycle.json; .gitignore; docker-compose.yml.
- **IMPLEMENTATION STEPS:** Build GH image; start GH only; query /info and /route for car and motorcycle; record import logs and cache size.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Both profiles return real routes; patched PBF SHA verified.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 4 ? Configuration removal

### Task GH-04

- **TASK ID:** GH-04
- **OBJECTIVE:** Remove engine selectors and single-profile settings.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** No production engine-selection settings or branches.
- **DEPENDENCIES:** Phase 3 exit gate PASS.
- **FILES TO CHANGE:** backend/app/config.py; .env.example; backend/tests/test_config.py; backend/app/api/v1/candidate.py; backend/app/api/v1/map_match.py; backend/app/api/v1/realtime.py.
- **IMPLEMENTATION STEPS:** Replace engine branches with GH wiring; use graphhopper_car_profile and graphhopper_motorcycle_profile; run config/API regression.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** No production engine-selection settings or branches.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 5 ? Active OSRM removal

### Task GH-05

- **TASK ID:** GH-05
- **OBJECTIVE:** Disconnect legacy clients and infrastructure while retaining removable files until replacement verified.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Backend and Compose no longer instantiate or depend on OSRM.
- **DEPENDENCIES:** Phase 4 exit gate PASS.
- **FILES TO CHANGE:** docker-compose.yml; backend/app/api/v1/health.py; backend/app/services/candidate/service.py; backend/app/services/map_matching/engine.py; backend/app/services/map_matching/models.py; backend/app/services/map_matching/__init__.py; backend/tests/conftest.py.
- **IMPLEMENTATION STEPS:** Move neutral matching result types out of legacy adapter; disconnect imports and factories; update readiness to GH; stop project OSRM container.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Backend and Compose no longer instantiate or depend on OSRM.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 6 ? Routing adapter

### Task GH-06

- **TASK ID:** GH-06
- **OBJECTIVE:** Translate domain requests into correct GH routes and explicit failures.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Real profiles work; no fake distance or alternate engine on failure.
- **DEPENDENCIES:** Phase 5 exit gate PASS.
- **FILES TO CHANGE:** backend/app/services/routing/graphhopper_routing_adapter.py; backend/app/services/routing/models.py; backend/tests/test_graphhopper_routing_adapter.py; backend/app/services/routing/profiles.py.
- **IMPLEMENTATION STEPS:** Test car/bike mapping, coordinate order, milliseconds, malformed responses and outages; implement real leg details; reject unsupported requested constraints explicitly.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Real profiles work; no fake distance or alternate engine on failure.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 7 ? Map matching adapter

### Task GH-07

- **TASK ID:** GH-07
- **OBJECTIVE:** Use GPX matching and reconstruct observations from actual matched path.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Real car/bike matching and segment resolution; no invented identifiers.
- **DEPENDENCIES:** Phase 6 exit gate PASS.
- **FILES TO CHANGE:** backend/app/services/map_matching/graphhopper_adapter.py; backend/app/services/map_matching/engine.py; backend/app/services/map_matching/models.py; backend/app/services/map_matching/service.py; backend/app/services/map_matching/segment_resolver.py; backend/tests/test_graphhopper_adapter.py; backend/tests/test_map_matching.py.
- **IMPLEMENTATION STEPS:** Test GPX serialization, profile mapping, geometry projection, OSM details, quality metric, malformed/no-match/error responses; resolve segments from geometry/OSM identity.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Real car/bike matching and segment resolution; no invented identifiers.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 8 ? Week 1 integration

### Task GH-08

- **TASK ID:** GH-08
- **OBJECTIVE:** Use common GH service in batch and realtime without changing state policy.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Week 1 functional regression passes and both endpoints call GH.
- **DEPENDENCIES:** Phase 7 exit gate PASS.
- **FILES TO CHANGE:** backend/app/api/v1/map_match.py; backend/app/api/v1/realtime.py; backend/tests/test_realtime.py.
- **IMPLEMENTATION STEPS:** Resolve category from request vehicle or frozen runtime trip/driver/vehicle records; return actual matched last observation; distinguish no-match and engine failure; test unchanged trigger/window/stationary/gap/stale behavior.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Week 1 functional regression passes and both endpoints call GH.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 9 ? Week 1 quality

### Task GH-09

- **TASK ID:** GH-09
- **OBJECTIVE:** Measure frozen-label matching quality and inspect errors.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Measurements and historical comparison documented, including sampling limitations.
- **DEPENDENCIES:** Phase 8 exit gate PASS.
- **FILES TO CHANGE:** scripts/evaluate_graphhopper.py; docs/GRAPHHOPPER_MIGRATION_REPORT.md; docs/graphhopper_quality.json.
- **IMPLEMENTATION STEPS:** Replay labeled trajectories using runtime inputs only; join labels after predictions; compute match rate, position mean/median/P95/max, directed/base/way/direction accuracy and raw request latency; inspect mismatch examples.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Measurements and historical comparison documented, including sampling limitations.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 10 ? Week 3 integration

### Task GH-10

- **TASK ID:** GH-10
- **OBJECTIVE:** Preserve candidate semantics while using vehicle-specific GH routes.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** All Week 3 tests pass; real multi-leg arithmetic correct.
- **DEPENDENCIES:** Phase 9 exit gate PASS.
- **FILES TO CHANGE:** backend/app/services/candidate/service.py; backend/app/services/routing/multi_leg.py; backend/app/api/v1/candidate.py; backend/tests/test_candidate_api.py; backend/tests/test_multi_leg_routing.py.
- **IMPLEMENTATION STEPS:** Require injected RoutingEngine in domain service; propagate engine faults from every leg instead of UNREACHABLE success; verify car, fixed bike and BOTH services; preserve eligibility precedence.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** All Week 3 tests pass; real multi-leg arithmetic correct.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 11 ? Readiness

### Task GH-11

- **TASK ID:** GH-11
- **OBJECTIVE:** Probe required GH and PostGIS dependencies truthfully.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Unavailable dependency produces HTTP 503, no legacy probe.
- **DEPENDENCIES:** Phase 10 exit gate PASS.
- **FILES TO CHANGE:** backend/app/api/v1/health.py; backend/app/main.py; backend/tests/test_health.py.
- **IMPLEMENTATION STEPS:** Liveness stays process-only; readiness checks both configured profiles and required road table; retain /api/v1/ready and expose /readiness; test unavailable GH.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Unavailable dependency produces HTTP 503, no legacy probe.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 12 ? Deployment

### Task GH-12

- **TASK ID:** GH-12
- **OBJECTIVE:** Verify complete Compose stack without legacy service.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Required services healthy and version pinned.
- **DEPENDENCIES:** Phase 11 exit gate PASS.
- **FILES TO CHANGE:** docker-compose.yml; backend/Dockerfile; Makefile; scripts/smoke_test.py.
- **IMPLEMENTATION STEPS:** docker compose config; docker compose up -d --build; confirm API, GH, DB readiness; make map import and smoke commands GH-only.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Required services healthy and version pinned.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 13 ? Real end-to-end

### Task GH-13

- **TASK ID:** GH-13
- **OBJECTIVE:** Exercise both vehicle profiles, both APIs, candidates and outage.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Real evidence for every required path; no mock-only completion.
- **DEPENDENCIES:** Phase 12 exit gate PASS.
- **FILES TO CHANGE:** scripts/smoke_test_week3.py; scripts/evaluate_graphhopper.py; docs/graphhopper_live.json.
- **IMPLEMENTATION STEPS:** Run real car/bike route and Dataset trajectory matching; replay realtime; search car/fixed bike/BOTH; temporarily stop GH and verify route/MM/readiness fail explicitly; restart GH in finally.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Real evidence for every required path; no mock-only completion.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 14 ? Performance

### Task GH-14

- **TASK ID:** GH-14
- **OBJECTIVE:** Measure initial local GH performance without load-capacity claims.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** INITIAL LOCAL GRAPHHOPPER PERFORMANCE BASELINE recorded.
- **DEPENDENCIES:** Phase 13 exit gate PASS.
- **FILES TO CHANGE:** scripts/benchmark_week3.py; scripts/benchmark_realtime_map_matching.py; docs/graphhopper_performance.json.
- **IMPLEMENTATION STEPS:** At least 20 representative searches; raw latency median/P90/P95/max, throughput and counted calls/search; matching size and percentiles; concurrency 1/5/10; docker stats snapshot.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** INITIAL LOCAL GRAPHHOPPER PERFORMANCE BASELINE recorded.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 15 ? Dead-code cleanup

### Task GH-15

- **TASK ID:** GH-15
- **OBJECTIVE:** Delete disconnected legacy code after real engine passes.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** No active legacy path; mock imports restricted to tests.
- **DEPENDENCIES:** Phase 14 exit gate PASS.
- **FILES TO CHANGE:** backend/app/services/routing/osrm_routing_adapter.py; backend/app/services/map_matching/osrm_adapter.py; backend/tests/test_osrm_routing_adapter.py; runtime/osrm/profiles/car.lua; backend/app/services/routing/mock_adapter.py; backend/tests/mock_routing_adapter.py; PLAN.md.
- **IMPLEMENTATION STEPS:** Delete old clients/tests/profile; move mock to tests; replace obsolete scripts; classify each remaining occurrence including immutable Dataset provenance.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** No active legacy path; mock imports restricted to tests.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 16 ? Documentation

### Task GH-16

- **TASK ID:** GH-16
- **OBJECTIVE:** Make repository source of truth match mentor decision.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** Current instructions describe sole GH runtime and OSM foundation.
- **DEPENDENCIES:** Phase 15 exit gate PASS.
- **FILES TO CHANGE:** AGENTS.md; README.md; docs/ARCHITECTURE.md; docs/DECISIONS.md; docs/ROUTING_STRATEGY.md; docs/DATA_CONTRACT.md; docs/WEEK_3.md; docs/GRAPHHOPPER_MIGRATION_REPORT.md.
- **IMPLEMENTATION STEPS:** Add sole-runtime ADR; preserve historical freeze evidence with superseded notices; document profile limitations, error handling, setup and measurements.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** Current instructions describe sole GH runtime and OSM foundation.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 17 ? Full regression

### Task GH-17

- **TASK ID:** GH-17
- **OBJECTIVE:** Verify Weeks 1/2/3, migration and frozen Dataset.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** All tests and dataset validation pass; frozen data unchanged.
- **DEPENDENCIES:** Phase 16 exit gate PASS.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_MIGRATION_REPORT.md.
- **IMPLEMENTATION STEPS:** python -m pytest backend/tests -q; python dataset_v1/validation/validate_dataset.py; compare every source SHA against initial manifest; report suites separately.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** All tests and dataset validation pass; frozen data unchanged.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Phase 18 ? Final audit and freeze

### Task GH-18

- **TASK ID:** GH-18
- **OBJECTIVE:** Audit architecture, commits, generated files and completion criteria.
- **WHY:** Required for sole-engine migration while preserving Weeks 1?3 contracts.
- **INPUTS:** Audited repository, frozen Dataset runtime inputs, approved migration requirements, release-tag research.
- **OUTPUTS:** All final gates pass; no Week 4; clean tree; then graphhopper-full-migration-complete and week3-candidate-routing-complete.
- **DEPENDENCIES:** Phase 17 exit gate PASS.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_MIGRATION_REPORT.md; docs/GRAPHHOPPER_FULL_MIGRATION_PLAN.md.
- **IMPLEMENTATION STEPS:** Repository-wide search; git diff --check; final code review; fix/retest; explicit git add paths and coherent commits; inspect clean status; create tags only after full pass.
- **TESTS:** Run the named task checks; run `python -m pytest backend/tests -q` for application changes. Live gates must use actual GH and fail on outage; no mock fallback.
- **SELF-REVIEW:** Inspect `git diff --check` and file diffs; check vehicle mapping, honest failures, unchanged policies, labels excluded from runtime, no Dataset edits, no generated caches staged. Fix findings and rerun affected checks before exit.
- **EXIT GATE:** All final gates pass; no Week 4; clean tree; then graphhopper-full-migration-complete and week3-candidate-routing-complete.
- **RISKS:** API mismatch, profile access limitations, engine latency and regression in inherited code; measure rather than infer.
- **ROLLBACK / FAILURE BEHAVIOR:** Remain in this phase and fix/retest; preserve inherited work and frozen data. Do not silently restore legacy runtime or fake success. No freeze tags on partial completion.
- **RESULT:** PASS. See the corresponding phase evidence in GRAPHHOPPER_MIGRATION_REPORT.md.
- **PHASE EXIT GATE:** PASS; Phase 18 freeze is finalized only at the clean tagged commit.

## Plan exit gate ? PASS

- [x] Sole GH routing and matching; no selectable engine or fallback.
- [x] Mock test-only and legacy deletion tasks.
- [x] Weeks 1/2/3 preserved, Week 4 excluded.
- [x] Frozen Dataset and historical tags protected.
- [x] Real runtime, both profiles, matching quality, candidates, outages and performance included.
- [x] Every phase has a task with all requested fields.
- [x] Full regression, final code/architecture audit, documentation and conditional freeze included.

Plan self-review: inherited draft assumptions are superseded by verified release APIs. Supported motorcycle model shared-access limitations are disclosed, not hidden by the profile name. Historical mock benchmark is not compared as an OSRM runtime benchmark. Execute automatically.
