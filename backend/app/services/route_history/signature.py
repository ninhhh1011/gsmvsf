"""
H3 Resolution 11 Signature Generator
===================================

Converts route geometries to ordered H3 hex sequences for spatial indexing.

Key design:
- Resolution 11: ~5.16 m² per hex - fine-grained enough for road-level indexing
- Ordered sequence: maintains direction (H1→H2→H3), not Set<H3>
- Each point in route gets H3 cell; consecutive duplicates collapsed
- Supports both lat/lng coordinates and segment_id based routes

Example:
    Route geometry: [(lat1, lng1), (lat2, lng2), ...]
    Output: ["H3_index_1", "H3_index_2", "H3_index_3", ...]
"""

from typing import List, Tuple, Optional, Sequence
from dataclasses import dataclass
import h3


# H3 Resolution 11: ~5.16 m² per hex - road-level granularity
H3_ROUTE_RESOLUTION = 11


@dataclass
class H3Signature:
    """Immutable H3 signature for a route."""
    route_id: str
    hex_sequence: Tuple[str, ...]  # Ordered H3 indices
    hex_count: int
    start_hex: str  # First H3 cell (origin)
    end_hex: str    # Last H3 cell (destination)
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float


@dataclass
class H3Transition:
    """Directed transition between two H3 cells."""
    from_hex: str
    to_hex: str
    transition_key: str  # "from_hex->to_hex"


class H3SignatureGenerator:
    """
    Generates H3 Resolution 11 signatures from route data.

    Supports multiple input formats:
    - Lat/lng coordinate pairs
    - Road segment IDs (from map matching)
    - Pre-computed H3 indices

    The signature maintains directionality - H1→H2 is different from H2→H1.
    """

    def __init__(self, resolution: int = H3_ROUTE_RESOLUTION):
        self.resolution = resolution

    def signature_from_coords(
        self,
        route_id: str,
        coordinates: Sequence[Tuple[float, float]]
    ) -> H3Signature:
        """
        Generate H3 signature from lat/lng coordinate sequence.

        Args:
            route_id: Unique identifier for this route
            coordinates: List of (lat, lng) tuples

        Returns:
            H3Signature with ordered hex sequence
        """
        if len(coordinates) < 2:
            raise ValueError(f"Route {route_id} has insufficient coordinates: {len(coordinates)}")

        # Convert all coordinates to H3 cells
        raw_hexes = []
        for lat, lng in coordinates:
            hex_id = h3.latlng_to_cell(lat, lng, self.resolution)
            raw_hexes.append(hex_id)

        # Collapse consecutive duplicates
        # (When vehicle dwells, multiple points fall in same hex)
        hex_sequence = self._collapse_consecutive(raw_hexes)

        # Extract start/end
        start_lat, start_lng = coordinates[0]
        end_lat, end_lng = coordinates[-1]

        return H3Signature(
            route_id=route_id,
            hex_sequence=tuple(hex_sequence),
            hex_count=len(hex_sequence),
            start_hex=hex_sequence[0] if hex_sequence else "",
            end_hex=hex_sequence[-1] if hex_sequence else "",
            start_lat=start_lat,
            start_lng=start_lng,
            end_lat=end_lat,
            end_lng=end_lng,
        )

    def signature_from_segments(
        self,
        route_id: str,
        segments: Sequence[Tuple[str, float, float]]  # (segment_id, lat, lng)
    ) -> H3Signature:
        """
        Generate H3 signature from ordered road segments.

        Args:
            route_id: Unique identifier for this route
            segments: List of (segment_id, lat, lng) tuples

        Returns:
            H3Signature with ordered hex sequence
        """
        if not segments:
            raise ValueError(f"Route {route_id} has no segments")

        coordinates = [(lat, lng) for _, lat, lng in segments]
        return self.signature_from_coords(route_id, coordinates)

    def signature_from_segment_ids(
        self,
        route_id: str,
        segment_ids: List[str],
        segment_geometries: dict[str, Tuple[float, float, float, float]]
        # segment_id -> (start_lat, start_lng, end_lat, end_lng)
    ) -> H3Signature:
        """
        Generate H3 signature from ordered segment IDs with geometry lookup.

        Args:
            route_id: Unique identifier for this route
            segment_ids: Ordered list of directed segment IDs
            segment_geometries: Dict mapping segment_id to its geometry endpoints

        Returns:
            H3Signature with ordered hex sequence
        """
        if not segment_ids:
            raise ValueError(f"Route {route_id} has no segment IDs")

        coordinates = []
        prev_end = None

        for seg_id in segment_ids:
            geom = segment_geometries.get(seg_id)
            if geom is None:
                continue

            start_lat, start_lng, end_lat, end_lng = geom

            # For first segment, use start point
            if prev_end is None:
                coordinates.append((start_lat, start_lng))

            # Always add end point
            coordinates.append((end_lat, end_lng))
            prev_end = (end_lat, end_lng)

        if len(coordinates) < 2:
            raise ValueError(f"Route {route_id} has insufficient coordinates after geometry lookup")

        return self.signature_from_coords(route_id, coordinates)

    def _collapse_consecutive(self, hex_list: List[str]) -> List[str]:
        """Remove consecutive duplicate H3 indices."""
        if not hex_list:
            return []

        collapsed = [hex_list[0]]
        for h in hex_list[1:]:
            if h != collapsed[-1]:
                collapsed.append(h)

        return collapsed

    def get_transitions(self, signature: H3Signature) -> List[H3Transition]:
        """
        Get directed transitions between consecutive H3 cells.

        This captures the movement direction through H3 space.

        Returns:
            List of H3Transition objects
        """
        transitions = []
        for i in range(len(signature.hex_sequence) - 1):
            from_hex = signature.hex_sequence[i]
            to_hex = signature.hex_sequence[i + 1]
            transitions.append(H3Transition(
                from_hex=from_hex,
                to_hex=to_hex,
                transition_key=f"{from_hex}->{to_hex}"
            ))

        return transitions

    def compute_hex_overlap(
        self,
        sig1: H3Signature,
        sig2: H3Signature
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Compute H3 cell overlap between two signatures.

        Returns:
            Tuple of (common_hexes, only_in_sig1, only_in_sig2)
        """
        set1 = set(sig1.hex_sequence)
        set2 = set(sig2.hex_sequence)

        common = sorted(list(set1 & set2))
        only1 = sorted(list(set1 - set2))
        only2 = sorted(list(set2 - set1))

        return common, only1, only2

    def compute_sequential_overlap(
        self,
        sig1: H3Signature,
        sig2: H3Signature
    ) -> float:
        """
        Compute sequential overlap - considers H3 order.

        This is more strict than set overlap because it respects direction.

        Returns:
            Fraction 0.0-1.0 representing sequential match
        """
        if not sig1.hex_sequence or not sig2.hex_sequence:
            return 0.0

        # Find longest common subsequence (LCS) considering direction
        # Simple approach: count how many consecutive hexes in sig1 also appear in sig2 in order

        matches = 0
        sig2_indices = {h: i for i, h in enumerate(sig2.hex_sequence)}

        last_match_idx = -1
        for i, h in enumerate(sig1.hex_sequence):
            if h in sig2_indices:
                if sig2_indices[h] > last_match_idx:
                    matches += 1
                    last_match_idx = sig2_indices[h]

        # Return fraction of sig1 that matches sequentially
        return matches / len(sig1.hex_sequence)


def test_h3_signature():
    """Basic test of H3 signature generation."""
    # Hanoi area coordinates
    coords = [
        (21.0285, 105.8542),  # Start - Ba Đình
        (21.0300, 105.8560),
        (21.0315, 105.8580),
        (21.0330, 105.8600),
        (21.0350, 105.8620),  # End - near West Lake
    ]

    gen = H3SignatureGenerator()
    sig = gen.signature_from_coords("TEST_ROUTE_001", coords)

    print(f"Route: {sig.route_id}")
    print(f"H3 Resolution: {gen.resolution}")
    print(f"Number of H3 cells: {sig.hex_count}")
    print(f"Start Hex: {sig.start_hex}")
    print(f"End Hex: {sig.end_hex}")
    print(f"Sequence (first 5): {sig.hex_sequence[:5]}...")

    # Test another route
    coords2 = [
        (21.0285, 105.8542),  # Same start
        (21.0290, 105.8550),
        (21.0295, 105.8558),
        (21.0360, 105.8630),  # Different end
    ]

    sig2 = gen.signature_from_coords("TEST_ROUTE_002", coords2)
    common, only1, only2 = gen.compute_hex_overlap(sig, sig2)

    print(f"\nOverlap Analysis:")
    print(f"Common H3 cells: {len(common)}")
    print(f"Only in route 1: {len(only1)}")
    print(f"Only in route 2: {len(only2)}")

    seq_overlap = gen.compute_sequential_overlap(sig, sig2)
    print(f"Sequential overlap: {seq_overlap:.2%}")

    return sig, sig2


if __name__ == "__main__":
    test_h3_signature()
