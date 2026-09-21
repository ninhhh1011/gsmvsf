"""Import only canonical operational source rows; run with python -B."""
import argparse
import asyncio
import csv
import gzip
import json
import sys
from itertools import islice
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import settings
from backend.app.services.snapshots.ingestion import IngestionService
from backend.app.services.snapshots.models import snapshot_adapter
from backend.app.services.snapshots.repository import SnapshotRepository


def iter_snapshots(dataset_path: Path):
    for kind, filename, entity_field in [
        ('station', 'stations/station_status.csv.gz', 'station_id'),
        ('queue', 'queue/queue_status.csv.gz', 'station_id'),
        ('traffic', 'traffic/traffic_snapshots.csv.gz', 'segment_id'),
    ]:
        with gzip.open(dataset_path / filename, 'rt', encoding='utf-8', newline='') as handle:
            for row in csv.DictReader(handle):
                row['entity_id'] = row.pop(entity_field)
                row.update(kind=kind, source='dataset-v1.3.1')
                # Count contracts intentionally reject strings at API boundaries.
                for field, value in row.items():
                    if field.endswith(('_slots', '_batteries', '_length', '_count')):
                        row[field] = int(value)
                yield snapshot_adapter.validate_python(row)


async def load_snapshots(service: IngestionService, snapshots, batch_size: int = 1000):
    if batch_size < 1 or batch_size > 10000:
        raise ValueError('batch_size must be between 1 and 10000')
    counts = {'read': 0, 'created': 0}
    iterator = iter(snapshots)
    while batch := list(islice(iterator, batch_size)):
        counts['created'] += await service.ingest_many(batch)
        counts['read'] += len(batch)
    return counts


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default='postgresql://postgres:postgres@127.0.0.1:5432/ev_recommendation')
    parser.add_argument('--batch-size', type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 10000:
        parser.error('--batch-size must be between 1 and 10000')
    dsn = args.database_url.replace('postgresql+asyncpg://', 'postgresql://').replace(
        'postgresql+psycopg2://', 'postgresql://')
    async with asyncpg.create_pool(dsn, min_size=1, max_size=2, timeout=5) as pool:
        repository = SnapshotRepository(pool)
        await repository.setup()
        counts = await load_snapshots(IngestionService(repository), iter_snapshots(settings.dataset_path),
                                      args.batch_size)
        totals = await pool.fetch('SELECT kind,count(*) AS count FROM state_snapshots GROUP BY kind')
        print(json.dumps(counts | {'stored_by_kind': {row['kind']: row['count'] for row in totals}}))


if __name__ == '__main__':
    asyncio.run(main())
