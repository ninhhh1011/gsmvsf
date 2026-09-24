# Project Progress — Week 1 to Week 6

**Status:** COMPLETE  
**Last Updated:** 2026-09-24

---

## Executive Summary

6-week EV charging recommendation system delivering real-time station recommendations for VinFast drivers in Hanoi. Built on PostGIS map matching, GraphHopper routing, and PostgreSQL/Redis state management.

| Week | Milestone | Key Deliverable |
|------|-----------|----------------|
| Week 1 | Map Matching | GPS → road segment identification |
| Week 2 | Demand Detection | SOC-based energy service need |
| Week 3 | Candidate Search | Station filtering + multi-leg routing |
| Week 4 | Ranking | Snapshot-aware scoring (traffic, queue, capacity) |
| Week 5 | Realtime API | Request-driven recommendation + evaluation |
| Week 6 | Production | Concurrency + observability + deployment |

---

## Week 1 — Map Matching

**Goal:** GPS observations → road segment identification and direction

### Key Results
- Match rate: 98.8% (247/250 observations)
- Position error: median 3.91m, P95 11.84m
- Selected policy: HybridTrigger(10s / 50m)

### Architecture
```
GPS Observation → HybridTrigger → MapMatcher → Road Segment → MatchedState
```

### Components
- `POST /api/v1/drivers/{driver_id}/location` — GPS ingestion
- `GET /api/v1/drivers/{driver_id}/location` — Current matched position
- PostGIS directed segment resolution

### Tests
- 41 baseline tests for Map Matching
- Realtime policy benchmark on 150 trajectories

---

## Week 2 — Demand Detection

**Goal:** SOC-based energy service need determination

### Key Results
- 19 vehicle models with deterministic capability resolution
- 4 demand reason codes: SUFFICIENT_SOC_RANGE, LOW_SOC, INSUFFICIENT_POST_DESTINATION_RESERVE, DESTINATION_NOT_REACHABLE
- Unified EnergyServiceRequest contract for Week 3

### Architecture
```
Vehicle Telemetry + Trip Context → AutoDemandDetector → EnergyServiceRequest
                                    DriverRequestProcessor ↗
```

### Components
- `AutoDemandDetector` — Physical energy feasibility model
- `VehicleCapabilityResolver` — 19 model deterministic map
- Safety reserve policy: min 1.0km buffer + 15% trip distance

### Tests
- 347 total backend tests (including Week 1 baseline)

---

## Week 3 — Candidate Search + Routing

**Goal:** Find eligible stations, compute routes, ETA, detour

### Key Results
- 30 stations evaluated per request
- Multi-leg routing: driver → station → destination
- GraphHopper 11.0 as sole routing engine

### Architecture
```
EnergyServiceRequest → CandidateSearchService → 30 Station Evaluations
                                                   ↓
                                              GraphHopper Routes
                                                   ↓
                                              EvaluatedCandidate[]
```

### Components
- `POST /api/v1/candidate-search` — Evaluate energy request
- `POST /api/v1/route` — Domain RouteRequest → RouteResult
- Service time: charging 18min, swap 6min

### Eligibility Reasons
```
UNREACHABLE → INCOMPATIBLE → OFFLINE → NO_SWAP_BATTERY → FULL → EXCESSIVE_QUEUE → INSUFFICIENT_SOC_TO_REACH → ELIGIBLE
```

### Tests
- 239 total tests (71 Week 3 specific)

---

## Week 4 — Snapshot-Aware Ranking

**Goal:** Rank candidates by traffic, queue, capacity

### Key Results
- 890,137 snapshot rows imported (traffic, station, queue)
- Immutable PostgreSQL history + Redis latest-payload cache
- TOTAL_SERVICE_COMPLETION_V1 ranking formula

### Architecture
```
Request → SnapshotResolver (DB latest) → CandidateSearch
       → CandidateSearchEvidence (persisted)
       → RankingService → RecommendationResult
```

### Components
- PostgreSQL: `state_snapshots`, `candidate_searches` tables
- Redis: optional latest-payload cache with DB fallback
- Invalidation: HTTP 409 CANDIDATE_STATE_CHANGED

### Tests
- 302 total tests (302 passing)
- Canonical validator: 152 PASS / 0 FAIL

---

## Week 5 — Realtime API + Evaluation

**Goal:** Request-driven recommendation + evaluation

### Key Results
- 308 recommendation requests in replay
- 90.76% recommendation presence agreement
- 85.87% station/service identity agreement

### Architecture
```
GPS/Event → DriverState → Location Bridge → POST /recommend
                                              ↓
                                        EnergyServiceRequest
                                              ↓
                                        Eligible Candidates
                                              ↓
                                        Snapshot-Aware Ranking
                                              ↓
                                        RecommendationResult
```

### Replay Evidence
| Metric | Value |
|--------|-------|
| Trajectories processed | 30 |
| GPS/SOC events | 1,952 |
| Recommendation requests | 308 |
| Success rate | 100% |

### Location Precedence
1. Explicit coordinates (None check)
2. Matched position (Week 1)
3. Raw GPS fallback (RAW_GPS_FALLBACK)
4. Unavailable

### Tests
- 347 backend tests
- 22/22 scenario assertions

---

## Week 6 — Productionization

**Goal:** Optimize latency, observability, deployment

### Key Results
- 38.5% latency reduction (302ms → 186ms P50)
- Prometheus metrics endpoint
- Cross-process driver state via Redis

### Optimizations
| Config | P50 Before | P50 After |
|--------|------------|-----------|
| Sequential routing | 302.81ms | - |
| Concurrent routing (8x) | - | 186.4ms |

### Components
- `GET /api/v1/metrics` — Prometheus metrics
- `GET /health` — Liveness probe
- `GET /ready` — Readiness probe (includes Redis)
- Redis-backed driver state (1hr TTL)

### Prometheus Metrics
- `ev_recommendation_requests_total`
- `ev_graphhopper_route_calls_total`
- `ev_candidate_state_conflicts_total`
- `ev_recommendation_latency_seconds`
- `ev_active_drivers`
- `ev_cache_hit_rate`

### Tests
- 359 total tests

---

## File Structure

```
docs/
├── PROGRESS.md          # This file — consolidated timeline
├── TEST_RESULTS.md      # All test evidence
├── ARCHITECTURE.md      # System architecture
├── PROJECT_SCOPE.md     # Problem statement
├── ACCEPTANCE_CRITERIA.md
├── DATA_CONTRACT.md
└── DECISIONS.md         # Architecture decision records
```

---

## Migration Notes

### OSRM → GraphHopper (Week 3)
- OSRM deprecated in favor of GraphHopper 11.0
- Migration completed 2026-09-21
- OSRM-related files retained as historical reference

### Week 5.5 — Demo UI
- High-fidelity SPA for demonstration
- NOT a production driver application
- Demonstrates Week 1→5 pipeline visually

---

## Remaining Production Gaps

For true production deployment:
1. TLS/HTTPS termination
2. API authentication
3. Rate limiting
4. Resource limits (CPU/memory)
5. Persistent volumes
6. Grafana dashboards
7. Alerting
