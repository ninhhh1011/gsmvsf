"""Confirmed guidance-departure origins, never visit-frequency or motivation."""
from bisect import bisect_right
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
import math

import h3
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.services.route_familiarity.route_matcher import (
    _EARTH_RADIUS_M, _haversine_m, _heading_deg, _heading_diff, _lerp, _tiles, prepare_route,
    match_and_compare_routes,
)
from backend.app.services.route_familiarity.similarity import ComparisonBudget, SimilarityWorkLimitExceeded

LATERAL_M = 45.0
CONFIRM_SAMPLES = 3
CONFIRM_DISTANCE_M = 30.0
MAX_GAP_S = 60.0
MAX_JUMP_M = 200.0


class TimedLocation(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    at: datetime
    coordinates: tuple[float, float]

    @field_validator('at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError('Observation time requires a timezone')
        return value

    @field_validator('coordinates')
    @classmethod
    def valid_location(cls, value):
        if not -90 <= value[0] <= 90 or not -180 <= value[1] <= 180:
            raise ValueError('Invalid latitude/longitude')
        return value


class GuidanceVersion(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    effective_at: datetime
    coordinates: list[tuple[float, float]] = Field(min_length=2, max_length=20000)

    @field_validator('effective_at')
    @classmethod
    def aware(cls, value):
        return TimedLocation.aware(value)

    @field_validator('coordinates')
    @classmethod
    def valid_coordinates(cls, value):
        for point in value:
            TimedLocation.valid_location(point)
        return value


class GuidedTrip(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    driver_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    trip_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    started_at: datetime
    completed_at: datetime
    guidance: list[GuidanceVersion] = Field(min_length=1, max_length=100)
    observations: list[TimedLocation] = Field(min_length=3, max_length=20000)

    @field_validator('started_at', 'completed_at')
    @classmethod
    def aware(cls, value):
        return TimedLocation.aware(value)

    @model_validator(mode='after')
    def chronology(self):
        if self.started_at >= self.completed_at:
            raise ValueError('Trip start must precede completion')
        times = [item.at for item in self.observations]
        versions = [item.effective_at for item in self.guidance]
        if any(a >= b for a, b in zip(times, times[1:])) or any(a >= b for a, b in zip(versions, versions[1:])):
            raise ValueError('Observation and guidance times must be strictly increasing')
        if (times[0] < self.started_at or times[-1] > self.completed_at or
                versions[0] > times[0] or versions[0] < self.started_at or versions[-1] > self.completed_at):
            raise ValueError('Evidence must be within trip time with guidance issued before observations')
        if sum(len(version.coordinates) for version in self.guidance) + len(times) > 40000:
            raise ValueError('Combined evidence exceeds work limit')
        return self


def _project(point, piece):
    scale = _EARTH_RADIUS_M * math.pi / 180
    cos_lat = math.cos(math.radians(piece.start[0]))
    dx = (piece.end[1] - piece.start[1]) * scale * cos_lat
    dy = (piece.end[0] - piece.start[0]) * scale
    px = (point[1] - piece.start[1]) * scale * cos_lat
    py = (point[0] - piece.start[0]) * scale
    squared = dx * dx + dy * dy
    t = min(1.0, max(0.0, (px * dx + py * dy) / squared)) if squared else 0.0
    projected = _lerp(piece.start, piece.end, t)
    return _haversine_m(point, projected), piece.offset_m + t * piece.length_m, projected


def _on_corridor(point, route, heading, last_offset, budget):
    margin = math.degrees(LATERAL_M / _EARTH_RADIUS_M)
    lon_margin = margin / max(0.01, math.cos(math.radians(point[0])))
    tiles = _tiles(point[0] - margin, point[0] + margin, point[1] - lon_margin, point[1] + lon_margin)
    if route.spatial_positions is None or tiles is None:
        raise ValueError('Unsupported geographic projection')
    candidates = {index for tile in tiles for index in route.spatial_positions.get(tile, ())}
    budget.consume(len(candidates))
    matches = []
    for index in candidates:
        piece = route.pieces[index]
        distance, offset, projected = _project(point, piece)
        if (distance <= LATERAL_M and offset >= last_offset - LATERAL_M and
                (heading is None or _heading_diff(heading, piece.heading) <= 60)):
            matches.append((distance, offset, projected))
    if not matches:
        return None, False
    matches.sort()
    best = matches[0]
    # Crossing/repeated corridors cannot establish one departure origin safely.
    ambiguous = any(abs(item[1] - best[1]) > 90 and abs(item[0] - best[0]) < 5 for item in matches[1:])
    return (None, True) if ambiguous else (best, False)


def analyze_guided_trip(trip: GuidedTrip, *, include_trace=False):
    sample_budget = ComparisonBudget(200000)
    routes = [prepare_route(version.coordinates, 9, sample_budget=sample_budget) for version in trip.guidance]
    if any(not route.pieces for route in routes):
        raise ValueError('Guidance must contain a nonzero route')
    times = [version.effective_at for version in trip.guidance]
    exposures, departures, pending_exposures, uncertain_origins = [], [], [], []
    current_version, previous, anchor = -1, None, None
    off_route, armed = False, False
    run_kind, run_count, run_distance, run_start = None, 0, 0.0, None
    last_offset, uncertain = 0.0, 0
    budget = ComparisonBudget(1000000)
    states = ['UNKNOWN'] * len(trip.observations) if include_trace else None
    run_indices = []
    for observation_index, observation in enumerate(trip.observations):
        version = bisect_right(times, observation.at) - 1
        distance = _haversine_m(previous.coordinates, observation.coordinates) if previous else 0.0
        gap = (observation.at - previous.at).total_seconds() if previous else 0.0
        broken = previous is not None and (gap > MAX_GAP_S or distance > MAX_JUMP_M or distance / gap > 55)
        if version != current_version or broken:
            if anchor and (broken or run_kind == 'off' and not off_route):
                uncertain_origins.append(anchor)
            uncertain += int(broken)
            current_version = version
            off_route, armed, anchor = False, False, None
            run_kind, run_count, run_distance, run_start = None, 0, 0.0, None
            last_offset, previous, distance = 0.0, None, 0.0
            pending_exposures = []
            run_indices = []
        heading = _heading_deg(previous.coordinates, observation.coordinates) if previous and distance >= 3 else None
        match, ambiguous = _on_corridor(observation.coordinates, routes[version], heading,
                                        0.0 if off_route else last_offset, budget)
        if ambiguous:
            if anchor:
                uncertain_origins.append(anchor)
            uncertain += 1
            armed, anchor, previous = False, None, None
            run_kind, run_count, run_distance = None, 0, 0.0
            pending_exposures = []
            run_indices = []
            continue
        on_route = match is not None
        if on_route:
            _, offset, projected = match
            last_offset = offset if off_route else max(last_offset, offset)
        kind = 'on' if on_route else 'off'
        if kind != run_kind:
            run_kind, run_count, run_distance = kind, 1, 0.0
            run_start = observation.at.timestamp()
            pending_exposures = []
            run_indices = []
        else:
            run_count += 1
            run_distance += distance
        confirmed = run_count >= CONFIRM_SAMPLES and run_distance >= CONFIRM_DISTANCE_M
        if include_trace:
            run_indices.append(observation_index)
            if confirmed:
                for index in run_indices:
                    states[index] = 'ON_ROUTE' if on_route else 'OFF_ROUTE'
                run_indices = []
        if on_route:
            pending_exposures.append((projected, observation.at.timestamp()))
            if confirmed:
                off_route, armed = False, True
            if armed:
                exposures.extend(pending_exposures)
                pending_exposures = []
            if not off_route:
                anchor = (match[2], observation.at.timestamp())
        elif armed and not off_route and confirmed and anchor:
            departures.append((anchor[0], run_start))
            # Departure-time exposure keeps numerator and denominator in the same window.
            exposures.append((anchor[0], run_start))
            off_route, armed = True, False
        previous = observation
    if (trip.completed_at - trip.observations[-1].at).total_seconds() > MAX_GAP_S:
        uncertain += 1
        if anchor:
            uncertain_origins.append(anchor)
    if run_kind == 'off' and not off_route and anchor:
        uncertain += 1
        uncertain_origins.append(anchor)
    cells = {}
    for resolution in range(5, 11):
        values = defaultdict(lambda: {'reached': [], 'departures': [], 'uncertain': [], 'observed': []})
        for observation in trip.observations:
            values[h3.latlng_to_cell(*observation.coordinates, resolution)]['observed'].append(observation.at.timestamp())
        for coordinates, at in exposures:
            values[h3.latlng_to_cell(*coordinates, resolution)]['reached'].append(at)
        for coordinates, at in departures:
            values[h3.latlng_to_cell(*coordinates, resolution)]['departures'].append(at)
        for coordinates, at in uncertain_origins:
            values[h3.latlng_to_cell(*coordinates, resolution)]['uncertain'].append(at)
        cells[str(resolution)] = dict(values)
    result = {'cells': cells, 'comparable': bool(exposures), 'uncertain_intervals': uncertain,
            'method': 'DIRECTED_GEOMETRIC_CORRIDOR', 'lateral_m': LATERAL_M,
            'confirmation_samples': CONFIRM_SAMPLES, 'confirmation_distance_m': CONFIRM_DISTANCE_M,
            'max_gap_s': MAX_GAP_S, 'max_jump_m': MAX_JUMP_M}
    if include_trace:
        result['states'] = states
    return result


def inspect_guided_trip(trip: GuidedTrip):
    """Offline inspection of caller-supplied evidence; never reads protected history."""
    analysis = analyze_guided_trip(trip, include_trace=True)
    intervals, totals = [], {'ON_ROUTE': [0.0, 0.0], 'OFF_ROUTE': [0.0, 0.0], 'UNKNOWN': [0.0, 0.0]}
    guidance_times = [version.effective_at for version in trip.guidance]
    disconnected = ((trip.observations[0].at - trip.started_at).total_seconds() > MAX_GAP_S or
                    (trip.completed_at - trip.observations[-1].at).total_seconds() > MAX_GAP_S)
    for index, (first, second) in enumerate(zip(trip.observations, trip.observations[1:])):
        seconds = (second.at - first.at).total_seconds()
        distance = _haversine_m(first.coordinates, second.coordinates)
        broken = seconds > MAX_GAP_S or distance > MAX_JUMP_M or distance / seconds > 55
        changed = bisect_right(guidance_times, first.at) != bisect_right(guidance_times, second.at)
        disconnected |= broken
        state = (analysis['states'][index] if not broken and not changed and
                 analysis['states'][index] == analysis['states'][index + 1] else 'UNKNOWN')
        totals[state][0] += 0 if broken or changed else distance
        totals[state][1] += seconds
        intervals.append({'state': state, 'from_iso': first.at.isoformat(), 'to_iso': second.at.isoformat(),
                          'distance_m': round(distance, 2) if not broken and not changed else None,
                          'seconds': seconds,
                          'coordinates': [] if broken or changed else [first.coordinates, second.coordinates]})
    for first_at, second_at in [(trip.started_at, trip.observations[0].at),
                                 (trip.observations[-1].at, trip.completed_at)]:
        seconds = (second_at - first_at).total_seconds()
        if seconds > 0:
            totals['UNKNOWN'][1] += seconds
            interval = {'state': 'UNKNOWN', 'from_iso': first_at.isoformat(), 'to_iso': second_at.isoformat(),
                        'distance_m': None, 'seconds': seconds, 'coordinates': []}
            if first_at == trip.started_at:
                intervals.insert(0, interval)
            else:
                intervals.append(interval)
    comparison = {'status': 'UNAVAILABLE_GPS_CONTINUITY', 'shared_pct_on_actual': None,
                  'shared_pct_on_proposed': None}
    if not disconnected:
        try:
            comparison = {'status': 'AVAILABLE', **asdict(match_and_compare_routes(
                trip.guidance[0].coordinates, [point.coordinates for point in trip.observations]))}
        except (ValueError, SimilarityWorkLimitExceeded):
            comparison = {'status': 'COMPARISON_WORK_LIMIT', 'shared_pct_on_actual': None,
                          'shared_pct_on_proposed': None}
        if comparison.get('actual_distance_m') == 0:
            comparison.update(status='NO_OBSERVED_MOVEMENT', shared_pct_on_actual=None,
                              shared_pct_on_proposed=None)
    summary = {'on_route_distance_m': round(totals['ON_ROUTE'][0], 2),
               'off_route_distance_m': round(totals['OFF_ROUTE'][0], 2),
               'unknown_distance_m': round(totals['UNKNOWN'][0], 2),
               'on_route_seconds': totals['ON_ROUTE'][1], 'off_route_seconds': totals['OFF_ROUTE'][1],
               'unknown_seconds': totals['UNKNOWN'][1],
               'departure_events': sum(len(cell['departures']) for cell in analysis['cells']['9'].values())}
    return {'summary': summary, 'intervals': intervals, 'whole_trip_comparison': comparison,
            'guidance_versions': [version.model_dump(mode='json') for version in trip.guidance],
            'departure_origin_cells': {cell: len(value['departures']) for cell, value in analysis['cells']['9'].items()
                                       if value['departures']},
            'limitations': 'Whole-trip percentages compare initial guidance; interval states use active guidance. '
                           'Geometric corridor assumptions, not calibrated field accuracy.'}
