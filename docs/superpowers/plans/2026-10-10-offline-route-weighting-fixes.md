# Offline route comparison and weighting corrections implementation plan

**Goal:** Correct the reviewed matching, history, energy and UI bugs, and connect the corrected comparison to the existing bounded ranking penalty.

**Architecture:** Reuse H3, GraphHopper, asyncpg and the current modular monolith. Keep the stored index compatible while adding geometric evidence. Offline comparison and causal history ranking share one matcher; energy remains backend-owned.

**Spec:** `docs/superpowers/specs/2026-10-10-offline-route-weighting-fixes.md`.
**Execution:** implement in this session with independent energy/frontend tasks and final independent review; no merge, push, runtime activation or destructive migration.

## Constraints and rulings

Dataset V1 stays read-only. No new dependencies. Feature remains opt-in behind identity authentication. Preserve 30-second penalty cap, physical ETA, eligibility and 409 retry. Work on `fix/offline-route-weighting` in the shared checkout because its runtime and Dataset already reside here; preserve pre-existing `runtime/review-h3-energy` artifacts. The user requested both planning and execution, so proceed without another approval round.

## Task 1 — Correct bounded geometric comparison

Owner: primary. Files: `route_familiarity/route_matcher.py`, matcher/API tests. Add failing reproductions for 80 m vs 2 m, repeated traversal, neighboring-cell 4 m offset and sampling-density invariance. Use local metric projection onto directed segments, H3 neighbor bins, ordered alignment and one-use distance accounting. Bound route vertices/distance/sample pairs, expose shared geometry and both route cell sets. Compare the resulting checks before progressing.

```python
assert result.shared_distance_m <= min(result.proposed_distance_m, result.actual_distance_m)
assert compare(route, list(reversed(route))).shared_distance_m == 0
```

## Task 2 — Add causal geometry history and connect ranking

Owner: primary. Files: signature/models, repository/schema/ingestion/API, temporal, familiarity service, ranking explanation; corresponding history/ranking tests and benchmark fixtures. Add bounded geometry and optional started_at through explicit additive DDL. Exclude completion at or after request time, group by start, query neighboring stored index cells. Skip legacy geometry as unavailable and make this visible. Reuse the matcher for personal/community evidence, maintain capped penalties and shared batch work budget. Protected comparison history uses existing driver identity checks; anonymous comparisons do no history reads. Reproduce an actual change in ranked station order using geometric history.

```python
assert assessment.penalty_s <= 30
assert history_completed_at >= request_time implies record_not_used
```

## Task 3 — Unify energy and catalog

Owner: energy worker. Files: `services/energy/`, `api/v1/vehicles.py`, energy tests. Preserve physical metadata through the API catalog. Add validated power-step API returning power, interval energy and updated SOC/range. Source/provenance applies per parameter; unknown models are explicit. Add tests for parked HVAC depletion, regeneration, infeasible acceleration, zero interval, unsupported model and catalog fields. Keep frontend changes under Task 4 ownership.

## Task 4 — Offline Driver UI and real contracts

Owner: frontend worker. Files: Driver controller, overlay, catalog/model JS, cockpit renderers/bindings, index and frontend tests. Canonical comparison payload uses proposed_coordinates/actual_coordinates/resolution/as_of_iso/vehicle_model. Response uses shared_pct_on_proposed/shared_pct_on_actual/shared_distance_m/shared_cells and route cell sets. Freeze offline proposed geometry; reject stale generations/resolutions/toggle states. Distinguish a comparison with zero matches from station coverage. Fetch energy from Task 3 power-step API rather than duplicate physics; preserve catalog metadata. Rewrite obsolete removed-view tests against Driver-only behavior; never resurrect removed apps.

## Task 5 — API bounds, lint and documentation

Owner: primary. Run CPU matcher in a worker thread, reject work exhaustion clearly, canonicalize response, update ADR/architecture/operations and tracker with accurate current evidence. Remove unused imports in the API and existing lint errors without unrelated behavior changes. Add direct contract checks linking frontend requests to backend validation/response; no mocks inventing a second protocol.

## Task 6 — Verify and review

Run `python -B -m pytest backend/tests -q -p no:cacheprovider --basetemp=runtime/offline-route-fixes/pytest`, `node --test tests/frontend/*.mjs`, `ruff check backend`, and `python -B scripts/validate_frozen_dataset.py`. Compare before/after hashes for canonical Dataset files including PBFs. Review shared geometry, anonymous history access, unknown metadata, migration idempotency, time-window bounds and stale UI. Record evidence and remaining model limitations; fix material findings before completion.

## Interface preflight

| Producer / consumer | Contract |
|---|---|
| Matcher / ranking & comparison API | RouteComparisonMetrics; projection/heading/order; shared budget |
| Ingestion / repository / ranking | geometry coordinate pairs, optional started_at, strict completed_at < as_of |
| Energy API / Driver | power-step request model/speed/previous speed/dt/current SOC; return instantaneous_power_kw, energy_delta_kwh, current_soc_pct, estimated_range_km |
| Comparison API / Driver | canonical fields above; whole offline route inputs; metric units in meters |

All tasks consume the spec constraints. No field name synonyms are introduced. Legacy history remains preserved but cannot stand in for missing geometric evidence.

## Completion ledger

- Task 1 complete: reviewed 80 m/2 m, revisits, neighbor-cell and distance-limit regressions failed first, then passed. Added dateline and sample-budget regressions from final review.
- Task 2 complete: geometry/start persistence, trusted additive evidence upgrade, causal window scoring and existing ranking cost integration verified, including a station-order change without changing ETA.
- Task 3 complete: backend catalog/power API, interval energy, unavailable models and honest provenance; task review passed.
- Task 4 complete: frozen offline extent/time, canonical contracts, catalog preservation, backend energy and stale response/lifecycle fixes; 196 frontend checks passed.
- Task 5 complete: bounds/thread execution, request-local reuse, lint and ADR/operations/current evidence.
- Task 6 complete: 561 backend checks passed (12 existing skips), full frontend/lint/validator/hash gates passed; actual GraphHopper and isolated real PostgreSQL checks passed. Independent review findings fixed.
- Ruling: retain Resolution 11 as backward-compatible persisted search index while geometric comparison uses 9 — avoids rewriting old signatures; cost is explicit two-resolution metadata.
- Ruling: preserve legacy records as unavailable until trusted evidence upgrade — avoids invented geometry/time; legacy history contributes no ranking penalty until upgraded.
- Ruling: leave runtime opt-in off and application database unmigrated — identity gateway/ingestion secrets remain protected; deployment activation is separate from code implementation.
- Known limits: 10 m corridor approximation; uncalibrated 45 m/60-degree tolerances and physics coefficients; no live browser deployment QA.
