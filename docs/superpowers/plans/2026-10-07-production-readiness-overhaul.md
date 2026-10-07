# Production-Readiness & Architectural Overhaul Implementation Plan

> **Role**: Lead Staff Engineer / Principal Engineer  
> **Status**: Ready for Inline Execution  
> **Target**: Systematic 10/10 across Architecture, Backend, Frontend, Testing, Maintainability, Reliability, Configuration, Documentation, Hygiene, and Production Readiness.

---

## 1. Executive Summary & Reviewer Baseline

The system underwent an external review scoring **6.5/10**, primarily due to:
1. **Dead code**: 5,600+ lines in `route_history` services, dead endpoints, and unexecuted familiarity logic.
2. **Sync/async database mixing**: Mixed usage of synchronous `psycopg2` in API health probes, segment resolver, and error catches alongside production async `asyncpg`.
3. **Global singleton abuse**: Mutable module globals (`_candidate_service_instance`, `_global_service`, `_segment_resolver`, etc.) bypassing clean DI.
4. **Hardcoded Hanoi / VinFast assumptions**: Hardcoded map coordinates `(21.0285, 105.8542)`, hardcoded VinFast models in domain/frontend, and hardcoded PBF paths without environment abstraction.
5. **Monolithic frontend**: `driver_mode.js` is 2,529 lines containing DOM manipulation, energy models, replay orchestration, and direct global `window` references.
6. **Zero meaningful frontend tests & broken test**: `ReferenceError: window is not defined` when running Node test runner against `driver_mode.js`.
7. **Undefined-variable bugs**: Undefined `origin` in `ranking/service.py:143`, undefined `DriverTraceState` in `driver_state_repository.py:282`, undefined `argparse` in `route_history/benchmark.py:306`.

---

## 2. Engineering Backlog

| Priority | Issue / Task | Impact | Files Affected |
| :--- | :--- | :--- | :--- |
| **P0** | Undefined variables (`origin`, `DriverTraceState`, `window`) | Runtime crashes, swallowed NameErrors | `ranking/service.py`, `driver_state_repository.py`, `driver_mode.js` |
| **P0** | Broken frontend test in Node test runner | Test suite failure | `driver_mode.js`, `test_replay_state_machine.mjs` |
| **P0** | Delete `route_history` dead code (5,600+ LOC) | Eliminates technical debt, cleans DB schema | `services/route_history/`, `api/v1/route_history.py`, `tests/` |
| **P1** | Eliminate sync `psycopg2` DB mixing | Event-loop blocking, inconsistent connection lifecycles | `health.py`, `map_match.py`, `realtime.py`, `segment_resolver.py`, `lifespan.py` |
| **P1** | Decompose `driver_mode.js` (2,529 LOC) | Unmaintainable god-module, tight DOM coupling | `static/demo/js/driver_mode.js` -> domain/ui/navigation modules |
| **P1** | Eliminate global singleton abuse | Hard to test, hidden mutable state | `candidate.py`, `map_match.py`, `demand/service.py`, `lifespan.py` |
| **P1** | Environment-driven geo & multi-brand EV configuration | Flexibility for other cities (HCMC, Da Nang) & brands (BYD, Tesla) | `config.py`, `capability.py`, `driver_mode.js`, `sim_mode.js`, `map.js` |
| **P2** | Comprehensive frontend test suite | Production frontend engineering discipline | `tests/frontend/` (add 6 new test modules, 60+ assertions) |
| **P2** | Unified DX, linters, and quality scripts | Reproducible commands for dev/test/lint | `package.json`, `Makefile`, `.env.example`, `ruff.toml` |
| **P2** | Security, input validation, and error boundaries | Graceful degradation, no leaked traces | `health.py`, `map_match.py`, `realtime.py`, `tech_view.js` |
| **P3** | Documentation and Architecture Decisions (ADR) update | Source of truth alignment | `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` |

---

## 3. Phase-by-Phase Implementation Steps

### Phase 2: Elimination of Dead Code (`route_history`)
- **Action**: Completely remove the unused `backend/app/services/route_history` directory (14 files, ~5,600 lines), `backend/app/api/v1/route_history.py`, and corresponding dead tests:
  - `backend/tests/services/test_bayesian_familiarity.py`
  - `backend/tests/services/test_familiarity.py`
  - `backend/tests/services/test_h3_integration.py`
  - `backend/tests/services/test_route_families.py`
  - `backend/tests/services/test_route_history.py`
  - `backend/tests/services/test_route_history_e2e.py`
  - `scripts/generate_hanoi_corridors_h3.py`
- Remove all imports and router inclusions in `backend/app/main.py`.
- Remove dead familiarity calls and fields in `backend/app/services/ranking/service.py` and `models.py`.
- Remove route history settings in `backend/app/config.py` and `docker-compose.yml`.
- Clean frontend references in `backend/app/static/demo/js/sim_mode.js` and `map.js`.
- **Verification**: Run `python -B -m pytest backend/tests` and `git grep -i "route_history"`.

### Phase 3: Unified Async Database Architecture
- **Action**: Eliminate all synchronous `psycopg2` calls in production runtime:
  1. `backend/app/api/v1/health.py`: Replace sync `_database_ready()` and sync `_redis_ready()` with non-blocking async checks utilizing `asyncpg` and `redis.asyncio`.
  2. `backend/app/services/map_matching/segment_resolver.py`: Refactor `RouteConstrainedSegmentResolver` to operate cleanly with async database connection pool / domain exception handling (`SegmentResolverUnavailableError`), keeping compatibility for mocked unit tests.
  3. `backend/app/api/v1/map_match.py` & `realtime.py`: Remove `import psycopg2` and replace `psycopg2.Error` catch blocks with standard domain exception `SegmentResolverUnavailableError` / `DatabaseError`.
  4. Ensure explicit connection lifecycle in `lifespan.py`.
- **Verification**: Zero occurrences of `import psycopg2` in `backend/app/api/v1/` and zero sync database calls in async handlers.

### Phase 4: Elimination of Global Singletons
- **Action**: Refactor service getters:
  1. Replace `_candidate_service_instance` and `_global_service` module globals with FastAPI dependency injection / `app.state` composition.
  2. In `lifespan.py`, instantiate services (`CandidateSearchService`, `DemandService`, `MapMatchingService`, `SegmentResolver`) and attach them to `app.state`.
  3. Provide `Depends(get_candidate_service)` etc. that retrieve from `request.app.state` when running within FastAPI, with a clean factory fallback for isolated testing.
- **Verification**: All backend integration and unit tests pass with zero global state bleed between test cases.

### Phase 5: Removal of Hardcoded Hanoi / VinFast Assumptions
- **Action**:
  1. **City / Geo Config**: Add `city_name`, `map_default_center_lat`, `map_default_center_lng`, `map_default_zoom`, `map_bounding_box` to `backend/app/config.py` with environment variable overrides.
  2. Expose a configuration endpoint `GET /api/v1/config` (or config bootstrap) returning active city and map center.
  3. Update `map.js`, `sim_mode.js`, and `driver_mode.js` to read from the configured map center and default coordinates rather than hardcoding Hanoi.
  4. **Multi-Brand Vehicle Architecture**:
     - Generalize `CANONICAL_MODEL_CATALOG` in `capability.py` to support dynamic registration (`register_vehicle_model`) and multi-brand support (e.g. VinFast, BYD, Tesla, Hyundai, Dat Bike).
     - Decouple frontend vehicle catalog in `driver_mode.js` / `components.js` so it consumes models dynamically from the backend catalog instead of hardcoded `VINFAST_MODEL_SPECS`.
  5. Add tests verifying multi-city and multi-brand vehicle resolution.

### Phase 6 & 7: Frontend Architecture & `driver_mode.js` Decomposition
- **Action**: Decompose `backend/app/static/demo/js/driver_mode.js` (2,529 lines) into clean, single-responsibility modules:
  - `backend/app/static/demo/js/domain/vehicle_model.js`: Vehicle catalog, range estimation, physics SOC depletion, multi-brand specs.
  - `backend/app/static/demo/js/domain/driver_state.js`: State constants, valid state transitions, navigation locking logic.
  - `backend/app/static/demo/js/domain/navigation.js`: Geodesic distance, route slicing, off-route detection, reroute triggers.
  - `backend/app/static/demo/js/domain/station_evaluator.js`: Stations drawer evaluation, filtering (ALL, CHARGING, SWAP, COMPATIBLE), post-trip destination routing.
  - `backend/app/static/demo/js/ui/cockpit_renderer.js`: Rendering Available, Offline, Assigned, Active, and Complete HUD views.
  - `backend/app/static/demo/js/ui/drawer_renderer.js`: Stations drawer list rendering, cost breakdown modal rendering.
  - `backend/app/static/demo/js/ui/map_picker.js`: Drag-and-drop origin and destination picking interactions on Leaflet.
  - `backend/app/static/demo/js/driver_mode.js`: Thin orchestrator (~300 lines) coordinating state, UI, API, and map.
  - Fix `window.driverMode`: Protect with `if (typeof window !== 'undefined')`.
- **Verification**: All existing UI flows work identically in the browser; all modules can be imported and tested in Node.js.

### Phase 8: Comprehensive Automated Frontend Test Suite
- **Action**: Build a robust, high-value automated test suite using Node.js native test runner (`node --test tests/frontend/*.mjs`):
  1. Fix existing test failure in `test_replay_state_machine.mjs`.
  2. Add `tests/frontend/test_vehicle_model.mjs`: Tests specs, range estimation, multi-brand catalog (VinFast, BYD, Tesla), and SOC depletion physics.
  3. Add `tests/frontend/test_driver_state.mjs`: Tests state transitions, navigation locking, trip cancellation, and invalid transition guards.
  4. Add `tests/frontend/test_navigation.mjs`: Tests straightLineDistanceKm, route slicing, off-route threshold detection, and detour calculations.
  5. Add `tests/frontend/test_station_evaluator.mjs`: Tests drawer filtering, candidate compatibility, cost breakdown formatting, and post-trip reroute.
  6. Add `tests/frontend/test_cockpit_renderer.mjs`: Tests UI rendering across states, warning banner generation, badge status.
  7. Add `tests/frontend/test_api_client.mjs`: Tests error wrapping, HTTP status flags, retry/fallback logic.
- **Verification**: `npm test` runs all frontend test suites with 100% pass rate.

### Phase 9 & 10: Correctness Bugs, Error Handling & Reliability
- **Action**:
  1. Fix undefined `origin` bug in `ranking/service.py`.
  2. Fix undefined `DriverTraceState` in `driver_state_repository.py`.
  3. Ensure no swallowed exceptions in services.
  4. Run `ruff check backend` to verify zero undefined variables or lint syntax errors.
  5. Audit error boundaries in API endpoints for structured JSON error responses.

### Phase 11 & 12: Code Quality, DX & Configuration
- **Action**:
  1. Update `.env.example` and `config.py` with full documentation and safe defaults.
  2. Update `package.json` with scripts: `test`, `test:frontend`, `lint`.
  3. Update `Makefile` with targets: `test-frontend`, `test-all`, `lint`.
  4. Ensure zero hardcoded secrets or environment assumptions.

### Phase 13 & 14: Verification & Architectural Review
- **Action**: Run the complete verification battery:
  1. `make validate-data` -> Ensure 152 PASS / 0 FAIL, 22/22 scenarios.
  2. `python -B -m pytest backend/tests` -> 100% pass.
  3. `node --test tests/frontend/*.mjs` -> 100% pass.
  4. `ruff check backend` -> 0 errors.
  5. Update `docs/DECISIONS.md` with ADR for dead code removal and async DB unification.
  6. Produce the final engineering evaluation report.
