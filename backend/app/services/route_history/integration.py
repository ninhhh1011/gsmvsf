"""
Route History Integration with Recommendation Ranking
===============================================

Integrates historical familiarity into the ranking pipeline.

Hook point: After routing, before final ranking decision.

Design:
- HistoricalFamiliarityService: Queries route history for driver/context
- Adds familiarity_penalty_s to candidate features
- Feature flag: ENABLE_ROUTE_FAMILIARITY

IMPORTANT:
- Familiarity does NOT affect candidate eligibility
- Only affects ranking order (tie-breaking)
- Neutral when no history (fallback to existing behavior)
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import structlog

from .familiarity import (
    HistoricalFamiliarity,
    FamiliarityConfig,
    FamiliarityContext,
    FamiliarityPenalty,
    FamiliaritySource,
)

logger = structlog.get_logger()


class HistoryStatus(Enum):
    """Status of historical lookup for a request."""
    MATCHED = "MATCHED"  # Found relevant history
    NO_HISTORY = "NO_HISTORY"  # No history for this context
    DISABLED = "DISABLED"  # Feature flag off
    ERROR = "ERROR"  # Lookup error


@dataclass
class HistoricalEvidence:
    """Evidence from historical route analysis."""
    status: HistoryStatus
    driver_id: str
    route_adherence: float = 0.0  # 0-1
    family_support: float = 0.0  # 0-1
    family_id: Optional[str] = None
    dominant_family_trip_count: int = 0
    driver_trip_count: int = 0
    familiarity_penalty_s: float = 0.0  # Penalty in seconds
    history_window_days: int = 7

    @property
    def has_history(self) -> bool:
        return self.status == HistoryStatus.MATCHED


class RouteHistoryConfig:
    """Configuration for route history integration."""

    def __init__(
        self,
        enable_route_familiarity: bool = False,  # Default off for safety
        max_penalty_s: float = 30.0,  # Max 30 seconds penalty
        adherence_threshold: float = 0.5,
        history_window_days: int = 7,
        min_history_trips: int = 3,
        h3_resolution: int = 11,
    ):
        self.enable_route_familiarity = enable_route_familiarity
        self.max_penalty_s = max_penalty_s
        self.adherence_threshold = adherence_threshold
        self.history_window_days = history_window_days
        self.min_history_trips = min_history_trips
        self.h3_resolution = h3_resolution

        # Create familiarity config
        self.familiarity_config = FamiliarityConfig(
            enabled=True,  # Always enabled when feature is on
            max_penalty=max_penalty_s / 100.0 if max_penalty_s else 0.1,  # Convert to ratio
            adherence_threshold=adherence_threshold,
            min_history_trips=min_history_trips,
        )


class HistoricalFamiliarityService:
    """
    Service for historical familiarity in ranking.

    This service:
    1. Queries historical routes for driver/context
    2. Calculates familiarity penalty
    3. Returns evidence for ranking

    Does NOT:
    - Affect candidate eligibility
    - Override safety checks
    - Modify GraphHopper routing
    """

    def __init__(
        self,
        config: RouteHistoryConfig,
        historical_search_service=None,  # HistoricalRouteSearch
    ):
        self.config = config
        self.historical_search = historical_search_service
        self.familiarity = HistoricalFamiliarity(config.familiarity_config)

    def calculate_evidence(
        self,
        driver_id: str,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        timestamp: datetime,
        recommended_segment_ids: List[str],
        request_time: datetime,
    ) -> HistoricalEvidence:
        """
        Calculate historical familiarity evidence for a candidate.

        Args:
            driver_id: Driver making the request
            origin_lat, origin_lng: Origin coordinates
            dest_lat, dest_lng: Destination coordinates
            timestamp: When the trip started
            recommended_segment_ids: Ordered list of recommended segment IDs
            request_time: When the ranking request was made

        Returns:
            HistoricalEvidence with familiarity penalty
        """
        # Check feature flag
        if not self.config.enable_route_familiarity:
            return HistoricalEvidence(
                status=HistoryStatus.DISABLED,
                driver_id=driver_id,
            )

        try:
            # Query historical routes for this context
            history_result = self._query_history(
                driver_id=driver_id,
                origin=(origin_lat, origin_lng),
                destination=(dest_lat, dest_lng),
                timestamp=timestamp,
                request_time=request_time,
            )

            if history_result is None or not history_result.has_history:
                return HistoricalEvidence(
                    status=HistoryStatus.NO_HISTORY,
                    driver_id=driver_id,
                    history_window_days=self.config.history_window_days,
                )

            # Calculate familiarity penalty
            context = FamiliarityContext(
                driver_id=driver_id,
                route_adherence=history_result.avg_similarity,
                family_support=history_result.dominant_family.weighted_support
                    if history_result.dominant_family else 0.0,
                unique_driver_support=history_result.unique_driver_ratio,
                historical_trip_count=history_result.total_trips,
                has_history=True,
            )

            penalty = self.familiarity.calculate_penalty(context)

            # Convert penalty ratio to seconds
            # penalty.penalty is a ratio (0 to max_penalty which is ~0.3)
            # We scale by max_penalty_s to get seconds
            penalty_s = penalty.penalty * self.config.max_penalty_s

            return HistoricalEvidence(
                status=HistoryStatus.MATCHED,
                driver_id=driver_id,
                route_adherence=penalty.adherence,
                family_support=context.family_support,
                family_id=history_result.dominant_family.family_id
                    if history_result.dominant_family else None,
                dominant_family_trip_count=history_result.dominant_family.trip_count
                    if history_result.dominant_family else 0,
                driver_trip_count=history_result.total_trips,
                familiarity_penalty_s=penalty_s,
                history_window_days=self.config.history_window_days,
            )

        except Exception as e:
            logger.error("historical_familiarity_error", driver_id=driver_id, error=str(e))
            return HistoricalEvidence(
                status=HistoryStatus.ERROR,
                driver_id=driver_id,
            )

    def _query_history(
        self,
        driver_id: str,
        origin: tuple,
        destination: tuple,
        timestamp: datetime,
        request_time: datetime,
    ):
        """Query historical routes for this context."""
        if self.historical_search is None:
            return None

        # Delegate to historical search service
        # This would query the PostgreSQL inverted index
        # and return matching routes
        try:
            return self.historical_search.find_similar_routes(
                route_coords=[origin, destination],
                origin=origin,
                destination=destination,
                timestamp=request_time,
                max_candidates=20,
                driver_id=driver_id,
            )
        except Exception as e:
            logger.warning("history_query_error", error=str(e))
            return None

    def apply_penalty_to_features(
        self,
        features: List[Any],
        evidence: HistoricalEvidence,
    ) -> List[Any]:
        """
        Apply familiarity penalty to candidate features.

        This adds the familiarity_penalty_s to adjusted_travel_duration_s
        as a tie-breaker, not a primary ranking signal.

        IMPORTANT: This does NOT change candidate eligibility.
        """
        if not evidence.has_history:
            return features

        # Only apply if there's a non-zero penalty
        if evidence.familiarity_penalty_s <= 0:
            return features

        # Add penalty to features (feels like slightly longer travel time)
        for f in features:
            if hasattr(f, 'adjusted_travel_duration_s'):
                # Add small penalty to travel duration
                f.adjusted_travel_duration_s += evidence.familiarity_penalty_s

        return features

    def format_evidence_report(self, evidence: HistoricalEvidence) -> str:
        """Format evidence as human-readable report."""
        lines = [
            "Historical Familiarity Evidence",
            "=" * 40,
            f"Status: {evidence.status.value}",
            f"Driver: {evidence.driver_id}",
        ]

        if evidence.has_history:
            lines.extend([
                f"Route Adherence: {evidence.route_adherence:.1%}",
                f"Family: {evidence.family_id}",
                f"Family Trips: {evidence.dominant_family_trip_count}",
                f"Driver Trips: {evidence.driver_trip_count}",
                f"Penalty: {evidence.familiarity_penalty_s:.1f}s",
                f"History Window: {evidence.history_window_days} days",
            ])
        elif evidence.status == HistoryStatus.NO_HISTORY:
            lines.append("No historical routes for this context")
        elif evidence.status == HistoryStatus.DISABLED:
            lines.append("Route familiarity feature disabled")
        else:
            lines.append("Error in historical lookup")

        return "\n".join(lines)


# Default singleton instance (disabled by default)
default_config = RouteHistoryConfig(enable_route_familiarity=False)
default_service = HistoricalFamiliarityService(default_config)
