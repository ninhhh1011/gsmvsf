"""FastAPI application entry point."""
from fastapi import FastAPI

from backend.app.api.v1.health import router as health_router
from backend.app.core.lifespan import lifespan
from backend.app.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    return app


app = create_app()


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"app": settings.app_name, "version": settings.app_version}
