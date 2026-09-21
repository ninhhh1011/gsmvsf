"""Application lifespan management."""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
import asyncpg
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from backend.app.services import graphhopper
from backend.app.config import settings

from backend.app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    configure_logging()
    logger.info("application_startup", version="0.1.0")
    # ponytail: one application per process, matching existing service singletons.
    async with httpx.AsyncClient(timeout=60.0) as client, asyncpg.create_pool(
        settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'),
        min_size=0, max_size=10, timeout=settings.snapshot_db_timeout_s,
        command_timeout=settings.snapshot_db_timeout_s,
    ) as pool, Redis.from_url(settings.redis_url,
        socket_connect_timeout=settings.snapshot_cache_timeout_s,
        socket_timeout=settings.snapshot_cache_timeout_s,
        retry=Retry(NoBackoff(), 0),
    ) as redis:
        graphhopper.http_client = client
        from backend.app.services.snapshots.repository import SnapshotRepository
        from backend.app.services.snapshots.resolver import SnapshotCache, SnapshotResolver
        from backend.app.services.snapshots.ingestion import IngestionService
        from backend.app.services.ranking.models import RankingPolicy
        from backend.app.services.ranking.orchestration import RecommendationWorkflow
        from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
        repository = SnapshotRepository(pool, timeout_s=settings.snapshot_db_timeout_s)
        policy = RankingPolicy(missing_queue_wait_s=settings.missing_queue_wait_s,
            station_fresh_s=settings.station_fresh_s, queue_fresh_s=settings.queue_fresh_s,
            traffic_fresh_s=settings.traffic_fresh_s)
        cache = SnapshotCache(redis, settings.snapshot_cache_ttl_s, prefix=settings.snapshot_cache_prefix)
        resolver = SnapshotResolver(repository, cache, policy)
        app.state.snapshot_resolver = resolver
        app.state.snapshot_ingestion = IngestionService(repository, cache=cache)
        app.state.recommendation_workflow = RecommendationWorkflow(repository, resolver,
            GraphHopperRoutingAdapter(client=client), policy=policy)
        try:
            yield
        finally:
            app.state.recommendation_workflow = None
            app.state.snapshot_ingestion = None
            graphhopper.http_client = None
            from backend.app.api.v1.candidate import set_candidate_service
            from backend.app.api.v1.map_match import _segment_resolver
            set_candidate_service(None)
            if _segment_resolver is not None:
                _segment_resolver.close()
    logger.info("application_shutdown")
