"""Deterministic completion-time ranking; no routing calls or hidden penalties."""
from math import inf
from time import perf_counter

from backend.app.core.logging import get_logger
from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.context import build_features, invalid_evidence
from backend.app.services.ranking.models import RankedCandidate, RankingPolicy, RecommendationResult
from backend.app.services.snapshots.models import aware_utc

logger = get_logger(__name__)


def rank_features(features) -> list[RankedCandidate]:
    def order(f):
        start = f.adjusted_travel_duration_s + f.effective_queue_wait_s
        return (round(start + f.service_duration_s, 3), round(start, 3),
                f.detour_duration_s if f.detour_duration_s is not None else inf,
                f.detour_distance_m if f.detour_distance_m is not None else inf,
                f.station_state.snapshot_age_s if f.station_state.snapshot_age_s is not None else inf,
                -f.available_capacity, f.station_id, f.service_type.value)

    ranked = []
    for rank, f in enumerate(sorted(features, key=order), 1):
        start = f.adjusted_travel_duration_s + f.effective_queue_wait_s
        complete = start + f.service_duration_s
        ranked.append(RankedCandidate(rank=rank, station_id=f.station_id, service_type=f.service_type,
            features=f, eta_to_station_s=f.adjusted_travel_duration_s, eta_to_service_start_s=start,
            eta_to_service_complete_s=complete, final_cost_s=complete))
    return ranked


class RankingService:
    def __init__(self, resolver, catalog=station_catalog, policy=None):
        self.resolver, self.catalog = resolver, catalog
        self.policy = policy or RankingPolicy()

    async def recommend(self, evidence, request_time=None, top_n=None) -> RecommendationResult:
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
        rank_started = perf_counter()
        ranked = rank_features(features)
        rank_ms = (perf_counter() - rank_started) * 1000
        best = ranked[0] if ranked else None
        degraded_reasons = sorted({f'{kind.upper()}_{getattr(f, kind + "_state").freshness}'
            for f in features for kind in ('station', 'queue', 'traffic')
            if getattr(f, kind + '_state').freshness != 'FRESH'})
        result = RecommendationResult(candidate_search_id=evidence.candidate_search_id,
            request_time=request_time, has_recommendation=best is not None,
            recommended_station_id=best.station_id if best else None,
            recommended_service_type=best.service_type if best else None,
            ranked_candidates=ranked[:top_n], eligible_count=len(ranked), policy=self.policy,
            energy_context=evidence.energy_request, degraded=bool(degraded_reasons),
            degraded_reasons=degraded_reasons,
            reason='RANKED_ELIGIBLE_CANDIDATES' if best else 'NO_ELIGIBLE_CANDIDATES')
        logger.info('recommendation', candidate_search_id=evidence.candidate_search_id,
            latency_ms=round((perf_counter() - started) * 1000, 3), ranking_ms=round(rank_ms, 3),
            eligible_count=len(ranked), returned_count=len(result.ranked_candidates),
            policy=self.policy.name, selected_station_id=result.recommended_station_id,
            selected_service_type=result.recommended_service_type, degraded=result.degraded)
        return result
