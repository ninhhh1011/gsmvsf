# ARCHITECTURE

## Current System (Milestone 0)

```
dataset_v1/
     │
     │ (read-only canonical data)
     ▼
future FastAPI application
     │
     ├──────────────────────────────┐
     ▼                              ▼
PostgreSQL/PostGIS             OSRM
     │                              │
     │                       ┌──────┴──────┐
     │                       ▼             ▼
     │              hanoi-baseline.osm.pbf  hanoi-patched.osm.pbf
     │                   (REFERENCE)      (PRIMARY)
     │                       │
     │                       ▼
     │              osrm-extract → osrm-partition → osrm-customize
     │                       │
     │                       ▼
     │              runtime/osrm/
     │                       │
     │                       ▼
     │              OSRM HTTP API (MLD routing)
```

## Planned Architecture (Weeks 1-6)

```
                    ┌─────────────────────────────────────────┐
                    │              FastAPI Backend            │
                    │            (Modular Monolith)           │
                    └─────────────────────┬───────────────────┘
                                          │
          ┌────────────────────────────────┼────────────────────────────────┐
          │                                │                                │
          ▼                                ▼                                ▼
    MapMatchingService               DemandDetection                  CandidateSearch
    [PLANNED: RoutingEngine]        (Week 2)                         (Week 3)
    (Week 1) ← FROZEN               │                                │
          │                           │                                │
          └───────────────────────────┼────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │       RoutingDomainLayer             │
                    │  RouteRequest → RouteResult          │
                    │  (Week 3 — PLANNED)                  │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┼───────────────────┐
                    │                 │                   │
                    ▼                 ▼                   ▼
              OsrmAdapter      ValhallaAdapter      GraphHopperAdapter
              [CURRENT]        [FUTURE]            [FUTURE]
                    │                 │                   │
                    └────────┬────────┴───────────┬───────┘
                             ▼                    ▼
                    ┌────────────────┐  ┌──────────────────┐
                    │   OSRM HTTP     │  │  External Engine  │
                    │   (MLD/MLD)    │  │   HTTP APIs      │
                    └────────────────┘  └──────────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   StationRanking       │
                         │   (Week 4 — PLANNED)   │
                         └───────────┬─────────────┘
                                     │
                                     ▼
                         ┌─────────────────────────┐
                         │   RecommendationAPI     │
                         │   (Week 5 — PLANNED)   │
                         └─────────────────────────┘
```

### Data Flow (Planned)

```
GPS / Driver State
        │
        ▼
Vehicle Capability / Service Intent
        │
        ▼
Candidate Search (station + service_type pairs)
        │
        ▼
RouteRequest (per candidate)
        │
        ▼
RoutingService (domain)
        │
        ▼
RoutingEngine Adapter (OsrmAdapter, etc.)
        │
        ▼
Engine HTTP API
        │
        ▼
RouteResult
        │
        ▼
Route Metrics + Dynamic Service Metrics
        │
        ▼
RankingPolicy (configurable)
        │
        ▼
Recommendation
```

### Legend

| Component | Status | Notes |
|-----------|--------|-------|
| MapMatchingService | **CURRENT** | Week 1 frozen, OSRM-coupled |
| RoutingDomainLayer | **PLANNED** | Week 3 — RouteRequest → RouteResult |
| OsrmAdapter | **PLANNED** | Week 3 — implements RoutingEngine |
| StationRanking | **PLANNED** | Week 4 |
| RecommendationAPI | **PLANNED** | Week 5 |

## Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Database | PostgreSQL 16 + PostGIS 3 |
| Map Matching / Routing | OSRM (MLD profile) |
| Containers | Docker + Docker Compose |
| Testing | pytest |
| Architecture | Modular Monolith |

## Excluded Technologies

The following are NOT used at Milestone 0 and will not be introduced without demonstrated need:

- Kafka / RabbitMQ / Redis / Celery
- Kubernetes
- Microservices
- Vector DB
- LLM Agent / Multi-Agent

## Week 1 Specifics

Week 1 begins after Milestone 0 passes. Week 1 delivers:
- MapMatchingService
- POST /api/v1/map-match endpoint
- HMM-based map matching algorithm
- Candidate scoring
- Confidence logic
