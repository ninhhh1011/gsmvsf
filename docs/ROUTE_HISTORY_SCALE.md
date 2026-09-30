# Route History Scale - Ph
ase 1 Implementation

## Overview

This document describes the implementation of historical route similarity analysis using H3 Resolution 11 for spatial indexing.

## Architecture

```
GPS Observations
      ↓
Map Matching (existing)
      ↓
Directed Road Segments (Route Truth)
      ↓
┌─────────────────────────────┐
│   H3 Resolution 11          │  ← Spatial Index
│   Signature Generation       │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   H3 Inverted Index         │  ← H3 → [route_ids]
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Candidate Search          │  ← Shortlist historical routes
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Hard Filters:             │
│   - Origin/Destination      │
│   - Direction               │
│   - 7-day window            │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Time + Recency Weight     │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Road-level Similarity     │
└─────────────────────────────┘
      ↓
┌─────────────────────────────┐
│   Route Family Clustering   │
└─────────────────────────────┘
```

## Implementation Phases

### Phase 1: Historical Route Foundation + Similarity (Current)
- [ ] H3 Resolution 11 Signature
- [ ] H3 Inverted Index
- [ ] Historical Candidate Search
- [ ] Hard Filters (OD, Direction, 7-day)
- [ ] Time/Recency Weight
- [ ] Road-level Similarity

### Phase 2: Route Family + Integration
- [ ] Route Family Clustering
- [ ] Historical Familiarity Feature
- [ ] Integration into Ranking

## Key Design Decisions

1. **H3 Resolution 11**: ~5.16 m² per hex - fine-grained enough for road-level spatial indexing
2. **Ordered H3 Sequence**: Maintains direction (H1→H2, not Set<H3>)
3. **Road Segments**: Route Truth - not H3 - for final similarity calculation
4. **7-day Window**: Only recent history for relevance
5. **Hard Filters First**: Reduce search space before expensive similarity calculation
6. **Inverted Index**: H3 → [route_ids] for O(1) candidate lookup
