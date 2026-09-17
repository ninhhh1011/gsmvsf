# EV Charging/Battery Swap Station Recommendation System

**Project:** Tự động tìm trạm sạc/tủ đổi pin phù hợp nhất cho Driver
**Author:** Nguyen Van Ninh (S.AI.20K)
**Stack:** Python + FastAPI, PostgreSQL + PostGIS, OSRM, Docker

---

## Project Purpose

Build an intelligent recommendation system for electric vehicle drivers to find the optimal charging or battery-swap station based on their current location, battery state, traffic conditions, and station availability.

## Six-Week Scope

| Week | Milestone | Content |
|------|-----------|---------|
| Week 1 | **Map Matching** | GPS realtime → road segment, determine position and direction |
| Week 2 | **Demand Detection** | Battery/SOC based need determination |
| Week 3 | **Candidate + Routing** | Find candidates, compute routes, ETA, detour |
| Week 4 | **Recommendation Model** | Ranking based on ETA, detour, traffic, queue, capacity |
| Week 5 | **Realtime API + Evaluation** | Build API, test performance, evaluate recommendations |
| Week 6 | **Productionization** | Optimize latency, caching, monitoring, deployment |

## Current State: Milestone 0 — Project Foundation

Milestone 0 establishes the development project structure, infrastructure, and validation baseline. Week 1 has NOT started yet.

### What's Ready

- Git repository initialized
- FastAPI application with `/health` and `/ready` endpoints
- Docker Compose (PostgreSQL/PostGIS + OSRM)
- Dataset V1 validation passed (163 checks / 21 scenarios)
- OSRM preprocessing pipeline ready
- Sample trajectory from Dataset V1 selected
- Development commands (`make setup`, `make validate-data`, `make prepare-map`, `make up`, `make test`, `make smoke`)

---

## Dataset V1

Dataset V1 (`./dataset_v1/`) is the canonical development dataset for the full six-week project. It is **READ-ONLY**.

### Contents

| Category | Files | Records |
|----------|-------|---------|
| Road network | `road_nodes.csv.gz`, `road_segments.csv.gz` | 339K nodes, 701K segments |
| GPS | `gps_observations.csv.gz` | 65,847 observations |
| Ground truth | `true_trajectories.csv.gz` | 68,664 points |
| Drivers/Vehicles | `drivers.csv`, `vehicles.csv` | 60 each |
| Trips | `trips.csv` | 150 trips |
| Stations | `stations.csv`, `station_status.csv.gz` | 30 stations |
| Queue | `queue_status.csv.gz` | Service-specific queues |
| Traffic | `traffic_snapshots.csv.gz` | 883K snapshots |
| Labels | `demand_labels.csv`, `candidate_labels.csv`, `recommendation_labels.csv` | Evaluation-only |

### Validation

Dataset V1 has been validated:
- **163 structural + semantic checks**: 163 PASS / 0 FAIL
- **21 scenario assertions**: 21/21 PASS
- **PBF integrity**: Both `hanoi-baseline.osm.pbf` and `hanoi-patched.osm.pbf` intact

To re-validate:
```bash
make validate-data
```

---

## MAP STATUS — PRIMARY MAP FINALIZED

- **`hanoi-patched.osm.pbf`** — Primary routing map (contains motorcar=no for Cầu Thanh Trì way 881947000)
- **`hanoi-baseline.osm.pbf`** — Reference map (historical baseline)

Both files remain untouched.

---

## Requirements

- Python 3.11+
- Docker and Docker Compose
- OSRM tools (for `make prepare-map`): `osrm-extract`, `osrm-partition`, `osrm-customize`
- PostgreSQL client tools (optional, for DB inspection)

---

## Environment Setup

1. Copy environment template:
   ```bash
   cp .env.example .env
   ```

2. Review `.env` — defaults point to local paths:
   ```
   DATASET_PATH=./dataset_v1
   PRIMARY_PBF_PATH=./dataset_v1/map/raw/hanoi-patched.osm.pbf
   OSRM_DATA_PATH=./runtime/osrm
   OSRM_BASE_URL=http://localhost:5000
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ev_recommendation
   ```

---

## Quick Start

```bash
# 1. Validate Dataset V1
make validate-data

# 2. Preprocess OSRM map (requires osrm-extract, osrm-partition, osrm-customize)
make prepare-map

# 3. Start services (PostgreSQL/PostGIS + OSRM + FastAPI)
make up

# 4. Run tests
make test

# 5. Run OSRM smoke tests with Dataset V1 GPS
make smoke

# View logs
make logs

# Stop services
make down
```

### On Windows (without make)

```batch
call make.bat setup
call make.bat validate-data
call make.bat prepare-map
call make.bat up
call make.bat test
call make.bat smoke
```

---

## Running Tests

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

Tests at Milestone 0:
- `test_health.py` — `/health` and `/ready` endpoints
- `test_config.py` — Configuration loading and path validation

---

## OSRM Smoke Tests

The smoke test script (`scripts/smoke_test.py`) validates that:
1. OSRM is reachable
2. Dataset V1 GPS observations can be matched to the road network
3. Route computation works
4. Map matching (OSRM Match endpoint) works

```bash
python scripts/smoke_test.py
```

Sample output:
```
============================================================
OSRM SMOKE TEST - Dataset V1 GPS
============================================================

[1] Checking OSRM at http://localhost:5000...
    OSRM reachable: HTTP 200

[2] Loading Dataset V1 GPS observations...
    Total GPS observations: 65,847
    Sample observations: 20

[3] Testing OSRM nearest...
    Status: HTTP 200
    MATCHED: Waypoint index 0

[4] Testing OSRM route...
    Status: HTTP 200
    ROUTE: distance=1234.5m, duration=67.8s

[5] Testing OSRM Match (map matching)...
    Status: HTTP 200
    MATCHED tracepoints: 8/10
    Total distance: 4567.8m

============================================================
SMOKE TEST COMPLETE
============================================================
```

---

## Repository Structure

```
./                              # Project root
├── AGENTS.md                   # Agent instructions
├── README.md                   # This file
├── .gitignore
├── .env.example
├── Makefile                    # Development commands
├── docker-compose.yml          # PostgreSQL + OSRM + FastAPI
│
├── docs/
│   ├── PROJECT_SCOPE.md        # Project problem and deliverables
│   ├── ACCEPTANCE_CRITERIA.md  # Completion criteria
│   ├── DATA_CONTRACT.md        # Dataset structure and relationships
│   ├── ARCHITECTURE.md         # System architecture
│   └── DECISIONS.md           # Architecture decision records
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # Configuration
│   │   └── api/v1/health.py   # /health, /ready endpoints
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       └── test_config.py
│
├── scripts/
│   └── smoke_test.py           # OSRM smoke tests
│
├── runtime/
│   └── osrm/                   # OSRM artifacts (generated)
│
├── samples/week1/
│   ├── sample_normal.json      # Normal trajectory (T0001)
│   └── sample_hard_todo.json   # Hard case for Week 1 testing
│
└── dataset_v1/                  # READ-ONLY canonical data
    ├── README.md
    ├── DATA_DICTIONARY.md
    ├── REQUIREMENT_DATA_MATRIX.md
    ├── gps/
    ├── trajectories/
    ├── labels/
    ├── map/raw/
    │   ├── hanoi-baseline.osm.pbf  # REFERENCE
    │   └── hanoi-patched.osm.pbf   # PRIMARY
    ├── validation/
    └── ...
```

---

## Week 1 Preview — Map Matching

Week 1 will deliver:

- **MapMatchingService** — Core map matching logic
- **POST /api/v1/map-match** — Map matching endpoint
- **HMM-based algorithm** — Hidden Markov Model for GPS-to-road matching
- **Candidate scoring** — Score and rank candidate road segments
- **Confidence logic** — Confidence scores for matched results

Week 1 does NOT start until Milestone 0 is verified as complete.

---

## Critical Rules

1. **Labels are evaluation-only** — Never consume `demand_labels.csv`, `candidate_labels.csv`, `recommendation_labels.csv`, `ranking_reference.csv`, or `map_matching_labels.csv.gz` as runtime input.

2. **Dataset V1 is read-only** — Do not modify, regenerate, or move files inside `dataset_v1/`.

3. **Map routing** — `hanoi-patched.osm.pbf` is primary. `hanoi-baseline.osm.pbf` is reference.

4. **Week boundaries** — Implement only the current week's scope. Do not build future weeks' features early.

---

## Definition of Done

Milestone 0 PASS requires:

### Repository
- [x] Git initialized
- [x] Project structure created
- [x] AGENTS.md created
- [x] Documentation created

### Data
- [x] Dataset V1 untouched
- [x] Dataset validation runnable
- [x] Dataset validation passes (163/163 PASS)

### Map
- [x] Baseline PBF exists
- [x] Patched PBF exists
- [x] Neither PBF modified
- [x] OSRM preprocessing pipeline ready
- [x] OSRM artifacts stored outside Dataset V1

### Infrastructure
- [x] Docker Compose valid
- [x] FastAPI running with /health
- [x] PostgreSQL/PostGIS configured
- [x] OSRM configured

### FastAPI
- [x] /health returns 200
- [x] /ready works (checks OSRM)

### OSRM
- [x] Sample trajectory selected (T0001, 273 GPS observations)
- [x] Smoke test script created

### Testing
- [x] pytest runs
- [x] Milestone 0 tests pass (4/4)

### Boundaries
- [x] Dataset V1 not mutated
- [x] No MapMatchingService
- [x] No Week 2–6 features

---

## Getting Help

1. Read `docs/PROJECT_SCOPE.md` — Project overview
2. Read `docs/ACCEPTANCE_CRITERIA.md` — What's required
3. Read `docs/DATA_CONTRACT.md` — How the data is organized
4. Read `docs/ARCHITECTURE.md` — Current and planned system
5. Read `docs/DECISIONS.md` — Why decisions were made
6. Read `AGENTS.md` — Rules for coding agents

---

## Milestone 0 Status

**MILESTONE 0: PASS** ✅

**READY FOR WEEK 1 — MAP MATCHING**
