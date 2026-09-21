"""Request workflow; only this layer may retry Candidate Search on a conflict."""
from time import perf_counter
from math import isfinite
from datetime import timezone

from backend.app.core.logging import get_logger
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.context import catalog_digest, operational_snapshot
from backend.app.services.ranking.models import CandidateSearchEvidence, CandidateStateChanged
from backend.app.services.ranking.service import RankingService
from backend.app.services.snapshots.models import StateError, aware_utc

logger = get_logger(__name__)


class SnapshotCatalogView:
    """Existing Week 3 search reads one pinned operational view per attempt."""
    def __init__(self, catalog, view):
        self.catalog, self.view = catalog, view

    def get_all_stations(self):
        return self.catalog.get_all_stations()

    def get_station(self, station_id):
        return self.catalog.get_station(station_id)

    def get_operational_snapshot(self, station_id, service_type, timestamp=None):
        return operational_snapshot(station_id, service_type, self.view)


class RecommendationWorkflow:
    def __init__(self, repository, resolver, routing_engine, catalog=station_catalog, policy=None):
        self.repository, self.resolver, self.routing_engine = repository, resolver, routing_engine
        self.catalog = catalog
        self.ranking = RankingService(resolver, catalog=catalog, policy=policy)

    async def search(self, request):
        request_time = aware_utc(request.energy_request.timestamp)
        energy = request.energy_request
        if (request.destination_latitude is None) != (request.destination_longitude is None):
            raise StateError('Both destination coordinates are required together', 'INVALID_CANDIDATE_REQUEST', 422)
        for field in ('current_soc_pct', 'remaining_energy_kwh', 'estimated_remaining_range_km',
                      'remaining_trip_distance_km', 'safety_reserve_km'):
            value = getattr(energy, field)
            if value is not None and (not isfinite(value) or value < 0 or
                                     (field == 'current_soc_pct' and value > 100)):
                raise StateError(f'Invalid {field}', 'INVALID_ENERGY_REQUEST', 422)
        if request.max_candidates is not None:
            raise StateError('Week 4 search requires the complete candidate set; use ranking top_n.',
                             'INVALID_CANDIDATE_REQUEST', 422)
        if (not energy.request_valid or energy.reason_code in
                ('MISSING_DATA', 'INVALID_STATE', 'STALE_STATE')):
            raise StateError('Energy service request is invalid', 'INVALID_ENERGY_REQUEST', 422)
        stations = self.catalog.get_all_stations()
        baseline_catalog_digest = catalog_digest(self.catalog)
        # No operational reads needed for the existing no-service short circuit.
        keys = [f'{kind}:{s.station_id}' for s in stations for kind in ('station', 'queue')]
        view = await self.resolver.resolve(keys, request_time) if request.energy_request.need_service else {}
        service = CandidateSearchService(self.routing_engine, SnapshotCatalogView(self.catalog, view))
        result = await service.search_candidates(request)
        # Week 3's internal clock is datetime.utcnow(); normalize at this boundary.
        if result.search_timestamp.tzinfo is None:
            result = result.model_copy(update={
                'search_timestamp': result.search_timestamp.replace(tzinfo=timezone.utc)})
        if result.search_status not in ('SUCCESS', 'NO_SERVICE_NEEDED'):
            raise StateError(result.details or result.search_status, 'CANDIDATE_SEARCH_FAILED', 422)
        evidence = CandidateSearchEvidence(request_time=request_time, energy_request=request.energy_request,
            result=result, snapshot_ids={key: value.snapshot_id for key, value in view.items()},
            catalog_digest=baseline_catalog_digest)
        await self.repository.save_search(evidence)
        return evidence

    async def recommend(self, request, top_n=None, metrics=None):
        started = perf_counter()
        if metrics is None:
            metrics = {}
        metrics.update(workflow_attempts=0, candidate_search_calls=0, ranking_calls=0,
                       candidate_state_conflicts=0, timings_ms={'candidate_search': 0.0, 'ranking': 0.0})
        for attempt in range(2):
            metrics['workflow_attempts'] = attempt + 1
            metrics['candidate_search_calls'] += 1
            stage_started = perf_counter()
            try:
                evidence = await self.search(request)
            finally:
                metrics['timings_ms']['candidate_search'] += (perf_counter() - stage_started) * 1000
            try:
                metrics['ranking_calls'] += 1
                stage_started = perf_counter()
                try:
                    result = await self.ranking.recommend(evidence, top_n=top_n)
                finally:
                    metrics['timings_ms']['ranking'] += (perf_counter() - stage_started) * 1000
                logger.info('recommendation_workflow', latency_ms=round((perf_counter()-started)*1000, 3),
                            attempts=attempt+1, candidate_count=evidence.result.total_candidates_evaluated,
                            eligible_count=result.eligible_count, policy=result.policy.name,
                            station_id=result.recommended_station_id,
                            service_type=result.recommended_service_type)
                return result
            except CandidateStateChanged:
                metrics['candidate_state_conflicts'] += 1
                if attempt == 1:
                    raise
                logger.info('candidate_search_retry', reason='CANDIDATE_STATE_CHANGED', attempt=1)
