"""Build ranking context from persisted evidence without reevaluating eligibility."""
from dataclasses import asdict
from hashlib import sha256
import json
from math import isfinite

from backend.app.services.candidate.eligibility import CANDIDATE_MAX_WAIT_MIN
from backend.app.services.candidate.models import StationOperationalSnapshot
from backend.app.services.demand.models import ServiceType
from backend.app.services.ranking.models import CandidateRankingFeatures, CandidateStateChanged
from backend.app.services.snapshots.models import (
    QueueSnapshot, ResolvedSnapshot, StateError, StationStateSnapshot, aware_utc,
)


def catalog_digest(catalog) -> str:
    records = sorted((asdict(s) for s in catalog.get_all_stations()), key=lambda s: s['station_id'])
    return sha256(json.dumps(records, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def operational_snapshot(station_id, service_type, view) -> StationOperationalSnapshot:
    station_state = view.get(f'station:{station_id}')
    queue_state = view.get(f'queue:{station_id}')
    station = station_state.snapshot if station_state else None
    queue = queue_state.snapshot if queue_state else None
    if not isinstance(station, StationStateSnapshot) or station.entity_id != station_id:
        raise StateError(f'Station state unavailable for {station_id}')
    if queue is not None and (not isinstance(queue, QueueSnapshot) or queue.entity_id != station_id):
        raise StateError(f'Queue state inconsistent for {station_id}')
    prefix = 'charging' if service_type == ServiceType.CHARGING else 'swap'
    slots = getattr(station, f'available_{prefix}_slots')
    batteries = station.available_swap_batteries if prefix == 'swap' else 0
    return StationOperationalSnapshot(
        operating_status=station.operating_status, available_service_slots=slots,
        available_swap_batteries=batteries,
        available_capacity=min(slots, batteries) if prefix == 'swap' else slots,
        queue_length=getattr(queue, f'{prefix}_queue_length') if queue else 0,
        estimated_wait_min=getattr(queue, f'{prefix}_estimated_wait_min') if queue else None,
        service_time_min=getattr(station, f'{prefix}_service_time_min'),
        state_timestamp=station.timestamp.isoformat())


def invalid_evidence(message):
    return StateError(message, 'INVALID_CANDIDATE_EVIDENCE', 422)


def build_features(evidence, view, request_time, policy, catalog) -> list[CandidateRankingFeatures]:
    request_time = aware_utc(request_time)
    if request_time < evidence.request_time:
        raise invalid_evidence('Ranking time cannot precede candidate search time')
    candidates = [c for c in evidence.result.candidates if c.eligible]
    identities = [(c.station_id, c.service_type) for c in candidates]
    if len(set(identities)) != len(identities):
        raise invalid_evidence('Duplicate eligible station/service identity')
    for candidate in candidates:
        metrics = candidate.route_metrics
        if candidate.reason != 'ELIGIBLE' or metrics is None:
            raise invalid_evidence('Eligible candidate must have ELIGIBLE reason and route evidence')
        if metrics.distance_to_station_m is None or metrics.duration_to_station_s is None:
            raise invalid_evidence('Eligible candidate is missing station route metrics')
        if any(value is not None and (not isfinite(value) or value < 0)
               for value in metrics.model_dump().values()):
            raise invalid_evidence('Candidate route metrics must be finite and nonnegative')

    def changed(candidate, reason):
        return dict(station_id=candidate.station_id, service_type=candidate.service_type,
                    previous_state='ELIGIBLE', current_state=reason)

    if catalog_digest(catalog) != evidence.catalog_digest:
        raise CandidateStateChanged(evidence.candidate_search_id,
                                    [changed(c, 'CATALOG_CHANGED') for c in candidates])
    # This is only an invalidation guard on changed persisted versions. Week 3
    # retains ownership of compatibility, reachability and eligibility decisions.
    conflicts, operational = [], {}
    for candidate in candidates:
        sid, service = candidate.station_id, candidate.service_type
        op = operational_snapshot(sid, service, view)
        operational[(sid, service)] = op
        station_key, queue_key = f'station:{sid}', f'queue:{sid}'
        station_changed = view[station_key].snapshot_id != evidence.snapshot_ids.get(station_key)
        queue_state = view.get(queue_key)
        queue_changed = (queue_state.snapshot_id if queue_state else None) != evidence.snapshot_ids.get(queue_key)
        reason = None
        if station_changed:
            if op.operating_status == 'OFFLINE':
                reason = 'OFFLINE'
            elif service == ServiceType.BATTERY_SWAP and op.available_service_slots > 0 and op.available_swap_batteries == 0:
                reason = 'NO_SWAP_BATTERY'
            elif op.available_capacity == 0:
                reason = 'FULL'
        if reason is None and queue_changed and op.estimated_wait_min is not None and op.estimated_wait_min > CANDIDATE_MAX_WAIT_MIN:
            reason = 'EXCESSIVE_QUEUE'
        if reason:
            conflicts.append(changed(candidate, reason))
    if conflicts:
        raise CandidateStateChanged(evidence.candidate_search_id,
                                    sorted(conflicts, key=lambda c: (c['station_id'], c['service_type'].value)))

    missing = ResolvedSnapshot.resolve(None, request_time, 0)
    segment = evidence.energy_request.road_segment_id
    traffic = view.get(f'traffic:{segment}', missing) if segment else missing
    features = []
    for candidate in candidates:
        sid, service = candidate.station_id, candidate.service_type
        op, metrics = operational[(sid, service)], candidate.route_metrics
        base = metrics.duration_to_station_s
        adjusted = base * traffic.snapshot.delay_factor if traffic.snapshot else base
        observed_wait = op.estimated_wait_min * 60 if op.estimated_wait_min is not None else None
        features.append(CandidateRankingFeatures(
            station_id=sid, service_type=service, base_travel_duration_s=base,
            adjusted_travel_duration_s=adjusted, traffic_adjustment_s=adjusted-base,
            traffic_method='ORIGIN_SEGMENT_PROXY' if traffic.snapshot else 'BASE_DURATION_MISSING',
            observed_queue_wait_s=observed_wait,
            effective_queue_wait_s=observed_wait if observed_wait is not None else policy.missing_queue_wait_s,
            queue_assumption='PROJECT_POLICY_MISSING_QUEUE' if observed_wait is None else None,
            service_duration_s=op.service_time_min * 60,
            detour_duration_s=metrics.detour_duration_s, detour_distance_m=metrics.detour_distance_m,
            distance_to_station_m=metrics.distance_to_station_m, available_capacity=op.available_capacity,
            station_state=view[f'station:{sid}'], queue_state=view.get(f'queue:{sid}', missing),
            traffic_state=traffic))
    return features
