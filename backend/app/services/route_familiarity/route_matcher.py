"""
Direction- and Sequence-Aware Route Matching using Uber H3.

H3 is used as a spatial index to bin candidate corridor segments (Res 8, 9, 10).
Candidate points are strictly verified for:
1. Heading consistency: heading difference <= max_heading_diff_deg (default 60 deg).
2. Spatial proximity: lateral distance <= max_lateral_m (default 45m).
3. Monotonic sequence ordering.

Returns verified shared distance and dual percentages:
- shared_pct_on_proposed = (shared_m / proposed_total_m) * 100%
- shared_pct_on_actual   = (shared_m / actual_total_m) * 100%
"""
import math
from dataclasses import dataclass
from typing import Sequence
import h3

_EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class RouteComparisonMetrics:
    proposed_distance_m: float
    actual_distance_m: float
    shared_distance_m: float
    shared_pct_on_proposed: float
    shared_pct_on_actual: float
    resolution: int
    shared_cells_count: int
    shared_cells: list[str]
    shared_segments: list[list[tuple[float, float]]]


def _haversine_m(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _heading_deg(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def _heading_diff(h1: float, h2: float) -> float:
    diff = abs(h1 - h2) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def _get_step_m_for_resolution(resolution: int) -> float:
    if resolution <= 8:
        return 60.0
    if resolution == 9:
        return 35.0
    return 20.0  # res 10 or finer


def _discretize_route(coords: Sequence[tuple[float, float]], resolution: int):
    samples = []
    total_len = 0.0
    step_m = _get_step_m_for_resolution(resolution)

    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        dist = _haversine_m(p1, p2)
        if dist <= 0:
            continue
        heading = _heading_deg(p1, p2)
        steps = max(1, math.ceil(dist / step_m))
        step_len = dist / steps
        for s in range(steps):
            frac = (s + 0.5) / steps
            lat = p1[0] + (p2[0] - p1[0]) * frac
            lon = p1[1] + (p2[1] - p1[1]) * frac
            cell = h3.latlng_to_cell(lat, lon, resolution)
            samples.append({
                "lat": lat,
                "lon": lon,
                "heading": heading,
                "cell": cell,
                "length_m": step_len,
            })
            total_len += step_len
    return samples, total_len


def match_and_compare_routes(
    proposed_coords: Sequence[tuple[float, float]],
    actual_coords: Sequence[tuple[float, float]],
    resolution: int = 9,
    max_lateral_m: float = 45.0,
    max_heading_diff_deg: float = 60.0,
) -> RouteComparisonMetrics:
    """
    Compare two routes via H3 spatial binning with heading and sequence verification.
    """
    if len(proposed_coords) < 2 or len(actual_coords) < 2:
        return RouteComparisonMetrics(
            proposed_distance_m=0.0,
            actual_distance_m=0.0,
            shared_distance_m=0.0,
            shared_pct_on_proposed=0.0,
            shared_pct_on_actual=0.0,
            resolution=resolution,
            shared_cells_count=0,
            shared_cells=[],
            shared_segments=[],
        )

    prop_samples, prop_total_m = _discretize_route(proposed_coords, resolution)
    act_samples, act_total_m = _discretize_route(actual_coords, resolution)

    if prop_total_m <= 0 or act_total_m <= 0:
        return RouteComparisonMetrics(
            proposed_distance_m=round(prop_total_m, 1),
            actual_distance_m=round(act_total_m, 1),
            shared_distance_m=0.0,
            shared_pct_on_proposed=0.0,
            shared_pct_on_actual=0.0,
            resolution=resolution,
            shared_cells_count=0,
            shared_cells=[],
            shared_segments=[],
        )

    # Index actual route samples by H3 cell
    cell_to_act_indices: dict[str, list[int]] = {}
    for idx, sample in enumerate(act_samples):
        cell_to_act_indices.setdefault(sample["cell"], []).append(idx)

    shared_m = 0.0
    shared_cells: set[str] = set()
    matched_prop_samples: list[dict] = []
    last_act_matched_idx = -1

    for p_idx, p_sample in enumerate(prop_samples):
        candidate_indices = cell_to_act_indices.get(p_sample["cell"], [])
        best_match_idx = None
        min_dist = max_lateral_m

        for a_idx in candidate_indices:
            # Monotonic sequence constraint with minor tolerance for intersection weaving
            if a_idx < last_act_matched_idx - 3:
                continue
            a_sample = act_samples[a_idx]
            # 1. Heading verification: discard opposite-direction lanes
            h_diff = _heading_diff(p_sample["heading"], a_sample["heading"])
            if h_diff > max_heading_diff_deg:
                continue
            # 2. Spatial lateral distance verification
            dist = _haversine_m((p_sample["lat"], p_sample["lon"]), (a_sample["lat"], a_sample["lon"]))
            if dist <= min_dist:
                min_dist = dist
                best_match_idx = a_idx

        if best_match_idx is not None:
            shared_m += p_sample["length_m"]
            shared_cells.add(p_sample["cell"])
            matched_prop_samples.append(p_sample)
            last_act_matched_idx = max(last_act_matched_idx, best_match_idx)

    # Assemble continuous matched polyline segments
    shared_segments: list[list[tuple[float, float]]] = []
    if matched_prop_samples:
        current_segment: list[tuple[float, float]] = [(matched_prop_samples[0]["lat"], matched_prop_samples[0]["lon"])]
        for s1, s2 in zip(matched_prop_samples, matched_prop_samples[1:]):
            d = _haversine_m((s1["lat"], s1["lon"]), (s2["lat"], s2["lon"]))
            if d <= _get_step_m_for_resolution(resolution) * 2.5:
                current_segment.append((s2["lat"], s2["lon"]))
            else:
                if len(current_segment) >= 2:
                    shared_segments.append(current_segment)
                current_segment = [(s2["lat"], s2["lon"])]
        if len(current_segment) >= 2:
            shared_segments.append(current_segment)

    pct_proposed = min(100.0, max(0.0, (shared_m / prop_total_m) * 100.0))
    pct_actual = min(100.0, max(0.0, (shared_m / act_total_m) * 100.0))

    return RouteComparisonMetrics(
        proposed_distance_m=round(prop_total_m, 1),
        actual_distance_m=round(act_total_m, 1),
        shared_distance_m=round(shared_m, 1),
        shared_pct_on_proposed=round(pct_proposed, 2),
        shared_pct_on_actual=round(pct_actual, 2),
        resolution=resolution,
        shared_cells_count=len(shared_cells),
        shared_cells=sorted(shared_cells),
        shared_segments=shared_segments,
    )
