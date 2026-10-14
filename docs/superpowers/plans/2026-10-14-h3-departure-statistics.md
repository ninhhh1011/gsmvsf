# H3 departure statistics implementation plan

> Execute inline using executing-plans and test-driven-development. User explicitly
> authorized implementation in this session; no merge until separately permitted.

**Goal:** A truthful seven-day map of confirmed guidance-departure origins.
**Architecture:** Trusted paired evidence, analysis at ingestion, PostgreSQL aggregate,
and a presentation-only H3 overlay; retain the existing comparison mode.
**Tech stack:** Existing Python/FastAPI/asyncpg/H3, Leaflet and Node tests.
**Spec:** [approved contract](../specs/2026-10-14-h3-departure-statistics.md).

## Global constraints

Do not modify Dataset V1 or legacy histories. No new dependencies or ranking changes.
Evidence/outputs live inside this repository. Branch remains unmerged.

## Review focus

GPS noise/gaps, route version boundaries, repeated departures in the same cell,
causal window denominators, production privacy and stale browser requests.

### Task 1: Validate and detect departures

Files: new `backend/app/services/route_familiarity/deviations.py` and
`backend/tests/test_route_deviations.py`. Consume timestamped guidance/observations;
produce `analyze_guided_trip` cell evidence for resolutions 5–10.

- [x] Write and run failing scenario/validation tests.
- [x] Reuse corridor geometry to confirm departures/returns, rejecting gaps and ambiguity.
- [x] Run domain tests and record assumptions.

### Task 2: Persist and aggregate evidence

Files: familiarity schema/repository/API, new API tests. Consume Task 1 analysis;
produce protected immutable ingestion and `/routing/departure-heatmap` aggregate.

- [x] Write failing idempotency, window, privacy and outage tests.
- [x] Add a separate evidence table and explicit additive migration.
- [x] Aggregate distinct trips and all events in seven days; disclose legacy exclusions.
- [x] Verify tests and real isolated PostgreSQL schema/API.

### Task 3: Display the city grid

Files: overlay, controller, bindings, API client and demo HTML; frontend regressions.
Consume Task 2 percentages at the effective grid resolution, not static visit weights.

- [x] Write failing full-viewport, unknown-data and stale-response tests.
- [x] Add departure/comparison mode, gray unknown cells, truthful popups and adaptive detail.
- [x] Run frontend suite and inspect desktop/mobile browser.

### Task 4: Audit and independently verify synthetic data

Files: verification script, reports, DATA_CONTRACT/ARCHITECTURE/DECISIONS/PHASE_TRACKER.
Consume paired ingestion/aggregation and independently authored offline event truth.

- [x] Audit actual stored evidence without rewriting old trips.
- [x] Verify deterministic fake noise/leave/return/reroute/gap cases and distinct counts.
- [x] Run backend/frontend suites, lint and canonical validator; record evidence.
- [x] Review branch, fix findings, leave it unmerged for the owner.

Completion: all tasks verified; see `docs/reports/h3-departure-statistics-2026-10-14.md`. Branch held unmerged by owner instruction.
