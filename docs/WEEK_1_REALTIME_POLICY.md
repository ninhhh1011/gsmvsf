> Historical baseline: engine-specific instructions and measurements in this document predate the GraphHopper-only migration. Current runtime and verification are documented in [the migration report](GRAPHHOPPER_MIGRATION_REPORT.md).

# Week 1 Realtime Policy

## Selected Baseline Policy

**HybridTrigger(10s / 50m)**

## Evidence Summary

### Native GPS Sampling (Dataset V1)
- Median: 1.87s
- P90: 2.92s
- P95: 3.35s
- P99: 5.97s
- Max: 14.69s

### Policy Comparison (10 trajectories, 3,845 observations)

| Policy | Calls/Traj | Obs/Call | Latency Mean | Latency P95 | Est. Calls/Driver/Min |
|--------|------------|----------|--------------|-------------|----------------------|
| TimeTrigger(5s) | 122.5 | 3.1 | 599ms | 303ms | ~2.0 |
| TimeTrigger(10s) | 65.9 | 5.8 | 331ms | 312ms | ~1.1 |
| TimeTrigger(15s) | 45.9 | 8.4 | 350ms | 304ms | ~0.8 |
| DistanceTrigger(20m) | 208.4 | 1.8 | 303ms | 310ms | ~3.5 |
| DistanceTrigger(50m) | 103.7 | 3.7 | 315ms | 306ms | ~1.7 |
| DistanceTrigger(100m) | 56.6 | 6.8 | 441ms | 319ms | ~0.9 |
| **HybridTrigger(10s/50m)** | **103.9** | **3.7** | **371ms** | **308ms** | **~1.7** |
| HybridTrigger(5s/30m) | 160.8 | 2.4 | 340ms | 312ms | ~2.7 |
| HybridTrigger(15s/100m) | 57.4 | 6.7 | 440ms | 315ms | ~1.0 |

### Request Rate Estimates (Extrapolated)

| Drivers | Calls/Day (Hybrid 10s/50m) |
|---------|------------------------------|
| 1 | ~2,500 |
| 100 | ~250,000 |
| 1,000 | ~2.5M |
| 10,000 | ~25M |

*Estimates based on ~3,845 obs/10 trajectories ≈ 385 obs/trajectory. Real-world GPS frequency may vary.*

## Why HybridTrigger(10s/50m)?

1. **Balanced call volume**: ~104 calls/traj ≈ ~7.0 calls/driver/min (using actual mean trajectory duration of 14.8 min)
2. **Good observation batching**: ~3.7 obs/call reduces per-call overhead
3. **Time + distance coverage**: Catches both slow-moving and fast-moving drivers
4. **Not too aggressive**: Avoids high-frequency 5s-only triggers
5. **Not too conservative**: Avoids stale 100m-only triggers that miss urban driving

**Note**: Previous estimates used ~60 min trajectory duration. Actual Dataset V1 durations: mean 14.8 min, median 15.0 min, range 5.0-24.3 min. Corrected call rate is ~7.0 calls/driver/min.

### Alternatives Considered

- **TimeTrigger(10s)**: Good but pure time-only may miss rapid movement
- **DistanceTrigger(50m)**: Good but pure distance may over-trigger in slow traffic
- **HybridTrigger(15s/100m)**: More conservative, may be too stale for urban driving

## Policy Parameters

```
Trigger: 10s elapsed OR 50m movement (whichever first)
Context Window: 30 seconds (last ~15 points at native 2s sampling)
Max Context Points: 50
Warm-up: 3+ observations before first Match call
Stationary Suppression: 3+ consecutive observations with <5m movement
Gap Threshold: 60s → session reset
```

## Implementation Notes

- GPS observations ingested as received (native sampling)
- Context sent to OSRM includes recent window, not full trajectory
- Stationary suppression prevents redundant calls during stops
- Gap reset prevents connecting unrelated driving sessions
