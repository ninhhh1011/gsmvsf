"""Read-only synthetic experiment against the production H3 algorithms."""
import json
import math
import statistics
from pathlib import Path

import h3

from backend.app.services.route_familiarity import signature as module
from backend.app.services.route_familiarity.similarity import weighted_ordered_overlap
from backend.tests.test_route_familiarity_domain import polyline


def points(lat, lon, bearing, offset=0, length=2000, count=2):
    theta = math.radians(bearing)
    result = []
    for i in range(count):
        along = length * i / (count - 1)
        north = along * math.cos(theta) - offset * math.sin(theta)
        east = along * math.sin(theta) + offset * math.cos(theta)
        result.append((lat + north / 111195,
                       lon + east / (111195 * math.cos(math.radians(lat)))))
    return result


def make(coordinates):
    return module.create_route_signature([polyline(coordinates)])


rows = []
for resolution in (8, 9, 10, 11):
    # Overrides are confined to this process; source and database stay unchanged.
    module.H3_ROUTE_RESOLUTION = resolution
    module._MAX_CELL_STEP_M = h3.average_hexagon_edge_length(resolution, 'm') / 2
    values = {offset: [] for offset in (0, 10, 25, 40, 100, 200, 400)}
    reversals, density, counts = [], [], []
    for i in range(10):
        lat, lon = 20.985 + i * 0.0043, 105.79 + i * 0.0057
        for bearing in (0, 45, 90):
            p = points(lat, lon, bearing)
            a = make(p)
            counts.append(len(a.cells))
            for offset in values:
                b = make(points(lat, lon, bearing, offset))
                score = weighted_ordered_overlap(a, b).adherence
                assert 0 <= score <= 1
                values[offset].append(score * 100)
            reversals.append(weighted_ordered_overlap(a, make(p[::-1])).adherence * 100)
            density.append(weighted_ordered_overlap(
                a, make(points(lat, lon, bearing, count=68))).adherence * 100)
    cell = h3.latlng_to_cell(21, 105.82, resolution)
    lat, lon = h3.cell_to_latlng(cell)
    a = make(points(lat, lon, 0, length=10))
    b = make(points(lat, lon, 90, length=10))
    assert all(abs(value - 100) < 1e-8 for value in values[0])
    rows.append({
        'resolution': resolution,
        'route_cells_median': statistics.median(counts),
        'offset_overlap_pct': {
            str(k): {'median': round(statistics.median(v), 2),
                     'min': round(min(v), 2), 'max': round(max(v), 2)}
            for k, v in values.items()},
        'reverse_overlap_pct_median': round(statistics.median(reversals), 2),
        'same_geometry_different_sampling_pct': {
            'median': round(statistics.median(density), 2), 'min': round(min(density), 2)},
        'different_10m_routes_inside_same_cell_pct': round(
            weighted_ordered_overlap(a, b).adherence * 100, 2),
        'reversed_10m_route_inside_same_cell_pct': round(
            weighted_ordered_overlap(a, make(points(lat, lon, 0, length=10)[::-1])).adherence * 100, 2),
    })
report = {
    'scope': 'Synthetic sensitivity experiment using unchanged production signature and '
             'similarity functions; resolution and sample step overridden only in this '
             'process. No real-road or GPS accuracy claim.',
    'h3_version': h3.__version__, 'route_length_m': 2000,
    'locations': 10, 'bearings': [0, 45, 90],
    'route_pairs_per_offset_per_resolution': 30, 'results': rows,
}
Path('runtime/h3-resolution-review/sensitivity.json').write_text(
    json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
