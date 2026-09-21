# DEMO UI IMPLEMENTATION PLAN (WEEK 5.5)

**Milestone:** Week 5.5 — Demo / Integration UI  
**Repository Root:** `E:\build6week`  
**Base Tag:** `week5-realtime-api-evaluation-complete`  
**Starting Commit:** `f0ec912`  
**Target Completion Tag:** `demo-ui-integration-complete`  
**Status:** In Execution  

---

## 1. Executive Summary & Purpose

The purpose of Week 5.5 is to create an integrated, high-fidelity web demonstration interface for the entire Week 1 through Week 5 pipeline.
The UI:
1. Visualizes the full pipeline: Week 1 (Map Matching / Realtime Driver State) → Week 2 (Demand Detection) → Week 3 (Candidate Search & Routing) → Week 4 (Snapshot-aware Ranking) → Week 5 (Request-driven Realtime Recommendation).
2. Provides a realistic, distraction-free **Driver Mode** for an in-car EV driver workflow (Available → Assigned → On Trip → Trip Complete → Recommended Energy Stop).
3. Provides an information-dense **Simulation / Debug Mode** for mentor evaluation and scenario inspection (custom origin/destination coordinates, vehicle selection, SOC slider, timestamp/scenario selector, candidate table, score breakdown, pipeline latency).
4. Faithfully renders backend truth: **NO BUSINESS LOGIC IN THE FRONTEND**. The frontend collects inputs, calls actual FastAPI endpoints, decodes GraphHopper geometries, and renders exact backend evidence and reason codes.
5. Exposes dynamic snapshot changes (queue spikes, station status changes) and graceful failure/degraded handling (409 `CANDIDATE_STATE_CHANGED`, 503 engine outages, degraded state flags).
6. Preserves the frozen baseline: 347 backend tests pass, canonical Dataset V1.3.1 (152 PASS / 0 FAIL, 22/22 scenarios) remains untouched.

---

## 2. Technical Stack Selection & Justification

| Layer | Selection | Justification |
|---|---|---|
| **Architecture** | Single-Page Application (SPA) served directly by FastAPI | Eliminates heavy node_modules/build dependencies; zero changes to Docker runtime or deployment pipeline; matches Week 1 `debug-map` precedent. |
| **Location** | `backend/app/static/demo/` mounted at `/demo` | Clean separation from internal Week 1 test map; accessible locally at `http://127.0.0.1:8000/demo`. |
| **Map Rendering** | Leaflet 1.9.4 via CDN + CartoDB / OSM tiles | Proven in Week 1 `debug-map`; zero build steps; standard polyline decoding for GraphHopper routes and map-matched traces. |
| **Scripting / Modules** | Modern Vanilla ES6+ Modules (`api.js`, `map.js`, `driver.js`, `sim.js`, `pipeline.js`, `replay.js`) | Clean modular code with zero bundling tools; easily unit-testable via Node's native test runner (`node --test`). |
| **Styling** | Semantic CSS3 Design System with CSS variables | Mobility-focused, clean light/dark theme, responsive across mobile (375px), tablet (768px), and desktop (1280px+). |
| **Data Presets** | Canonical JSON catalogs in `backend/app/static/demo/data/` | Pinned extraction of Dataset V1 stations, vehicles, and real scenarios (`scenario_coverage.csv`) to provide reliable demo presets without hardcoded fake logic. |

---

## 3. Endpoints & API Contract Matrix

| Endpoint | Method | Role in Demo UI |
|---|---|---|
| `/health` & `/ready` | GET | System health indicator (FastAPI, GraphHopper, PostGIS, Redis) |
| `/api/v1/recommend` | POST | Primary orchestration endpoint (returns `RecommendationResult`, ETAs, ranked candidates, stage timings) |
| `/api/v1/candidate-search/evaluate` | POST | Simulation mode candidate inspection (returns all 30 evaluated candidates, ELIGIBLE and INELIGIBLE with reasons) |
| `/api/v1/demand/evaluate` | POST | Demand detection telemetry evaluation (returns `EnergyServiceRequest`, reason codes, safety reserve) |
| `/api/v1/route` | POST | Dynamic route geometry calculation (GraphHopper encoded polyline for origin→destination, driver→station, station→destination) |
| `/api/v1/drivers/{id}/location` | POST / GET | Realtime GPS ingestion and matched state retrieval |
| `/api/v1/debug/trajectories/{id}` | GET | Trajectory replay observations loader from Dataset V1 |

---

## 4. Phased Execution Plan

```text
Phase 0: Repository & API Contract Audit [COMPLETE]
    ↓
Phase 1: Frontend Foundation, Design System & Centralized API Client
    ↓
Phase 2: Leaflet Map Layer & Geometry Engine
    ↓
Phase 3: Driver Mode Core Experience (Offline -> Available -> On Trip -> Complete)
    ↓
Phase 4: Energy Warning Hierarchy & Recommendation Card (Safe, Advisory, Critical)
    ↓
Phase 5: Simulation Mode Controls (A/B map picker, vehicle catalog, SOC, timestamp)
    ↓
Phase 6: Pipeline Latency & Candidate Ranking Debug Panels (W1->W5 breakdown)
    ↓
Phase 7: Trajectory Replay & Dataset Scenario Switcher
    ↓
Phase 8: Failure States, 409 Conflict Handling & System Health
    ↓
Phase 9: Responsive Layout & Accessibility Polish
    ↓
Phase 10: End-to-End Verification, Backend Regression & Freeze
```

---

## 5. Detailed Task Specifications

### PHASE 1: Frontend Foundation & Centralized API Client

#### Task 1.1: Static Asset Directory & Server Integration
- **TASK ID:** W55-01
- **OBJECTIVE:** Establish `backend/app/static/demo/` directory structure, create base `index.html`, and mount `/demo` in FastAPI application.
- **WHY:** Single-origin serving from FastAPI eliminates CORS issues and keeps all demo assets in the repository without external runtime dependencies.
- **INPUTS:** `backend/app/main.py`, `backend/app/config.py`.
- **OUTPUTS:** `backend/app/static/demo/index.html`, route `/demo` in `main.py`.
- **DEPENDENCIES:** FastAPI static file mounting.
- **FILES:** `backend/app/main.py`, `backend/app/static/demo/index.html`.
- **IMPLEMENTATION:** Mount static files directory at `/demo/static` and serve `index.html` at `/demo`.
- **TESTS:** Test HTTP GET `/demo` returns status 200 and HTML content.
- **VISUAL REVIEW:** Load `http://127.0.0.1:8000/demo` in browser.
- **SELF REVIEW:** Ensure no changes to core business endpoints.
- **EXIT GATE:** `/demo` responds with 200 OK.
- **RISKS:** Trailing slash redirects; ensure both `/demo` and `/demo/` work cleanly.

#### Task 1.2: Design Tokens & Styling Shell
- **TASK ID:** W55-02
- **OBJECTIVE:** Build `style.css` defining semantic design tokens, color palette, typography, grid layout, and mode switcher.
- **WHY:** Clean visual hierarchy distinguishing distraction-free Driver Mode from information-dense Simulation Mode.
- **INPUTS:** Green Mobility / VinFast aesthetic (teal, navy, clean white, slate, amber, crimson).
- **OUTPUTS:** `backend/app/static/demo/style.css`.
- **DEPENDENCIES:** W55-01.
- **FILES:** `backend/app/static/demo/style.css`.
- **IMPLEMENTATION:** CSS custom properties for `--status-safe`, `--status-advisory`, `--status-critical`, `--bg-primary`, `--text-primary`, `--card-bg`, font stacks, flex/grid layouts.
- **TESTS:** Verify CSS syntax, token definitions, and responsive media queries (`@media (max-width: 768px)`).
- **VISUAL REVIEW:** Verify clean contrast, badge stylings, and crisp typography.
- **SELF REVIEW:** Ensure no inline styles scattered across components.
- **EXIT GATE:** Stylesheet loads without syntax errors and renders cohesive theme.
- **RISKS:** Excessive specificity; keep classes modular.

#### Task 1.3: Centralized API Client
- **TASK ID:** W55-03
- **OBJECTIVE:** Build `backend/app/static/demo/js/api.js` providing typed async API methods, timeout handling, and structured error propagation.
- **WHY:** Rule 28 prohibits scattered fetch calls and requires structured error handling (409, 422, 503).
- **INPUTS:** Backend OpenAPI schema (`/openapi.json`).
- **OUTPUTS:** `backend/app/static/demo/js/api.js`.
- **DEPENDENCIES:** W55-01.
- **FILES:** `backend/app/static/demo/js/api.js`.
- **IMPLEMENTATION:** Implement `ApiClient` with:
  - `checkHealth()`, `checkReadiness()`
  - `recommend(payload)`
  - `evaluateAndSearch(payload)`
  - `evaluateDemand(payload)`
  - `computeRoute(origin, destination, profile)`
  - `ingestLocation(driverId, obs)`
  - `getDriverLocation(driverId)`
  - `getTrajectory(trajectoryId)`
  - Error class `ApiError` with `status`, `code`, `detail`, `isConflict`.
- **TESTS:** Node.js unit tests in `tests/frontend/test_api_client.js` mocking HTTP fetch.
- **VISUAL REVIEW:** Verify console logs format network errors meaningfully.
- **SELF REVIEW:** Verify zero frontend business logic; all results passed through.
- **EXIT GATE:** Node unit tests pass.
- **RISKS:** Network timeout handling; provide 10s default abort signal.

---

### PHASE 2: Map & Geometry Engine

#### Task 2.1: Leaflet Map & Polyline Engine
- **TASK ID:** W55-04
- **OBJECTIVE:** Implement `backend/app/static/demo/js/map.js` supporting layer groups, custom markers, route polylines, and bounds fitting.
- **WHY:** Map must visualize real GraphHopper geometries, driver position, matched position, and station alternatives.
- **INPUTS:** Leaflet 1.9.4, CartoDB Positron / OSM tiles.
- **OUTPUTS:** `backend/app/static/demo/js/map.js`.
- **DEPENDENCIES:** W55-01, W55-02.
- **FILES:** `backend/app/static/demo/js/map.js`.
- **IMPLEMENTATION:**
  - Encoded polyline decoder (Google 5-decimal algorithm).
  - Custom SVG icons: Driver car (blue/arrow), Driver matched (green ring), Destination pin (red/flag), Station (green plug for charge, purple swap for battery swap), Ineligible station (gray dot).
  - Layers: `directRouteLayer`, `recommendationRouteLayer`, `candidateStationsLayer`, `driverLayer`.
  - Methods: `renderDriver(rawPos, matchedPos, heading)`, `renderTrip(origin, dest, polyline)`, `renderRecommendationRoute(poly1, poly2)`, `renderCandidateMarkers(candidates, onSelect)`.
- **TESTS:** Node unit test for polyline decoding with known test vectors.
- **VISUAL REVIEW:** Check marker visibility, route contrast, and zoom stability.
- **SELF REVIEW:** Ensure no fake straight routes are drawn.
- **EXIT GATE:** Route geometry decodes and plots accurately in Hanoi coordinates.
- **RISKS:** Coordinate ordering (`[lat, lon]` vs GeoJSON `[lon, lat]`).

---

### PHASE 3 & 4: Driver Mode, Energy Warnings & Recommendation

#### Task 3.1: Driver Mode State Machine & Workflow
- **TASK ID:** W55-05
- **OBJECTIVE:** Implement `backend/app/static/demo/js/driver_mode.js` managing Driver states (`OFFLINE`, `AVAILABLE`, `TRIP_ASSIGNED`, `TO_PICKUP`, `ON_TRIP`, `TRIP_COMPLETE`).
- **WHY:** Minimal demo state model satisfying Section 5 & 6 without inventing unsupported dispatch logic.
- **INPUTS:** Preloaded trips from Dataset V1 (`dataset_v1/trips/trips.csv`).
- **OUTPUTS:** `backend/app/static/demo/js/driver_mode.js`.
- **DEPENDENCIES:** W55-03, W55-04.
- **FILES:** `backend/app/static/demo/js/driver_mode.js`.
- **IMPLEMENTATION:**
  - On AVAILABLE: show active driver card with "Accept Trip" from curated list.
  - On TRIP_ASSIGNED / TO_PICKUP: simulate arrival at pickup.
  - On ON_TRIP: render primary navigation card (destination, distance remaining, ETA, vehicle model, SOC, estimated range, energy status banner). No giant ranking tables while moving!
  - On TRIP_COMPLETE: trigger energy recommendation check and show prominent recommendation card if service required.
- **TESTS:** Unit test state transition sequences.
- **VISUAL REVIEW:** Verify uncluttered, driver-friendly layout.
- **SELF REVIEW:** Confirm no multiple passenger trips allowed.
- **EXIT GATE:** State transitions work sequentially without UI jumps.
- **RISKS:** Out-of-order state triggers; lock transitions during active API requests.

#### Task 4.1: Energy Warning Hierarchy & Recommendation Card
- **TASK ID:** W55-06
- **OBJECTIVE:** Implement energy warning banner and detailed recommendation card based on backend Week 2 & Week 4/5 outputs.
- **WHY:** Expose exact backend energy reason codes and full recommendation evidence (Section 8, 9, 10).
- **INPUTS:** `RecommendationResult`, `EnergyServiceRequest`.
- **OUTPUTS:** UI rendering functions for warning banners and recommendation cards.
- **DEPENDENCIES:** W55-05.
- **FILES:** `backend/app/static/demo/js/components.js`.
- **IMPLEMENTATION:**
  - SAFE banner: Neutral/green status, no modal.
  - ADVISORY banner: `INSUFFICIENT_POST_DESTINATION_RESERVE` ("Energy reserve low. You can complete the current trip. Energy service is recommended after drop-off.") Non-blocking.
  - CRITICAL banner: `DESTINATION_NOT_REACHABLE` ("ENERGY CRITICAL. Estimated range may not be sufficient to complete the current trip. Energy service recommendation available.") High-priority warning icon.
  - Recommendation Card:
    - Station ID & Service Type (CHARGING vs BATTERY_SWAP distinct tags).
    - ETA to station, ETA to service start, ETA to complete.
    - Queue wait (observed vs policy assumption), service duration, detour.
    - Snapshot freshness & degraded indicators.
    - Cost breakdown / ranking explanation.
- **TESTS:** Unit test warning level mapping against all ReasonCode values.
- **VISUAL REVIEW:** Inspect visual styling for SAFE, ADVISORY, CRITICAL, and Recommendation Card.
- **SELF REVIEW:** Confirm no frontend calculation of range or cost.
- **EXIT GATE:** Warning banners and recommendation card display exact backend data.
- **RISKS:** Misclassification of reason codes; strictly follow Section 8 table.

---

### PHASE 5 & 6: Simulation Mode, Pipeline Debug & Candidate Panels

#### Task 5.1: Simulation Mode Controls & Presets
- **TASK ID:** W55-07
- **OBJECTIVE:** Build `backend/app/static/demo/js/sim_mode.js` with A/B coordinate pickers, vehicle selector, SOC slider, timestamp picker, and preset scenarios.
- **WHY:** Allow mentor demonstrations and controlled exploration of dynamic edge cases (Section 13).
- **INPUTS:** Stations, vehicles, scenarios metadata.
- **OUTPUTS:** `backend/app/static/demo/js/sim_mode.js`.
- **DEPENDENCIES:** W55-03, W55-04.
- **FILES:** `backend/app/static/demo/js/sim_mode.js`.
- **IMPLEMENTATION:**
  - Origin / Destination: inputs + map click capture.
  - Vehicle dropdown (VF_3, VF_5, VF_6, EVO, FELIZ_II).
  - SOC slider (0% to 100%) with live value display.
  - Service Intent: AUTO, CHARGING, BATTERY_SWAP, ANY.
  - Snapshot timestamp input / scenario quick-selector (NORMAL, RUSH_HOUR, HIGH_QUEUE, STATION_OFFLINE).
  - "RUN SIMULATION" button triggering parallel candidate evaluate and recommend calls.
- **TESTS:** Verify form data extraction and payload formatting.
- **VISUAL REVIEW:** Test map clicking for origin/destination coordinate selection.
- **SELF REVIEW:** Simulation only supplies inputs; backend does all reasoning.
- **EXIT GATE:** Form triggers API calls and displays responses.
- **RISKS:** Invalid coordinate inputs outside Hanoi bounding box.

#### Task 6.1: Pipeline Latency & Candidate Debug Panels
- **TASK ID:** W55-08
- **OBJECTIVE:** Render multi-stage pipeline card (W1 Map Matching, W2 Demand, W3 Candidate Search, W4 Ranking, W5 Total) and Candidate lists (ELIGIBLE vs INELIGIBLE).
- **WHY:** Section 14, 16, 17 require transparent latency and candidate eligibility breakdown.
- **INPUTS:** `RecommendationResult.timings_ms`, `CandidateSearchResult.candidates`.
- **OUTPUTS:** Pipeline latency bar, Candidate accordion table.
- **DEPENDENCIES:** W55-07.
- **FILES:** `backend/app/static/demo/js/components.js`.
- **IMPLEMENTATION:**
  - Pipeline card showing actual latencies from `timings_ms` (location, demand, candidate_search, ranking, total).
  - Candidate panel:
    - ELIGIBLE: rank, station_id, service_type, travel duration, queue wait, service time, detour, available capacity, final cost.
    - INELIGIBLE: station_id, service_type, reason (INCOMPATIBLE, OFFLINE, NO_SWAP_BATTERY, FULL, UNREACHABLE, etc.).
  - Ranking explanation card showing formula `TOTAL_SERVICE_COMPLETION_V1` components.
- **TESTS:** Unit test candidate grouping into eligible and ineligible.
- **VISUAL REVIEW:** Verify dense, readable layout in Simulation Mode.
- **SELF REVIEW:** Ineligible candidates are never displayed as ranked.
- **EXIT GATE:** Real stage timings and candidate groups render accurately.
- **RISKS:** Long candidate lists causing layout overflow; implement scrollable container.

---

### PHASE 7 & 8: Replay, Failure UX & Health

#### Task 7.1: Trajectory Replay & Scenario Controls
- **TASK ID:** W55-09
- **OBJECTIVE:** Implement `backend/app/static/demo/js/replay.js` to replay Dataset V1 trajectories with Play/Pause/Step and speed controls (1x, 5x, 10x, 25x, 50x).
- **WHY:** Section 22 & 23 require request-driven trajectory replay calling the backend on each step.
- **INPUTS:** `/api/v1/debug/trajectories/{id}`.
- **OUTPUTS:** `backend/app/static/demo/js/replay.js`.
- **DEPENDENCIES:** W55-03, W55-04.
- **FILES:** `backend/app/static/demo/js/replay.js`.
- **IMPLEMENTATION:**
  - Load trajectory points from API.
  - Replay loop with configurable interval (speed multipliers).
  - Ingest GPS to `/api/v1/drivers/{id}/location`.
  - Update driver raw and matched markers on map.
  - Trigger `/api/v1/recommend` on matched events or step.
- **TESTS:** Test replay loop start/pause/step/reset.
- **VISUAL REVIEW:** Watch driver marker move smoothly along Hanoi road network.
- **SELF REVIEW:** Ensure replay is strictly client-driven; no server push daemon.
- **EXIT GATE:** Replay ingests observations and updates map/recommendation live.
- **RISKS:** Race conditions when clicking Step rapidly; queue requests sequentially.

#### Task 8.1: Failure States, 409 Conflict Handling & System Health
- **TASK ID:** W55-10
- **OBJECTIVE:** Implement robust error banners, 409 `CANDIDATE_STATE_CHANGED` handling, and compact backend health monitor.
- **WHY:** Section 19, 20, 21 require structured error UX instead of generic error messages.
- **INPUTS:** HTTP error statuses (409, 422, 503), `/health`, `/ready`.
- **OUTPUTS:** Error display modal/banner, auto/manual retry flow, status indicators.
- **DEPENDENCIES:** W55-03.
- **FILES:** `backend/app/static/demo/js/components.js`.
- **IMPLEMENTATION:**
  - 409 `CANDIDATE_STATE_CHANGED`: Display banner with changed stations list and "Refresh Recommendation" action.
  - 422 `LOCATION_UNAVAILABLE`: Specific warning banner.
  - 503 `ENGINE_UNAVAILABLE`: GraphHopper / Database outage warning.
  - Degraded badge: Shown when `degraded: true` in recommendation result.
  - System Health Widget: Polls `/ready` and `/health` every 15s in Simulation Mode (FastAPI, GraphHopper, PostGIS, Redis badges).
- **TESTS:** Unit test error parser mapping HTTP responses to UI states.
- **VISUAL REVIEW:** Verify health pill colors (green/red) and error alert banners.
- **SELF REVIEW:** No masking of backend outages.
- **EXIT GATE:** Structured error states display correctly when triggered.
- **RISKS:** Health polling overwhelming server; throttle to 15s.

---

### PHASE 9 & 10: Polish, E2E Verification & Freeze

#### Task 9.1: Responsive & Visual Design Polish
- **TASK ID:** W55-11
- **OBJECTIVE:** Audit and refine layout across mobile (375px), tablet (768px), and desktop (1280px+).
- **WHY:** Section 25 requires mobile/tablet-first driver mode and responsive simulation mode.
- **INPUTS:** Viewport dimensions.
- **OUTPUTS:** Polished responsive CSS rules and layout adjustments.
- **DEPENDENCIES:** W55-01 through W55-10.
- **FILES:** `backend/app/static/demo/style.css`.
- **IMPLEMENTATION:** Media queries, touch-friendly tap targets (minimum 44px), collapsible sidebars on mobile, responsive map container height.
- **TESTS:** CSS linting and visual inspection at 375px, 768px, 1280px.
- **VISUAL REVIEW:** Verify full layout readability across device sizes.
- **SELF REVIEW:** Driver mode remains uncluttered on small screens.
- **EXIT GATE:** Responsive layout PASS without horizontal scroll defects.
- **RISKS:** Leaflet resize glitches; trigger `map.invalidateSize()` on tab/viewport change.

#### Task 10.1: End-to-End Scenarios & Backend Regression Verification
- **TASK ID:** W55-12
- **OBJECTIVE:** Execute all 8 required demo scenarios against live backend stack, verify backend test suite (347 tests), canonical dataset validation (152 PASS), and freeze repo.
- **WHY:** Ensure zero regressions and complete verification before tag creation.
- **INPUTS:** Live Docker containers (`ev_api`, `ev_db`, `ev_graphhopper`, `ev_redis`).
- **OUTPUTS:** Final audit report and git tag `demo-ui-integration-complete`.
- **DEPENDENCIES:** All previous tasks.
- **FILES:** `docs/WEEK_5_5_DEMO_REPORT.md`.
- **IMPLEMENTATION:**
  - Run Scenario 1: Driver trip safe
  - Run Scenario 2: Destination reachable but reserve insufficient (Advisory)
  - Run Scenario 3: Destination not reachable (Critical)
  - Run Scenario 4: Charge recommendation
  - Run Scenario 5: Swap recommendation
  - Run Scenario 6: Queue snapshot changes recommendation (S022 at 07:42 -> S016 at 07:52)
  - Run Scenario 7: Station OFFLINE (S001 at 08:00)
  - Run Scenario 8: Simulation custom A -> B
  - Run backend pytest (347 tests)
  - Run dataset validation (152 checks, 22 scenarios)
  - Commit explicit files and create tag `demo-ui-integration-complete`.
- **TESTS:** Pytest suite, dataset validator, live E2E script.
- **VISUAL REVIEW:** Full demo walk-through.
- **SELF REVIEW:** Working tree clean, zero unauthorized modifications to `dataset_v1/`.
- **EXIT GATE:** All gates pass; freeze tag created.
- **RISKS:** Dirty working tree; verify `git status --short`.

---

## 6. Execution Ledger & Milestones

| Phase | Tasks | Status |
|---|---|---|
| Phase 0 | Audit & Research | COMPLETE |
| Phase 1 | W55-01, W55-02, W55-03 | READY |
| Phase 2 | W55-04 | READY |
| Phase 3 & 4 | W55-05, W55-06 | READY |
| Phase 5 & 6 | W55-07, W55-08 | READY |
| Phase 7 & 8 | W55-09, W55-10 | READY |
| Phase 9 & 10 | W55-11, W55-12 | READY |
