# Local coverage and deviation-rich cohorts implementation plan

> Execute inline with executing-plans; independent whole-change review before completion.

**Goal:** More distinct local road journeys and more diverse departing trips, measured honestly.
**Spec:** [contract](../specs/2026-10-15-local-coverage-and-deviations.md).
**Stack:** Existing Python/PostGIS/GraphHopper/H3/FastAPI/Leaflet; no new dependency.

- [x] Extend offline audit with engine-scope evidence and small-cell local gap targets;
  test scope clipping, local-road selection and target uniqueness. Record baseline.
- [x] Test/implement deterministic local trip generation with varied departure indices,
  nearby vias, strict snap/length checks and varied drivers. Persist manifests/truth
  before analysis; report rejections and detector disagreements, preserve old data.
- [x] Separate coverage/stress cohorts in metadata and optional aggregate selection;
  test causal SQL, default compatibility, legacy exclusion and API input validation.
- [x] Run real local generation and held-out evaluation; audit same-time before/after
  reference length, local diversity and departing-trip counts. Verify browser controls.
- [x] Run appropriate suites, Dataset integrity and review; update ADR/report/tracker,
  commit on feature branch without merging/pushing.

Ruling: imported map bounds are smaller than configured bbox. Work within their
intersection and disclose the missing-map area; do not alter canonical PBF or
pretend all Hanoi is available. Coverage reports remain approximate reference
proximity, not verified administrative/drivable coverage.
