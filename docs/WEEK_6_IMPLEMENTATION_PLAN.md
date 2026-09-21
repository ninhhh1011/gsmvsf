# Week 6 Implementation Plan — Productionization

**Date:** 2026-09-22
**Status:** Phase 2 In Progress
**Based on:** Phase 0 Repository Audit

---

## Executive Summary

Week 6 productionizes the existing Week 1→5 system without adding new business features. The focus is on:

1. **Measured latency reduction** — particularly GraphHopper routing concurrency ✅ DONE
2. **Cross-process driver state** — shared state across multiple API instances ⏳ Pending
3. **Observability** — Prometheus metrics endpoint ✅ DONE
4. **Reliability hardening** — timeouts, failure policies, recovery ⏳ Pending
5. **Deployment hardening** — reproducible deployment configuration ⏳ Pending

---

## Phase 0 Audit Findings

### Current Architecture State

| Component | Status | Notes |
|-----------|--------|-------|
| HTTP Client | ⚠️ Basic | Single `httpx.AsyncClient` with 60s timeout, no explicit pool config |
| GraphHopper Routing | ✅ Concurrent | 8 parallel calls (was sequential) |
| Route Caching | ✅ Request-scoped | Direct and station routes cached within request |
| Snapshot Cache | ✅ Redis + PG | CAS Lua script, 60s TTL, PostgreSQL fallback |
| Driver State | ❌ Process-local | In-memory `dict`, not shared across processes |
| Prometheus Metrics | ✅ Added | `/api/v1/metrics` endpoint |
| Structured Logging | ✅ Present | structlog + JSONRenderer |
| Health Checks | ✅ Basic | /health and /readiness verified |
| Docker Compose | ✅ Present | 4 services with healthchecks |

### Historical Week 5 Baseline (Reference)

| Concurrency | Median ms | P90 ms | P95 ms | Max ms |
|-------------|-----------|--------|--------|--------|
| 1 | 302.814 | 352.801 | 370.677 | 442.097 |
| 5 | 1,003.411 | 1,138.937 | 1,189.425 | 1,242.757 |
| 10 | 2,011.372 | 2,436.568 | 2,536.864 | 2,815.297 |

**Stage Breakdown (C1):**
- Location resolution: 0.023 ms
- Demand: 0.077 ms
- Candidate search: 291.967 ms (97%)
- Ranking: 7.129 ms (2%)
- Total: 299.996 ms

### Identified Bottlenecks

1. **Sequential GraphHopper calls** — ~60 route calls per request executed sequentially ✅ FIXED
2. **No cross-request route cache** — same driver→station routes recomputed ⏳
3. **No Prometheus metrics** — observability limited ✅ FIXED
4. **Process-local driver state** — single-instance only ⏳
5. **No HTTP connection pool tuning** — default httpx limits ✅ Adequate

---

## Phase 1: Baseline Measurement

**Status:** Running fresh baseline on current HEAD (160e556)

**Command:** `python scripts/benchmark_week5.py --api-url http://127.0.0.1:8000 --warmup 5 --samples 50`

**Output:** `runtime/week6/baseline-pre-optimization.json`

---

## Phase 2: Implementation Tasks

### Phase A: Candidate Search / GraphHopper Optimization

#### Task A1: Route De-duplication Verification

**Objective:** Verify that identical physical routes are not duplicated within one request

**Evidence:** `multi_leg.py` lines 187-195 show `station_routes` cache keyed by `station_id`

**Current Behavior:**
- `compute_station_metrics` is called once per unique station
- CHARGING and BATTERY_SWAP for same station share routes
- ✅ De-duplication already correct

**Action:** Document and verify

---

#### Task A2: Bounded GraphHopper Concurrency

**Objective:** Enable concurrent GraphHopper routing calls within Candidate Search

**Bottleneck:** Sequential execution in `multi_leg.py` (leg1 → leg2 → direct)

**Implementation:**
```
multi_leg.py:
  - Add asyncio.gather for parallel leg computation
  - Add configurable concurrency limit (default: 8)
  - Measure P50/P90 latency at limits 1, 2, 4, 8

Files to change:
  - backend/app/services/routing/multi_leg.py
  - backend/app/config.py (new settings)
```

**Approach:**
```python
# Conceptual implementation
async def compute_all_stations_concurrent(self, stations, ...):
    semaphore = asyncio.Semaphore(self.max_concurrent_routes)
    async def compute_one(station):
        async with semaphore:
            return await self.compute_station_metrics(...)
    return await asyncio.gather(*[compute_one(s) for s in stations])
```

**Test Plan:**
1. Run benchmark at C1 with concurrency 1, 2, 4, 8
2. Measure candidate_search latency
3. Verify GraphHopper error rate unchanged
4. Verify correctness (same eligible candidates)

**BEFORE:** Sequential ~292ms median (C1)
**AFTER:** Expected ~50-100ms median (C1) if parallelized

**Risks:**
- GraphHopper connection limit exhaustion → use Semaphore
- Increased memory under load → configurable limit
- Out-of-order results → gather preserves order

**Rollback:** Set `max_concurrent_routes=1` restores sequential behavior

---

#### Task A3: GraphHopper Connection Pool Review

**Objective:** Ensure HTTP client pooling is optimal

**Current State:**
- `httpx.AsyncClient(timeout=60.0)` in lifespan.py
- No explicit connection limits

**Audit:**
- httpx default: 100 connections per host
- GraphHopper can handle concurrent requests
- Keep-alive enabled by default

**Action:** Document that pooling is adequate; no changes needed unless Task A2 shows connection issues

---

### Phase B: Selective Cross-Request Route Cache

#### Task B1: Route Cacheability Analysis

**Objective:** Determine if cross-request route caching is worthwhile

**Analysis:**
| Route Type | Cacheability | Rationale |
|------------|--------------|------------|
| driver → station | Low | Driver moves frequently |
| station → destination | Medium | Stable during active trip |
| direct driver → destination | Low | Changes with driver movement |

**Recommendation:** Cache station→destination routes with 60s TTL
- Key: `route:{station_id}:{dest_node_id}:{profile}`
- Use Redis with configurable TTL
- Only cache successful routes

**Alternative:** Skip cache if hit rate < 10% — complexity not justified

---

#### Task B2: Route Cache Implementation (Conditional)

**Condition:** If Task B1 analysis shows >10% hit rate potential

**Files to change:**
- `backend/app/services/routing/route_cache.py` (new)
- `backend/app/services/routing/multi_leg.py`
- `backend/app/config.py`

**Implementation:**
```python
class RouteCache:
    def __init__(self, redis, ttl=60):
        self.redis = redis
        self.ttl = ttl

    def key(self, origin, dest, profile):
        return f"route:{hash((origin, dest, profile))}"

    async def get(self, key): ...
    async def put(self, key, route_result): ...
```

**Metrics to track:**
- `route_cache_hit`
- `route_cache_miss`
- `route_cache_latency_ms`

---

### Phase C: Cross-Process Driver State

#### Task C1: Driver State Repository Interface

**Objective:** Abstract driver state behind repository interface

**Current State:** `DriverStateStore` in `services/realtime/state.py` is process-local

**Implementation:**
```
backend/app/services/realtime/driver_state_repository.py:
  - DriverStateRepository (ABC)
  - InMemoryDriverStateRepository (test/dev)
  - RedisDriverStateRepository (production)
```

**State to Persist:**
- `observations` (deque of GPSObservation)
- `last_match_time`, `last_matched_state`
- `movement_since_match`, `consecutive_stationary`
- `total_observations_received`, `total_match_calls`

**NOT persisted (ephemeral):**
- In-memory deque maxlen (recreate with same limit)
- Temporary gap/reset counters

**Files to change:**
- `backend/app/services/realtime/state.py`
- `backend/app/services/realtime/driver_state_repository.py` (new)
- `backend/app/core/lifespan.py`
- `backend/app/config.py`

---

#### Task C2: Redis Driver State Repository

**Objective:** Implement production Redis-backed driver state

**Implementation:**
```python
class RedisDriverStateRepository(DriverStateRepository):
    def __init__(self, redis_client, max_drivers=10000):
        self.redis = redis_client
        self._max = max_drivers

    async def get(self, driver_id) -> Optional[DriverTraceState]:
        # Redis GET with JSON deserialization
        raw = await self.redis.get(f"driver:{driver_id}")
        return DriverTraceState.from_dict(json.loads(raw)) if raw else None

    async def save(self, state: DriverTraceState):
        # Redis SET with JSON serialization
        key = f"driver:{state.driver_id}"
        await self.redis.set(key, state.to_json(), ex=3600)
```

**Concurrency Model:**
- Use Redis SETNX for distributed locking if needed
- Per-driver atomic updates
- No cross-driver transactions

**Failure Semantics:**
- Redis unavailable → HTTP 503 with `DRIVER_STATE_UNAVAILABLE`
- No fallback to in-memory (would cause split-brain)

---

#### Task C3: Cross-Process Verification

**Objective:** Verify driver state works across multiple API instances

**Test Scenario:**
1. Start API instance A on port 8000
2. Start API instance B on port 8001
3. Instance A ingests GPS for driver D001
4. Instance B reads driver D001 state
5. Verify state matches

**Verification:**
```python
async def test_cross_process_driver_state():
    # Instance A: ingest observation
    await api_a.post('/api/v1/realtime', json={...})

    # Instance B: read state
    response = await api_b.get(f'/api/v1/realtime/{driver_id}/state')

    # Assert state exists and matches
    assert response.status_code == 200
    assert response.json()['driver_id'] == driver_id
```

---

### Phase D: Observability

#### Task D1: Prometheus Metrics Endpoint

**Objective:** Expose `/metrics` endpoint in Prometheus format

**Metrics to Track:**
```
# Counters
recommendation_requests_total{status}
graphhopper_route_calls_total{status}
candidate_state_conflicts_total
db_fallback_total
dependency_errors_total{dependency}

# Histograms
recommendation_latency_seconds{stage}
candidate_search_latency_seconds
graphhopper_route_latency_seconds
driver_state_latency_seconds

# Gauges
active_drivers_count
cache_hit_rate
```

**Files to change:**
- `backend/app/api/v1/metrics.py` (new)
- `backend/app/core/metrics.py` (new)
- `backend/app/main.py`

**Implementation:**
```python
from prometheus_client import Counter, Histogram, generate_latest

router = APIRouter()

@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

**Labels:** Avoid high-cardinality labels (no driver_id, station_id, request_id)

---

#### Task D2: Stage Timing Integration

**Objective:** Instrument all stages with metrics

**Integration Points:**
1. `realtime.py` — location resolution, demand timing
2. `orchestration.py` — candidate search, ranking timing
3. `multi_leg.py` — GraphHopper call timing
4. `resolver.py` — cache hit/miss

**Implementation:**
```python
from backend.app.core.metrics import (
    LATENCY, REQUEST_COUNT, ERROR_COUNT,
)

LATENCY.labels(stage="candidate_search").observe(duration_s)
REQUEST_COUNT.labels(endpoint="recommend").inc()
```

---

### Phase E: Reliability Hardening

#### Task E1: Timeout Verification

**Objective:** Verify all dependency calls have explicit bounded timeouts

**Current Timeouts:**
| Component | Current Timeout | Status |
|-----------|-----------------|--------|
| GraphHopper route | 10.0s (adapter) | ✅ Configurable |
| HTTP client | 60.0s (lifespan) | ⚠️ Very long |
| Snapshot DB | 5.0s | ✅ Configurable |
| Snapshot cache | 0.2s | ✅ Configurable |
| Readiness checks | 5.0s | ✅ OK |

**Action:** Reduce HTTP client timeout to 30s; keep GraphHopper adapter at 10s

---

#### Task E2: Dependency Failure Policy Documentation

**Objective:** Document explicit failure behavior for each dependency

**Policies:**
| Dependency | Failure | Behavior |
|------------|---------|----------|
| GraphHopper | 503 | Explicit routing/matching failure |
| PostgreSQL | 503 | Readiness false; DB operations fail |
| Redis (snapshot) | 200 | PostgreSQL fallback |
| Redis (driver state) | 503 | Explicit `DRIVER_STATE_UNAVAILABLE` |

**Document in:** `docs/PRODUCTIONIZATION_RUNBOOK.md`

---

### Phase F: Health / Readiness

#### Task F1: Enhanced Health Endpoint

**Objective:** Distinguish required vs optional dependencies

**Current:** `/readiness` returns 503 if any dependency fails

**Enhanced:**
```python
@router.get("/readiness")
async def ready():
    deps = await dependencies_ready()
    required = deps['graphhopper'] and deps['postgis']
    snapshot_cache = deps.get('redis_snapshot', True)  # Optional
    driver_state = deps.get('redis_driver_state', True)  # Optional

    if not required:
        raise HTTPException(503, detail={
            'status': 'not_ready',
            'required': {k: v for k, v in deps.items() if k in ('graphhopper', 'postgis')},
            'optional': {k: v for k, v in deps.items() if k not in ('graphhopper', 'postgis')}
        })
    return {'status': 'ready', **deps}
```

---

### Phase G: Deployment Hardening

#### Task G1: Docker Compose Production Config

**Objective:** Create production-ready compose configuration

**Files to create:**
- `docker-compose.prod.yml`
- `.env.example` (update)

**Configuration:**
```yaml
services:
  api:
    profiles: [api]  # Start separately
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M
    restart: unless-stopped
    stop_grace_period: 30s
```

---

#### Task G2: Graceful Shutdown Verification

**Objective:** Verify graceful shutdown works correctly

**Current:** `lifespan.py` closes HTTP client on shutdown

**Verification:**
```bash
docker stop ev_api --timeout 30
# Verify in-flight requests complete
# Verify connections drain properly
```

---

### Phase H: Load / Failure / Recovery Testing

#### Task H1: Failure Injection Tests

**Objective:** Verify recovery from dependency failures

| Scenario | Test | Expected |
|----------|------|----------|
| Redis down | Snapshot reads | PostgreSQL fallback |
| Redis recovery | Snapshot reads | Redis cache resumes |
| GraphHopper down | /route | HTTP 504 |
| GraphHopper recovery | /route | Success |
| PostgreSQL down | /ready | HTTP 503 |
| PostgreSQL recovery | /ready | HTTP 200 |

---

#### Task H2: Final Load Test

**Objective:** Compare before/after optimization

**Test Configuration:**
- Warmup: 5 requests
- Measured: 50 requests
- Concurrency: 1, 5, 10
- Output: `runtime/week6/performance-post-optimization.json`

---

## Phase 3: Exit Gates

### Phase A Exit Gate
- [ ] Sequential routing verified
- [ ] Concurrent routing benchmarked at 1, 2, 4, 8
- [ ] Optimal concurrency selected with evidence
- [ ] Routing correctness unchanged

### Phase B Exit Gate
- [ ] Route cache hit rate measured OR
- [ ] Cache rejected with evidence (<10% hit rate)

### Phase C Exit Gate
- [ ] Driver state repository interface clean
- [ ] Redis implementation works
- [ ] Cross-process scenario PASS
- [ ] Week 1 tests PASS

### Phase D Exit Gate
- [ ] /metrics endpoint works
- [ ] Key stage metrics track
- [ ] No high-cardinality explosion
- [ ] Structured logs useful

### Phase E Exit Gate
- [ ] Timeouts bounded
- [ ] Retries bounded
- [ ] Dependency policies documented
- [ ] No fake fallback

### Phase F Exit Gate
- [ ] Health semantics correct
- [ ] Readiness semantics correct
- [ ] Required vs optional distinction correct
- [ ] Tests PASS

### Phase G Exit Gate
- [ ] Deployment config valid
- [ ] Versions pinned
- [ ] Healthchecks PASS
- [ ] Graceful shutdown checked

### Phase H Exit Gate
- [ ] Redis failure verified
- [ ] Redis recovery verified
- [ ] GraphHopper failure verified
- [ ] GraphHopper recovery verified
- [ ] PostgreSQL failure verified
- [ ] PostgreSQL recovery verified
- [ ] No fake success
- [ ] Evidence recorded

---

## Expected Outcomes

| Metric | Before (Week 5) | After (Week 6 Target) |
|--------|-----------------|------------------------|
| Recommendation P50 (C1) | ~300ms | ~100-150ms |
| Recommendation P90 (C1) | ~350ms | ~200-250ms |
| Candidate Search P50 | ~292ms | ~80-120ms |
| GraphHopper calls avoided | 0 | TBD (if cache) |
| Driver state | Process-local | Shared (Redis) |
| Metrics | Response-only | Prometheus |

---

## Non-Negotiable Constraints

- **No OSRM runtime** — GraphHopper only
- **No Kafka** — No new message broker
- **No Redis Streams** — Standard Redis only
- **No WebSocket push** — Request-response only
- **No new business logic** — Productionization only
- **No mock fallback** — Real dependency failures

---

## Files Expected to Change

### New Files
- `backend/app/services/realtime/driver_state_repository.py`
- `backend/app/core/metrics.py`
- `backend/app/api/v1/metrics.py`
- `docker-compose.prod.yml`
- `docs/WEEK_6.md`
- `docs/PRODUCTIONIZATION_RUNBOOK.md`

### Modified Files
- `backend/app/services/routing/multi_leg.py`
- `backend/app/services/realtime/state.py`
- `backend/app/core/lifespan.py`
- `backend/app/config.py`
- `backend/app/api/v1/health.py`
- `backend/app/api/v1/realtime.py`
- `docker-compose.yml`
- `.env.example`

---

## Timeline

| Phase | Estimated Time |
|-------|---------------|
| Phase A: GraphHopper Optimization | 2-3 hours |
| Phase B: Route Cache (if justified) | 1-2 hours |
| Phase C: Cross-Process Driver State | 3-4 hours |
| Phase D: Observability | 2 hours |
| Phase E: Reliability | 1 hour |
| Phase F: Health/Readiness | 1 hour |
| Phase G: Deployment | 2 hours |
| Phase H: Testing | 3-4 hours |
| **Total** | **15-19 hours** |

---

## Rollback Plan

If any optimization causes regression:

1. **Candidate Search Concurrency:** Set `max_concurrent_routes=1` in config
2. **Route Cache:** Disable with `route_cache_enabled=false`
3. **Driver State:** Revert to in-memory `DriverStateStore`
4. **Metrics:** Disable `/metrics` endpoint

All configurations are environment-variable driven for zero-downtime changes.
