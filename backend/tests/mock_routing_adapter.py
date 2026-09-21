"""
In-Memory Mock Routing Adapter implementing RoutingEngine.

Provides fast, deterministic route computation without requiring an external routing service.
Uses Haversine distance with configurable urban road network tortuosity and speed.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.app.services.routing.engine import RoutingEngine
from backend.app.services.routing.models import (
    Position,
    RouteLeg,
    RouteRequest,
    RouteResult,
    RouteStatus,
)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in meters between two lat/lon points."""
    r = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


class MockRoutingAdapter(RoutingEngine):
    """
    In-memory mock routing engine for unit testing and offline evaluation.
    """

    def __init__(
        self,
        winding_factor: float = 1.3,
        average_speed_mps: float = 8.33,  # ~30 km/h urban speed
        force_status: Optional[RouteStatus] = None,
    ):
        self.winding_factor = winding_factor
        self.average_speed_mps = average_speed_mps
        self.force_status = force_status
        self.unreachable_points: set[tuple[float, float]] = set()

    def set_unreachable_point(self, lat: float, lon: float) -> None:
        """Mark a specific coordinate as unreachable on the road network."""
        self.unreachable_points.add((round(lat, 5), round(lon, 5)))

    async def route(self, request: RouteRequest) -> RouteResult:
        """Compute synthetic route between coordinates."""
        if self.force_status is not None:
            return RouteResult(
                status=self.force_status,
                distance_m=float("inf") if self.force_status != RouteStatus.SUCCESS else 1000.0,
                duration_s=float("inf") if self.force_status != RouteStatus.SUCCESS else 120.0,
                engine_name="mock",
                error_message=f"Forced status {self.force_status}",
            )

        # Check unreachable
        dest_coord = (round(request.destination.latitude, 5), round(request.destination.longitude, 5))
        if dest_coord in self.unreachable_points:
            return RouteResult(
                status=RouteStatus.NO_ROUTE,
                distance_m=float("inf"),
                duration_s=float("inf"),
                engine_name="mock",
                error_message="Destination marked unreachable in mock adapter",
            )

        points = [request.origin] + list(request.via) + [request.destination]
        total_distance = 0.0
        legs: list[RouteLeg] = []

        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            straight_dist = _haversine_meters(p1.latitude, p1.longitude, p2.latitude, p2.longitude)
            road_dist = straight_dist * self.winding_factor
            leg_dur = road_dist / self.average_speed_mps

            total_distance += road_dist
            legs.append(
                RouteLeg(
                    from_position=p1,
                    to_position=p2,
                    distance_m=round(road_dist, 1),
                    duration_s=round(leg_dur, 1),
                )
            )

        total_duration = total_distance / self.average_speed_mps

        return RouteResult(
            status=RouteStatus.SUCCESS,
            distance_m=round(total_distance, 1),
            duration_s=round(total_duration, 1),
            legs=legs,
            geometry="mock_polyline",
            engine_name="mock",
        )

    async def is_healthy(self) -> bool:
        return True
