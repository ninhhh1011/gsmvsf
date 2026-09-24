# Test Results — Consolidated Evidence

**Last Updated:** 2026-09-24

---

## Summary

| Category | Tests | Status |
|----------|-------|--------|
| Canonical Dataset Validator | 152 checks | ✅ PASS |
| Backend Tests | 368 | ✅ PASS |
| Frontend Tests | 18 | ✅ PASS |
| Demo Scenarios | 8 | ✅ PASS |
| **Total** | **546** | **ALL PASS** |

---

## 1. Canonical Dataset Validator

**Command:** `python scripts/validate_frozen_dataset.py`

**Results:**
- 152 checks PASS
- 0 checks FAIL
- 22 scenario assertions PASS

**Coverage:**
- Station catalog integrity
- Vehicle catalog integrity
- Trip definitions
- Trajectory GPS data
- Demand labels
- Candidate labels
- Recommendation labels
- Ranking reference
- Map matching labels

---

## 2. Backend Test Suite

**Command:** `python -B -m pytest backend/tests -q`

### Test Distribution by Week

| Week | Test Files | Key Coverage |
|------|------------|--------------|
| Week 1 | `test_realtime.py`, `test_driver_*.py` | GPS ingestion, map matching, hybrid trigger |
| Week 2 | `test_demand_*.py` | AutoDemandDetector, VehicleCapabilityResolver |
| Week 3 | `test_candidate_*.py`, `test_routing_*.py` | Eligibility, expansion, GraphHopper adapter |
| Week 4 | `test_week4_*.py` | Snapshot ingestion, ranking, invalidation |
| Week 5 | `test_week5_*.py` | Realtime API, replay, evaluation |
| Week 6 | `test_*_production*.py` | Concurrency, metrics, health |

### Key Test Categories

| Category | Files | Coverage |
|----------|-------|----------|
| Candidate Search | 7 files | Eligibility, compatibility, energy feasibility |
| Routing | 4 files | GraphHopper adapter, multi-leg routing |
| Map Matching | 2 files | GPS-to-road matching, integration |
| Demand | 2 files | Demand models, service API |
| Realtime | 2 files | Driver location, state management |
| Health | 2 files | Health endpoints, configuration |

### Week 6 New Tests

| Test | Result |
|------|--------|
| `test_concurrent_station_metrics_produces_correct_results` | ✅ |
| `test_concurrent_with_semaphore_limits` | ✅ |
| `test_in_memory_repository_*` (7 tests) | ✅ |

---

## 3. Frontend Test Suite

**Command:** `node --test tests/frontend/*.mjs`

### Results
- **18 tests total**
- **18 passed**
- **0 failed**

### Test Files

| File | Tests |
|------|-------|
| `test_demo_frontend.mjs` | ApiError, polyline decoding, energy warning, driver state |
| `test_tech_view.mjs` | System health, location inspector, demand inspector, pipeline timing |
| `test_tech_view_scenarios.mjs` | Scenario-specific formatting |

### Coverage

| Component | Tested |
|-----------|--------|
| API error handling | ✅ |
| Polyline decoding | ✅ |
| Energy warning classification | ✅ |
| Driver state constants | ✅ |
| System health classification | ✅ |
| Pipeline latency formatting | ✅ |
| Candidate filtering | ✅ |

---

## 4. Demo Scenario Verification

**Command:** `python scripts/verify_demo_scenarios.py`

### Scenarios

| ID | Title | Status | Evidence |
|----|-------|--------|----------|
| SCENARIO 1 | Driver Trip Safe | ✅ PASS | `need_service=False`, `level=SAFE` |
| SCENARIO 2 | Reserve Insufficient | ✅ PASS | `need_service=True`, `level=ADVISORY` |
| SCENARIO 3 | Destination Unreachable | ✅ PASS | `need_service=True`, `level=CRITICAL` |
| SCENARIO 4 | Car Charging Recommendation | ✅ PASS | Recommended S017, 18 candidates |
| SCENARIO 5 | Motorbike Swap Recommendation | ✅ PASS | Recommended S003, 481.5s total |
| SCENARIO 6 | Dynamic Queue Invalidation | ✅ PASS | S022 → S016 on queue surge |
| SCENARIO 7 | Station OFFLINE | ✅ PASS | S001 flagged `eligible=False` |
| SCENARIO 8 | Custom Simulation A → B | ✅ PASS | 9891.2m route computed |

### Live Verification Evidence

All 8 scenarios executed against production stack:
- **FastAPI** ✅
- **GraphHopper 11.0** ✅
- **PostgreSQL 16.4/PostGIS 3.4** ✅
- **Redis 7.4** ✅

---

## 5. Smoke Tests

### Main Smoke Test
**Command:** `python scripts/smoke_test.py`

Results: ✅ PASS
- `/health` returns 200
- `/ready` returns 200
- API endpoints respond correctly

### Week 3 Smoke Test
**Command:** `python scripts/smoke_test_week3.py`

Results: ✅ PASS
- GraphHopper routing: real geometry
- 9.89 km route computed
- Map matching: real matched positions

---

## 6. Week 5 Replay Evidence

**Command:** `python scripts/replay_week5.py`

### Coverage
| Metric | Value |
|--------|-------|
| Trajectories | 30 (13 cars, 9 charge-only motorcycles, 8 swap-capable motorcycles) |
| GPS observations | 1,712 |
| SOC decisions | 240 |
| Recommendation requests | 308 |
| Success rate | 100% |

### Performance Baseline

| Concurrency | P50 (ms) | P90 (ms) | P95 (ms) | Max (ms) |
|-------------|----------|----------|----------|----------|
| 1 | 302.81 | 352.80 | 370.68 | 442.10 |
| 5 | 1,003.41 | 1,138.94 | 1,189.43 | 1,242.76 |
| 10 | 2,011.37 | 2,436.57 | 2,536.86 | 2,815.30 |

### Stage Breakdown (C1)
| Stage | Median (ms) |
|-------|-------------|
| Location resolution | 0.02 |
| Demand | 0.08 |
| Candidate search | 291.97 |
| Ranking | 7.13 |
| **Total** | **299.99** |

---

## 7. Week 6 Performance

**After concurrency optimization**

| Concurrency | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Max (ms) |
|-------------|----------|----------|----------|----------|----------|
| 1 | 186.4 | 218.5 | 233.8 | 309.2 | 394.7 |

### Improvement
- **Latency reduction:** 38.5% (302ms → 186ms P50)
- **Candidate search reduction:** 44.2% (292ms → 163ms P50)

---

## 8. Week 5 Evaluation Results

**Command:** `python scripts/evaluate_week5.py`

### AUTO Predictions vs Reference

| Metric | Matches | Denominator | Agreement |
|--------|---------|-------------|-----------|
| Recommendation presence | 167 | 184 | 90.76% |
| Station/service identity | 158 | 184 | 85.87% |
| Station/service top-1 | 85 | 95 | 89.47% |
| Service type | 94 | 95 | 98.95% |
| Pairwise order | 1,102 | 1,224 | 90.03% |
| No-service accuracy | 56 | 56 | 100% |

---

## 9. Git History Summary

### Major Commits

| Commit | Description |
|--------|-------------|
| `363d275` | feat(week6): concurrent GraphHopper routing + Prometheus metrics |
| `e07d055` | refactor(phase3): product-quality demo UI |
| `708442c` | refactor(phase2): remove fake driver movement |
| `c08d36b` | chore: remove SQLAlchemy (unused) |

### Freeze Tags
- `week6-production-complete`
- `demo-ui-integration-complete`
- `week5-realtime-api-evaluation-complete`
- `week4-ranking-recommendation-complete`
- `graphhopper-full-migration-complete`
- `week3-candidate-routing-complete`

---

## Verification Commands

```bash
# 1. Dataset validation
python -B scripts/validate_frozen_dataset.py

# 2. Backend tests
python -B -m pytest backend/tests -q

# 3. Frontend tests
node --test tests/frontend/*.mjs

# 4. Demo scenarios
python scripts/verify_demo_scenarios.py

# 5. Smoke tests
python scripts/smoke_test.py
python scripts/smoke_test_week3.py
```

---

## Evidence Files

| Category | Location |
|----------|----------|
| Dataset validation | `runtime/migration/validation/` |
| Replay results | `runtime/week5/replay-*.json` |
| Evaluation results | `runtime/week5/evaluation-*.json` |
| Performance results | `runtime/week5/performance-*.json` |
| Week 6 benchmark | `runtime/week6/baseline-*.json` |
