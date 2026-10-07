"""Prometheus metrics for Week 6 productionization."""
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Counters
RECOMMENDATION_REQUESTS = Counter(
    'ev_recommendation_requests_total',
    'Total recommendation requests',
    ['status', 'endpoint']
)


GRAPHHOPPER_ROUTE_CALLS = Counter(
    'ev_graphhopper_route_calls_total',
    'Total GraphHopper route calls',
    ['status', 'leg']
)


CANDIDATE_STATE_CONFLICTS = Counter(
    'ev_candidate_state_conflicts_total',
    'Total candidate state conflicts requiring retry'
)

ROUTE_FAMILIARITY_WORK_LIMITS = Counter(
    'ev_route_familiarity_work_limits_total',
    'Route familiarity evaluations rejected by the matching-pair budget'
)


DB_FALLBACKS = Counter(
    'ev_db_fallback_total',
    'Times database was used instead of Redis cache'
)


DEPENDENCY_ERRORS = Counter(
    'ev_dependency_errors_total',
    'Dependency failures by type',
    ['dependency', 'error_type']
)


# Histograms
REQUEST_LATENCY = Histogram(
    'ev_request_latency_seconds',
    'Request latency by endpoint and method',
    ['endpoint', 'method'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)


RECOMMENDATION_LATENCY = Histogram(
    'ev_recommendation_latency_seconds',
    'Recommendation request latency by stage',
    ['stage'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


GRAPHHOPPER_ROUTE_LATENCY = Histogram(
    'ev_graphhopper_route_latency_seconds',
    'GraphHopper route call latency',
    ['leg'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)


CANDIDATE_SEARCH_LATENCY = Histogram(
    'ev_candidate_search_latency_seconds',
    'Candidate search latency',
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


# Gauges
ACTIVE_DRIVERS = Gauge(
    'ev_active_drivers',
    'Number of active driver sessions'
)


CACHE_HIT_RATE = Gauge(
    'ev_cache_hit_rate',
    'Snapshot cache hit rate (last 100 lookups)'
)


DB_POOL_AVAILABLE = Gauge(
    'ev_db_pool_available',
    'Database connection pool available connections'
)


DB_POOL_SIZE = Gauge(
    'ev_db_pool_size',
    'Database connection pool total size'
)


REDIS_AVAILABLE = Gauge(
    'ev_redis_available',
    'Redis availability (1=available, 0=unavailable)'
)


def metrics_endpoint():
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


def observe_request_latency(endpoint: str, method: str, duration_seconds: float):
    """Record overall request latency."""
    REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(duration_seconds)


def observe_recommendation(stage: str, duration_seconds: float):
    """Record recommendation stage latency."""
    RECOMMENDATION_LATENCY.labels(stage=stage).observe(duration_seconds)


def observe_candidate_search(duration_seconds: float):
    """Record candidate search latency."""
    CANDIDATE_SEARCH_LATENCY.observe(duration_seconds)


def observe_route_call(leg: str, status: str, duration_seconds: float):
    """Record GraphHopper route call metrics."""
    GRAPHHOPPER_ROUTE_CALLS.labels(status=status, leg=leg).inc()
    GRAPHHOPPER_ROUTE_LATENCY.labels(leg=leg).observe(duration_seconds)


def record_request(status: str, endpoint: str = 'recommend'):
    """Record a recommendation request."""
    RECOMMENDATION_REQUESTS.labels(status=status, endpoint=endpoint).inc()


def record_candidate_conflict():
    """Record a candidate state conflict."""
    CANDIDATE_STATE_CONFLICTS.inc()


def record_familiarity_work_limit():
    ROUTE_FAMILIARITY_WORK_LIMITS.inc()


def record_db_fallback():
    """Record a database fallback."""
    DB_FALLBACKS.inc()


def record_dependency_error(dependency: str, error_type: str):
    """Record a dependency error."""
    DEPENDENCY_ERRORS.labels(dependency=dependency, error_type=error_type).inc()


def set_active_drivers(count: int):
    """Set the active driver count."""
    ACTIVE_DRIVERS.set(count)


def set_db_pool_available(available: int, total: int):
    """Set database pool availability metrics."""
    DB_POOL_AVAILABLE.set(available)
    DB_POOL_SIZE.set(total)


def set_redis_available(available: bool):
    """Set Redis availability metric."""
    REDIS_AVAILABLE.set(1 if available else 0)
