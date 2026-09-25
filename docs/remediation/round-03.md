# Round 03 Remediation Plan & Execution Report — Recommendation Flow & State Correctness

## 1. Metadata & Working Tree
- **Date**: 2026-09-25
- **Branch**: `week5-realtime-api-evaluation`
- **Git HEAD**: `a9e1cfd docs: Update round-02-fixpack.md - FIX-05 complete, all cases passed`
- **Working Tree**: Modified (`backend/app/static/demo/package.json` created for Node ESM test runner, `playwright.config.js` updated to `127.0.0.1` for Windows IPv6 Docker compatibility).
- **Run ID**: `run-20260925-194000`
- **Canonical Dataset Integrity**: 152 PASS / 0 FAIL, 22/22 scenarios PASS (`dataset_v1` untouched).

---

## 2. PHASE 0 — AUDIT LUỒNG HIỆN TẠI

### Task 0.1 — Trace Application Flow
```
User Selection (Trip / Scenario / Vehicle / Telemetry)
    │
    ▼
Session Coordinator (`DemoApp.session` / `generationId`)
    │
    ├── Mode: Driver Mode (`DriverModeController`)
    │     ├── Select Trip (T0001-T0005) -> assigns trip, computes direct route via GraphHopper
    │     ├── Energy State -> from scenario/trip metadata (not hardcoded 85% / 100km / 2km)
    │     └── Start Trip -> transitions to TRIP_ACTIVE, loads trajectory into Replay Controller
    │
    └── Mode: Trajectory Replay (`TrajectoryReplayController`)
          ├── Load Trajectory -> fetches `TRJ0001` - `TRJ0005` observations from backend
          ├── Sequential Step Loop (Max 1 in-flight step, sequential async promise chain)
          │     ├── Read observation at `currentIndex` (timestamp, lat, lng, speed, heading, vehicle)
          │     ├── Ingest GPS to `/api/v1/drivers/{driver_id}/location` (await)
          │     ├── Receive `locResp` (status: MATCHED / AMBIGUOUS / NO_MATCH / RAW_GPS_FALLBACK)
          │     ├── Update position: Matched road segment or raw GPS (honestly reported)
          │     ├── Compute road-network remaining distance to destination (via GraphHopper route)
          │     ├── Call `/api/v1/recommend` (context with observation timestamp, road distance, real SOC)
          │     ├── Render Map layers (raw point, matched point, station route leg1/leg2)
          │     └── Confirm step progress (increment confirmed index only after success)
          │
          └── State Transitions: IDLE -> LOADING -> READY -> PLAYING -> PAUSED -> COMPLETE / ERROR
```

### Task 0.2 — Data Ownership Matrix

| Field | Source of Truth | Owner | Consumer | Invalidation Rule |
| :--- | :--- | :--- | :--- | :--- |
| `session_id` | `DemoApp` (`crypto.randomUUID()`) | App Session | All Controllers, Requests | Invalidate on Reset, Cancel, New Session |
| `generation_id` | Monotonic int per session/action | App / Controller | In-flight request handlers | Incremented on Reset, Pause, Scenario change |
| `driver_id` | Shared Session context | App Session | Replay, DriverMode, TechView, API | Invalidate on Reset, Cancel |
| `vehicle_id` | Catalog (`vehicles.json`) / Scenario | Active Trip / Scenario | Routing, Demand, Ingestion payload | Invalidate on vehicle switch |
| `vehicle_category`| Catalog (`EV_CAR` \| `EV_MOTORBIKE`) | Vehicle Catalog | GraphHopper profile mapper | Invalidate on vehicle switch |
| `trip_id` | Catalog (`trips.json`) | DriverModeController | Replay mapper, Recommend context | Invalidate on trip cancel/switch |
| `trajectory_id` | Curated trip mapping / Scenario | ReplayController | Replay loader | Invalidate on trip/scenario switch |
| `event timestamp` | Observation (`obs.timestamp`) [REPLAY] / Wall Clock [LIVE] | Observation fixture / Clock | Ingestion, Demand, Tech View | Invalidate per observation step |
| `current SOC` | Scenario fixture / Telemetry input | Scenario / Input | Demand detection, HUD | Invalidate on scenario change |
| `estimated remaining range` | Scenario fixture / Vehicle capability | Scenario / Vehicle | Demand detection, HUD | Invalidate on SOC/vehicle change |
| `safety reserve` | Scenario fixture (`safety_reserve_km`) | Scenario / Input | Demand detection | Invalidate on scenario change |
| `destination` | Trip catalog / Scenario | Trip / Scenario | Route, Recommend, Detour | Invalidate on trip/scenario switch |
| `raw position` | Observation coordinates (`obs.lat/lng`) | Observation / Input | Marker, Ingestion, Tech View | Invalidate per step |
| `matched position`| Backend `/location` response | Realtime Service | Matched marker, Context, Tech View| Null when unmatched or ambiguous |
| `road_segment_id` | Backend `/location` response | PostGIS Road Segments | HUD, Tech View | Null when ambiguous or unbuffered |
| `direction` | Backend `/location` response | Map Matcher | Direction arrow, Tech View | UNKNOWN when ambiguous or unbuffered |
| `confidence` | Backend `/location` response | Map Matcher | Tech View quality inspector | Null when unmatched |
| `remaining trip distance` | Backend `/route` road distance | Routing Engine | Demand evaluation, HUD | Recomputed per step; no Haversine |
| `recommendation` | Backend `/recommend` response | Recommendation API | Card, Routes, Tech View | Cleared on error/context change |
| `route geometry` | Backend `/route` encoded polyline | GraphHopper Adapter | Map polylines | Cleared on trip change, error, reset |
| `snapshot timestamp` | Backend snapshot metadata | Backend Ranking | Tech View, Candidate inspector | Fresh on each evaluation |
| `latency/timing` | Backend `timings_ms` response | Backend Pipeline | Timing inspector, indicators | Fresh on each response |

### Task 0.3 — Historical Bug Verification

| # | Bug Description | Status | Evidence in Code |
| :--- | :--- | :--- | :--- |
| 1 | Replay `setInterval` causes request overlap | **CONFIRMED** | `replay.js:157` uses `setInterval(() => this.step(), ...)` while `step()` is async. Also line 93 had `if (this.isPlaying) return;` which made play dysfunctional or race-prone. |
| 2 | `step()` increments index before success | **CONFIRMED** | `replay.js:103` does `this.currentIndex++` before `await this.api.ingestDriverLocation()`. |
| 3 | Callback async not awaited | **CONFIRMED** | `replay.js:144` calls `this.onStep(...)` synchronously without `await`. In `driver_mode.js`, `_onReplayStep` is async. |
| 4 | Pause does not stop in-flight request | **CONFIRMED** | `pause()` only clears interval; in-flight promise resolves and updates UI after pause. |
| 5 | Reset resurrects stale state | **CONFIRMED** | `reset()` does not invalidate generation; in-flight request resolving after reset mutates map and index. |
| 6 | Scenario switch does not invalidate pending request | **CONFIRMED** | `sim_mode.js:runSimulation()` has no cancellation token or generation ID. |
| 7 | `currentIndex` mismatches observation | **CONFIRMED** | Incrementing index before network response causes off-by-one and desync on failure. |
| 8 | Tech View fabricates MATCHED/FORWARD/confidence | **CONFIRMED** | `driver_mode.js:349-356` and `sim_mode.js:377-386` hardcoded `status: 'MATCHED'`, `direction: 'FORWARD'`, `confidence: 1.0`. |
| 9 | Remaining distance uses Haversine as road distance | **CONFIRMED** | `driver_mode.js:255-260` called `haversineKm()` and passed it as `remaining_trip_distance_km` in recommendation payload (line 295). |
| 10 | Replay historical timestamp replaced with wall clock | **CONFIRMED** | `driver_mode.js:291` uses `timestamp: new Date().toISOString()`. |
| 11 | Hardcoded fake SOC/range/reserve defaults | **CONFIRMED** | `driver_mode.js:71-73` hardcodes `85.0%`, `100.0 km`, `2.0 km`. |
| 12 | Recommendation error retains stale routes | **CONFIRMED** | `driver_mode.js:364` catches recommendation error without clearing or marking map routes as stale. |
| 13 | Replay end automatically calls TRIP_COMPLETE | **CONFIRMED** | `driver_mode.js:264` transitions to `TRIP_COMPLETE` purely because replay GPS ran out. |

### Task 0.4 — Baseline Test Verification
- **Node.js Frontend Unit Tests** (`node --test tests/frontend/*.mjs`):
  - Passed: 18 / 18
  - Duration: 161 ms
- **Playwright Browser Tests** (`npx playwright test frontend/tests/demo.spec.js`):
  - Passed: 12 / 12
  - Duration: 47.2 s
- **Backend Demo UI Tests** (`python -m pytest backend/tests/test_demo_ui.py`):
  - Passed: 3 / 3
  - Duration: 0.17 s
- **Dataset Frozen Validator** (`python scripts/validate_frozen_dataset.py`):
  - Passed: 152 / 152
  - Scenario Assertions: 22 / 22 PASS
  - Duration: ~18 s

### Task 0.5 — Exit Gate 0
- [x] Application flow traced.
- [x] Data ownership matrix established.
- [x] All 13 historical issues verified on current HEAD.
- [x] Verified baselines documented.
- **Result**: **EXIT GATE 0 PASS**

---

## 3. IMPLEMENTATION PLAN (Phase 1 -> Phase 4)

### Phase 1: Một Session, Một Clock, Đúng Data Provenance
- **Task 1.1**: Shared Session Context & Monotonic Generation Tracking (`session_id`, `generation_id`, `driver_id`, `vehicle_id`, `vehicle_category`, `trip_id`, `trajectory_id`).
- **Task 1.2**: Distinguish LIVE vs REPLAY modes. Replay uses observation timestamp (`obs.timestamp`); Live uses current timestamp. Never use wall clock for replay decisions.
- **Task 1.3**: SOC / Range / Reserve sourced strictly from Scenario / Vehicle metadata; eliminate hardcoded 85% / 100km / 2km.
- **Task 1.4**: Remaining distance: Use backend routing road distance via `/api/v1/route`. Haversine strictly labeled as straight-line for display only, never passed to backend as road network distance.
- **Task 1.5**: Raw vs Matched honesty: Never synthesize `MATCHED`, `FORWARD`, `1.0`. Only expose backend returned values.
- **Task 1.6**: Tech View data contract standardization: Uniform event payload schema across controllers.

### Phase 2: Replay Sequential Async State Machine
- **Task 2.1**: Remove `setInterval`. Implement sequential async step runner (`_scheduleNextStep()` with `setTimeout`) ensuring strictly max 1 in-flight step.
- **Task 2.2**: Explicit State Machine (`IDLE`, `LOADING`, `READY`, `PLAYING`, `PAUSED`, `ERROR`, `COMPLETE`). Separate playback state from network flight.
- **Task 2.3**: Step Semantics: Immutable context (`generation_id`, `observation`, `index`). Advance confirmed index ONLY after ingestion & evaluation succeed.
- **Task 2.4**: Safe Pause: Cancel scheduled timers, ignore pending completions if generation mismatch.
- **Task 2.5**: Safe Reset: Invalidate generation (`generation_id++`), clear scheduled steps, reset backend driver state, clear map and UI.
- **Task 2.6**: Scenario Switch: Invalidate pending requests immediately, clear/mark old route and recommendation as stale.
- **Task 2.7**: Error & Retry: Categorize transport error, 409, 422, 503, NO_MATCH. Do not advance confirmed progress on failure.

### Phase 3: Thu Gọn UI Về Recommendation Demo
- **Task 3.1**: Focus on core flow: Vehicle/Scenario -> Telemetry -> Replay -> Demand -> Recommendation -> Routes/ETA/Detour -> Tech View. Remove unsupported dispatch/passenger lifecycle.
- **Task 3.2**: Clear UI states (`INITIAL`, `LOADING`, `NO_SERVICE_NEEDED`, `RECOMMENDATION_READY`, `NO_ELIGIBLE_CANDIDATES`, `DEGRADED`, `ERROR`).
- **Task 3.3**: Recommendation card: Station, service type, travel ETA, queue wait, service duration, detour dist/dur, total cost per ranking policy.
- **Task 3.4**: Map layers: Cleanly manage, clear, and invalidate layers on context change.
- **Task 3.5**: Pipeline indicator: Show real stage timings from backend `timings_ms`; remove hardcoded W5 active highlight.
- **Task 3.6**: Responsive check: Usable at 1440x900 and 390x844 viewports.

### Phase 4: Browser Test Matrix & Regression
- **Task 4.1**: Expand Playwright test suite to cover all required deterministic scenarios (Bootstrap, Safe, Advisory, Critical, Charging, Swap, No Eligible, Warmup/Raw, API slow, Timeout, Pause-while-pending, Reset-while-pending, Switch-while-pending, Duplicate clicks, Tech View provenance, Mobile viewport).
- **Task 4.2**: Async assertions (max concurrency = 1, generation checks, stale rejection).
- **Task 4.3**: Live smoke test against running services.
- **Task 4.4**: Regression suite (Node unit tests, Playwright tests, Pytest suite, Dataset validator).
- **Task 4.5**: Code review & diff audit.

---

## 4. PHASE EXECUTION & EXIT GATE VERIFICATIONS

### Phase 1 Execution & Exit Gate 1 Verification
- **Changes**:
  - `backend/app/static/demo/js/replay.js`: Session context binding, historical timestamp provenance (`obs.timestamp` used in replay mode; wall clock only in LIVE mode).
  - `backend/app/static/demo/js/driver_mode.js`: Sourced energy state from scenario fixtures (`soc_pct`, `estimated_range_km`, `safety_reserve_km`) or vehicle specifications, removing hardcoded defaults (85% / 100km / 2km).
  - Removed Haversine as road distance: `remainingTripDistanceKm` is derived from backend GraphHopper `/api/v1/route`. Haversine straight-line distance is computed solely as `straightLineKm` for display and never supplied to the backend as road network distance.
  - Truthful position states: Exposes real `locResp.status`, `matched_position`, `direction`, and `confidence` from the backend without fabricating `MATCHED`, `FORWARD`, or `1.0`.
  - Stale route handling: Clears diversion routes on recommendation failure; direct route is preserved.
  - Tech View contract: Exposes truthful driver location properties (`RAW_GPS_FALLBACK`, `EXPLICIT_COORDINATES`, `NO_MATCH`) without synthetic indicators.
- **Exit Gate 1 Verification**:
  - Session identity unified across all controllers.
  - Live vs Replay timestamps separated.
  - Telemetry parameters truthfully sourced.
  - Road network distance strictly computed via GraphHopper route API.
  - **Result**: **EXIT GATE 1 PASS**

---

### Phase 2 Execution & Exit Gate 2 Verification
- **Changes**:
  - `backend/app/static/demo/js/replay.js`:
    - Replaced buggy `setInterval` with sequential async loop (`while (this.state === ReplayState.PLAYING)` with `await this.step(true)` and `setTimeout`).
    - Explicit state machine: `IDLE`, `LOADING`, `READY`, `PLAYING`, `PAUSED`, `ERROR`, `COMPLETE`.
    - Concurrency lock: `this.isStepInProgress` enforces strictly max 1 in-flight step. Rapid clicks do not spawn concurrent requests.
    - Generation tracking: `this.generation` increments on load/reset/pause; stale in-flight responses dropped immediately.
    - Confirmed progress: `this.currentIndex` advances strictly after backend ingestion and `onStep` callbacks finish.
  - `backend/app/static/demo/js/driver_mode.js`:
    - Synchronized `generation` tracking on trip assignment, start, return, and cancellation.
    - `_onReplayStep` guarded by active trip state (`this.state === DriverState.TRIP_ACTIVE`), preventing stale mutations.
    - Unique element IDs for Driver Mode replay buttons (`#btn-driver-replay-play`, `#btn-driver-replay-pause`, `#btn-driver-replay-step`) eliminating DOM collisions with Simulation Mode replay buttons.
    - Removed auto-transition to `TRIP_COMPLETE` on replay exhaustion; driver controls trip completion via UI.
  - `backend/app/static/demo/js/sim_mode.js`:
    - Added `this.generation` incrementing on scenario switch and `runSimulation`.
    - In-flight responses discarded if generation has changed.
    - Route cleared on error.
- **Exit Gate 2 Verification**:
  - Replay overlap eliminated (max in-flight concurrency = 1 verified via Playwright).
  - State machine transitions verified across all states.
  - Step progress advances only on confirmed success.
  - Reset and Pause cleanly cancel pending responses.
  - **Result**: **EXIT GATE 2 PASS**

---

### Phase 3 Execution & Exit Gate 3 Verification
- **Changes**:
  - `backend/app/static/demo/js/app.js`: Reused `driverMode.replay` instance as `app.replay`, eliminating duplicate controller instantiations and dual event listener bindings.
  - Pipeline indicators: Stages dynamically reflect backend `timings_ms` without hardcoded active highlights.
  - Viewports: Verified responsive layout at desktop (1440x900) and mobile (390x844).
- **Exit Gate 3 Verification**:
  - Focused recommendation workflow operational end-to-end.
  - UI states accurately rendered (`NO_SERVICE_NEEDED`, `RECOMMENDATION_READY`, `NO_ELIGIBLE_CANDIDATES`, `ERROR`).
  - Mobile responsiveness verified via Playwright mobile viewport test.
  - **Result**: **EXIT GATE 3 PASS**

---

### Phase 4 Execution & Exit Gate 4 Verification

#### 1. Targeted Backend Contract Regression Suite Classification
- **Wording Classification**: **`TARGETED BACKEND CONTRACT REGRESSION`**
- **Exact Execution Command**:
  ```bash
  python -m pytest backend/tests/test_shared_state_integration.py backend/tests/test_demo_ui.py backend/tests/test_week5_workflow.py backend/tests/test_week4_api.py
  ```
- **Collection Scope**:
  - The repository's full `backend/tests/` collection contains **388 tests** across historical development milestones (Weeks 1 to 5).
  - Round 03 does not alter backend database schemas, ML ranking weights, or routing engine implementations.
  - The targeted regression suite executes **22 tests** specifically exercising the shared driver state store, demo UI contracts, realtime recommendation workflow, and candidate ranking API consumed by the frontend demo application.
- **Results**: **22 passed, 0 failed** in 14.54s (Exit Code: 0).

#### 2. Detailed Bug #3 Verification & Resolution
- **Bug #3 Definition**: Callback async (`onStep`) not awaited in `TrajectoryReplayController`.
- **Root Cause on HEAD**: In `replay.js:144` (prior to Round 03), `this.onStep(obs, locResp)` was called synchronously without `await`. In `driver_mode.js`, `_onReplayStep` is an async function that computes road network distance via GraphHopper route API and calls `/api/v1/recommend`. By not awaiting `onStep`, the replay step finished before the recommendation was computed, causing race conditions, unhandled promise rejections, and out-of-order map updates.
- **Fix Implementation**: In `replay.js:210`, `await this.onStep({ observation: obs, locResp, currentIndex: targetIndex + 1, generation: currentGen })` was placed inside the sequential promise chain, and confirmed progress is only advanced after `onStep` completes.
- **Test Evidence**:
  - `tests/frontend/test_replay_state_machine.mjs`: `TrajectoryReplayController enforces max 1 step in flight and confirmed progress` verifies `onStep` is awaited before next step executes.
  - `frontend/tests/demo.spec.js`: `D. Replay Step >> replay step sends correct metadata` and `E. Recommendation >> recommendation displays after UI action with charging station and detour`.
- **Status**: **RESOLVED & VERIFIED**.

#### 3. Complete 20 Mandatory Round 03 Cases Matrix

| Case # | Mandatory Case | Test File | Test Name | Key Assertion | Fixture / Live | Status |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **01** | Bootstrap | `frontend/tests/demo.spec.js` | `A. Bootstrap >> page renders without page error`<br>`A. Bootstrap >> controls appear and are usable` | No uncaught errors, `#driver-status-badge` and `#select-driver-trip` visible | Live Backend + Static Data | **PASS** |
| **02** | Safe / No Service | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_tech_view_scenarios.mjs` | `F. No-Service State >> displays no-service correctly`<br>`Scenario 4: No recommendation when vehicle has sufficient range` | `has_recommendation: false`, `reason: SUFFICIENT_SOC_RANGE`, panel visible without crash | Mock Recommendation (`SUFFICIENT_SOC_RANGE`) | **PASS** |
| **03** | Advisory Warning | `frontend/tests/demo.spec.js` | `J. Service Types & Warnings >> advisory warning displays when reserve insufficient` | Banner visible, has class `banner-advisory`, contains `Energy Reserve Low` | Mock Recommendation (`INSUFFICIENT_POST_DESTINATION_RESERVE`) | **PASS** |
| **04** | Critical Warning | `frontend/tests/demo.spec.js` | `J. Service Types & Warnings >> critical energy warning displays when destination not reachable` | Banner visible, has class `banner-critical`, contains `ENERGY CRITICAL` | Mock Recommendation (`DESTINATION_NOT_REACHABLE`) | **PASS** |
| **05** | Charging Recommendation | `frontend/tests/demo.spec.js` | `E. Recommendation >> recommendation displays after UI action with charging station and detour` | HUD contains `S001`, `Charging`, `+0.5 km detour`, `Recommended` | Mock Recommendation (`CHARGING` at `S001`) | **PASS** |
| **06** | Battery Swap Recommendation | `frontend/tests/demo.spec.js` | `J. Service Types & Warnings >> battery swap recommendation displays swap branding and badge` | HUD contains `Battery Swap`, `S003`, `badge-purple` | Mock Recommendation (`BATTERY_SWAP` at `S003`) | **PASS** |
| **07** | No Eligible Candidates | `frontend/tests/demo.spec.js` | `K. No Eligible & Raw GPS >> no eligible candidates renders empty state without fake station` | Recommendation card contains `No Service Needed / No Eligible Stations`, no fake station | Mock Recommendation (`NO_ELIGIBLE_CANDIDATES`, count: 0) | **PASS** |
| **08** | Warm-up / Raw GPS Only | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_tech_view_scenarios.mjs` | `K. No Eligible & Raw GPS >> raw GPS only observation displays honest raw position and no fake match`<br>`Scenario 3: Null, Ambiguous, and No-Match map matching states displayed honestly` | HUD contains `Raw GPS: 21.0500, 105.8000`, does NOT contain `Road: RS001` | Mock Location (`RAW_GPS_FALLBACK`, matched: null) | **PASS** |
| **09** | Slow API | `frontend/tests/demo.spec.js` | `L. Concurrency & State Invalidation >> slow API keeps max 1 active replay step and maintains correct progress` | `maxConcurrentSteps === 1`, `currentIndex` does not jump erratically under rapid clicks | Mock Delayed Location (400ms delay) | **PASS** |
| **10** | HTTP 409 Conflict | `frontend/tests/demo.spec.js` | `G. API Error >> HTTP 409 conflict clears recommendation and does not retain stale route` | `lastRecommendation === null`, HUD does not contain `Recommended`, route cleared | Mock HTTP 409 (`CANDIDATE_STATE_CHANGED`) | **PASS** |
| **11** | HTTP 422 Unprocessable | `frontend/tests/demo.spec.js` | `G. API Error >> HTTP 422 validation error displays error without fake no-service` | HUD does NOT contain `No Service Needed` or `Sufficient Range` | Mock HTTP 422 (Validation Error) | **PASS** |
| **12** | HTTP 503 Engine Unavailable | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_tech_view_scenarios.mjs` | `G. API Error >> displays 503 service unavailable error state without fake success`<br>`Scenario 5: Backend outage and dependency failure isolation` | Error displayed, HUD does NOT contain `Recommended`, no fake success | Mock HTTP 503 (`ENGINE_UNAVAILABLE`) | **PASS** |
| **13** | Network Timeout / Abort | `frontend/tests/demo.spec.js` | `G. API Error >> network timeout abort transitions to error and does not advance progress` | `replay.state === 'ERROR'`, `replay.currentIndex === 0`, `isStepInProgress === false` | Mock Transport Abort (`timedout`) | **PASS** |
| **14** | Pause while Pending | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_replay_state_machine.mjs` | `L. Concurrency & State Invalidation >> pause while pending stops subsequent steps and does not schedule next step`<br>`Pause stops playback loop without losing progress` | `replay.state === 'PAUSED'`, progress index remains fixed at paused step, no future step scheduled | Mock Delayed Location (500ms delay) | **PASS** |
| **15** | Reset while Pending | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_replay_state_machine.mjs` | `L. Concurrency & State Invalidation >> reset while pending invalidates response and prevents stale update`<br>`Reset invalidates generation and drops stale in-flight responses` | Driver badge is `AVAILABLE`, stale position from pending request ignored, generation incremented | Mock Delayed Location (600ms delay) | **PASS** |
| **16** | Switch Scenario while Pending | `frontend/tests/demo.spec.js` | `L. Concurrency & State Invalidation >> switch scenario while pending discards earlier response without updating new scenario` | Stale station `STALE_STATION_A` from scenario 1 is discarded via generation mismatch and never displayed in scenario 3 | Mock Delayed Scenario Candidates (600ms delay) | **PASS** |
| **17** | Duplicate UI Action / Click | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_replay_state_machine.mjs` | `L. Concurrency & State Invalidation >> rapid step clicks enforce max 1 in-flight request without overlap`<br>`TrajectoryReplayController enforces max 1 step in flight and confirmed progress` | `maxConcurrency === 1` despite 3 rapid step clicks | Mock Delayed Location (200ms delay) | **PASS** |
| **18** | Tech View Data Provenance | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_tech_view.mjs` | `H. Tech View >> tech view truthfully displays raw GPS vs matched road segment without fake values`<br>`formatLocationInspector truthfully displays raw GPS vs matched road point and ambiguous states` | Tech drawer contains honest raw GPS coordinates (`21.0285`, `105.8542`), does NOT claim `confidence: 1.000` or hardcoded `FORWARD` | Mock Location (`RAW_GPS_FALLBACK`, matched: null) | **PASS** |
| **19** | Stale Response Ignored (Token Assert) | `frontend/tests/demo.spec.js`<br>`tests/frontend/test_replay_state_machine.mjs` | `L. Concurrency & State Invalidation >> stale in-flight response is dropped via generation token verification`<br>`Reset invalidates generation and drops stale in-flight responses` | `genAfterReset > genBeforeReset`, `currentPos === null`, `lastRecommendation === null` after delayed response resolves | Mock Delayed Location (600ms delay) | **PASS** |
| **20** | Mobile Viewport 390x844 | `frontend/tests/demo.spec.js` | `M. Mobile Viewport >> mobile viewport renders controls and permits navigation` | Map, driver container, and trip dropdown visible at 390x844; Tech View drawer opens and closes correctly | Live Backend + Viewport 390x844 | **PASS** |

#### 4. Summary Test Counts Across Suites

| Test Suite | Total Collected | Passed | Failed | Skipped | Execution Time |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Playwright Browser Tests** (`frontend/tests/demo.spec.js`) | **28** | **28** | **0** | **0** | **2.2 min** |
| **Node.js Frontend Unit Tests** (`tests/frontend/*.mjs`) | **23** | **23** | **0** | **0** | **322 ms** |
| **Targeted Backend Contract Tests** (`backend/tests/test_shared_state_integration.py` etc.) | **22** | **22** | **0** | **0** | **14.54 s** |
| **Dataset V1 Frozen Canonical Validator** (`scripts/validate_frozen_dataset.py`) | **152 assertions**<br>**22 scenarios** | **152**<br>**22** | **0**<br>**0** | **0**<br>**0** | **~18 s** |

- **Evidence Files**:
  - `runtime/remediation/round-03/run-20260925-194000/playwright-summary.json`
  - `runtime/remediation/round-03/run-20260925-194000/node-tests-summary.txt`
  - `runtime/remediation/round-03/run-20260925-194000/backend-pytest.txt`
  - `runtime/remediation/round-03/run-20260925-194000/dataset-validation.json`

---

## 5. CODE REVIEW & DIFF AUDIT

- **Dataset V1 & PBF Files**: Unchanged and read-only.
- **Frontend Code (`backend/app/static/demo/`)**:
  - Replaced buggy `setInterval` with sequential async loop.
  - Implemented `isStepInProgress` concurrency lock and `generation` invalidation tokens.
  - Sourced SOC, range, and reserve from scenario metadata / vehicle specifications.
  - Road distance computed strictly via GraphHopper route API; straight-line distance isolated for display only.
  - Truthful location state representation without synthetic `MATCHED` or `1.0`.
  - Replaced duplicate button IDs with unique `#btn-driver-replay-*` IDs.
- **Over-engineering Verification**: Zero new dependencies, no framework rewrite (React/Vue/Next), no streaming/WebSocket, no Celery/Kafka added.

---

## 6. ROUND 04 DEFERRED TASKS (OUT OF SCOPE FOR ROUND 03)

The following items are explicitly reserved for future milestones (Round 04+):
1. **Dynamic Battery Drain Simulation**: Realtime SOC depletion modeling during vehicle motion (Round 03 intentionally uses scenario telemetry inputs).
2. **Passenger Pickup & Dispatch Workflow**: Full ride-hailing driver dispatch lifecycle (Round 03 focuses strictly on energy routing and recommendation).
3. **Turn-by-Turn Audio & Native Navigation**: TTS navigation prompts and driver turn guidance.
4. **WebSocket / Server-Sent Events Push**: Realtime streaming updates from backend (Round 03 strictly adheres to request-driven HTTP polling).

---

## 7. FINAL ACCEPTANCE CONCLUSION

All **20 mandatory Round 03 cases** are covered by dedicated automated tests with deterministic assertions and zero failures. All 13 historical bugs are confirmed fixed. Data provenance is honest and verified.

**ROUND 03 ACCEPTANCE STATUS**: **`ROUND_03_PASS`**

