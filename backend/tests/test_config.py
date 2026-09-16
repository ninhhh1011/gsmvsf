"""Tests for configuration."""
import pytest

from backend.app.config import Settings


def test_settings_defaults():
    """Test default settings load correctly."""
    settings = Settings()
    assert settings.app_name == "EV Recommendation API"
    assert settings.log_level == "INFO"


def test_settings_validate_paths():
    """Test path validation."""
    settings = Settings()
    errors = settings.validate_paths()
    assert isinstance(errors, list)
