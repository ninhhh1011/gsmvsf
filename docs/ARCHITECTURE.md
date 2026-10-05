# System Architecture

## High-Level Architecture

### Week 1-6 Components

| Week | Component | File | Description |
|------|-----------|------|-------------|
| 1 | Map Matching | `services/map_matching/` | GPS → road segments |
| 2 | Demand Detection | `services/demand/` | SOC evaluation |
| 3 | Candidate Search | `services/candidate/` | Station filtering |
| 4 | Ranking | `services/ranking/` | ML scoring |
| 5 | Realtime API | `api/v1/realtime/` | GPS ingestion |
| 6 | Production | `core/monitoring/` | Metrics, caching |

### Scale Up: Route History

| Feature | File | Description |
|---------|------|-------------|
| H3 Signature | `route_history/signature.py` | Convert routes to H3 cells |
| Similarity | `route_history/similarity.py` | Compare route similarity |
| Bayesian Penalty | `route_history/familiarity.py` | Intelligent penalty |

## Data Flow

1. Driver GPS → Realtime API
2. Demand Detection (SOC evaluation)
3. Candidate Search (nearby stations)
4. Routing (GraphHopper)
5. Ranking (ML model)
6. Response

## Technology Stack

- **Backend**: FastAPI, Python 3.10+
- **Routing**: GraphHopper
- **Database**: PostgreSQL
- **Cache**: Redis
- **Monitoring**: Prometheus, Grafana
- **Spatial Index**: H3 (Uber)

## External Dependencies

| Service | Purpose | SLA |
|---------|---------|-----|
| GraphHopper | Routing | 99.9% |
| PostgreSQL | Data storage | 99.9% |
| Redis | Caching | 99.5% |

## Key Design Decisions

### 1. Snapshot-based State
Traffic, queue, and station states are snapshotted hourly.
Benefits: replay-ability, debugging, backtesting.

### 2. H3-based Route Comparison
Routes compared using H3 Resolution 10-11 hexagons.
Benefits: efficient spatial indexing, direction-aware.

### 3. Bayesian Familiarity Penalty
Driver deviation penalized based on population agreement.
Benefits: smarter routing for habitual routes.
