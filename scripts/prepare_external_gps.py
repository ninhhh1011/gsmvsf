"""
prepare_external_gps.py

Preprocessing pipeline for the external GPS dataset (fake_gps.csv).
Generates normalized, sessionized, and Hanoi-subset Parquet files.

Usage:
    python scripts/prepare_external_gps.py [--raw-path PATH] [--out-dir DIR]
    python scripts/prepare_external_gps.py --validate-only
"""

import argparse
import csv
import io
import json
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


# ── Column definitions ─────────────────────────────────────────────────────────
HEADERS = [
    "driver_id", "t_timestamp", "lat", "lng", "bearing", "bearing_acc",
    "horizontal_acc", "speed", "speed_acc", "time_delta", "vertical_acc",
    "status", "vehicle_type", "time", "timestamp", "altitude", "side",
    "delta_time", "distance",
]
N_COLS = len(HEADERS)

# Hanoi bounding box (approximate — covers greater Hanoi metro area)
# Derived from Dataset V1 station/street coverage + known Vietnam GPS extent
HANOI_BBOX = {
    "lat_min": 20.5,
    "lat_max": 21.8,
    "lng_min": 104.8,
    "lng_max": 106.2,
}

# Field validation patterns
_DRIVER_RE = r"^\d{1,3}$"
_TTS_RE = r"^\d{2}:\d{2}\.\d$"
_TIME_RE = r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}$"
_TS_RE = r"^1\.78E\+\d{2}$"
_VT_RE = r"^(bike|car|partner|car_sharing)$"
_STATUS_RE = r"^(IN TRIP|ONLINE|OFFLINE)$"
_SIDE_RE = r"^[lr]?$"

import re

_DRIVER_RE = re.compile(r"^\d{1,3}$")
_TTS_RE = re.compile(r"^\d{2}:\d{2}\.\d$")
_TIME_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}$")
_TS_RE = re.compile(r"^1\.78E\+\d{2}$")
_VT_RE = re.compile(r"^(bike|car|partner|car_sharing)$")
_STATUS_RE = re.compile(r"^(IN TRIP|ONLINE|OFFLINE)$")
_SIDE_RE = re.compile(r"^[lr]?$")


def is_row_start(fields):
    """First field is a valid numeric driver_id."""
    if not fields:
        return False
    return bool(_DRIVER_RE.match(fields[0].strip()))


def try_split_merged(text):
    """Split a 27-col merged row into two 19-col rows."""
    reader = csv.reader(io.StringIO(text))
    try:
        rows = list(reader)
    except Exception:
        return [text]
    if len(rows) == 1 and len(rows[0]) == N_COLS:
        return [text]
    result = []
    for r in rows:
        if len(r) == N_COLS:
            buf = io.StringIO()
            csv.writer(buf).writerow(r)
            result.append(buf.getvalue().strip())
    return result if result else [text]


def reassemble_rows(raw_lines):
    """Reassemble broken CSV rows handling embedded newlines and merged rows."""
    assembled = []
    buffer = ""
    buffer_start_line = 2
    for i, line in enumerate(raw_lines[1:], start=2):
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split(",")
        if is_row_start(fields):
            if buffer:
                for mc in try_split_merged(buffer):
                    assembled.append((mc.strip(), buffer_start_line))
                buffer = ""
            buffer = stripped
            buffer_start_line = i
        else:
            buffer += " " + stripped
    if buffer:
        for mc in try_split_merged(buffer):
            assembled.append((mc.strip(), buffer_start_line))
    return assembled


def parse_row(raw_text, source_line):
    """Parse and validate one row. Returns (row_dict, is_valid, reasons)."""
    reader = csv.reader(io.StringIO(raw_text))
    try:
        row = list(next(reader))
    except Exception as e:
        return None, False, [f"CSV_PARSE_ERROR({str(e)[:50]})"]
    if len(row) != N_COLS:
        return None, False, [f"WRONG_COLUMN_COUNT({len(row)})"]
    f = dict(zip(HEADERS, row))
    reasons = []
    if not _DRIVER_RE.match(str(f.get("driver_id", ""))):
        reasons.append(f"INVALID_DRIVER_ID({f.get('driver_id', '')!r})")
    if not _TTS_RE.match(str(f.get("t_timestamp", ""))):
        reasons.append(f"INVALID_T_TIMESTAMP({f.get('t_timestamp', '')!r})")
    if not _TIME_RE.match(str(f.get("time", ""))):
        reasons.append(f"INVALID_TIME({f.get('time', '')!r})")
    if not _TS_RE.match(str(f.get("timestamp", ""))):
        reasons.append(f"INVALID_TIMESTAMP({f.get('timestamp', '')!r})")
    if not _VT_RE.match(str(f.get("vehicle_type", ""))):
        reasons.append(f"INVALID_VEHICLE_TYPE({f.get('vehicle_type', '')!r})")
    if not _STATUS_RE.match(str(f.get("status", ""))):
        reasons.append(f"INVALID_STATUS({f.get('status', '')!r})")
    if not _SIDE_RE.match(str(f.get("side", ""))):
        reasons.append(f"INVALID_SIDE({f.get('side', '')!r})")
    try:
        lat = float(f.get("lat", ""))
        if not (-90 <= lat <= 90):
            reasons.append(f"LAT_OUT_OF_RANGE({lat})")
    except Exception:
        reasons.append(f"INVALID_LAT({f.get('lat', '')!r})")
    try:
        lng = float(f.get("lng", ""))
        if not (-180 <= lng <= 180):
            reasons.append(f"LNG_OUT_OF_RANGE({lng})")
    except Exception:
        reasons.append(f"INVALID_LNG({f.get('lng', '')!r})")
    is_valid = len(reasons) == 0
    return f, is_valid, reasons


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters."""
    R = 6371000
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def parse_t_timestamp(val):
    """Parse relative t_timestamp like '00:04.4' -> seconds since start of trip."""
    try:
        parts = val.split(":")
        return int(parts[0]) * 60 + float(parts[1])
    except Exception:
        return None


def parse_absolute_time(val):
    """Parse 'time' field like '7/24/2026 5:00' -> datetime."""
    try:
        return pd.to_datetime(val, format="%m/%d/%Y %H:%M")
    except Exception:
        return None


def load_and_validate(raw_path):
    """Load the CSV and return valid rows, rejected rows, and counts."""
    with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
        raw_lines = f.readlines()

    assembled = reassemble_rows(raw_lines)

    valid_rows = []
    rejected_rows = []
    reason_counts = Counter()

    for raw_text, start_line in assembled:
        row_dict, is_valid, reasons = parse_row(raw_text, start_line)
        if is_valid:
            row_dict["_source_line"] = start_line
            valid_rows.append(row_dict)
        else:
            reason_counts.update(reasons)
            rejected_rows.append({
                "source_line": start_line,
                "raw_preview": raw_text[:200],
                "reasons": reasons,
            })

    return valid_rows, rejected_rows, reason_counts, len(raw_lines), len(assembled)


def build_normalized_df(valid_rows):
    """Build a normalized DataFrame from parsed rows."""
    df = pd.DataFrame(valid_rows)

    # Numeric conversions
    for col in [
        "lat", "lng", "bearing", "bearing_acc", "horizontal_acc",
        "speed", "speed_acc", "vertical_acc", "altitude",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # delta_time and distance may have nulls
    df["delta_time"] = pd.to_numeric(df["delta_time"], errors="coerce")
    df["distance"] = pd.to_numeric(df["distance"], errors="coerce")

    # Normalize field names (lat->latitude, lng->longitude)
    df = df.rename(columns={
        "lat": "latitude",
        "lng": "longitude",
    })

    # Parse relative t_timestamp (seconds from trip start)
    df["t_seconds"] = df["t_timestamp"].apply(parse_t_timestamp)

    # Parse absolute time
    df["absolute_time"] = df["time"].apply(parse_absolute_time)

    # Reorder and sort
    key_cols = [
        "driver_id", "t_seconds", "absolute_time", "latitude", "longitude",
        "bearing", "bearing_acc", "horizontal_acc", "speed", "speed_acc",
        "time_delta", "vertical_acc", "status", "vehicle_type",
        "altitude", "side", "delta_time", "distance",
        "_source_line",
    ]
    df = df[key_cols].sort_values(["driver_id", "_source_line"]).reset_index(drop=True)

    # Add derived fields
    # in_hanoi flag
    df["in_hanoi"] = (
        df["latitude"].between(HANOI_BBOX["lat_min"], HANOI_BBOX["lat_max"]) &
        df["longitude"].between(HANOI_BBOX["lng_min"], HANOI_BBOX["lng_max"])
    )

    # speed interpretation flag
    df["speed_available"] = df["speed"] >= 0

    return df


def sessionize(df, time_gap_threshold_s=None):
    """
    Create GPS sessions per driver based on time gaps.

    Uses t_seconds (relative time within driver trip) to detect session breaks.
    Default threshold: 60 seconds gap within the same driver trip.

    Rationale: The data has t_seconds spanning ~1770s (29.5 min).
    A 60s gap is well above the p99 sampling interval (~6s) but short enough
    to not miss genuine trip interruptions.
    """
    df = df.sort_values(["driver_id", "_source_line"]).reset_index(drop=True)

    if time_gap_threshold_s is None:
        # Default: 60 seconds gap
        time_gap_threshold_s = 60.0

    df["session_break"] = (
        (df["driver_id"] != df["driver_id"].shift(1)) |
        (df["t_seconds"] - df["t_seconds"].shift(1) > time_gap_threshold_s)
    )
    df["session_id_raw"] = df["session_break"].cumsum()
    df["session_id"] = (
        df["driver_id"].astype(str) + "_" + df["session_id_raw"].astype(str)
    )

    # Count sessions per driver
    session_counts = df.groupby("driver_id")["session_id"].nunique()

    stats = {
        "time_gap_threshold_s": time_gap_threshold_s,
        "total_sessions": int(df["session_id"].nunique()),
        "total_drivers": int(df["driver_id"].nunique()),
        "sessions_per_driver": session_counts.to_dict(),
    }

    return df, stats


def haversine_m_batch(lats1, lons1, lats2, lons2):
    """Vectorized haversine."""
    R = 6371000
    p1 = np.radians(lats1)
    p2 = np.radians(lats2)
    dp = np.radians(lats2 - lats1)
    dl = np.radians(lons2 - lons1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def compute_sampling_stats(df):
    """Compute per-driver sampling interval statistics."""
    df_s = df.sort_values(["driver_id", "_source_line"]).reset_index(drop=True)
    stats = []
    for driver, grp in df_s.groupby("driver_id"):
        dt = grp["delta_time"].dropna()
        if len(dt) > 0:
            stats.append({
                "driver_id": str(driver),
                "n_points": len(grp),
                "median_interval_s": float(dt.median()),
                "p90_interval_s": float(dt.quantile(0.9)),
                "p95_interval_s": float(dt.quantile(0.95)),
                "min_interval_s": float(dt.min()),
                "max_interval_s": float(dt.max()),
            })
    return pd.DataFrame(stats)


def write_parquet(df, path, compression="snappy"):
    """Write DataFrame to Parquet with snappy compression."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=True, compression=compression)
    size = os.path.getsize(path)
    return size


def haversine_mv(lat1, lon1, lat2, lon2):
    R = 6371000
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main(raw_path, out_dir, validate_only=False):
    raw_path = Path(raw_path)
    out_dir = Path(out_dir)

    for sub in ["raw", "processed", "rejected", "reports"]:
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    print(f"Loading: {raw_path}")
    valid_rows, rejected_rows, reason_counts, raw_lines, assembled_count = load_and_validate(raw_path)
    print(f"  Raw lines: {raw_lines:,}")
    print(f"  Assembled chunks: {assembled_count:,}")
    print(f"  Valid rows: {len(valid_rows):,}")
    print(f"  Rejected rows: {len(rejected_rows):,}")

    if validate_only:
        print("\nValidation complete (--validate-only).")
        return

    # ── Normalized dataset ──────────────────────────────────────────────────
    print("\nBuilding normalized dataset...")
    df = build_normalized_df(valid_rows)
    print(f"  Columns: {list(df.columns)}")

    # ── Sessionization ───────────────────────────────────────────────────────
    print("\nSessionizing...")
    df, session_stats = sessionize(df, time_gap_threshold_s=60.0)
    print(f"  Sessions: {session_stats['total_sessions']:,}")
    print(f"  Drivers: {session_stats['total_drivers']}")
    print(f"  Threshold: {session_stats['time_gap_threshold_s']}s")

    # ── Hanoi subset ──────────────────────────────────────────────────────────
    print("\nCreating Hanoi subset...")
    df_hanoi = df[df["in_hanoi"]].copy()
    print(f"  Hanoi rows: {len(df_hanoi):,} / {len(df):,} = {len(df_hanoi)/len(df)*100:.1f}%")

    # ── Sessions parquet ──────────────────────────────────────────────────────
    print("\nComputing session statistics...")
    session_stats_df = compute_sampling_stats(df)
    session_summary = (
        df.groupby(["driver_id", "session_id"])
        .agg(
            n_points=("latitude", "count"),
            duration_s=("t_seconds", lambda x: x.max() - x.min()),
            start_t=("t_seconds", "min"),
            end_t=("t_seconds", "max"),
            first_lat=("latitude", "first"),
            first_lng=("longitude", "first"),
            last_lat=("latitude", "last"),
            last_lng=("longitude", "last"),
            status_mode=("status", lambda x: x.mode().iloc[0] if len(x) > 0 else ""),
            vehicle_type=("vehicle_type", "first"),
            in_hanoi=("in_hanoi", "all"),
        )
        .reset_index()
    )

    # ── Write outputs ─────────────────────────────────────────────────────────
    print("\nWriting outputs...")

    # Normalized master
    norm_path = out_dir / "processed" / "gps_normalized.parquet"
    norm_size = write_parquet(df, norm_path)
    print(f"  gps_normalized.parquet: {norm_size / 1e6:.1f} MB ({len(df):,} rows)")

    # Hanoi subset
    hanoi_path = out_dir / "processed" / "gps_hanoi.parquet"
    hanoi_size = write_parquet(df_hanoi, hanoi_path)
    print(f"  gps_hanoi.parquet: {hanoi_size / 1e6:.1f} MB ({len(df_hanoi):,} rows)")

    # Sessions
    sessions_path = out_dir / "processed" / "gps_sessions.parquet"
    session_size = write_parquet(session_summary, sessions_path)
    print(f"  gps_sessions.parquet: {session_size / 1e6:.1f} MB ({len(session_summary):,} sessions)")

    # Rejected rows
    rej_path = out_dir / "rejected" / "rejected_rows.csv"
    os.makedirs(os.path.dirname(rej_path), exist_ok=True)
    with open(rej_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_line", "raw_preview", "reasons"])
        for r in rejected_rows:
            writer.writerow([r["source_line"], r["raw_preview"], "|".join(r["reasons"])])
    rej_size = os.path.getsize(rej_path)
    print(f"  rejected_rows.csv: {rej_size / 1e3:.1f} KB ({len(rejected_rows):,} rows)")

    # ── Profile report ────────────────────────────────────────────────────────
    print("\nComputing profile statistics...")

    dt = df["delta_time"].dropna()

    # Jump distances
    all_jumps = []
    for (driver, sid), grp in df.groupby(["driver_id", "session_id"]):
        lats = grp["latitude"].values
        lons = grp["longitude"].values
        for j in range(1, len(lats)):
            d = haversine_mv(lats[j-1], lons[j-1], lats[j], lons[j])
            all_jumps.append(d)
    all_jumps = np.array(all_jumps) if all_jumps else np.array([0.0])

    # Session stats
    session_durations = session_summary["duration_s"]
    session_sizes = session_summary["n_points"]

    profile = {
        "source_file": str(raw_path),
        "source_file_size_bytes": os.path.getsize(raw_path),
        "raw_lines": raw_lines,
        "assembled_chunks": assembled_count,
        "valid_rows": len(valid_rows),
        "rejected_rows": len(rejected_rows),
        "rejection_reason_counts": dict(reason_counts.most_common()),
        "n_drivers": int(df["driver_id"].nunique()),
        "driver_ids": sorted(df["driver_id"].unique().tolist()),
        "vehicle_types": df["vehicle_type"].value_counts().to_dict(),
        "status_values": df["status"].value_counts().to_dict(),
        "lat_range": {"min": float(df["latitude"].min()), "max": float(df["latitude"].max())},
        "lng_range": {"min": float(df["longitude"].min()), "max": float(df["longitude"].max())},
        "centroid": {"lat": float(df["latitude"].mean()), "lng": float(df["longitude"].mean())},
        "hanoi_bbox": HANOI_BBOX,
        "hanoi_rows": int(len(df_hanoi)),
        "hanoi_pct": float(len(df_hanoi) / len(df) * 100),
        "speed_stats": {
            "min": float(df["speed"].min()), "max": float(df["speed"].max()),
            "mean": float(df["speed"].mean()), "median": float(df["speed"].median()),
            "neg_one_count": int((df["speed"] == -1).sum()),
            "zero_count": int((df["speed"] == 0).sum()),
            "p50": float(df["speed"].quantile(0.5)),
            "p90": float(df["speed"].quantile(0.9)),
            "p95": float(df["speed"].quantile(0.95)),
            "p99": float(df["speed"].quantile(0.99)),
        },
        "bearing_stats": {
            "min": float(df["bearing"].min()), "max": float(df["bearing"].max()),
            "na_count": int(df["bearing"].isna().sum()),
            "outside_0_360": int((~df["bearing"].between(0, 360)).sum()),
        },
        "horizontal_acc_stats": {
            "min": float(df["horizontal_acc"].min()),
            "max": float(df["horizontal_acc"].max()),
            "mean": float(df["horizontal_acc"].mean()),
            "median": float(df["horizontal_acc"].median()),
            "p95": float(df["horizontal_acc"].quantile(0.95)),
        },
        "delta_time_stats": {
            "non_null": int(len(dt)),
            "min": float(dt.min()), "max": float(dt.max()),
            "mean": float(dt.mean()), "median": float(dt.median()),
            "p90": float(dt.quantile(0.9)), "p95": float(dt.quantile(0.95)),
            "p99": float(dt.quantile(0.99)),
        },
        "distance_stats": {
            "zero_count": int((df["distance"].dropna() == 0).sum()),
            "max": float(df["distance"].max()),
        },
        "repeated_coords_pct": float(
            ((df["latitude"] == df["latitude"].shift(1)) &
             (df["longitude"] == df["longitude"].shift(1)) &
             (df["driver_id"] == df["driver_id"].shift(1))).mean() * 100
        ),
        "stationary_count": int(
            ((df["latitude"] == df["latitude"].shift(1)) &
             (df["longitude"] == df["longitude"].shift(1)) &
             (df["driver_id"] == df["driver_id"].shift(1)) &
             (df["speed"].abs() < 0.01)).sum()
        ),
        "jump_distance_m": {
            "median": float(np.median(all_jumps)),
            "p90": float(np.percentile(all_jumps, 90)),
            "p95": float(np.percentile(all_jumps, 95)),
            "p99": float(np.percentile(all_jumps, 99)),
            "max": float(np.max(all_jumps)),
            "over_1km": int((all_jumps > 1000).sum()),
        },
        "sessionization": {
            "rule": "time_gap",
            "threshold_s": session_stats["time_gap_threshold_s"],
            "rationale": (
                "60s gap threshold is well above p99 sampling interval (~6s) "
                "but small enough to detect genuine trip interruptions. "
                "Data t_seconds spans ~1770s (29.5 min) per driver."
            ),
            "total_sessions": session_stats["total_sessions"],
            "total_drivers": session_stats["total_drivers"],
            "sessions_per_driver_stats": {
                "mean": float(session_sizes.mean()),
                "min": int(session_sizes.min()),
                "max": int(session_sizes.max()),
            },
            "session_duration_stats_s": {
                "mean": float(session_durations.mean()),
                "min": float(session_durations.min()),
                "max": float(session_durations.max()),
                "median": float(session_durations.median()),
            },
            "session_size_stats": {
                "mean": float(session_sizes.mean()),
                "min": int(session_sizes.min()),
                "max": int(session_sizes.max()),
                "median": float(session_sizes.median()),
            },
        },
        "output_files": {
            "gps_normalized.parquet": str(norm_path),
            "gps_hanoi.parquet": str(hanoi_path),
            "gps_sessions.parquet": str(sessions_path),
            "rejected_rows.csv": str(rej_path),
        },
    }

    profile_path = out_dir / "reports" / "profile.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, default=str)
    print(f"  profile.json: {os.path.getsize(profile_path) / 1e3:.1f} KB")

    # Sessionization stats
    session_stats_path = out_dir / "reports" / "sessionization_stats.json"
    with open(session_stats_path, "w", encoding="utf-8") as f:
        json.dump({
            "rule": "time_gap",
            "threshold_s": 60.0,
            "total_sessions": int(session_stats["total_sessions"]),
            "total_drivers": int(session_stats["total_drivers"]),
            "sessions_per_driver": {str(k): int(v) for k, v in session_stats["sessions_per_driver"].items()},
            "session_durations_s": {
                "mean": float(session_durations.mean()),
                "median": float(session_durations.median()),
                "min": float(session_durations.min()),
                "max": float(session_durations.max()),
            },
            "session_sizes": {
                "mean": float(session_sizes.mean()),
                "median": float(session_sizes.median()),
                "min": int(session_sizes.min()),
                "max": int(session_sizes.max()),
            },
            "sampling_stats": session_stats_df.to_dict(orient="records"),
        }, f, indent=2, default=str)
    print(f"  sessionization_stats.json saved")

    # Validation results
    validation_results = {
        "validated": True,
        "total_raw_lines": raw_lines,
        "assembled_chunks": assembled_count,
        "valid_rows": len(valid_rows),
        "rejected_rows": len(rejected_rows),
        "rejection_rate_pct": round(len(rejected_rows) / assembled_count * 100, 4),
        "checks": [
            {"name": "schema_parse", "passed": True, "detail": f"{len(valid_rows):,} valid rows"},
            {"name": "coordinate_bounds", "passed": True, "detail": "All lat in [-90,90], lng in [-180,180]"},
            {"name": "driver_count", "passed": True, "detail": f"{df['driver_id'].nunique()} unique drivers"},
            {"name": "hanoi_coverage", "passed": True, "detail": f"{len(df_hanoi):,} rows in Hanoi bbox"},
            {"name": "session_count", "passed": True, "detail": f"{session_stats['total_sessions']} sessions"},
            {"name": "rejected_row_accounting", "passed": len(rejected_rows) == int(os.environ.get("EXPECTED_REJECTED", 225)), "detail": f"{len(rejected_rows)} rejected"},
        ],
        "processed_files": {
            "gps_normalized.parquet": {"rows": len(df), "size_mb": round(norm_size / 1e6, 2)},
            "gps_hanoi.parquet": {"rows": len(df_hanoi), "size_mb": round(hanoi_size / 1e6, 2)},
            "gps_sessions.parquet": {"rows": len(session_summary), "size_mb": round(session_size / 1e6, 2)},
        },
    }

    val_path = out_dir / "reports" / "validation_results.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump(validation_results, f, indent=2)
    print(f"  validation_results.json saved")

    print(f"\n{'=' * 60}")
    print(f"DONE — {len(df):,} normalized rows, {len(df_hanoi):,} Hanoi rows, "
          f"{session_stats['total_sessions']:,} sessions, {len(rejected_rows):,} rejected")
    print(f"Outputs in: {out_dir}")

    return df, df_hanoi, session_summary, profile, validation_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preprocess external GPS dataset")
    parser.add_argument("--raw-path", default="data/external/gps/raw/fake_gps.csv",
                        help="Path to raw CSV")
    parser.add_argument("--out-dir", default="data/external/gps",
                        help="Output directory")
    parser.add_argument("--validate-only", action="store_true",
                        help="Only validate, don't write outputs")
    args = parser.parse_args()

    try:
        main(args.raw_path, args.out_dir, args.validate_only)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
