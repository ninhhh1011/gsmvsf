# Guided data quality implementation plan

> Execute inline with executing-plans. Owner explicitly requested planning followed immediately by implementation.

**Goal:** Produce a compact, road-diverse paired-guidance benchmark and an actual measured coverage expansion while retaining runtime 80/10/10.

**Architecture:** Extend the existing local GraphHopper seeder with an opt-in versioned benchmark mode; reuse existing coverage audit, detector and synthetic storage. Freeze source targets, route geometry, grouped splits and maneuver declarations before detection. Existing manifests retain their old behavior.

**Tech stack:** Existing Python, GraphHopper, H3, PostgreSQL/PostGIS and pytest; no new dependencies.

**Spec:** `docs/reports/route-data-research-audit-2026-10-15.md`, narrowed by the owner's latest instruction to retain 80/10/10.

## Global constraints

- Use the intersection of configured and imported map bounds; report candidate-reference proximity, never all-Hanoi or verified directed-access coverage.
- Ranking weights and runtime detector remain unchanged. No retraining or weight activation.
- Keep canonical baseline and old histories available. New generated data is versioned; ingest only train records in the synthetic namespace.
- Source/template grouping is fixed before detector results, with train/validation/test and disjoint driver identities. Group by H3-7 origin plus identical geometry; report that traversed roads can overlap.
- Select a bounded route library by incremental H3-11 sampled road-footprint novelty, then measure actual reference-length gain with the existing PostGIS audit. The selection proxy is not the final coverage metric.
- Freeze balanced controls and departure scenarios. Never remove a case because detection disagrees with its declaration.

## Review focus

1. Same-template variants/driver IDs cannot cross splits; deterministic assignments survive input reordering.
2. Guidance updates and observation gaps survive generation; cadence changes cannot turn a reroute into a false departure or fill a gap.
3. Zero predicted departures and empty strata produce defined counts and null undefined ratios, not division errors or fabricated success.
4. Existing manifests remain reproducible; benchmark retry rejects incompatible mode/options.
5. Coverage reports compare the same as-of and denominator; no label consumption at runtime or ranking change.

### Task 1: Reproducible grouped benchmark and tests

Files: create `scripts/guided_benchmark.py`, `backend/tests/test_guided_benchmark.py`; modify `scripts/seed_local_guided.py`.

Interfaces: `select_templates(templates, maximum, seed)` returns frozen selected templates with split/group/held_out metadata; `benchmark_inputs(manifest, batch)` returns GuidedTrip records and offline declarations; `evaluation_report(rows)` returns split/scenario confusion counts and event count discrepancies.

- [x] Write/run failing tests for deterministic novelty selection, grouped splits, driver isolation, all seven maneuver types, preserved GAP/REROUTE chronology, and confusion accounting.
- [x] Implement versioned benchmark mode with cases FOLLOW, EXIT, EXIT_LATE, RETURN_EXIT, REROUTE, GAP, NOISE. Keep original seeder mode and manifests usable.
- [x] Run `python -m pytest backend/tests/test_guided_benchmark.py backend/tests/test_local_guided_seed.py backend/tests/test_route_deviations.py -q` and Ruff. Expect all passing; commit.

### Task 2: Coverage-driven targets and real generation

Files: modify `scripts/audit_guided_coverage.py`, `backend/tests/test_guided_coverage.py`; generated files under `runtime/guided-quality-20261015/`.

- [x] Test configurable target resolution/count validation, retaining old default 120/H3-7.
- [x] Add bounded CLI selection of H3-8 targets and up to 240 candidates. Reuse uncovered reference roads; retain all rejection evidence.
- [x] Run a same-time pre-audit, prepare real GraphHopper routes, greedily retain at most 120 templates, generate paired records and freeze train/validation/test before detector evaluation. Ingest train only.
- [x] Run same-time post-audit. Report actual improvement, rejections, scenario metrics and split sizes even when outcomes are unfavorable; no outcome-based generator tuning.

### Task 3: Honest status and verification

Files: `AGENTS.md`, `README.md`, `docs/PHASE_TRACKER.md`, `docs/DATA_CONTRACT.md`, `docs/DECISIONS.md`, and a results report under `docs/reports/`.

- [x] Correct tracker path and historical Week 6 status while separating local operational checks from current production readiness.
- [x] Document coverage proxy, grouped holdout limits, synthetic stress semantics and unchanged ranking. Mark prior calibration report exploratory due generator changes after held-out inspection.
- [x] Run focused regression, lint, data/report checks and unchanged-ranking diff; run appropriate wider backend checks. Verify direct API readiness without redeploying.
- [x] Fresh whole-change review, fix material findings, commit and report measurements and limits.
