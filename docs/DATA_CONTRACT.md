# DATA_CONTRACT

**MAP STATUS — APPROVED:** `hanoi-patched.osm.pbf` is the primary OSRM map. Contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì). `hanoi-baseline.osm.pbf` is reference.

## Dataset V1 Location

Dataset V1 is located at `./dataset_v1/` and is the canonical development dataset for the full six-week project.

**Dataset V1 is READ-ONLY during normal development.** Do not regenerate, patch, move, or alter files inside it.

## Dataset V1 Contents

### Map / Road Network

| File | Description |
|------|-------------|
| `map/raw/hanoi-baseline.osm.pbf` | Primary OSRM routing map (baseline OSM) |
| `map/raw/hanoi-patched.osm.pbf` | Patched OSM (pending human review for Cầu Thanh Trì) |
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
| `scenarios/scenario_coverage.csv` | 21 scenario definitions with quantitative evidence |
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
- Road network (from OSRM / road_segments.csv.gz)
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

## FARTHER_BUT_FASTER Evidence

Validated event DE000580 / trip T0073:
- S028 is 542.9 m farther than S026 by network distance
- S028's total ETA is 13.472 min lower (53.339 vs 66.811 min)
- Meaningful margin: ≥500 m farther and ≥10 min faster

## Service Semantics (V1.2)

- CHARGING service time: 18 minutes
- BATTERY_SWAP service time: 6 minutes
- CHARGING capacity: available_charging_slots
- BATTERY_SWAP capacity: min(available_swap_slots, available_swap_batteries)
- FARTHER_BUT_FASTER threshold: ≥500 m farther AND ≥10 min lower total ETA
