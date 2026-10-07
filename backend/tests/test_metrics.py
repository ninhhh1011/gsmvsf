"""Tests for metrics instrumentation."""
import pytest

from backend.app.core import metrics


class TestMetricsIncrement:
    """Test that metric functions increment counters."""

    def test_record_request_increments_counter(self):
        """record_request should increment RECOMMENDATION_REQUESTS counter."""
        # Get initial value
        initial = metrics.RECOMMENDATION_REQUESTS.labels(status='success', endpoint='recommend')._value.get()

        # Call record_request
        metrics.record_request(status='success', endpoint='recommend')

        # Verify increment
        after = metrics.RECOMMENDATION_REQUESTS.labels(status='success', endpoint='recommend')._value.get()
        assert after == initial + 1

    def test_record_candidate_conflict_increments_counter(self):
        """record_candidate_conflict should increment CANDIDATE_STATE_CONFLICTS counter."""
        initial = metrics.CANDIDATE_STATE_CONFLICTS._value.get()
        metrics.record_candidate_conflict()
        after = metrics.CANDIDATE_STATE_CONFLICTS._value.get()
        assert after == initial + 1

    def test_record_db_fallback_increments_counter(self):
        """record_db_fallback should increment DB_FALLBACKS counter."""
        initial = metrics.DB_FALLBACKS._value.get()
        metrics.record_db_fallback()
        after = metrics.DB_FALLBACKS._value.get()
        assert after == initial + 1

    def test_record_dependency_error_increments_counter(self):
        """record_dependency_error should increment DEPENDENCY_ERRORS counter."""
        initial = metrics.DEPENDENCY_ERRORS.labels(dependency='redis', error_type='timeout')._value.get()
        metrics.record_dependency_error(dependency='redis', error_type='timeout')
        after = metrics.DEPENDENCY_ERRORS.labels(dependency='redis', error_type='timeout')._value.get()
        assert after == initial + 1

    def test_observe_recommendation_records_latency(self):
        """observe_recommendation should record stage latency."""
        # Histogram doesn't have a simple value getter, but we can verify no exception
        metrics.observe_recommendation(stage='candidate_search', duration_seconds=0.05)
        metrics.observe_recommendation(stage='ranking', duration_seconds=0.1)

    def test_observe_route_call_increments_and_records_latency(self):
        """observe_route_call should increment counter and record latency."""
        initial = metrics.GRAPHHOPPER_ROUTE_CALLS.labels(status='success', leg='origin')._value.get()
        metrics.observe_route_call(leg='origin', status='success', duration_seconds=0.02)
        after = metrics.GRAPHHOPPER_ROUTE_CALLS.labels(status='success', leg='origin')._value.get()
        assert after == initial + 1

    def test_set_active_drivers_sets_gauge(self):
        """set_active_drivers should set ACTIVE_DRIVERS gauge."""
        metrics.set_active_drivers(42)
        assert metrics.ACTIVE_DRIVERS._value.get() == 42
        metrics.set_active_drivers(0)  # Reset

    def test_set_db_pool_available_sets_gauges(self):
        """set_db_pool_available should set DB pool gauges."""
        metrics.set_db_pool_available(available=5, total=10)
        assert metrics.DB_POOL_AVAILABLE._value.get() == 5
        assert metrics.DB_POOL_SIZE._value.get() == 10

    def test_set_redis_available_sets_gauge(self):
        """set_redis_available should set REDIS_AVAILABLE gauge."""
        metrics.set_redis_available(available=True)
        assert metrics.REDIS_AVAILABLE._value.get() == 1
        metrics.set_redis_available(available=False)
        assert metrics.REDIS_AVAILABLE._value.get() == 0

    def test_observe_request_latency_records_latency(self):
        """observe_request_latency should record request latency."""
        # Verify no exception
        metrics.observe_request_latency(endpoint='/api/v1/recommend', method='POST', duration_seconds=0.1)

    def test_metrics_endpoint_returns_prometheus_format(self):
        """metrics_endpoint should return Prometheus format response."""
        response = metrics.metrics_endpoint()
        assert 'text/plain' in response.media_type
        content = response.body.decode('utf-8')
        assert 'ev_' in content  # Metric names should start with ev_


class TestMetricsLabels:
    """Test metrics label combinations."""

    def test_record_request_with_different_endpoints(self):
        """record_request should handle different endpoint labels."""
        metrics.record_request(status='success', endpoint='recommend')
        metrics.record_request(status='error', endpoint='ranking')
        metrics.record_request(status='success', endpoint='candidate_search')

    def test_observe_route_call_with_different_legs(self):
        """observe_route_call should handle different leg labels."""
        metrics.observe_route_call(leg='origin', status='success', duration_seconds=0.01)
        metrics.observe_route_call(leg='destination', status='success', duration_seconds=0.01)
        metrics.observe_route_call(leg='return', status='error', duration_seconds=0.01)
