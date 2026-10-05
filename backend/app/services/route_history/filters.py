"""
Hard Filters and Time/Recency Weighting
=======================================

Hard filters reduce the search space before expensive similarity calculations:
- Origin/Destination proximity
- Direction matching (same direction, not reverse)
- 7-day time window

Time and recency weighting:
- Time of day relevance (closer departure times are more relevant)
- Recency within the 7-day window
"""

from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import math


class Direction(Enum):
    """Route direction classification."""
    FORWARD = "forward"  # A → B as expected
    REVERSE = "reverse"  # B → A (opposite direction)
    OTHER = "other"      # Different origin/destination


@dataclass
class RouteMetadata:
    """Metadata for a historical route."""
    route_id: str
    trip_id: str
    driver_id: str
    timestamp: datetime
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    origin_h3: Optional[str] = None
    destination_h3: Optional[str] = None
    origin_node_id: Optional[str] = None
    destination_node_id: Optional[str] = None


@dataclass
class FilterResult:
    """Result of applying hard filters."""
    passed: bool
    reason: Optional[str] = None
    distance_km: Optional[float] = None


@dataclass
class WeightedScore:
    """Route relevance score with breakdown."""
    route_id: str
    time_weight: float  # 0-1, based on time of day proximity
    recency_weight: float  # 0-1, based on days since trip
    combined_weight: float  # time_weight * recency_weight
    days_ago: int
    hours_diff: float


# Distance threshold constants (in km)
ORIGIN_MATCH_THRESHOLD_KM = 2.0  # Origin must be within 2km
DEST_MATCH_THRESHOLD_KM = 2.0    # Destination must be within 2km


class HardFilters:
    """
    Hard filters for candidate route selection.

    These filters eliminate irrelevant routes before expensive similarity calculation:
    1. Origin proximity: Origin must be within threshold of query origin
    2. Destination proximity: Destination must be within threshold of query destination
    3. Direction: Route must go same direction (A→B not B→A)
    4. Time window: Route must be within 7 days
    """

    def __init__(
        self,
        origin_threshold_km: float = ORIGIN_MATCH_THRESHOLD_KM,
        dest_threshold_km: float = DEST_MATCH_THRESHOLD_KM,
        days_window: int = 7
    ):
        self.origin_threshold_km = origin_threshold_km
        self.dest_threshold_km = dest_threshold_km
        self.days_window = days_window

    def haversine_km(
        self,
        lat1: float, lng1: float,
        lat2: float, lng2: float
    ) -> float:
        """Calculate haversine distance in km."""
        R = 6371.0
        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)
        a = (math.sin(d_lat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(d_lng / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def filter_by_origin(
        self,
        query_lat: float,
        query_lng: float,
        candidate: RouteMetadata
    ) -> FilterResult:
        """Check if candidate origin is within threshold of query origin."""
        distance = self.haversine_km(
            query_lat, query_lng,
            candidate.origin_lat, candidate.origin_lng
        )

        if distance <= self.origin_threshold_km:
            return FilterResult(passed=True, distance_km=distance)
        else:
            return FilterResult(
                passed=False,
                reason=f"Origin too far: {distance:.1f}km > {self.origin_threshold_km}km",
                distance_km=distance
            )

    def filter_by_destination(
        self,
        query_lat: float,
        query_lng: float,
        candidate: RouteMetadata
    ) -> FilterResult:
        """Check if candidate destination is within threshold of query destination."""
        distance = self.haversine_km(
            query_lat, query_lng,
            candidate.destination_lat, candidate.destination_lng
        )

        if distance <= self.dest_threshold_km:
            return FilterResult(passed=True, distance_km=distance)
        else:
            return FilterResult(
                passed=False,
                reason=f"Destination too far: {distance:.1f}km > {self.dest_threshold_km}km",
                distance_km=distance
            )

    def filter_by_direction(
        self,
        query_origin_lat: float,
        query_origin_lng: float,
        query_dest_lat: float,
        query_dest_lng: float,
        candidate: RouteMetadata
    ) -> FilterResult:
        """
        Check if candidate goes in the same general direction as query.

        This prevents matching A→B routes with B→A routes.
        Uses bearing comparison to determine if directions are consistent.
        """
        # Calculate bearing for query route
        query_bearing = self._calculate_bearing(
            query_origin_lat, query_origin_lng,
            query_dest_lat, query_dest_lng
        )

        # Calculate bearing for candidate route
        candidate_bearing = self._calculate_bearing(
            candidate.origin_lat, candidate.origin_lng,
            candidate.destination_lat, candidate.destination_lng
        )

        # Check if bearings are within 90 degrees (same general direction)
        bearing_diff = abs(query_bearing - candidate_bearing)
        # Normalize to 0-180 range
        if bearing_diff > 180:
            bearing_diff = 360 - bearing_diff

        # Allow up to 90 degree difference for same direction
        if bearing_diff <= 90:
            return FilterResult(passed=True)
        else:
            return FilterResult(
                passed=False,
                reason=f"Wrong direction: {bearing_diff:.1f}° bearing difference"
            )

    def filter_by_time_window(
        self,
        query_timestamp: datetime,
        candidate: RouteMetadata
    ) -> FilterResult:
        """Check if candidate is within 7-day time window."""
        time_diff = abs((query_timestamp - candidate.timestamp).total_seconds())
        days_diff = time_diff / (24 * 3600)

        if days_diff <= self.days_window:
            return FilterResult(passed=True)
        else:
            return FilterResult(
                passed=False,
                reason=f"Outside time window: {days_diff:.1f} days > {self.days_window} days"
            )

    def _calculate_bearing(
        self,
        lat1: float, lng1: float,
        lat2: float, lng2: float
    ) -> float:
        """Calculate initial bearing from point 1 to point 2 in degrees."""
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        d_lng = math.radians(lng2 - lng1)

        x = math.sin(d_lng) * math.cos(lat2_rad)
        y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lng))

        bearing = math.atan2(x, y)
        return (math.degrees(bearing) + 360) % 360

    def apply_all_filters(
        self,
        query_origin_lat: float,
        query_origin_lng: float,
        query_dest_lat: float,
        query_dest_lng: float,
        query_timestamp: datetime,
        candidate: RouteMetadata
    ) -> Tuple[bool, List[str]]:
        """
        Apply all hard filters.

        Returns:
            Tuple of (passed, list_of_failure_reasons)
        """
        failures = []

        # Origin filter
        result = self.filter_by_origin(query_origin_lat, query_origin_lng, candidate)
        if not result.passed:
            failures.append(result.reason)

        # Destination filter
        result = self.filter_by_destination(query_dest_lat, query_dest_lng, candidate)
        if not result.passed:
            failures.append(result.reason)

        # Direction filter
        result = self.filter_by_direction(
            query_origin_lat, query_origin_lng,
            query_dest_lat, query_dest_lng,
            candidate
        )
        if not result.passed:
            failures.append(result.reason)

        # Time window filter
        result = self.filter_by_time_window(query_timestamp, candidate)
        if not result.passed:
            failures.append(result.reason)

        return len(failures) == 0, failures


class TimeRecencyWeight:
    """
    Calculate time and recency weights for route relevance.

    Uses exponential decay:
    - Time weight: closer departure times have higher weight
    - Recency weight: more recent days have higher weight

    Combined weight = time_weight * recency_weight
    """

    def __init__(
        self,
        time_decay_hours: float = 2.0,  # Half-life for time of day
        recency_decay_days: float = 2.0  # Half-life for recency
    ):
        self.time_decay_hours = time_decay_hours
        self.recency_decay_days = recency_decay_days

    def time_weight(self, query_timestamp: datetime, trip_timestamp: datetime) -> float:
        """
        Calculate weight based on time of day proximity.

        Trips at similar times of day are more relevant (e.g., morning commute).

        Returns:
            Float 0-1, where 1 = same hour, decaying with time difference
        """
        # Extract hour of day (ignore date)
        query_hour = query_timestamp.hour + query_timestamp.minute / 60
        trip_hour = trip_timestamp.hour + trip_timestamp.minute / 60

        # Circular distance in hours (24-hour clock)
        hour_diff = abs(query_hour - trip_hour)
        if hour_diff > 12:
            hour_diff = 24 - hour_diff

        # Exponential decay
        return math.exp(-0.693 * hour_diff / self.time_decay_hours)

    def recency_weight(self, query_timestamp: datetime, trip_timestamp: datetime) -> float:
        """
        Calculate weight based on recency (days since trip).

        More recent trips are more relevant for predicting current behavior.

        Returns:
            Float 0-1, where 1 = today, decaying with days difference
        """
        days_diff = abs((query_timestamp - trip_timestamp).days)
        return math.exp(-0.693 * days_diff / self.recency_decay_days)

    def combined_weight(
        self,
        query_timestamp: datetime,
        trip_timestamp: datetime
    ) -> WeightedScore:
        """
        Calculate combined time and recency weight.

        Returns:
            WeightedScore with breakdown
        """
        t_weight = self.time_weight(query_timestamp, trip_timestamp)
        r_weight = self.recency_weight(query_timestamp, trip_timestamp)

        days_ago = abs((query_timestamp - trip_timestamp).days)

        # Hour difference for reporting
        query_hour = query_timestamp.hour + query_timestamp.minute / 60
        trip_hour = trip_timestamp.hour + trip_timestamp.minute / 60
        hour_diff = abs(query_hour - trip_hour)
        if hour_diff > 12:
            hour_diff = 24 - hour_diff

        return WeightedScore(
            route_id="",  # Set by caller
            time_weight=t_weight,
            recency_weight=r_weight,
            combined_weight=t_weight * r_weight,
            days_ago=days_ago,
            hours_diff=hour_diff
        )

    def batch_weight(
        self,
        query_timestamp: datetime,
        candidates: List[RouteMetadata]
    ) -> List[WeightedScore]:
        """Calculate weights for multiple candidates."""
        scores = []
        for candidate in candidates:
            score = self.combined_weight(query_timestamp, candidate.timestamp)
            score.route_id = candidate.route_id
            scores.append(score)

        # Sort by combined weight descending
        scores.sort(key=lambda x: -x.combined_weight)
        return scores


def test_filters_and_weights():
    """Test hard filters and time/recency weighting."""
    filters = HardFilters(
        origin_threshold_km=2.0,
        dest_threshold_km=2.0,
        days_window=7
    )

    weight_calc = TimeRecencyWeight(
        time_decay_hours=2.0,
        recency_decay_days=2.0
    )

    # Create test query
    query_origin = (21.0285, 105.8542)  # Ba Đình
    query_dest = (21.0500, 105.7800)    # Cầu Giấy area
    query_time = datetime(2026, 9, 21, 8, 15)  # 8:15 AM

    # Create test candidates
    candidates = [
        RouteMetadata(
            route_id="R001",
            trip_id="T001",
            driver_id="D001",
            timestamp=datetime(2026, 9, 21, 8, 10),
            origin_lat=21.0280, origin_lng=105.8540,
            destination_lat=21.0495, destination_lng=105.7805,
        ),
        RouteMetadata(
            route_id="R002",
            trip_id="T002",
            driver_id="D001",
            timestamp=datetime(2026, 9, 20, 18, 30),  # Yesterday evening
            origin_lat=21.0270, origin_lng=105.8550,
            destination_lat=21.0480, destination_lng=105.7810,
        ),
        RouteMetadata(
            route_id="R003",
            trip_id="T003",
            driver_id="D002",
            timestamp=datetime(2026, 9, 15, 8, 0),  # 6 days ago
            origin_lat=21.0290, origin_lng=105.8545,
            destination_lat=21.0510, destination_lng=105.7795,
        ),
        RouteMetadata(
            route_id="R004",  # Wrong direction
            trip_id="T004",
            driver_id="D002",
            timestamp=datetime(2026, 9, 21, 8, 5),
            origin_lat=21.0500, origin_lng=105.7800,  # Swapped!
            destination_lat=21.0285, destination_lng=105.8542,
        ),
        RouteMetadata(
            route_id="R005",  # Too far
            trip_id="T005",
            driver_id="D003",
            timestamp=datetime(2026, 9, 21, 8, 0),
            origin_lat=21.1000, origin_lng=106.0000,  # Far away
            destination_lat=21.1200, destination_lng=106.0100,
        ),
    ]

    print("=== Hard Filter Results ===")
    for candidate in candidates:
        passed, reasons = filters.apply_all_filters(
            query_origin[0], query_origin[1],
            query_dest[0], query_dest[1],
            query_time,
            candidate
        )
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"\n{candidate.route_id}: {status}")
        if reasons:
            for reason in reasons:
                print(f"  - {reason}")

    print("\n=== Time/Recency Weights (for passing candidates) ===")
    passing_candidates = [c for c in candidates if c.route_id in ["R001", "R002", "R003"]]
    weighted = weight_calc.batch_weight(query_time, passing_candidates)

    for score in weighted:
        print(f"\n{score.route_id}:")
        print(f"  Time weight:   {score.time_weight:.3f} (hour diff: {score.hours_diff:.1f})")
        print(f"  Recency weight: {score.recency_weight:.3f} (days ago: {score.days_ago})")
        print(f"  Combined:      {score.combined_weight:.3f}")


if __name__ == "__main__":
    test_filters_and_weights()
