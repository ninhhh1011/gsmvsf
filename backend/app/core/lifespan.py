"""Application lifespan management."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import asyncpg
import httpx
from backend.app.config import settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.services.realtime.driver_state_manager import DriverStateManager
from backend.app.services.realtime.driver_state_repository import RedisDriverStateRepository
from backend.app.services.realtime.state import DriverStateStore
from fastapi import FastAPI
from redis.asyncio import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    configure_logging()
    logger.info("application_startup", version="0.1.0")
    async with httpx.AsyncClient(timeout=60.0) as client, asyncpg.create_pool(
        settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'),
        min_size=0, max_size=10, timeout=settings.snapshot_db_timeout_s,
        command_timeout=settings.snapshot_db_timeout_s,
        server_settings={'search_path': 'realtime,public'},
    ) as pool, Redis.from_url(settings.redis_url,
        socket_connect_timeout=settings.snapshot_cache_timeout_s,
        socket_timeout=settings.snapshot_cache_timeout_s,
        retry=Retry(NoBackoff(), 0),
    ) as redis:
        from backend.app.services.ranking.models import RankingPolicy
        from backend.app.services.ranking.orchestration import RecommendationWorkflow
        from backend.app.services.snapshots.ingestion import IngestionService
        from backend.app.services.snapshots.repository import SnapshotRepository
        from backend.app.services.snapshots.resolver import SnapshotCache, SnapshotResolver
        from backend.app.services.route_familiarity.repository import RouteHistoryRepository
        from backend.app.services.route_familiarity.ingestion import RouteHistoryIngestion
        app.state.db_pool = pool
        app.state.route_history_repository = RouteHistoryRepository(pool)
        app.state.route_history_ingestion = RouteHistoryIngestion(app.state.route_history_repository)
        app.state.redis = redis
        app.state.http_client = client
        app.state.driver_state_repository = RedisDriverStateRepository(client=redis)
        app.state.driver_state_manager = DriverStateManager(repository=app.state.driver_state_repository)
        app.state.driver_state_store = DriverStateStore()

        from backend.app.services.candidate.service import CandidateSearchService
        from backend.app.services.demand.capability import VehicleCapabilityResolver
        from backend.app.services.demand.service import DemandService
        from backend.app.services.map_matching.graphhopper_adapter import (
            GraphHopperMapMatchingAdapter,
        )
        from backend.app.services.map_matching.segment_resolver import (
            RouteConstrainedSegmentResolver,
        )
        from backend.app.services.map_matching.service import MapMatchingService
        from backend.app.services.routing.graphhopper_routing_adapter import (
            GraphHopperRoutingAdapter,
        )

        capability_resolver = VehicleCapabilityResolver()
        routing_adapter = GraphHopperRoutingAdapter(client=client)
        app.state.routing_adapter = routing_adapter
        app.state.capability_resolver = capability_resolver
        app.state.candidate_service = CandidateSearchService(
            routing_engine=routing_adapter, capability_resolver=capability_resolver)
        app.state.demand_service = DemandService(capability_resolver=capability_resolver)
        app.state.segment_resolver = RouteConstrainedSegmentResolver(pool)
        app.state.map_matching_service = MapMatchingService(
            GraphHopperMapMatchingAdapter(base_url=settings.graphhopper_base_url, client=client),
            app.state.segment_resolver,
        )

        repository = SnapshotRepository(pool, timeout_s=settings.snapshot_db_timeout_s)
        policy = RankingPolicy(missing_queue_wait_s=settings.missing_queue_wait_s,
            station_fresh_s=settings.station_fresh_s, queue_fresh_s=settings.queue_fresh_s,
            traffic_fresh_s=settings.traffic_fresh_s)
        cache = SnapshotCache(redis, settings.snapshot_cache_ttl_s, prefix=settings.snapshot_cache_prefix)
        resolver = SnapshotResolver(repository, cache, policy)
        app.state.snapshot_resolver = resolver
        app.state.snapshot_ingestion = IngestionService(repository, cache=cache)
        app.state.recommendation_workflow = RecommendationWorkflow(repository, resolver,
            routing_adapter, policy=policy)
        from backend.app.services.snapshots.simulator import RealtimeSimulator
        simulator = RealtimeSimulator()
        app.state.realtime_simulator = simulator
        if settings.enable_realtime_simulator:
            simulator.start_background(app.state.snapshot_ingestion, interval_s=settings.realtime_simulator_interval_s)
        try:
            yield
        finally:
            if simulator is not None:
                await simulator.stop()
            app.state.realtime_simulator = None
            app.state.recommendation_workflow = None
            app.state.snapshot_ingestion = None
            app.state.route_history_ingestion = None
            app.state.route_history_repository = None
            app.state.candidate_service = None
            app.state.demand_service = None
            app.state.capability_resolver = None
            app.state.map_matching_service = None
            app.state.segment_resolver = None
            app.state.db_pool = None
            app.state.redis = None
            app.state.http_client = None
            app.state.driver_state_manager = None
            app.state.driver_state_repository = None
            app.state.driver_state_store = None
    logger.info("application_shutdown")
