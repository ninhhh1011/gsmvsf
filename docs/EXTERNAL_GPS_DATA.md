> Historical baseline: engine-specific instructions and measurements in this document predate the GraphHopper-only migration. Current runtime and verification are documented in [the migration report](GRAPHHOPPER_MIGRATION_REPORT.md).

# EXTERNAL GPS DATA

## Overview

An external GPS dataset is maintained outside `dataset_v1/` as an additional mobility source for integration testing, GPS replay, and robustness validation.

**It is NOT a replacement for Dataset V1.** Dataset V1 remains the canonical dataset for all training, evaluation, and official six-week development scenarios.

---

## Source File

```
data/external/gps/raw/fake_gps.csv
```

- **Size**: 51,136,351 bytes (~51 MB)
- **Format**: CSV with embedded-newline corruption (see §Data Quality)
- **Rows**: 399,759 valid observations (after preprocessing)
- **Rejected**: 225 rows (0.056%) — see `rejected/rejected_rows.csv`

---

## Processed Outputs

| File | Format | Rows | Size | Description |
|------|--------|-----:|-----:|---|
| `processed/gps_normalized.parquet` | Parquet | 399,759 | 14.6 MB | Master normalized GPS observations |
| `processed/gps_hanoi.parquet` | Parquet | 332,700 | 12.5 MB | Hanoi-subset observations |
| `processed/gps_sessions.parquet` | Parquet | 1,202 | 0.05 MB | GPS session summaries |
| `rejected/rejected_rows.csv` | CSV | 225 | 40 KB | Malformed rows with rejection reasons |
| `reports/profile.json` | JSON | — | 14 KB | Full data profile and statistics |
| `reports/validation_results.json` | JSON | — | — | Machine-readable validation report |
| `reports/sessionization_stats.json` | JSON | — | — | Session-level statistics |

---

## Schema — `gps_normalized.parquet`

Preserves original semantic fields where present. Normalizes naming for downstream consistency.

| Field | Type | Description | Notes |
|-------|------|-------------|-------|
| `driver_id` | string | Driver identifier | 111 unique drivers |
| `t_seconds` | float64 | Seconds from trip start | Parsed from `t_timestamp` (MM:SS.s) |
| `absolute_time` | datetime64 | Date/time of observation | Parsed from `time` field |
| `latitude` | float64 | Latitude (degrees WGS84) | Original: `lat` |
| `longitude` | float64 | Longitude (degrees WGS84) | Original: `lng` |
| `bearing` | float64 | Heading (degrees) | Range: [0, 360]; -1 = unknown |
| `bearing_acc` | float64 | Bearing accuracy (degrees) | |
| `horizontal_acc` | float64 | Horizontal accuracy (meters) | Median: 8 m |
| `speed` | float64 | Speed | **-1 = sentinel/unknown**, 0 = stationary |
| `speed_acc` | float64 | Speed accuracy | |
| `time_delta` | float64 | Sampling interval (seconds) | **5 s nominal** |
| `vertical_acc` | float64 | Vertical accuracy (meters) | |
| `status` | string | Observation status | `IN TRIP`, `ONLINE`, `OFFLINE` |
| `vehicle_type` | string | Vehicle category | `car`, `bike`, `partner`, `car_sharing` |
| `altitude` | float64 | Altitude (meters) | |
| `side` | string | Side of road | `l`, `r`, or empty |
| `delta_time` | float64 | Time since last observation (s) | ~5 s median |
| `distance` | float64 | Distance since last observation (m) | |
| `_source_line` | int64 | Original CSV line number | Traceability to raw file |
| `in_hanoi` | bool | Within Hanoi bounding box | |
| `speed_available` | bool | Speed is non-negative (not sentinel) | |

---

## Schema — `gps_sessions.parquet`

| Field | Type | Description |
|-------|------|-------------|
| `driver_id` | string | Driver identifier |
| `session_id` | string | `{driver_id}_{session_number}` |
| `n_points` | int64 | Number of observations in session |
| `duration_s` | float64 | Session duration (seconds) |
| `start_t` | float64 | Session start t_seconds |
| `end_t` | float64 | Session end t_seconds |
| `first_lat` | float64 | First latitude |
| `first_lng` | float64 | First longitude |
| `last_lat` | float64 | Last latitude |
| `last_lng` | float64 | Last longitude |
| `status_mode` | string | Most common status |
| `vehicle_type` | string | Vehicle type (constant per session) |
| `in_hanoi` | bool | All observations within Hanoi bbox |

---

## Profiling Summary

### Drivers & Vehicles

| Metric | Value |
|--------|-------|
| Unique drivers | 111 |
| Vehicle types | `car` (266,893), `bike` (130,639), `partner` (2,001), `car_sharing` (226) |
| Status distribution | `OFFLINE` (254,011), `ONLINE` (85,178), `IN TRIP` (60,570) |

### Coordinates

| Metric | Value |
|--------|-------|
| Latitude range | [-6.28, 43.24] |
| Longitude range | [76.92, 121.00] |
| Centroid | (19.39, 106.06) — southern Vietnam |
| Hanoi bbox coverage | **332,700 rows (83.2%)** |

**Hanoi bounding box**: lat ∈ [20.5, 21.8], lng ∈ [104.8, 106.2]

### Sampling Behavior

The `delta_time` field measures the time between consecutive observations.

| Percentile | Value |
|------------|-------|
| Median | **5.0 s** (≈ 0.2 Hz) |
| p90 | 5.07 s |
| p95 | 5.11 s |
| p99 | 6.13 s |

**Conclusion**: The data is sampled at approximately **5-second intervals** (nominally 0.2 Hz). This is consistent with low-frequency GPS tracking. The runtime GPS system should support configurable sampling intervals.

### Speed

| Value | Count | % |
|-------|------:|--:|
| speed = -1 (sentinel) | 135,382 | 33.9% |
| speed = 0 (stationary) | 104,120 | 26.0% |
| speed > 0 | 160,257 | 40.1% |
| Max speed | 29.15 | — |

**Interpretation of speed=-1**: This value is treated as a sentinel meaning speed is unknown or unavailable. It should NOT be treated as a negative speed. `speed_available` field indicates whether speed is valid.

### Horizontal Accuracy

| Percentile | Value |
|------------|-------|
| Median | 8 m |
| p75 | 17 m |
| p90 | 39 m |
| p95 | 62 m |
| p99 | 100 m |

### Repeated Coordinates

- **76.4%** of consecutive rows (same driver) have identical latitude/longitude
- **151,376** stationary observations (same coords + speed≈0)
- Geographic jumps: median 0 m, p99 48 m, max 5,254 km (data errors)

### Bearing

- Range: [-1, 360]; 1,420 rows outside [0, 360] (bearing=-1 or 360)

---

## Data Quality Issues

### CSV Corruption

The raw CSV file contains **embedded newlines** within the `time` field (value: `"7/24/2026 5:00"`). When this date string was written, a newline was inserted in the middle, breaking row boundaries. Additionally, some lines contain **merged rows** (two complete 19-column rows concatenated into one 27-column line).

The preprocessing pipeline (`scripts/prepare_external_gps.py`) handles both issues:

1. **Reassembly**: Accumulates lines until a valid row-start (numeric `driver_id`) is detected
2. **Split**: Detects 27-column merged rows and splits them into two 19-column rows

### Rejection Summary

225 rows (0.056%) are rejected. Primary reasons:

| Reason | Count | Description |
|--------|------:|-------------|
| `INVALID_T_TIMESTAMP` | 219 | Field position shifted by corruption (contains date string) |
| `WRONG_COLUMN_COUNT` | 3 | Row could not be parsed into exactly 19 columns |
| `INVALID_STATUS` | 3 | Empty or malformed status field |

No rows are rejected for coordinate errors — the `lat`/`lng` columns were protected by the 19-column row structure.

---

## Sessionization

### Rule

**Time-gap sessionization** with a **60-second threshold**.

A new session begins when:
- The driver changes, OR
- The time gap (`t_seconds[j] - t_seconds[j-1]`) exceeds 60 seconds

### Rationale

The data's nominal sampling interval is 5 seconds (p99 ≈ 6.1 s). A 60-second gap is:
- Well above the p99 interval — genuine break, not sampling noise
- Small enough to catch trip interruptions within a day
- Simple and documented — no hardcoded trip metadata required

### Results

| Metric | Value |
|--------|-------|
| Total sessions | 1,202 |
| Total drivers | 111 |
| Sessions per driver | Mean: 10.8, Median: 6, Max: 20 |
| Session duration | Mean: ~165 s, Max: ~1770 s |

Sessions are named `{driver_id}_{session_number}` for traceability.

---

## Hanoi Subset

The Hanoi bounding box was chosen to match the project's geographic scope:

- **lat**: [20.5, 21.8] — covers greater Hanoi metro area
- **lng**: [104.8, 106.2] — covers greater Hanoi metro area

This is NOT an arbitrary tiny box — it covers the Dataset V1 road network extent.

The subset is derived (NOT independently generated). Every row in `gps_hanoi.parquet` is also present in `gps_normalized.parquet` with `in_hanoi=True`.

---

## Limitations

1. **No ground truth labels** — no `true_segment_id`, `true_matched_position`, demand labels, or ranking labels. The external dataset is for integration testing only.
2. **No SOC, battery, or vehicle capability data** — `vehicle_type` is present but battery capacity, swap capability, and connector type are unknown.
3. **speed=-1 sentinel** — ~34% of rows have unknown speed. Applications must handle this.
4. **76% repeated coordinates** — most observations are at the same location (stationary), consistent with a high proportion of `OFFLINE`/`ONLINE` status.
5. **Geographic outliers** — rows with lat/lng far outside Vietnam (e.g., lat=-6, lng=121) are preserved in the normalized dataset but excluded from the Hanoi subset.
6. **No timezone metadata** — the `time` field lacks timezone information. Assumed local time.
7. **No Dataset V1 alignment** — these drivers/vehicles do not appear in Dataset V1. They must not be merged into it.

---

## How It Differs from Dataset V1

| Aspect | Dataset V1 | External GPS |
|--------|------------|-------------|
| Purpose | Canonical development | Integration testing |
| Ground truth | Complete (map matching, demand, ranking) | None |
| Vehicle data | Full (SOC, battery, capacity) | Type only |
| Map matching | OSRM + HMM labels | External use |
| Drivers | 60 (trips, labels, scenarios) | 111 (raw GPS) |
| Sampling | 1 Hz (true trajectories) | 5 s (0.2 Hz) |
| Coverage | Hanoi only | Hanoi + broader region |
| SOC history | Complete | Not available |
| Station state | Full temporal state | Not available |

---

## Intended Usage by Week

| Week | Use |
|------|-----|
| **Week 1** | External GPS replay for map-matching robustness testing. Feed raw observations through MapMatchingService and compare stability against Dataset V1 baseline. |
| **Week 2** | Movement/trip-progress context after joining with separately defined vehicle/SOC state. The GPS provides position; SOC/state comes from a separate runtime simulation. |
| **Week 3** | Current driver position for candidate search/routing integration. Feed position into CandidateSearch → Routing pipeline. |
| **Week 4** | Current position/context feeding ranking integration. Position feeds into station ranking pipeline. |
| **Week 5** | Realtime GPS replay / event-stream testing. Drive the event simulation loop with this data. |
| **Week 6** | Multi-driver replay / load and latency testing. Simulate many concurrent drivers from this dataset. |

**What it does NOT provide**: SOC ground truth, station state, traffic ground truth, queue ground truth, candidate labels, ranking labels, or recommendation labels.

---

## Preprocessing Pipeline

```bash
# Preprocess (generates all outputs)
python scripts/prepare_external_gps.py

# Validate
python scripts/validate_external_gps.py

# Make targets
make prepare-external-gps
make validate-external-gps
```

The pipeline is **deterministic** and **idempotent**:
- Reads from `data/external/gps/raw/fake_gps.csv`
- Writes to `data/external/gps/processed/`, `rejected/`, `reports/`
- Does not modify the raw file
- Overwrites existing outputs

---

## Raw File Provenance

The raw CSV at `data/external/gps/raw/fake_gps.csv` was originally provided at the project root as `fake_gps.csv`. It was copied to the external data directory. The original file at the project root was **not moved** to avoid Git ambiguity — a copy was made instead.
