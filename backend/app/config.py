"""Application configuration management."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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

    # Paths
    app_path: Path = Path(__file__).parent
    dataset_path: Path = Path("dataset_v1")
    primary_pbf_path: Path = Path("dataset_v1/map/raw/hanoi-patched.osm.pbf")

    # GraphHopper
    graphhopper_base_url: str = "http://127.0.0.1:8989"
    graphhopper_data_path: Path = Path("runtime/graphhopper")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/ev_recommendation"
    database_url_sync: str = "postgresql://postgres:postgres@db:5432/ev_recommendation"

    # Week 4 project policy; freshness follows Dataset cadence, TTL is cache retention.
    redis_url: str = "redis://127.0.0.1:6379/0"
    snapshot_cache_ttl_s: int = Field(default=60, ge=1)
    snapshot_cache_timeout_s: float = Field(default=0.2, gt=0, allow_inf_nan=False)
    snapshot_db_timeout_s: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    station_fresh_s: float = Field(default=600, ge=0, allow_inf_nan=False)
    queue_fresh_s: float = Field(default=600, ge=0, allow_inf_nan=False)
    traffic_fresh_s: float = Field(default=1800, ge=0, allow_inf_nan=False)
    missing_queue_wait_s: float = Field(default=5400, ge=0, allow_inf_nan=False)
    snapshot_ingestion_token: str = ""

    # Mapping
    mapping_dir: Path = Path("runtime/map_mapping")

    # Logging
    log_level: str = "INFO"

    def validate_paths(self) -> list[str]:
        """Validate critical paths exist. Returns list of errors."""
        errors = []
        if not self.dataset_path.exists():
            errors.append(f"Dataset path not found: {self.dataset_path}")
        if not self.primary_pbf_path.exists():
            errors.append(f"Primary PBF not found: {self.primary_pbf_path}")
        return errors


settings = Settings()
