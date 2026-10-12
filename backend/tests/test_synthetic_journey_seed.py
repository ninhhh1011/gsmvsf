from scripts.seed_synthetic_journeys import choice_cost


def test_behavioral_inputs_change_choice_without_expected_route_outputs():
    assert choice_cost(600, 0, 0) < choice_cost(500, 10, 1)
    assert choice_cost(600, 0, 1) < choice_cost(500, 0, 0)
