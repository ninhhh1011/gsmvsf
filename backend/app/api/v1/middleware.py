"""
API Middleware for rate limiting and request logging.
"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
import time
from collections import defaultdict


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter."""
    
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(list)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host
        path = request.url.path
        if path.startswith("/api/v1/drivers/") or path.startswith("/api/v1/debug/") or path == "/health":
            return await call_next(request)

        now = time.time()
        
        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip]
            if now - req_time < 60
        ]
        
        # Check rate limit
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."}
            )
        
        # Record request
        self.requests[client_ip].append(now)
        
        # Process request
        return await call_next(request)


def setup_middleware(app):
    """Apply all middleware to the FastAPI app."""
    from .middleware import RateLimitMiddleware
    
    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=100
    )
