from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.core.metrics import ROUTE_FAMILIARITY_EVENTS, ROUTE_FAMILIARITY_WORK_LIMITS
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.service import RouteFamiliarityService


NOW = datetime(2026, 10, 7, tzinfo=UTC)


def sig(cells):
    return RouteSignature(tuple(cells), tuple(100.0 for _ in cells), 100 * len(cells), 11)


class Repository:
    def __init__(self, personal=(), community=()):
        self.personal, self.community = personal, community
        self.calls = []

    async def personal_routes(self, *args):
        self.calls.append(("personal", args))
        return self.personal

    async def community_routes(self, *args):
        self.calls.append(("community", args))
        return self.community


@pytest.mark.asyncio
async def test_no_history_has_zero_penalty_and_bounded_two_queries():
    community = [dict(driver_id=f"d{i}", trip_id=f"t{i}", cells=["a", "b"],
                      cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
                 for i in range(5)]
    repo = Repository(community=community)
    service = RouteFamiliarityService(repo)
    before = ROUTE_FAMILIARITY_EVENTS.labels(stage="no_history", outcome="completed")._value.get()
    result = await service.assess_many("driver", {("station", "CHARGING"): sig(["a", "b"])}, NOW)
    assessment = result[("station", "CHARGING")]
    assert assessment.status == "NO_HISTORY"
    assert assessment.penalty_s == 0
    assert assessment.community_driver_count == 5
    assert ROUTE_FAMILIARITY_EVENTS.labels(stage="no_history", outcome="completed")._value.get() == before + 1
    assert repo.calls == [
        ("personal", ("driver", NOW, timedelta(days=7))),
        ("community", (["a", "b"], "driver", NOW, timedelta(days=7))),
    ]


@pytest.mark.asyncio
async def test_community_uses_distinct_driver_best_and_suppresses_below_five():
    rows = [dict(driver_id=f"d{i}", trip_id=f"t{i}", cells=["a", "b"],
                 cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
            for i in range(4)]
    repo = Repository(personal=[dict(driver_id="me", trip_id="p", cells=["a", "b"],
                                      cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)],
                      community=rows)
    assessment = (await RouteFamiliarityService(repo).assess_many(
        "me", {("station", "CHARGING"): sig(["a", "b"])}, NOW))["station", "CHARGING"]
    assert assessment.status == "AVAILABLE"
    assert assessment.personal_adherence == 1
    assert assessment.penalty_s == 0
    assert assessment.community_driver_count is None


@pytest.mark.asyncio
async def test_unmatched_personal_history_still_gives_confidence_and_penalty():
    repo = Repository(personal=[dict(driver_id="me", trip_id="p", cells=["x"],
                                    cell_distances_m=[100.0], distance_m=100.0, resolution=11)])
    assessment = (await RouteFamiliarityService(repo).assess_many(
        "me", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
    assert assessment.status == "AVAILABLE"
    assert assessment.personal_history_trip_count == 1
    assert assessment.personal_trip_count == 0
    assert assessment.confidence == pytest.approx(0.25)
    assert assessment.penalty_s == pytest.approx(7.5)


@pytest.mark.asyncio
async def test_community_smoothing_counts_each_driver_once():
    personal = [dict(driver_id="me", trip_id="p", cells=["a", "b"],
                     cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)]
    community = [dict(driver_id=f"d{i}", trip_id=f"t{i}-{j}", cells=["a", "b"],
                      cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
                  for i in range(5) for j in range(2)]
    assessment = (await RouteFamiliarityService(Repository(personal, community)).assess_many(
        "me", {("s", "x"): sig(["a", "b"])}, NOW))["s", "x"]
    assert assessment.community_driver_count == 5
    assert assessment.community_trip_count == 10
    assert assessment.community_adherence == pytest.approx(0.8125)


@pytest.mark.asyncio
async def test_matching_pair_budget_returns_entire_assessment_unavailable():
    route = sig(["a", "b"] * 400)
    row = dict(driver_id="me", trip_id="p", cells=list(route.cells),
               cell_distances_m=list(route.cell_distances_m), distance_m=route.distance_m, resolution=11)
    repo = Repository(personal=[row])
    before = ROUTE_FAMILIARITY_WORK_LIMITS._value.get()
    assessments = await RouteFamiliarityService(repo).assess_many(
        "me", {("s1", "x"): sig(["a"]), ("s2", "x"): route}, NOW)
    assert set(a.status for a in assessments.values()) == {"UNAVAILABLE"}
    assert all(a.penalty_s == 0 for a in assessments.values())
    assert all(a.degraded_reason == "SIMILARITY_WORK_LIMIT" for a in assessments.values())
    assert ROUTE_FAMILIARITY_WORK_LIMITS._value.get() == before + 1


@pytest.mark.asyncio
async def test_event_time_and_retrieval_caps_are_passed_to_repository():
    repo = Repository()
    await RouteFamiliarityService(repo).assess_many("me", {("s", "x"): sig(["a"])}, NOW)
    assert repo.calls == [
        ("personal", ("me", NOW, timedelta(days=7))),
        ("community", (["a"], "me", NOW, timedelta(days=7))),
    ]


@pytest.mark.asyncio
async def test_missing_route_geometry_is_unavailable_without_history_reads():
    repo = Repository()
    assessment = (await RouteFamiliarityService(repo).assess_many(
        "me", {("s", "x"): None}, NOW))["s", "x"]
    assert assessment.status == "UNAVAILABLE"
    assert assessment.penalty_s == 0
    assert repo.calls == []


def test_feature_is_off_by_default_and_enabled_requires_identity_secret():
    assert Settings(_env_file=None).enable_route_familiarity is False
    with pytest.raises(ValidationError):
        Settings(_env_file=None, enable_route_familiarity=True)
    assert Settings(_env_file=None, enable_route_familiarity=True,
                    route_familiarity_identity_secret="x" * 32).enable_route_familiarity
