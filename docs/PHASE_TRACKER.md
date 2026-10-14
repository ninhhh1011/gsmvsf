# Phase 0–3 Production Shape Tracker

**Branch:** `fix/phase-0-3-production-shape`
**Status:** All locked gates pass locally; whole-branch review passed and final verification is green.

## Locked DoD evidence

Commands and results must be recorded from the current checkout. An unchecked item is not complete.

- [x] DoD1: `.github/workflows/ci.yml` has a unit job running ruff, backend pytest, and frontend Node tests; `make test` depends on backend and frontend suites.
- [x] DoD2: `driver_mode.js` is 2 lines; controller delegates recommendation snippets, cockpit templates, and state-to-view formatting to renderers. `ui/cockpit_bindings.js` applies prepared renderer output and wires semantic events. Controller contains no DOM lookup, listener registration, or presentation markup. Domain modules have no DOM references. Spec and code-quality task reviews passed.
- [x] DoD3: exact banned-pattern scan under `backend/app` returned 0 matches; `datetime.utcnow()` was replaced with `datetime.now(UTC)` in app and tests; the warning filter was removed.
- [x] DoD4: security tests cover missing token (401), invalid token (403), and unset token (503).
- [x] DoD5: metric call sites are present; tests exercise request, route, conflict, and DB fallback counter increments and recommendation observation.
- [x] DoD6: architecture and operations docs describe two API containers on one host and a single-node data plane; local Markdown link scan returned `[]`; no unsupported deployment instructions remain.
- [x] DoD7: `Test-Path graphify-out` returned `False`; H3 unpkg scan returned 0 matches; H3 overlay removed.
- [x] DoD8: app fetches `GET /api/v1/vehicles/catalog`; static vehicle rows contain identifiers only; fallback specs are used if API fetch fails.

## Verified command output

Current checkout evidence:

| Gate | Command | Result |
|---|---|---|
| Backend suite | `$env:DEBUG='false'; python -B -m pytest backend/tests -q --basetemp=runtime/migration/pytest` | 419 passed, 12 skipped |
| Frontend suite | `node --test tests/frontend/*.mjs` | 86 passed after renderer/bindings boundary and controller display-decision extraction |
| Lint | `ruff check backend` | All checks passed |
| Entrypoint size | Python line-count assertion for `driver_mode.js` | 2 lines (at most 400) |
| Forbidden app references | `rg -n "utcnow|psycopg2|_candidate_service_instance|_global_service|_global_resolver|_global_store" backend/app` | 0 matches |
| H3 / generated graph | `Test-Path graphify-out`; `rg -n "unpkg.com/h3-js" backend/app/static/demo/index.html` | `graphify-out` absent; 0 matches |
| Domain DOM access | `rg -n "innerHTML|document|window" backend/app/static/demo/js/domain` | 0 matches across every domain `.js` module |
| Compose port binds | `rg -n "127.0.0.1:" docker-compose.yml` | All six published ports bind loopback |
| Documentation links | Local Markdown link scan under `docs/` | `[]` |

All eight locked DoD items pass based on the command results above and the reviewed frontend responsibility boundaries. Independent whole-branch review passed; the command results above are from the current checkout after the final implementation and tracker edits.

## Allowed remaining debts

- No API key on `/recommend`.
- Motorcycle `car_access` coverage.
- Single-node data plane.
- Candidate fanout latency.

## 2026-10-10 offline comparison and weighting corrections

Implemented on `fix/offline-route-weighting`; this does not start Week 6 infrastructure or activate the deployed opt-in feature. See [current correction evidence](reports/offline-route-weighting-fixes-2026-10-10.md) and ADR-022.

- [x] Corrected directed geometric overlap, neighbor-cell lookup, ordered nonreuse and bounded shared distance.
- [x] Frozen whole-trip offline proposal/time; canonical Driver/API contracts and stale-response guards.
- [x] Additive geometry/start history migration, causal queries and bounded geometric ranking penalty integration.
- [x] Backend-owned interval energy and catalog metadata/provenance; explicit unavailable models.
- [x] Independent review findings reproduced and fixed; complete backend/frontend suites, lint and validator verified.
- [x] Real GraphHopper and disposable PostgreSQL migration/history/API checks; canonical hashes unchanged.
- [ ] Runtime activation/migration of application database and live browser deployment verification (not performed by this code implementation).

Current checks: 561 backend PASS / 12 skipped, 196 frontend PASS, Ruff PASS, validator 152 PASS / 0 FAIL and 22/22 assertions; 63 canonical Dataset files unchanged during verification.

## 2026-10-10 Driver UI panels

User-authorized UI refinements complete: one station drawer with Top-5, compact/expandable mobile cockpit, primary distance/destination ETA/SOC, native analysis disclosure and readable light surfaces. Reroute progress, persistent controls and drawer update state are covered by regressions. See [verification report](reports/driver-ui-panels-2026-10-10.md) and ADR-023.

Checks: frontend 205 PASS; backend 561 PASS / 12 skipped; Ruff PASS; real desktop/mobile browser 39/39 PASS. No Dataset V1 edits, runtime feature activation or Week 6 infrastructure changes. Driving ETA remains an estimate; station-leg fallback and physical calibration limitations are documented.

## 2026-10-12 Energy warning fix and deep project review

Fixed the `VALID_REQUEST` false low-reserve banner through separate backend physical assessment, preserved derived/range-only candidate evidence, rejected nonfinite telemetry, and guarded energy responses after manual/replay updates. Locked station navigation refreshes energy without reranking the selected station. See ADR-024 and [the fix/review report](reports/energy-warning-and-project-review-2026-10-12.md).

Verification: backend 574 PASS / 12 skipped; frontend 215 PASS; Ruff PASS; validator 152 PASS / 0 FAIL and 22/22 assertions; 63 canonical file hashes unchanged; live contract verified on both updated API replicas; desktop/mobile browser 18/18 PASS. Independent review regressions reproduced and fixed. Eight further audit findings remain explicitly open in the report; this is not project-wide bug clearance or Week 6 activation.


## 2026-10-13 Journey ranking and synthetic scale-up

Customer-approved ADR-025 implementation replaces the 30-second personal-only preference with full-completion 80/10/10 scoring, supports optional B and authoritative station plans, and closes the eight findings from the prior energy review. Additional source/browser/load-discovered regressions are tracked in the [current report](reports/journey-ranking-scale-up-2026-10-13.md). Historical milestones above retain their original verification scope.

Current checks: backend 666 PASS / 12 skipped; frontend 247 PASS; Ruff PASS; validator 152 PASS / 0 FAIL and 22/22 assertions; 63 canonical hashes unchanged. Real API eight checks passed and final finite load measured (100 clean; 500/1,000 overloaded). Desktop/mobile browser 32/32 passed, independent review has no remaining blocker within scope. Merged into local main with backend/frontend/Ruff rerun passing; no remote push. This extension does not start Week 6 productionization; replenishment evidence and real-world causal motivations remain explicit limitations.

## 2026-10-14 H3 departure origins — branch only

Owner-authorized ADR-027 replaces static visit-weight rendering with seven-day
paired-guidance departure-origin statistics and an adaptive full-viewport H3 grid.
Every confirmed exit counts; ratios use distinct trips, current guidance and causal
event time. Unknown outcomes remain gray. Legacy histories stay unpaired and intact;
30 new synthetic paired cases support review, not real behavior claims.

Verified: 737 backend PASS / 12 existing skips (main batch plus separate evaluation
process), 267 frontend PASS, Ruff PASS, canonical validator 152/0 and 22/22 scenarios,
63 identical canonical hashes, eight real engine/DB/API verification groups and
14/14 desktop/mobile browser checks. Independent review findings were reproduced
and corrected; final review has no material blocker in scope. Evidence and limits:
[branch report](reports/h3-departure-statistics-2026-10-14.md).

Branch `feat/h3-departure-statistics-7d` remains unmerged; no remote push. Merge only
with explicit owner permission. Existing API containers are retained; review uses
the separate localhost port 8005. This does not start Week 6.

Owner screenshot clarification supersedes the viewport-grid behavior: only
journey-supported cells are rendered, requested H3 resolution is preserved,
and empty history/outage creates no geographic background cells. Correction
validation: 268 frontend PASS and six backend/API contract tests PASS. Backend
ratio/data contracts remain unchanged. The sparse 30-case synthetic fixture is
not citywide behavioral evidence; unpaired history is not assigned departure weights.

Approved branch-only source expansion: all 48,535 in-window old synthetic journeys
now supply gray footprints (eight repeated signature patterns), without departure
weights. Added 360 paired trips on 12 real GraphHopper road corridors, 108 distinct
observed geometries; at resolution 9 the combined sample has 649 cells, 505 with
known ratios and six red cells. This replaces the sparse 30-control-only demo.
No merge/push, Dataset changes, ranking change or Week 6 activation.

Latest expansion verification: 742 backend PASS / 12 existing skips, 269 frontend
PASS, Ruff PASS, canonical validator 152/0 and 22/22, 63 unchanged file hashes,
nine real engine/isolated DB/API groups, 16/16 desktop/mobile checks. Independent
review clear within scope. Query optimization retains five-second statement budget;
no load-capacity or field-accuracy claim. Main remains unchanged.

Branch-only H3 pan/zoom stability fix: retain existing visible polygons and batch
only entering cells; stable subset at the 500 cap. 271 frontend PASS and 18/18
live desktop/mobile checks. Backend/Dataset unchanged; no merge or push.

Latest owner-approved H3 change removes default display cap and loads all evidence
with Leaflet Canvas, independent of viewport. 273 frontend PASS, 18/18 browser
checks, 649 cells retained. Gray background independently traced to external OSM
tile DNS failure; visible notice/canonical host added, network success unverified.
Backend/Dataset unchanged; branch remains unmerged.
