"""Application configuration management."""
from pathlib import Path

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

    # Paths
    dataset_path: Path = Path("dataset_v1")
    primary_pbf_path: Path = Path("dataset_v1/map/raw/hanoi-patched.osm.pbf")
    osrm_data_path: Path = Path("runtime/osrm")

    # OSRM
    osrm_base_url: str = "http://localhost:5000"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/ev_recommendation"
    database_url_sync: str = "postgresql://postgres:postgres@db:5432/ev_recommendation"

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
