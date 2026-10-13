from datetime import UTC, datetime, timedelta
import asyncio
import threading

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.core.metrics import (
    ROUTE_FAMILIARITY_EVENTS, ROUTE_FAMILIARITY_WORK_LIMITS,
    ROUTE_FAMILIARITY_HISTORY_PAIRS,
)
from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.service import RouteFamiliarityService


NOW = datetime(2026, 10, 7, 1, tzinfo=UTC)


def sig(cells):
    coordinates = geometry(cells)
    return RouteSignature(tuple(cells), tuple(100.0 for _ in cells), 100 * len(cells), 11,
                          coordinates)


def geometry(cells):
    offset = 0 if cells[0] in ("a", "b", "target") else 0.02
    points = [(21.0 + offset, 105.8)]
    for i, cell in enumerate(cells):
        distance = (100 if cell == "a" else 200) if len(cells) > 10 else (i + 1) * 100
        points.append((21.0 + offset + distance / 111195, 105.8))
    return tuple(points)


def history_row(**values):
    return dict(values, geometry=geometry(values["cells"]),
                started_at=NOW - timedelta(minutes=2), completed_at=NOW - timedelta(minutes=1))


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
@pytest.mark.parametrize('cancel_first', [False, True])
async def test_cpu_evaluations_share_one_slot_without_serializing_history_or_blocking_loop(monkeypatch, cancel_first):
    entered, release = threading.Event(), threading.Event()
    active = peak = calls = 0
    repo = Repository()
    service = RouteFamiliarityService(repo)
    def evaluate(*args):
        nonlocal active, peak, calls
        active += 1
        peak = max(peak, active)
        calls += 1
        entered.set()
        try:
            assert release.wait(5)
            return {}
        finally:
            active -= 1
    monkeypatch.setattr(service, '_evaluate', evaluate)
    first = asyncio.create_task(service.assess_many('first', {'station': sig(['a'])}, NOW))
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        second = asyncio.create_task(service.assess_many('second', {'station': sig(['a'])}, NOW))
        await asyncio.sleep(0.05)
        assert len(repo.calls) == 4
        assert calls == 1
        if cancel_first:
            first.cancel()
            await asyncio.sleep(0.05)
            assert calls == 1
            assert not first.done()
    finally:
        release.set()
        if cancel_first:
            with pytest.raises(asyncio.CancelledError):
                await first
        else:
            await first
        if 'second' in locals():
            await second
    assert peak == 1


@pytest.mark.asyncio
async def test_no_history_has_zero_penalty_and_bounded_two_queries():
    community = [history_row(driver_id=f"d{i}", trip_id=f"t{i}", cells=["a", "b"],
                      cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
                 for i in range(5)]
    repo = Repository(community=community)
    service = RouteFamiliarityService(repo)
    before = ROUTE_FAMILIARITY_EVENTS.labels(stage="no_history", outcome="completed")._value.get()
    result = await service.assess_many("driver", {("station", "CHARGING"): sig(["a", "b"])}, NOW)
    assessment = result[("station", "CHARGING")]
    assert assessment.status == "AVAILABLE"
    assert assessment.penalty_s == 0
    assert assessment.community_driver_count == 5
    assert ROUTE_FAMILIARITY_EVENTS.labels(stage="no_history", outcome="completed")._value.get() == before
    assert repo.calls == [
        ("personal", ("driver", NOW, timedelta(days=7))),
        ("community", (["a", "b"], "driver", NOW, timedelta(days=7))),
    ]


@pytest.mark.asyncio
async def test_community_uses_distinct_driver_best_and_suppresses_below_five():
    rows = [history_row(driver_id=f"d{i}", trip_id=f"t{i}", cells=["a", "b"],
                 cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
            for i in range(4)]
    repo = Repository(personal=[history_row(driver_id="me", trip_id="p", cells=["a", "b"],
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
    repo = Repository(personal=[history_row(driver_id="me", trip_id="p", cells=["x"],
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
    personal = [history_row(driver_id="me", trip_id="p", cells=["a", "b"],
                     cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)]
    community = [history_row(driver_id=f"d{i}", trip_id=f"t{i}-{j}", cells=["a", "b"],
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
    row = history_row(driver_id="me", trip_id="p", cells=list(route.cells),
               cell_distances_m=list(route.cell_distances_m), distance_m=route.distance_m, resolution=11)
    repo = Repository(personal=[row])
    before = ROUTE_FAMILIARITY_WORK_LIMITS._value.get()
    history_pairs_before = ROUTE_FAMILIARITY_HISTORY_PAIRS._value.get()
    assessments = await RouteFamiliarityService(repo).assess_many(
        "me", {("s1", "x"): sig(["a"]), ("s2", "x"): route}, NOW)
    assert set(a.status for a in assessments.values()) == {"UNAVAILABLE"}
    assert all(a.penalty_s == 0 for a in assessments.values())
    assert all(a.degraded_reason == "SIMILARITY_WORK_LIMIT" for a in assessments.values())
    assert ROUTE_FAMILIARITY_WORK_LIMITS._value.get() == before + 1
    assert ROUTE_FAMILIARITY_HISTORY_PAIRS._value.get() == history_pairs_before + 2


@pytest.mark.asyncio
async def test_event_time_and_retrieval_caps_are_passed_to_repository():
    repo = Repository()
    await RouteFamiliarityService(repo).assess_many("me", {("s", "x"): sig(["a"])}, NOW)
    assert repo.calls == [
        ("personal", ("me", NOW, timedelta(days=7))),
        ("community", (["a"], "me", NOW, timedelta(days=7))),
    ]


@pytest.mark.asyncio
async def test_history_pairs_metric_counts_each_candidate_and_history_pair_without_labels():
    row = history_row(driver_id="private", trip_id="private-trip", cells=["a"],
               cell_distances_m=[100.0], distance_m=100.0, resolution=11)
    repo = Repository(personal=[row, row], community=[row, row, row])
    metric = ROUTE_FAMILIARITY_HISTORY_PAIRS
    before = metric._value.get()

    await RouteFamiliarityService(repo).assess_many(
        "private", {("s1", "x"): sig(["a"]), ("s2", "x"): sig(["a"])}, NOW)

    assert metric._value.get() == before + 10
    assert not metric._labelnames

    await RouteFamiliarityService(Repository()).assess_many("private", {("s", "x"): sig(["a"])}, NOW)
    assert metric._value.get() == before + 10

    non_overlapping = dict(row, cells=["different"])
    await RouteFamiliarityService(Repository(personal=[non_overlapping], community=[non_overlapping])).assess_many(
        "private", {("s", "x"): sig(["a"])}, NOW)
    assert metric._value.get() == before + 12


@pytest.mark.asyncio
async def test_missing_route_geometry_is_unavailable_without_history_reads(monkeypatch):
    from backend.app.services.route_familiarity import service as familiarity_service

    repo = Repository()
    events, durations = [], []
    monkeypatch.setattr(familiarity_service, "record_route_familiarity_event",
                        lambda *event: events.append(event))
    monkeypatch.setattr(familiarity_service, "observe_route_familiarity",
                        lambda *timing: durations.append(timing))
    assessment = (await RouteFamiliarityService(repo).assess_many(
        "private-driver", {("s", "x"): None}, NOW))["s", "x"]
    assert assessment.status == "UNAVAILABLE"
    assert assessment.penalty_s == 0
    assert repo.calls == []
    assert ("assessment", "unavailable") in events
    assert ("fallback", "unavailable") in events
    assert any(stage == "evaluation" and elapsed >= 0 for stage, elapsed in durations)


@pytest.mark.asyncio
async def test_geometric_heading_rejection_drives_capped_penalty():
    target = sig(["a", "b"])
    reverse = history_row(driver_id="me", trip_id="reverse", cells=["a", "b"],
                          cell_distances_m=[100.0, 100.0], distance_m=200.0, resolution=11)
    reverse["geometry"] = tuple(reversed(target.coordinates))
    assessment = (await RouteFamiliarityService(Repository(personal=[reverse])).assess_many(
        "me", {("s", "CHARGING"): target}, NOW))["s", "CHARGING"]
    assert assessment.personal_adherence == 0
    assert assessment.penalty_s == pytest.approx(7.5)


@pytest.mark.asyncio
async def test_legacy_cell_history_is_unavailable_without_inventing_geometry():
    row = dict(driver_id="me", trip_id="legacy", cells=["a"], cell_distances_m=[100.0],
               distance_m=100.0, resolution=11, completed_at=NOW - timedelta(minutes=1))
    assessment = (await RouteFamiliarityService(Repository(personal=[row])).assess_many(
        "me", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
    assert assessment.status == "UNAVAILABLE"
    assert assessment.penalty_s == 0


@pytest.mark.asyncio
async def test_sparse_long_history_cannot_expand_beyond_batch_sample_budget():
    rows = [history_row(driver_id="me", trip_id=f"long-{i}", cells=["a"],
                        cell_distances_m=[40030.0], distance_m=40030.0, resolution=11)
            for i in range(15)]
    for i, row in enumerate(rows):
        row["geometry"] = ((21, 105.8 + i * .00001), (21.36, 105.8 + i * .00001))
    assessment = (await RouteFamiliarityService(Repository(personal=rows)).assess_many(
        "me", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
    assert assessment.status == "UNAVAILABLE"
    assert assessment.degraded_reason == "SIMILARITY_WORK_LIMIT"
    assert assessment.penalty_s == 0


def test_feature_is_off_by_default_and_enabled_requires_identity_secret():
    assert Settings(_env_file=None).enable_route_familiarity is False
    with pytest.raises(ValidationError):
        Settings(_env_file=None, enable_route_familiarity=True)
    assert Settings(_env_file=None, enable_route_familiarity=True,
                    route_familiarity_identity_secret="x" * 32).enable_route_familiarity


def test_familiarity_penalty_configuration_cannot_exceed_contract_cap():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_familiarity_penalty_s=30.01)


@pytest.mark.parametrize("override", [-0.01, 30.01])
def test_service_rejects_penalty_overrides_outside_contract_cap(override):
    with pytest.raises(ValueError, match="max_penalty_s"):
        RouteFamiliarityService(Repository(), max_penalty_s=override)


@pytest.mark.asyncio
async def test_final_penalty_remains_capped_even_if_service_override_changes():
    row = history_row(driver_id="d", trip_id="t", cells=["other"], cell_distances_m=[100.0],
               distance_m=100.0, resolution=11)
    service = RouteFamiliarityService(Repository(personal=[row] * 50), max_penalty_s=30)
    service.max_penalty_s = 100
    assessment = (await service.assess_many("d", {("s", "x"): sig(["target"])}, NOW))["s", "x"]
    assert assessment.penalty_s == 30


@pytest.mark.asyncio
async def test_truncation_uses_sentinel_metadata_not_exact_full_result_counts():
    row = history_row(driver_id="d", trip_id="t", cells=["a"], cell_distances_m=[100.0],
               distance_m=100.0, resolution=11)
    assessment = (await RouteFamiliarityService(Repository(personal=[row] * 50)).assess_many(
        "d", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
    assert assessment.history_truncated is False

    repo = Repository(personal=[row] * 51)
    assessment = (await RouteFamiliarityService(repo).assess_many(
        "d", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
    assert assessment.history_truncated is True

    for sentinel in (dict(active_rank=101, driver_rank=1), dict(active_rank=1, driver_rank=6)):
        repo = Repository(community=[dict(row, **sentinel)])
        assessment = (await RouteFamiliarityService(repo).assess_many(
            "d", {("s", "x"): sig(["a"])}, NOW))["s", "x"]
        assert assessment.history_truncated is True
