"""
Route History Scale Service - Phase 1
=====================================

H3 Resolution 11 based spatial indexing for historical route similarity analysis.

Key concepts:
- H3 Resolution 11: ~5.16 m² per hex - fine-grained road-level indexing
- Ordered H3 sequence: maintains direction (H1→H2, not Set<H3>)
- Road Segments: Route Truth for final similarity calculation
- 7-day window: only recent history for relevance
- Inverted Index: H3 → [route_ids] for O(1) candidate lookup
- Route Families: Incremental clustering with medoid representatives

Architecture:
    GPS → Map Matching → Road Segments → H3 Signature → Inverted Index → Candidate Search
                                                                        ↓
                                                              Hard Filters + Weighting
                                                                        ↓
                                                              Road-level Similarity
                                                                        ↓
                                                              Route Family Clustering
"""

from .signature import H3SignatureGenerator
from .index import RouteInvertedIndex
from .similarity import RoadLevelSimilarity
from .filters import HardFilters, TimeRecencyWeight
from .families import RouteFamilyCluster, RouteFamily, RouteFamilyMember
from .search import HistoricalRouteSearch

__all__ = [
    "H3SignatureGenerator",
    "RouteInvertedIndex",
    "RoadLevelSimilarity",
    "HardFilters",
    "TimeRecencyWeight",
    "RouteFamilyCluster",
    "RouteFamily",
    "RouteFamilyMember",
    "HistoricalRouteSearch",
]
