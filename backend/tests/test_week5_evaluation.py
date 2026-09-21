"""Labels cannot be opened before a complete, immutable prediction artifact exists."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.evaluate_week5 import completed_predictions, evaluate
from scripts.replay_week5 import COUNTERS


def test_unfinished_inference_fails_before_any_label_access(tmp_path):
    (tmp_path / 'manifest.json').write_text('{"status":"RUNNING"}')
    with pytest.raises(ValueError, match='Inference must finish'):
        evaluate(tmp_path, tmp_path / 'labels-do-not-exist')


def test_prediction_hash_and_label_audit_are_required(tmp_path):
    predictions = tmp_path / 'predictions.jsonl'
    predictions.write_text('{"event_id":"DE1"}\n')
    manifest = dict(status='PASS', labels_opened_during_inference=False,
        predictions_sha256=sha256(predictions.read_bytes()).hexdigest())
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    assert completed_predictions(tmp_path)[1] == [{'event_id': 'DE1'}]
    predictions.write_text('{"event_id":"DE2"}\n')
    with pytest.raises(ValueError, match='changed after inference'):
        completed_predictions(tmp_path)


def test_complete_offline_evaluation_uses_canonical_reference_locations(tmp_path):
    row = dict(event_id='DE000001', mode='AUTO', need_service=False, ranked=[], candidates=[],
        response={'has_recommendation': False, 'recommended_service_type': None})
    path = tmp_path / 'predictions.jsonl'
    path.write_text(json.dumps(row) + '\n')
    manifest = dict(status='PASS', labels_opened_during_inference=False,
        predictions_sha256=sha256(path.read_bytes()).hexdigest(), counters=dict.fromkeys(COUNTERS, 0))
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    report = evaluate(tmp_path, Path(__file__).resolve().parents[2] / 'dataset_v1')
    assert report['prediction_count'] == 1
    assert report['no_service_behavior'] == {'requests': 1, 'empty_recommendations': 1}
    assert report['label_leakage_audit']['status'] == 'PASS'
