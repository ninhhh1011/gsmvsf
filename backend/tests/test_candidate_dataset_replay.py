"""
Pytest integration of Dataset V1.3.1 candidate replay evaluation.
"""

import pytest
from scripts.evaluate_candidate_search import run_candidate_dataset_replay


def test_candidate_dataset_replay_sample():
    """Verify runtime candidate eligibility matches Dataset V1.3.1 canonical ground truth."""
    report = run_candidate_dataset_replay(sample_size=1000)
    assert report["total_evaluated"] == 1000
    assert report["eligible_accuracy"] == 100.0
    assert report["reason_accuracy"] == 100.0
    assert report["confusion_matrix"]["FP"] == 0
    assert report["confusion_matrix"]["FN"] == 0
