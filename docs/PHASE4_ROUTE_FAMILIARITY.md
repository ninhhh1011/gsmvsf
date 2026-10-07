# Phase 4 Route Familiarity v2 Tracker

**Branch:** `feature/route-familiarity-v2`  
**Baseline:** `c80a2b4` (Phase 0–3 verified)  
**Status:** In progress. No Phase 4 gates are marked complete until verified from the final checkout.

## Locked behavior and architecture

- [ ] H3 Resolution 11 is the single backend/frontend representation.
- [ ] Ordered, distance-weighted signatures are deterministic and direction-aware.
- [ ] Personal and community evidence uses bounded asyncpg lookups and causal event-time cutoffs.
- [ ] Community evidence is suppressed below the configured distinct-driver threshold and is explanation-only.
- [ ] No history gives zero penalty; feature off performs no familiarity work.
- [ ] Familiarity changes only final ranking cost, with a configured maximum of 30 seconds.
- [ ] Eligibility, physical ETA, queue/service semantics, and the 409 retry are unchanged.
- [ ] Recommendation explanation contains no raw history or driver identifiers.
- [ ] Feature remains disabled unless deployment supplies trusted driver identity.
- [ ] H3 overlay is opt-in, locally vendored, and renders only Resolution 11.

## Verification gates

- [ ] Focused signature and similarity tests pass, including malformed, repeated, reversed, partial, zero, and full overlap routes.
- [ ] Repository, migration/rollback, protected ingestion, event-time, and query-cap tests pass.
- [ ] Personal/community scoring and all ranking invariants pass.
- [ ] API, metrics, privacy, and no-history behavior tests pass.
- [ ] Frontend overlay tests and full Node suite pass; no H3 CDN reference remains.
- [ ] Full backend suite passes with only documented skips.
- [ ] `ruff check backend` passes.
- [ ] H3 resolution architectural scan reports one canonical source and no mixed familiarity resolution.
- [ ] Benchmark reports sample count, warmup, p50/p95, and data sizes for signature, database lookup, similarity, and full evaluation at 150, 10,000, and 100,000 records with 30-candidate fanout.
- [ ] Actual PostgreSQL query plans are recorded when local PostgreSQL is available; unavailable status is explicit otherwise.
- [ ] Documentation links pass; migration rollback is documented.
- [ ] `dataset_v1/` is unchanged.
- [ ] Task spec and quality reviews pass; fresh whole-branch review passes.
- [ ] Final verification is rerun after tracker edits.

## Evidence

Benchmark methodology and the captured local output are recorded in
[the Phase 4 route familiarity benchmark report](reports/phase4-route-familiarity-benchmark.md)
and its [raw JSON plans and measurements](reports/phase4-route-familiarity-benchmark.json).

This section will contain current-checkout commands and outputs after implementation. Design and historical Phase 0–3 evidence do not satisfy Phase 4 gates.
