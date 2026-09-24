# Final Demo Guide

**Status:** VERIFIED  
**Date:** 2026-09-24  
**Phase:** Phase 5 — Demo Hardening

---

## 1. Quick Start

```powershell
# 1. Install dependencies
python -m pip install -e "backend[dev]"

# 2. Validate Dataset
python -B scripts/validate_frozen_dataset.py

# 3. Start infrastructure
docker compose up -d --build db graphhopper redis

# 4. Wait for GraphHopper to become healthy (~2 minutes)
# Check: docker compose logs -f graphhopper | findstr "started"

# 5. Load road network data
python scripts/load_road_network.py

# 6. Load Week 4 snapshots
python -B scripts/load_week4_snapshots.py

# 7. Start API
docker compose up -d --build api

# 8. Verify readiness
curl http://127.0.0.1:8000/ready
```

---

## 2. Demo Access

| URL | Description |
|---|---|
| http://127.0.0.1:8000/demo | **Product UI** — Driver-facing view |
| http://127.0.0.1:8000/demo/technical | **Technical View** — Pipeline inspector |

---

## 3. Demo Scenarios

### DEMO 1 — Normal / SAFE
**Story:** Driver has sufficient energy. No diversion needed.

**Steps:**
1. Open Product UI
2. Select Scenario 1 (VF_3, SOC 85%, Trip 3.5 km)
3. Verify: "SAFE" status, no recommendation

**Expected:** `need_service=False`, `SUFFICIENT_SOC_RANGE`

---

### DEMO 2 — Charging Required
**Story:** Driver needs energy but can reach destination.

**Steps:**
1. Select Scenario 2 (VF_6, SOC 22%, Trip 10 km)
2. Verify: "ADVISORY" banner, recommendation after trip complete

**Expected:** `need_service=True`, `INSUFFICIENT_POST_DESTINATION_RESERVE`

---

### DEMO 3 — Destination Unreachable
**Story:** Range insufficient to complete trip.

**Steps:**
1. Select Scenario 3 (VF_6, SOC 25%, Range 30km, Trip 45km)
2. Verify: "CRITICAL" banner with immediate recommendation

**Expected:** `need_service=True`, `DESTINATION_NOT_REACHABLE`

---

### DEMO 4 — Charging Recommendation
**Story:** System recommends charging station.

**Steps:**
1. Select Scenario 4 (VF_6, SOC 12%, Trip 4.1km)
2. Verify: Charging recommendation displayed
3. Click "Navigate to Station" to see route

**Expected:** `has_recommendation=True`, recommended station S017 (CHARGING)

---

### DEMO 5 — Battery Swap
**Story:** Swap-capable vehicle gets battery swap recommendation.

**Steps:**
1. Select Scenario 5 (EVO motorcycle, SOC 10%)
2. Verify: Swap recommendation for S003

**Expected:** `has_recommendation=True`, recommended station S003 (BATTERY_SWAP)

---

### DEMO 6 — Nearest Station Invalid
**Story:** Physically nearby station is rejected.

**Steps:**
1. Compare Scenario 6 at T1 vs T2
2. T1: S022 recommended (0m queue)
3. T2: S016 recommended (S022 queue surged to 46 minutes)

**Expected:** Recommendation changes when nearest station queue increases

---

### DEMO 7 — Offline Station
**Story:** Station goes offline and is rejected.

**Steps:**
1. Select Scenario 7 (S001 at 08:00 VN)
2. Verify: S001 marked as ineligible

**Expected:** S001 `eligible=False`, `reason=OFFLINE`

---

### DEMO 8 — Custom Simulation
**Story:** User-defined origin/destination route.

**Steps:**
1. Click "Custom" in Simulation Mode
2. Pick origin and destination on map
3. Select vehicle and SOC
4. Click "RUN SIMULATION"

**Expected:** Real GraphHopper route computed

---

## 4. Technical View Walkthrough

### Accessing Technical View
1. Click **"🛠 Technical"** button in Product UI header
2. View opens as slide-over panel

### Inspect Pipeline Stages
1. **System Health** — FastAPI, GraphHopper, PostGIS, Redis status
2. **Location** — Raw GPS vs matched road position
3. **Demand** — Energy service request details
4. **Candidates** — Filter by ELIGIBLE/REJECTED/ALL
5. **Routing** — Leg distances, durations, detour metrics
6. **Ranking** — TOTAL_SERVICE_COMPLETION_V1 policy
7. **Timing** — Per-stage latency breakdown

### Key Inspection Points

| Stage | What to Verify |
|---|---|
| Location | `quality_semantics` explains: "not a probability" |
| Demand | `reason_code` matches backend decision |
| Candidates | `(station_id, service_type)` composite identity |
| Routing | `engine: GraphHopper 11.0` on all routes |
| Ranking | `policy_name: TOTAL_SERVICE_COMPLETION_V1` |
| Timing | Real measurements from `timings_ms` |

### Returning to Product View
Click **"← Product View"** or **"✕"** to close Technical View.

---

## 5. Failure Mode Demos

### GraphHopper Unavailable
1. Stop GraphHopper: `docker compose stop graphhopper`
2. Attempt recommendation
3. Verify: HTTP 503 or `ENGINE_UNAVAILABLE` status

**Recovery:** `docker compose up -d graphhopper`

### Redis Unavailable
1. Stop Redis: `docker compose stop redis`
2. Attempt recommendation
3. Verify: Works with PostgreSQL fallback (degraded)

**Recovery:** `docker compose up -d redis`

---

## 6. Verification Commands

```powershell
# Dataset validation
python -B scripts/validate_frozen_dataset.py
# Expected: 152 PASS / 0 FAIL / 22 scenarios

# Backend tests
python -B -m pytest backend/tests -q
# Expected: 368 passed

# Frontend tests
node --test tests/frontend/*.mjs
# Expected: 18 passed

# Demo scenarios
python scripts/verify_demo_scenarios.py
# Expected: 8/8 PASS

# Smoke tests
python scripts/smoke_test.py
python scripts/smoke_test_week3.py
# Expected: All PASS
```

---

## 7. Demo Walkthrough Script

```
========================================
VINFAST EV RECOMMENDATION DEMO SCRIPT
========================================

SECTION 1: Product UI Basics
-----------------------------
1. Open http://127.0.0.1:8000/demo
2. Show clean driver-facing interface
3. Select Scenario 1 (SAFE trip)
4. Show: map, vehicle badge, SOC indicator

SECTION 2: Energy Warning Hierarchy
-----------------------------------
5. Select Scenario 2 (ADVISORY)
6. Show: Amber "Energy reserve low" banner
7. Note: Recommendation available after trip complete

8. Select Scenario 3 (CRITICAL)
9. Show: Red "ENERGY CRITICAL" banner
10. Note: Immediate recommendation needed

SECTION 3: Real Recommendations
--------------------------------
11. Select Scenario 4 (Charging)
12. Show: Recommendation card with ETA, queue, detour
13. Click station marker on map
14. Show: Route to station

15. Select Scenario 5 (Swap)
16. Show: Battery swap recommendation (purple marker)

SECTION 4: Why Nearby Isn't Always Best
----------------------------------------
17. Show Scenario 6 queue change
18. Compare T1 vs T2 recommendation
19. Explain: Nearest station (S022) rejected due to queue surge
20. Alternative (S016) recommended

SECTION 5: Technical Deep Dive
-------------------------------
21. Click "🛠 Technical" button
22. Show: Pipeline stages from bottom to top
23. Show: System health panel (4 services)
24. Show: Location inspector (raw GPS → matched position)
25. Show: Demand inspector (reason codes)
26. Show: Candidate table (eligible vs rejected)
27. Show: Routing details (GraphHopper geometry)
28. Show: Ranking policy and features
29. Click "← Product View"

SECTION 6: Failure Modes
------------------------
30. Open Technical View
31. Point out: health panel shows all 4 services healthy
32. (Optional) Stop graphhopper and show degradation

SECTION 7: Summary
-------------------
33. Return to Product UI
34. Show: All 8 scenario pills
35. Close with: "This system combines GPS, demand detection,
    candidate search, and ranking to recommend the best
    energy service station for EV drivers."

========================================
```

---

## 8. Expected Demo Outcomes

| Demo | Expected Result | Verification |
|---|---|---|
| DEMO 1 | No recommendation | `has_recommendation=False` |
| DEMO 2 | Advisory warning | ADVISORY banner shown |
| DEMO 3 | Critical warning | CRITICAL banner shown |
| DEMO 4 | Charging station | S017 (CHARGING) recommended |
| DEMO 5 | Swap station | S003 (BATTERY_SWAP) recommended |
| DEMO 6 | Queue change | S022 → S016 switch |
| DEMO 7 | Offline rejection | S001 ineligible |
| DEMO 8 | Route computed | Real polyline returned |

---

## 9. Troubleshooting

| Issue | Solution |
|---|---|
| GraphHopper not ready | Wait 2 minutes after `docker compose up` |
| PostGIS not ready | Check `docker compose logs db` |
| No recommendation | Verify Week 4 snapshots loaded |
| Map not loading | Check browser console for JS errors |
| Frontend 404 | Ensure `/demo/static/` path works |

---

## 10. Demo Environment Requirements

- Python 3.11+
- Docker + Docker Compose
- 8GB RAM minimum
- Modern browser (Chrome, Firefox, Edge, Safari)
- Network access for Leaflet tile server
