# Week 1 — Map Matching

## Official Goal

GPS observations → road segment identification and direction

## Current Status

**WEEK 1 = COMPLETE** ✅

### Phase A: Batch Map Matching — COMPLETE
### Phase B: Realtime Policy Benchmark — COMPLETE
### Phase C: Realtime Implementation — COMPLETE

---

## Phase A: Batch Map Matching

### FINAL EVALUATION RESULTS (Phase A)

| Metric | Value | Notes |
|--------|-------|-------|
| **Match Rate** | 98.8% | 247/250 observations matched |
| **Segment Resolution Rate** | 100% | 247/247 matched resolved |
| **Segment Accuracy** | 36.0% | 89/247 predicted == true |
| **Direction Accuracy** | 46.2% | 114/247 predicted == true |
| **Position Error Mean** | 4.65m | Distance to true position |
| **Position Error Median** | 3.91m | 50th percentile |
| **Position Error P95** | 11.84m | 95th percentile |
| **Position Error Max** | 20.21m | Worst case |

---

## Phase B: Realtime Policy Benchmark

### Native GPS Sampling (Dataset V1)

| Metric | Value |
|--------|-------|
| Total observations | 65,847 |
| Total trajectories | 150 |
| Median delta | 1.87s |
| P90 delta | 2.92s |
| P95 delta | 3.35s |
| P99 delta | 5.97s |
| Max delta | 14.69s |

### Policy Comparison (10 trajectories, 3,845 observations)

| Policy | Calls/Traj | Obs/Call | Latency Mean | Est. Calls/Driver/Min |
|--------|------------|----------|--------------|----------------------|
| TimeTrigger(5s) | 122.5 | 3.1 | 599ms | ~2.0 |
| TimeTrigger(10s) | 65.9 | 5.8 | 331ms | ~1.1 |
| TimeTrigger(15s) | 45.9 | 8.4 | 350ms | ~0.8 |
| DistanceTrigger(20m) | 208.4 | 1.8 | 303ms | ~3.5 |
| DistanceTrigger(50m) | 103.7 | 3.7 | 315ms | ~1.7 |
| DistanceTrigger(100m) | 56.6 | 6.8 | 441ms | ~0.9 |
| **HybridTrigger(10s/50m)** | **103.9** | **3.7** | **371ms** | **~1.7** |
| HybridTrigger(5s/30m) | 160.8 | 2.4 | 340ms | ~2.7 |
| HybridTrigger(15s/100m) | 57.4 | 6.7 | 440ms | ~1.0 |

### Selected Policy: HybridTrigger(10s / 50m)

**Why:**
1. Balanced call volume (~104 calls/traj ≈ ~7.0 calls/driver/min based on actual mean trajectory duration of 14.8 min)
2. Good observation batching (~3.7 obs/call reduces per-call overhead)
3. Time + distance coverage catches both slow and fast drivers
4. Not too aggressive (avoids 5s-only triggers)
5. Not too conservative (avoids stale 100m-only triggers)

**Note**: Earlier estimates used ~60 min trajectory duration. Actual Dataset V1 durations: mean 14.8 min, median 15.0 min, range 5.0-24.3 min. Corrected call rate is ~7.0 calls/driver/min.

---

## Phase C: Realtime Implementation

### API Endpoints

#### POST /api/v1/drivers/{driver_id}/location
Ingest single GPS observation.

**Request:**
```json
{
  "timestamp": "2026-09-01T06:00:00+07:00",
  "latitude": 21.103793,
  "longitude": 106.002398,
  "speed_kmh": 25.5,
  "heading_deg": 90.0
}
```

**Response:**
```json
{
  "driver_id": "D001",
  "status": "MATCHED",
  "trigger_reason": "TIME(10.5s>=10.0s)",
  "raw_position": {
    "latitude": 21.103793,
    "longitude": 106.002398,
    "timestamp": "2026-09-01T06:00:10Z"
  },
  "matched_position": {
    "latitude": 21.103802,
    "longitude": 106.002381,
    "road_segment_id": "651937125_5_R",
    "osm_way_id": 651937125,
    "direction": "REVERSE",
    "confidence": 0.95
  },
  "last_match_time": "2026-09-01T06:00:10Z",
  "last_match_latency_ms": 312.5,
  "total_observations": 5,
  "total_match_calls": 2,
  "buffered_points": 5,
  "movement_since_match_m": 125.3,
  "is_stationary": false
}
```

#### GET /api/v1/drivers/{driver_id}/location
Get current driver state.

#### GET /api/v1/drivers
List all active drivers.

#### DELETE /api/v1/drivers/{driver_id}/location
Reset driver state.

#### GET /api/v1/debug/trajectories/{trajectory_id}
Load Dataset V1 trajectory for replay.

### Status Values

| Status | Meaning |
|--------|---------|
| WARMING_UP | Collecting initial observations (<3) |
| GPS_ACCEPTED | Observation received, no match triggered |
| MATCHED | Map matching triggered and succeeded |
| PARTIAL_MATCH | Some points matched |
| NO_MATCH | OSRM returned no match |
| INVALID_GPS | Invalid observation data |
| STALE_OBSERVATION | Timestamp before last observation |
| GAP_RESET | Session reset due to large gap |
| ENGINE_UNAVAILABLE | OSRM not reachable |

### Policy Parameters

```
Trigger: 10s elapsed OR 50m movement (whichever first)
Context Window: 30 seconds (last ~15 points at native 2s sampling)
Max Context Points: 50
Warm-up: 3+ observations before first Match call
Stationary Suppression: 3+ consecutive observations with <5m movement
Gap Threshold: 60s → session reset
```

---

## Debug UI

**URL**: http://localhost:8000/debug-map/

**Features:**
- Trajectory selection from Dataset V1
- Play/Pause/Reset controls
- Speed control (1x to 100x)
- Step-by-step observation replay
- Raw GPS point visualization
- Matched point visualization
- Route geometry display
- Current position markers
- State panel with all metrics
- Event log with trigger reasons

**Requires**: Internet for Leaflet map tiles

---

## Tests

| Suite | Tests | Result |
|-------|-------|--------|
| `backend/tests/test_map_matching.py` | 13 | PASS |
| `backend/tests/test_realtime.py` | 24 | PASS |
| **Total** | **37** | **PASS** |

---

## API Contract

### Realtime Endpoint
- `POST /api/v1/drivers/{driver_id}/location`
- `GET /api/v1/drivers/{driver_id}/location`
- `DELETE /api/v1/drivers/{driver_id}/location`
- `GET /api/v1/drivers`
- `GET /api/v1/debug/trajectories/{trajectory_id}`

### Batch Endpoint (Phase A)
- `POST /api/v1/map-match`

---

## Architecture

```
GPS Observation Stream
        ↓
POST /api/v1/drivers/{driver_id}/location
        ↓
DriverTraceState (in-memory)
        ↓
Trigger Policy (HybridTrigger 10s/50m)
        ↓
Context Window (30s, max 50 points)
        ↓
OSRM Match
        ↓
Matched State
        ↓
Response + State Update
```

---

## Known Limitations

1. **In-memory state only**: No persistence across restarts
2. **No Redis/Kafka**: Week 1 uses simple in-memory store
3. **Segment accuracy 36%**: OSRM often matches parallel roads
4. **Direction accuracy 46%**: Per-segment direction may not match travel direction
5. **No external GPS preprocessing**: Only Dataset V1 tested

---

## Scope Exclusions

- Custom HMM implementation
- Valhalla/GraphHopper integration
- Week 2+ Demand Detection
- Station candidate search
- Charging/Battery swap recommendation

---

## Files Changed

### New Files
- `backend/app/services/realtime/__init__.py`
- `backend/app/services/realtime/state.py`
- `backend/app/services/realtime/trigger.py`
- `backend/app/api/v1/realtime.py`
- `backend/app/static/debug-map/index.html`
- `backend/tests/test_realtime.py`
- `scripts/benchmark_realtime_map_matching.py`
- `scripts/replay_realtime.py`
- `docs/WEEK_1_REALTIME_POLICY.md`
- `docs/WEEK_1_REMAINING_PLAN.md`

### Modified Files
- `backend/app/main.py`
- `backend/app/config.py`

---

## Dataset V1

**UNCHANGED** - All files intact, no modifications

---

## STATUS

```
WEEK 1 PHASE A = PASS ✅
WEEK 1 PHASE B = PASS ✅
WEEK 1 PHASE C = PASS ✅

WEEK 1 = COMPLETE ✅

READY FOR WEEK 2 — DEMAND DETECTION
```
