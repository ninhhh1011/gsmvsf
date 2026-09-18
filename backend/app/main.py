"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.map_match import router as map_match_router
from backend.app.api.v1.realtime import router as realtime_router
from backend.app.api.v1.demand import router as demand_router
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
    app.include_router(map_match_router, prefix="/api/v1", tags=["map-matching"])
    app.include_router(realtime_router, prefix="/api/v1", tags=["realtime"])
    app.include_router(demand_router, prefix="/api/v1", tags=["demand"])

    # Serve debug UI
    static_path = settings.app_path / "static" / "debug-map"
    index_file = static_path / "index.html"

    if index_file.exists():
        @app.get("/debug-map")
        async def debug_map_index():
            """Serve debug map index page."""
            return HTMLResponse(content=index_file.read_text())

        # Also mount static files under /debug-map/assets
        app.mount(
            "/debug-map/static",
            StaticFiles(directory=str(static_path)),
            name="debug-map-static"
        )

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {"app": settings.app_name, "version": settings.app_version}

    return app


app = create_app()
