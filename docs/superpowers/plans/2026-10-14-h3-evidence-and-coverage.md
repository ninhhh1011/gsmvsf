# H3 evidence and coverage implementation plan

> Execute inline with executing-plans, task by task; use independent code review.

**Goal:** Explain each trip and the spatial evidence gaps without invented behavior.
**Architecture:** Existing FastAPI/PostgreSQL/H3/Leaflet; offline PostGIS coverage
audit and GraphHopper-targeted seeding. No dependency, ranking or production change.
**Spec:** [contract](../specs/2026-10-14-h3-evidence-and-coverage.md).

- [x] Add tested per-trip active-guidance interval classification and existing
  two-denominator whole-route comparison; expose bounded stateless inspection.
- [x] Add gated synthetic examples and a review screen showing guidance, observed
  route, confirmed red intervals, unknown intervals and support/copy. Preserve stale
  response guards and current aggregate mode. Test gaps, updates and privacy gates.
- [x] Audit candidate-reference road length by geographic region using paired GPS,
  explicit tolerance and continuity. Tests verify duplicate directions, gaps and
  lack of permissions do not become authoritative eligible-road claims.
- [x] Seed diverse real routes through measured gaps in a separate reproducible
  batch. Audit before/after; preserve original rows and offline independent truth.
- [x] Verify meaningful backend/frontend regressions, actual engine/DB/API,
  desktop/mobile rendering and Dataset hashes. Record limits and review; no merge.

Completion requires evidence for both route denominators, off-route geometry/time,
unknown handling, source diversity and road-length coverage. A fully painted map,
high trip count or all-zero controls alone do not constitute completion.

Evidence and remaining data/permission limits: [report](../../reports/h3-evidence-and-coverage-2026-10-14.md).
