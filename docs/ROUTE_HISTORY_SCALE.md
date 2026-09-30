# Route History Scale - Implementation Documentation

## Overview

Historical route similarity analysis using H3 Resolution 11 for spatial indexing, enabling scale to millions of historical routes while maintaining road-level accuracy.

## Implemented Features

### Phase 1: Historical Route Foundation ✅
- [x] H3 Resolution 11 Signature Generation
- [x] H3 Inverted Index (O(1) lookup)
- [x] Historical Candidate Search
- [x] Hard Filters (OD proximity, Direction, 7-day window)
- [x] Time/Recency Weighting
- [x] Road-level Similarity (directed segments)

### Phase 2: Route Family Clustering ✅
- [x] Incremental clustering (no N×N comparisons)
- [x] Medoid (existing route) as representative
- [x] Configurable similarity threshold (default 60%)
- [x] Weighted support (time × recency)
- [x] Family lookup by origin/destination context

### Phase 3: PostgreSQL Persistence ✅
- [x] Schema: historical_routes, historical_route_segments, historical_route_h3
- [x] Schema: route_families, route_family_members
- [x] Repository with bulk insert
- [x] H3 inverted index query (PostgreSQL backed)
- [x] Importer from dataset_v1

### Phase 4: Historical Familiarity Feature ✅
- [x] Bounded familiarity penalty
- [x] Configurable max_penalty (default 10%)
- [x] Graceful fallback (neutral when no history)
- [x] Does NOT override safety/feasibility checks

## Not Implemented (Future Work)

- Phase 5: Recommendation Pipeline Integration
- Phase 6: API Endpoints
- Phase 7: End-to-End Validation & Scale Benchmark

## Architecture

```
GPS Observations
      ↓
Map Matching (existing)
      ↓
Directed Road Segments (Route Truth) ← NOT H3
      ↓
┌─────────────────────────────┐
│   H3 Resolution 11          │  ← Spatial Index Only
│   Signature Generation       │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   H3 Inverted Index         │  ← H3 → [route_ids]
│   PostgreSQL or In-memory   │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Hard Filters:             │  ← EXCLUDE Wrong Routes
│   - Origin/Destination      │
│   - Direction              │
│   - 7-day window           │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Time + Recency Weight     │
│   time_weight × recency    │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Road-level Similarity     │  ← Route Truth
│   Directed Segments + Dist  │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Route Family Clustering   │  ← Incremental
│   Medoid Representative    │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   PostgreSQL Persistence    │
└─────────────────────────────┘
```

## Key Design Decisions

### H3 Resolution 11
- ~5.16 m² per hex
- Fine-grained enough for road-level spatial indexing
- Role: **Spatial Index Only** - NOT for final similarity

### Ordered H3 Sequence
- Maintains direction: H1→H2 is different from H2→H1
- Tuple[str, ...] not Set[str]
- Consecutive duplicates collapsed

### Route Truth = Directed Road Segments
- Final similarity based on actual road segments
- Both segment ID and direction must match
- Distance-weighted overlap

### Historical Window
- 7 days (configurable)
- Hard filter: EXCLUDE routes outside window

### Direction
- Hard filter: EXCLUDE reverse direction routes
- Bearing comparison with 90° tolerance

### Weighting
- time_weight: exponential decay based on hour difference
- recency_weight: exponential decay based on days difference
- Combined: time_weight × recency_weight

### Familiarity Penalty
```
familiarity_penalty = min(max_penalty, max_penalty * (1 - adherence))
final_cost = existing_cost + familiarity_penalty
```
- Is a PENALTY, not a reward
- Bounded by max_penalty (default 10%)
- Neutral when no history exists

## Storage

### PostgreSQL Tables
- `historical_routes`: route metadata with origin/destination
- `historical_route_segments`: ordered segment IDs per route
- `historical_route_h3`: H3 Res 11 cells for inverted index
- `route_families`: family metadata with weighted support
- `route_family_members`: family membership relationships

### Indexes
- `h3_cell_res11` on historical_route_h3 (inverted index)
- Origin/destination bounding box indexes
- Route family context indexes

## Files

```
backend/app/services/route_history/
├── __init__.py              # Module exports
├── signature.py             # H3 Signature Generator
├── index.py                 # H3 Inverted Index
├── filters.py               # Hard Filters + Time/Recency Weight
├── similarity.py            # Road-level Similarity Calculator
├── families.py             # Route Family Clustering
├── repository.py            # PostgreSQL Repository
├── importer.py             # Dataset Importer
├── familiarity.py           # Historical Familiarity Feature
└── schema.sql              # Database Schema

backend/tests/services/
├── test_route_history.py    # Phase 1 tests (27 tests)
├── test_route_families.py   # Phase 2 tests (14 tests)
└── test_familiarity.py      # Phase 4 tests (12 tests)
```

## Test Coverage

- 53 tests passing
- Unit tests for each module
- Integration tests for clustering
- Configurable threshold boundary tests

## Configuration

### HardFilters
```python
HardFilters(
    origin_threshold_km=2.0,
    dest_threshold_km=2.0,
    days_window=7
)
```

### TimeRecencyWeight
```python
TimeRecencyWeight(
    time_decay_hours=2.0,      # Half-life for time of day
    recency_decay_days=2.0     # Half-life for recency
)
```

### RouteFamilyCluster
```python
RouteFamilyCluster(
    similarity_calculator=calc,
    join_threshold=0.6,         # 60% similarity to join
    representative_update_interval=10
)
```

### FamiliarityConfig
```python
FamiliarityConfig(
    enabled=True,
    max_penalty=0.1,            # Max 10% penalty
    adherence_threshold=0.5,    # Below this, full penalty
    individual_weight=0.7,
    popular_weight=0.3
)
```

## Limitations

1. **No API Endpoints**: Full pipeline not integrated into FastAPI
2. **No Scale Benchmark**: Performance not measured at scale
3. **No Pipeline Integration**: Familiarity not hooked into ranking
4. **In-memory index optional**: PostgreSQL backed index not fully tested

## Next Steps (Phase 5-7)

1. **Pipeline Integration**: Hook familiarity into ranking
2. **Feature Flag**: ENABLE_ROUTE_FAMILIARITY
3. **API Endpoints**: Route similarity, family queries
4. **End-to-End Tests**: All 9 validation cases
5. **Scale Benchmark**: Demonstrate detailed comparisons << total routes
