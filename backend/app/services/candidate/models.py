"""
Domain models and contracts for Week 3 Candidate Search.

Maintains strict separation from Week 4 Ranking:
- Candidate identity is (station_id, service_type).
- Evaluates operational status, compatibility, reachability, energy feasibility.
- Contains NO ranking score, NO rank position, and NO best-station recommendation.
"""

from datetime import datetime
from enum import Enum

from backend.app.services.demand.models import EnergyServiceRequest, ServiceType
from backend.app.services.routing.models import RouteConstraints
from pydantic import BaseModel, ConfigDict, Field


class CandidateEligibilityReason(str, Enum):
    """
    Explainable eligibility reason codes derived from canonical Dataset V1.3.1.
    """
    ELIGIBLE = "ELIGIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    OFFLINE = "OFFLINE"
    NO_SWAP_BATTERY = "NO_SWAP_BATTERY"
    FULL = "FULL"
    EXCESSIVE_QUEUE = "EXCESSIVE_QUEUE"
    UNREACHABLE = "UNREACHABLE"
    INSUFFICIENT_SOC_TO_REACH = "INSUFFICIENT_SOC_TO_REACH"


class StationServiceCandidate(BaseModel):
    """
    Minimal candidate representation preserving station_id + service_type identity.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str
    service_type: ServiceType
    eligible: bool
    reason: CandidateEligibilityReason


class CandidateRouteMetrics(BaseModel):
    """
    Complete routing metrics for an evaluated station candidate.
    Captures multi-leg metrics (driver -> station -> destination) and detour.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Leg 1: Driver -> Station
    distance_to_station_m: float | None = None
    duration_to_station_s: float | None = None

    # Leg 2: Station -> Destination
    distance_station_to_dest_m: float | None = None
    duration_station_to_dest_s: float | None = None

    # Via Total: Leg 1 + Leg 2
    via_total_distance_m: float | None = None
    via_total_duration_s: float | None = None

    # Direct Route: Driver -> Destination
    direct_distance_m: float | None = None
    direct_duration_s: float | None = None

    # Detour Metrics: Via Total - Direct Route
    detour_distance_m: float | None = None
    detour_duration_s: float | None = None

    # Base ETA is route duration to station (seconds)
    eta_to_station_s: float | None = None

    # Traffic adjustment (only when real traffic data is present, never fabricated)
    traffic_delay_factor: float | None = None
    traffic_adjusted_duration_to_station_s: float | None = None


class StationOperationalSnapshot(BaseModel):
    """
    Station operational and queue state at the moment of evaluation.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    operating_status: str
    available_service_slots: int
    available_swap_batteries: int
    available_capacity: int
    queue_length: int
    estimated_wait_min: float | None = None
    service_time_min: float
    state_timestamp: str | None = None


class EvaluatedCandidate(BaseModel):
    """
    Full candidate evaluation record prepared for Week 4 ranking handoff.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    station_id: str
    service_type: ServiceType
    eligible: bool
    reason: CandidateEligibilityReason

    # Geographic location of station
    station_latitude: float
    station_longitude: float
    access_node_id: str | None = None

    # Network distance from driver to station (meters)
    network_distance_m: float | None = None

    # Energy reachability proof (network routing distance + buffer <= remaining range)
    soc_feasible: bool

    # Capacity and queue metrics
    operational: StationOperationalSnapshot

    # Multi-leg route metrics (populated if reachable)
    route_metrics: CandidateRouteMetrics | None = None


class CandidateSearchRequest(BaseModel):
    """
    Request contract for Candidate Search.
    Consumes the Week 2 EnergyServiceRequest and optional destination coordinates.
    """
    model_config = ConfigDict(extra="forbid")

    energy_request: EnergyServiceRequest
    destination_latitude: float | None = None
    destination_longitude: float | None = None
    destination_node_id: str | None = None
    max_candidates: int | None = None
    constraints: RouteConstraints | None = None


class CandidateSearchResult(BaseModel):
    """
    Final output contract of Week 3 Candidate Search.
    """
    model_config = ConfigDict(extra="forbid")

    service_request_id: str
    search_timestamp: datetime = Field(default_factory=datetime.utcnow)
    search_status: str = "SUCCESS"  # SUCCESS, NO_SERVICE_NEEDED, INVALID_REQUEST, ERROR
    total_candidates_evaluated: int
    eligible_count: int
    candidates: list[EvaluatedCandidate]
    details: str | None = None
