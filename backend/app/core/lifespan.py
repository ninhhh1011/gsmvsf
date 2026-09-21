"""Application lifespan management."""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from backend.app.services import graphhopper

from backend.app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    configure_logging()
    logger.info("application_startup", version="0.1.0")
    # ponytail: one application per process, matching existing service singletons.
    async with httpx.AsyncClient(timeout=60.0) as client:
        graphhopper.http_client = client
        try:
            yield
        finally:
            graphhopper.http_client = None
            from backend.app.api.v1.candidate import set_candidate_service
            from backend.app.api.v1.map_match import _segment_resolver
            set_candidate_service(None)
            if _segment_resolver is not None:
                _segment_resolver.close()
    logger.info("application_shutdown")
