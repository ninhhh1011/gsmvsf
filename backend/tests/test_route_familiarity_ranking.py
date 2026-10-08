from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.context import build_features
from backend.app.services.ranking.models import RankingPolicy
from backend.app.services.ranking.service import rank_features
from backend.app.services.route_familiarity.service import FamiliarityAssessment
from backend.tests.test_week4_ranking import candidate, evidence, station, queue, traffic, view


def test_familiarity_only_changes_final_cost_and_close_order():
    saved = evidence([candidate(duration=100), candidate("S002", duration=125)])
    features = build_features(saved, view(station(), queue(), station("S002"), queue("S002"), traffic()),
                              saved.request_time, RankingPolicy(), station_catalog)
    baseline = rank_features(features)
    familiar = rank_features(features, {("S001", "CHARGING"): type("A", (), {"penalty_s": 0})(),
                                        ("S002", "CHARGING"): type("A", (), {"penalty_s": 30})()})
    assert baseline[0].station_id == "S001"
    assert familiar[0].station_id == "S001"  # 25 seconds faster remains faster.
    assert familiar[0].features == baseline[0].features
    assert familiar[1].final_cost_s == baseline[1].final_cost_s + 30


def test_penalty_can_break_close_tie_but_not_a_large_physical_gap():
    saved = evidence([candidate(duration=100), candidate("S002", duration=110)])
    features = build_features(saved, view(station(), queue(), station("S002"), queue("S002"), traffic()),
                              saved.request_time, RankingPolicy(), station_catalog)
    ranked = rank_features(features, {("S001", "CHARGING"): type("A", (), {"penalty_s": 25})()})
    assert ranked[0].station_id == "S002"


def test_maximum_penalty_cannot_overturn_a_physical_gap_greater_than_thirty_seconds():
    saved = evidence([candidate(duration=100), candidate("S002", duration=131)], segment=None)
    features = build_features(saved, view(station(), queue(), station("S002"), queue("S002")),
                              saved.request_time, RankingPolicy(), station_catalog)
    ranked = rank_features(features, {
        ("S001", "CHARGING"): FamiliarityAssessment("AVAILABLE", penalty_s=30),
    })
    faster, slower = ranked
    assert faster.station_id == "S001"
    assert faster.eta_to_station_s == 100
    assert faster.eta_to_service_start_s == 220
    assert faster.eta_to_service_complete_s == 1300
    assert faster.final_cost_s == 1330
    assert faster.penalty_components_s == {"route_familiarity": 30}
    assert slower.eta_to_station_s == 131
    assert slower.eta_to_service_complete_s == slower.final_cost_s == 1331
    assert faster.features == features[0]
    assert slower.features == features[1]


async def test_history_failure_is_observable_and_degraded_without_details():
    from backend.app.services.ranking.service import RankingService
    from backend.tests.test_week4_ranking import HistoryResolver

    class BrokenEvaluator:
        async def assess_many(self, *_):
            raise RuntimeError("database details must not escape")

    resolver = HistoryResolver(station(), queue(), traffic())
    result = await RankingService(resolver, familiarity_evaluator=BrokenEvaluator()).recommend(
        evidence([candidate()]), candidate_signatures={("S001", "CHARGING"): None})
    assert result.familiarity_enabled is True
    assert result.familiarity_status == "UNAVAILABLE"
    assert result.degraded is True
    assert "ROUTE_FAMILIARITY_UNAVAILABLE" in result.degraded_reasons
    assert result.familiarity_penalty_s == 0
    assert "database details" not in str(result.model_dump())


async def test_enabled_familiarity_has_no_disabled_status_when_no_candidate_is_selected():
    from backend.app.services.ranking.service import RankingService
    from backend.tests.test_week4_ranking import HistoryResolver

    class Evaluator:
        async def assess_many(self, *_):
            raise AssertionError("no candidates should not query history")

    result = await RankingService(HistoryResolver(), familiarity_evaluator=Evaluator()).recommend(
        evidence([]), candidate_signatures={}, include_familiarity=True)
    assert result.familiarity_enabled is True
    assert result.has_recommendation is False
    assert result.familiarity_status is None
    assert result.familiarity is None
