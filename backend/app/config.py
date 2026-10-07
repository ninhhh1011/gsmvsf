"""Application configuration management."""
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "EV Recommendation API"
    app_version: str = "0.1.0"
    debug: bool = False

    # City & Geographic Configuration (Default Hanoi, configurable for HCMC, Da Nang, etc.)
    city_name: str = "Hanoi"
    map_default_center_lat: float = 21.0285
    map_default_center_lng: float = 105.8542
    map_default_zoom: int = 13
    map_bbox_min_lat: float = 20.8000
    map_bbox_min_lng: float = 105.6000
    map_bbox_max_lat: float = 21.2500
    map_bbox_max_lng: float = 106.1000

    # Paths
    app_path: Path = Path(__file__).parent
    dataset_path: Path = Path("dataset_v1")
    primary_pbf_path: Path = Path("dataset_v1/map/raw/hanoi-patched.osm.pbf")

    # GraphHopper
    graphhopper_base_url: str = "http://127.0.0.1:8989"
    graphhopper_data_path: Path = Path("runtime/graphhopper")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@ev_db:5432/ev_recommendation"
    database_url_sync: str = "postgresql://postgres:postgres@ev_db:5432/ev_recommendation"

    # Week 4 project policy; freshness follows Dataset cadence, TTL is cache retention.
    redis_url: str = "redis://127.0.0.1:6379/0"
    snapshot_cache_prefix: str = Field(default="week4:snapshot:", min_length=1)
    snapshot_cache_ttl_s: int = Field(default=60, ge=1)
    snapshot_cache_timeout_s: float = Field(default=0.2, gt=0, allow_inf_nan=False)
    snapshot_db_timeout_s: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    station_fresh_s: float = Field(default=600, ge=0, allow_inf_nan=False)
    queue_fresh_s: float = Field(default=600, ge=0, allow_inf_nan=False)
    traffic_fresh_s: float = Field(default=1800, ge=0, allow_inf_nan=False)
    missing_queue_wait_s: float = Field(default=5400, ge=0, allow_inf_nan=False)
    snapshot_ingestion_token: str = ""

    enable_route_familiarity: bool = False
    route_familiarity_identity_secret: str = ""
    route_familiarity_lookback_days: int = Field(default=7, ge=1, le=365)
    max_familiarity_penalty_s: float = Field(default=30.0, ge=0, allow_inf_nan=False)
    familiarity_minimum_support_adherence: float = Field(default=0.10, ge=0, le=1)
    familiarity_prior_mean: float = Field(default=0.5, ge=0, le=1)
    familiarity_prior_strength: float = Field(default=3.0, ge=0, allow_inf_nan=False)
    familiarity_minimum_community_drivers: int = Field(default=5, ge=1, le=100)
    familiarity_confidence_prior_strength: float = Field(default=3.0, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_route_familiarity(self):
        if self.enable_route_familiarity and len(self.route_familiarity_identity_secret.encode()) < 32:
            raise ValueError("ROUTE_FAMILIARITY_IDENTITY_SECRET must be at least 32 bytes when enabled")
        return self

    # Mapping
    mapping_dir: Path = Path("runtime/map_mapping")

    # Logging
    log_level: str = "INFO"

    # Week 6 productionization: routing concurrency
    max_concurrent_routes: int = Field(
        default=8, ge=1, le=32,
        description="Maximum concurrent GraphHopper route calls per candidate search",
    )

    # Realtime operational state simulator (Problem D)
    enable_realtime_simulator: bool = Field(
        default=False,
        description="Enable periodic background simulation of station & traffic state",
    )
    realtime_simulator_interval_s: float = Field(
        default=30.0, ge=1.0,
        description="Interval in seconds between simulation ticks",
    )

    def validate_paths(self) -> list[str]:
        """Validate critical paths exist. Returns list of errors."""
        errors = []
        if not self.dataset_path.exists():
            errors.append(f"Dataset path not found: {self.dataset_path}")
        if not self.primary_pbf_path.exists():
            errors.append(f"Primary PBF not found: {self.primary_pbf_path}")
        return errors


settings = Settings()
