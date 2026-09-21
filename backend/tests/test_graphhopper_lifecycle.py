import pytest
from backend.app.core.lifespan import lifespan
from backend.app.main import create_app
from backend.app.services.routing.graphhopper_routing_adapter import GraphHopperRoutingAdapter
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter

@pytest.mark.asyncio
async def test_adapters_share_and_close_lifespan_client():
    async with lifespan(create_app()):
        route = GraphHopperRoutingAdapter()
        match = GraphHopperMapMatchingAdapter()
        assert route._client is not None
        assert route._client is match._client
        assert not route._client.is_closed
    assert route._client.is_closed
