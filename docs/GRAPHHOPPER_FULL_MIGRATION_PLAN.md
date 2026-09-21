# GraphHopper full migration implementation plan

Goal: OSM foundation; GraphHopper sole routing and matching runtime through Week 3. Existing domain contracts, state policies, demand and candidate semantics remain. Shared deterministic vehicle mapping; actual GPX matched geometry and existing PostGIS segment resolver. No runtime fallback.

User authorizes automatic implementation. Work stays in E:/build6week on graphhopper-full-migration with original dirty work preserved. Frozen dataset stays read-only. Each task: failing behavior test, implementation, task test, regression, diff review, fix/retest, task gate, phase gate. Environmental blockers recorded while independent work continues; failing ordinary gates repaired before dependent work.

## Phase 0: Audit

- [ ] **TASK ID:** GH-0.1
- **OBJECTIVE:** Audit.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** AGENTS.md; docs; backend; scripts; runtime.
- **IMPLEMENTATION STEPS:** Read docs and Git history, inventory dependencies, hash all dataset files.
- **TESTS:** git status; rg inventory; SHA256 manifest.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** All dependencies classified and original changes preserved.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 1: Research

- [ ] **TASK ID:** GH-1.1
- **OBJECTIVE:** Research.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_MIGRATION_RESEARCH.md.
- **IMPLEMENTATION STEPS:** Verify official stable release, Java, GPX API and motorcycle limits.
- **TESTS:** Read official 11.0 source.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Pinned release and documented profile strategy.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 2: Plan

- [ ] **TASK ID:** GH-2.1
- **OBJECTIVE:** Plan.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** docs/GRAPHHOPPER_FULL_MIGRATION_PLAN.md.
- **IMPLEMENTATION STEPS:** Map brief to tasks and check scope.
- **TESTS:** Self-review against migration brief.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Sole engine, no fallback, immutable dataset, no Week 4.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 3: Infrastructure

- [ ] **TASK ID:** GH-3.1
- **OBJECTIVE:** Infrastructure.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** runtime/graphhopper/; docker-compose.yml; .gitignore.
- **IMPLEMENTATION STEPS:** Pin 11.0 JAR and Java, fresh cache, patched PBF read-only, car/motorcycle models.
- **TESTS:** docker compose config; build/start GH; real route and GPX both profiles.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Imported graph and both profiles work.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 4: Selectors

- [ ] **TASK ID:** GH-4.1
- **OBJECTIVE:** Selectors.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** config.py; .env.example; API providers.
- **IMPLEMENTATION STEPS:** Remove engine switches and global profile.
- **TESTS:** Config/factory tests; rg selectors.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Only GraphHopper injection.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 5: Active removal

- [ ] **TASK ID:** GH-5.1
- **OBJECTIVE:** Active removal.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** docker-compose.yml; Makefile; scripts; health.py.
- **IMPLEMENTATION STEPS:** Remove old service, startup, environment and probes.
- **TESTS:** Compose validation; source inventory.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** No active OSRM dependency.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 6: Routing

- [ ] **TASK ID:** GH-6.1
- **OBJECTIVE:** Routing.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** routing/graphhopper_routing_adapter.py; routing/models.py; graphhopper.py; tests.
- **IMPLEMENTATION STEPS:** Test and implement domain category mapping, real schema, actual via legs, explicit errors.
- **TESTS:** Adapter and multi-leg tests; real routes.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Car/motorcycle routes, no fake metrics.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 7: Matching

- [ ] **TASK ID:** GH-7.1
- **OBJECTIVE:** Matching.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** map_matching/engine.py; graphhopper_adapter.py; models.py; tests.
- **IMPLEMENTATION STEPS:** Neutral contracts, GPX POST, geometry projection, quality, client cleanup.
- **TESTS:** Adapter tests; real dataset traces.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Both profiles match with no fabricated identifiers.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 8: Week 1

- [ ] **TASK ID:** GH-8.1
- **OBJECTIVE:** Week 1.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** map_matching/service.py; segment_resolver.py; map_match.py; realtime.py.
- **IMPLEMENTATION STEPS:** Resolve category using trip/vehicle metadata; share batch pipeline; preserve state policies.
- **TESTS:** Matching/realtime tests; real ingestion.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Actual segment resolution, policies unchanged.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 9: Quality

- [ ] **TASK ID:** GH-9.1
- **OBJECTIVE:** Quality.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** scripts/verify_graphhopper.py; docs/reports/.
- **IMPLEMENTATION STEPS:** Evaluate frozen labelled observations with trace context and inspect mismatches.
- **TESTS:** Real quality evaluation and historical comparison.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** All quality metrics measured with sample caveats.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 10: Week 3

- [ ] **TASK ID:** GH-10.1
- **OBJECTIVE:** Week 3.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** candidate/service.py; routing/multi_leg.py; candidate.py; tests.
- **IMPLEMENTATION STEPS:** Inject GH only; propagate engine failures; preserve eligibility and expansion.
- **TESTS:** Candidate suites; car/fixed bike/BOTH live searches.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Real multi-leg sums, detours, no fallback.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 11: Readiness

- [ ] **TASK ID:** GH-11.1
- **OBJECTIVE:** Readiness.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** health.py; main.py; test_health.py.
- **IMPLEMENTATION STEPS:** Probe GH profiles and required PostGIS, process-only health.
- **TESTS:** Healthy/down tests and live engine stop.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Unavailable GH returns 503.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 12: Deployment

- [ ] **TASK ID:** GH-12.1
- **OBJECTIVE:** Deployment.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** docker-compose.yml; backend/Dockerfile.
- **IMPLEMENTATION STEPS:** Build API, mount data read-only, correct health probes.
- **TESTS:** docker compose config; up --build; ps.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Required services healthy.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 13: End-to-end

- [ ] **TASK ID:** GH-13.1
- **OBJECTIVE:** End-to-end.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** scripts/verify_graphhopper.py; docs/reports/.
- **IMPLEMENTATION STEPS:** Real routes, matching, realtime, three candidate cases; stop GH then restore.
- **TESTS:** Real HTTP assertions and logs.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** All live cases and failure behavior verified.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 14: Performance

- [ ] **TASK ID:** GH-14.1
- **OBJECTIVE:** Performance.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** scripts/verify_graphhopper.py; docs/reports/.
- **IMPLEMENTATION STEPS:** 20 searches and matching samples; concurrency 1/5/10; calls/resources.
- **TESTS:** Run real benchmark.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** INITIAL LOCAL GRAPHOPPER PERFORMANCE BASELINE recorded.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 15: Dead cleanup

- [ ] **TASK ID:** GH-15.1
- **OBJECTIVE:** Dead cleanup.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** old adapters/tests/scripts; runtime/osrm/profiles/car.lua.
- **IMPLEMENTATION STEPS:** Reinventory after live pass; remove dead clients; relocate mocks to tests.
- **TESTS:** rg entire repo; regression.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Only historical/frozen references remain.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 16: Documentation

- [ ] **TASK ID:** GH-16.1
- **OBJECTIVE:** Documentation.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** AGENTS.md; README.md; ARCHITECTURE.md; DECISIONS.md; ROUTING_STRATEGY.md; WEEK_3.md; migration report.
- **IMPLEMENTATION STEPS:** Sole-engine ADR, reproducible commands and limitations; supersede old plan.
- **TESTS:** Review docs versus code and evidence.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** Current docs agree with actual architecture.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 17: Regression

- [ ] **TASK ID:** GH-17.1
- **OBJECTIVE:** Regression.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** backend/tests; dataset validator.
- **IMPLEMENTATION STEPS:** All tests and validator; compare dataset hashes.
- **TESTS:** python -m pytest backend/tests; python dataset_v1/validation/validate_dataset.py.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** All pass and dataset unchanged.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Phase 18: Audit/freeze

- [ ] **TASK ID:** GH-18.1
- **OBJECTIVE:** Audit/freeze.
- **WHY:** Required migration gate.
- **INPUTS:** Audited repository, contracts, frozen data, release research.
- **OUTPUTS:** Reviewed changes and command evidence.
- **DEPENDENCIES:** Prior applicable gates.
- **FILES TO CHANGE:** migration report; Git explicit paths.
- **IMPLEMENTATION STEPS:** Final diff/source/data audit, coherent commits; tags only on complete status.
- **TESTS:** git diff --check; rg audit; git status; code review.
- **SELF-REVIEW:** No labels as prediction input, invented metrics, engine fallback, generated cache commits or Week 4.
- **EXIT GATE:** No selectors/fallback/mocks in runtime, clean migration tree.
- **RISKS:** Schema mismatch, stock motorcycle access limits, unavailable services, original untracked files.
- **ROLLBACK / FAILURE BEHAVIOR:** Repair without destructive Git; explicit failure; preserve evidence; no tags on PARTIAL.

## Plan exit gate

PASS: sole routing/matching engine, tests-only mocks, preserved Weeks 1-3, frozen dataset, real tests, quality, failure injection, benchmark and final audits included. Implement automatically.
