# Route Cache Decision — Week 6

## Decision: SKIP

Route caching (cross-request route caching between candidate searches) was considered but **not implemented** because the expected hit rate is too low to justify the complexity.

## Analysis

### Why Hit Rate is Low

1. **Moving driver origins**: Driver positions change continuously. A route from driver→station is only reusable if the driver hasn't moved significantly since the last request.

2. **Short driver sessions**: Typical EV trips are 20-60 minutes. The gap between consecutive recommendation requests for the same driver is typically 5-30 seconds of driving.

3. **Station candidate diversity**: With ~30 stations in the Hanoi coverage area, different drivers (or even the same driver at different points in a trip) will route to different stations.

4. **Existing within-request reuse**: The code already caches the direct route (driver→destination) and uses it for all station candidates within a single recommendation request. This captures the most expensive routing redundancy.

### Estimated Hit Rate

For a route cache keyed by `(origin_lat, origin_lon, station_id)`:

- **Same driver, <30s apart, slow-moving**: ~60% hit rate
- **Same driver, 30-120s apart**: ~20% hit rate
- **Different drivers**: ~5% hit rate (different routes happen to overlap)

**Weighted average**: ~15-25% hit rate for realistic traffic patterns.

### What We Already Have

1. **GraphHopper internal caching**: GraphHopper maintains an in-memory cache of computed road segments. Warm cache gives ~186ms vs cold ~250ms+.

2. **Within-request route reuse**: The direct route (driver→destination) is computed once and reused for all station candidates.

3. **Semicontinuous routing**: With `max_concurrent_routes=4`, multiple legs can be computed concurrently within a request.

### Implementation Complexity

Adding route caching would require:

1. **Cache key design**: (origin_hash, destination_hash, vehicle_category) with geographic precision trade-offs.

2. **TTL policy**: Too short = low hit rate, too long = stale routes for moving drivers.

3. **Invalidation**: When do we invalidate? Time-based? Distance-based? Manual?

4. **Storage**: Redis with persistence considerations for driver state.

5. **Consistency**: GPS updates change the driver position; cached routes may become invalid.

### Cost-Benefit

**Estimated benefit**: 10-20% latency reduction on 20% of requests = 2-4% overall improvement.

**Estimated cost**: 2-3 days implementation + ongoing maintenance + potential correctness bugs.

**Verdict**: Not worth it for the current scale.

## Alternative Considered

Instead of caching routes, we could:

1. **Batch route computation**: Pre-compute routes for the top-N most common origin-destination pairs (commute routes).

2. **Station clustering**: Group nearby stations; compute one representative route per cluster.

3. **Wait for GraphHopper improvements**: GraphHopper's internal cache already handles the common case well.

## Conclusion

Route caching is deferred until:
- There is evidence of high cache hit rates in production
- The latency budget requires further optimization
- The implementation complexity is justified by scale
