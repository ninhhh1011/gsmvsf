"""
Centralized application constants.

All magic numbers are defined here with descriptive names.
This file is the single source of truth for numeric constants.
"""

# =============================================================================
# GEOGRAPHIC CONSTANTS
# =============================================================================

# Earth radius in meters (WGS84 ellipsoid approximation)
EARTH_RADIUS_M = 6371000


# =============================================================================
# GPS / TRACKING CONSTANTS
# =============================================================================

# Maximum GPS observations to retain per driver
MAX_OBSERVATIONS_PER_DRIVER = 1000

# Maximum deduplication entries before cleanup
MAX_DEDUP_ENTRIES = 10000

# Maximum concurrent driver states in memory
MAX_ACTIVE_DRIVERS = 10000

# Default context window for map matching (seconds)
DEFAULT_CONTEXT_WINDOW_SECONDS = 30.0

# Maximum GPS points to include in context
DEFAULT_MAX_CONTEXT_POINTS = 50

# Gap threshold before resetting driver state (seconds)
DEFAULT_GAP_THRESHOLD_SECONDS = 60.0

# Consecutive observations required to be considered stationary
DEFAULT_STATIONARY_THRESHOLD = 3

# Movement below this distance (meters) = stationary
DEFAULT_STATIONARY_DISTANCE_M = 5.0


# =============================================================================
# REDIS / CACHE CONSTANTS
# =============================================================================

# Driver state TTL in seconds (1 hour)
DRIVER_STATE_TTL_SECONDS = 3600


# =============================================================================
# RATE LIMITING CONSTANTS
# =============================================================================

# Requests per minute per client
REQUESTS_PER_MINUTE = 100


# =============================================================================
# HTTP STATUS CODE CONSTANTS (for reference)
# =============================================================================

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_GATEWAY_TIMEOUT = 504
