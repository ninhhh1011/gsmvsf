# Route History Scale - Implementation Plan

## Implementation Phases

### Phase 2: Route Family Clustering
- [ ] Incremental family assignment
- [ ] Representative route selection (medoid)
- [ ] Configurable similarity threshold
- [ ] Weighted family support (time × recency)
- [ ] Tests for family boundary cases

### Phase 3: PostgreSQL Persistence
- [ ] historical_routes table
- [ ] historical_route_segments table
- [ ] historical_route_h3 table
- [ ] route_families table
- [ ] route_family_members table
- [ ] Inverted index backed by PostgreSQL
- [ ] Migration scripts

### Phase 4: Historical Familiarity Feature
- [ ] Bounded familiarity penalty
- [ ] Configurable weight and cap
- [ ] Graceful fallback when no history
- [ ] Integration into ranking

### Phase 5: Recommendation Pipeline Integration
- [ ] Feature flag ENABLE_ROUTE_FAMILIARITY
- [ ] Pipeline hook for historical context
- [ ] No candidate eligibility changes based on familiarity

### Phase 6: API Endpoints
- [ ] GET /route-similarity
- [ ] GET /route-families
- [ ] GET /driver-habitual-routes

### Phase 7: End-to-End Validation
- [ ] Same route test
- [ ] Partial divergence test
- [ ] Reverse direction test
- [ ] Parallel roads test
- [ ] Different time test
- [ ] Recency test
- [ ] Multiple families test
- [ ] No history fallback test
- [ ] Safety override test
- [ ] Scale benchmark

## Acceptance Criteria per Phase

### Phase 2: Route Family Clustering
1. New route can be assigned to existing family if similarity > threshold
2. New family created if no match
3. Representative route is existing route (medoid), not synthetic
4. Family support is weighted by time × recency
5. Threshold is configurable
6. Tests pass at threshold boundaries

### Phase 3: PostgreSQL Persistence
1. All historical routes persistable to PostgreSQL
2. H3 index backed by PostgreSQL with h3_cell_res11 index
3. Inverted index queryable without full table scan
4. Migration script provided

### Phase 4: Historical Familiarity Feature
1. familiarity_penalty bounded by max_penalty config
2. No history → neutral behavior (no penalty)
3. Feature flag can disable entirely

### Phase 5: Recommendation Pipeline Integration
1. Existing ranking unchanged when feature disabled
2. Historical context available at ranking stage
3. Candidate eligibility not affected by familiarity

### Phase 6: API Endpoints
1. All endpoints return structured data
2. No database internals exposed
3. Graceful error handling

### Phase 7: End-to-End Validation
1. All 9 test cases pass
2. Scale benchmark shows detailed comparisons << total routes
3. Performance acceptable for demo

## Scale Evidence Format
```
Total historical routes: N
→ H3 candidate shortlist: M (M << N)
→ After hard filters: K (K << M)
→ Detailed comparisons: K (no reduction)
→ Lookup latency: < Xms
→ Compare latency: < Yms per route
```

## Technical Notes

### PostgreSQL H3 Index Strategy
```sql
-- h3_cell_res11 is the H3 cell at resolution 11
CREATE INDEX idx_historical_route_h3 ON historical_route_h3(h3_cell_res11);
CREATE INDEX idx_historical_routes_origin ON historical_routes USING gist (origin_point geography);
CREATE INDEX idx_historical_routes_dest ON historical_routes USING gist (dest_point geography);
```

### Similarity Threshold Default
- JOIN_FAMILY_THRESHOLD = 0.6 (60% symmetric similarity)
- Configurable via config

### Familiarity Penalty Formula
```
familiarity_penalty = min(max_penalty, max_penalty * (1 - adherence))
```
Where adherence = shared_distance / recommended_distance

Default max_penalty = 0.1 (10% of ranking cost)
