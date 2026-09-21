"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.map_match import router as map_match_router
from backend.app.api.v1.realtime import router as realtime_router
from backend.app.api.v1.demand import router as demand_router
from backend.app.api.v1.candidate import router as candidate_router
from backend.app.api.v1.ranking import router as ranking_router
from backend.app.services.snapshots.models import StateError
from backend.app.services.routing.engine import RoutingEngineError
from backend.app.api.v1.candidate import _routing_http_error
from backend.app.core.lifespan import lifespan
from backend.app.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(health_router, tags=["health"])
    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    app.include_router(map_match_router, prefix="/api/v1", tags=["map-matching"])
    app.include_router(realtime_router, prefix="/api/v1", tags=["realtime"])
    app.include_router(demand_router, prefix="/api/v1", tags=["demand"])
    app.include_router(candidate_router, prefix="/api/v1", tags=["candidate-search"])
    app.include_router(ranking_router, prefix="/api/v1", tags=["ranking"])

    @app.exception_handler(StateError)
    async def state_error_handler(request, exc):
        return JSONResponse(status_code=exc.status, content=exc.detail)

    @app.exception_handler(RoutingEngineError)
    async def routing_error_handler(request, exc):
        error = _routing_http_error(exc)
        return JSONResponse(status_code=error.status_code, content={'detail': error.detail})

    # Serve debug UI
    static_path = settings.app_path / "static" / "debug-map"
    index_file = static_path / "index.html"

    if index_file.exists():
        @app.get("/debug-map")
        async def debug_map_index():
            """Serve debug map index page."""
            return HTMLResponse(content=index_file.read_text())

        app.mount(
            "/debug-map/static",
            StaticFiles(directory=str(static_path)),
            name="debug-map-static"
        )

    # Serve Demo UI (Week 5.5)
    demo_path = settings.app_path / "static" / "demo"
    demo_index = demo_path / "index.html"

    if demo_path.exists() and demo_index.exists():
        @app.get("/demo")
        @app.get("/demo/")
        async def demo_page():
            """Serve Week 5.5 Demo UI."""
            return HTMLResponse(content=demo_index.read_text(encoding="utf-8"))

        app.mount(
            "/demo/static",
            StaticFiles(directory=str(demo_path)),
            name="demo-static"
        )

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {"app": settings.app_name, "version": settings.app_version}

    return app


app = create_app()
