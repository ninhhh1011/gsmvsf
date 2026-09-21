"""Ranking contracts preserve Week 2/3 models and expose costs in seconds."""
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import Field, field_validator

from backend.app.services.candidate.models import CandidateSearchResult
from backend.app.services.demand.models import EnergyServiceRequest, ServiceType
from backend.app.services.snapshots.models import (
    Count, FrozenModel, Nonnegative, ResolvedSnapshot, StateError, aware_utc,
)


class RankingPolicy(FrozenModel):
    name: str = 'TOTAL_SERVICE_COMPLETION_V1'
    missing_queue_wait_s: Nonnegative = 5400.0
    station_fresh_s: Nonnegative = 600.0
    queue_fresh_s: Nonnegative = 600.0
    traffic_fresh_s: Nonnegative = 1800.0


class CandidateSearchEvidence(FrozenModel):
    candidate_search_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_time: datetime
    energy_request: EnergyServiceRequest
    result: CandidateSearchResult
    snapshot_ids: dict[str, str | None]
    catalog_digest: str

    _time = field_validator('request_time', 'created_at')(aware_utc)


class CandidateRankingFeatures(FrozenModel):
    station_id: str
    service_type: ServiceType
    base_travel_duration_s: Nonnegative
    adjusted_travel_duration_s: Nonnegative
    traffic_adjustment_s: float
    traffic_method: str
    observed_queue_wait_s: Nonnegative | None
    effective_queue_wait_s: Nonnegative
    queue_assumption: str | None = None
    service_duration_s: Nonnegative
    detour_duration_s: Nonnegative | None
    detour_distance_m: Nonnegative | None
    distance_to_station_m: Nonnegative
    available_capacity: int = Field(ge=0)
    station_state: ResolvedSnapshot
    queue_state: ResolvedSnapshot
    traffic_state: ResolvedSnapshot


class RankedCandidate(FrozenModel):
    rank: int = Field(ge=1)
    station_id: str
    service_type: ServiceType
    features: CandidateRankingFeatures
    eta_to_station_s: Nonnegative
    eta_to_service_start_s: Nonnegative
    eta_to_service_complete_s: Nonnegative
    final_cost_s: Nonnegative
    penalty_components_s: dict[str, float] = Field(default_factory=dict)


class RecommendationResult(FrozenModel):
    candidate_search_id: str
    request_time: datetime
    has_recommendation: bool
    recommended_station_id: str | None
    recommended_service_type: ServiceType | None
    ranked_candidates: list[RankedCandidate]
    eligible_count: Count
    policy: RankingPolicy
    energy_context: EnergyServiceRequest
    degraded: bool
    degraded_reasons: list[str]
    reason: str

    _time = field_validator('request_time')(aware_utc)


class ChangedCandidate(FrozenModel):
    station_id: str
    service_type: ServiceType
    previous_state: str
    current_state: str


class CandidateStateChanged(StateError):
    def __init__(self, candidate_search_id: str, changed_candidates: list[dict]):
        super().__init__('Candidate eligibility state changed after candidate search.',
                         'CANDIDATE_STATE_CHANGED', 409)
        self.detail.update(candidate_search_id=candidate_search_id,
                           changed_candidates=[ChangedCandidate.model_validate(c).model_dump(mode='json')
                                               for c in changed_candidates],
                           action='RERUN_CANDIDATE_SEARCH')
