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
