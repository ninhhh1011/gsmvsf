# Single Driver Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three-tab UI (Driver/Simulation/Debug) with one unified Driver Mode. "Tìm đường" always finds up to 5 stations. Hover/click shows tooltip. H3 is display-only. Synthetic GPS replay. Auto-refresh Top 5.

**Architecture:** DriverModeController owns route, GPS loop, Top 5 result, and navigation lock. Replay.js provides synthetic GPS from GraphHopper geometry. Renderers consume shared Top 5 result. H3 overlay computes cells from route geometry only (no backend familiarity).

**Tech Stack:** Vanilla JS (ES modules), Leaflet, H3.js, FastAPI backend, GraphHopper 11

**Spec:** `docs/superpowers/specs/2026-10-08-driver-only-design.md`

---

## Global Constraints

- Do NOT copy Debug orchestration into Driver
- Do NOT auto-select top 1 station
- Do NOT create fake operational numbers
- Do NOT add new technology without explicit approval
- Do NOT modify `dataset_v1/`
- Do NOT start Week 6 infrastructure
- H3 does NOT call backend familiarity endpoint
- All changes must have regression test evidence

---

## Review Focus

Five failure modes the spec implies but no existing test pins:

1. **Two loops after Pause→Play** — `reset()` sets `isStepInProgress=false` while a request is in-flight; `pause()` increments `playbackToken` but doesn't cancel the sleep; `play()` creates a new loop. Existing test `test_pause_resume` may not verify only one loop remains. **Owning task: Task 2.**
2. **10x speed bypasses rate limit** — The `>= 10` branch uses `Math.max(30, 500/10) = 50ms` delay. At 50ms, the loop can fire ~1200 times/minute before recommendation/route budget. No test verifies total request count at 10x on a real stack. **Owning task: Task 2.**
3. **STALE_OBSERVATION increments index** — `step()` increments `currentIndex` even when the backend rejects the observation. Test `test_stale_observation_rejected` asserts `false` is returned but doesn't assert `currentIndex` is unchanged. **Owning task: Task 2.**
4. **OLD recommendation overwrites NEW station selection** — The probe test shows `lastRecommendedStationId` flips back to OLD after user selects NEW. No unit test covers the revision guard on the `onRecommendation` callback. **Owning task: Task 4.**
5. **Scenario JSON still loaded after "removal"** — `app.js:loadCatalogs()` throws if scenarios.json 404s. The handoff says "gracefully degrade" but no test verifies the app still boots when scenarios.json is absent. **Owning task: Task 8.**

---

## File Map

```
backend/app/static/demo/js/
├── app.js                          [MODIFY] Remove Sim init, scenario load, mode tabs
├── replay.js                       [MODIFY] Stabilize loop/retry/event-time
├── sim_mode.js                    [DELETE]
├── driver_mode.js                 [MODIFY] Add Top 5 result, auto-refresh, H3, synthetic GPS init
├── driver_controller.js            [MODIFY] Shared Top 5 result for list/map/tooltip
├── map.js                         [MODIFY] Station markers from recommend result, H3 overlay
├── api.js                         [KEEP]
├── components.js                   [KEEP]
├── domain/
│   ├── vehicle-catalog.js         [KEEP]
│   ├── vehicle_model.js            [KEEP]
│   ├── driver_state.js             [KEEP]
│   ├── navigation_tracker.js       [KEEP]
│   ├── route-display.js            [KEEP]
│   ├── soc-calculator.js          [KEEP]
│   └── station_evaluator.js        [KEEP]
└── ui/
    ├── cockpit_bindings.js        [MODIFY] Rebind: "Tìm đường", H3 toggle, card clicks
    ├── cockpit_renderer.js         [MODIFY] Remove scenario list, add Top 5 list
    ├── drawer_renderer.js          [MODIFY] Unified station card (list + tooltip)
    ├── driver_recommendation_renderer.js  [KEEP] Panel behavior only
    └── route_familiarity_overlay.js [MODIFY] H3-only, owned by Driver

demo/data/
├── scenarios.json                 [DELETE]
└── trips.json                    [DELETE]
```

---

## Task 0: Baseline Snapshot

**Files:** N/A  
**Test:** N/A

- [ ] **Step 1: Capture git diff**

```bash
git diff --stat HEAD
git diff backend/app/static/demo/js/app.js
git diff backend/app/static/demo/js/replay.js
git diff backend/app/static/demo/js/sim_mode.js
```

- [ ] **Step 2: Run existing tests**

```bash
node --test tests/frontend/test_replay_state_machine.mjs tests/frontend/test_mode_isolation.mjs
npm test 2>&1 | tail -20
```

- [ ] **Step 3: Verify container versions**

```bash
docker compose exec -T api_1 python -c "import backend.app.version; print(backend.app.version.__version__)"
```

- [ ] **Step 4: Save snapshot**

Write `runtime/driver-only-snapshot.md`:
- Current test pass count
- Current git diff summary (files changed, lines changed)
- Container versions
- Any known failing tests

- [ ] **Step 5: Commit snapshot**

```bash
git add runtime/ && git commit -m "docs: capture pre-implementation baseline snapshot"
```

---

## Task 1: Regression Test Contract — Replay Stability

**Files:**
- Create: `tests/frontend/test_replay_loop_ownership.mjs`
- Read: `backend/app/static/demo/js/replay.js`

**Interfaces:**
- Consumes: `TrajectoryReplayController`, `ReplayState` from `replay.js`
- Produces: Tests that assert loop ownership, retry limits, and stale guards

**Tests to write (each in its own `it()` block):**

- [ ] **Step 1: Test — exactly one loop after Pause→Play**

```javascript
it('pause then play leaves exactly one active loop', async () => {
    // Setup: controller with mock API, 10 observations
    // Action: play() → pause() → play()
    // Assert: only one playback token is active (verify _runPlaybackLoop guard)
    // Fail if: two loops both calling step() simultaneously
});
```

- [ ] **Step 2: Test — STALE_OBSERVATION does not increment index**

```javascript
it('STALE_OBSERVATION response does not advance currentIndex', async () => {
    // Setup: mock ingestDriverLocation returns { status: 'STALE_OBSERVATION' }
    // Action: step()
    // Assert: currentIndex === 0, isStepInProgress === false
    // Fail if: index advances on stale response
});
```

- [ ] **Step 3: Test — retry exhausts after exactly 3 attempts**

```javascript
it('transient error retries at most 3 times', async () => {
    // Setup: mock API throws 429 three times, succeeds on 4th
    // Action: play() with speed >= 10
    // Assert: step() was called 4 times (1 original + 3 retries), then state === ERROR
    // Fail if: more than 4 calls, or succeeds after 3 retries
});
```

- [ ] **Step 4: Test — reset() cancels in-flight step**

```javascript
it('reset() cancels in-flight request and sets isStepInProgress=false', async () => {
    // Setup: mock API has 200ms delay
    // Action: step(true) → immediately reset()
    // Assert: generation incremented, isStepInProgress === false, no downstream called
});
```

- [ ] **Step 5: Test — 10x speed has minimum delay guard**

```javascript
it('speed 10x respects minimum delay of 50ms', async () => {
    // Setup: speedMultiplier = 10, 60 observations
    // Action: measure wall time for 10 steps
    // Assert: total time >= 10 * 50ms = 500ms
    // Fail if: 10x completes 10 steps in < 500ms (bypassing production rate)
});
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_replay_loop_ownership.mjs
```

Expected: All FAIL (stubs, no implementation yet) — this is the TDD red phase.

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_replay_loop_ownership.mjs
git commit -m "test: add replay loop ownership regression tests"
```

---

## Task 2: Stabilize Replay.js

**Files:**
- Modify: `backend/app/static/demo/js/replay.js`
- Test: `tests/frontend/test_replay_loop_ownership.mjs`

**Interfaces:**
- Consumes: `api.ingestDriverLocation`, `api.resetDriverLocation`
- Produces: Stable `TrajectoryReplayController` passing all Task 1 tests

**Fixes needed (read `driver-playback-investigation-2026-10-08.md` for line references):**

- [ ] **Step 1: Fix pause() — don't create a new loop token on pause**

Current: `pause()` increments `playbackToken` → new loop could start on `play()`
Fix: Remove `this.playbackToken++` from `pause()`. `play()` should only increment token when transitioning from non-PLAYING state.

```javascript
pause() {
    // Cancel sleep only — do NOT increment token
    if (this._cancelSleep) { this._cancelSleep(); }
    if (this.stepTimer) { clearTimeout(this.stepTimer); this.stepTimer = null; }
    if (this.state === ReplayState.PLAYING) { this.setState(ReplayState.PAUSED); }
}
```

- [ ] **Step 2: Fix reset() — don't set isStepInProgress=false while request is pending**

Current: `reset()` sets `isStepInProgress=false` immediately
Fix: Await any in-flight step or set a "resetting" flag that `step()` checks and exits early.

```javascript
reset() {
    // Increment generation first — this invalidates all pending operations
    this.generation++;
    this.playbackToken++;
    if (this._cancelSleep) { this._cancelSleep(); }
    if (this.stepTimer) { clearTimeout(this.stepTimer); this.stepTimer = null; }
    // isStepInProgress: let in-flight step() finish and self-clean via generation check
    this.currentIndex = 0;
    this.lastAcceptedTimestampMs = 0;
    // ... clear map markers ...
    this.setState(ReplayState.READY);
}
```

- [ ] **Step 3: Fix 10x delay — use production minimum, not test bypass**

Current: `speedMultiplier >= 10` uses `Math.max(30, 500/10) = 50ms`
Fix: Remove the `>= 10` branch. All speeds use the same minimum pacing:

```javascript
const delay = this.speedMultiplier >= 5
    ? Math.max(1500, 800)    // 5x-9x: 800ms
    : this.speedMultiplier >= 2
    ? 1000                    // 2x-4x: 1000ms
    : 1500;                  // 1x: 1500ms
```

- [ ] **Step 4: Fix STALE_OBSERVATION guard — don't advance index**

Current: `step()` increments `currentIndex` regardless of `locResp.status`
Fix: Move `currentIndex++` inside the non-error path, after the stale check:

```javascript
// After stale check throws, add:
if (locResp.status !== 'STALE_OBSERVATION') {
    this.currentIndex = targetIndex + 1;
    this.updateProgressUI();
    if (this.currentIndex >= this.observations.length) {
        this.setState(ReplayState.COMPLETE);
    }
}
```

- [ ] **Step 5: Run tests**

```bash
node --test tests/frontend/test_replay_loop_ownership.mjs
```

Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/static/demo/js/replay.js
git commit -m "fix(replay): stabilize loop ownership, retry limits, STALE guard

- pause() no longer increments playbackToken (one loop invariant)
- reset() invalidates via generation increment (in-flight step self-cleans)
- removed >=10 speed bypass (production minimum 800ms for 5x)
- STALE_OBSERVATION does not advance currentIndex

Refs: driver-playback-investigation-2026-10-08.md"
```

---

## Task 3: Navigation Revision Guards

**Files:**
- Create: `tests/frontend/test_navigation_revision.mjs`
- Modify: `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: `_navigationRevision`, `_recommendationRevision`, `_routeRevision`
- Produces: Tests that stale async responses are discarded

**Tests to write:**

- [ ] **Step 1: Test — select NEW while OLD evaluation pending leg-2**

```javascript
it('selecting NEW station while OLD evaluation pending does not overwrite with OLD response', async () => {
    // Setup: mock API, pending recommend for station A
    // Action: user selects station B (NEW), OLD response arrives
    // Assert: selectedStationId === B (NEW), not A (OLD)
});
```

- [ ] **Step 2: Test — rapid B changes commit only final revision**

```javascript
it('rapid destination changes commit only the final revision', async () => {
    // Setup: mock API with 100ms delay per response
    // Action: change B → B' → B'' in rapid succession (50ms apart)
    // Assert: final route matches B'', not B' or B
});
```

- [ ] **Step 3: Implement revision guards in driver_controller.js**

Read existing code for revision patterns. Add checks in:
- `_onRecommendationResponse()` — check `_recommendationRevision` matches
- `_onRouteResponse()` — check `_routeRevision` matches
- `_onNavigation()` — check `_navigationRevision` matches

- [ ] **Step 4: Run tests**

```bash
node --test tests/frontend/test_navigation_revision.mjs
```

- [ ] **Step 5: Commit**

```bash
git add tests/frontend/test_navigation_revision.mjs backend/app/static/demo/js/driver_controller.js
git commit -m "test+fix: add navigation revision guards to prevent stale response overwrites"
```

---

## Task 4: Merge Recommendation Data Flow

**Files:**
- Create: `tests/frontend/test_top5_result_sharing.mjs`
- Modify: `backend/app/static/demo/js/driver_mode.js`, `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: `api.recommend(A, B, vehicle, soc, top_n=5, requested_service)`
- Produces: `this._top5Result` — shared by list renderer, map markers, tooltip

**Tests to write:**

- [ ] **Step 1: Test — "Tìm đường" always calls recommend, even with sufficient SOC**

```javascript
it('findRoute calls recommend even when SOC >= 50%', async () => {
    // Setup: soc = 80%
    // Action: call findRoute()
    // Assert: api.recommend was called with top_n=5
});
```

- [ ] **Step 2: Test — top 1 is NOT auto-selected after recommend**

```javascript
it('recommend response does not auto-select top 1 station', async () => {
    // Setup: mock recommend returns 3 candidates
    // Action: findRoute()
    // Assert: selectedStationId === null, no "Ghé trạm này" committed
});
```

- [ ] **Step 3: Test — 0/1/5 results handled without fake data**

```javascript
it('recommend with 0 results shows empty state, not fake candidates', async () => {
    // Setup: mock recommend returns empty array
    // Action: findRoute()
    // Assert: top5Result.candidates.length === 0, no fallback data
});
```

- [ ] **Step 4: Test — station with 2 services renders as one card with both services**

```javascript
it('station with BATTERY_SWAP and CHARGING renders as one composite card', async () => {
    // Setup: mock candidate with both service types
    // Action: render station card
    // Assert: one card, both services shown, rank not duplicated
});
```

- [ ] **Step 5: Implement `_top5Result` sharing**

In `DriverModeController`:
```javascript
// Add property
this._top5Result = null;
this._top5Revision = 0;

// In _onRecommendResponse():
if (responseRevision !== this._top5Revision) return;
this._top5Result = result;
this._notifyTop5Updated(result);

// map.js receives result via callback
this.map.updateStationMarkers(this._top5Result.candidates);
```

- [ ] **Step 6: Implement auto-refresh timer**

```javascript
// In init():
this._recommendRefreshInterval = options.recommendRefreshInterval ?? 30000;
this._recommendTimer = null;

startRecommendRefresh() {
    this.stopRecommendRefresh();
    this._recommendTimer = setInterval(
        () => this._refreshRecommendation(),
        this._recommendRefreshInterval
    );
}

stopRecommendRefresh() {
    if (this._recommendTimer) { clearInterval(this._recommendTimer); this._recommendTimer = null; }
}
```

- [ ] **Step 7: Run tests**

```bash
node --test tests/frontend/test_top5_result_sharing.mjs
```

- [ ] **Step 8: Commit**

```bash
git add tests/frontend/test_top5_result_sharing.mjs
git commit -m "test: add Top 5 result sharing and auto-refresh regression tests"
```

```bash
git add backend/app/static/demo/js/driver_mode.js backend/app/static/demo/js/driver_controller.js
git commit -m "feat(driver): add _top5Result sharing, auto-refresh, explicit service request"
```

---

## Task 5: Station Card and Tooltip UX

**Files:**
- Create: `tests/frontend/test_station_tooltip.mjs`
- Modify: `backend/app/static/demo/js/ui/drawer_renderer.js`, `backend/app/static/demo/js/ui/cockpit_renderer.js`, `backend/app/static/demo/js/map.js`

**Interfaces:**
- Consumes: `_top5Result` candidates
- Produces: `renderStationCardHTML(candidate, mode: 'list'|'tooltip')` and `renderStationTooltipHTML(candidate)`

**Tests to write:**

- [ ] **Step 1: Test — hover generates 0 API calls**

```javascript
it('hovering over station card produces 0 API calls', async () => {
    // Setup: controller with 5 candidates
    // Action: simulate 100 hover events on station elements
    // Assert: api call count === 0, SOC unchanged, selectedStationId unchanged
});
```

- [ ] **Step 2: Test — offline station has no "Ghé trạm" button**

```javascript
it('offline station card disables the select button', async () => {
    // Setup: candidate with station_state === 'offline'
    // Action: render card
    // Assert: no "Ghé trạm" button, tooltip shows station offline status
});
```

- [ ] **Step 3: Test — null queue_wait displays "Chưa có dữ liệu"**

```javascript
it('null effective_queue_wait_s displays placeholder, not 0', async () => {
    // Setup: candidate with queue_wait null
    // Action: render card
    // Assert: text contains "Chưa có dữ liệu", not "0 phút"
});
```

- [ ] **Step 4: Implement tooltip rendering**

```javascript
// drawer_renderer.js
export function renderStationTooltipHTML(candidate, stationCatalog) {
    const station = stationCatalog.find(s => s.station_id === candidate.station_id);
    const wait = candidate.features.effective_queue_wait_s !== null
        ? formatDuration(candidate.features.effective_queue_wait_s)
        : 'Chưa có dữ liệu';
    const capacity = candidate.features.available_capacity !== null
        ? candidate.features.available_capacity
        : '—';

    return `
        <div class="station-tooltip" data-station-id="${candidate.station_id}">
            <div class="tooltip-header">
                #${candidate.rank} ${station?.name || candidate.station_id}
                <span class="service-badge">${formatServiceType(candidate.service_type)}</span>
            </div>
            <div class="tooltip-metrics">
                <div>Xe → trạm: ${formatDistance(candidate.features.distance_to_station_m)} · ${formatDuration(candidate.features.eta_to_station_s)}</div>
                <div>Chờ: ${wait} · ${formatServiceType(candidate.service_type)}: ${formatDuration(candidate.features.service_duration_s)}</div>
                <div>Trạm → B: ${formatDistance(candidate.features.distance_station_to_dest_m)} · ${formatDuration(candidate.features.duration_station_to_dest_s)}</div>
                <div>Đi vòng: +${formatDistance(candidate.features.detour_distance_m)}</div>
                <div class="tooltip-total">Tổng: ${formatDuration(candidate.eta_to_destination_via_station_s)}</div>
                <div>Trống: ${capacity} vị trí</div>
            </div>
            <div class="tooltip-freshness">${renderFreshness(candidate.freshness)}</div>
            ${candidate.eligible ? '<button class="btn-ghe-tram">Ghé trạm này</button>' : '<div class="tooltip-ineligible">Không phù hợp</div>'}
        </div>
    `;
}
```

- [ ] **Step 5: Bind tooltip to hover/click in cockpit_bindings.js**

```javascript
// In setStationsDrawer():
each('.station-card[data-station-id]', card => {
    card.addEventListener('mouseenter', event => callbacks.showTooltip(event.currentTarget.dataset.stationId));
    card.addEventListener('mouseleave', () => callbacks.hideTooltip());
    card.addEventListener('click', event => callbacks.selectStationForTooltip(event.currentTarget.dataset.stationId));
});
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_station_tooltip.mjs
```

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_station_tooltip.mjs backend/app/static/demo/js/ui/drawer_renderer.js backend/app/static/demo/js/ui/cockpit_renderer.js backend/app/static/demo/js/ui/cockpit_bindings.js backend/app/static/demo/js/map.js
git commit -m "feat(ui): add station tooltip with full metrics, no API calls on hover"
```

---

## Task 6: H3 Display-Only Layer

**Files:**
- Create: `tests/frontend/test_h3_display.mjs`
- Modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`, `backend/app/static/demo/js/driver_mode.js`

**Interfaces:**
- Consumes: route geometry `[lat, lng][]` from `driver_mode._currentRoute`
- Produces: H3-11 cells rendered as overlay

**Tests to write:**

- [ ] **Step 1: Test — H3 toggle produces 0 API calls**

```javascript
it('H3 toggle does not call any API endpoint', async () => {
    // Setup: controller with active route
    // Action: toggle H3 on → wait 100ms → toggle H3 off
    // Assert: no api.* calls made during toggle
});
```

- [ ] **Step 2: Test — H3 toggle does not change selected station**

```javascript
it('H3 toggle does not modify selectedStationId', async () => {
    // Action: toggle H3
    // Assert: selectedStationId unchanged
});
```

- [ ] **Step 3: Test — route change clears old H3 cells**

```javascript
it('changing route removes previous H3 overlay', async () => {
    // Setup: H3 overlay visible with 50 cells
    // Action: change destination → new route
    // Assert: old cells removed, new cells added
});
```

- [ ] **Step 4: Implement H3 cell computation from geometry**

In `route_familiarity_overlay.js`, add method:

```javascript
computeH3CellsFromGeometry(geometryCoords, resolution = 11) {
    if (!geometryCoords || geometryCoords.length < 2) return [];
    const cells = new Set();
    // Sample along route segments every ~100m
    for (let i = 0; i < geometryCoords.length - 1; i++) {
        const [lat1, lng1] = geometryCoords[i];
        const [lat2, lng2] = geometryCoords[i + 1];
        const segDist = approxDistMeters(lat1, lng1, lat2, lng2);
        const numSamples = Math.max(1, Math.ceil(segDist / 100));
        for (let s = 0; s <= numSamples; s++) {
            const t = s / numSamples;
            const lat = lat1 + (lat2 - lat1) * t;
            const lng = lng1 + (lng2 - lng1) * t;
            const cell = h3.latLngToCell(lat, lng, resolution);
            cells.add(cell);
            if (cells.size >= 500) break; // cap per spec
        }
        if (cells.size >= 500) break;
    }
    return Array.from(cells);
}
```

- [ ] **Step 5: Bind H3 toggle in driver_mode.js**

```javascript
// In init():
this._h3Overlay = new RouteFamiliarityOverlay({ /* ... */ });
this._h3Enabled = false;

// In onToggleH3():
this._h3Enabled = !this._h3Enabled;
if (this._h3Enabled) {
    const cells = this._h3Overlay.computeH3CellsFromGeometry(this._currentRoute?.geometry);
    this._h3Overlay.render(cells);
} else {
    this._h3Overlay.clear();
}
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_h3_display.mjs
```

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_h3_display.mjs backend/app/static/demo/js/ui/route_familiarity_overlay.js backend/app/static/demo/js/driver_mode.js
git commit -m "feat(ui): add H3 display-only overlay from route geometry"
```

---

## Task 7: Transfer Synthetic GPS Init to Driver

**Files:**
- Modify: `backend/app/static/demo/js/driver_mode.js`, `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: GraphHopper route geometry from `api.route()`
- Produces: `replay.loadFromPolyline(geometry)` called on route selection

**Context (from sim_mode.js `runSimulation`):**

Sim currently generates synthetic GPS in `runSimulation()`. This logic moves to `driver_mode.js`.

- [ ] **Step 1: In driver_mode.js, call replay.loadFromPolyline() after route calculation**

```javascript
async _onRouteCalculated(geometry) {
    // geometry: [{lat, lng}, ...] from GraphHopper
    this._currentRoute = { geometry };
    this._routeRevision++;

    // Load synthetic GPS for replay
    if (this.replay) {
        await this.replay.loadFromPolyline(geometry, this._vehicleSpeedKmh ?? 35);
    }

    // Update map
    this.map.renderRoute(geometry);
}
```

- [ ] **Step 2: Bind Play/Pause/Speed controls**

The existing `cockpit_bindings.js` already has `btn-driver-replay-play`, `btn-driver-replay-pause`, `select-replay-speed`. Ensure these call `this.replay.play()`, `this.replay.pause()`, `this.replay.setSpeedMultiplier()`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/static/demo/js/driver_mode.js backend/app/static/demo/js/driver_controller.js
git commit -m "feat(driver): integrate synthetic GPS from GraphHopper geometry into replay"
```

---

## Task 8: Clean app.js Bootstrap

**Files:**
- Modify: `backend/app/static/demo/js/app.js`
- Create: `tests/frontend/test_scenario_removal.mjs`

**Interfaces:**
- Consumes: `fetch('/demo/static/data/scenarios.json')`
- Produces: App boots and initializes without scenarios.json

**Tests to write:**

- [ ] **Step 1: Test — app boots when scenarios.json returns 404**

```javascript
it('app boots successfully when scenarios.json is unavailable', async () => {
    // Setup: mock fetch for scenarios.json to reject
    // Action: new DemoApp().init()
    // Assert: no bootstrap error thrown, driverMode initialized
});
```

- [ ] **Step 2: Test — app does not instantiate SimModeController**

```javascript
it('app does not create SimModeController instance', async () => {
    // Setup: full app init
    // Assert: app.simMode === undefined
});
```

- [ ] **Step 3: Modify app.js — remove SimModeController and scenarios bootstrap**

```javascript
// REMOVE from imports:
import { SimModeController } from './sim_mode.js';

// REMOVE from constructor:
this.simMode = null;

// REMOVE from init():
// SimModeController initialization block (lines ~57-70)

// MODIFY loadCatalogs():
// scenarios and trips: if fetch fails, log warning and continue with empty array
// DO NOT throw — degrade gracefully
```

- [ ] **Step 4: Remove mode tab HTML from index.html**

Search for `id="tab-driver"`, `id="tab-sim"`, `id="tab-debug"` in index.html. Remove sim and debug tab containers.

- [ ] **Step 5: Run tests**

```bash
node --test tests/frontend/test_scenario_removal.mjs
npm test 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add tests/frontend/test_scenario_removal.mjs backend/app/static/demo/js/app.js
git commit -m "refactor(app): remove SimModeController and graceful scenario degradation"
```

---

## Task 9: Delete Removed Files

**Files:**
- Delete: `backend/app/static/demo/js/sim_mode.js`, `backend/app/static/demo/js/tech_view.js`
- Delete: `backend/app/static/demo/data/scenarios.json`, `backend/app/static/demo/data/trips.json`

**Note:** Check `git status` first — some files may already be gone or moved.

- [ ] **Step 1: Verify no remaining imports of deleted files**

```bash
grep -r "sim_mode\|tech_view\|scenarios\.json\|trips\.json" backend/app/static/demo/js/ --include="*.js"
```

Expected: only references in test files or comments.

- [ ] **Step 2: Delete files**

```bash
# Linux/macOS:
rm backend/app/static/demo/js/sim_mode.js
rm backend/app/static/demo/js/tech_view.js
rm demo/data/scenarios.json
rm demo/data/trips.json

# Windows (Git Bash):
rm backend/app/static/demo/js/sim_mode.js
rm backend/app/static/demo/js/tech_view.js
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete sim_mode.js, tech_view.js, scenarios.json, trips.json

These files are removed from the runtime UI per the single Driver Mode design.
Dataset V1 and offline evaluation tests are unaffected."
```

---

## Task 10: Full Regression Suite

**Files:**
- Update: `tests/frontend/test_driver_playback_probe.mjs`
- Create: `tests/frontend/test_complete_journey.mjs`

**Tests from handoff section 10 not yet covered:**

- [ ] **Test 5: Rapid B changes, responses out of order**

Add to `test_navigation_revision.mjs` — already covered in Task 3.

- [ ] **Test 8: Pause/Play/reset during ingest**

Add to `test_replay_loop_ownership.mjs` — already covered in Task 1.

- [ ] **Test 10: Long synthetic route, many reroutes**

```javascript
it('replaying a long route maintains monotonic timestamps', async () => {
    // Setup: route with 500+ synthetic observations
    // Action: play() full route
    // Assert: every observation timestamp > previous timestamp
});
```

- [ ] **Test 13: Drive to B fires COMPLETE exactly once**

```javascript
it('COMPLETE state fires exactly once when reaching destination', async () => {
    // Setup: 10 synthetic observations
    // Action: play() all steps
    // Assert: onStateChange called with COMPLETE exactly once
});
```

- [ ] **Test 14: Scenario removal**

Add to `test_scenario_removal.mjs` — already covered in Task 8.

- [ ] **Run full suite**

```bash
node --test \
  tests/frontend/test_replay_state_machine.mjs \
  tests/frontend/test_mode_isolation.mjs \
  tests/frontend/test_replay_loop_ownership.mjs \
  tests/frontend/test_navigation_revision.mjs \
  tests/frontend/test_top5_result_sharing.mjs \
  tests/frontend/test_station_tooltip.mjs \
  tests/frontend/test_h3_display.mjs \
  tests/frontend/test_scenario_removal.mjs
```

- [ ] **Commit**

```bash
git add tests/frontend/
git commit -m "test: complete regression suite for single Driver Mode"
```

---

## Task 11: E2E Acceptance

**Files:** N/A  
**Requires:** Running backend, GraphHopper, PostgreSQL, Redis (Docker Compose)

- [ ] **Step 1: Restart containers with updated code**

```bash
docker compose down
docker compose build api
docker compose up -d
```

- [ ] **Step 2: Navigate to http://127.0.0.1:8000/demo**

Verify:
- Single Driver Mode UI loads (no tab switcher)
- "[Xe ▼] [SOC] [Chọn A] [Chọn B] [Tìm đường] [H3]" header visible
- No "Sim Mode" or "Debug" references in UI

- [ ] **Step 3: Test "Tìm đường" flow**

1. Select vehicle
2. Set SOC = 80% (sufficient)
3. Pick A and B on map
4. Click "Tìm đường"
5. Verify: Top 5 list appears, map shows station markers, no station auto-selected
6. Verify: network tab shows exactly 2 requests (route + recommend)

- [ ] **Step 4: Test hover tooltip**

1. Hover over station in list
2. Verify: tooltip shows vehicle→station, wait, station→B, detour, total
3. Verify: no new API calls in network tab

- [ ] **Step 5: Test "Ghé trạm" confirmation**

1. Click station → tooltip shown
2. Click "Ghé trạm này"
3. Verify: route changes to A→station→B, navigation locked, Play button enabled

- [ ] **Step 6: Test synthetic GPS replay**

1. Click Play
2. Verify: GPS marker moves along route, SOC decreases
3. Click Pause → Play → verify only one loop active
4. Test 5x and 10x speeds

- [ ] **Step 7: Test H3 toggle**

1. Click H3 button
2. Verify: H3 cells appear along route
3. Click H3 again → cells disappear
4. Verify: no API calls during toggle

- [ ] **Step 8: Test complete journey to B**

1. Start with short route (~20 synthetic points)
2. Play through to end
3. Verify: COMPLETE fires once, Trip Complete card appears
4. Verify: replay controls disabled after COMPLETE

- [ ] **Step 9: Test offline station handling**

1. Find or mock a candidate with `station_state === 'offline'`
2. Verify: card shows offline status, "Ghé trạm" button absent/disabled

- [ ] **Step 10: Run backend test suite**

```bash
cd backend && python -m pytest tests/ -q --tb=short 2>&1 | tail -20
```

- [ ] **Step 11: Run canonical validator**

```bash
make validate-data
```

Expected: 152 PASS / 0 FAIL, 22/22 scenarios (unchanged from baseline)

- [ ] **Step 12: Save acceptance report**

Write `docs/reports/driver-only-acceptance.md` with:
- Test pass counts (frontend + backend)
- Validator result
- Container versions
- Any remaining gaps or known limitations

- [ ] **Step 13: Final commit**

```bash
git add docs/reports/driver-only-acceptance.md
git commit -m "docs: driver-only implementation acceptance report"
```

---

## Test Coverage Summary

| Test File | What It Covers | Handoff Test # |
|---|---|---|
| `test_replay_loop_ownership.mjs` | Loop ownership, STALE guard, retry limit, 10x speed, reset | 8, 9, 11 |
| `test_navigation_revision.mjs` | Revision guards, stale overwrite prevention | 5, 6, 7 |
| `test_top5_result_sharing.mjs` | Auto-refresh, explicit service, no auto-select top 1 | 1, 3 |
| `test_station_tooltip.mjs` | Hover=tooltip, offline eligibility, null handling | 2, 3, 4 |
| `test_h3_display.mjs` | H3 toggle, no API calls, route change clears cells | 12 |
| `test_scenario_removal.mjs` | No scenarios.json load, no Sim instantiation | 14 |
| `test_complete_journey.mjs` | Drive to B, COMPLETE fires once, timestamps monotonic | 10, 13 |

---

## Open Questions (for ADR)

| # | Question | Decision |
|---|---|---|
| OQ1 | Auto-refresh interval | Default 30s; expose as config `recommendRefreshInterval` option |
| OQ2 | Retry on 409 (candidate state changed) | Max 1 retry (existing backend contract); document |
| OQ3 | H3 cell cap | 500 cells, batch 50; if exceeded, show "Showing 500 of N cells" |
| OQ4 | "Đến B rồi sạc" feature | Scope out from this implementation; add later if needed |
