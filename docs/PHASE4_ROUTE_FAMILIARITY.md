# Phase 4 Route Familiarity v2 Tracker

**Branch:** `feature/route-familiarity-v2`  
**Baseline:** `c80a2b4` (Phase 0–3 verified)  
**Status:** Implementation gates verified on the current checkout. Whole-branch review and post-tracker verification are pending.

## Locked behavior and architecture

- [x] H3 Resolution 11 is the canonical familiarity representation: `H3_ROUTE_RESOLUTION` is 11, storage enforces 11, and the browser validates returned cells at 11.
- [x] Ordered, distance-weighted signatures are deterministic and direction-aware.
- [x] Personal and community evidence uses bounded asyncpg lookups and causal event-time cutoffs.
- [x] Community evidence is suppressed below the configured distinct-driver threshold and is explanation-only.
- [x] No history gives zero penalty; feature off performs no familiarity work.
- [x] Familiarity changes only final ranking cost, with a configured maximum of 30 seconds.
- [x] Eligibility, physical ETA, queue/service semantics, and the 409 retry are unchanged.
- [x] Recommendation explanation contains no raw route history, driver IDs, trip IDs, or identity signature.
- [x] Feature remains disabled unless deployment supplies trusted driver identity.
- [x] H3 overlay is opt-in, locally vendored, and renders only Resolution 11.

## Verification gates

- [x] Focused signature and similarity tests pass, including malformed, repeated, reversed, partial, zero, and full overlap routes.
- [x] Repository, migration/rollback, protected ingestion, event-time, and query-cap tests pass.
- [x] Personal/community scoring and all ranking invariants pass.
- [x] API, metrics, privacy, and no-history behavior tests pass.
- [x] Frontend overlay tests and full Node suite pass; no H3 CDN reference remains.
- [x] Full backend suite passes with only documented skips.
- [x] `ruff check backend` passes.
- [x] H3 resolution scan reports one backend canonical source, the matching SQL constraint, and Resolution 11 browser validation; no mixed route-familiarity resolution exists.
- [x] Benchmark reports warmup/sample count, p50/p95, and data sizes for signature, database lookup, similarity, and full evaluation at 150, 10,000, and 100,000 records with 30-candidate fanout.
- [x] Actual PostgreSQL query plans are recorded for the available local service; the UUID-named benchmark database was dropped.
- [x] Documentation links pass; migration rollback and post-rollback absence are documented.
- [x] `dataset_v1/` is unchanged.
- [ ] Task spec and quality reviews pass; fresh whole-branch review passes.
- [ ] Final verification is rerun after tracker edits.

## Evidence

Benchmark methodology and the captured local output are recorded in
[the Phase 4 route familiarity benchmark report](reports/phase4-route-familiarity-benchmark.md)
and its [raw JSON plans and measurements](reports/phase4-route-familiarity-benchmark.json).

Current-checkout evidence before whole-branch review:

| Gate | Command / evidence | Result |
|---|---|---|
| CI/local test entry points | `.github/workflows/ci.yml` has a `unit` job for Ruff, backend pytest, and Node tests without GitHub service calls; `Makefile` `test` runs backend and frontend suites. | Present |
| Backend | `$env:DEBUG='false'; python -B -m pytest backend/tests -q --basetemp=runtime/migration/pytest_final` | 466 passed, 12 skipped |
| Frontend | `node --test tests/frontend/*.mjs` | 91 passed, 0 failed |
| Ruff | `ruff check backend` | All checks passed |
| Banned backend references | `rg -n "utcnow|psycopg2|_candidate_service_instance|_global_service|_global_resolver|_global_store" backend/app` | 0 matches |
| Browser-independent domain | `rg -n "innerHTML|document|window" backend/app/static/demo/js/domain` | 0 matches |
| Driver orchestrator size | `python -c "from pathlib import Path; n=sum(1 for _ in open('backend/app/static/demo/js/driver_mode.js')); print(n); assert n<=400, n"` | 2 lines |
| H3 external dependency | `rg -n "unpkg.com/h3-js" backend/app/static/demo/index.html` | 0 matches; local `h3-js` 4.5.0 UMD + Apache license |
| Generated graph | `Test-Path graphify-out` | False |
| Local docs links | Python scan of `docs/**/*.md` relative Markdown links | No broken links |
| Compose config and active containers | `docker compose config --format json`; `docker compose ps` | 5432, 6379, 8989, 8000, 8002, and 3000 all bound to `127.0.0.1` |
| Migration | Rollback, absence check, final apply, presence/count query | Exit 0; absent after rollback; final table present with 0 rows |
| Benchmark | `python -B -m scripts.benchmark_route_familiarity --output docs/reports/phase4-route-familiarity-benchmark.json` | Measured; disposable DB created and dropped; application DB not written; 0 leftover benchmark DBs |
| Protected data | `git diff --quiet c80a2b4 -- dataset_v1` | Unchanged |

The full suite and static gates will be rerun after review and any tracker changes. Design and historical Phase 0–3 evidence do not satisfy Phase 4 gates.
