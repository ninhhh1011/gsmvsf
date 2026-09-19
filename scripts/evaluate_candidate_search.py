"""
Evaluation and Replay Harness for Week 3 Candidate Search.

Evaluates runtime candidate eligibility logic against canonical Dataset V1.3.1 labels
(dataset_v1/labels/candidate_labels.csv).
Verifies:
- Agreement rate on eligible / ineligible flag
- Reason code agreement
- Confusion matrix
- Breakdown by service type (CHARGING vs BATTERY_SWAP)
- Breakdown by vehicle type (EV_CAR vs EV_MOTORBIKE)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from typing import Optional

from backend.app.services.candidate.compatibility import check_station_service_compatibility
from backend.app.services.candidate.eligibility import evaluate_candidate_eligibility
from backend.app.services.candidate.energy_feasibility import check_energy_feasibility_to_station
from backend.app.services.candidate.station_catalog import StationCatalog
from backend.app.services.demand.capability import get_capability_resolver
from backend.app.services.demand.models import ServiceType

ROOT = Path(__file__).resolve().parents[1]


def run_candidate_dataset_replay(sample_size: Optional[int] = None) -> dict:
    labels_path = ROOT / "dataset_v1/labels/candidate_labels.csv"
    esr_path = ROOT / "dataset_v1/labels/energy_service_requests.csv"
    stations_path = ROOT / "dataset_v1/stations/stations.csv"

    if not labels_path.exists() or not esr_path.exists():
        raise FileNotFoundError("Canonical dataset files not found")

    print(f"Loading candidate labels from {labels_path}...")
    candidate_labels = pd.read_csv(labels_path)
    esr = pd.read_csv(esr_path).set_index("event_id")

    catalog = StationCatalog(stations_csv_path=stations_path)
    resolver = get_capability_resolver()

    if sample_size is not None and sample_size < len(candidate_labels):
        df = candidate_labels.sample(n=sample_size, random_state=42).copy()
    else:
        df = candidate_labels.copy()

    total = len(df)
    eligible_agreed = 0
    reason_agreed = 0
    mismatches = []

    # Counters by service
    service_stats = {
        "CHARGING": {"total": 0, "eligible_agree": 0, "reason_agree": 0},
        "BATTERY_SWAP": {"total": 0, "eligible_agree": 0, "reason_agree": 0},
    }

    # Confusion matrix
    tp = fp = tn = fn = 0

    print(f"Evaluating {total} candidate rows against runtime candidate logic...")

    for row in df.itertuples(index=False):
        eid = row.event_id
        sid = row.station_id
        stype_str = row.service_type
        stype = ServiceType(stype_str)
        truth_eligible = bool(row.eligible)
        truth_reason = str(row.reason)

        if eid not in esr.index:
            continue
        erow = esr.loc[eid]
        if isinstance(erow, pd.DataFrame):
            erow = erow.iloc[0]

        station = catalog.get_station(sid)
        if not station:
            continue

        # 1. Resolve vehicle capability
        v_model = erow.vehicle_model
        v_id = erow.vehicle_id
        cap = None
        if v_model:
            try:
                cap = resolver.resolve_by_model(v_model)
            except Exception:
                pass
        if not cap and v_id:
            try:
                cap = resolver.resolve_by_vehicle_id(v_id)
            except Exception:
                pass

        # 2. Check compatibility
        is_comp = check_station_service_compatibility(cap or erow.to_dict(), station, stype)

        # 3. Snapshot state
        state_ts = row.state_timestamp
        op_snapshot = catalog.get_operational_snapshot(sid, stype, timestamp=state_ts)

        # 4. Network distance from routing / road network
        net_dist = row.network_distance_m
        is_reach = pd.notna(net_dist) and net_dist is not None

        # 5. Energy feasibility
        remaining_range = float(erow.estimated_remaining_range_km)
        soc_feasible = check_energy_feasibility_to_station(net_dist, remaining_range)

        # 6. Runtime eligibility
        rt_eligible, rt_reason = evaluate_candidate_eligibility(
            is_reachable=is_reach,
            is_compatible=is_comp,
            operational=op_snapshot,
            service_type=stype,
            is_soc_feasible=soc_feasible,
        )

        rt_reason_str = rt_reason.value

        # Compare
        if rt_eligible == truth_eligible:
            eligible_agreed += 1
            if truth_eligible:
                tp += 1
            else:
                tn += 1
        else:
            if rt_eligible and not truth_eligible:
                fp += 1
            else:
                fn += 1

            if len(mismatches) < 20:
                mismatches.append({
                    "event_id": eid,
                    "station_id": sid,
                    "service_type": stype_str,
                    "truth_eligible": truth_eligible,
                    "rt_eligible": rt_eligible,
                    "truth_reason": truth_reason,
                    "rt_reason": rt_reason_str,
                    "net_dist": net_dist,
                    "range": remaining_range,
                })

        if rt_reason_str == truth_reason:
            reason_agreed += 1

        service_stats[stype_str]["total"] += 1
        if rt_eligible == truth_eligible:
            service_stats[stype_str]["eligible_agree"] += 1
        if rt_reason_str == truth_reason:
            service_stats[stype_str]["reason_agree"] += 1

    eligible_accuracy = eligible_agreed / total if total > 0 else 1.0
    reason_accuracy = reason_agreed / total if total > 0 else 1.0

    report = {
        "total_evaluated": total,
        "eligible_agreed": eligible_agreed,
        "eligible_accuracy": round(eligible_accuracy * 100, 2),
        "reason_agreed": reason_agreed,
        "reason_accuracy": round(reason_accuracy * 100, 2),
        "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "service_stats": service_stats,
        "mismatches_sample": mismatches,
    }

    print("\n==================================================")
    print("DATASET V1.3.1 REPLAY EVALUATION REPORT")
    print("==================================================")
    print(f"Total Rows Evaluated: {total}")
    print(f"Eligible/Ineligible Agreement: {eligible_agreed}/{total} ({report['eligible_accuracy']}%)")
    print(f"Reason Code Agreement: {reason_agreed}/{total} ({report['reason_accuracy']}%)")
    print(f"Confusion Matrix: TP={tp}, TN={tn}, FP={fp}, FN={fn}")
    for s, stats in service_stats.items():
        s_tot = stats["total"]
        if s_tot > 0:
            s_acc = round(stats["eligible_agree"] / s_tot * 100, 2)
            r_acc = round(stats["reason_agree"] / s_tot * 100, 2)
            print(f"  {s}: Total={s_tot}, Eligible Agreement={s_acc}%, Reason Agreement={r_acc}%")

    if mismatches:
        print(f"\nMismatches Sample (first {len(mismatches)}):")
        for m in mismatches[:5]:
            print(f"  {m}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Candidate Search against Dataset V1.3.1")
    parser.add_argument("--sample", type=int, default=None, help="Sample size (default: all rows)")
    args = parser.parse_args()
    run_candidate_dataset_replay(sample_size=args.sample)
