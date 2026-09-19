"""
Domain models and contracts for Week 3 Candidate Search.

Maintains strict separation from Week 4 Ranking:
- Candidate identity is (station_id, service_type).
- Evaluates operational status, compatibility, reachability, energy feasibility.
- Contains NO ranking score, NO rank position, and NO best-station recommendation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.demand.models import EnergyServiceRequest, ServiceType


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
    distance_to_station_m: Optional[float] = None
    duration_to_station_s: Optional[float] = None

    # Leg 2: Station -> Destination
    distance_station_to_dest_m: Optional[float] = None
    duration_station_to_dest_s: Optional[float] = None

    # Via Total: Leg 1 + Leg 2
    via_total_distance_m: Optional[float] = None
    via_total_duration_s: Optional[float] = None

    # Direct Route: Driver -> Destination
    direct_distance_m: Optional[float] = None
    direct_duration_s: Optional[float] = None

    # Detour Metrics: Via Total - Direct Route
    detour_distance_m: Optional[float] = None
    detour_duration_s: Optional[float] = None

    # Base ETA is route duration to station (seconds)
    eta_to_station_s: Optional[float] = None

    # Traffic adjustment (only when real traffic data is present, never fabricated)
    traffic_delay_factor: Optional[float] = None
    traffic_adjusted_duration_to_station_s: Optional[float] = None


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
    estimated_wait_min: Optional[float] = None
    service_time_min: float
    state_timestamp: Optional[str] = None


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
    access_node_id: Optional[str] = None

    # Network distance from driver to station (meters)
    network_distance_m: Optional[float] = None

    # Energy reachability proof (network routing distance + buffer <= remaining range)
    soc_feasible: bool

    # Capacity and queue metrics
    operational: StationOperationalSnapshot

    # Multi-leg route metrics (populated if reachable)
    route_metrics: Optional[CandidateRouteMetrics] = None


class CandidateSearchRequest(BaseModel):
    """
    Request contract for Candidate Search.
    Consumes the Week 2 EnergyServiceRequest and optional destination coordinates.
    """
    model_config = ConfigDict(extra="forbid")

    energy_request: EnergyServiceRequest
    destination_latitude: Optional[float] = None
    destination_longitude: Optional[float] = None
    destination_node_id: Optional[str] = None
    max_candidates: Optional[int] = None


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
    details: Optional[str] = None
