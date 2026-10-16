"""Pytest configuration and fixtures."""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import create_app
from backend.app.config import settings
from backend.app.services.candidate.service import CandidateSearchService
from backend.app.services.demand.capability import VehicleCapabilityResolver
from backend.app.services.demand.service import DemandService
from backend.tests.mock_routing_adapter import MockRoutingAdapter
from backend.app.services.realtime.driver_state_manager import DriverStateManager
from backend.app.services.realtime.state import DriverStateStore


@pytest.fixture
def app():
    """Create application for testing."""
    application = create_app()
    resolver = VehicleCapabilityResolver()
    application.state.capability_resolver = resolver
    application.state.demand_service = DemandService(resolver)
    application.state.candidate_service = CandidateSearchService(
        MockRoutingAdapter(), capability_resolver=resolver)
    application.state.driver_state_manager = DriverStateManager.for_local()
    application.state.driver_state_store = DriverStateStore()
    return application


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
