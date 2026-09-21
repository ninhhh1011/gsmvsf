"""GraphHopper 11 OSS GPX matching with project-defined observation projection."""
import math
import xml.etree.ElementTree as ET

import httpx

from backend.app.config import settings
from backend.app.services import graphhopper
from backend.app.services.graphhopper import profile_for_vehicle
from backend.app.services.map_matching.engine import (
    Matching, Tracepoint, MapMatchingEngineError, MapMatchingEngineUnavailableError,
    MapMatchingNoMatchError, MapMatchingTimeoutError, MapMatchingInvalidRequestError,
)


def _encode_polyline(coordinates):
    result, previous = [], [0, 0]
    for lon, lat in coordinates:
        for axis, value in enumerate((lat, lon)):
            current = math.floor(value * 1e5 + 0.5)
            delta = current - previous[axis]
            previous[axis] = current
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 0x20:
                result.append(chr((0x20 | (encoded & 0x1f)) + 63))
                encoded >>= 5
            result.append(chr(encoded + 63))
    return "".join(result)


def _project(point, geometry):
    """Local metric projection on the returned path, not a substitute routing engine."""
    lon, lat = point
    scale_x, scale_y = 111195 * math.cos(math.radians(lat)), 111195
    candidates = []
    # ponytail: O(observations * path edges); spatial index if long traces dominate.
    for index, (a, b) in enumerate(zip(geometry, geometry[1:])):
        ax, ay = (a[0] - lon) * scale_x, (a[1] - lat) * scale_y
        dx, dy = (b[0] - a[0]) * scale_x, (b[1] - a[1]) * scale_y
        length2 = dx * dx + dy * dy
        if not length2:
            continue
        t = max(0, min(1, -(ax * dx + ay * dy) / length2))
        distance = math.hypot(ax + t * dx, ay + t * dy)
        candidate = (distance, index, (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])),
                     math.degrees(math.atan2(dx, dy)) % 360)
        candidates.append(candidate)
    if not candidates:
        raise MapMatchingNoMatchError("Matched path has no traversable geometry")
    best = min(candidates, key=lambda candidate: candidate[0])
    tied = [candidate for candidate in candidates if candidate[0] <= best[0] + 0.05]
    # Revisited geometry cannot establish traversal order from position alone.
    bearing = best[3]
    if any(abs((candidate[3] - bearing + 180) % 360 - 180) > 45 for candidate in tied):
        bearing = None
    return best[0], [candidate[1] for candidate in tied], best[2], bearing


class GraphHopperMapMatchingAdapter:
    def __init__(self, base_url=None, timeout=60.0, client=None):
        self.base_url = (base_url or settings.graphhopper_base_url).rstrip("/")
        self.timeout = timeout
        self._client = client or graphhopper.http_client

    async def match(self, coordinates, *, vehicle_category):
        try:
            profile = profile_for_vehicle(vehicle_category)
            if len(coordinates) < 2 or any(
                not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90)
                for lon, lat in coordinates
            ):
                raise ValueError("At least two finite valid coordinates required")
        except (ValueError, TypeError) as exc:
            raise MapMatchingInvalidRequestError(str(exc)) from exc
        gpx = ET.Element("gpx", version="1.1", creator="build6week")
        segment = ET.SubElement(ET.SubElement(gpx, "trk"), "trkseg")
        for lon, lat in coordinates:
            ET.SubElement(segment, "trkpt", lat=str(lat), lon=str(lon))
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.post(
                self.base_url + "/match", content=ET.tostring(gpx),
                headers={"Content-Type": "application/gpx+xml"},
                params={"profile": profile, "points_encoded": "false", "instructions": "false",
                        "way_point_max_distance": 0, "details": "osm_way_id", "gps_accuracy": 20},
            )
            if response.status_code == 400:
                message = response.text[:500]
                if any(s in message.lower() for s in ("sequence is broken", "no candidates", "not found", "cannot find", "no match")):
                    raise MapMatchingNoMatchError(message)
                raise MapMatchingInvalidRequestError(message)
            if response.status_code != 200:
                raise MapMatchingEngineUnavailableError(f"GraphHopper HTTP {response.status_code}")
            try:
                data = response.json()
                if not data.get("paths"):
                    raise MapMatchingNoMatchError("GraphHopper returned no path")
                path = data["paths"][0]
                geometry = path["points"]["coordinates"]
                if len(geometry) < 2 or any(len(p) != 2 or not all(math.isfinite(v) for v in p)
                                           or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90) for p in geometry):
                    raise ValueError("Invalid matched path geometry")
                distance, duration = float(path["distance"]), float(path["time"]) / 1000
                if not all(math.isfinite(v) and v >= 0 for v in (distance, duration)):
                    raise ValueError("Invalid matched path metrics")
                details = path.get("details", {}).get("osm_way_id", [])
                for start, end, way in details:
                    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start <= end < len(geometry)
                            and isinstance(way, int) and way > 0):
                        raise ValueError("Invalid OSM way detail")
            except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
                raise MapMatchingEngineError("Malformed GraphHopper matching response") from exc
            tracepoints = []
            for index, point in enumerate(coordinates):
                offset, edges, snapped, bearing = _project(point, geometry)
                ways = {next((w for start, end, w in details if start <= edge < end), None) for edge in edges}
                way = next(iter(ways)) if len(ways) == 1 else None
                if len(ways) > 1:
                    bearing = None
                matched = offset <= 100.0
                tracepoints.append(Tracepoint(index, snapped, offset, "", matched,
                                              way if matched else None, bearing if matched else None,
                                              ("ambiguous_path_projection" if bearing is None else None) if matched else "outside_matched_path_tolerance"))
            quality = sum(max(0, 1 - p.distance / 100) for p in tracepoints) / len(tracepoints)
            return Matching(quality, distance, duration, _encode_polyline(geometry), tracepoints, profile), tracepoints
        except httpx.TimeoutException as exc:
            raise MapMatchingTimeoutError("GraphHopper matching timed out") from exc
        except httpx.RequestError as exc:
            raise MapMatchingEngineUnavailableError("GraphHopper unavailable") from exc
        finally:
            if self._client is None:
                await client.aclose()
