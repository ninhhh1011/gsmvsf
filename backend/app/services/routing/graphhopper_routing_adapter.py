"""Translate domain routing requests to the GraphHopper 11 HTTP contract."""
from __future__ import annotations

import math
from typing import Optional

import httpx

from backend.app.config import settings
from backend.app.services import graphhopper
from backend.app.services.graphhopper import profile_for_vehicle
from backend.app.services.routing.engine import RoutingEngine
from backend.app.services.routing.models import (
    DynamicRoutingContext, OptimizationObjective, Position, RouteConstraints,
    RouteLeg, RouteRequest, RouteResult, RouteStatus, VehicleRoutingProfile,
)


def _failure(status: RouteStatus, message: str) -> RouteResult:
    return RouteResult(status=status, distance_m=float("inf"), duration_s=float("inf"),
                       engine_name="graphhopper", error_message=message)


def _metric(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Route metrics must be numbers")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Route metrics must be finite and nonnegative")
    return float(value)


class GraphHopperRoutingAdapter(RoutingEngine):
    def __init__(self, base_url: Optional[str] = None, timeout_seconds: float = 10.0,
                 client: Optional[httpx.AsyncClient] = None):
        self.base_url = (base_url or settings.graphhopper_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client or graphhopper.http_client

    async def route(self, request: RouteRequest) -> RouteResult:
        try:
            profile = profile_for_vehicle(request.profile.vehicle_category if request.profile else None)
            if request.profile.routing_profile_hint:
                raise ValueError("Engine profile hints are unsupported; supply vehicle_category")
            if request.constraints and request.constraints != RouteConstraints():
                raise ValueError("Route constraints are not supported by the current adapter")
            if request.objective != OptimizationObjective.MIN_TRAVEL_TIME:
                raise ValueError("Only MIN_TRAVEL_TIME is supported")
            if request.dynamic_context and request.dynamic_context != DynamicRoutingContext():
                raise ValueError("Dynamic routing context is not supported by the current adapter")
        except ValueError as exc:
            return _failure(RouteStatus.INVALID_REQUEST, str(exc))

        points = [request.origin, *request.via, request.destination]
        params = {
            "point": [f"{p.latitude:.6f},{p.longitude:.6f}" for p in points],
            "profile": profile, "points_encoded": "true", "instructions": "false",
            "details": ["leg_distance", "leg_time"],
        }
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.get(f"{self.base_url}/route", params=params, timeout=self.timeout_seconds)
            if response.status_code != 200:
                status = RouteStatus.ENGINE_ERROR
                if response.status_code == 400:
                    status = RouteStatus.INVALID_REQUEST
                    try:
                        hints = response.json().get("hints", [])
                        if any(hint.get("details", "").rsplit(".", 1)[-1] in
                               {"ConnectionNotFoundException", "PointNotFoundException"} for hint in hints):
                            status = RouteStatus.NO_ROUTE
                    except (ValueError, TypeError, AttributeError):
                        pass
                return _failure(status, f"GraphHopper HTTP {response.status_code}: {response.text[:200]}")

            path = response.json()["paths"][0]
            distance = _metric(path["distance"])
            duration_ms = _metric(path["time"])
            geometry = path["points"]
            if not isinstance(geometry, str) or not geometry:
                raise ValueError("Expected encoded points string")
            distances = path["details"]["leg_distance"]
            times = path["details"]["leg_time"]
            if not isinstance(distances, list) or not isinstance(times, list) or len(distances) != len(points) - 1 or len(times) != len(distances):
                raise ValueError("Missing route leg details")
            legs = []
            previous_end = 0
            for index, (dist, time) in enumerate(zip(distances, times)):
                if (len(dist) != 3 or len(time) != 3 or dist[:2] != time[:2]
                        or any(type(i) is not int for i in dist[:2])
                        or dist[0] != previous_end or dist[1] < dist[0]):
                    raise ValueError("Invalid route leg detail intervals")
                previous_end = dist[1]
                legs.append(RouteLeg(from_position=points[index], to_position=points[index + 1],
                                     distance_m=_metric(dist[2]), duration_s=_metric(time[2]) / 1000))
            if (not math.isclose(sum(leg.distance_m for leg in legs), distance, abs_tol=0.1)
                    or not math.isclose(sum(leg.duration_s for leg in legs), duration_ms / 1000, abs_tol=0.001)):
                raise ValueError("Route leg totals disagree with path totals")
            return RouteResult(status=RouteStatus.SUCCESS, distance_m=distance,
                               duration_s=duration_ms / 1000, legs=legs, geometry=geometry,
                               engine_name="graphhopper", raw_metadata={"profile": profile})
        except httpx.TimeoutException as exc:
            return _failure(RouteStatus.TIMEOUT, f"GraphHopper request timed out: {exc}")
        except httpx.RequestError as exc:
            return _failure(RouteStatus.ENGINE_ERROR, f"GraphHopper connection failed: {exc}")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            return _failure(RouteStatus.ENGINE_ERROR, f"Malformed GraphHopper response: {exc}")
        finally:
            if self._client is None:
                await client.aclose()

    async def is_healthy(self) -> bool:
        """Both production profiles must successfully route on the loaded graph."""
        for category in ("EV_CAR", "EV_MOTORBIKE"):
            result = await self.route(RouteRequest(
                origin=Position(latitude=21.028, longitude=105.854),
                destination=Position(latitude=21.036, longitude=105.830),
                profile=VehicleRoutingProfile(vehicle_category=category),
            ))
            if result.status != RouteStatus.SUCCESS:
                return False
        return True
