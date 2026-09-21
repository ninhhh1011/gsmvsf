"""
Routing Engine Interface and Exceptions.

Defines the engine-independent protocol for production and test routing adapters.
"""

from typing import Protocol, runtime_checkable
from backend.app.services.routing.models import RouteRequest, RouteResult, RouteStatus


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


def raise_for_routing_failure(result: RouteResult) -> None:
    """Keep infrastructure/request failures distinct from business unreachability."""
    error_type = {
        RouteStatus.ENGINE_ERROR: RoutingEngineUnavailableError,
        RouteStatus.TIMEOUT: RoutingTimeoutError,
        RouteStatus.INVALID_REQUEST: RoutingInvalidRequestError,
    }.get(result.status)
    if error_type:
        raise error_type(result.error_message or result.status.value)


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
