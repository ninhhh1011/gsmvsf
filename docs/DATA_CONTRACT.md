# DATA_CONTRACT

**MAP STATUS — APPROVED:** `hanoi-patched.osm.pbf` is the primary GraphHopper map; OSM remains canonical map data. Contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì). `hanoi-baseline.osm.pbf` is reference.

## Dataset V1 Location

Dataset V1 is located at `./dataset_v1/` and is the canonical development dataset for the full six-week project.

**Dataset V1 is READ-ONLY during normal development.** Do not regenerate, patch, move, or alter files inside it.

## Dataset V1 Contents

### Map / Road Network

| File | Description |
|------|-------------|
| `map/raw/hanoi-baseline.osm.pbf` | Historical baseline OSM reference; not the active runtime map |
| `map/raw/hanoi-patched.osm.pbf` | Approved primary OSM PBF; immutable GraphHopper import source |
| `map/processed/road_nodes.csv.gz` | 339,441 topological road nodes |
| `map/processed/road_segments.csv.gz` | 701,407 directed road segments |

### GPS / Trajectories

| File | Description |
|------|-------------|
| `gps/gps_observations.csv.gz` | 65,847 noisy GPS observations |
| `trajectories/true_trajectories.csv.gz` | 68,664 ground-truth trajectory points |
| `labels/map_matching_labels.csv.gz` | Ground-truth segment/direction per GPS observation |

### Trips / Drivers / Vehicles

| File | Description |
|------|-------------|
| `drivers/drivers.csv` | 60 drivers |
| `vehicles/vehicles.csv` | 60 vehicles with battery/service profile |
| `trips/trips.csv` | 150 trips |
| `battery/soc_history.csv.gz` | SOC history per trip |

### Stations

| File | Description |
|------|-------------|
| `stations/stations.csv` | 30 stations |
| `stations/station_status.csv.gz` | Temporal station state (service-specific capacity) |
| `queue/queue_status.csv.gz` | Service-specific queue state |

### Traffic

| File | Description |
|------|-------------|
| `traffic/traffic_snapshots.csv.gz` | 883,597 temporal traffic snapshots |

### Training / Evaluation

| File | Description |
|------|-------------|
| `training/map_matching_candidates.csv.gz` | 27,042 map-matching candidate segments |
| `training/map_matching_candidates_with_split.csv.gz` | Candidates with train/validation/test split |
| `training/demand_features.csv` | Leakage-safe demand features |
| `training/ranking_reference.csv` | 3,727 ranking reference rows |
| `training/trip_splits.csv` | Trip-level train/validation/test split |

### Labels (Evaluation-Only — NOT Runtime Input)

| File | Description |
|------|-------------|
| `labels/demand_labels.csv` | 1,200 demand labels (NONE/CHARGING/BATTERY_SWAP) |
| `labels/candidate_labels.csv` | 36,000 candidate eligibility labels |
| `labels/recommendation_labels.csv` | 848 recommendation labels (evaluation only) |
| `labels/map_matching_labels.csv.gz` | Ground-truth map-matching labels |

### Scenarios / Realtime

| File | Description |
|------|-------------|
| `scenarios/scenario_coverage.csv` | 21 scenario-definition rows; the current validator runs 22 scenario assertions |
| `realtime/events.csv.gz` | 109,193 chronological replay events |

## Key Relationships

`trips/trips.csv`
  ├── driver_id → drivers/drivers.csv
  ├── vehicle_id → vehicles/vehicles.csv
  ├── origin_node_id → road_nodes
  └── destination_node_id → road_nodes

`gps/gps_observations.csv.gz`
  ├── trajectory_id → true_trajectories.csv.gz
  └── trip_id → trips/trips.csv

`labels/map_matching_labels.csv.gz`
  ├── observation_id → gps_observations
  └── true_segment_id → road_segments

## Runtime vs Evaluation Data

### Runtime Inputs (Used at Runtime)
- GPS observations (gps_observations.csv.gz)
- Road network (GraphHopper graph imported from the patched PBF, plus canonical road_segments.csv.gz for PostGIS identity resolution)
- Stations + temporal state (stations.csv + station_status.csv.gz + queue_status.csv.gz)
- Traffic snapshots (traffic_snapshots.csv.gz)
- SOC history (soc_history.csv.gz)
- Demand features (for demand detection features)

### Evaluation Labels (Never Runtime Input)
- demand_labels.csv
- candidate_labels.csv
- recommendation_labels.csv
- ranking_reference.csv
- map_matching_labels.csv.gz

**CRITICAL: Labels must NEVER be consumed as runtime prediction input.**

## External GPS Data

An additional GPS mobility source is maintained outside `dataset_v1/`.

| File | Description |
|------|-------------|
| `data/external/gps/raw/fake_gps.csv` | Raw GPS CSV (51 MB, ~400K rows) |
| `data/external/gps/processed/gps_normalized.parquet` | 399,759 normalized observations |
| `data/external/gps/processed/gps_hanoi.parquet` | 332,700 Hanoi-subset observations |
| `data/external/gps/processed/gps_sessions.parquet` | 1,202 GPS session summaries |
| `data/external/gps/rejected/rejected_rows.csv` | 225 rejected malformed rows |
| `docs/EXTERNAL_GPS_DATA.md` | Full documentation |

**External GPS is NOT part of Dataset V1.** It has no ground truth labels, no SOC data, and no station state. See `docs/EXTERNAL_GPS_DATA.md` for schema, profiling, and usage guidance.

Pipeline:
```bash
python scripts/prepare_external_gps.py   # preprocess
python scripts/validate_external_gps.py  # validate
```

## Service Semantics (V1.2)

- CHARGING service time: 18 minutes
- BATTERY_SWAP service time: 6 minutes
- CHARGING capacity: available_charging_slots
- BATTERY_SWAP capacity: min(available_swap_slots, available_swap_batteries)
- FARTHER_BUT_FASTER threshold: ≥500 m farther AND ≥10 min lower total ETA

## Current Runtime and Validation (2026-09-21)

The migration integrity manifest (`runtime/migration/dataset-integrity.json`)
reports all 63 Dataset file hashes identical to the pre-migration manifest.
Functional verification passed with 239 tests and live normal/outage API checks;
formal reporting and freeze remain separate final gates. Ambiguous projected
traversal or PostGIS directed-segment ties withhold road segment and direction,
returning `AMBIGUOUS` even when the geometric location is matched.

GraphHopper 11.0 is the only production routing and matching engine. Both profiles
use the same immutable patched PBF: `EV_CAR -> car`, `EV_MOTORBIKE -> motorcycle`.
The motorcycle model shares `car_access`; `motorcar=no` therefore excludes
motorcycles too. This includes patched way 881947000 and is a documented access
limitation, not permission to alter the map.

`scripts/load_road_network.py` loads the 701,407 canonical directed road segments
into PostGIS for matched Dataset identity resolution. GraphHopper internal graph
IDs are not equivalent to Dataset segment/node IDs or OSM IDs. Matching projects
observations onto actual returned matched geometry; PostGIS uses that location,
OSM way details and traversal bearing. Unresolved IDs stay null. Quality scores
measure geometric proximity and must not be treated as native engine confidence
or ground-truth accuracy; see [ARCHITECTURE](ARCHITECTURE.md).

`make validate-data` runs `scripts/validate_frozen_dataset.py`. It executes the
canonical validator while redirecting generated reports to
`runtime/migration/validation`, preserving the frozen tree. The current run
reports **152 PASS / 0 FAIL and 22/22 scenario assertions**. Historical references
to 163 checks and 21 scenarios describe an earlier validator baseline and are
superseded for current counts. Dataset hashes and migration-quality gates remain
separate verification obligations.

Live routing smoke/benchmark fixtures consume only vehicles, trips, canonical
road nodes and SOC telemetry. All labels and ranking references remain confined
to offline evaluation. Neither smoke results nor business-eligibility agreement
alone establish matching accuracy or recommendation quality.
