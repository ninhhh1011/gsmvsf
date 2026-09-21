> Historical baseline: engine-specific instructions and measurements in this document predate the GraphHopper-only migration. Current runtime and verification are documented in [the migration report](GRAPHHOPPER_MIGRATION_REPORT.md).

# Week 1 Freeze

**Date**: 2026-09-17
**Status**: Week 1 Map Matching — COMPLETE

---

## Week 1 Status

| Dimension | Status |
|-----------|--------|
| Functional | PASS |
| Evidence Quality | TRUSTWORTHY |
| Quality | PARTIAL |
| Production Readiness | NOT READY |

---

## Canonical Week 1 Documentation

| Document | Purpose |
|----------|---------|
| `docs/WEEK_1.md` | Primary summary with Phase A/B/C results |
| `docs/WEEK_1_REALTIME_POLICY.md` | Selected policy rationale and parameters |
| `docs/WEEK_1_TECHNICAL_AUDIT.md` | Audit findings and corrections |
| `docs/WEEK_1_ACCEPTANCE_REPORT.md` | External review report |

---

## Current APIs

### Batch Map Matching
```
POST /api/v1/map-match
```

### Realtime GPS
```
POST /api/v1/drivers/{driver_id}/location  — Ingest GPS observation
GET  /api/v1/drivers/{driver_id}/location  — Get driver state
DELETE /api/v1/drivers/{driver_id}/location — Reset driver state
GET  /api/v1/drivers                        — List active drivers
GET  /api/v1/debug/trajectories/{id}       — Load Dataset V1 trajectory
```

### Debug UI
```
http://localhost:8000/debug-map/
```

### Health
```
GET /api/v1/health
GET /api/v1/ready
```

---

## Selected Realtime Policy

**HybridTrigger(10s / 50m)**

```
Trigger:     10s elapsed OR 50m movement
Context:     30 seconds (max 50 points)
Warm-up:     3+ observations before first Match call
Stationary:  Suppress after 3+ consecutive <5m movements
Gap:         Reset after 60s gap
```

**Estimated call rate**: ~7.0 calls/driver/min (based on actual mean trajectory duration of 14.8 min)

---

## Known Technical Debt

| Item | Value | Note |
|------|-------|------|
| Exact segment accuracy | ~36% | Root cause not fully isolated |
| Direction accuracy | ~46% | From road_segments.travel_direction |
| Position error median | 3.91m | Acceptable |
| Position error P95 | 11.84m | Acceptable |
| State persistence | In-memory only | Lost on restart |
| Production TPS proof | Not measured | Extrapolation only |

---

## What Week 2 May Rely On

### Stable Runtime Outputs

Week 2 (Demand Detection) can consume from Week 1:

| Field | Source | Available |
|--------|--------|-----------|
| `driver_id` | Request | Always |
| `raw_position.latitude` | GPS observation | Always |
| `raw_position.longitude` | GPS observation | Always |
| `matched_position.latitude` | OSRM match | When MATCHED |
| `matched_position.longitude` | OSRM match | When MATCHED |
| `road_segment_id` | Segment resolver | When resolved |
| `osm_way_id` | Segment resolver | When resolved |
| `direction` | road_segments.travel_direction | When resolved |
| `status` | DriverTraceState | Always |
| `matched_position.confidence` | OSRM | When MATCHED |
| `timestamp` | GPS observation | Always |

### What Week 2 Must NOT Consume

- Any Dataset V1 labels (demand_labels, candidate_labels, etc.)
- Any evaluation-only artifacts
- Ground truth segment IDs for runtime prediction

---

## What Must NOT Be Modified Casually

1. **Dataset V1** — Canonical dataset, immutable
2. **Road segment schema** — Week 2 routing may depend on segment_id format
3. **Realtime policy parameters** — Changing requires re-benchmarking
4. **DriverTraceState structure** — Week 2 may extend this
5. **OSRM integration** — Changing routing engine requires ADR

---

## Test Baseline

```
backend/tests/test_config.py:       2 tests
backend/tests/test_health.py:      2 tests
backend/tests/test_map_matching.py: 13 tests
backend/tests/test_realtime.py:    24 tests
─────────────────────────────────
Total:                            41 tests PASS
```

---

## Git Tag

```
week1-map-matching-complete
```

---

## Dataset V1 Status

**UNCHANGED** — Byte-for-byte intact

| Check | Result |
|-------|--------|
| gps_observations | 65,847 rows |
| true_trajectories | 68,664 rows |
| road_nodes | 339,441 rows |
| road_segments | 701,407 rows |
| Validation | 163 PASS / 0 FAIL |

---

## Map Status

| Map | Path | Status |
|-----|------|--------|
| Primary | `dataset_v1/map/raw/hanoi-patched.osm.pbf` | APPROVED |
| Reference | `dataset_v1/map/raw/hanoi-baseline.osm.pbf` | Intact |

---

## Week 1 NOT Included

- Week 2 Demand Detection
- Station candidate search
- Routing to stations
- ETA/detour calculation
- Queue/capacity ranking
- Recommendation API
- Production infrastructure (Redis, Kafka, monitoring)

---

## Next Step

**Week 2: Demand Detection**

Ready to plan.
