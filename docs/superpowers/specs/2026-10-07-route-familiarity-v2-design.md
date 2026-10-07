# Route Familiarity v2 Design

**Baseline:** Phase 0–3 verified at commit `c80a2b4` on `fix/phase-0-3-production-shape`; Phase 4 branch is `feature/route-familiarity-v2`.

## Purpose and constraints

Route Familiarity v2 compares a GraphHopper recommended route with completed routes previously taken by that driver and with routes from other drivers. It returns a directional, distance-weighted adherence percentage, transparent personal/community evidence, confidence, and an unfamiliarity penalty that can only act as a bounded ranking tie-breaker.

The existing recommendation pipeline remains authoritative for physical route/ETA, queue and service time, feasibility, eligibility, and `CANDIDATE_STATE_CHANGED`/409 behavior. Familiarity is evaluated only for eligible candidates and cannot alter eligibility. `ENABLE_ROUTE_FAMILIARITY` defaults to `false`; when disabled, no route-signature or route-history work is performed and ranking is byte-for-byte behaviorally equivalent on deterministic fixtures.

For the first version, the recommended route is each eligible candidate's complete GraphHopper path from driver to station and station to destination. The route geometry is already computed by the existing multi-leg routing flow. The signature is derived from those returned legs without another routing call or a change to physical ETA semantics.

## Current and historical architecture evidence

The current application is a FastAPI modular monolith. `core/lifespan.py` creates the shared asyncpg pool and request-scoped application services. `CandidateSearchEvidence` is persisted by `SnapshotRepository`; `RecommendationWorkflow` is the sole owner of the one allowed 409 search retry. Candidate eligibility remains in `services/candidate`; ranking reads eligible evidence in `services/ranking`. GraphHopper route geometries are encoded polylines, currently discarded from candidate evidence. Phase 0–3 already has placeholder familiarity fields in `RecommendationResult` but no working history persistence or ranking integration.

The removed v1 tree used an ordered H3-11 signature but also had synchronous DB access, an in-memory inverted index, route-family tables, a hardcoded similarity placeholder, and an unused ranking penalty helper. The factual audit is [ROUTE_FAMILIARITY_V1_AUDIT.md](../../research/ROUTE_FAMILIARITY_V1_AUDIT.md). V2 replaces that removed implementation; it does not restore it.

## Canonical signature and similarity

One backend constant, `H3_ROUTE_RESOLUTION = 11`, is the only resolution source. Pin the existing backend `h3` dependency to its v4 API and vendor matching `h3-js` 4.5.0 locally for display only. The frontend receives the resolution in the API response and rejects cells whose resolution does not match it. No lower-resolution parent, family, or display representation is created.

Decode encoded polylines with finite/range-checked coordinates. Densify deterministically at no more than half the average resolution-11 edge length. Attribute each densified segment's geodesic distance to the H3 cell containing its midpoint; the sum of cell weights must equal measured route distance within 1 mm. Collapse only consecutive duplicate cells while adding weights. Preserve nonconsecutive revisits and traversal order. Reject malformed or zero-length routes at ingestion; a short nonzero route that stays in one cell remains valid. Cap signatures at 2,000 cells.

For signatures A and B, use exact sparse weighted longest common subsequence over ordered H3 cells. A matching pair contributes the smaller of the two cell-distance weights. Index historical cell positions and use a prefix-maximum structure so work scales with matching cell pairs rather than every possible cell pair; precompute each stored route signature once per request and skip pairs with no common cells. This is order-aware and directional: reversing a route cannot score as a full match just because the cell sets are equal. A request has a total budget of 250,000 matching-cell pairs across all candidate/history comparisons. If exhausted, the entire familiarity evaluation is `UNAVAILABLE` with zero penalty (never partial-ranked), and a low-cardinality work-limit metric increments. For the recommended route R and a historical route H:

`shared_route_distance_m(R,H) = weighted_ordered_shared_distance(R,H)`

`adherence(R,H) = clamp(shared_route_distance_m / R.distance_m, 0, 1)`

The user-facing percentage is `adherence * 100`. Similarity never uses unweighted set-intersection count.

## History ingestion and storage

Completed route input is accepted only by the internal, ingestion-token-protected route-history ingestion endpoint. It carries `driver_id`, `trip_id`, completion time, and an encoded polyline; the service stores the ordered resolution-11 signature and measured distance, not raw GPS coordinates or a raw polyline. The shared ingestion token identifies a trusted backend/replay producer. `ENABLE_ROUTE_FAMILIARITY` defaults to false. When enabled, configuration must include a 32-byte-or-longer `ROUTE_FAMILIARITY_IDENTITY_SECRET`, and `/recommend` requires `X-Driver-Identity-Signature`, the lowercase hex HMAC-SHA256 of the exact `context.driver_id` using that secret. A trusted gateway signs the identity after authenticating the end driver; the API rejects missing or invalid signatures with 401/403 before querying history. Staged `/ranking` remains familiarity-free. Feature-off recommendations preserve existing auth behavior.

Validate before decoding: encoded polyline at most 100 KB, at most 20,000 decoded vertices, at most 2,000 signature cells, and measured route length at most 100 km. Exceeding an ingestion limit is a 422; an over-limit recommendation geometry becomes `UNAVAILABLE` and adds no penalty. `(driver_id, trip_id)` is idempotent: identical retry returns the existing record; a conflicting retry is rejected.

Use a new `realtime.route_familiarity_routes` table and the existing asyncpg pool. Store driver/trip identifiers, completion time, measured distance, constant resolution, ordered `text[]` cells, aligned `double precision[]` distance weights, and creation time. Enforce array alignment and nonnegative finite weights in the service. Add a B-tree index for `(driver_id, completed_at DESC)` and a GIN index for cell-overlap candidate lookup. Use an explicit idempotent SQL migration script; do not add application-startup DDL.

Lookback defaults to seven days and is configurable. Every query is event-time bounded by `completed_at <= request_time`; this is required for causal replay. Query personal and community evidence in two bounded asyncpg queries using one union of candidate cells, never one SQL query per candidate. Select at most 50 recent personal routes and at most 5 recent routes for each of at most 100 community drivers (500 total), then choose one best route per distinct community driver. Bounded sentinel rows identify whether any cap actually excluded history; exact-full results do not set `history_truncated`. Route IDs, driver IDs, cells, and full signatures are not logged or used as metric labels. Recommendation responses contain derived scores/counts only, never another driver's route records.

## Personal/community assessment and confidence

For each eligible candidate, personal adherence is the best directional adherence among that driver's retrieved historical routes within the lookback window. `personal_history_trip_count` counts all retrieved personal routes; a personal supporting trip has adherence at least `minimum_support_adherence` (default 0.10), and `personal_trip_count` counts only those supporting trips. Community adherence is the mean of each distinct supporting driver's best adherence, smoothed as `(sum(driver_best_adherence) + prior_mean * prior_strength) / (supporting_driver_count + prior_strength)`. Defaults are `minimum_support_adherence=0.10`, `prior_mean=0.5`, `prior_strength=3`, `minimum_community_drivers=5`, and `confidence_prior_strength=3`. `community_trip_count` counts supporting trips and `community_driver_count` counts distinct supporting drivers. Below five distinct drivers, community adherence and counts are suppressed (null) to reduce route-pattern disclosure. No matching support yields zero adherence and null support counts rather than invented positive values. Community evidence is explanation-only in V2 and never changes ranking; only personal evidence can affect the bounded penalty.

Confidence is personal-evidence confidence only: `personal_history_trip_count / (personal_history_trip_count + confidence_prior_strength)`, clamped to `[0,1]`. All parameters are application settings and validated. `NO_HISTORY` means there are no stored personal routes in the event-time window (not merely no overlapping route); it always yields zero penalty, even if community evidence exists. Thus no-history is neutral, while a driver with sufficient non-overlapping history can receive a bounded unfamiliarity penalty. Missing destination, missing/failed leg geometry, or database/signature failures produce explicit `UNAVAILABLE`, zero penalty, a degraded reason, and a metric; they do not fabricate support. A complete recommendation signature requires both driver-to-station and station-to-destination legs. No extra GraphHopper call is made.

## Ranking integration and invariants

The ranking service receives an optional familiarity evaluator from application lifespan. `rank_features` continues to receive only already-eligible candidates. For each eligible candidate:

`familiarity_penalty_s = 0` when disabled, unavailable, or `NO_HISTORY`; otherwise `min(max_familiarity_penalty_s, max_familiarity_penalty_s * (1 - personal_adherence) * confidence)`.

The default configurable ceiling is 30 seconds. Final ordering uses physical service-completion cost plus this nonnegative penalty. `eta_to_service_complete_s`, route duration, queue wait, service time, and `eta_to_destination_via_station_s` remain physical values. Existing tie-break ordering follows the adjusted total cost. Feature OFF tests compare deterministic ranking results to baseline; additional tests prove that faster-by-more-than-ceiling routes still win, no penalty changes eligibility, and infeasible/unsafe candidates are never ranked.

## API contract

Keep existing response fields backward-compatible. Preserve legacy placeholder fields with their current disabled/neutral defaults; add a structured familiarity explanation with status (`DISABLED`, `UNAVAILABLE`, `NO_HISTORY`, `AVAILABLE`), resolution, personal adherence and percentage, personal supporting-trip count, personal history-route count, community support/adherence, supporting trip and distinct-driver counts (null when suppressed), confidence, recommended/shared route distance, penalty, and `history_truncated`. Include resolution-11 cells only for the selected recommendation; personal/community per-cell support is omitted in V2 to avoid disclosing low-count travel patterns. Familiarity output is added only to the combined `/recommend` response; staged `/ranking/candidates` and `/ranking` remain free of familiarity data because they lack an authenticated user context and transient route signature. No raw route or other driver's ID is returned.

Signatures and assessments remain transient in the combined workflow and are not added to `CandidateSearchEvidence`, the `candidate_searches` table, or `/ranking/candidates` output. A private workflow carrier holds `CandidateSearchEvidence` and the candidate signatures only in memory for one combined recommendation. Staged `search()` persists/returns evidence without signatures. The retry loop discards the prior carrier and recomputes signatures on the single allowed search retry. The combined workflow passes signatures directly into ranking. It evaluates familiarity as-of `CandidateSearchEvidence.request_time`; any later operational `request_time` supplied to the staged ranking API does not shift familiarity because staged ranking does not run familiarity.

## Frontend explanation overlay

Vendor `h3-js` 4.5.0 under `static/demo/vendor/h3/` with its license and no CDN. Add an opt-in overlay in Simulation/Debug Mode, disabled by default. It visualizes only cells returned for the selected recommended route, uses the API resolution field, and includes a legend for supported community/personal counts. Clip rendering to current map bounds, batch Leaflet polygons across animation frames, and cap visible cells with explicit “showing N of M” UI. The underlying signature and API cells remain resolution 11. The overlay is explanatory only; no frontend ranking or H3 scoring is introduced.

## Metrics, performance, and privacy

Add low-cardinality counters/timers for evaluations, `NO_HISTORY`, candidate histories examined, signature generation, similarity, and unavailable fallback. Never label metrics with driver/trip/route IDs.

Benchmark signature generation, personal lookup, community lookup, similarity, and full evaluation on deterministic generated fixtures at multiple history sizes. Record dataset size and p50/p95. Capture `EXPLAIN (ANALYZE, BUFFERS)` for the indexed personal and community lookup when local PostgreSQL is available. Measure before changing query/index strategy; record before/after if optimized.

Security review verifies ingestion token behavior, no raw history read endpoint, no personal route data in logs/metrics/errors, no community driver IDs, safe H3-cell response handling, and no IDOR path beyond the existing recommendation request context. The feature defaults off for environments without a trusted driver identity boundary.

## Decisions and external API reference

ADR-021 records the V2 decision and explicitly supersedes the removed code while retaining ADR-020's architecture cleanup. H3 APIs follow the official [`h3-py`](https://github.com/uber/h3-py) and [`h3-js`](https://github.com/uber/h3-js) 4.x interfaces.
