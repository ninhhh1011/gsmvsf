# Single Driver Mode — Architectural Design Spec

**Date:** 2026-10-08  
**Status:** Approved for implementation  
**Based on:** `docs/reports/driver-only-design-handoff-2026-10-08.md`

## 1. Overview

Replace the three-tab UI (Driver / Simulation / Debug) with a single unified Driver Mode. The new mode owns route selection, synthetic GPS replay, Top 5 station ranking with auto-refresh, hover/click station tooltips, H3 display-only overlay, and energy warnings.

**What is deleted:**
- `sim_mode.js`
- `demo/data/scenarios.json`, `demo/data/trips.json`
- Debug tab and `tech_view.js`
- Scenario bootstrap in `app.js`

**What stays:**
- `driver_controller.js`, `replay.js`, `map.js`, `api.js`
- All renderers in `ui/`
- All domain modules
- `dataset_v1/` and offline evaluation tests

## 2. User Flow

```
[Xe ▼] [SOC] [Chọn A] [Chọn B] [Tìm đường]          [H3]

Bản đồ: tuyến A→B + trạm #1…#5
Danh sách Top 5: hạng, tên, dịch vụ, khoảng cách, chờ, tổng

Hover/Click trạm → tooltip:
  Xe → trạm: {distance}m · {eta}s
  Chờ: {wait}s · Dịch vụ: {service}s
  Trạm → B: {distance}m · {eta}s
  Đi vòng: +{detour}m
  Tổng: {total}s
  [Ghé trạm này]

[Ghé trạm này] → khóa navigation, route A→trạm→B, start GPS replay
[Play/Pause] [1x] [5x] [10x] → điều khiển replay
```

## 3. Key Behaviors

### 3.1 "Tìm đường" Always Runs
- Calls on every user action: initial route, auto-refresh timer, manual button
- Explicit `requested_service` sent to backend
- Works even with sufficient SOC (user intent, not energy-triggered)
- Never auto-selects top 1; user must confirm via "Ghé trạm này"

### 3.2 Top 5 Always Visible
- After "Tìm đường": show up to 5 ranked candidates
- Auto-refresh by timer (configurable, default 30s)
- Manual "Tìm đường" button for immediate refresh
- One shared `recommend` result for list + map + tooltip

### 3.3 Hover/Click = Tooltip, Not Selection
- Hover or click → show tooltip with full metrics
- "Ghé trạm này" button in tooltip → explicit confirmation
- No API calls on hover/click
- No SOC change, no selected station change

### 3.4 H3 = Display Only
- Off by default
- Toggle button only; no API calls
- Computes H3-11 cells from route geometry
- Route change → recompute cells; old cells removed
- Does NOT call backend familiarity endpoint

### 3.5 Synthetic GPS Replay
- Source: GraphHopper route geometry
- Replay owned by Driver controller (not Sim)
- Play/Pause/1x/5x/10x controls
- GPS replay advances trip progress, not driver state

## 4. Data Contract

### 4.1 Top 5 Result

```javascript
{
  request_time: ISO8601,
  candidates: [
    {
      rank: 1,
      station_id: "S001",
      service_type: "BATTERY_SWAP",
      features: {
        distance_to_station_m: 1234,
        eta_to_station_s: 67,
        effective_queue_wait_s: 120,
        queue_assumption: "observed" | "assumed" | null,
        service_duration_s: 300,
        distance_station_to_dest_m: 567,
        duration_station_to_dest_s: 89,
        detour_distance_m: 1100,
        detour_duration_s: 145,
        available_capacity: 10
      },
      eta_to_destination_via_station_s: 571,
      freshness: {
        station_state: "observed" | "stale",
        queue_state: "...",
        traffic_state: "..."
      }
    },
    // ... up to 5
  ],
  freshness: {
    request_time: ISO8601,
    degraded_reasons: []
  }
}
```

### 4.2 Null Handling

| Field | null means | Display |
|---|---|---|
| `effective_queue_wait_s` | No data | "Chưa có dữ liệu" |
| `available_capacity` | Unknown | "—" |
| `queue_assumption` | null | No "(ước tính)" label |

## 5. State Ownership

| State | Owner | Mutations |
|---|---|---|
| Session, A/B, vehicle | Driver controller | User actions only |
| GPS loop, index, clock | Replay (singleton) | Replay internal |
| Route geometry | Driver controller | On route change |
| Selected station + navigation lock | Driver controller | On "Ghé trạm này" |
| Top 5 result | Driver controller | On recommend response |
| H3 overlay | Renderer | On toggle / route change |

### 5.1 Revision Guards

Every async response checks current revision before committing:
- `navigationRevision`: increments on A/B/vehicle/station change
- `recommendationRevision`: increments on recommend call
- `routeRevision`: increments on route geometry change

Stale responses are discarded.

## 6. File Changes

### 6.1 Modified

| File | Change |
|---|---|
| `app.js` | Remove Sim initialization, scenario load, mode tabs; init only DriverModeController |
| `replay.js` | Stabilize loop ownership, retry logic, event-time consistency |
| `driver_controller.js` | Add Top 5 result sharing, auto-refresh, hover tooltip, H3 overlay ownership |
| `cockpit_renderer.js` | Remove scenario list, add Top 5 list, new tooltip template |
| `drawer_renderer.js` | Unified station card for list and tooltip |
| `cockpit_bindings.js` | Rebind: "Tìm đường", H3 toggle, station card clicks |
| `map.js` | Station marker lifecycle from recommend result; H3 overlay rendering |
| `route_familiarity_overlay.js` | Transferred from Sim to Driver; H3-only (no backend familiarity) |

### 6.2 Deleted

| File | Reason |
|---|---|
| `sim_mode.js` | Replaced by unified Driver with synthetic GPS |
| `demo/data/scenarios.json` | Removed from runtime UI |
| `demo/data/trips.json` | Removed from runtime UI |
| `tech_view.js` | Debug-only, no longer needed |

## 7. Testing Requirements

### 7.1 Regression Tests (per handoff section 10)

| # | Test Case | Pass Condition |
|---|---|---|
| 1 | Pin sufficient, click "Tìm đường" | Explicit search called; top 1 NOT auto-selected |
| 2 | 0/1/5 results; station with 2 services | No fake data; composite keys not overwritten |
| 3 | Hover 100× | 0 API calls; SOC/index/selected unchanged |
| 4 | Station offline or unknown capacity | No "Ghé trạm" button; null not shown as 0 |
| 5 | Rapid B changes, responses out of order | Only final revision committed |
| 6 | Select NEW while OLD pending leg-2 | OLD response does NOT overwrite NEW selection |
| 7 | Refresh starts while navigation pending | User navigation NOT cancelled |
| 8 | Pause/Play/reset during ingest | Max 1 loop; no double SOC debit |
| 9 | 429/503/422/STALE injection | Exact attempt count; payload unchanged; index not skipped |
| 10 | Long route, many reroutes | Timestamp monotonic; backend does not reject |
| 11 | 1x/5x/10x real runtime | No test-bypass code in production path |
| 12 | H3 toggle/zoom/route | 0 orchestration calls; old cells removed |
| 13 | Drive to B | COMPLETE fires exactly once |
| 14 | Scenario removal | No scenarios.json load; no Sim instantiation |

### 7.2 Test Approach

- **Unit tests:** Pure functions, revision guards, null handling
- **Integration tests:** API calls with fake clock, deferred barriers
- **Browser tests:** Hover/click UI, H3 toggle, mode transitions
- **E2E:** Real GraphHopper route to B, through multiple rate limit windows

## 8. Constraints

- Do not copy Debug orchestration into Driver
- Do not auto-select top 1
- Do not create fake operational numbers
- Do not add new technology without explicit approval
- Do not modify `dataset_v1/`
- Do not start Week 6 infrastructure
- H3 does NOT call backend familiarity endpoint
- All changes must have regression test evidence

## 9. Open Questions (for ADR if needed)

| Question | Decision Needed |
|---|---|
| Auto-refresh interval | Default 30s; configurable? |
| Retry behavior for recommend | Max 1 retry on 409, or fail fast? |
| H3 cell sampling strategy | Along route geometry segments, cap at 500 cells |
| "Đến B rồi sạc" feature | Keep (if exists), or scope out? |
