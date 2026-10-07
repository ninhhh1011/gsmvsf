# Route Familiarity v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task by task. Each task receives a fresh implementer, then a spec reviewer and a code-quality reviewer; resolve findings and re-review before marking it done.

**Goal:** Add directional, resolution-11 personal/community route familiarity as an opt-in, explainable, strictly bounded ranking penalty with a local map overlay and measured lookup performance.

**Architecture:** Generate ordered, distance-weighted H3 signatures from existing GraphHopper route polylines and trusted internal completed-route ingestion. Keep candidate signatures and assessments transient through the combined `/recommend` workflow; do not persist them in candidate evidence. The ranking stage evaluates them as-of the candidate search time and adds only a bounded personal-evidence penalty after eligibility and physical completion-cost calculation. Community evidence is explanation-only. The staged `/ranking/candidates` and `/ranking` endpoints do not return familiarity data. Render an opt-in local-vendored H3 overlay from the combined recommendation response.

**Tech Stack:** FastAPI, Pydantic v2, asyncpg/PostgreSQL, existing `h3` Python package pinned to v4, vendored `h3-js` 4.5.0, Leaflet, pytest, Node test runner, Ruff.

**Spec:** [2026-10-07-route-familiarity-v2-design.md](../specs/2026-10-07-route-familiarity-v2-design.md)

## Global Constraints

- `H3_ROUTE_RESOLUTION = 11` is the sole backend resolution source.
- `dataset_v1/` is read-only.
- GraphHopper remains the only production routing adapter.
- Candidate eligibility, physical ETA, queue/service semantics, and 409 behavior remain unchanged.
- `ENABLE_ROUTE_FAMILIARITY` defaults to `false`; disabled ranking equals baseline ranking and performs no familiarity DB lookup.
- No psycopg2, synchronous DB calls, module singletons, CDN H3, Kafka, Kubernetes, or new runtime infrastructure.
- No personal route-history read API; ingestion is token-protected and trusted-producer-only; metrics/logs contain no driver/trip identifiers. Feature-on `/recommend` requires an HMAC-SHA256 signature from a trusted gateway over the exact driver ID; feature-off authentication behavior stays unchanged.
- Familiarity penalty is nonnegative and bounded by configurable `max_familiarity_penalty_s` (default 30 seconds).

## Review Focus

- Malformed, non-finite, out-of-range, dateline-crossing, short, long, repeated-cell, and reversed polylines must reject or produce deterministic signatures safely.
- H3 set overlap must not make a reversed route a full directional match; overlapping-distance math must stay within `[0, recommended_distance]`.
- No history, disabled feature, database outage, and missing route geometry must never add penalty or alter eligibility.
- Community aggregation must count distinct drivers and keep one high-volume driver from dominating.
- Overlay must remain responsive at the cell cap, keep all cells at resolution 11, and show truncation clearly.

---

### Task 1: Resolution-11 route signature and directional similarity

**Files:**
- Create: `backend/app/services/route_familiarity/constants.py`
- Create: `backend/app/services/route_familiarity/models.py`
- Create: `backend/app/services/route_familiarity/signature.py`
- Create: `backend/app/services/route_familiarity/similarity.py`
- Create: `backend/app/services/route_familiarity/__init__.py`
- Modify: `backend/pyproject.toml` (pin supported H3 v4)
- Test: `backend/tests/test_route_familiarity_domain.py`

**Interfaces:**
- `H3_ROUTE_RESOLUTION = 11` in one backend constant module.
- `decode_polyline(encoded: str) -> list[tuple[float,float]]`.
- `create_route_signature(polylines: Sequence[str]) -> RouteSignature` with `cells`, aligned `cell_distances_m`, `distance_m`, and `resolution`.
- `weighted_ordered_overlap(recommended: RouteSignature, historical: RouteSignature) -> SimilarityResult` with shared distance and adherence.

- [ ] Write tests first for malformed coordinates, deterministic short/long routes, repeated cells, reversal, partial/complete/zero overlap, and valid ranges.
- [ ] Run `python -B -m pytest backend/tests/test_route_familiarity_domain.py -q`; verify expected failures.
- [ ] Implement polyline decoding/densification and ordered H3-11 weighted signatures with H3 v4.
- [ ] Implement weighted LCS and clamp shared distance/adherence.
- [ ] Rerun focused tests and `ruff check backend`; commit `feat: add deterministic res11 route signatures`.

### Task 2: Async history schema, repository, and protected ingestion

**Files:**
- Create: `backend/app/services/route_familiarity/schema.sql`
- Create: `backend/app/services/route_familiarity/repository.py`
- Create: `backend/app/services/route_familiarity/ingestion.py`
- Create: `backend/app/api/v1/route_familiarity.py`
- Create: `scripts/migrate_route_familiarity.py`
- Modify: `backend/app/main.py`, `backend/app/core/lifespan.py`, `backend/app/dependencies.py`
- Test: `backend/tests/test_route_familiarity_repository.py`, `backend/tests/test_route_familiarity_api.py`

**Interfaces:**
- `RouteHistoryRepository(pool).ensure_schema()` is not called by app startup; migration script applies explicit DDL.
- `async upsert_route(driver_id, trip_id, completed_at, signature) -> (record, created)` is idempotent; conflicting retry raises domain `StateError` 409.
- `POST /api/v1/internal/route-familiarity/routes` reuses `authorize_ingestion` and accepts only completed route data; no read API.
- Repository methods use only `asyncpg.Pool` and async connections.

- [ ] Write failing tests for migration shape/indexes, async pool acquire, idempotent retry/conflicting retry, future-event exclusion, and 401/403/503 ingestion authorization.
- [ ] Run focused tests and verify they fail on missing repository/API behavior.
- [ ] Add `realtime.route_familiarity_routes` with aligned ordered cell/distance arrays, resolution check, unique `(driver_id,trip_id)`, B-tree driver/time and GIN cell indexes.
- [ ] Implement 100 KB encoded-polyline, 20,000-vertex, 2,000-cell, and 100 km limits; signature creation; token-protected upsert; and generic errors without logging payloads.
- [ ] Wire repository only through lifespan/app.state; feature-off startup and recommendation must not require the table.
- [ ] Rerun focused tests and commit `feat: persist protected route familiarity history`.

### Task 3: Candidate signatures and personal/community evaluation

**Files:**
- Create: `backend/app/services/route_familiarity/service.py`
- Modify: `backend/app/services/routing/multi_leg.py`, `backend/app/services/candidate/models.py`, `backend/app/services/candidate/service.py`, `backend/app/services/ranking/models.py`, `backend/app/services/ranking/orchestration.py`, `backend/app/services/ranking/service.py`, `backend/app/config.py`, `backend/app/core/lifespan.py`, `.env.example`
- Test: `backend/tests/test_route_familiarity_service.py`, `backend/tests/test_route_familiarity_ranking.py`

**Interfaces:**
- Multi-leg routing returns both existing leg results internally so candidate search can derive a signature from the complete via-station path without a new GraphHopper call.
- Combined `/recommend` carries transient signatures from candidate search to ranking; candidate evidence and the candidate-search API contain no signatures or familiarity assessments.
- A private `SearchOutput(evidence, signatures)` carrier is used only by the combined workflow. Staged `search()` persists/returns evidence only. A 409 retry discards the old carrier and recomputes signatures on the one permitted re-search.
- `RouteFamiliarityService.assess_many(driver_id, candidate_signatures, as_of)` performs bounded personal/community history retrieval and in-memory comparisons; one best route per distinct community driver.
- `RecommendationWorkflow` passes transient signatures only to the combined ranking call. `RankingService` evaluates as-of `evidence.request_time`; staged ranking has no signatures and remains familiarity-free. `rank_features` only adds the supplied assessment penalty to final ranking cost after the existing eligibility boundary.

- [ ] Write failing tests for `NO_HISTORY`, personal repeats, multiple routes, community distinct-driver weighting, prior smoothing, unavailable lookup, as-of event-time exclusion, retrieval caps/truncation, one bounded personal plus one bounded community query per search, and configuration validation.
- [ ] Add `ENABLE_ROUTE_FAMILIARITY=false`, 7-day window, maximum penalty 30s, configurable prior/support parameters, and require a 32-byte identity secret when enabled.
- [ ] Build complete-route signatures only when destination and both leg geometries are present; pass signatures transiently through combined `/recommend`, leaving signatures/assessments/geometry out of candidate evidence and staged APIs.
- [ ] Use 50 recent personal-route and 500-route community caps (max 5 routes per driver); expose truncation explicitly. Community values are suppressed below five distinct supporting drivers and never affect rank.
- [ ] Add assessment to eligible features only, keep physical `eta_to_service_complete_s` unchanged, and add the penalty only to `final_cost_s` ordering.
- [ ] Prove feature-off deterministic ranking equals baseline, no-history penalty is zero, physical/safety/eligibility are immutable, faster-by-more-than-max wins, and near ties may change.
- [ ] Rerun affected backend suite and commit `feat: rank with bounded route familiarity`.

### Task 4: Explanation API, metrics, and privacy checks

**Files:**
- Modify: `backend/app/services/ranking/models.py`, `backend/app/api/v1/ranking.py`, `backend/app/core/metrics.py`, `backend/app/services/route_familiarity/service.py`
- Test: `backend/tests/test_route_familiarity_api.py`, `backend/tests/test_metrics.py`, `backend/tests/test_route_familiarity_privacy.py`

**Interfaces:**
- Ranked candidate and selected result expose status, resolution, personal adherence/percentage/trip count, community support/trip/driver counts, confidence, distances, penalty, and selected route cells.
- Raw route signatures/history and driver IDs never appear in recommendation output, logs, or metric labels.

- [ ] Write failing response/schema/auth tests for disabled, unavailable, no-history, and available cases, including resolution 11, derived counts, missing/invalid HMAC rejection, altered driver ID rejection, constant-time comparison helper coverage, and unchanged feature-off auth behavior.
- [ ] Add low-cardinality count/timing metrics for signature, lookup, comparison, no-history, evaluation, and unavailable fallback.
- [ ] Add privacy tests confirming no personal history endpoint, no familiarity in `/ranking/candidates` or staged `/ranking`, ingestion token auth, HMAC driver identity binding, no raw signatures/IDs in output/logs/metrics, and no SQL details in errors.
- [ ] Verify all docs examples use null/explicit absence for unavailable community data rather than fabricated numbers.
- [ ] Run focused API/metrics/privacy tests and commit `feat: expose route familiarity evidence safely`.

### Task 5: Local H3 Resolution-11 explanation overlay

**Files:**
- Create: `backend/app/static/demo/vendor/h3/h3-js.umd.js`
- Create: `backend/app/static/demo/vendor/h3/LICENSE`
- Create or modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`
- Modify: `backend/app/static/demo/index.html`, `backend/app/static/demo/js/tech_view.js`, relevant map/controller module
- Test: `tests/frontend/test_route_familiarity_overlay.mjs`

**Interfaces:**
- Overlay consumes API cell IDs plus API `resolution`; rejects noncanonical cell resolution.
- Overlay is opt-in and owns one removable Leaflet layer, with viewport clipping, animation-frame batches, and explicit visible/total count when capped.

- [ ] Write tests for disabled default, enable/disable, correct res11 boundaries, wrong resolution rejection, safe cell data, large-list cap/cancel behavior, and local asset path.
- [ ] Vendor pinned `h3-js` 4.5.0 UMD bundle and its license under static assets; add no npm runtime dependency and no CDN.
- [ ] Render only returned candidate-route cells, in batches, clipped to map bounds; state the legend and cap in the UI.
- [ ] Rerun Node frontend suite and confirm no `unpkg.com/h3-js`; commit `feat: add local resolution-11 familiarity overlay`.

### Task 6: Benchmark, migration/query evidence, and documentation

**Files:**
- Create: `scripts/benchmark_route_familiarity.py`
- Create: `docs/reports/route-familiarity-benchmark.json` (or generated runtime report plus committed summary)
- Modify: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/OPERATIONS.md`, `docs/PHASE4_ROUTE_FAMILIARITY.md`, `Makefile`
- Test: benchmark smoke tests and docs link checks

**Interfaces:**
- Deterministic generated route-history fixture sizes are recorded in every output.
- Benchmark reports p50/p95 for signature, personal query, community query, similarity, and total evaluation; DB query plans are included when PostgreSQL is available.
- Migration command is explicit and reversible via documented `DROP TABLE` rollback script/steps.

- [ ] Write benchmark smoke test and verify report records stage samples and fixture sizes.
- [ ] Measure at 150, 10k, and 100k route records with warmup/repeated samples and 30-candidate fanout; capture p50/p95 for the actual asyncpg lookup queries and `EXPLAIN (ANALYZE, BUFFERS)` when local PostgreSQL is available; report query caps and whether capping occurred.
- [ ] Optimize only measured bottlenecks; rerun all correctness tests and benchmark comparison.
- [ ] Document V2 replacement rationale, bounded ranking, canonical H3-11, flags, no-history, privacy, overlay, migrations/rollback, and benchmark method.
- [ ] Add Phase4 tracker checkboxes for each of the 24 requested completion dimensions; leave unchecked until fresh evidence passes.
- [ ] Run docs link validation and commit `docs: record route familiarity v2 evidence`.

### Task 7: Full review and verification

**Files:**
- Review entire branch diff from baseline `c80a2b4`.

- [ ] Run Phase 4 unit, frontend, Ruff, API, migration, static-resolution, privacy, and benchmark gates.
- [ ] Dispatch fresh whole-branch reviewer for eligibility/ETA/409 invariants, directionality, H3 policy, privacy, DB async behavior, query scale, tests, overlay, and docs.
- [ ] Fix every blocking/important finding through a fresh implementer; run task-level spec and quality review; rerun full gates.
- [ ] Run `verification-before-completion` on the final committed checkout and ensure `dataset_v1/` is unchanged.
