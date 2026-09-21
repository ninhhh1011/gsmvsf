from scripts.verify_graphhopper import dataset_cases


def test_verification_statistics_and_source_request():
    from scripts.verify_week4 import summary, recommend_request
    stats = summary([1, 2, 3, 4, 5], [0, 1, 2, 3, 4])
    assert stats['samples'] == 5
    assert stats['median_ms'] == 3 and stats['p90_ms'] == 4.6
    assert stats['p95_ms'] == 4.8 and stats['max_ms'] == 5
    assert stats['eligible_counts'] == [0, 1, 2, 3, 4]
    group, request = dataset_cases()[0]
    payload = recommend_request(group, request)
    assert payload['context']['vehicle_id'] == request.energy_request.vehicle_id
    assert payload['context']['estimated_remaining_range_km'] == request.energy_request.estimated_remaining_range_km
    assert payload['destination_node_id'] == request.destination_node_id
    assert payload['requested_service'] == 'CHARGING'


def test_traffic_probe_uses_canonical_identity_and_consistent_speeds():
    from datetime import datetime, timezone
    from scripts.verify_graphhopper import rows
    from scripts.verify_week4 import traffic_probe
    source = next(rows('traffic/traffic_snapshots.csv.gz'))
    timestamp = datetime(2026, 9, 3, tzinfo=timezone.utc)
    snapshot = traffic_probe(timestamp, 'verification-test')
    assert snapshot.entity_id == source['segment_id']
    assert snapshot.timestamp == timestamp
    assert snapshot.delay_factor == snapshot.free_flow_speed_kmh / snapshot.current_speed_kmh == 2


def test_dependency_probe_accepts_explicit_unavailable_and_timeout():
    import pytest
    from backend.app.services.routing.models import RouteResult, RouteStatus
    from scripts.verify_week4 import routing_failure_evidence
    for status, expected_status, exception in [
        (RouteStatus.ENGINE_ERROR, 503, 'RoutingEngineUnavailableError'),
        (RouteStatus.TIMEOUT, 504, 'RoutingTimeoutError'),
    ]:
        result = RouteResult(status=status, distance_m=float('inf'), duration_s=float('inf'),
                             engine_name='graphhopper', error_message='Dependency probe')
        assert routing_failure_evidence(result) == {
            'route_status': status.value, 'exception': exception, 'http_status': expected_status}
    with pytest.raises(AssertionError):
        routing_failure_evidence(RouteResult(status=RouteStatus.SUCCESS, distance_m=1,
                                            duration_s=1, engine_name='graphhopper'))
