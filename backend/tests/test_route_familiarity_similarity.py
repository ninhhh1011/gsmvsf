import random

import pytest

from backend.app.services.route_familiarity.models import RouteSignature
from backend.app.services.route_familiarity.similarity import (
    ComparisonBudget,
    SimilarityWorkLimitExceeded,
    index_route_signature,
    weighted_ordered_overlap,
)


def signature(cells, weights):
    return RouteSignature(tuple(cells), tuple(weights), sum(weights), 11)


def dense_oracle(a, b):
    previous = [0.0] * (len(b.cells) + 1)
    for cell, weight in zip(a.cells, a.cell_distances_m):
        current = [0.0]
        for index, other in enumerate(b.cells, 1):
            current.append(max(previous[index], current[-1],
                               previous[index - 1] + min(weight, b.cell_distances_m[index - 1])
                               if cell == other else 0.0))
        previous = current
    return previous[-1]


def test_sparse_weighted_lcs_matches_dense_oracle_on_random_routes():
    randomizer = random.Random(711)
    for _ in range(100):
        a_len, b_len = randomizer.randrange(1, 9), randomizer.randrange(1, 9)
        a = signature([randomizer.choice("abcd") for _ in range(a_len)],
                      [randomizer.uniform(0.1, 50) for _ in range(a_len)])
        b = signature([randomizer.choice("abcd") for _ in range(b_len)],
                      [randomizer.uniform(0.1, 50) for _ in range(b_len)])
        result = weighted_ordered_overlap(a, b, historical_positions=index_route_signature(b))
        assert result.shared_route_distance_m == pytest.approx(dense_oracle(a, b))


def test_sparse_lcs_keeps_direction_and_minimum_weight_semantics():
    a = signature(["a", "b", "c"], [10, 20, 30])
    b = signature(["c", "b", "a"], [100, 100, 100])
    assert weighted_ordered_overlap(a, b).shared_route_distance_m == 30
    assert weighted_ordered_overlap(a, a).shared_route_distance_m == 60


def test_repeated_cell_matches_consume_budget_before_sparse_work():
    a = signature(["a", "b"] * 400, [1] * 800)
    b = signature(["a", "b"] * 400, [1] * 800)
    with pytest.raises(SimilarityWorkLimitExceeded):
        weighted_ordered_overlap(a, b, budget=ComparisonBudget(250_000))
