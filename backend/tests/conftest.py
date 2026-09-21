"""Pytest configuration and fixtures."""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.app.config import settings


@pytest.fixture
def app():
    """Create application for testing."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def dataset_path():
    """Return dataset path."""
    return settings.dataset_path
