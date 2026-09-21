"""Actual GraphHopper matching error contract; geometry covered by migration tests."""
from unittest.mock import AsyncMock
import httpx
import pytest
from backend.app.services.map_matching.graphhopper_adapter import GraphHopperMapMatchingAdapter
from backend.app.services.map_matching.engine import (MapMatchingTimeoutError, MapMatchingEngineUnavailableError, MapMatchingInvalidRequestError, MapMatchingNoMatchError)

@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [(httpx.ReadTimeout("timeout"), MapMatchingTimeoutError), (httpx.ConnectError("down"), MapMatchingEngineUnavailableError)])
async def test_transport_errors(error, expected):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.side_effect = error
    with pytest.raises(expected):
        await GraphHopperMapMatchingAdapter(client=client).match([(105.8,21), (105.81,21)], vehicle_category="EV_CAR")
    client.aclose.assert_not_called()

@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected", [("Sequence is broken", MapMatchingNoMatchError), ("Invalid profile", MapMatchingInvalidRequestError)])
async def test_engine_rejection(message, expected):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = httpx.Response(400, text=message)
    with pytest.raises(expected):
        await GraphHopperMapMatchingAdapter(client=client).match([(105.8,21), (105.81,21)], vehicle_category="EV_CAR")

@pytest.mark.asyncio
async def test_invalid_input_never_sent():
    client = AsyncMock(spec=httpx.AsyncClient)
    with pytest.raises(MapMatchingInvalidRequestError):
        await GraphHopperMapMatchingAdapter(client=client).match([], vehicle_category="EV_CAR")
    client.post.assert_not_called()
