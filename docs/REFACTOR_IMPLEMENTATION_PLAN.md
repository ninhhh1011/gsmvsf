# Refactor Implementation Plan
**Created:** 2026-09-23
**Phases:** Architecture & Repository Cleanup → Truthful E2E Demo Pipeline → Product-Quality Demo UI

---

## 1. REPOSITORY AUDIT SUMMARY

### 1.1 Architecture
```
Frontend (Vanilla JS, Leaflet)
  ↓ HTTP
FastAPI (backend/app/)
  ↓ httpx     ↓ psycopg2  ↓ redis-py
GraphHopper  PostgreSQL/  Redis
  (11.0 JAR)   PostGIS
```

### 1.2 Runtime Truth
| Concern | Source | Method |
|---------|--------|--------|
| Routing engine | GraphHopper 11.0 | httpx → POST /route |
| Map matching | GraphHopper 11.0 | httpx → POST /match |
| Driver state | Redis | redis-py |
| Station truth | Static JSON (30 stations, Dataset V1-derived) | backend/app/static/demo/data/stations.json |
| Vehicle truth | Static JSON (60 vehicles, Dataset V1-derived) | backend/app/static/demo/data/vehicles.json |
| Trip truth | Static JSON (10 trips) | backend/app/static/demo/data/trips.json |
| Scenario truth | Static JSON (8 scenarios) | backend/app/static/demo/data/scenarios.json |
| Traffic/Queue snapshots | PostgreSQL state_snapshots | asyncpg |
| Recommendation | FastAPI /recommend | backend owns demand, routing, eligibility, ranking |

### 1.3 Technology Audit
| Tech | Status | Evidence |
|------|--------|----------|
| FastAPI | KEEP | App framework |
| GraphHopper 11 | KEEP | Sole routing/matching engine |
| PostgreSQL 16/PostGIS | KEEP | Road data, snapshots, candidate state |
| Redis | KEEP | Driver state, snapshot cache |
| asyncpg | KEEP | Async DB pool in lifespan.py |
| psycopg2 | KEEP | Sync DB reads in health.py, map_match.py, realtime.py, segment_resolver.py |
| sqlalchemy | REMOVE | Declared but NEVER imported in app code |
| redis-py | KEEP | Redis client |
| httpx | KEEP | Routing adapter |
| pandas | KEEP | Check usage in app code |
| prometheus-client | KEEP | Metrics endpoint |
| Leaflet 1.9.4 | KEEP | Map rendering |
| Docker Compose | KEEP | Deployment |

**Action:** Remove `sqlalchemy` from pyproject.toml dependencies (unused — never imported).

### 1.4 Fake/Synthetic Logic Found

#### CRITICAL in `driver_mode.js`:

**Line 149:** `this.progress += 0.25` — Fixed 25% step increment (fake movement)
**Lines 160–166:** `latitude = orig + (dest - orig) * progress` — Straight-line interpolation (NOT road routing)
**Line 172:** `const consumedRange = (totalDist * 0.25)` — Fixed 25% range consumption
**Line 174:** `this.currentSocPct -= 4.5` — Fixed 4.5% SOC decrement per step
**Line 346:** `const etaMin = (this.remainingTripDistanceKm * 2.1)` — Frontend calculates ETA from raw distance

**Lines 100–112:** Trip-specific hardcoded SOC overrides per trip_id (T0003, T0004, T0110)

### 1.5 Backend Business Ownership Audit
✅ Backend owns: demand, energy state, candidate eligibility, routing, ETA, queue, detour, ranking, recommendation
⚠️ Frontend owns: FAKE movement (driver_mode.js lines 149–174), FAKE ETA (line 346)
✅ components.js energy classification: Presentation-only mapping from backend semantic values
✅ api.js: Clean HTTP client, no business logic

### 1.6 Frontend Business Logic to Migrate/Remove in Phase 2
1. `driver_mode.js` `stepProgress()`: Remove fake movement, use Dataset trajectory replay
2. `driver_mode.js` hardcoded SOC per trip_id: Remove, use scenario parameters
3. `driver_mode.js` `renderOnTripUI()` ETA: Use backend routing result, not `(km * 2.1)`
4. `driver_mode.js` fixed SOC decrement: Remove

---

## 2. PHASE 1 — ARCHITECTURE & REPOSITORY CLEANUP

**Goal:** Reduce architectural noise. No business behavior changes.

### Task 1.1 — Remove Unused Dependency

**Files:** `backend/pyproject.toml`
**Implementation:**
- Remove `sqlalchemy>=2.0.0` from dependencies (never imported in app code)
- Verify no `import sqlalchemy` anywhere in `backend/app/`

**Validation:** `grep -r "sqlalchemy" backend/app/ --include="*.py"` returns empty

**Exit condition:** pyproject.toml updated, no runtime breakage, tests pass

### Task 1.2 — Verify psycopg2 / asyncpg Split

**Files:** Reviewed already. Current state:
- `asyncpg`: Pool in lifespan.py, snapshots repository — KEEP
- `psycopg2`: Sync reads in health.py (health check), map_match.py (PostGIS segment resolver), realtime.py (segment lookup), segment_resolver.py (sync resolver) — JUSTIFIED

**Implementation:** Document in code comment. No changes needed.

**Exit condition:** Docs updated explaining sync vs async split

### Task 1.3 — Verify pandas Usage

**Files:** Check where pandas is used
**Implementation:** Audit pandas imports in app code

**Exit condition:** Usage documented

### Task 1.4 — Agent Tooling Audit

**Files:** `.claude/`, `claude_week1_skills/`
**Implementation:** Mark as DEFERRED. Does not affect runtime. Do not modify.

**Exit condition:** DEFERRED marked in plan

### Task 1.5 — Verify Backend Business Ownership Boundaries

**Files:** `backend/app/` API routes and services
**Implementation:** Confirm each service is correctly backend-owned. No changes expected.

**Exit condition:** Audit complete, no violations found

---

## PHASE 1 EXIT GATE

- sqlalchemy removed from pyproject.toml
- Agent tooling DEFERRED
- Dataset unchanged
- Tests pass
- App boots

---

## 3. PHASE 2 — TRUTHFUL END-TO-END DEMO PIPELINE

**Goal:** Demo reflects actual backend behavior. No frontend simulation tricks.

### Task 2.1 — Remove Fake Driver Movement from Driver Mode

**Files:** `backend/app/static/demo/js/driver_mode.js`

**Implementation:**
Remove `stepProgress()` method's fake interpolation:
```javascript
// REMOVE: this.progress += 0.25
// REMOVE: straight-line interpolation
// REMOVE: consumedRange = totalDist * 0.25
// REMOVE: this.currentSocPct -= 4.5
```
Replace with: advance through real Dataset V1 trajectory observations using `replay.js` pattern (each GPS observation ingested via `/api/v1/drivers/{id}/location`).

### Task 2.2 — Remove Hardcoded Trip SOC

**Files:** `backend/app/static/demo/js/driver_mode.js` lines 100–112

**Implementation:**
Remove trip_id → SOC mapping. Use scenario parameters from `scenarios.json` (which already defines `soc_pct`).

### Task 2.3 — Replace Fake ETA

**Files:** `backend/app/static/demo/js/driver_mode.js` line 346

**Implementation:**
Replace `(this.remainingTripDistanceKm * 2.1)` with backend routing result. The backend `/route` response already contains `duration_s`. Display that.

### Task 2.4 — Backend-Owned Energy Classification

**Files:** `backend/app/static/demo/js/components.js`

**Status:** Already correct. `classifyEnergyWarning()` maps backend semantic values (need_service, reason_code) to presentation levels. NO recalculation of business thresholds. KEEP AS IS.

### Task 2.5 — Verify Candidate Identity

**Files:** `backend/app/static/demo/js/map.js`, `components.js`

**Status:** Verified — `key = \`${station_id}_${service_type}\`` preserves composite identity. OK.

### Task 2.6 — Route Geometry Truth

**Files:** `backend/app/static/demo/js/map.js`, `sim_mode.js`

**Status:** `renderDirectRoute()` uses GraphHopper encoded polyline via `decodePolyline()`. Routes are real. OK.

### Task 2.7 — Data Source Consolidation

**Files:** `backend/app/static/demo/data/*.json`

**Status:** Static JSON files are authoritative demo manifest derived from Dataset V1. Not competing with live API. OK.

### Task 2.8 — Deterministic Demo Scenarios

**Files:** `backend/app/static/demo/data/scenarios.json`

**Current:** 8 scenarios covering SAFE, ADVISORY, CRITICAL, CHARGING, SWAP, QUEUE_CHANGE, OFFLINE, ROUTE

**Verification:** Run `scripts/verify_demo_scenarios.py` against live backend

**Exit condition:** All 8 scenarios pass

---

## PHASE 2 EXIT GATE

- No fake product-demo movement
- No arbitrary frontend ETA
- No fixed runtime SOC decrement
- No hidden trip-ID battery hacks
- Frontend does NOT decide demand
- Frontend does NOT decide candidate eligibility
- Frontend does NOT rank stations
- Candidate identity preserves (station_id, service_type)
- Displayed routes use GraphHopper geometry
- Deterministic scenarios pass
- Backend regression passes
- Dataset unchanged

---

## 4. PHASE 3 — PRODUCT-QUALITY DEMO UI

**Goal:** Transform from "technical report" to "believable driver-facing product".

### Task 3.1 — Product Information Architecture

**Files:** `backend/app/static/demo/index.html`, `style.css`

**Changes:**
- Hide technical sidebar sections (Week labels, Dataset V1 references, pipeline latency, raw API details)
- Default view shows: brand + map + recommendation card + energy status
- Move technical content to separate Technical/Debug tab (later separate task)

### Task 3.2 — Map-First Layout

**Files:** `backend/app/static/demo/style.css`, `index.html`

**Changes:**
- Map takes full viewport height
- Recommendation card as overlay/bottom sheet on the right or bottom
- Header: brand + trip status + vehicle + SOC badge
- Clean driver HUD without technical jargon

### Task 3.3 — Product States

**Files:** `backend/app/static/demo/js/components.js`, `driver_mode.js`, `sim_mode.js`

**States to implement:**
- Idle (no trip selected)
- Trip Ready
- Driving (in trip)
- Energy Safe (no diversion needed)
- Energy Advisory (recommendation after drop-off)
- Energy Critical (immediate diversion needed)
- Recommendation Available
- No Eligible Station
- Location unavailable
- Backend dependency error (graceful)

### Task 3.4 — Recommendation Card Redesign

**Files:** `backend/app/static/demo/js/components.js`

**Changes:**
- Primary: station name, service type, ETA, detour
- Show total completion time prominently
- Action button: "Navigate to Station"
- Alternatives collapsed by default (2–5 shown if expanded)

### Task 3.5 — Alternative Stations

**Files:** `backend/app/static/demo/js/components.js`

**Changes:**
- Max 5 alternatives shown in dropdown
- Each shows: station, service, ETA, detour
- No ranking debug rows on default screen

### Task 3.6 — Map Visual Language

**Files:** `backend/app/static/demo/js/map.js`, `style.css`

**Changes:**
- Driver: pulsing blue dot
- Destination: pin A
- Recommended station: highlighted marker
- Eligible stations: subtle markers
- Ineligible stations: hidden or very faded
- Route: blue line, diversion route: orange dashed

### Task 3.7 — Loading / Error UX

**Files:** All JS controllers, `components.js`

**Changes:**
- Loading spinner during route computation
- Graceful timeout state
- "No stations available" state
- "Routing unavailable" state (GraphHopper down)

### Task 3.8 — Demo Scenario Selector

**Files:** `backend/app/static/demo/index.html`, `driver_mode.js`

**Changes:**
- Keep scenario pills but make them SECONDARY
- Primary UI is the product view
- Scenario selector as a small toolbar above the map

### Task 3.9 — Responsive UX

**Files:** `backend/app/static/demo/style.css`

**Changes:**
- 1440px, 1280px, 1024px: map + sidebar layout
- 768px: map + bottom sheet
- Mobile: bottom sheet for recommendation

### Task 3.10 — Frontend Architecture Decision

**Decision:** NO migration to React/Vue/etc.

**Rationale:**
- Current vanilla JS is ~3250 lines, manageable
- All modules are ES6, testable
- Migration risk outweighs benefits for a demo UI
- Keep vanilla JS

---

## PHASE 3 EXIT GATE

- Default /demo looks like a real product
- Map is primary surface
- Technical details not dominant
- Recommendation understandable to non-technical viewer
- Real backend truth drives displayed decisions
- No fake runtime values
- Deterministic scenarios stable
- Desktop responsive passes
- Backend regression passes
- No critical console/runtime error

---

## 5. TEST STRATEGY

| Phase | Tests |
|-------|-------|
| Phase 1 | Backend: `pytest backend/tests -q` |
| Phase 2 | Backend: `pytest backend/tests -q` + `scripts/verify_demo_scenarios.py` |
| Phase 3 | Manual browser test + `test_demo_ui.py` |

---

## 6. KNOWN RISKS

1. **Dataset V1 geography mismatch**: Trip origins in trips.json may differ from scenario.json origins. Must verify cross-references.
2. **GraphHopper motorcycle profile**: No motorcycle routing in production (only car). Driver mode motorcycle trips may fail routing.
3. **Demo UI browser compatibility**: Vanilla ES6 modules require modern browser. Document minimum version.
4. **No end-to-end frontend tests**: No Playwright/Cypress tests exist. Phase 3 relies on manual inspection.

---

## 7. DEFERRED

1. **Technical/Debug View redesign** — Separate task per scope
2. **SQLAlchemy removal** — Dead import only (harmless)
3. **React/Vue migration** — Not justified for demo scope
4. **GraphHopper motorcycle routing** — Blocks driver mode for motorcycle vehicles
5. **E2E browser tests** — Would require Playwright setup
6. **Agent tooling physical cleanup** — May affect coding session stability
