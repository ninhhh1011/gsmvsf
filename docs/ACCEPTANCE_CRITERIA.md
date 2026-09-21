# ACCEPTANCE_CRITERIA

## Dataset V1 Acceptance

Dataset V1 is the canonical development dataset. All acceptance criteria reference it.

### Dataset Validation

Counts were corrected against the canonical V1.3.1 validator executed during migration; Dataset files and validation rules were not changed.

- **152 structural + semantic validation checks**: All PASS
- **22 scenario assertions**: All PASS
- **PBF integrity**: Both hanoi-baseline.osm.pbf and hanoi-patched.osm.pbf byte-for-byte intact
- **Key counts preserved**:
  - 339,441 road nodes
  - 701,407 road segments
  - 60 drivers, 60 vehicles, 150 trips
  - 68,664 true trajectory points
  - 65,847 GPS observations
  - 30 stations
  - 1,200 demand labels (NONE 352 / CHARGING 448 / BATTERY_SWAP 400)
  - 5,029 map-matching selected observations

## Week-by-Week Acceptance

### Week 1 — Map Matching

- GPS observations can be matched to road segments
- Trajectory continuity validated
- Map-matching accuracy meets project thresholds
- Map-matching service (POST /api/v1/map-match) operational

### Week 2 — Demand Detection

- Demand Detection model identifies NONE / CHARGING / BATTERY_SWAP
- Demand Detection (POST /api/v1/demand) operational
- Demand labels preserved from Dataset V1 for evaluation

### Week 3 — Candidate + Routing

- Candidate Search finds all eligible stations
- Routing service computes driver→station and station→destination routes
- ETA, distance, detour computed via road network
- Routing Service (POST /api/v1/route) operational

### Week 4 — Recommendation Model

- Ranking model computes station scores
- Ranking considers ETA, detour, traffic, queue, capacity
- Best Station + Top-N alternatives returned
- Ranking API operational
- Snapshot ingestion persists validated, idempotent history in PostgreSQL
- Request-time resolution, Redis KV/DB fallback and visible freshness verified
- Composite station/service identity and explainable completion cost preserved
- Eligibility-changing state returns HTTP409; ranking never silently filters it
- Synchronous orchestration retries Candidate Search at most once
- Dataset baseline evaluation, real state-change demo and local latency evidence

The user-approved Week 4 extension (ADR-013) includes a synchronous
`POST /api/v1/recommend`, snapshot caching and measurements. It does not complete
Week 5 continuous recommendation or Week 6 productionization.

### Week 5 — Realtime API + Evaluation

- Realtime recommendation API responds within latency targets
- Historical replay evaluation pipeline functional
- Recommendation API (POST /api/v1/recommend) operational

The Week 5 contract was clarified by the project owner on 2026-09-21 (ADR-014):
continuous recommendation means request-driven refresh. Replay/client requests
reuse the existing workflow. No numeric latency SLA is specified; report an
initial local baseline with warmup, measured sample counts, concurrency 1/5/10,
median/P90/P95/max and errors. Correctness, causal historical replay, explicit
dependency failures and bounded retries remain acceptance gates. Production
latency optimization and durable recommendation lifecycle are outside Week 5.

### Week 6 — Productionization

- Latency, caching, monitoring operational
- Deployment documentation complete
- All six weeks integrated

## Critical Rules

1. **Labels are evaluation-only**: recommendation_labels, demand_labels, candidate_labels, ranking_reference must never be consumed as runtime prediction input
2. **Dataset V1 is read-only**: do not modify, regenerate, or move files inside dataset_v1/
3. **Map routing**: Map selection is documented in docs/DECISIONS.md (ADR-006) and runtime configuration. Primary map is set via PRIMARY_PBF_PATH.
4. **Candidate-to-ranking contract**: All Stations -> Candidate Search -> eligible==true -> Ranking -> top-N output
