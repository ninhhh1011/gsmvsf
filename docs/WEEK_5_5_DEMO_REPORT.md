# Week 5.5 — Demo / Integration UI Report

**Date:** 2026-09-21  
**Milestone:** Week 5.5 — Demo / Integration UI  
**Target Completion Tag:** `demo-ui-integration-complete`  
**Baseline Tag:** `week5-realtime-api-evaluation-complete` (`f0ec912`)  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

Week 5.5 delivers a high-fidelity, responsive Single Page Application (SPA) that visually integrates and demonstrates the complete Week 1 through Week 5 pipeline:
- **Week 1:** Realtime GPS Ingestion, Hybrid Map Matching Trigger Policy, PostGIS directed road segment resolution.
- **Week 2:** Demand Detection and Energy Service Request contracts (`need_service`, `reason_code`, `energy_margin_km`, `safety_reserve_km`).
- **Week 3:** Candidate Search and Multi-leg Routing (Origin → Station → Destination) with GraphHopper encoded polyline geometries.
- **Week 4:** PostgreSQL immutable state snapshots, Redis latest-payload cache, `TOTAL_SERVICE_COMPLETION_V1` ranking policy, and composite station/service identity.
- **Week 5:** Request-driven realtime recommendation orchestration, stage timing breakdown (`timings_ms`), and conflict handling (HTTP 409 `CANDIDATE_STATE_CHANGED`).

### Critical Architectural Rules Preserved:
1. **NO BUSINESS LOGIC IN FRONTEND:** All ranking formulas, candidate eligibility rules, demand thresholds, and route calculations remain strictly inside the backend. The UI collects input, queries actual FastAPI endpoints, decodes GraphHopper geometries, and renders exact backend evidence.
2. **ZERO HEAVY DEPENDENCIES:** The frontend is served directly by FastAPI from `backend/app/static/demo/` using modern vanilla ES6 modules and Leaflet 1.9.4 via CDN. No Node build steps or heavy frontend frameworks were introduced.
3. **FROZEN BASELINE INTACT:** All 63 canonical Dataset V1 files remain read-only. Full backend regression passes with 350 tests (347 baseline + 3 new integration tests), and the canonical validator reports 152 PASS / 0 FAIL and 22/22 scenario assertions.

---

## 2. Product Modes & UX Architecture

The UI is divided into two clearly separated modes:

### A. Driver Mode (Primary Driver Workflow)
Driver Mode models an in-car VinFast driver on an active passenger trip:
- **Concept:** Origin ($A$) is the driver's current position from GPS / Map Matching; Destination ($B$) is the passenger drop-off location. The driver does not manually input routing waypoints.
- **State Model:**
  $$\text{OFFLINE} \longrightarrow \text{AVAILABLE} \longrightarrow \text{TRIP\_ASSIGNED} \longrightarrow \text{TO\_PICKUP} \longrightarrow \text{ON\_TRIP} \longrightarrow \text{TRIP\_COMPLETE}$$
- **Single Passenger Trip Rule:** Strictly one active passenger trip at a time. No stacked trips or dispatch engines.
- **Distraction-Free Driving View:** Giant ranking tables and raw candidate lists are hidden while `ON_TRIP`. The driver HUD displays:
  - Destination name & estimated arrival time.
  - Remaining trip distance (km) and vehicle battery SOC progress bar.
  - Estimated remaining range (km) computed by the backend.
  - Non-intrusive energy status banner.
- **Energy Warning Hierarchy:**
  - **SAFE:** Neutral/positive status indicator (`SUFFICIENT_SOC_RANGE`). No warning modal.
  - **ADVISORY:** Non-blocking amber banner (`INSUFFICIENT_POST_DESTINATION_RESERVE`). Warns that energy reserve is low after drop-off; recommends service after completing current trip. No automatic reroute.
  - **CRITICAL:** High-priority crimson banner with warning icon (`DESTINATION_NOT_REACHABLE`). Warns that range is insufficient to complete the trip; active recommendation stop displayed.
- **Trip Complete Prominence:** Upon reaching `TRIP_COMPLETE`, if energy service is needed, the top recommended station card is prominently highlighted with total completion time, queue wait, service time, and detour details.

### B. Simulation / Debug Mode (Mentor & Scenario Inspection)
An information-dense laboratory for evaluating pipeline behavior and dynamic edge cases:
- **A/B Map & Coordinate Controls:** Interactive map-picking crosshairs or numeric lat/lng inputs for origin and destination.
- **Vehicle & SOC Selection:** Real vehicle models (VF_3, VF_5, VF_6, EVO, FELIZ_II) with live SOC slider (0–100%) and vehicle capability spec display.
- **Service Intent Selector:** `AUTO`, `CHARGING`, `BATTERY_SWAP`, or `ANY`.
- **Pipeline Latency Bar:** Exposes exact per-stage execution times from backend `timings_ms`:
  - W1 Location Resolution (ms)
  - W2 Demand Evaluation (ms)
  - W3 Candidate Search (ms)
  - W4 Snapshot Ranking (ms)
  - W5 Total Pipeline Latency (ms)
- **Candidate Panels:**
  - **ELIGIBLE:** Full breakdown of travel time, queue wait, service time, detour, available capacity, and final cost.
  - **INELIGIBLE:** Categorized with explainable backend rejection reasons (`OFFLINE`, `INCOMPATIBLE`, `FULL`, `NO_SWAP_BATTERY`, `UNREACHABLE`).
- **Trajectory Replay Widget:** Replays real Dataset V1 GPS observations through `/api/v1/drivers/{id}/location` with 1x, 5x, 10x, 25x, and 50x speed controls.

---

## 3. End-to-End Live Scenario Verification Evidence

All 8 canonical scenarios were executed against the live production stack (FastAPI, GraphHopper 11.0, PostGIS 16-3.4, Redis 7.4) via `scripts/verify_demo_scenarios.py`:

| Scenario ID | Title | Input State | Backend Reason Code | Result & Evidence | Status |
|---|---|---|---|---|:---:|
| **SCENARIO 1** | Driver Trip Safe | Trip T0001, VF_3, SOC 85%, Range 100 km, Trip 3.5 km | `SUFFICIENT_SOC_RANGE` | `need_service=False`, `level=SAFE`, No recommendation needed | **PASS** |
| **SCENARIO 2** | Reserve Insufficient (Advisory) | Trip T0003, VF_6, SOC 22%, Range 12 km, Trip 10 km, Reserve 5 km | `INSUFFICIENT_POST_DESTINATION_RESERVE` | `need_service=True`, `margin_km=-3.0`, `level=ADVISORY` banner | **PASS** |
| **SCENARIO 3** | Destination Unreachable (Critical) | Trip T0003, VF_6, SOC 25%, Range 30 km, Trip 45 km, Reserve 5 km | `DESTINATION_NOT_REACHABLE` | `need_service=True`, `range < trip`, `level=CRITICAL` warning | **PASS** |
| **SCENARIO 4** | Car Charging Recommendation | Trip T0004, VF_6, SOC 12%, Range 25 km, Trip 4.1 km | `LOW_SOC` / `CHARGING` | Recommended `S017` (`CHARGING`), 18 ranked candidates, Cost 1441.3s | **PASS** |
| **SCENARIO 5** | Motorbike Swap Recommendation | Trip T0110, EVO, SOC 10%, Range 15 km, `BATTERY_SWAP` | `LOW_SOC` / `BATTERY_SWAP` | Recommended `S003` (`BATTERY_SWAP`), Cost 481.5s (8.0 min total) | **PASS** |
| **SCENARIO 6** | Dynamic Queue Invalidation | Trip T0017, VF_6, Time T1 (07:42) vs Time T2 (07:52) | `TOTAL_SERVICE_COMPLETION_V1` | T1: `S022` (0m queue) → T2: `S016` (S022 surged to 46.29m queue) | **PASS** |
| **SCENARIO 7** | Station Status OFFLINE | Station S001 at 08:00+07:00 | `OFFLINE` | Candidate Search flags S001 as `eligible=False`, `reason=OFFLINE` | **PASS** |
| **SCENARIO 8** | Custom Simulation A → B | Custom Origin (21.0285, 105.8542) to Dest (21.0150, 105.7800) | `SUCCESS` | GraphHopper route computed: 9891.2m, 704.9s duration, decoded polyline | **PASS** |

---

## 4. Test & Regression Results

### Backend Test Suite
```text
350 passed in 21.89s
```
- Historical baseline: 347 passed.
- New demo UI integration tests: 3 passed (`test_demo_page_serving`, `test_demo_static_assets`, `test_demo_catalogs`).
- Zero regressions across Weeks 1–5.

### Frontend Unit Tests (Node.js Native Test Runner)
```text
✔ ApiError sets flags correctly (2.37ms)
✔ decodePolyline decodes standard encoded polylines (0.83ms)
✔ classifyEnergyWarning maps backend reason codes to UX warning levels (0.20ms)
✔ DriverState constants are defined correctly (0.11ms)
ℹ tests 4 | pass 4 | fail 0 | duration 111ms
```

### Canonical Dataset V1.3.1 Validation
```text
152 passed, 0 failed, 22 scenario assertions passed, 0 failed.
Overall: PASS
```

---

## 5. File Inventory

| Path | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI mount for `/demo`, `/demo/`, and static assets under `/demo/static` |
| `backend/app/static/demo/index.html` | SPA HTML shell with header, mode switchers, HUD, debug controls, and Leaflet map container |
| `backend/app/static/demo/style.css` | Comprehensive CSS design system with mobility tokens, responsive breakpoints, and custom marker pulses |
| `backend/app/static/demo/js/api.js` | Centralized API client with structured error handling (409 conflict, 422 location, 503 outage) |
| `backend/app/static/demo/js/map.js` | Leaflet engine, polyline decoder, custom SVG icons, and GraphHopper route visualizer |
| `backend/app/static/demo/js/components.js` | UI component renderers for energy banners, recommendation card, pipeline latency, candidate tables, and conflict alerts |
| `backend/app/static/demo/js/driver_mode.js` | State machine and HUD controller for Driver Mode |
| `backend/app/static/demo/js/sim_mode.js` | Form handler, map coordinate picker, scenario loader, and simulation orchestrator |
| `backend/app/static/demo/js/replay.js` | Trajectory replay controller with speed multiplier and GPS ingestion loops |
| `backend/app/static/demo/js/app.js` | Main coordinator, catalog loader, and backend health monitor |
| `backend/app/static/demo/data/*.json` | Static JSON catalogs for stations, vehicles, scenarios, and trips extracted from Dataset V1 |
| `backend/tests/test_demo_ui.py` | Pytest integration tests for demo endpoint and asset delivery |
| `tests/frontend/test_demo_frontend.mjs` | Node.js unit tests for API error flags, polyline decoding, and energy classification |
| `scripts/verify_demo_scenarios.py` | Automated end-to-end verifier for the 8 canonical demo scenarios |
| `docs/DEMO_UI_IMPLEMENTATION_PLAN.md` | Complete implementation plan, task breakdowns, and exit gates |

---

## 6. Known Limitations & Handoff to Week 6

1. **Local Demo Scope:** The UI is designed for live project demonstration, mentor review, and visual inspection. It does not replace the official VinFast driver native application.
2. **Single Driver Simulation:** Replay is request-driven on the client side; there is no server-side push, websocket daemon, or Kafka streaming broker (consistent with ADR-014).
3. **Week 6 Optimization Targets:** Visual pipeline latency breakdown identifies GraphHopper routing and Candidate Search (multi-candidate route calls) as the primary target for Week 6 caching and batch routing optimization.
