"""
Candidate Search Orchestration Service for Week 3.

Implements the canonical Week 3 pipeline:
EnergyServiceRequest
        ↓
Validate request (short-circuit if invalid or no service needed)
        ↓
Expand allowed / unresolved service alternatives
        ↓
Load all station / service candidate pairs
        ↓
Routing & Reachability (driver -> station, station -> destination, direct)
        ↓
Energy feasibility to station
        ↓
Deterministic eligibility evaluation (Compatibility, Status, Capacity, Reachability, Energy)
        ↓
Assemble EvaluatedCandidate records with complete routing metrics
        ↓
CandidateSearchResult
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from backend.app.services.candidate.compatibility import check_station_service_compatibility
from backend.app.services.candidate.eligibility import evaluate_candidate_eligibility
from backend.app.services.candidate.energy_feasibility import check_energy_feasibility_to_station
from backend.app.services.candidate.expansion import expand_candidate_pairs
from backend.app.services.candidate.models import (
    CandidateSearchRequest,
    CandidateSearchResult,
    EvaluatedCandidate,
)
from backend.app.services.candidate.station_catalog import StationCatalog, station_catalog
from backend.app.services.demand.capability import (
    CANONICAL_MODEL_CATALOG,
    get_capability_resolver,
)
from backend.app.services.demand.models import EnergyServiceRequest, RequestSource
from backend.app.services.routing.engine import RoutingEngine
from backend.app.services.routing.models import Position, VehicleRoutingProfile
from backend.app.services.routing.multi_leg import MultiLegRouteCalculator
from backend.app.services.routing.osrm_routing_adapter import OSRMRoutingAdapter

logger = logging.getLogger(__name__)


class CandidateSearchService:
    """
    Coordinates candidate search and routing evaluation.
    """

    def __init__(
        self,
        routing_engine: Optional[RoutingEngine] = None,
        catalog: Optional[StationCatalog] = None,
    ):
        self.routing_engine = routing_engine or OSRMRoutingAdapter()
        self.catalog = catalog or station_catalog
        self.route_calculator = MultiLegRouteCalculator(self.routing_engine)

    async def search_candidates(
        self,
        request: CandidateSearchRequest,
        eligible_only: bool = False,
    ) -> CandidateSearchResult:
        """
        Execute full candidate search pipeline for an incoming CandidateSearchRequest.
        """
        esr: EnergyServiceRequest = request.energy_request
        req_id = esr.service_request_id

        # 1. Short-circuit: Invalid request
        if not esr.request_valid:
            logger.info("Short-circuiting invalid energy request %s (%s)", req_id, esr.reason_code)
            return CandidateSearchResult(
                service_request_id=req_id,
                search_status="INVALID_REQUEST",
                total_candidates_evaluated=0,
                eligible_count=0,
                candidates=[],
                details=f"Invalid energy request: {esr.reason_code.value}",
            )

        # 2. Short-circuit: AUTO_DETECTED with no service needed
        if esr.request_source == RequestSource.AUTO_DETECTED and not esr.need_service:
            logger.info("Short-circuiting AUTO_DETECTED request %s: no service needed", req_id)
            return CandidateSearchResult(
                service_request_id=req_id,
                search_status="NO_SERVICE_NEEDED",
                total_candidates_evaluated=0,
                eligible_count=0,
                candidates=[],
                details="No service needed: vehicle has sufficient SOC and range",
            )

        # 3. Establish origin position (Driver coordinates)
        if esr.latitude is None or esr.longitude is None:
            logger.warning("Missing driver coordinates in energy request %s", req_id)
            return CandidateSearchResult(
                service_request_id=req_id,
                search_status="ERROR",
                total_candidates_evaluated=0,
                eligible_count=0,
                candidates=[],
                details="Missing driver location coordinates in request",
            )
        driver_pos = Position(latitude=esr.latitude, longitude=esr.longitude, node_id=esr.road_segment_id)

        # 4. Establish destination position (if provided)
        dest_pos: Optional[Position] = None
        if request.destination_latitude is not None and request.destination_longitude is not None:
            dest_pos = Position(
                latitude=request.destination_latitude,
                longitude=request.destination_longitude,
                node_id=request.destination_node_id,
            )

        # 5. Resolve vehicle capability
        vehicle_cap = None
        resolver = get_capability_resolver()
        if esr.vehicle_model:
            try:
                vehicle_cap = resolver.resolve_by_model(esr.vehicle_model)
            except Exception:
                vehicle_cap = None
        elif esr.vehicle_id:
            try:
                vehicle_cap = resolver.resolve_by_vehicle_id(esr.vehicle_id)
            except Exception:
                vehicle_cap = None

        vehicle_profile = VehicleRoutingProfile(
            vehicle_id=esr.vehicle_id,
            vehicle_model=esr.vehicle_model,
            vehicle_category=esr.vehicle_type,
        )

        # 6. Load all stations and expand candidate pairs
        stations = self.catalog.get_all_stations()
        candidate_pairs = expand_candidate_pairs(esr, stations)

        # 7. Compute direct route once (driver -> destination) to avoid redundant route calls
        cached_direct = None
        if dest_pos is not None:
            cached_direct = await self.route_calculator.compute_direct_route(
                driver_pos=driver_pos,
                destination_pos=dest_pos,
                profile=vehicle_profile,
            )

        # 8. Evaluate all candidate pairs
        evaluated_candidates: list[EvaluatedCandidate] = []

        for station, service_type in candidate_pairs:
            station_pos = Position(
                latitude=station.latitude,
                longitude=station.longitude,
                node_id=station.access_node_id,
            )

            # Check service compatibility
            is_comp = check_station_service_compatibility(
                vehicle=vehicle_cap or esr,
                station=station,
                service_type=service_type,
            )

            # Fetch operational snapshot
            op_snapshot = self.catalog.get_operational_snapshot(
                station_id=station.station_id,
                service_type=service_type,
                timestamp=esr.timestamp,
            )

            # Route computation
            is_reach, route_metrics, leg1_res = await self.route_calculator.compute_station_metrics(
                driver_pos=driver_pos,
                station_pos=station_pos,
                destination_pos=dest_pos,
                cached_direct_route=cached_direct,
                profile=vehicle_profile,
            )

            net_dist_m = route_metrics.distance_to_station_m if (is_reach and route_metrics) else None

            # Energy feasibility to station
            soc_feasible = check_energy_feasibility_to_station(
                network_distance_m=net_dist_m,
                estimated_remaining_range_km=esr.estimated_remaining_range_km,
            )

            # Full eligibility determination
            eligible, reason = evaluate_candidate_eligibility(
                is_reachable=is_reach,
                is_compatible=is_comp,
                operational=op_snapshot,
                service_type=service_type,
                is_soc_feasible=soc_feasible,
            )

            candidate = EvaluatedCandidate(
                station_id=station.station_id,
                service_type=service_type,
                eligible=eligible,
                reason=reason,
                station_latitude=station.latitude,
                station_longitude=station.longitude,
                access_node_id=station.access_node_id,
                network_distance_m=net_dist_m,
                soc_feasible=soc_feasible,
                operational=op_snapshot,
                route_metrics=route_metrics,
            )
            evaluated_candidates.append(candidate)

        # Count eligible candidates
        eligible_count = sum(1 for c in evaluated_candidates if c.eligible)

        # Filter if eligible_only requested
        final_candidates = evaluated_candidates
        if eligible_only:
            final_candidates = [c for c in evaluated_candidates if c.eligible]

        # Optional deterministic top-N reduction (eligibility MUST happen first)
        if request.max_candidates is not None and request.max_candidates > 0:
            if eligible_only:
                final_candidates = final_candidates[: request.max_candidates]
            else:
                # Keep eligible first, then ineligibles up to max_candidates
                eligs = [c for c in final_candidates if c.eligible]
                ineligs = [c for c in final_candidates if not c.eligible]
                combined = eligs + ineligs
                final_candidates = combined[: request.max_candidates]

        return CandidateSearchResult(
            service_request_id=req_id,
            search_timestamp=datetime.utcnow(),
            search_status="SUCCESS",
            total_candidates_evaluated=len(evaluated_candidates),
            eligible_count=eligible_count,
            candidates=final_candidates,
            details=f"Evaluated {len(evaluated_candidates)} candidate alternatives; {eligible_count} eligible.",
        )
