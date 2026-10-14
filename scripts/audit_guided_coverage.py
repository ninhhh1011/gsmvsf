"""Offline candidate-reference road coverage from causal paired GPS; no labels or DDL on canonical data."""
import argparse
import asyncio
import csv
from datetime import timedelta
import gzip
import json
import math
import re

import asyncpg
import h3

from backend.app.config import settings
from backend.app.services.route_familiarity.deviations import GuidedTrip, MAX_GAP_S, MAX_JUMP_M
from backend.app.services.route_familiarity.route_matcher import _haversine_m
from scripts.seed_synthetic_journeys import output_directory, seed_time

ROAD_TYPES = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified',
              'residential', 'living_street', 'service', 'motorway_link', 'trunk_link',
              'primary_link', 'secondary_link', 'tertiary_link'}


def road_midpoint(pairs):
    lengths = [_haversine_m((a[1], a[0]), (b[1], b[0])) for a, b in zip(pairs, pairs[1:])]
    remaining = sum(lengths) / 2
    for a, b, length in zip(pairs, pairs[1:], lengths):
        if remaining <= length and length:
            fraction = remaining / length
            return a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1])
        remaining -= length
    return pairs[0]


def reference_roads(source):
    seen = set()
    with gzip.open(source, 'rt', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            if (row['base_segment_id'] in seen or row['road_type'] not in ROAD_TYPES or
                    row['access'] not in ('', 'yes', 'permissive') or row['osm_way_id'] == '881947000'):
                continue
            seen.add(row['base_segment_id'])
            pairs = [list(map(float, point.split())) for point in row['geometry'][12:-1].split(',')]
            if not pairs or any(len(point) != 2 or not all(math.isfinite(v) for v in point) for point in pairs):
                raise ValueError('Malformed canonical reference geometry')
            lon, lat = road_midpoint(pairs)
            if not (settings.map_bbox_min_lat <= lat <= settings.map_bbox_max_lat and
                    settings.map_bbox_min_lng <= lon <= settings.map_bbox_max_lng):
                continue
            yield row['base_segment_id'], h3.latlng_to_cell(lat, lon, 5), row['geometry'], lat, lon


def continuous_paths(trip, lower):
    current = []
    for point in trip.observations:
        if point.at < lower:
            if len(current) > 1:
                yield current
            current = []
            continue
        if current:
            previous = current[-1]
            seconds = (point.at - previous.at).total_seconds()
            distance = _haversine_m(previous.coordinates, point.coordinates)
            if seconds > MAX_GAP_S or distance > MAX_JUMP_M or distance / seconds > 55:
                if len(current) > 1:
                    yield current
                current = []
        current.append(point)
    if len(current) > 1:
        yield current


async def audit(args):
    as_of = seed_time(args.as_of)
    output = output_directory(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.exclude_batch and not re.fullmatch('[a-f0-9]{12}', args.exclude_batch):
        raise ValueError('Invalid batch identifier')
    references = list(reference_roads(settings.dataset_path / 'map/processed/road_segments.csv.gz'))
    async with asyncpg.create_pool(args.database_url, min_size=1, max_size=1) as pool:
        async with pool.acquire() as conn:
            rows = await conn.fetch('''SELECT evidence FROM synthetic.route_deviation_trips
                WHERE completed_at >= $1 AND completed_at <= $2
                  AND ($3::text IS NULL OR driver_id NOT LIKE 'h3-road-' || $3 || '-%')
                ORDER BY driver_id,trip_id LIMIT 10001''', as_of - timedelta(days=7), as_of, args.exclude_batch)
            if len(rows) > 10000:
                raise ValueError('Paired audit work limit exceeded')
            paths = set()
            for row in rows:
                trip = GuidedTrip.model_validate_json(row['evidence'])
                for path in continuous_paths(trip, as_of - timedelta(days=7)):
                    paths.add('LINESTRING (' + ','.join(f'{p.coordinates[1]} {p.coordinates[0]}' for p in path) + ')')
            await conn.execute('CREATE TEMP TABLE reference_input (id text, region text, wkt text, latitude float8, longitude float8)')
            await conn.copy_records_to_table('reference_input', records=references)
            await conn.execute('''CREATE TEMP TABLE audit_roads AS SELECT id,region,latitude,longitude,
                ST_Transform(ST_GeomFromText(wkt,4326),32648) AS geom FROM reference_input''')
            await conn.execute('CREATE TEMP TABLE audit_paths (wkt text)')
            await conn.copy_records_to_table('audit_paths', records=[(path,) for path in paths])
            # Spatial proximity measures evidence, not verified directed road identity/access.
            await conn.execute('''CREATE TEMP TABLE footprint AS SELECT
                ST_UnaryUnion(ST_Collect(ST_Buffer(ST_Transform(ST_GeomFromText(wkt,4326),32648),12))) AS geom
                FROM audit_paths''')
            await conn.execute('CREATE TEMP TABLE footprint_parts AS SELECT ST_Subdivide(geom,256) AS geom FROM footprint')
            await conn.execute('CREATE INDEX ON footprint_parts USING gist(geom)')
            await conn.execute('ANALYZE footprint_parts')
            await conn.execute('''CREATE TEMP TABLE road_coverage AS SELECT r.*,
                ST_Length(r.geom) AS reference_length_m,
                coalesce((SELECT ST_Length(ST_UnaryUnion(ST_Collect(ST_Intersection(r.geom,f.geom))))
                    FROM footprint_parts f WHERE r.geom && f.geom AND ST_Intersects(r.geom,f.geom)),0) AS covered_length_m
                FROM audit_roads r''')
            regions = [dict(row) for row in await conn.fetch('''SELECT region,
                sum(reference_length_m) AS reference_length_m,sum(covered_length_m) AS covered_length_m
                FROM road_coverage GROUP BY region ORDER BY region''')]
            for region in regions:
                region['coverage_pct'] = round(100 * region['covered_length_m'] / region['reference_length_m'], 2)
            targets = [dict(row) for row in await conn.fetch('''WITH ranked AS (
                SELECT *,row_number() OVER (PARTITION BY region ORDER BY reference_length_m-covered_length_m DESC,id) AS rank
                FROM road_coverage WHERE reference_length_m-covered_length_m > 100)
                SELECT id,region,latitude,longitude FROM ranked WHERE rank <= 2 ORDER BY rank,region LIMIT 36''')]
    total = sum(region['reference_length_m'] for region in regions)
    covered = sum(region['covered_length_m'] for region in regions)
    report = {'status': 'PASS', 'as_of': as_of.isoformat(), 'source': 'synthetic',
        'lookback_days': 7, 'paired_trip_count': len(rows), 'distinct_continuous_paths': len(paths),
        'reference_physical_segments': len(references), 'reference_length_m': total,
        'covered_reference_length_m': covered, 'reference_coverage_pct': round(100 * covered / total, 2) if total else None,
        'eligible_road_coverage_pct': None, 'tolerance_m': 12, 'projection': 'EPSG:32648',
        'excluded_batch': args.exclude_batch,
        'bbox': [settings.map_bbox_min_lat, settings.map_bbox_min_lng, settings.map_bbox_max_lat, settings.map_bbox_max_lng],
        'regions': regions,
        'limitations': 'Candidate reference roads by canonical class/access, not authoritative motorcar permissions. '
            'Roads bucketed by approximate geodesic midpoint into H3-5, not clipped regions or districts. '
            'GPS proximity can include nearby parallel roads; '
            'physical road geometry is deduplicated, direction is not a coverage claim. Legacy signatures excluded.'}
    (output / 'coverage-summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'targets.json').write_text(json.dumps({'source_as_of': as_of.isoformat(), 'targets': targets}, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('paired_trip_count', 'reference_physical_segments',
        'distinct_continuous_paths', 'reference_coverage_pct')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', default='runtime/h3-coverage')
    parser.add_argument('--exclude-batch', help='Reproduce a pre-extension source cohort without deleting stored trips')
    parser.add_argument('--database-url', default=settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'))
    asyncio.run(audit(parser.parse_args()))


if __name__ == '__main__':
    main()
