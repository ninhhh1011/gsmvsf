from scripts.benchmark_route_familiarity import benchmark_cases


def test_benchmark_covers_required_dataset_sizes_and_candidate_fanout():
    assert [(case.history_size, case.candidate_count) for case in benchmark_cases()] == [
        (150, 30), (10_000, 30), (100_000, 30)
    ]
