"""Bounded, event-time route familiarity assessment for eligible routes."""
from dataclasses import dataclass
from datetime import timedelta

from backend.app.config import settings
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.similarity import weighted_ordered_overlap


@dataclass(frozen=True)
class FamiliarityAssessment:
    status: str
    personal_adherence: float | None = None
    personal_trip_count: int | None = None
    personal_history_trip_count: int | None = None
    community_adherence: float | None = None
    community_trip_count: int | None = None
    community_driver_count: int | None = None
    confidence: float = 0.0
    recommended_distance_m: float | None = None
    shared_distance_m: float | None = None
    penalty_s: float = 0.0
    history_truncated: bool = False
    degraded_reason: str | None = None


def _signature(row) -> RouteSignature:
    return RouteSignature(tuple(row["cells"]), tuple(row["cell_distances_m"]),
                          float(row["distance_m"]), int(row["resolution"]))


class RouteFamiliarityService:
    def __init__(self, repository, *, lookback_days=None, max_penalty_s=None,
                 minimum_support_adherence=None, prior_mean=None, prior_strength=None,
                 minimum_community_drivers=None, confidence_prior_strength=None):
        self.repository = repository
        self.lookback = timedelta(days=lookback_days if lookback_days is not None else settings.route_familiarity_lookback_days)
        self.max_penalty_s = max_penalty_s if max_penalty_s is not None else settings.max_familiarity_penalty_s
        self.minimum_support = (minimum_support_adherence if minimum_support_adherence is not None
                                else settings.familiarity_minimum_support_adherence)
        self.prior_mean = prior_mean if prior_mean is not None else settings.familiarity_prior_mean
        self.prior_strength = prior_strength if prior_strength is not None else settings.familiarity_prior_strength
        self.minimum_drivers = (minimum_community_drivers if minimum_community_drivers is not None
                                else settings.familiarity_minimum_community_drivers)
        self.confidence_prior = (confidence_prior_strength if confidence_prior_strength is not None
                                 else settings.familiarity_confidence_prior_strength)

    async def assess_many(self, driver_id, candidate_signatures, as_of):
        if not candidate_signatures:
            return {}
        valid = {key: sig for key, sig in candidate_signatures.items() if sig is not None}
        unavailable = {key: FamiliarityAssessment("UNAVAILABLE", degraded_reason="ROUTE_GEOMETRY_UNAVAILABLE")
                       for key, sig in candidate_signatures.items() if sig is None}
        if not valid:
            return unavailable
        personal = await self.repository.personal_routes(driver_id, as_of, self.lookback)
        community = await self.repository.community_routes(
            sorted({cell for sig in valid.values() for cell in sig.cells}),
            driver_id, as_of, self.lookback)
        result = unavailable.copy()
        truncated = len(personal) >= 50 or len(community) >= 500
        for key, recommended in valid.items():
            personal_scores = [weighted_ordered_overlap(recommended, _signature(row)).adherence
                               for row in personal]
            best = max(personal_scores) if personal_scores else None
            supporting = sum(score >= self.minimum_support for score in personal_scores)
            confidence = len(personal) / (len(personal) + self.confidence_prior) if personal else 0.0
            penalty = self.max_penalty_s * (1 - best) * confidence if best is not None else 0.0
            driver_best = {}
            driver_trips = {}
            for row in community:
                score = weighted_ordered_overlap(recommended, _signature(row)).adherence
                driver = row["driver_id"]
                if score >= self.minimum_support:
                    driver_best[driver] = max(score, driver_best.get(driver, 0.0))
                    driver_trips[driver] = driver_trips.get(driver, 0) + 1
            drivers = len(driver_best)
            visible = drivers >= self.minimum_drivers
            adherence = ((sum(driver_best.values()) + self.prior_mean * self.prior_strength) /
                         (drivers + self.prior_strength)) if visible else None
            shared = (weighted_ordered_overlap(recommended, _signature(personal[personal_scores.index(best)]))
                      .shared_route_distance_m if personal else None)
            result[key] = FamiliarityAssessment(
                "AVAILABLE" if personal else "NO_HISTORY", best, supporting if personal else None,
                len(personal), adherence,
                sum(driver_trips.values()) if visible else None, drivers if visible else None,
                confidence, recommended.distance_m, shared, min(self.max_penalty_s, max(0.0, penalty)), truncated)
        return result
