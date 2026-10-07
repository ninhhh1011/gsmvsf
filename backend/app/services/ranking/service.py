"""Deterministic completion-time ranking; no routing calls or hidden penalties."""
from math import inf
from time import perf_counter

from backend.app.core.logging import get_logger
from backend.app.core.metrics import record_route_familiarity_event
from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.context import build_features, invalid_evidence
from backend.app.services.ranking.models import (
    FamiliarityExplanation, RankedCandidate, RankingPolicy, RecommendationResult,
)
from backend.app.services.route_familiarity.service import FamiliarityAssessment
from backend.app.services.snapshots.models import aware_utc

# Lazy import to avoid circular dependency
logger = get_logger(__name__)


def _explanation(assessment, *, cells=()):
    if assessment is None:
        return FamiliarityExplanation(status='DISABLED')
    adherence = assessment.personal_adherence
    return FamiliarityExplanation(
        status=assessment.status, personal_adherence=adherence,
        personal_adherence_pct=round(adherence * 100, 2) if adherence is not None else None,
        personal_trip_count=assessment.personal_trip_count,
        personal_history_trip_count=assessment.personal_history_trip_count,
        community_adherence=assessment.community_adherence,
        community_trip_count=assessment.community_trip_count,
        community_driver_count=assessment.community_driver_count,
        confidence=assessment.confidence,
        recommended_distance_m=assessment.recommended_distance_m,
        shared_distance_m=assessment.shared_distance_m,
        penalty_s=assessment.penalty_s, history_truncated=assessment.history_truncated,
        route_cells=list(cells),
    )


def rank_features(features, assessments=None, *, include_familiarity=False) -> list[RankedCandidate]:
    assessments = assessments or {}
    def order(f):
        start = f.adjusted_travel_duration_s + f.effective_queue_wait_s
        assessment = assessments.get((f.station_id, f.service_type.value))
        penalty = assessment.penalty_s if assessment else 0.0
        return (round(start + f.service_duration_s + penalty, 3), round(start, 3),
                f.detour_duration_s if f.detour_duration_s is not None else inf,
                f.detour_distance_m if f.detour_distance_m is not None else inf,
                f.station_state.snapshot_age_s if f.station_state.snapshot_age_s is not None else inf,
                -f.available_capacity, f.station_id, f.service_type.value)

    ranked = []
    for rank, f in enumerate(sorted(features, key=order), 1):
        start = f.adjusted_travel_duration_s + f.effective_queue_wait_s
        complete = start + f.service_duration_s
        assessment = assessments.get((f.station_id, f.service_type.value))
        penalty = assessment.penalty_s if assessment else 0.0
        eta_to_dest = round(complete + f.duration_station_to_dest_s, 3) if f.duration_station_to_dest_s is not None else None
        ranked.append(RankedCandidate(
            rank=rank,
            station_id=f.station_id,
            service_type=f.service_type,
            features=f,
            eta_to_station_s=f.adjusted_travel_duration_s,
            eta_to_service_start_s=start,
            eta_to_service_complete_s=complete,
            final_cost_s=complete + penalty,
            eta_to_destination_via_station_s=eta_to_dest,
            penalty_components_s={"route_familiarity": penalty} if penalty else {},
            familiarity=(_explanation(assessment) if include_familiarity else None),
        ))
    return ranked


class RankingService:
    def __init__(self, resolver, catalog=station_catalog, policy=None, familiarity_evaluator=None):
        self.resolver, self.catalog = resolver, catalog
        self.policy = policy or RankingPolicy()
        self.familiarity_evaluator = familiarity_evaluator
        self.familiarity_enabled = familiarity_evaluator is not None

    async def recommend(self, evidence, request_time=None, top_n=None, candidate_signatures=None,
                        include_familiarity=False) -> RecommendationResult:
        started = perf_counter()
        request_time = aware_utc(request_time if request_time is not None else evidence.request_time)
        if request_time < evidence.request_time:
            raise invalid_evidence('Ranking time cannot precede candidate search time')
        if top_n is not None and (type(top_n) is not int or top_n < 1):
            raise invalid_evidence('top_n must be a positive integer')
        candidates = [c for c in evidence.result.candidates if c.eligible]
        keys = {f'{kind}:{c.station_id}' for c in candidates for kind in ('station', 'queue')}
        if candidates and evidence.energy_request.road_segment_id:
            keys.add(f'traffic:{evidence.energy_request.road_segment_id}')
        view = await self.resolver.resolve(keys, request_time) if keys else {}
        features = build_features(evidence, view, request_time, self.policy, self.catalog)

        assessments = {}
        familiarity_evaluated = self.familiarity_evaluator is not None and candidate_signatures is not None
        if familiarity_evaluated and candidates:
            try:
                assessments = await self.familiarity_evaluator.assess_many(
                    evidence.energy_request.driver_id, candidate_signatures or {}, evidence.request_time)
            except Exception:
                logger.warning('route_familiarity_unavailable')
                record_route_familiarity_event('fallback', 'unavailable')
                assessments = {(candidate.station_id, candidate.service_type.value):
                               FamiliarityAssessment('UNAVAILABLE', degraded_reason='HISTORY_LOOKUP_FAILED')
                               for candidate in candidates}

        rank_started = perf_counter()
        ranked = rank_features(features, assessments, include_familiarity=include_familiarity)
        rank_ms = (perf_counter() - rank_started) * 1000
        best = ranked[0] if ranked else None
        degraded_reasons = sorted({f'{kind.upper()}_{getattr(f, kind + "_state").freshness}'
            for f in features for kind in ('station', 'queue', 'traffic')
            if getattr(f, kind + "_state").freshness != 'FRESH'})
        selected_assessment = (assessments.get((best.station_id, best.service_type.value))
                               if best and familiarity_evaluated else None)
        selected_signature = ((candidate_signatures or {}).get((best.station_id, best.service_type.value))
                              if best and familiarity_evaluated else None)
        if familiarity_evaluated and any(a.status == 'UNAVAILABLE' for a in assessments.values()):
            degraded_reasons = sorted(set(degraded_reasons) | {'ROUTE_FAMILIARITY_UNAVAILABLE'})
        result = RecommendationResult(
            candidate_search_id=evidence.candidate_search_id,
            request_time=request_time, has_recommendation=best is not None,
            recommended_station_id=best.station_id if best else None,
            recommended_service_type=best.service_type if best else None,
            ranked_candidates=ranked[:top_n], eligible_count=len(ranked), policy=self.policy,
            familiarity_enabled=familiarity_evaluated,
            familiarity_status=(selected_assessment.status if selected_assessment else
                                'UNAVAILABLE' if familiarity_evaluated and best else
                                'DISABLED' if include_familiarity and not familiarity_evaluated else None),
            familiarity=(_explanation(selected_assessment,
                cells=selected_signature.cells if selected_signature is not None else ())
                if include_familiarity and best else None),
            route_adherence=selected_assessment.personal_adherence if selected_assessment else None,
            family_support=selected_assessment.community_adherence if selected_assessment else None,
            familiarity_penalty_s=selected_assessment.penalty_s if selected_assessment else 0.0,
            driver_trip_count=selected_assessment.personal_history_trip_count or 0 if selected_assessment else 0,
            history_window_days=getattr(getattr(self.familiarity_evaluator, 'lookback', None), 'days', 7),
            energy_context=evidence.energy_request, degraded=bool(degraded_reasons),
            degraded_reasons=degraded_reasons,
            reason='RANKED_ELIGIBLE_CANDIDATES' if best else 'NO_ELIGIBLE_CANDIDATES',
        )
        logger.info('recommendation', candidate_search_id=evidence.candidate_search_id,
            latency_ms=round((perf_counter() - started) * 1000, 3), ranking_ms=round(rank_ms, 3),
            eligible_count=len(ranked), returned_count=len(result.ranked_candidates),
            policy=self.policy.name, selected_station_id=result.recommended_station_id,
            selected_service_type=result.recommended_service_type, degraded=result.degraded)
        return result
