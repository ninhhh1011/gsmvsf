import csv
import gzip

import h3

from scripts.audit_guided_coverage import continuous_paths, reference_roads, road_midpoint, intersect_bbox, local_targets
from backend.tests.test_route_deviations import evidence, point, BASE


def test_reference_roads_deduplicate_directions_and_do_not_include_restricted_or_nonmotor_roads(tmp_path):
    row = {'base_segment_id': 'road', 'road_type': 'residential', 'access': 'yes',
           'osm_way_id': '1', 'geometry': 'LINESTRING (105.8 21,105.81 21)'}
    source = tmp_path / 'roads.csv.gz'
    with gzip.open(source, 'wt', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerows([row, row, {**row, 'base_segment_id': 'private', 'access': 'private'},
                         {**row, 'base_segment_id': 'foot', 'road_type': 'footway'},
                         {**row, 'base_segment_id': 'patched', 'osm_way_id': '881947000'}])
    result = list(reference_roads(source))
    assert len(result) == 1 and result[0][0] == 'road'


def test_coverage_paths_do_not_fill_unobserved_gaps_or_pre_window_points():
    trip = evidence([point(i * 20) for i in range(8)], times=[0, 5, 10, 15, 120, 125, 130, 135])
    paths = list(continuous_paths(trip, BASE))
    assert len(paths) == 2 and all(len(path) == 4 for path in paths)
    assert paths[0][-1].at < paths[1][0].at
    paths = list(continuous_paths(trip, trip.observations[4].at))
    assert len(paths) == 1 and len(paths[0]) == 4


def test_cross_region_road_and_seed_target_use_same_geometric_midpoint():
    pairs = [[105.65, 21], [106.05, 21]]
    lon, lat = road_midpoint(pairs)
    assert abs(lon - 105.85) < 1e-8 and lat == 21
    assert h3.latlng_to_cell(lat, lon, 5) != h3.latlng_to_cell(21, 106.05, 5)


def test_scope_intersection_and_local_targets_reject_trunks_duplicates_and_outside_map():
    bbox = intersect_bbox([105.6, 20.8, 106.1, 21.25], [105.73, 20.66, 106.04, 21.13])
    assert bbox == [105.73, 20.8, 106.04, 21.13]
    rows = [{'id': 'a', 'latitude': 21, 'longitude': 105.8, 'road_type': 'residential'},
            {'id': 'same', 'latitude': 21.00001, 'longitude': 105.80001, 'road_type': 'service'},
            {'id': 'trunk', 'latitude': 21.03, 'longitude': 105.9, 'road_type': 'trunk'},
            {'id': 'outside', 'latitude': 21.2, 'longitude': 105.8, 'road_type': 'residential'},
            {'id': 'b', 'latitude': 21.06, 'longitude': 105.9, 'road_type': 'residential'}]
    selected = local_targets(rows, bbox, 20)
    assert {row['id'] for row in selected} == {'a', 'b'}
    assert len({row['local_cell'] for row in selected}) == 2
