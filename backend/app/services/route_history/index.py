"""
H3 Inverted Index
=================

Spatial index mapping H3 Resolution 11 cells to route IDs.

This enables O(1) lookup of routes that pass through a given H3 cell,
dramatically reducing the search space when finding similar routes.

Inverted Index Structure:
    H3_cell → Set[route_id]

Example:
    "891a...c3" → {"R001", "R015", "R023"}
    "891a...d7" → {"R001", "R042"}
    ...

This allows finding candidate routes by:
1. Getting H3 cells from current route
2. Looking up all routes containing those cells
3. Deduplicating and ranking by overlap count
"""

from typing import Dict, Set, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class RouteH3Index:
    """In-memory H3 inverted index for route lookups."""
    # H3 cell → set of route IDs that pass through this cell
    hex_to_routes: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    # Route ID → set of H3 cells this route covers
    route_to_hexes: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    # Statistics
    total_routes: int = 0
    total_cells: int = 0


class RouteInvertedIndex:
    """
    Inverted index for H3-based route lookup.

    Provides fast O(1) lookup of routes passing through any H3 cell,
    enabling efficient candidate search without scanning all historical routes.

    Supports:
    - Adding routes to the index
    - Removing routes from the index
    - Querying routes by H3 cell(s)
    - Persistence to/from JSON
    """

    def __init__(self):
        self.index = RouteH3Index()

    def add_route(
        self,
        route_id: str,
        hex_sequence: List[str]
    ) -> None:
        """
        Add a route to the inverted index.

        Args:
            route_id: Unique route identifier
            hex_sequence: Ordered list of H3 cell IDs (from signature)
        """
        # Add route to each hex's route set
        for hex_cell in hex_sequence:
            self.index.hex_to_routes[hex_cell].add(route_id)
            self.index.route_to_hexes[route_id].add(hex_cell)

        self.index.total_routes = len(self.index.route_to_hexes)
        self.index.total_cells = len(self.index.hex_to_routes)

    def remove_route(self, route_id: str) -> None:
        """
        Remove a route from the inverted index.

        Args:
            route_id: Route to remove
        """
        if route_id not in self.index.route_to_hexes:
            return

        # Remove route_id from each hex's route set
        for hex_cell in self.index.route_to_hexes[route_id]:
            self.index.hex_to_routes[hex_cell].discard(route_id)
            # Clean up empty hex entries
            if not self.index.hex_to_routes[hex_cell]:
                del self.index.hex_to_routes[hex_cell]

        del self.index.route_to_hexes[route_id]
        self.index.total_routes = len(self.index.route_to_hexes)
        self.index.total_cells = len(self.index.hex_to_routes)

    def query_by_hex(
        self,
        hex_cell: str
    ) -> Set[str]:
        """
        Get all route IDs that pass through a given H3 cell.

        Args:
            hex_cell: H3 cell ID

        Returns:
            Set of route IDs
        """
        return self.index.hex_to_routes.get(hex_cell, set()).copy()

    def query_by_hexes(
        self,
        hex_cells: List[str],
        min_overlap: int = 1
    ) -> List[Tuple[str, int]]:
        """
        Get routes passing through ANY of the given H3 cells.

        Args:
            hex_cells: List of H3 cell IDs
            min_overlap: Minimum number of hex cells a route must share

        Returns:
            List of (route_id, overlap_count) sorted by overlap count descending
        """
        # Aggregate route counts
        route_counts: Dict[str, int] = defaultdict(int)
        for hex_cell in hex_cells:
            for route_id in self.index.hex_to_routes.get(hex_cell, set()):
                route_counts[route_id] += 1

        # Filter by minimum overlap and sort
        results = [
            (route_id, count)
            for route_id, count in route_counts.items()
            if count >= min_overlap
        ]
        results.sort(key=lambda x: -x[1])  # Descending by overlap count

        return results

    def query_by_signature(
        self,
        signature_hexes: List[str],
        min_overlap_pct: float = 0.0
    ) -> List[Tuple[str, int, float]]:
        """
        Get routes similar to a given H3 signature.

        Args:
            signature_hexes: H3 signature of the query route
            min_overlap_pct: Minimum percentage of hexes that must overlap

        Returns:
            List of (route_id, shared_count, overlap_pct) sorted by shared_count descending
        """
        min_overlap = max(1, int(len(signature_hexes) * min_overlap_pct))
        results = self.query_by_hexes(signature_hexes, min_overlap)

        # Calculate overlap percentage
        enriched_results = []
        for route_id, shared_count in results:
            route_hex_count = len(self.index.route_to_hexes.get(route_id, set()))
            # Overlap pct relative to the query route
            overlap_pct = shared_count / len(signature_hexes) if signature_hexes else 0.0
            enriched_results.append((route_id, shared_count, overlap_pct))

        return enriched_results

    def get_route_hexes(self, route_id: str) -> Set[str]:
        """Get all H3 cells covered by a route."""
        return self.index.route_to_hexes.get(route_id, set()).copy()

    def get_stats(self) -> Dict:
        """Get index statistics."""
        return {
            "total_routes": self.index.total_routes,
            "total_cells": self.index.total_cells,
            "avg_hexes_per_route": (
                self.index.total_cells / self.index.total_routes
                if self.index.total_routes > 0 else 0
            ),
            "avg_routes_per_hex": (
                sum(len(routes) for routes in self.index.hex_to_routes.values()) /
                self.index.total_cells
                if self.index.total_cells > 0 else 0
            ),
        }

    def save(self, path: str) -> None:
        """Persist index to JSON file."""
        data = {
            "hex_to_routes": {
                hex_cell: list(route_ids)
                for hex_cell, route_ids in self.index.hex_to_routes.items()
            },
            "route_to_hexes": {
                route_id: list(hex_cells)
                for route_id, hex_cells in self.index.route_to_hexes.items()
            },
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> "RouteInvertedIndex":
        """Load index from JSON file."""
        index = cls()

        with open(path) as f:
            data = json.load(f)

        for hex_cell, route_ids in data.get("hex_to_routes", {}).items():
            index.index.hex_to_routes[hex_cell] = set(route_ids)

        for route_id, hex_cells in data.get("route_to_hexes", {}).items():
            index.index.route_to_hexes[route_id] = set(hex_cells)

        index.index.total_routes = len(index.index.route_to_hexes)
        index.index.total_cells = len(index.index.hex_to_routes)

        return index


def test_inverted_index():
    """Test the inverted index."""
    index = RouteInvertedIndex()

    # Add some routes
    index.add_route("R001", ["H1", "H2", "H3", "H4"])
    index.add_route("R002", ["H2", "H3", "H5"])
    index.add_route("R003", ["H6", "H7", "H8"])
    index.add_route("R004", ["H1", "H2", "H3", "H6"])

    print("=== Index Statistics ===")
    stats = index.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n=== Query: H1 ===")
    routes = index.query_by_hex("H1")
    print(f"  Routes through H1: {routes}")

    print("\n=== Query: [H2, H3] ===")
    results = index.query_by_hexes(["H2", "H3"])
    for route_id, count in results:
        print(f"  {route_id}: {count} hexes shared")

    print("\n=== Query by signature ===")
    sig = ["H1", "H2", "H3", "H4"]
    results = index.query_by_signature(sig, min_overlap_pct=0.5)
    for route_id, shared, pct in results:
        print(f"  {route_id}: {shared} shared ({pct:.1%})")

    # Test persistence
    test_path = "/tmp/test_route_index.json"
    index.save(test_path)
    loaded = RouteInvertedIndex.load(test_path)

    print("\n=== Loaded Index Statistics ===")
    stats = loaded.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    return index


if __name__ == "__main__":
    test_inverted_index()
