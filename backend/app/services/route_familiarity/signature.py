import math
from collections.abc import Sequence

import h3

from backend.app.services.route_familiarity.constants import (
    H3_ROUTE_RESOLUTION,
    MAX_ENCODED_POLYLINE_BYTES,
    MAX_ROUTE_CELLS,
    MAX_ROUTE_DISTANCE_M,
    MAX_ROUTE_VERTICES,
)
from backend.app.services.route_familiarity.models import RouteSignature

_EARTH_RADIUS_M = 6_371_008.8
_MAX_CELL_STEP_M = h3.average_hexagon_edge_length(H3_ROUTE_RESOLUTION, unit="m") / 2


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > MAX_ENCODED_POLYLINE_BYTES:
        raise ValueError("invalid encoded polyline size")

    coordinates = []
    values = [0, 0]
    index = 0
    while index < len(encoded):
        point = []
        for axis in range(2):
            result = shift = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("truncated encoded polyline")
                chunk = ord(encoded[index]) - 63
                index += 1
                if chunk < 0 or chunk > 63 or shift >= 60:
                    raise ValueError("invalid encoded polyline")
                result |= (chunk & 0x1F) << shift
                shift += 5
                if chunk < 0x20:
                    break
            values[axis] += ~(result >> 1) if result & 1 else result >> 1
            point.append(values[axis] / 1e5)
        lat, lon = point
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("polyline coordinate out of range")
        coordinates.append((lat, lon))
        if len(coordinates) > MAX_ROUTE_VERTICES:
            raise ValueError("too many route vertices")
    if len(coordinates) < 2:
        raise ValueError("route needs at least two vertices")
    return coordinates


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(value)))


def _interpolate(a: tuple[float, float], b: tuple[float, float], fraction: float):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta = _distance_m(a, b) / _EARTH_RADIUS_M
    if delta < 1e-12:
        return a
    sine = math.sin(delta)
    left, right = math.sin((1 - fraction) * delta) / sine, math.sin(fraction * delta) / sine
    x = left * math.cos(lat1) * math.cos(lon1) + right * math.cos(lat2) * math.cos(lon2)
    y = left * math.cos(lat1) * math.sin(lon1) + right * math.cos(lat2) * math.sin(lon2)
    z = left * math.sin(lat1) + right * math.sin(lat2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def create_route_signature(polylines: Sequence[str]) -> RouteSignature:
    if not polylines or sum(len(line.encode("utf-8")) for line in polylines) > MAX_ENCODED_POLYLINE_BYTES:
        raise ValueError("invalid encoded route size")

    cells: list[str] = []
    weights: list[float] = []
    total_distance = 0.0
    vertex_count = 0
    for encoded in polylines:
        points = decode_polyline(encoded)
        vertex_count += len(points)
        if vertex_count > MAX_ROUTE_VERTICES:
            raise ValueError("too many route vertices")
        for start, end in zip(points, points[1:]):
            segment_distance = _distance_m(start, end)
            if segment_distance == 0:
                continue
            total_distance += segment_distance
            if total_distance > MAX_ROUTE_DISTANCE_M:
                raise ValueError("route exceeds maximum distance")
            steps = math.ceil(segment_distance / _MAX_CELL_STEP_M)
            weight = segment_distance / steps
            for step in range(steps):
                midpoint = _interpolate(start, end, (step + 0.5) / steps)
                cell = h3.latlng_to_cell(*midpoint, H3_ROUTE_RESOLUTION)
                if cells and cells[-1] == cell:
                    weights[-1] += weight
                else:
                    cells.append(cell)
                    weights.append(weight)
                    if len(cells) > MAX_ROUTE_CELLS:
                        raise ValueError("route exceeds maximum signature cells")
    if total_distance <= 0 or not cells:
        raise ValueError("route must have nonzero length")
    return RouteSignature(tuple(cells), tuple(weights), total_distance, H3_ROUTE_RESOLUTION)
