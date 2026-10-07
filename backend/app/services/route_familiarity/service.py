"""Bounded, event-time route familiarity assessment for eligible routes."""
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter

from backend.app.config import settings
from backend.app.core.metrics import (
    observe_route_familiarity, record_familiarity_work_limit,
    record_route_familiarity_event,
)
from backend.app.services.route_familiarity.models import RouteSignature, SimilarityResult
from backend.app.services.route_familiarity.similarity import (
    ComparisonBudget,
    SimilarityWorkLimitExceeded,
    index_route_signature,
    weighted_ordered_overlap,
)


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
        evaluation_started = perf_counter()
        record_route_familiarity_event('evaluation')
        valid = {key: sig for key, sig in candidate_signatures.items() if sig is not None}
        unavailable = {key: FamiliarityAssessment("UNAVAILABLE", degraded_reason="ROUTE_GEOMETRY_UNAVAILABLE")
                       for key, sig in candidate_signatures.items() if sig is None}
        if not valid:
            for assessment in unavailable.values():
                record_route_familiarity_event('assessment', assessment.status.lower())
                record_route_familiarity_event('fallback', 'unavailable')
            observe_route_familiarity('evaluation', perf_counter() - evaluation_started)
            return unavailable
        lookup_started = perf_counter()
        personal = await self.repository.personal_routes(driver_id, as_of, self.lookback)
        community = await self.repository.community_routes(
            sorted({cell for sig in valid.values() for cell in sig.cells}),
            driver_id, as_of, self.lookback)
        observe_route_familiarity('lookup', perf_counter() - lookup_started)
        record_route_familiarity_event('lookup')
        personal_indexed = [self._index_row(row) for row in personal]
        community_indexed = [self._index_row(row) for row in community]
        result = unavailable.copy()
        truncated = len(personal) >= 50 or len(community) >= 500
        budget = ComparisonBudget()
        comparison_started = perf_counter()
        try:
            for key, recommended in valid.items():
                candidate_cells = set(recommended.cells)
                personal_results = [
                    weighted_ordered_overlap(recommended, signature, budget=budget,
                                             historical_positions=positions)
                    if candidate_cells.intersection(positions) else SimilarityResult(0.0, 0.0)
                    for signature, positions in personal_indexed
                ]
                best_result = max(personal_results, key=lambda score: score.adherence) if personal_results else None
                best = best_result.adherence if best_result else None
                supporting = sum(score.adherence >= self.minimum_support for score in personal_results)
                confidence = len(personal) / (len(personal) + self.confidence_prior) if personal else 0.0
                penalty = self.max_penalty_s * (1 - best) * confidence if best is not None else 0.0
                driver_best = {}
                driver_trips = {}
                for row, (signature, positions) in zip(community, community_indexed):
                    if not candidate_cells.intersection(positions):
                        continue
                    score = weighted_ordered_overlap(recommended, signature, budget=budget,
                                                     historical_positions=positions).adherence
                    driver = row["driver_id"]
                    if score >= self.minimum_support:
                        driver_best[driver] = max(score, driver_best.get(driver, 0.0))
                        driver_trips[driver] = driver_trips.get(driver, 0) + 1
                drivers = len(driver_best)
                visible = drivers >= self.minimum_drivers
                adherence = ((sum(driver_best.values()) + self.prior_mean * self.prior_strength) /
                             (drivers + self.prior_strength)) if visible else None
                result[key] = FamiliarityAssessment(
                    "AVAILABLE" if personal else "NO_HISTORY", best, supporting,
                    len(personal), adherence,
                    sum(driver_trips.values()) if visible else None, drivers if visible else None,
                    confidence, recommended.distance_m,
                    best_result.shared_route_distance_m if best_result else None,
                    min(self.max_penalty_s, max(0.0, penalty)), truncated)
        except SimilarityWorkLimitExceeded:
            record_familiarity_work_limit()
            record_route_familiarity_event('comparison', 'unavailable')
            record_route_familiarity_event('fallback', 'unavailable')
            observe_route_familiarity('comparison', perf_counter() - comparison_started)
            observe_route_familiarity('evaluation', perf_counter() - evaluation_started)
            return {key: FamiliarityAssessment("UNAVAILABLE", degraded_reason="SIMILARITY_WORK_LIMIT")
                    for key in candidate_signatures}
        observe_route_familiarity('comparison', perf_counter() - comparison_started)
        record_route_familiarity_event('comparison')
        for assessment in result.values():
            record_route_familiarity_event('assessment', assessment.status.lower())
            if assessment.status == 'NO_HISTORY':
                record_route_familiarity_event('no_history')
            if assessment.status == 'UNAVAILABLE':
                record_route_familiarity_event('fallback', 'unavailable')
        observe_route_familiarity('evaluation', perf_counter() - evaluation_started)
        return result

    @staticmethod
    def _index_row(row):
        signature = _signature(row)
        return signature, index_route_signature(signature)
