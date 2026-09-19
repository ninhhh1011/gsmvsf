"""
Routing Engine Interface and Exceptions.

Defines the engine-independent protocol for all routing adapters (OSRM, Mock, etc.).
"""

from typing import Protocol, runtime_checkable
from backend.app.services.routing.models import RouteRequest, RouteResult


class RoutingEngineError(Exception):
    """Base exception for routing engine failures."""
    pass


class RoutingEngineUnavailableError(RoutingEngineError):
    """Routing engine backend is unreachable or unhealthy."""
    pass


class RouteNotFoundError(RoutingEngineError):
    """No viable route between requested points on the road network."""
    pass


class RoutingTimeoutError(RoutingEngineError):
    """Routing engine query timed out."""
    pass


class RoutingInvalidRequestError(RoutingEngineError):
    """Invalid routing coordinates, waypoints, or profile."""
    pass


@runtime_checkable
class RoutingEngine(Protocol):
    """
    Project-level routing engine contract.
    Decoupled from specific backend implementations.
    """

    async def route(self, request: RouteRequest) -> RouteResult:
        """
        Compute a route matching the given RouteRequest.
        Must never return silent 0.0 distance or 0.0 duration on failure.
        """
        ...

    async def is_healthy(self) -> bool:
        """Check health and connectivity of routing backend."""
        ...
