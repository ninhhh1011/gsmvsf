"""
Multi-Leg Routing and Detour Calculator for Week 3.

Computes:
- Leg 1: Driver -> Station
- Leg 2: Station -> Destination
- Direct Route: Driver -> Destination
- Via Total: Leg 1 + Leg 2
- Detour: Via Total - Direct Route
- Base ETA: duration_to_station_s

Week 6: Supports configurable concurrent routing for improved latency.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.app.services.candidate.models import CandidateRouteMetrics
from backend.app.services.routing.engine import RoutingEngine, raise_for_routing_failure
from backend.app.services.routing.models import (
    Position,
    RouteRequest,
    RouteResult,
    RouteStatus,
    VehicleRoutingProfile,
)

logger = logging.getLogger(__name__)

# Default max concurrent route computations (Week 6 productionization)
DEFAULT_MAX_CONCURRENT_ROUTES = 8


class MultiLegRouteCalculator:
    """
    Computes multi-leg routing metrics between driver, station, and destination.
    Supports concurrent routing for reduced latency.
    """

    def __init__(self, engine: RoutingEngine, max_concurrent_routes: int = DEFAULT_MAX_CONCURRENT_ROUTES):
        self.engine = engine
        self.max_concurrent_routes = max_concurrent_routes

    async def compute_direct_route(
        self,
        driver_pos: Position,
        destination_pos: Optional[Position],
        profile: Optional[VehicleRoutingProfile] = None,
    ) -> Optional[RouteResult]:
        """
        Compute direct driver -> destination route once for the candidate search request.
        """
        if destination_pos is None:
            return None

        req = RouteRequest(origin=driver_pos, destination=destination_pos, profile=profile)
        res = await self.engine.route(req)
        raise_for_routing_failure(res)
        return res

    async def compute_station_metrics(
        self,
        driver_pos: Position,
        station_pos: Position,
        destination_pos: Optional[Position] = None,
        cached_direct_route: Optional[RouteResult] = None,
        profile: Optional[VehicleRoutingProfile] = None,
    ) -> tuple[bool, Optional[CandidateRouteMetrics], Optional[RouteResult]]:
        """
        Compute complete route metrics for a station candidate.
        Returns:
            (is_reachable, route_metrics, leg1_route_result)
        """
        # Leg 1: Driver -> Station
        req_leg1 = RouteRequest(origin=driver_pos, destination=station_pos, profile=profile)
        res_leg1 = await self.engine.route(req_leg1)
        raise_for_routing_failure(res_leg1)

        if res_leg1.status != RouteStatus.SUCCESS:
            # Station unreachable from current driver position
            return (False, None, res_leg1)

        leg1_dist = res_leg1.distance_m
        leg1_dur = res_leg1.duration_s

        # If destination is missing, return station-leg metrics only
        if destination_pos is None:
            metrics = CandidateRouteMetrics(
                distance_to_station_m=round(leg1_dist, 1),
                duration_to_station_s=round(leg1_dur, 1),
                eta_to_station_s=round(leg1_dur, 1),
            )
            return (True, metrics, res_leg1)

        # Leg 2: Station -> Destination
        req_leg2 = RouteRequest(origin=station_pos, destination=destination_pos, profile=profile)
        res_leg2 = await self.engine.route(req_leg2)
        raise_for_routing_failure(res_leg2)

        # Direct route (use cached if provided)
        res_direct = cached_direct_route
        if res_direct is None:
            res_direct = await self.compute_direct_route(driver_pos, destination_pos, profile=profile)

        if res_direct is not None:
            raise_for_routing_failure(res_direct)

        if res_leg2.status == RouteStatus.SUCCESS:
            leg2_dist = res_leg2.distance_m
            leg2_dur = res_leg2.duration_s

            via_dist = leg1_dist + leg2_dist
            via_dur = leg1_dur + leg2_dur

            direct_available = res_direct is not None and res_direct.status == RouteStatus.SUCCESS
            direct_dist = res_direct.distance_m if direct_available else None
            direct_dur = res_direct.duration_s if direct_available else None
            detour_dist = max(0.0, via_dist - direct_dist) if direct_available else None
            detour_dur = max(0.0, via_dur - direct_dur) if direct_available else None

            metrics = CandidateRouteMetrics(
                distance_to_station_m=round(leg1_dist, 1),
                duration_to_station_s=round(leg1_dur, 1),
                distance_station_to_dest_m=round(leg2_dist, 1),
                duration_station_to_dest_s=round(leg2_dur, 1),
                via_total_distance_m=round(via_dist, 1),
                via_total_duration_s=round(via_dur, 1),
                direct_distance_m=round(direct_dist, 1) if direct_available else None,
                direct_duration_s=round(direct_dur, 1) if direct_available else None,
                detour_distance_m=round(detour_dist, 1) if direct_available else None,
                detour_duration_s=round(detour_dur, 1) if direct_available else None,
                eta_to_station_s=round(leg1_dur, 1),
            )
            return (True, metrics, res_leg1)

        # No onward road route: the station remains reachable, with station-leg metrics only.
        metrics = CandidateRouteMetrics(
            distance_to_station_m=round(leg1_dist, 1),
            duration_to_station_s=round(leg1_dur, 1),
            eta_to_station_s=round(leg1_dur, 1),
        )
        return (True, metrics, res_leg1)

    async def compute_all_station_metrics_concurrent(
        self,
        driver_pos: Position,
        station_positions: dict[str, Position],
        destination_pos: Optional[Position],
        profile: Optional[VehicleRoutingProfile] = None,
        cached_direct_route: Optional[RouteResult] = None,
    ) -> dict[str, tuple[bool, Optional[CandidateRouteMetrics], Optional[RouteResult]]]:
        """
        Compute route metrics for all stations concurrently with bounded parallelism.

        Args:
            driver_pos: Driver's current position
            station_positions: Dict of station_id -> station Position
            destination_pos: Trip destination position (optional)
            profile: Vehicle routing profile
            cached_direct_route: Pre-computed direct route (optional)

        Returns:
            Dict of station_id -> (is_reachable, route_metrics, leg1_route_result)
        """
        if not station_positions:
            return {}

        # Pre-compute direct route if not provided (avoid redundant calls)
        if cached_direct_route is None and destination_pos is not None:
            try:
                cached_direct_route = await self.compute_direct_route(
                    driver_pos, destination_pos, profile
                )
            except Exception:
                # If direct route fails, continue without it
                cached_direct_route = None

        semaphore = asyncio.Semaphore(self.max_concurrent_routes)

        async def compute_one(
            station_id: str,
            station_pos: Position,
        ) -> tuple[str, bool, Optional[CandidateRouteMetrics], Optional[RouteResult]]:
            async with semaphore:
                result = await self.compute_station_metrics(
                    driver_pos=driver_pos,
                    station_pos=station_pos,
                    destination_pos=destination_pos,
                    cached_direct_route=cached_direct_route,
                    profile=profile,
                )
                return (station_id, *result)

        tasks = [
            compute_one(station_id, station_pos)
            for station_id, station_pos in station_positions.items()
        ]

        results = await asyncio.gather(*tasks)

        return {
            station_id: (reachable, metrics, leg1)
            for station_id, reachable, metrics, leg1 in results
        }
