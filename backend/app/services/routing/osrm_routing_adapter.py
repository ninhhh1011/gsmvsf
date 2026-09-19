"""
OSRM Routing Adapter implementing the RoutingEngine protocol.

Connects to the canonical local OSRM HTTP daemon (osrm-routed) loaded with hanoi-patched.osrm.
Translates between domain RouteRequest/RouteResult and OSRM JSON schemas.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import httpx

from backend.app.config import settings
from backend.app.services.routing.engine import RoutingEngine
from backend.app.services.routing.models import (
    Position,
    RouteLeg,
    RouteRequest,
    RouteResult,
    RouteStatus,
)

logger = logging.getLogger(__name__)


class OSRMRoutingAdapter(RoutingEngine):
    """
    Adapter communicating with OSRM HTTP API (/route/v1/driving).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 5.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = (base_url or settings.osrm_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self.timeout_seconds)

    def _format_coordinates(self, origin: Position, destination: Position, via: list[Position]) -> str:
        """
        Format coordinates as 'lon,lat;lon,lat;...' as expected by OSRM.
        OSRM strictly requires longitude first, then latitude.
        """
        points = [origin] + list(via) + [destination]
        return ";".join(f"{p.longitude:.6f},{p.latitude:.6f}" for p in points)

    async def route(self, request: RouteRequest) -> RouteResult:
        """
        Execute route request against OSRM /route/v1/{profile}.
        """
        profile = "driving"
        if request.profile and request.profile.routing_profile_hint:
            profile = request.profile.routing_profile_hint

        coord_str = self._format_coordinates(request.origin, request.destination, request.via)
        url = f"{self.base_url}/route/v1/{profile}/{coord_str}"
        params = {
            "overview": "simplified",
            "geometries": "polyline",
            "steps": "false",
            "annotations": "false",
        }

        should_close_client = self._client is None
        client = await self._get_client()

        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                code = data.get("code")

                if code == "Ok":
                    routes = data.get("routes", [])
                    if not routes:
                        return RouteResult(
                            status=RouteStatus.NO_ROUTE,
                            distance_m=float("inf"),
                            duration_s=float("inf"),
                            engine_name="osrm",
                            error_message="OSRM returned Ok but empty routes list",
                        )

                    primary = routes[0]
                    total_dist = float(primary.get("distance", 0.0))
                    total_dur = float(primary.get("duration", 0.0))
                    geometry = primary.get("geometry")

                    # Parse legs
                    legs: list[RouteLeg] = []
                    all_points = [request.origin] + list(request.via) + [request.destination]
                    raw_legs = primary.get("legs", [])

                    for i, raw_leg in enumerate(raw_legs):
                        from_p = all_points[i]
                        to_p = all_points[i + 1] if (i + 1) < len(all_points) else all_points[-1]
                        leg = RouteLeg(
                            from_position=from_p,
                            to_position=to_p,
                            distance_m=float(raw_leg.get("distance", 0.0)),
                            duration_s=float(raw_leg.get("duration", 0.0)),
                        )
                        legs.append(leg)

                    # If no legs parsed but total distance exists, synthesize single leg
                    if not legs:
                        legs.append(
                            RouteLeg(
                                from_position=request.origin,
                                to_position=request.destination,
                                distance_m=total_dist,
                                duration_s=total_dur,
                                geometry=geometry,
                            )
                        )

                    return RouteResult(
                        status=RouteStatus.SUCCESS,
                        distance_m=total_dist,
                        duration_s=total_dur,
                        legs=legs,
                        geometry=geometry,
                        engine_name="osrm",
                        raw_metadata={"waypoints": data.get("waypoints", [])},
                    )

                elif code == "NoRoute":
                    return RouteResult(
                        status=RouteStatus.NO_ROUTE,
                        distance_m=float("inf"),
                        duration_s=float("inf"),
                        engine_name="osrm",
                        error_message="OSRM could not find route between coordinates",
                    )
                else:
                    return RouteResult(
                        status=RouteStatus.INVALID_REQUEST,
                        distance_m=float("inf"),
                        duration_s=float("inf"),
                        engine_name="osrm",
                        error_message=f"OSRM returned error code: {code} - {data.get('message', '')}",
                    )

            elif response.status_code == 400:
                return RouteResult(
                    status=RouteStatus.INVALID_REQUEST,
                    distance_m=float("inf"),
                    duration_s=float("inf"),
                    engine_name="osrm",
                    error_message=f"OSRM 400 Bad Request: {response.text}",
                )
            else:
                return RouteResult(
                    status=RouteStatus.ENGINE_ERROR,
                    distance_m=float("inf"),
                    duration_s=float("inf"),
                    engine_name="osrm",
                    error_message=f"OSRM HTTP {response.status_code}: {response.text}",
                )

        except httpx.TimeoutException as e:
            logger.warning("OSRM request timeout: %s", e)
            return RouteResult(
                status=RouteStatus.TIMEOUT,
                distance_m=float("inf"),
                duration_s=float("inf"),
                engine_name="osrm",
                error_message=f"OSRM request timed out: {e}",
            )
        except httpx.RequestError as e:
            logger.warning("OSRM connection error: %s", e)
            return RouteResult(
                status=RouteStatus.ENGINE_ERROR,
                distance_m=float("inf"),
                duration_s=float("inf"),
                engine_name="osrm",
                error_message=f"OSRM connection failed: {e}",
            )
        finally:
            if should_close_client:
                await client.aclose()

    async def is_healthy(self) -> bool:
        """Check if OSRM service is reachable."""
        # Simple query between two central Hanoi points
        test_req = RouteRequest(
            origin=Position(latitude=21.015, longitude=105.780),
            destination=Position(latitude=21.032, longitude=105.760),
        )
        res = await self.route(test_req)
        return res.status == RouteStatus.SUCCESS
