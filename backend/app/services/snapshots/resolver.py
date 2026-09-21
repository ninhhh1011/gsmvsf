"""Pin DB versions once; use Redis only for validated immutable payloads."""
import json
from collections import Counter
from datetime import datetime, timezone
from time import perf_counter

from pydantic import ValidationError
from redis.exceptions import RedisError

from backend.app.core.logging import get_logger
from backend.app.services.ranking.models import RankingPolicy
from backend.app.services.snapshots.models import ResolvedSnapshot, StateError, snapshot_adapter

logger = get_logger(__name__)

# Fixed-width UTC timestamps compare lexically, including subsecond ordering.
# Redis guarantees Lua script atomicity; no client-side read/write race.
LATEST_CAS = '''
local raw = redis.call('GET', KEYS[1])
if raw then
    local ok, old = pcall(cjson.decode, raw)
    if ok and type(old) == 'table' and type(old.stamp) == 'string'
       and old.stamp > ARGV[1] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
'''


class SnapshotCache:
    def __init__(self, client, ttl_s=60, prefix='week4:snapshot:'):
        if ttl_s < 1:
            raise ValueError('Cache TTL must be positive')
        self.client, self.ttl_s, self.prefix = client, ttl_s, prefix

    def key(self, entity_key):
        return f'{self.prefix}{entity_key}:latest'

    async def get_many(self, keys):
        if not keys:
            return {}
        values = await self.client.mget([self.key(key) for key in keys])
        result = {}
        for key, raw in zip(keys, values):
            if raw is None:
                continue
            try:
                parsed = json.loads(raw)
                snapshot = snapshot_adapter.validate_python(parsed['payload'])
                if snapshot.key == key:
                    result[key] = snapshot
            except (ValueError, TypeError, KeyError, ValidationError):
                logger.warning('snapshot_cache_corrupt', key=key)
        return result

    async def put(self, snapshot):
        stamp = snapshot.timestamp.isoformat(timespec='microseconds')
        value = json.dumps({'stamp': stamp, 'payload': snapshot.model_dump(mode='json')})
        return await self.client.eval(LATEST_CAS, 1, self.key(snapshot.key), stamp, value, self.ttl_s)

    async def populate_latest(self, repository, keys):
        """An empty/expired cache must not turn a historical read into latest state."""
        heads = await repository.heads(list(keys), datetime.max.replace(tzinfo=timezone.utc))
        values = await repository.payloads([sid for sid in heads.values() if sid])
        for snapshot in values.values():
            await self.put(snapshot)


class SnapshotResolver:
    def __init__(self, repository, cache=None, policy=None):
        self.repository, self.cache = repository, cache
        self.policy = policy or RankingPolicy()
        self.metrics = Counter()

    async def resolve(self, keys, request_time):
        started = perf_counter()
        keys = sorted(set(keys))
        # One MVCC statement pins a consistent view; payload rows are immutable.
        heads = await self.repository.heads(keys, request_time)
        cached = {}
        if self.cache is not None:
            try:
                cached = await self.cache.get_many(keys)
            except (RedisError, OSError, TimeoutError):
                self.metrics['cache_error'] += 1
                logger.warning('snapshot_cache_unavailable', operation='read')
        selected, missing_ids = {}, []
        hits = misses = 0
        for key in keys:
            sid = heads[key]
            value = cached.get(key)
            if sid and value is not None and value.snapshot_id == sid:
                selected[key] = value
                hits += 1
            elif sid:
                missing_ids.append(sid)
                misses += 1
        payloads = await self.repository.payloads(missing_ids) if missing_ids else {}
        for key in keys:
            sid = heads[key]
            if sid and key not in selected:
                value = payloads.get(sid)
                if value is None or value.snapshot_id != sid or value.key != key:
                    raise StateError('Pinned snapshot payload is unavailable or inconsistent')
                selected[key] = value
        if misses and self.cache is not None:
            try:
                await self.cache.populate_latest(self.repository,
                    [key for key in keys if heads[key] in missing_ids])
            except (RedisError, OSError, TimeoutError, StateError):
                # Pinned payloads are already read; cache maintenance is best effort.
                self.metrics['cache_error'] += 1
                logger.warning('snapshot_cache_unavailable', operation='write')
        result = {key: ResolvedSnapshot.resolve(selected.get(key), request_time,
                  getattr(self.policy, key.split(':', 1)[0] + '_fresh_s')) for key in keys}
        self.metrics.update(cache_hit=hits, cache_miss=misses, db_fallback=misses,
                            lookups=1, stale=sum(v.freshness == 'STALE' for v in result.values()),
                            missing=sum(v.freshness == 'MISSING' for v in result.values()))
        logger.info('snapshot_lookup', latency_ms=round((perf_counter()-started)*1000, 3),
                    entities=len(keys), cache_hit=hits, cache_miss=misses, db_fallback=misses,
                    stale_count=sum(v.freshness == 'STALE' for v in result.values()),
                    snapshot_ages_s=[v.snapshot_age_s for v in result.values()])
        return result
