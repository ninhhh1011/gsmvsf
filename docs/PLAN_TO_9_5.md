# PLAN: REACH 9.5/10 - COMPLETE EV CHARGING RECOMMENDATION SYSTEM

## MỤC TIÊU
Nâng repo từ 7.5/10 lên 9.5/10 bằng cách hoàn thiện H3 feature và production hardening.

---

## PHASE 1: H3 ROUTE HISTORY STORAGE (CRITICAL)
### Task 1.1: Enable H3 Feature Flag
- [ ] Change `ENABLE_ROUTE_FAMILIARITY=false` → `true` in config
- [ ] Update default in `RouteHistoryConfig`

### Task 1.2: Implement Route History Database Schema
**File: `backend/app/services/route_history/schema.sql`**
```sql
CREATE TABLE route_history (
    id SERIAL PRIMARY KEY,
    route_id VARCHAR(64) NOT NULL UNIQUE,
    driver_id VARCHAR(64) NOT NULL,
    vehicle_id VARCHAR(64),
    timestamp TIMESTAMP NOT NULL,
    origin_lat FLOAT NOT NULL,
    origin_lng FLOAT NOT NULL,
    dest_lat FLOAT NOT NULL,
    dest_lng FLOAT NOT NULL,
    segment_ids TEXT NOT NULL,  -- JSON array
    h3_signature TEXT NOT NULL,  -- JSON array of H3 cells
    total_distance_m FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    INDEX idx_driver_time (driver_id, timestamp),
    INDEX idx_origin (origin_lat, origin_lng),
    INDEX idx_dest (dest_lat, dest_lng),
    INDEX idx_h3 (h3_signature gin_idx USING gin)
);

CREATE TABLE route_families (
    family_id VARCHAR(64) PRIMARY KEY,
    representative_route_id VARCHAR(64),
    origin_lat FLOAT NOT NULL,
    origin_lng FLOAT NOT NULL,
    dest_lat FLOAT NOT NULL,
    dest_lng FLOAT NOT NULL,
    direction_bearing FLOAT,
    trip_count INT DEFAULT 1,
    unique_driver_count INT DEFAULT 1,
    weighted_support FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Task 1.3: Implement RouteHistoryRepository Methods
**File: `backend/app/services/route_history/repository.py`**
- [ ] `store_route(route_data)` - Save route to DB
- [ ] `get_driver_routes(driver_id, days)` - Get driver's history
- [ ] `query_by_origin_dest(origin, dest, radius_km)` - Find similar routes
- [ ] `query_by_h3_cells(cells, min_overlap)` - H3 inverted index lookup
- [ ] `get_family_stats(family_id)` - Get family metrics

### Task 1.4: Create Demo Endpoint
**File: `backend/app/api/v1/routes.py`** (NEW)
```python
@router.post("/routes/compare")
async def compare_routes(
    route_a: RouteInput,
    route_b: RouteInput,
    resolution: int = Query(10, ge=8, le=12)
):
    """
    Compare two routes using H3 signature.
    
    Returns:
    - Shared H3 cells
    - Adherence percentage
    - Similarity score
    - Common segments
    """
```

---

## PHASE 2: PRODUCTION HARDENING

### Task 2.1: Prometheus Alerts
**File: `backend/app/monitoring/alerts.yml`**
```yaml
groups:
  - name: recommendation_alerts
    rules:
      - alert: HighRecommendationLatency
        expr: histogram_quantile(0.95, rate(ev_recommendation_latency_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P95 latency exceeds 2s"
          
      - alert: HighErrorRate
        expr: rate(ev_recommendation_errors_total[5m]) / rate(ev_recommendation_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
          
      - alert: CacheHitRateLow
        expr: rate(ev_cache_hits_total[5m]) / rate(ev_cache_requests_total[5m]) < 0.7
        for: 10m
        labels:
          severity: warning
```

### Task 2.2: Health Check Endpoints
**File: `backend/app/api/v1/health.py`**
- [ ] `/health/live` - Kubernetes liveness probe
- [ ] `/health/ready` - Readiness probe (checks DB + GraphHopper)
- [ ] `/metrics` - Prometheus metrics endpoint

### Task 2.3: Rate Limiting
**File: `backend/app/api/v1/middleware.py`**
```python
from fastapi import RateLimiter

@router.middleware
async def rate_limit_middleware(request, call_next):
    limiter = RateLimiter(keygen=client_ip, rates={"100/min", "1000/hour"})
    await limiter.check()
    return await call_next(request)
```

---

## PHASE 3: DOCUMENTATION CONSOLIDATION

### Task 3.1: Consolidate 44 files into 5
Target structure:
```
docs/
├── README.md                    # Overview + quick start
├── ARCHITECTURE.md              # System design
├── API_REFERENCE.md             # Swagger/OpenAPI docs
├── OPERATIONS.md                # Deployment + monitoring
└── DEVELOPMENT.md               # Dev setup + testing
```

**Merge plan:**
- `docs/WEEK_*.md` → `docs/ARCHITECTURE.md`
- `docs/GRAPHHOPPER_*.md` → `docs/OPERATIONS.md`
- `docs/PROJECT_SCOPE.md` + `docs/ACCEPTANCE_CRITERIA.md` → `docs/README.md`
- Keep: `docs/CHALLENGES_*.md` as separate

### Task 3.2: Generate OpenAPI Spec
```python
# backend/app/main.py
from fastapi.openapi.utils import get_openapi

app = FastAPI(title="EV Charging Recommendation API")

@app.get("/openapi.json")
async def openapi_spec():
    return get_openapi(title=app.title, version=app.version, routes=app.routes)
```

---

## PHASE 4: TESTING & SECURITY

### Task 4.1: Integration Tests
**File: `backend/tests/integration/test_h3_comparison.py`**
```python
def test_route_similarity_integration():
    """Test H3 route comparison end-to-end."""
    # 1. Create two routes
    # 2. Store in DB
    # 3. Query by H3
    # 4. Compare similarity
    # 5. Verify results
```

**File: `backend/tests/integration/test_realtime_flow.py`**
```python
def test_realtime_recommendation_flow():
    """Test GPS → Demand → Candidate → Ranking → Response."""
```

### Task 4.2: Load Tests
**File: `backend/tests/load/test_load.py`**
```python
def test_concurrent_recommendations():
    """Test 100 concurrent recommendation requests."""
    # Use locust or k6
```

### Task 4.3: Security Review Checklist
- [ ] Dependency audit: `pip-audit` hoặc `safety`
- [ ] SQL injection check (SQLAlchemy ORM = safe)
- [ ] Input validation review
- [ ] Rate limiting test

---

## PHASE 5: POLISH & VERIFY

### Task 5.1: Final Integration
- [ ] Run all tests
- [ ] Verify H3 demo works
- [ ] Check Prometheus metrics
- [ ] Validate OpenAPI spec

### Task 5.2: Final Report
- [ ] Update `EVALUATION_REPORT.md` với điểm mới
- [ ] Document any trade-offs made
- [ ] List remaining tech debt

---

## DELIVERABLES CHECKLIST

| Deliverable | Target |
|-------------|--------|
| H3 feature enabled | ✅ |
| Route history DB schema | ✅ |
| Demo endpoint `/routes/compare` | ✅ |
| Prometheus alerts (3+ alerts) | ✅ |
| OpenAPI documentation | ✅ |
| Docs consolidated (44 → 5 files) | ✅ |
| Integration tests | ✅ |
| Load tests | ✅ |
| Security review | ✅ |

---

## ESTIMATED TIME

| Phase | Effort | Parallel? |
|-------|--------|----------|
| Phase 1: H3 Storage | 8h | Agent A |
| Phase 2: Production | 6h | Agent B |
| Phase 3: Docs | 3h | Agent C |
| Phase 4: Tests | 5h | Agent D |
| Phase 5: Polish | 2h | Main |

**Total: ~24 giờ = 3 tuần work**

---

## SCORE TARGET

| Milestone | Score |
|-----------|-------|
| Current | 7.5 |
| After Phase 1 | 8.5 |
| After Phase 2 | 8.9 |
| After Phase 3 | 9.1 |
| After Phase 4 | 9.4 |
| After Phase 5 | **9.5+** |

---

## AGENT ASSIGNMENTS

| Agent | Tasks |
|-------|-------|
| Agent A | Phase 1: H3 Storage |
| Agent B | Phase 2: Production Hardening |
| Agent C | Phase 3: Documentation |
| Agent D | Phase 4: Testing & Security |
| Main | Phase 5: Polish & Verify |
