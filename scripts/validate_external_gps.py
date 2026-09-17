"""
validate_external_gps.py

Reusable validator for the external GPS processed datasets.

Usage:
    python scripts/validate_external_gps.py [--data-dir DIR]
    python scripts/validate_external_gps.py  # defaults to data/external/gps
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path("data/external/gps")


def validate_profile(profile_path):
    """Validate the profile.json file."""
    with open(profile_path) as f:
        profile = json.load(f)

    checks = []
    passed = True

    # Check valid row count
    ok = profile["valid_rows"] == 399759
    checks.append({
        "name": "valid_row_count",
        "passed": ok,
        "detail": f"expected 399759, got {profile['valid_rows']}"
    })
    passed &= ok

    # Check rejection rate < 1%
    rate = profile["rejected_rows"] / profile["assembled_chunks"] * 100
    ok = rate < 1.0
    checks.append({
        "name": "rejection_rate",
        "passed": ok,
        "detail": f"rejection rate {rate:.3f}% < 1%"
    })
    passed &= ok

    # Check coordinate bounds
    ok = (-90 <= profile["lat_range"]["min"] <= 90 and
          -90 <= profile["lat_range"]["max"] <= 90)
    checks.append({"name": "lat_range", "passed": ok, "detail": str(profile["lat_range"])})
    passed &= ok

    ok = (-180 <= profile["lng_range"]["min"] <= 180 and
          -180 <= profile["lng_range"]["max"] <= 180)
    checks.append({"name": "lng_range", "passed": ok, "detail": str(profile["lng_range"])})
    passed &= ok

    # Check Hanoi coverage
    ok = profile["hanoi_pct"] > 50.0
    checks.append({
        "name": "hanoi_coverage",
        "passed": ok,
        "detail": f"{profile['hanoi_pct']:.1f}% > 50%"
    })
    passed &= ok

    # Check driver count
    ok = profile["n_drivers"] >= 100
    checks.append({
        "name": "driver_count",
        "passed": ok,
        "detail": f"{profile['n_drivers']} drivers >= 100"
    })
    passed &= ok

    # Check sessionization
    sess = profile.get("sessionization", {})
    ok = sess.get("total_sessions", 0) > 0
    checks.append({
        "name": "session_count",
        "passed": ok,
        "detail": f"{sess.get('total_sessions')} sessions"
    })
    passed &= ok

    ok = sess.get("threshold_s") == 60.0
    checks.append({
        "name": "session_threshold",
        "passed": ok,
        "detail": f"threshold={sess.get('threshold_s')}s"
    })
    passed &= ok

    return passed, checks


def validate_normalized(parquet_path):
    """Validate the gps_normalized.parquet file."""
    df = pd.read_parquet(parquet_path)
    checks = []
    passed = True

    # Check row count
    ok = len(df) == 399759
    checks.append({"name": "row_count", "passed": ok, "detail": f"{len(df)} rows"})
    passed &= ok

    # Check columns exist
    required_cols = ["driver_id", "latitude", "longitude", "bearing",
                     "horizontal_acc", "speed", "status", "vehicle_type",
                     "t_seconds", "in_hanoi", "_source_line"]
    for col in required_cols:
        ok = col in df.columns
        checks.append({"name": f"col_{col}", "passed": ok, "detail": col})
        passed &= ok

    # Check coordinates
    ok = df["latitude"].between(-90, 90).all()
    checks.append({"name": "lat_bounds", "passed": ok, "detail": "all lat in [-90,90]"})
    passed &= ok

    ok = df["longitude"].between(-180, 180).all()
    checks.append({"name": "lng_bounds", "passed": ok, "detail": "all lng in [-180,180]"})
    passed &= ok

    # Check no NaN in key fields
    ok = df["driver_id"].notna().all()
    checks.append({"name": "driver_id_notnull", "passed": ok, "detail": "no null driver_id"})
    passed &= ok

    ok = df["latitude"].notna().all()
    checks.append({"name": "lat_notnull", "passed": ok, "detail": "no null lat"})
    passed &= ok

    ok = df["longitude"].notna().all()
    checks.append({"name": "lng_notnull", "passed": ok, "detail": "no null lng"})
    passed &= ok

    # Check sorted order
    ok = df.equals(df.sort_values(["driver_id", "_source_line"]).reset_index(drop=True))
    checks.append({"name": "sort_order", "passed": ok, "detail": "sorted by driver_id, source_line"})
    passed &= ok

    # Check vehicle types
    valid_vt = {"car", "bike", "partner", "car_sharing"}
    ok = set(df["vehicle_type"].unique()).issubset(valid_vt)
    checks.append({
        "name": "vehicle_types",
        "passed": ok,
        "detail": f"vehicle_types={sorted(df['vehicle_type'].unique())}"
    })
    passed &= ok

    # Check status values
    valid_status = {"IN TRIP", "ONLINE", "OFFLINE"}
    ok = set(df["status"].unique()).issubset(valid_status)
    checks.append({
        "name": "status_values",
        "passed": ok,
        "detail": f"status={sorted(df['status'].unique())}"
    })
    passed &= ok

    # Check source traceability
    ok = "_source_line" in df.columns
    checks.append({"name": "source_traceability", "passed": ok, "detail": "_source_line present"})
    passed &= ok

    return passed, checks, df


def validate_hanoi(hanoi_path, normalized_path):
    """Validate the gps_hanoi.parquet file."""
    df_h = pd.read_parquet(hanoi_path)
    df_n = pd.read_parquet(normalized_path)
    checks = []
    passed = True

    # Check Hanoi subset is subset of normalized
    h_ids = set(zip(df_h["driver_id"], df_h["_source_line"]))
    n_ids = set(zip(df_n["driver_id"], df_n["_source_line"]))
    ok = h_ids.issubset(n_ids)
    checks.append({"name": "subset_of_normalized", "passed": ok, "detail": f"{len(h_ids)} rows subset of {len(n_ids)}"})
    passed &= ok

    # Check all in_hanoi=True
    ok = df_h["in_hanoi"].all()
    checks.append({"name": "all_in_hanoi", "passed": ok, "detail": "all rows have in_hanoi=True"})
    passed &= ok

    # Check row count
    expected = int(df_n["in_hanoi"].sum())
    ok = len(df_h) == expected
    checks.append({
        "name": "row_count",
        "passed": ok,
        "detail": f"{len(df_h)} rows, expected {expected}"
    })
    passed &= ok

    # Check Hanoi bbox coverage
    ok = (
        df_h["latitude"].between(20.5, 21.8).all() and
        df_h["longitude"].between(104.8, 106.2).all()
    )
    checks.append({"name": "hanoi_bbox", "passed": ok, "detail": "all within bbox"})
    passed &= ok

    return passed, checks


def validate_sessions(sessions_path, normalized_path):
    """Validate the gps_sessions.parquet file."""
    df_s = pd.read_parquet(sessions_path)
    df_n = pd.read_parquet(normalized_path)
    checks = []
    passed = True

    # Check sessions have expected columns
    required = ["driver_id", "session_id", "n_points", "duration_s",
                "start_t", "end_t", "vehicle_type", "in_hanoi"]
    for col in required:
        ok = col in df_s.columns
        checks.append({"name": f"col_{col}", "passed": ok, "detail": col})
        passed &= ok

    # Check each session is a subset of normalized
    all_session_ids = df_s["session_id"].unique()
    ok = len(all_session_ids) > 0
    checks.append({
        "name": "nonempty_sessions",
        "passed": ok,
        "detail": f"{len(all_session_ids)} sessions"
    })
    passed &= ok

    # Check session_id is driver_id + "_" + number
    ok = all("_" in str(sid) for sid in all_session_ids)
    checks.append({"name": "session_id_format", "passed": ok, "detail": "all contain '_'"})
    passed &= ok

    # Check session observations sum to normalized rows
    total_obs = df_s["n_points"].sum()
    ok = total_obs == len(df_n)
    checks.append({
        "name": "observation_sum",
        "passed": ok,
        "detail": f"sum={total_obs} normalized={len(df_n)}"
    })
    passed &= ok

    return passed, checks


def validate_rejected(rejected_path):
    """Validate the rejected_rows.csv file."""
    df = pd.read_csv(rejected_path)
    checks = []
    passed = True

    # Check expected columns
    for col in ["source_line", "raw_preview", "reasons"]:
        ok = col in df.columns
        checks.append({"name": f"col_{col}", "passed": ok, "detail": col})
        passed &= ok

    # Check count
    ok = len(df) == 225
    checks.append({
        "name": "row_count",
        "passed": ok,
        "detail": f"{len(df)} rejected rows (expected 225)"
    })
    passed &= ok

    return passed, checks


def validate_output_files(data_dir):
    """Check that all expected output files exist."""
    checks = []
    passed = True

    expected = {
        "processed/gps_normalized.parquet": "parquet",
        "processed/gps_hanoi.parquet": "parquet",
        "processed/gps_sessions.parquet": "parquet",
        "rejected/rejected_rows.csv": "csv",
        "reports/profile.json": "json",
        "reports/validation_results.json": "json",
        "reports/sessionization_stats.json": "json",
    }

    for rel_path, fmt in expected.items():
        full_path = data_dir / rel_path
        ok = full_path.exists()
        checks.append({
            "name": f"file_exists_{rel_path.replace('/', '_')}",
            "passed": ok,
            "detail": str(full_path)
        })
        passed &= ok
        if ok and fmt == "parquet":
            size_mb = full_path.stat().st_size / 1e6
            ok2 = size_mb > 0
            checks.append({
                "name": f"file_size_{rel_path.replace('/', '_')}",
                "passed": ok2,
                "detail": f"{size_mb:.2f} MB"
            })
            passed &= ok2

    return passed, checks


def run(data_dir=None):
    if data_dir is None:
        data_dir = DATA_DIR
    else:
        data_dir = Path(data_dir)

    print(f"Validating: {data_dir}")
    print("=" * 60)

    all_checks = []
    all_passed = True

    # File existence
    passed, checks = validate_output_files(data_dir)
    all_checks.extend(checks)
    all_passed &= passed
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['name']}: {c['detail']}")

    # Profile
    profile_path = data_dir / "reports" / "profile.json"
    if profile_path.exists():
        passed, checks = validate_profile(profile_path)
        all_checks.extend(checks)
        all_passed &= passed
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['name']}: {c['detail']}")

    # Normalized
    norm_path = data_dir / "processed" / "gps_normalized.parquet"
    if norm_path.exists():
        passed, checks, df_n = validate_normalized(norm_path)
        all_checks.extend(checks)
        all_passed &= passed
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['name']}: {c['detail']}")

    # Hanoi
    hanoi_path = data_dir / "processed" / "gps_hanoi.parquet"
    if hanoi_path.exists() and norm_path.exists():
        passed, checks = validate_hanoi(hanoi_path, norm_path)
        all_checks.extend(checks)
        all_passed &= passed
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['name']}: {c['detail']}")

    # Sessions
    sessions_path = data_dir / "processed" / "gps_sessions.parquet"
    if sessions_path.exists() and norm_path.exists():
        passed, checks = validate_sessions(sessions_path, norm_path)
        all_checks.extend(checks)
        all_passed &= passed
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['name']}: {c['detail']}")

    # Rejected
    rej_path = data_dir / "rejected" / "rejected_rows.csv"
    if rej_path.exists():
        passed, checks = validate_rejected(rej_path)
        all_checks.extend(checks)
        all_passed &= passed
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  [{status}] {c['name']}: {c['detail']}")

    # Write results
    # Serialize checks with native Python types
    serialized_checks = []
    for c in all_checks:
        serialized_checks.append({
            "name": str(c["name"]),
            "passed": bool(c["passed"]),
            "detail": str(c["detail"]),
        })

    results = {
        "validated": bool(all_passed),
        "total_checks": int(len(all_checks)),
        "passed_checks": int(sum(1 for c in all_checks if c["passed"])),
        "failed_checks": int(sum(1 for c in all_checks if not c["passed"])),
        "checks": serialized_checks,
    }

    out_path = data_dir / "reports" / "validation_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print("=" * 60)
    passed_count = sum(1 for c in all_checks if c["passed"])
    total = len(all_checks)
    print(f"RESULT: {passed_count}/{total} checks passed")
    print(f"OUTPUT: {out_path}")

    return all_passed, results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate external GPS processed data")
    parser.add_argument("--data-dir", default="data/external/gps",
                        help="Data directory")
    args = parser.parse_args()

    passed, results = run(args.data_dir)
    sys.exit(0 if passed else 1)
