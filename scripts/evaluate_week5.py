"""Offline Week 5 comparison. Replay must finish and persist predictions first."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_week4 import evaluate_predictions


def completed_predictions(directory: Path):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    path = directory / 'predictions.jsonl'
    if manifest.get('status') not in ('PASS', 'PARTIAL'):
        raise ValueError('Inference must finish before opening evaluation labels')
    if manifest.get('labels_opened_during_inference') is not False:
        raise ValueError('Replay label-access audit missing or failed')
    if sha256(path.read_bytes()).hexdigest() != manifest.get('predictions_sha256'):
        raise ValueError('Persisted predictions changed after inference')
    predictions = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if len({row['event_id'] for row in predictions}) != len(predictions):
        raise ValueError('Duplicate prediction identity')
    return manifest, predictions


def evaluate(directory: Path, dataset: Path):
    manifest, predictions = completed_predictions(directory)
    # This is the first point labels are opened; runtime/replay never executes a label reader.
    references = pd.read_csv(dataset / 'labels/recommendation_labels.csv')
    ranking = pd.read_csv(dataset / 'training/ranking_reference.csv')
    auto = [row for row in predictions if row['mode'] == 'AUTO']
    report = evaluate_predictions(auto, references, ranking)
    modes = Counter(row['mode'] for row in predictions)
    no_service = [row for row in predictions if not row['need_service']]
    report.update(label='INITIAL LOCAL WEEK 5 EVALUATION',
        replay_status=manifest['status'], replay_counters=manifest['counters'],
        prediction_modes=dict(modes), label_population='AUTO source event IDs only; explicit intent '
            'probes are correctness evidence, excluded from AUTO reference agreement.',
        no_service_behavior=dict(requests=len(no_service),
            empty_recommendations=sum(not row['response']['has_recommendation'] for row in no_service)),
        observed_services=dict(Counter(row['response']['recommended_service_type'] or 'NONE'
                                      for row in predictions)),
        invalid_request_behavior='Controlled invalid intent is measured by verify_week5, outside '
                                 'source-only replay reference agreement.',
        refresh_behavior={key: manifest['counters'][key] for key in ('recommendation_changes',
            'unchanged_recommendations', 'candidate_state_conflicts', 'one_retry_recoveries',
            'second_conflict_failures')},
        label_leakage_audit=dict(status='PASS', predictions_written_before_labels=True,
            predictions_sha256=manifest['predictions_sha256'],
            runtime_inputs='GPS, SOC, trips, vehicles, map nodes, station/queue/traffic source tables; '
                           'source realtime GPS schedule. No demand/candidate/recommendation/ranking labels.'),
        limitations=['Finite representative replay, not full-dataset evaluation.',
            'Matched Week 1 origins can differ from frozen reference geometry.',
            'Reference ranking and Week 4 runtime ranking objectives differ; agreement is descriptive, '
            'not an invented accuracy acceptance threshold.'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', required=True)
    parser.add_argument('--dataset', default=str(ROOT / 'dataset_v1'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = evaluate(Path(args.replay), Path(args.dataset))
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT) or output.is_relative_to(ROOT / 'dataset_v1') or \
            output.is_relative_to(Path(args.dataset).resolve()):
        raise ValueError('Evaluation artifacts must stay inside the repository and outside Dataset')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report['baselines']['total_service_completion'], indent=2))


if __name__ == '__main__':
    main()
