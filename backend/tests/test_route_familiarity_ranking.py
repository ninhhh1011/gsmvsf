from backend.app.services.candidate.station_catalog import station_catalog
from backend.app.services.ranking.context import build_features
from backend.app.services.ranking.models import RankingPolicy
from backend.app.services.ranking.service import rank_features
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
