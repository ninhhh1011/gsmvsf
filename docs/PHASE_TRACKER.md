# Phase 0–3 Production Shape Tracker

**Branch:** `fix/phase-0-3-production-shape`
**Status:** In progress until every locked gate below passes.

## Locked DoD evidence

Commands and results must be recorded from the current checkout. An unchecked item is not complete.

- [x] DoD1: `.github/workflows/ci.yml` has a unit job running ruff, backend pytest, and frontend Node tests; `make test` depends on backend and frontend suites.
- [ ] DoD2: `driver_mode.js` is at most 400 lines (19). Domain modules have no DOM references. **Not complete:** cockpit and drawer HTML is still partly built in `ui/driver_controller.js`; the renderer/bindings extraction is unfinished.
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
| Frontend suite | `node --test tests/frontend/*.mjs` | 69 passed |
| Lint | `ruff check backend` | All checks passed |
| Entrypoint size | Python line-count assertion for `driver_mode.js` | 19 lines |
| Forbidden app references | `rg -n "utcnow|psycopg2|_candidate_service_instance|_global_service|_global_resolver|_global_store" backend/app` | 0 matches |
| H3 / generated graph | `Test-Path graphify-out`; `rg -n "unpkg.com/h3-js" backend/app/static/demo/index.html` | Absent; 0 matches |
| Domain DOM access | `rg -n "innerHTML|document|window" backend/app/static/demo/js/domain` | 0 matches |
| Compose port binds | `rg -n "127.0.0.1:" docker-compose.yml` | All six published ports bind loopback |
| Documentation links | Local Markdown link scan under `docs/` | `[]` |

DoD2 remains red, so the phases are not complete.

## Allowed remaining debts

- No API key on `/recommend`.
- Motorcycle `car_access` coverage.
- Single-node data plane.
- Candidate fanout latency.
