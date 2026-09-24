# Final Architecture

**Status:** VERIFIED  
**Date:** 2026-09-24  
**Phase:** Phase 5 — Demo Hardening

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Browser                                     │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────┐  │
│  │         Product UI              │  │       Technical View         │  │
│  │  (Driver Mode + Sim Mode)      │  │  (Pipeline Inspector)       │  │
│  └──────────────┬──────────────────┘  └──────────────┬────────────┘  │
│                 │                                      │               │
│                 └──────────────┬───────────────────────┘               │
│                                │                                       │
│                    HTTP/REST API /demo                                │
└────────────────────────────────┼───────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │         FastAPI          │
                    │     (backend/app/)       │
                    └────────────┬────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    ┌────┴────┐           ┌─────┴─────┐          ┌────┴────┐
    │ GraphHopper│         │PostgreSQL │          │  Redis  │
    │   11.0   │          │/PostGIS   │          │  7.4    │
    └──────────┘           └───────────┘          └─────────┘
```

---

## 2. Component Responsibilities

### Browser (Frontend)
- **Vanilla ES6 JavaScript modules** served by FastAPI
- **Leaflet 1.9.4** for map rendering
- No business logic — pure UI rendering of backend responses
- Two modes: **Product UI** (driver-facing) and **Technical View** (pipeline inspection)

### FastAPI Backend
- Request-driven recommendation orchestration
- Owns all business logic: demand detection, candidate search, ranking
- Routes through to GraphHopper, PostgreSQL, and Redis
- Health and readiness endpoints

### GraphHopper 11.0
- **Sole routing engine** for path computation
- **Sole map-matching engine** for GPS projection
- No fallback, no mock in production paths
- Motorcycle routing uses `car_access` (excludes `motorcar=no` ways)

### PostgreSQL/PostGIS 16
- Road segment storage and spatial queries
- Snapshot persistence (traffic, queue, station state)
- Candidate search evidence storage
- Database is **authoritative** for operational state

### Redis 7.4
- **Shared driver state** (matched position, raw GPS, observations)
- **Optional cache** for latest snapshot payloads (PostgreSQL is authoritative)
- Driver state is authoritative in Redis for production multi-instance deployments
- No automatic fallback to local memory when Redis is unavailable (prevents split-brain)

---

## 3. Data Flow

```
GPS Observation
      │
      ▼
┌─────────────────┐
│  Map Matching   │──────────────► GraphHopper /match
│  (Week 1)       │
└────────┬────────┘
         │ matched_position
         ▼
┌─────────────────┐
│ Demand Detection│──────────────► EnergyServiceRequest
│ (Week 2)        │               (need_service, reason_code)
└────────┬────────┘
         │ eligible service types
         ▼
┌─────────────────┐
│Candidate Search │──────────────► GraphHopper /route (61 calls)
│ (Week 3)        │──────────────► PostgreSQL snapshots
└────────┬────────┘
         │ eligible candidates
         ▼
┌─────────────────┐
│    Ranking      │──────────────► TOTAL_SERVICE_COMPLETION_V1
│ (Week 4)        │               (eta + queue_wait + service_duration)
└────────┬────────┘
         │ ranked candidates
         ▼
┌─────────────────┐
│ Recommendation  │──────────────► RecommendationResult
│ (Week 5)        │
└─────────────────┘
```

---

## 4. API Boundaries

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Application liveness |
| `/ready`, `/readiness` | GET | Dependency readiness (GraphHopper, PostGIS, Redis) |
| `/demo`, `/demo/` | GET | Product UI |
| `/demo/technical` | GET | Technical View |
| `/api/v1/map-match` | POST | Batch GPS matching |
| `/api/v1/drivers/{id}/location` | POST/GET/DELETE | Realtime driver location |
| `/api/v1/demand` | POST | Demand evaluation |
| `/api/v1/candidate-search` | POST | Evaluate station alternatives |
| `/api/v1/candidate-search/evaluate` | POST | Demand + candidate search |
| `/api/v1/route` | POST | Route computation |
| `/api/v1/recommend` | POST | Full pipeline (location → demand → search → ranking) |

---

## 5. Technology Stack

| Technology | Purpose | Status |
|---|---|---|
| FastAPI | Web framework | **PRODUCTION** |
| GraphHopper 11.0 | Routing & matching | **PRODUCTION** (sole engine) |
| PostgreSQL 16/PostGIS | Road data, snapshots | **PRODUCTION** |
| Redis 7.4 | Optional cache, driver state | **PRODUCTION** (cache mode) |
| asyncpg | Async PostgreSQL driver | **PRODUCTION** |
| psycopg2-binary | Sync PostgreSQL reads | **PRODUCTION** |
| httpx | Async HTTP client | **PRODUCTION** |
| Leaflet 1.9.4 | Map rendering | **PRODUCTION** |
| Docker Compose | Container orchestration | **DEVELOPMENT** |

### Removed Technologies
| Technology | Reason |
|---|---|
| SQLAlchemy | Never used (Phase 1 removal) |
| OSRM | Superseded by GraphHopper (historical) |

---

## 6. Key Architecture Rules

1. **No business logic in frontend** — All decisions (demand, eligibility, ranking) are backend-owned
2. **GraphHopper is sole routing engine** — No fallback, no mock in production
3. **PostgreSQL is authoritative** — Redis is optional cache only
4. **Dataset V1 is immutable** — Read-only canonical data
5. **Composite candidate identity** — `(station_id, service_type)` preserved throughout
6. **Honest failure modes** — 503 for GraphHopper unavailable, not "no candidates found"
7. **Request-driven** — No background workers, no push/streaming
8. **Snapshots are immutable** — Traffic/queue/station snapshots stored with timestamps

---

## 7. Limitations

1. **Motorcycle routing** — Uses `car_access`, so `motorcar=no` excludes motorcycles
2. **Matching quality** — Geometric proximity, not calibrated probability
3. **No production SLA** — Local measurements only
4. **No multi-driver orchestration** — Driver state is keyed/shared per driver ID, and Redis
   supports multiple driver records. However, cross-driver coordination (e.g., load-aware
   multi-driver routing) or multi-driver recommendation workflows are outside current scope.
5. **Request-driven refresh** — No continuous background recommendation

---

## 8. Historical Context

- **Week 1-3**: Map matching, demand detection, candidate search with GraphHopper migration
- **Week 4**: Snapshot-aware ranking with PostgreSQL persistence
- **Week 5**: Request-driven realtime API with causal evaluation
- **Week 5.5**: Demo UI (Product + Technical views)
- **Phase 4**: Technical View implementation
- **Phase 5**: Demo hardening and release readiness (current)

OSRM references in documentation are **historical** and superseded by GraphHopper.
