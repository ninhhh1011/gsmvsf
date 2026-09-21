"""Source reconstruction and offline metrics; no routing fakes enter evaluation."""
from pathlib import Path

import pandas as pd

from scripts.evaluate_week4 import reconstruct_contexts, compare_order, evaluate_predictions


ROOT = Path(__file__).resolve().parents[2]


def test_source_contexts_match_frozen_event_schedule_and_causal_gps():
    contexts = reconstruct_contexts(ROOT / 'dataset_v1')
    # Evaluation labels are opened only after the independent reconstruction.
    labels = pd.read_csv(ROOT / 'dataset_v1/labels/demand_labels.csv')
    labels = labels[labels.request_source.eq('AUTO_DETECTED')].set_index('event_id')
    assert {row['event_id'] for row in contexts} == set(labels.index)
    for row in contexts:
        truth = labels.loc[row['event_id']]
        context = row['context']
        assert row['snapshot_index'] == truth.snapshot_index
        assert row['event_timestamp'] == truth.timestamp
        assert context['trip_id'] == truth.trip_id
        assert context['current_soc_pct'] == truth.current_soc_pct
        assert context['estimated_remaining_range_km'] == truth.estimated_remaining_range_km
        assert round(context['remaining_trip_distance_km'], 3) == truth.remaining_trip_distance_km
        assert round(context['safety_reserve_km'], 3) == truth.safety_reserve_km
        assert context['road_segment_id'] is None
        assert pd.Timestamp(row['gps_timestamp']) <= pd.Timestamp(row['event_timestamp'])
        assert row['gps_age_s'] >= 0


def test_common_pool_comparison_preserves_service_identity_and_pair_denominator():
    charge, swap, other = ('S1', 'CHARGING'), ('S1', 'BATTERY_SWAP'), ('S2', 'CHARGING')
    metrics = compare_order([swap, charge, other], [charge, swap])
    assert metrics == {'common_count': 2, 'common_top1_station_match': True,
                      'common_top1_identity_match': False, 'pairwise_agree': 0,
                      'pairwise_total': 1}
    assert compare_order([other], [charge])['common_top1_identity_match'] is None
    assert compare_order([charge], [charge])['pairwise_total'] == 0


def test_report_counts_empty_and_missing_reference_without_fabricating_accuracy():
    predictions = [dict(event_id='empty', candidates=[], ranked=[], need_service=True),
                   dict(event_id='no-demand', candidates=[], ranked=[], need_service=False)]
    references = pd.DataFrame([dict(event_id='empty', has_recommendation=False,
                                    reference_station_id=None, eligible_candidate_count=0)])
    ranking = pd.DataFrame(columns=['event_id', 'station_id', 'service_type', 'reference_rank'])
    report = evaluate_predictions(predictions, references, ranking)
    assert report['reference_events'] == 1
    assert report['runtime_group_sizes'] == {'zero': 2, 'single': 0, 'multiple': 0}
    assert report['reference_group_sizes'] == {'zero': 1, 'single': 0, 'multiple': 0}
    assert report['eligible_count_distribution']['all_predictions'] == dict(
        count=2, min=0, median=0.0, max=0, histogram={'0': 2})
    assert report['eligible_count_distribution']['joined_reference_events']['count'] == 1
    for score in report['baselines'].values():
        assert score['recommendation_presence']['matches'] == 1
        assert score['overall_station_agreement'] == dict(matches=1, total=1, rate=1.0)
        assert score['overall_composite_agreement'] == dict(matches=1, total=1, rate=1.0)
        assert score['station_top1']['total'] == 0
        assert score['station_top1']['rate'] is None
        assert score['pairwise_common_pool']['total'] == 0


def test_full_pool_miss_can_be_common_pool_match():
    ranked = [dict(station_id=sid, service_type='CHARGING', distance_to_station_m=i,
                   eta_to_station_s=i) for i, sid in enumerate(('outside', 'best', 'second'))]
    predictions = [dict(event_id='event', candidates=[], ranked=ranked, need_service=True)]
    references = pd.DataFrame([dict(event_id='event', has_recommendation=True,
                                    reference_station_id='best', eligible_candidate_count=3)])
    ranking = pd.DataFrame([dict(event_id='event', station_id=sid, service_type='CHARGING',
                                 reference_rank=i) for i, sid in enumerate(('best', 'second'), 1)])
    report = evaluate_predictions(predictions, references, ranking)
    score = report['baselines']['total_service_completion']
    assert score['overall_composite_agreement'] == dict(matches=0, total=1, rate=0.0)
    assert score['station_top1']['matches'] == 0
    assert score['common_pool_composite_top1']['matches'] == 1
    assert score['pairwise_common_pool'] == dict(matches=1, total=1, rate=1.0)
    assert report['mismatch_causes'] == {'RUNTIME_BEST_OUTSIDE_REFERENCE_POOL': 1}
    assert score['by_reference_group']['multiple']['station_top1']['matches'] == 0
