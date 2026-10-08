"""Familiarity integration preserves legacy ranking and the full-search retry."""
from datetime import timedelta
from types import SimpleNamespace

import h3
import pytest

from backend.app.config import settings
from backend.app.services.candidate.models import CandidateSearchRequest
from backend.app.services.candidate.station_catalog import StationRecord
from backend.app.services.demand.models import DemandContext, RequestedServiceType, RequestSource
from backend.app.services.ranking.models import CandidateSearchEvidence
from backend.app.services.ranking.orchestration import RecommendationWorkflow
from backend.app.services.route_familiarity.service import RouteFamiliarityService
from backend.app.services.route_familiarity.signature import create_route_signature, decode_polyline
from backend.app.services.routing.models import RouteResult, RouteStatus
from backend.tests.test_route_familiarity_domain import polyline
from backend.tests.test_week4_ranking import NOW, HistoryResolver, queue, station


ORIGIN = (21.0, 105.0)
DESTINATION = (21.003, 105.0)
STATION_POINTS = {"S001": (21.001, 105.0), "S002": (21.001, 105.002)}


def catalog():
    records = [StationRecord(
        station_id=sid, access_node_id=sid, latitude=point[0], longitude=point[1],
        access_latitude=point[0], access_longitude=point[1], station_type="CHARGING",
        connector_type="CCS2_TYPE2", battery_type="", supported_vehicle_type="EV_CAR",
        total_slots=2, charging_slots=2, swap_slots=0,
    ) for sid, point in STATION_POINTS.items()]
    return SimpleNamespace(get_all_stations=lambda: records,
                           get_station=lambda sid: next(s for s in records if s.station_id == sid))


class Routes:
    """External routing boundary with deterministic geometry and physical durations."""
    def __init__(self):
        self.generation = 0
        self.requests = []

    def points(self, origin, destination):
        if self.generation and origin == STATION_POINTS["S002"]:
            return [origin, (21.002, 105.003), destination]
        return [origin, destination]

    async def route(self, request):
        self.requests.append((self.generation, request))
        origin, destination = request.origin.coordinates_lat_lon, request.destination.coordinates_lat_lon
        duration = 100 if destination == STATION_POINTS["S001"] else 131
        return RouteResult(status=RouteStatus.SUCCESS, distance_m=1000, duration_s=duration,
                           geometry=polyline(self.points(origin, destination)), engine_name="test")


class Searches:
    def __init__(self, on_save=None):
        self.saved = []
        self.on_save = on_save

    async def save_search(self, evidence):
        # Mirror the persistent boundary: only JSON evidence survives a reload.
        self.saved.append(evidence.model_dump(mode="json"))
        if self.on_save:
            self.on_save(len(self.saved))

    async def get_search(self, search_id):
        return CandidateSearchEvidence.model_validate(next(
            row for row in self.saved if row["candidate_search_id"] == search_id))


class History:
    def __init__(self, rows=()):
        self.rows = rows
        self.calls = []

    async def personal_routes(self, driver_id, as_of, lookback):
        self.calls.append(("personal", driver_id, as_of, lookback))
        return self.rows

    async def community_routes(self, cells, driver_id, as_of, lookback):
        self.calls.append(("community", cells, driver_id, as_of, lookback))
        return []


def workflow(evaluator=None, repository=None, routes=None, resolver=None):
    return RecommendationWorkflow(repository or Searches(), resolver or HistoryResolver(
        station(), queue(), station("S002"), queue("S002")), routes or Routes(), catalog(),
        familiarity_evaluator=evaluator)


def body():
    result = {"requested_service": "CHARGING", "avoid_congestion": False, "context": {
        "driver_id": "driver", "vehicle_id": "V0001", "timestamp": NOW.isoformat(),
        "current_soc_pct": 60, "estimated_remaining_range_km": 200,
        "raw_latitude": ORIGIN[0], "raw_longitude": ORIGIN[1],
    }}
    result.update(destination_latitude=DESTINATION[0], destination_longitude=DESTINATION[1])
    return result


def search_request(app):
    context = DemandContext(**body()["context"])
    energy = app.state.demand_service.process_driver_request(context, RequestedServiceType.CHARGING)
    return CandidateSearchRequest(energy_request=energy, destination_latitude=DESTINATION[0],
                                  destination_longitude=DESTINATION[1])


@pytest.mark.asyncio
async def test_disabled_recommend_preserves_legacy_defaults_and_costs_without_familiarity_work(
        client, app, monkeypatch):
    from backend.app.services.route_familiarity import signature

    monkeypatch.setattr(settings, "enable_route_familiarity", False)
    monkeypatch.setattr(signature, "create_route_signature",
                        lambda *_: pytest.fail("disabled workflow built a route signature"))
    history = History()
    combined = workflow()
    app.state.recommendation_workflow = combined
    # The attached history boundary must remain untouched while feature-off.
    combined.ranking.familiarity_evaluator = RouteFamiliarityService(history)
    response = await client.post("/api/v1/recommend", json=body())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["familiarity_status"] is None  # c80a2b4 legacy neutral default.
    assert result["familiarity_enabled"] is False
    assert result["route_adherence"] is result["family_support"] is result["family_id"] is None
    assert result["familiarity_penalty_s"] == result["driver_trip_count"] == 0
    assert result["history_window_days"] == 7
    assert result["familiarity"]["status"] == "DISABLED"
    assert result["recommended_station_id"] == "S001"
    assert [c["final_cost_s"] for c in result["ranked_candidates"]] == [1300, 1331]
    assert all(c["final_cost_s"] == c["eta_to_service_complete_s"] and
               c["penalty_components_s"] == {} for c in result["ranked_candidates"])
    assert history.calls == []
    # Compare all candidate/legacy familiarity outputs with staged neutral ranking.
    saved = await combined.repository.get_search(result["candidate_search_id"])
    staged = (await combined.ranking.recommend(saved)).model_dump(mode="json")
    for key in ("ranked_candidates", "familiarity", "familiarity_status", "familiarity_enabled",
                "route_adherence", "family_support", "family_id", "familiarity_penalty_s",
                "driver_trip_count", "history_window_days"):
        if key == "ranked_candidates":
            assert [{k: v for k, v in c.items() if k != "familiarity"}
                    for c in result[key]] == [{k: v for k, v in c.items() if k != "familiarity"}
                                               for c in staged[key]]
        elif key != "familiarity":
            assert result[key] == staged[key]


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_staged_ranking_preserves_legacy_nulls_and_omits_only_new_explanations(client, app, empty):
    combined = workflow()
    app.state.recommendation_workflow = combined
    request = search_request(app)
    if empty:
        request = request.model_copy(update={"energy_request": request.energy_request.model_copy(
            update={"request_source": RequestSource.AUTO_DETECTED, "need_service": False,
                    "resolved_service_type": None})})
    else:
        request = request.model_copy(update={"destination_latitude": None, "destination_longitude": None})
    saved = await combined.search(request)
    response = await client.post("/api/v1/ranking", json={"candidate_search_id": saved.candidate_search_id})
    assert response.status_code == 200, response.text
    result = response.json()
    assert "familiarity" not in result
    assert result["familiarity_status"] is result["family_id"] is None
    assert result["location_source"] is result["location_timestamp"] is None
    assert result["energy_context"]["road_segment_id"] is None
    if empty:
        assert result["recommended_station_id"] is result["recommended_service_type"] is None
        assert result["ranked_candidates"] == []
    else:
        candidate = result["ranked_candidates"][0]
        assert "familiarity" not in candidate
        assert candidate["eta_to_destination_via_station_s"] is None
        assert candidate["features"]["detour_duration_s"] is None
        assert candidate["features"]["queue_assumption"] is None
        assert candidate["features"]["traffic_state"]["snapshot_id"] is None


@pytest.mark.asyncio
async def test_enabled_workflow_signs_both_legs_without_persisting_transient_signatures(app, monkeypatch):
    from backend.app.services.route_familiarity import signature

    built = []
    def capture(lines):
        result = create_route_signature(lines)
        built.append((lines, result))
        return result
    monkeypatch.setattr(signature, "create_route_signature", capture)
    history = History()
    combined = workflow(RouteFamiliarityService(history))
    result = await combined.recommend(search_request(app))
    assert result.familiarity.status == "NO_HISTORY"
    lines, selected = built[0]
    assert [decode_polyline(line) for line in lines] == [
        [ORIGIN, STATION_POINTS["S001"]], [STATION_POINTS["S001"], DESTINATION]]
    assert selected.distance_m == pytest.approx(333.585, abs=0.1)
    assert h3.latlng_to_cell(21.0029, 105.0, 11) in result.familiarity.route_cells
    assert result.familiarity.route_cells == list(selected.cells)
    assert history.calls[0] == ("personal", "driver", NOW, timedelta(days=7))
    assert len(history.calls) == 2
    saved = await combined.repository.get_search(result.candidate_search_id)
    assert saved.result.eligible_count == 2
    serialized = str(combined.repository.saved)
    assert "geometry" not in serialized and "signatures" not in serialized
    assert not any(cell in serialized for _, sig in built for cell in sig.cells)


@pytest.mark.asyncio
async def test_enabled_state_conflict_retries_search_and_uses_only_new_route_carrier(app, monkeypatch):
    from backend.app.services.route_familiarity import signature

    built = []
    def capture(lines):
        result = create_route_signature(lines)
        built.append(result)
        return result
    monkeypatch.setattr(signature, "create_route_signature", capture)
    routes = Routes()
    resolver = HistoryResolver(station(), queue(), station("S002"), queue("S002"))
    def change_after_first_save(count):
        if count == 1:
            resolver.snapshots = (station(operating_status="OFFLINE"), queue(),
                                  station("S002"), queue("S002"))
            routes.generation = 1
    searches = Searches(change_after_first_save)
    history = History()
    combined = workflow(RouteFamiliarityService(history), searches, routes, resolver)
    metrics = {}
    result = await combined.recommend(search_request(app), metrics=metrics)
    assert metrics["workflow_attempts"] == metrics["candidate_search_calls"] == metrics["ranking_calls"] == 2
    assert metrics["candidate_state_conflicts"] == 1
    assert len(searches.saved) == 2 and len(built) == 3
    assert [row["result"]["eligible_count"] for row in searches.saved] == [2, 1]
    assert result.candidate_search_id == searches.saved[1]["candidate_search_id"]
    assert result.recommended_station_id == "S002"
    assert built[1].cells != built[2].cells
    assert result.familiarity.route_cells == list(built[2].cells)
    assert history.calls[1][1] == sorted(set(built[2].cells))
    assert len(history.calls) == 2  # Invalidated ranking never read history.
    assert [generation for generation, request in routes.requests
            if request.origin.coordinates_lat_lon == STATION_POINTS["S002"]] == [0, 1]


@pytest.mark.asyncio
async def test_penalized_route_more_than_thirty_seconds_physically_faster_still_wins(app):
    routes = Routes()
    familiar = create_route_signature([
        polyline([ORIGIN, STATION_POINTS["S002"]]),
        polyline([STATION_POINTS["S002"], DESTINATION]),
    ])
    history = History([dict(cells=familiar.cells, cell_distances_m=familiar.cell_distances_m,
                           distance_m=familiar.distance_m, resolution=11)])
    evaluator = RouteFamiliarityService(history, max_penalty_s=30, confidence_prior_strength=0)
    combined = workflow(evaluator, routes=routes)
    result = await combined.recommend(search_request(app))
    faster, slower = result.ranked_candidates
    assert faster.station_id == result.recommended_station_id == "S001"
    assert slower.eta_to_service_complete_s - faster.eta_to_service_complete_s == 31
    assert faster.familiarity.penalty_s > slower.familiarity.penalty_s
    assert 0 < faster.familiarity.penalty_s <= 30
    assert faster.final_cost_s == faster.eta_to_service_complete_s + faster.familiarity.penalty_s
    assert faster.final_cost_s < slower.final_cost_s
