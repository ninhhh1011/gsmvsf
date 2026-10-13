# H3 Hanoi-wide Coverage & Route Deviation Heatmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the H3 grid overlay to be toggled at any time across Hanoi without requiring Origin A or Destination B selection, and highlight driver route deviations in red with distance-based penalty weights when comparing routes.

**Architecture:** 
1. In `route_familiarity_overlay.js`, remove the dependency on active route cells for enabling the H3 toggle; compute and render a baseline Hanoi-wide H3 hexagonal grid on viewport bounds with subtle neutral borders.
2. Introduce a deviation distance metric and color scale ($d \le 50\text{m}$: Green, $50\text{m} < d \le 200\text{m}$: Amber, $200\text{m} < d \le 500\text{m}$: Red, $d > 500\text{m}$: Deep Crimson) that colors cells where the driver veers off the proposed corridor.
3. Wire up `driver_controller.js` to immediately activate Hanoi grid rendering on toggle click, and automatically apply deviation weights when comparing proposed vs actual trajectories.

**Tech Stack:** JavaScript (ES modules), Leaflet 1.9.4, H3-js (local UMD), Node.js test runner (`node --test`), Playwright for E2E capture.

**Spec:** In-chat bounded design approved on branch `feat/h3-deviation-heatmap`.

## Global Constraints
- Do not modify canonical `dataset_v1/`.
- H3 resolution default is 9, with 8 and 10 cycle support.
- Keep rendering smooth (60fps) using viewport culling and batching (`maxCells = 500` visible at a time).
- Popup on deviated cells must explicitly display deviation distance in meters and severity status.

## Review Focus
1. Toggling H3 when no route, origin, or destination exists renders Hanoi grid without error.
2. Panning/zooming around Hanoi dynamically updates the visible H3 cells.
3. Deviated cells beyond 500m turn deep red (`#991b1b`).
4. Overlapping cells along the proposed route stay green (`#10b981`).
5. Switching resolution 9 -> 10 -> 8 re-computes grid cleanly.

---

### Task 1: Hanoi-wide Baseline Grid without A/B Requirement

**Files:**
- Modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`
- Test: `tests/frontend/test_h3_deviation_overlay.mjs`

**Interfaces:**
- Produces: `RouteFamiliarityOverlay.generateHanoiGrid(bounds, resolution)`, `RouteFamiliarityOverlay.renderHanoiBaseline()`
- Consumes: `this.h3.polygonToCells`, Leaflet `map.getBounds()`

- [ ] **Step 1: Write failing frontend unit tests for Hanoi grid generation and unblocked toggle**
- [ ] **Step 2: Run test to verify it fails (`node --test tests/frontend/test_h3_deviation_overlay.mjs`)**
- [ ] **Step 3: Implement `generateHanoiGrid` and update `setEnabled` / `setRoute` so toggle is never locked by missing route**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit `feat: enable Hanoi-wide H3 grid overlay without requiring A/B route`**

---

### Task 2: Deviation Weighting & Red Color Heatmap Algorithm

**Files:**
- Modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`
- Test: `tests/frontend/test_h3_deviation_overlay.mjs`

**Interfaces:**
- Produces: `RouteFamiliarityOverlay.computeDeviationMetadata(cells, proposedCoords)`
- Consumes: `_approxDistMeters`, H3 `cellToLatLng`

- [ ] **Step 1: Write failing frontend unit tests for deviation calculation and red color mapping**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement deviation distance calculation from cell center to proposed route polyline and assign graduated red colors**
- [ ] **Step 4: Update cell popup template to show deviation distance in meters and deviation penalty tier**
- [ ] **Step 5: Run test to verify it passes**
- [ ] **Step 6: Commit `feat: calculate route deviation weights and apply red heatmap styling`**

---

### Task 3: Driver Controller Integration & Interactive Deviation Demonstration

**Files:**
- Modify: `backend/app/static/demo/js/ui/driver_controller.js`
- Modify: `backend/app/static/demo/index.html` (if needed for quick comparison / deviation trigger)
- Test: `tests/frontend/test_h3_deviation_overlay.mjs`

- [ ] **Step 1: Update `driver_controller.js` to trigger `_h3Overlay.renderHanoiBaseline()` whenever H3 is toggled without a route**
- [ ] **Step 2: Ensure route comparison passes actual vs proposed geometry to calculate deviation weights for off-route cells**
- [ ] **Step 3: Verify resolution toggle (9 -> 10 -> 8) updates the city-wide grid immediately**
- [ ] **Step 4: Run frontend test suite (`node --test tests/frontend/*.mjs`)**
- [ ] **Step 5: Commit `feat: wire driver controller to Hanoi H3 grid and deviation analysis`**

---

### Task 4: E2E Playwright Verification & Visual Screenshots Capture

**Files:**
- Create: `scripts/verify_h3_deviation.mjs`
- Test: Execute script against `http://127.0.0.1:3000`

- [ ] **Step 1: Create Playwright script to verify clicking H3 toggle shows grid immediately without selecting A or B**
- [ ] **Step 2: Simulate a trajectory deviating from proposed route and verify cells turn RED**
- [ ] **Step 3: Capture screenshots to artifact directory (`01_hanoi_wide_h3_grid.png`, `02_h3_red_deviation_heatmap.png`)**
- [ ] **Step 4: Review and report results with visual evidence**
