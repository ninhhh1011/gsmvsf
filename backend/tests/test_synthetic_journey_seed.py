from datetime import datetime, UTC
import json

import pytest

import scripts.seed_synthetic_journeys as seed_module
from scripts.measure_virtual_driver_scale import load_driver_ids
from scripts.seed_synthetic_journeys import (
    choice_cost, output_directory, retry_templates, seed_time, trip_times,
)


def test_behavioral_inputs_change_choice_without_expected_route_outputs():
    assert choice_cost(600, 0, 0) < choice_cost(500, 10, 1)
    assert choice_cost(600, 0, 1) < choice_cost(500, 0, 0)


def test_seed_output_stays_inside_repository_and_outside_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(seed_module, 'ROOT', tmp_path)
    assert output_directory(tmp_path / 'runtime' / 'seed') == tmp_path / 'runtime' / 'seed'
    for output in (tmp_path.parent / 'escaped', tmp_path / 'dataset_v1' / 'seed'):
        with pytest.raises(ValueError):
            output_directory(output)


def test_manifest_retry_is_immutable_and_refuses_changed_or_missing_inputs(tmp_path):
    manifest = tmp_path / 'manifest.json'
    as_of = datetime(2026, 10, 12, tzinfo=UTC)
    data = {'seed': 7, 'as_of': as_of.isoformat(), 'drivers': 100,
            'load_namespace': 'synthetic-scale-personal', 'templates': [{'engine': 'graphhopper'}]}
    manifest.write_text(json.dumps(data), encoding='utf8')
    original = manifest.read_bytes()
    assert retry_templates(manifest, 7, as_of, 100, 'synthetic-scale-personal') == data['templates']
    assert manifest.read_bytes() == original
    with pytest.raises(ValueError):
        retry_templates(manifest, 8, as_of, 100, 'synthetic-scale-personal')
    with pytest.raises(ValueError):
        retry_templates(manifest, 7, as_of, 100, 'synthetic-scale-other')
    with pytest.raises(FileNotFoundError):
        retry_templates(tmp_path / 'missing.json', 7, as_of, 100, None)
    assert manifest.read_bytes() == original


def test_load_identity_alignment_and_causal_history_times():
    drivers = load_driver_ids('synthetic-scale-personal')
    assert len(drivers) == len(set(drivers)) == 1600
    assert drivers[0] == 'synthetic-scale-personal-100-0000'
    assert drivers[-1] == 'synthetic-scale-personal-1000-0999'
    with pytest.raises(ValueError):
        load_driver_ids('../real-driver')
    as_of = seed_time('2026-10-12T07:30:00Z')
    for day in range(1, 6):
        started, completed = trip_times(as_of, day, 600)
        assert started < completed < as_of
        assert (completed - started).total_seconds() == 600
    with pytest.raises(ValueError):
        seed_time('2026-10-12T07:30:00')
    with pytest.raises(ValueError):
        trip_times(as_of, 0, 600)
