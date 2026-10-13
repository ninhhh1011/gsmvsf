"""Bounded ordered corridor overlap; H3 is an index, not evidence of a match."""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

import h3

from backend.app.services.route_familiarity.constants import MAX_ROUTE_DISTANCE_M, MAX_ROUTE_VERTICES
from backend.app.services.route_familiarity.similarity import ComparisonBudget

_EARTH_RADIUS_M = 6_371_008.8
_SAMPLE_STEP_M = 10.0
_MAX_SAMPLES = 10_001
_SPATIAL_STEP_DEG = math.degrees(45 / _EARTH_RADIUS_M)


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
    proposed_cells: list[str] = field(default_factory=list)
    actual_cells: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoutePiece:
    start: tuple[float, float]
    end: tuple[float, float]
    offset_m: float
    length_m: float
    heading: float
    cell: str


@dataclass(frozen=True)
class PreparedRoute:
    pieces: tuple[RoutePiece, ...]
    distance_m: float
    resolution: int
    positions: dict[str, tuple[int, ...]]
    spatial_positions: dict[tuple[int, int], tuple[int, ...]] | None = None
    query_tiles: tuple[tuple[tuple[int, int], ...] | None, ...] | None = None
    neighbors: dict[str, frozenset[str]] | None = None


def _tiles(min_lat, max_lat, min_lon, max_lon):
    rows = range(math.floor(min_lat / _SPATIAL_STEP_DEG), math.floor(max_lat / _SPATIAL_STEP_DEG) + 1)
    columns = range(math.floor(min_lon / _SPATIAL_STEP_DEG), math.floor(max_lon / _SPATIAL_STEP_DEG) + 1)
    if len(rows) * len(columns) > 512:
        return None
    return [(row, column) for row in rows for column in columns]


def _spatial_index(pieces):
    positions, entries = defaultdict(list), 0
    for index, piece in enumerate(pieces):
        if abs(piece.start[0]) >= 80 or abs(piece.end[0]) >= 80 or abs(piece.end[1] - piece.start[1]) > 180:
            return None
        tiles = _tiles(min(piece.start[0], piece.end[0]), max(piece.start[0], piece.end[0]),
                       min(piece.start[1], piece.end[1]), max(piece.start[1], piece.end[1]))
        if tiles is None or entries + len(tiles) > 100_000:
            return None
        entries += len(tiles)
        for tile in tiles:
            positions[tile].append(index)
    return {tile: tuple(indexes) for tile, indexes in positions.items()}


def _query_tiles(piece, max_lateral_m):
    if abs(piece.start[0]) >= 80 or abs(piece.end[1] - piece.start[1]) > 180:
        return None
    lat_margin = math.degrees(max_lateral_m / _EARTH_RADIUS_M) + 1e-10
    lon_margin = lat_margin / math.cos(math.radians(piece.start[0]))
    min_lon, max_lon = min(piece.start[1], piece.end[1]) - lon_margin, max(piece.start[1], piece.end[1]) + lon_margin
    if min_lon < -180 or max_lon > 180:
        return None
    tiles = _tiles(min(piece.start[0], piece.end[0]) - lat_margin,
                   max(piece.start[0], piece.end[0]) + lat_margin, min_lon, max_lon)
    return tuple(tiles) if tiles is not None else None


def _haversine_m(p1, p2):
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _heading_deg(p1, p2):
    lat1, lon1 = map(math.radians, p1)
    lat2, lon2 = map(math.radians, p2)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360


def _heading_diff(h1, h2):
    return abs((h1 - h2 + 180) % 360 - 180)


def _lerp(a, b, t):
    delta_lon = (b[1] - a[1] + 180) % 360 - 180
    return (a[0] + (b[0] - a[0]) * t, (a[1] + delta_lon * t + 180) % 360 - 180)


def prepare_route(coords: Sequence[tuple[float, float]], resolution=9, *, sample_budget=None) -> PreparedRoute:
    if resolution not in (8, 9, 10):
        raise ValueError("resolution must be 8, 9 or 10")
    if len(coords) > MAX_ROUTE_VERTICES:
        raise ValueError("too many route vertices")
    points = []
    for point in coords:
        if (len(point) != 2 or not all(math.isfinite(v) for v in point) or
                not -90 <= point[0] <= 90 or not -180 <= point[1] <= 180):
            raise ValueError("invalid route coordinate")
        points.append(tuple(point))
    edges, total = [], 0.0
    for a, b in zip(points, points[1:]):
        length = _haversine_m(a, b)
        if length <= 1e-9:
            continue
        edges.append((total, length, a, b))
        total += length
        if total > MAX_ROUTE_DISTANCE_M:
            raise ValueError("route exceeds maximum distance")
    if not edges:
        return PreparedRoute((), 0.0, resolution, {})
    count = math.ceil(total / _SAMPLE_STEP_M)
    if count > _MAX_SAMPLES:
        raise ValueError("route exceeds maximum samples")
    if sample_budget is not None:
        sample_budget.consume(count)
    # A global distance grid makes collinear vertex density irrelevant.
    sampled, edge_index = [], 0
    for i in range(count + 1):
        position = min(total, i * _SAMPLE_STEP_M)
        while edge_index < len(edges) - 1 and position > sum(edges[edge_index][:2]):
            edge_index += 1
        offset, length, a, b = edges[edge_index]
        sampled.append((position, _lerp(a, b, min(1.0, (position - offset) / length))))
    pieces, positions = [], defaultdict(list)
    for (offset, a), (end_offset, b) in zip(sampled, sampled[1:]):
        if _haversine_m(a, b) <= 1e-9:
            continue
        cell = h3.latlng_to_cell(*_lerp(a, b, 0.5), resolution)
        positions[cell].append(len(pieces))
        pieces.append(RoutePiece(a, b, offset, end_offset - offset, _heading_deg(a, b), cell))
    return PreparedRoute(tuple(pieces), total, resolution,
                         {cell: tuple(indexes) for cell, indexes in positions.items()},
                         _spatial_index(pieces), tuple(_query_tiles(piece, 45) for piece in pieces),
                         {cell: frozenset(h3.grid_disk(cell, 1)) for cell in positions})


def _projected_interval(p: RoutePiece, a: RoutePiece, max_lateral_m):
    # Project onto the finite directed segment, never onto a sample point.
    cos_lat = math.cos(math.radians(p.start[0]))
    def xy(point):
        delta_lon = (point[1] - p.start[1] + 180) % 360 - 180
        return ((_EARTH_RADIUS_M * math.radians(delta_lon) * cos_lat),
                _EARTH_RADIUS_M * math.radians(point[0] - p.start[0]))
    ax, ay = xy(a.start)
    bx, by = xy(a.end)
    px, py = xy(p.end)
    dx, dy = bx - ax, by - ay
    squared = dx * dx + dy * dy
    if squared <= 1e-12:
        return None
    u0 = (-ax * dx - ay * dy) / squared
    du = (px * dx + py * dy) / squared
    if du <= 1e-12:
        return None
    lo, hi = max(0.0, -u0 / du), min(1.0, (1 - u0) / du)
    root = math.sqrt(squared)
    lateral0 = (-ax * dy + ay * dx) / root
    lateral_delta = (px * dy - py * dx) / root
    if abs(lateral_delta) > 1e-12:
        bounds = sorted(((-max_lateral_m - lateral0) / lateral_delta,
                         (max_lateral_m - lateral0) / lateral_delta))
        lo, hi = max(lo, bounds[0]), min(hi, bounds[1])
    elif abs(lateral0) > max_lateral_m:
        return None
    if hi - lo <= 1e-9:
        return None
    return lo, hi, u0, du, abs(lateral0 + lateral_delta * (lo + hi) / 2)


def compare_prepared_routes(proposed: PreparedRoute, actual: PreparedRoute, *,
                            max_lateral_m=45.0, max_heading_diff_deg=60.0,
                            budget: ComparisonBudget | None = None) -> RouteComparisonMetrics:
    if proposed.resolution != actual.resolution:
        raise ValueError("prepared routes must use the same resolution")
    if not 0 <= max_lateral_m <= 45 or not 0 <= max_heading_diff_deg <= 60:
        raise ValueError("corridor thresholds exceed supported bounds")
    budget = budget if budget is not None else ComparisonBudget()
    shared, last_actual = 0.0, 0.0
    cells, segments = set(), []
    neighbors = proposed.neighbors.copy() if proposed.neighbors is not None else {}
    candidate_cache = {}
    for piece_index, p in enumerate(proposed.pieces):
        if p.cell not in neighbors:
            neighbors[p.cell] = set(h3.grid_disk(p.cell, 1))
        tiles = None
        if actual.spatial_positions is not None:
            tiles = (proposed.query_tiles[piece_index] if max_lateral_m == 45 and proposed.query_tiles is not None
                     else _query_tiles(p, max_lateral_m))
        key = p.cell, tiles
        candidates = candidate_cache.get(key)
        if candidates is None:
            if tiles is not None:
                candidates = tuple(sorted({index for tile in tiles for index in actual.spatial_positions.get(tile, ())
                                          if actual.pieces[index].cell in neighbors[p.cell]}))
            else:
                candidates = tuple(sorted({index for cell in neighbors[p.cell]
                                          for index in actual.positions.get(cell, ())}))
        budget.consume(len(candidates))
        candidate_cache[key] = candidates
        intervals = []
        for index in candidates:
            a = actual.pieces[index]
            if a.offset_m + a.length_m <= last_actual + 1e-9:
                continue
            if _heading_diff(p.heading, a.heading) > max_heading_diff_deg:
                continue
            interval = _projected_interval(p, a, max_lateral_m)
            if interval:
                lo, hi, u0, du, lateral = interval
                intervals.append((lo, lateral, a.offset_m, hi, u0, du, a))
        cursor = 0.0
        for lo, lateral, offset, hi, u0, du, a in sorted(intervals, key=lambda item: item[:3]):
            lo = max(lo, cursor, ((last_actual - offset) / a.length_m - u0) / du)
            if hi - lo <= 1e-9:
                continue
            actual_length = (hi - lo) * du * a.length_m
            shared += min((hi - lo) * p.length_m, actual_length)
            last_actual = offset + (u0 + du * hi) * a.length_m
            cursor = hi
            cells.add(p.cell)
            cells.add(a.cell)
            start, end = _lerp(p.start, p.end, lo), _lerp(p.start, p.end, hi)
            if segments and _haversine_m(segments[-1][-1], start) < 0.05:
                segments[-1].append(end)
            else:
                segments.append([start, end])
    # shortcut: 10 m chord approximation, refine only against measured corridor error.
    shared = min(shared, proposed.distance_m, actual.distance_m)
    return RouteComparisonMetrics(
        round(proposed.distance_m, 1), round(actual.distance_m, 1), round(shared, 1),
        round(shared / proposed.distance_m * 100, 2) if proposed.distance_m else 0.0,
        round(shared / actual.distance_m * 100, 2) if actual.distance_m else 0.0,
        proposed.resolution, len(cells), sorted(cells), segments,
        sorted(proposed.positions), sorted(actual.positions))


def match_and_compare_routes(proposed_coords, actual_coords, resolution=9,
                             max_lateral_m=45.0, max_heading_diff_deg=60.0, *, budget=None):
    return compare_prepared_routes(prepare_route(proposed_coords, resolution),
                                   prepare_route(actual_coords, resolution),
                                   max_lateral_m=max_lateral_m,
                                   max_heading_diff_deg=max_heading_diff_deg, budget=budget)
