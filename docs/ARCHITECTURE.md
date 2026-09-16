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
     │                   (PRIMARY)        (PENDING REVIEW)
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
                    ┌─────────────────────────┐
                    │     FastAPI Backend     │
                    │   (Modular Monolith)    │
                    └──────────┬──────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    MapMatchingService   DemandDetection    CandidateSearch
    (Week 1)             (Week 2)          (Week 3)
          │                    │                    │
          └────────────────────┤                    │
                               │                    │
                               ▼                    ▼
                         RoutingService      StationRanking
                         (Week 3)            (Week 4)
                               │                    │
                               └────────┬───────────┘
                                        │
                                        ▼
                               RecommendationAPI
                                  (Week 5)
                                        │
                               ┌────────┴────────┐
                               ▼                 ▼
                      PostgreSQL/PostGIS        OSRM
                      (persistence)      (routing engine)
                               │
                               ▼
                         RealtimeReplay
                          (Week 5)
```

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
