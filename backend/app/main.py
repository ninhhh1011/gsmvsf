"""FastAPI application entry point."""

from backend.app.api.v1.candidate import _routing_http_error
from backend.app.api.v1.candidate import router as candidate_router
from backend.app.api.v1.demand import router as demand_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.map_match import router as map_match_router
from backend.app.api.v1.metrics import router as metrics_router
from backend.app.api.v1.middleware import setup_middleware
from backend.app.api.v1.ranking import router as ranking_router
from backend.app.api.v1.realtime import router as realtime_router
from backend.app.api.v1.vehicles import router as vehicles_router
from backend.app.config import settings
from backend.app.core.lifespan import lifespan
from backend.app.services.routing.engine import RoutingEngineError
from backend.app.services.snapshots.models import StateError
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Apply middleware (rate limiting, request logging)
    setup_middleware(app)

    app.include_router(health_router, tags=["health"])
    app.include_router(health_router, prefix="/api/v1", tags=["health"])
    app.include_router(map_match_router, prefix="/api/v1", tags=["map-matching"])
    app.include_router(realtime_router, prefix="/api/v1", tags=["realtime"])
    app.include_router(demand_router, prefix="/api/v1", tags=["demand"])
    app.include_router(candidate_router, prefix="/api/v1", tags=["candidate-search"])
    app.include_router(ranking_router, prefix="/api/v1", tags=["ranking"])
    app.include_router(metrics_router, prefix="/api/v1", tags=["metrics"])
    app.include_router(vehicles_router, prefix="/api/v1", tags=["vehicles"])

    @app.exception_handler(StateError)
    async def state_error_handler(request, exc):
        return JSONResponse(status_code=exc.status, content=exc.detail)

    @app.exception_handler(RoutingEngineError)
    async def routing_error_handler(request, exc):
        error = _routing_http_error(exc)
        return JSONResponse(status_code=error.status_code, content={'detail': error.detail})

    # Serve Demo UI (Week 5.5)
    demo_path = settings.app_path / "static" / "demo"
    demo_index = demo_path / "index.html"

    if demo_path.exists() and demo_index.exists():
        @app.get("/demo", include_in_schema=False)
        @app.get("/demo/", include_in_schema=False)
        @app.get("/demo/technical", include_in_schema=False)
        @app.get("/demo/technical/", include_in_schema=False)
        async def demo_page():
            """Serve Demo UI (Driver Product & Technical View)."""
            return HTMLResponse(content=demo_index.read_text(encoding="utf-8"))

        app.mount(
            "/demo/static",
            StaticFiles(directory=str(demo_path)),
            name="demo-static"
        )

    @app.get("/api/v1/config", tags=["config"])
    async def get_config() -> dict:
        """Expose client-safe application & geographic configuration."""
        return {
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "city_name": settings.city_name,
            "map_center": {
                "latitude": settings.map_default_center_lat,
                "longitude": settings.map_default_center_lng,
            },
            "map_default_zoom": settings.map_default_zoom,
            "map_bounding_box": {
                "min_latitude": settings.map_bbox_min_lat,
                "min_longitude": settings.map_bbox_min_lng,
                "max_latitude": settings.map_bbox_max_lat,
                "max_longitude": settings.map_bbox_max_lng,
            },
        }

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {"app": settings.app_name, "version": settings.app_version}

    return app


app = create_app()
