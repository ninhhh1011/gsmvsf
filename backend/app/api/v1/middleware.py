"""
API Middleware for rate limiting and request logging.
"""
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter with in-memory sliding window. Redis-based limiting can be added as future enhancement."""

    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host
        path = request.url.path

        # Exempt health endpoint only (rate limiting applies to /drivers/ and all /api/v1/ endpoints)
        if path == "/health":
            return await call_next(request)

        now = time.time()
        # Clean old requests outside lock window
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if now - req_time < 60
        ]

        if len(self.requests[client_ip]) >= self.requests_per_minute:
            retry_after = 60
            from backend.app.core.metrics import record_request
            route = request.scope.get('route')
            record_request('429', endpoint=getattr(route, 'path', path))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": str(retry_after)}
            )

        self.requests[client_ip].append(now)
        response = await call_next(request)
        from backend.app.core.metrics import record_request
        route = request.scope.get('route')
        record_request(str(response.status_code), endpoint=getattr(route, 'path', path))
        return response


def setup_middleware(app):
    """Apply all middleware to the FastAPI app."""
    from .middleware import RateLimitMiddleware

    # Rate limiting - applies to all /api/v1/ endpoints including /drivers/
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=100
    )
