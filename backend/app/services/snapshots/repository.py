"""PostgreSQL is authoritative for immutable snapshots and search evidence."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg

from backend.app.services.ranking.models import CandidateSearchEvidence
from backend.app.services.snapshots.models import Snapshot, StateError, aware_utc, snapshot_adapter


class SnapshotRepository:
    def __init__(self, pool: asyncpg.Pool, timeout_s: float = 30):
        self.pool = pool
        self.timeout_s = timeout_s

    @asynccontextmanager
    async def connection(self):
        try:
            async with asyncio.timeout(self.timeout_s), self.pool.acquire() as connection:
                yield connection
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError) as exc:
            raise StateError('Snapshot database unavailable', 'SNAPSHOT_DATABASE_UNAVAILABLE') from exc

    async def setup(self) -> None:
        async with self.connection() as connection:
            await connection.execute(Path(__file__).with_name('schema.sql').read_text('utf-8'))

    async def ingest(self, snapshot: Snapshot) -> tuple[Snapshot, bool]:
        created = await self.ingest_many([snapshot])
        return snapshot, bool(created)

    async def ingest_many(self, snapshots: list[Snapshot]) -> int:
        """Commit one bounded batch; any immutable-key conflict rejects the whole batch."""
        unique = {}
        for snapshot in snapshots:
            previous = unique.setdefault(snapshot.snapshot_id, snapshot)
            if previous != snapshot:
                raise StateError('Conflicting snapshot retry', 'SNAPSHOT_CONFLICT', 409)
        if not unique:
            return 0
        # Same lock order avoids deadlocks for concurrent overlapping batches.
        ordered = sorted(unique.values(), key=lambda value: (value.kind, value.entity_id, value.timestamp))
        ids = [UUID(value.snapshot_id) for value in ordered]
        payloads = [value.model_dump_json() for value in ordered]
        async with self.connection() as connection, connection.transaction():
            inserted = await connection.fetch('''
                INSERT INTO state_snapshots
                    (snapshot_id,kind,entity_id,timestamp,source,schema_version,payload)
                SELECT * FROM unnest($1::uuid[], $2::text[], $3::text[],
                    $4::timestamptz[], $5::text[], $6::integer[], $7::jsonb[])
                ON CONFLICT DO NOTHING RETURNING snapshot_id
                ''', ids, [value.kind for value in ordered], [value.entity_id for value in ordered],
                [value.timestamp for value in ordered], [value.source for value in ordered],
                [value.schema_version for value in ordered], payloads)
            # Separate statement sees a concurrently committed ON CONFLICT winner.
            conflict = await connection.fetchval('''
                SELECT EXISTS (
                    SELECT 1 FROM unnest($1::uuid[], $2::jsonb[]) AS incoming(id,payload)
                    LEFT JOIN state_snapshots stored ON stored.snapshot_id=incoming.id
                    WHERE stored.payload IS DISTINCT FROM incoming.payload
                )''', ids, payloads)
            if conflict:
                raise StateError('Conflicting snapshot retry', 'SNAPSHOT_CONFLICT', 409)
            return len(inserted)

    async def heads(self, keys: list[str], request_time: datetime) -> dict[str, str | None]:
        request_time = aware_utc(request_time)
        parts = [key.split(':', 1) for key in keys]
        if any(len(part) != 2 or part[0] not in ('station', 'queue', 'traffic') or not part[1]
               for part in parts):
            raise ValueError('Invalid snapshot key')
        async with self.connection() as connection:
            rows = await connection.fetch('''
                SELECT requested.key, latest.snapshot_id
                FROM unnest($1::text[], $2::text[], $3::text[]) AS requested(key,kind,entity_id)
                LEFT JOIN LATERAL (
                    SELECT snapshot_id FROM state_snapshots snapshot
                    WHERE snapshot.kind=requested.kind AND snapshot.entity_id=requested.entity_id
                        AND snapshot.timestamp <= $4
                    ORDER BY snapshot.timestamp DESC LIMIT 1
                ) latest ON TRUE
                ''', keys, [part[0] for part in parts], [part[1] for part in parts], request_time)
        return {row['key']: str(row['snapshot_id']) if row['snapshot_id'] else None for row in rows}

    async def payloads(self, ids: list[str]) -> dict[str, Snapshot]:
        async with self.connection() as connection:
            rows = await connection.fetch('SELECT snapshot_id,payload FROM state_snapshots '
                                          'WHERE snapshot_id=ANY($1::uuid[])', [UUID(id) for id in ids])
        return {str(row['snapshot_id']): snapshot_adapter.validate_json(row['payload']) for row in rows}

    async def existing_segments(self, ids: list[str]) -> set[str]:
        async with self.connection() as connection:
            rows = await connection.fetch('SELECT segment_id FROM road_segments '
                                          'WHERE segment_id=ANY($1::text[])', ids)
        return {row['segment_id'] for row in rows}

    async def save_search(self, evidence: CandidateSearchEvidence) -> None:
        async with self.connection() as connection, connection.transaction():
            await connection.execute('''INSERT INTO candidate_searches(candidate_search_id,payload)
                VALUES ($1,$2::jsonb) ON CONFLICT DO NOTHING''',
                evidence.candidate_search_id, evidence.model_dump_json())
            matches = await connection.fetchval('''SELECT payload=$2::jsonb FROM candidate_searches
                WHERE candidate_search_id=$1''', evidence.candidate_search_id, evidence.model_dump_json())
            if not matches:
                raise StateError('Conflicting candidate search identity', 'CANDIDATE_SEARCH_CONFLICT', 409)

    async def get_search(self, search_id: str) -> CandidateSearchEvidence:
        async with self.connection() as connection:
            payload = await connection.fetchval('SELECT payload FROM candidate_searches '
                                                 'WHERE candidate_search_id=$1', search_id)
        if payload is None:
            raise StateError('Candidate search not found', 'CANDIDATE_SEARCH_NOT_FOUND', 404)
        return CandidateSearchEvidence.model_validate_json(payload)
