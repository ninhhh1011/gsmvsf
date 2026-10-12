"""Bounded, event-time route familiarity assessment for eligible routes."""
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter

import h3
from starlette.concurrency import run_in_threadpool

from backend.app.config import settings
from backend.app.core.metrics import (
    ROUTE_FAMILIARITY_HISTORY_PAIRS, observe_route_familiarity, record_familiarity_work_limit,
    record_route_familiarity_event,
)
from backend.app.services.route_familiarity.models import SimilarityResult
from backend.app.services.route_familiarity.repository import coordinates_from_row
from backend.app.services.route_familiarity.route_matcher import prepare_route, compare_prepared_routes
from backend.app.services.route_familiarity.temporal import get_vietnam_time_window
from backend.app.services.route_familiarity.similarity import (
    ComparisonBudget,
    SimilarityWorkLimitExceeded,
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
    route_cells: tuple[str, ...] = ()
    community_confidence: float = 0.0
    community_cohort_driver_count: int | None = None


class RouteFamiliarityService:
    def __init__(self, repository, *, lookback_days=None, max_penalty_s=None,
                 minimum_support_adherence=None, prior_mean=None, prior_strength=None,
                 minimum_community_drivers=None, confidence_prior_strength=None):
        self.repository = repository
        self.lookback = timedelta(days=lookback_days if lookback_days is not None else settings.route_familiarity_lookback_days)
        self.max_penalty_s = max_penalty_s if max_penalty_s is not None else settings.max_familiarity_penalty_s
        if not 0 <= self.max_penalty_s <= 30:
            raise ValueError("max_penalty_s must be between 0 and 30")
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
        valid = {key: sig for key, sig in candidate_signatures.items() if sig is not None and sig.coordinates}
        unavailable = {key: FamiliarityAssessment("UNAVAILABLE", degraded_reason="ROUTE_GEOMETRY_UNAVAILABLE")
                       for key, sig in candidate_signatures.items() if sig is None or not sig.coordinates}
        if not valid:
            for assessment in unavailable.values():
                record_route_familiarity_event('assessment', assessment.status.lower())
                record_route_familiarity_event('fallback', 'unavailable')
            observe_route_familiarity('evaluation', perf_counter() - evaluation_started)
            return unavailable
        lookup_started = perf_counter()
        personal_rows = await self.repository.personal_routes(driver_id, as_of, self.lookback)
        community_rows = await self.repository.community_routes(
            history_query_cells(valid.values()),
            driver_id, as_of, self.lookback)
        personal_truncated = len(personal_rows) > 50
        community_truncated = (len(community_rows) > 500 or
                               any(row.get("active_rank", 1) > 100 or row.get("driver_rank", 1) > 5
                                   for row in community_rows))
        personal = personal_rows[:50]
        community = [row for row in community_rows
                      if row.get("active_rank", 1) <= 100 and row.get("driver_rank", 1) <= 5][:500]
        observe_route_familiarity('lookup', perf_counter() - lookup_started)
        record_route_familiarity_event('lookup')
        truncated = personal_truncated or community_truncated
        result = await run_in_threadpool(self._evaluate, valid, personal, community, as_of,
                                         truncated, unavailable)
        observe_route_familiarity('evaluation', perf_counter() - evaluation_started)
        return result

    def _evaluate(self, valid, personal, community, as_of, truncated, unavailable):
        result = unavailable.copy()
        budget = ComparisonBudget()
        comparison_started = perf_counter()
        target_window = get_vietnam_time_window(as_of)
        legacy_personal = any(not coordinates_from_row(row) or not row.get("started_at")
                              for row in personal)
        def usable(row):
            completed = row.get("completed_at")
            started = row.get("started_at")
            return (completed is not None and as_of - self.lookback <= completed < as_of
                    and started is not None and started <= completed
                    and get_vietnam_time_window(started) == target_window
                    and bool(coordinates_from_row(row)))
        personal = [row for row in personal if usable(row)]
        community = [row for row in community if usable(row)]
        try:
            point_count = sum(len(sig.coordinates) for sig in valid.values())
            point_count += sum(len(coordinates_from_row(row)) for row in personal + community)
            if point_count > 100_000:
                raise SimilarityWorkLimitExceeded
            route_cache, score_cache = {}, {}
            sample_budget = ComparisonBudget(max_pairs=50_000)
            def prepare(coordinates):
                if coordinates not in route_cache:
                    route_cache[coordinates] = prepare_route(coordinates, sample_budget=sample_budget)
                return route_cache[coordinates]
            personal_indexed = [prepare(coordinates_from_row(row)) for row in personal]
            community_indexed = [prepare(coordinates_from_row(row)) for row in community]
            prepared = {key: prepare(sig.coordinates) for key, sig in valid.items()}
            def score(recommended, historical):
                ROUTE_FAMILIARITY_HISTORY_PAIRS.inc()
                key = id(recommended), id(historical)
                if key not in score_cache:
                    metric = compare_prepared_routes(recommended, historical, budget=budget)
                    score_cache[key] = SimilarityResult(metric.shared_distance_m, metric.shared_pct_on_proposed / 100)
                return score_cache[key]
            for key, recommended in prepared.items():
                personal_results = [score(recommended, route) for route in personal_indexed]
                best = sum(item.adherence for item in personal_results) / len(personal_results) if personal_results else None
                supporting = sum(item.adherence >= self.minimum_support for item in personal_results)
                confidence = len(personal) / (len(personal) + self.confidence_prior) if personal else 0.0
                penalty = self.max_penalty_s * (1 - best) * confidence if best is not None else 0.0
                driver_best, driver_trips, driver_scores = {}, {}, {}
                for row, route in zip(community, community_indexed):
                    adherence = score(recommended, route).adherence
                    driver = row['driver_id']
                    driver_scores.setdefault(driver, []).append(adherence)
                    if adherence >= self.minimum_support:
                        driver_best[driver] = max(adherence, driver_best.get(driver, 0.0))
                        driver_trips[driver] = driver_trips.get(driver, 0) + 1
                drivers = len(driver_best)
                visible = drivers >= self.minimum_drivers
                community_adherence = ((sum(sum(scores) / len(scores) for scores in driver_scores.values()) + self.prior_mean * self.prior_strength) /
                                       (len(driver_scores) + self.prior_strength)) if visible else None
                legacy_only = not personal and legacy_personal
                result[key] = FamiliarityAssessment(
                    "UNAVAILABLE" if legacy_only else "AVAILABLE" if personal or visible else "NO_HISTORY",
                    best, supporting, len(personal), community_adherence,
                    sum(driver_trips.values()) if visible else None, drivers if visible else None,
                    confidence, recommended.distance_m,
                    sum(item.shared_route_distance_m for item in personal_results) / len(personal_results) if personal_results else None,
                    min(30.0, self.max_penalty_s, max(0.0, penalty)), truncated or legacy_personal,
                    "HISTORY_GEOMETRY_OR_START_UNAVAILABLE" if legacy_only else None,
                    tuple(sorted(recommended.positions)),
                    len(driver_scores) / (len(driver_scores) + self.confidence_prior) if visible else 0.0,
                    len(driver_scores) if visible else None)
        except SimilarityWorkLimitExceeded:
            record_familiarity_work_limit()
            record_route_familiarity_event('comparison', 'unavailable')
            record_route_familiarity_event('fallback', 'unavailable')
            observe_route_familiarity('comparison', perf_counter() - comparison_started)
            return {key: FamiliarityAssessment("UNAVAILABLE", degraded_reason="SIMILARITY_WORK_LIMIT")
                    for key in valid | unavailable}
        observe_route_familiarity('comparison', perf_counter() - comparison_started)
        record_route_familiarity_event('comparison')
        for assessment in result.values():
            record_route_familiarity_event('assessment', assessment.status.lower())
            if assessment.status == 'NO_HISTORY':
                record_route_familiarity_event('no_history')
            if assessment.status == 'UNAVAILABLE':
                record_route_familiarity_event('fallback', 'unavailable')
        return result


def history_query_cells(signatures):
    cells = set()
    for signature in signatures:
        for cell in signature.cells:
            if h3.is_valid_cell(cell):
                cells.update(h3.grid_disk(cell, 2))
            else:
                cells.add(cell)
            if len(cells) > 20_000:
                raise SimilarityWorkLimitExceeded
    return sorted(cells)
