"""OSRM adapter for map matching."""
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class OsrmAdapterError(Exception):
    """Base exception for OSRM adapter errors."""
    pass


class OsrmUnavailableError(OsrmAdapterError):
    """OSRM service is unavailable."""
    pass


class OsrmNoMatchError(OsrmAdapterError):
    """OSRM returned NoMatch for the trace."""
    pass


class OsrmTimeoutError(OsrmAdapterError):
    """OSRM request timed out."""
    pass


class OsrmBadRequestError(OsrmAdapterError):
    """OSRM returned a bad request error."""
    pass


class Tracepoint:
    """Represents a matched tracepoint from OSRM."""

    def __init__(
        self,
        waypoint_index: int,
        location: tuple[float, float],
        distance: float,
        name: str,
        matched: bool,
        alternatives_count: int = 0,
        matchings_index: Optional[int] = None,
        waypoint_index_in_match: Optional[int] = None,
        null_reason: Optional[str] = None,
    ):
        self.waypoint_index = waypoint_index
        self.location = location  # (lon, lat)
        self.distance = distance  # distance from input
        self.name = name
        self.matched = matched
        self.alternatives_count = alternatives_count
        self.matchings_index = matchings_index
        self.waypoint_index_in_match = waypoint_index_in_match
        self.null_reason = null_reason

    @classmethod
    def from_osrm(cls, data: Optional[dict], index: int) -> "Tracepoint":
        """Create from OSRM tracepoint data or null."""
        if data is None:
            return cls(
                waypoint_index=index,
                location=(0.0, 0.0),
                distance=0.0,
                name="",
                matched=False,
                null_reason="null_tracepoint",
            )
        return cls(
            waypoint_index=data.get("waypoint_index", index),
            location=tuple(data["location"]),  # [lon, lat]
            distance=data.get("distance", 0.0),
            name=data.get("name", ""),
            matched=True,
            alternatives_count=data.get("alternatives_count", 0),
            matchings_index=data.get("matchings_index"),
            waypoint_index_in_match=data.get("waypoint_index"),
        )


class RouteLeg:
    """Represents a leg of the matched route."""

    def __init__(
        self,
        distance: float,
        duration: float,
        annotation_nodes: Optional[list[int]] = None,
    ):
        self.distance = distance
        self.duration = duration
        self.annotation_nodes = annotation_nodes or []


class Matching:
    """Represents an OSRM matching (route)."""

    def __init__(
        self,
        confidence: float,
        distance: float,
        duration: float,
        geometry: str,
        tracepoints: list[Tracepoint],
        legs: Optional[list[RouteLeg]] = None,
    ):
        self.confidence = confidence
        self.distance = distance  # total matched distance
        self.duration = duration  # total matched duration
        self.geometry = geometry  # polyline encoding
        self.tracepoints = tracepoints
        self.legs = legs or []

    @classmethod
    def from_osrm(
        cls,
        data: dict,
        tracepoints: list[Tracepoint],
        include_annotations: bool = False,
    ) -> "Matching":
        """Create from OSRM matching data."""
        legs = []

        if include_annotations:
            legs_data = data.get("legs", [])
            for leg_data in legs_data:
                annotation = leg_data.get("annotation", {})
                leg = RouteLeg(
                    distance=leg_data.get("distance", 0.0),
                    duration=leg_data.get("duration", 0.0),
                    annotation_nodes=annotation.get("nodes", []),
                )
                legs.append(leg)

        return cls(
            confidence=data.get("confidence", 0.0),
            distance=data.get("distance", 0.0),
            duration=data.get("duration", 0.0),
            geometry=data.get("geometry", ""),
            tracepoints=tracepoints,
            legs=legs,
        )

    def get_route_nodes(self) -> list[int]:
        """
        Get the complete ordered list of OSM node IDs from route annotations.

        Returns:
            Ordered list of OSM node IDs
        """
        all_nodes = []
        for leg in self.legs:
            all_nodes.extend(leg.annotation_nodes)
        return all_nodes


class OsrmMapMatchingAdapter:
    """Adapter for OSRM map matching API."""

    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def match(
        self,
        coordinates: list[tuple[float, float]],
        overview: str = "simplified",
        annotations: bool = False,
    ) -> tuple[Matching, list[Tracepoint]]:
        """
        Match GPS coordinates to road network.

        Args:
            coordinates: List of (longitude, latitude) tuples
            overview: 'simplified', 'full', or 'false'
            annotations: Include node annotations for segment resolution

        Returns:
            Tuple of (Matching object, list of Tracepoints)

        Raises:
            OsrmUnavailableError: If OSRM is not reachable
            OsrmBadRequestError: If request is malformed
            OsrmNoMatchError: If no match found
            OsrmTimeoutError: If request times out
        """
        if not coordinates:
            raise OsrmBadRequestError("No coordinates provided")

        # Format coordinates: lon,lat;lon,lat;...
        coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates)

        url = f"{self.base_url}/match/v1/driving/{coords_str}"
        params = {
            "overview": overview,
            "steps": "true" if annotations else "false",
        }

        if annotations:
            params["annotations"] = "nodes"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
        except httpx.TimeoutException as e:
            raise OsrmTimeoutError(f"OSRM request timed out: {e}")
        except httpx.ConnectError as e:
            raise OsrmUnavailableError(f"Cannot connect to OSRM: {e}")
        except httpx.HTTPError as e:
            raise OsrmUnavailableError(f"OSRM HTTP error: {e}")

        if response.status_code == 400:
            raise OsrmBadRequestError(f"Bad request: {response.text[:200]}")
        elif response.status_code == 404:
            raise OsrmUnavailableError("OSRM endpoint not found")
        elif response.status_code >= 500:
            raise OsrmUnavailableError(f"OSRM server error: {response.status_code}")
        elif response.status_code != 200:
            raise OsrmBadRequestError(f"OSRM returned {response.status_code}: {response.text[:200]}")

        data = response.json()

        code = data.get("code", "")
        if code != "Ok":
            raise OsrmNoMatchError(f"OSRM returned code: {code}")

        # Parse tracepoints
        osrm_tracepoints = data.get("tracepoints", [])
        tracepoints = []
        for i in range(len(coordinates)):
            tp_data = osrm_tracepoints[i] if i < len(osrm_tracepoints) else None
            tracepoints.append(Tracepoint.from_osrm(tp_data, i))

        # Parse matchings
        matchings_data = data.get("matchings", [])
        if not matchings_data:
            raise OsrmNoMatchError("No matching returned")

        matching = Matching.from_osrm(
            matchings_data[0],
            tracepoints,
            include_annotations=annotations,
        )

        return matching, tracepoints
