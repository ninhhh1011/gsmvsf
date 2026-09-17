# Week 1 Remaining Plan — Phases B & C

## Phase B: Realtime Policy Benchmark

### B1 — Measure Native GPS Sampling ✅
**Status**: MEASURED

- **Total observations**: 65,847 across 150 trajectories
- **Median delta**: 1.87s
- **P90 delta**: 2.92s
- **P95 delta**: 3.35s
- **P99 delta**: 5.97s
- **Max delta**: 14.69s
- **Distribution**:
  - 10.3% at 0-1s
  - 49.0% at 1-2s
  - 31.9% at 2-3s
  - 7.4% at 3-5s
  - 1.2% at 5-10s
  - 0.2% at 10-14.69s
- **Conclusion**: Native sampling is ~2s; 96%+ of observations arrive within 3s of previous

### B2 — Sampling + Context Window Benchmark
**Files**: `scripts/benchmark_realtime_map_matching.py`

Benchmark variants:
- Native (as received)
- 2s downsampled
- 3s downsampled
- 5s downsampled (only for comparison)

Context windows:
- 10s (last ~5 points native)
- 20s (last ~10 points native)
- 30s (last ~15 points native)

### B3 — Time Trigger Benchmark
Test candidates:
- 5s elapsed (near P95)
- 10s elapsed (2× median)
- 15s elapsed (beyond P99)

Metrics: match rate, accuracy, latency, calls/min/driver

### B4 — Distance Trigger Benchmark
Test candidates:
- 20m movement (urban scale)
- 50m movement (block scale)
- 100m movement (intersection scale)

### B5 — Hybrid Trigger Benchmark
Based on B3/B4 evidence, test:
- 5s OR 30m
- 10s OR 50m
- 15s OR 100m

### B6 — Stationary Optimization
Measure wasted calls during stationary periods (speed < 2 m/s between consecutive obs)

### B7 — Policy Selection
**Output**: `docs/WEEK_1_REALTIME_POLICY.md`

---

## Phase C: Realtime Implementation

### C1 — Per-Driver Trace State
**Files**: `backend/app/services/realtime/state.py`
- `DriverTraceState` class with bounded deque
- State fields: observations, last_match_time, movement_since_match, last_matched_state

### C2 — Realtime GPS Ingestion API
**Files**: `backend/app/api/v1/realtime.py`
- `POST /api/v1/drivers/{driver_id}/location` — single GPS observation
- Validation, append to state, trigger evaluation

### C3 — Trigger Policy Implementation
**Files**: `backend/app/services/realtime/trigger.py`
- `TimeTrigger`, `DistanceTrigger`, `HybridTrigger` policies
- Policy selected in B7

### C4 — Current Matched State
**Files**: `backend/app/api/v1/realtime.py`
- `GET /api/v1/drivers/{driver_id}/location` — current state

### C5 — Gap/Session Reset
Threshold from B1 evidence: gap > 60s triggers state reset

### C6 — Stationary Suppression
Suppress Match calls when movement < 5m between consecutive obs and speed unreliable

### C7 — OSRM Failure Handling
Return NO_MATCH status, preserve raw GPS in state

### C8 — Realtime Replay
**Files**: `scripts/replay_realtime.py`
- Load Dataset V1 trajectory
- Send through API in timestamp order
- Accelerated replay (no real-time waits)

### C9 — External GPS Support (Optional)
Skip if data not ready

---

## Debug UI

### UI1 — Map Viewer
**Files**: `backend/app/static/debug-map/`
- MapLibre GL JS or Leaflet
- OpenStreetMap tiles (requires internet)

### UI2 — GPS Replay Controls
- Play/Pause/Reset
- Speed: 1x, 5x, 10x
- Step observation

### UI3 — Visualization Layers
- Raw GPS points
- Matched points
- Route geometry
- Current positions

### UI4 — Runtime State Panel
- Driver ID, trajectory
- Raw/matched positions
- Status, road segment, direction
- Trigger reason
- Latency metrics

---

## PASS Conditions

### Phase B
- [x] Dataset sampling measured
- [ ] Replay harness implemented
- [ ] Sampling benchmark completed
- [ ] Context window benchmark completed
- [ ] Time trigger benchmark completed
- [ ] Distance trigger benchmark completed
- [ ] Hybrid benchmark completed
- [ ] Stationary behavior measured
- [ ] One policy selected

### Phase C
- [ ] Per-driver state implemented
- [ ] GPS ingestion endpoint operational
- [ ] Trigger policy implemented
- [ ] Current state endpoint operational
- [ ] Gap/reset behavior implemented
- [ ] Stationary suppression implemented
- [ ] OSRM failure handled
- [ ] Replay script works
- [ ] All tests pass

### Final
- [ ] Dataset V1 validation passes
- [ ] Backend tests pass
- [ ] Integration tests pass
- [ ] Replay evaluation passes
- [ ] Week 1 docs updated
