import json
from pathlib import Path
import pandas as pd
ROOT=Path('/mnt/data/dataset_v1')
counts=json.load(open(ROOT/'validation/data_counts.json'))
val=json.load(open(ROOT/'validation/validation_results.json'))
patch=json.load(open(ROOT/'validation/patch_summary.json'))
rankbase=json.load(open(ROOT/'config/ranking_baseline.json'))

warning='**MAP WARNING — HUMAN CONFIRMATION REQUIRED:** `hanoi-patched.osm.pbf` changes OSM way `881947000` (Cầu Thanh Trì) from `motorcar=designated` to `motorcar=no`. Dataset V1.1 does not decide whether that edit is correct. Keep both PBFs unchanged and obtain human confirmation before freezing the patched PBF as the primary routing map.'
readme=f'''# Dataset V1.1 — Driver Charging / Battery Swap Recommendation

This workspace is the patched Dataset V1 for the supplied 6-week acceptance scope. It contains data generation, labels, evaluation references, scenario replay and validation only. It does **not** set up FastAPI, PostgreSQL/PostGIS, OSRM server, Docker Compose, Kafka, Redis, frontend, microservices or production infrastructure.

## Map source status
- Raw inputs retained byte-for-byte: `map/raw/hanoi-baseline.osm.pbf` and `map/raw/hanoi-patched.osm.pbf`.
- Current processed road representation was built from the patched working source during V1 generation; this is **provisional**, not a human-approved routing-map freeze.
- PBF integrity vs the originally uploaded inputs: **PASS**.

{warning}

## Patch V1.1 summary
- `NEED_SWAP` trips now use swap-capable EV motorbikes and their SOC/energy histories were recalculated using the assigned vehicle parameters.
- Demand training expanded from one decision/trip to **{counts['demand_labels']} decision snapshots** across {counts['trips']} trips.
- Demand distribution: **NONE {patch['demand_distribution']['NONE']} / CHARGING {patch['demand_distribution']['CHARGING']} / BATTERY_SWAP {patch['demand_distribution']['BATTERY_SWAP']}**.
- Candidate eligibility now evaluates service/vehicle/connector/battery compatibility, temporal station state, capacity, queue threshold, network reachability and SOC reachability.
- Map-matching training uses **{patch['map_matching']['observations_selected']} selected observations**, each guaranteed to have positive + negative candidates.
- Ranking expanded to **{patch['ranking']['event_groups']} candidate groups / {patch['ranking']['rows']} rows**, 8 candidates/group.
- `scenarios/scenario_coverage.csv` contains quantitative evidence; **21/21 scenario validators PASS**.
- Extended validation: **{val['passed']} passed / {val['failed']} failed — {val['overall']}**.

## Key counts
| Dataset | Records |
|---|---:|
| Road nodes | {counts['road_nodes']:,} |
| Directed road segments | {counts['road_segments']:,} |
| Drivers | {counts['drivers']:,} |
| Vehicles | {counts['vehicles']:,} |
| Trips | {counts['trips']:,} |
| True trajectory points | {counts['true_trajectory_points']:,} |
| GPS observations | {counts['gps_observations']:,} |
| SOC history | {counts['soc_history']:,} |
| Stations | {counts['stations']:,} |
| Station status | {counts['station_status']:,} |
| Queue status | {counts['queue_status']:,} |
| Traffic snapshots | {counts['traffic_snapshots']:,} |
| Realtime events | {counts['realtime_events']:,} |
| Demand decisions | {counts['demand_labels']:,} |
| Candidate labels | {counts['candidate_labels']:,} |
| Map-matching candidate rows | {counts['map_matching_candidates']:,} |
| Ranking rows | {counts['ranking_reference']:,} |
| Ranking event groups | {counts['ranking_event_groups']:,} |

## Demand labeling baseline
Decision snapshots are taken at multiple points in each trip. A service need is raised when SOC is near/below the safety threshold or estimated range is insufficient for remaining trip distance plus reserve. If service is needed, vehicles with a swappable battery use `BATTERY_SWAP`; otherwise a charging-capable vehicle uses `CHARGING`. Runtime feature files do not contain the target service label.

## Candidate eligibility reason priority
`NO_SERVICE_NEEDED` → `INCOMPATIBLE` → `UNREACHABLE` → `OFFLINE` → `FULL` / `NO_SWAP_BATTERY` → `EXCESSIVE_QUEUE` → `INSUFFICIENT_SOC_TO_REACH` → `ELIGIBLE`.

The current candidate wait cutoff is **90 min** and SOC reachability includes a **0.5 km buffer**. These values are configuration assumptions for Dataset V1.1 and are documented in `config/generation_config.json`.

## Ranking reference baseline
Candidate groups are training/evaluation references, not runtime recommendations. Baseline v2 uses the following components:

`{rankbase['cost_formula']}`

Penalties: station not open = {rankbase['penalties']['station_not_open']}, no available capacity = {rankbase['penalties']['no_available_capacity']}, SOC infeasible = {rankbase['penalties']['soc_infeasible']}.

`labels/recommendation_labels.csv` is evaluation-only and must not be read as a runtime recommendation input.

## Training splits
Splits are assigned by `trip_id`, never by individual row. Demand snapshots, map-matching candidate groups and ranking groups inherit the trip split, preventing the same trip from appearing across train/validation/test.

## Regeneration / patch workflow
For the existing Dataset V1 workspace, run:
1. `generators/04_patch_semantic_dataset.py` — semantic patch requiring the existing V1 base.
2. If execution is interrupted after candidate/ranking checkpoint, `generators/04b_finalize_semantic_patch.py` finalizes map-matching/replay/scenario artifacts.
3. `validation/validate_dataset.py` — full structural + semantic validation.

The patch does not download OSM and does not modify either raw PBF.

## Formats
Large time-series tables remain gzip-compressed CSV because the original V1 environment did not have a Parquet engine available. Raw OSM remains PBF; a small GeoJSON road sample is provided for visual inspection.
'''
(ROOT/'README.md').write_text(readme,encoding='utf-8')

matrix=f'''# REQUIREMENT_DATA_MATRIX — Dataset V1.1

| Requirement | Runtime / source data | Features / columns | Training labels | Evaluation / semantic evidence |
|---|---|---|---|---|
| Project-wide linked operational data | drivers, vehicles, trips, road network, trajectories, GPS, SOC, stations, temporal states | stable IDs, timestamps, road refs, compatibility refs | separated under `labels/` / `training/` | {val['passed']+val['failed']}-check validation + 21 scenario validators |
| Week 1 — Map Matching | `road_nodes`, `road_segments`, `true_trajectories`, `gps_observations` | segment geometry, direction, heading, GPS accuracy, projected candidate distance, heading difference | `map_matching_labels`; candidate `is_correct`, `hard_negative` | {patch['map_matching']['observations_selected']} selected obs; every selected group has positive + negative; {patch['map_matching']['hard_negative_count']} hard negatives |
| Week 2 — Charging/Swap Demand | `vehicles`, `trips`, `soc_history` | SOC, remaining range, remaining trip distance, reserve, consumption, safety threshold, charging/swap capability, connector/battery | `demand_labels` with NONE / CHARGING / BATTERY_SWAP | {counts['demand_labels']} snapshots; split by trip; NEED_SWAP vehicle/label assertion |
| Week 3 — Candidate Search | stations + station_status + queue + road graph + demand output | service/vehicle/connector/battery compatibility, network distance, station state, capacity, wait, SOC feasibility | `candidate_labels` reason/eligible | reasons distinguish ELIGIBLE, INCOMPATIBLE, OFFLINE, FULL, UNREACHABLE, INSUFFICIENT_SOC_TO_REACH, NO_SERVICE_NEEDED (+ optional state reasons) |
| Week 3 — Routing references | road graph, event road position, station access node, destination | driver→station distance/ETA; station→destination distance/ETA; direct driver→destination references | none as runtime | routing references live only in `ranking_reference.csv` for training/evaluation |
| Week 4 — Ranking/Recommendation | demand output + candidate/station/traffic/queue state | driver→station, station→destination, direct route, detour, traffic-adjusted ETA, queue wait, service time, capacity, status, SOC feasibility | `ranking_cost_label`, `reference_rank`, `is_reference_best`; `recommendation_labels` evaluation-only | {counts['ranking_event_groups']} groups / {counts['ranking_reference']} rows; documented baseline v2 |
| Week 5 — Realtime recomputation | `realtime/events.csv.gz`, station/queue/traffic temporal tables | GPS_UPDATE, SOC_UPDATE, STATION_STATUS_UPDATE, TRAFFIC_UPDATE | no runtime recommendation label | explicit before/after queue, traffic and station-status transitions validated from replay |
| Week 5 — Evaluation | all labels + split tables + scenario coverage | class/group distributions and quantitative scenario metrics | task-specific labels | 21/21 scenario conditions asserted against underlying data |
| Week 6 — Reproducibility / productionization support | config + generators + counts + validation | deterministic seed, configurable counts/frequencies, semantic thresholds | none required | generator patch, full validation, PBF byte-integrity check |

## Map routing caveat
{warning}

## Scope boundary
No backend/API/database/OSRM server/Kafka/Redis/frontend or production infrastructure is created. Runtime recommendation output is deliberately absent from runtime input tables.
'''
(ROOT/'REQUIREMENT_DATA_MATRIX.md').write_text(matrix,encoding='utf-8')

# Data dictionary generated from current schemas
meta={
'map/processed/road_nodes.csv.gz':('Topological road nodes','node_id','None','Map matching, routing, station access'),
'map/processed/road_segments.csv.gz':('Directed road segments split between consecutive OSM geometry vertices','segment_id','from_node_id, to_node_id','Map matching, routing, traffic, station access'),
'drivers/drivers.csv':('Driver population without real PII','driver_id','None','Trip ownership'),
'vehicles/vehicles.csv':('Vehicle, battery and service compatibility profile','vehicle_id','driver_id','Demand, compatibility, ranking'),
'trips/trips.csv':('Trips tied to network origin/destination, vehicle and scenario','trip_id','driver_id, vehicle_id, origin_node_id, destination_node_id','All pipeline modules'),
'trajectories/true_trajectories.csv.gz':('Ground-truth road-network trajectory','trajectory_id + point_index','trip_id, true_segment_id','Map-matching truth, scenario validation'),
'gps/gps_observations.csv.gz':('Noisy/missing GPS observations derived from true trajectory','observation_id','trajectory_id, trip_id','Map-matching runtime input, replay'),
'battery/soc_history.csv.gz':('Physically recomputed SOC, energy and estimated range history','vehicle_id + trip_id + timestamp','vehicle_id, trip_id','Demand runtime input, replay'),
'stations/stations.csv':('Charging/swap station master located at road access nodes','station_id','access_node_id','Candidate search, ranking'),
'stations/station_status.csv.gz':('Temporal operating/capacity/service state','station_id + timestamp','station_id','Candidate search, ranking, replay'),
'queue/queue_status.csv.gz':('Temporal queue/service/wait state','station_id + timestamp','station_id','Candidate/ranking/realtime'),
'traffic/traffic_snapshots.csv.gz':('Temporal traffic speed and delay on road segments','segment_id + timestamp','segment_id','Routing/ranking/realtime'),
'realtime/events.csv.gz':('Chronological event stream for deterministic replay','event_id','entity_id references trip/station/segment by event type','Week 5 replay'),
'labels/map_matching_labels.csv.gz':('Ground-truth segment/direction per GPS observation','observation_id','observation_id, true_segment_id','Map-matching training/evaluation label'),
'training/map_matching_candidates.csv.gz':('Selected candidate segments for map-matching training/evaluation','observation_id + candidate_segment_id','observation_id, candidate_segment_id','Map-matching training/evaluation'),
'training/map_matching_candidates_with_split.csv.gz':('Map-matching candidates with trip-safe train/validation/test assignment','observation_id + candidate_segment_id','observation_id, candidate_segment_id, trip_id','Map-matching training/evaluation'),
'labels/demand_labels.csv':('Service-demand target labels at multiple trip decision snapshots','event_id','trip_id','Demand training/evaluation label'),
'training/demand_features.csv':('Leakage-safe demand features at multiple trip decision snapshots','event_id','trip_id','Demand training/evaluation features'),
'labels/candidate_labels.csv':('Candidate station eligibility and reason labels with evaluation evidence','event_id + station_id','event_id, station_id','Candidate-search evaluation/training label'),
'training/ranking_reference.csv':('Grouped station-ranking training/evaluation references','event_id + station_id','event_id, trip_id, station_id','Week 4 ranking training/evaluation'),
'labels/recommendation_labels.csv':('Reference best-station evaluation label; never runtime input','event_id','event_id, reference_station_id','Recommendation evaluation only'),
'training/trip_splits.csv':('Leakage-safe split assignment at trip granularity','trip_id','trip_id','All training tasks'),
'scenarios/scenario_coverage.csv':('Quantitative scenario evidence and validator result','scenario_id','example_trip_id, example_event_id, evidence entities','Cross-module semantic evaluation')
}
files=list(meta)
unit_overrides={'latitude':'degrees WGS84','longitude':'degrees WGS84','true_latitude':'degrees WGS84','true_longitude':'degrees WGS84','projected_lat':'degrees WGS84','projected_lon':'degrees WGS84','access_latitude':'degrees WGS84','access_longitude':'degrees WGS84','geometry':'WKT EPSG:4326','timestamp':'ISO 8601','state_timestamp':'ISO 8601','before_timestamp':'ISO 8601','after_timestamp':'ISO 8601','payload_json':'JSON'}
def unit(c):
    if c in unit_overrides:return unit_overrides[c]
    if c.endswith('_kmh'):return 'km/h'
    if c.endswith('_kwh'):return 'kWh'
    if c.endswith('_wh_per_km'):return 'Wh/km'
    if c.endswith('_pct'):return '%'
    if c.endswith('_deg'):return 'degrees'
    if c.endswith('_min') or 'eta_min' in c or 'wait_min' in c or 'time_min' in c:return 'min'
    if c.endswith('_km'):return 'km'
    if c.endswith('_m') or 'distance_m' in c:return 'm'
    return ''
rel_notes={'event_id':'Decision/ranking event identifier; join to demand label/feature by event_id','trip_id':'References trips.trip_id','vehicle_id':'References vehicles.vehicle_id','driver_id':'References drivers.driver_id','station_id':'References stations.station_id','segment_id':'References road_segments.segment_id','candidate_segment_id':'References road_segments.segment_id','true_segment_id':'References road_segments.segment_id','from_node_id':'References road_nodes.node_id','to_node_id':'References road_nodes.node_id','access_node_id':'References road_nodes.node_id','origin_node_id':'References road_nodes.node_id','destination_node_id':'References road_nodes.node_id','reference_station_id':'Evaluation-only station reference; must not be runtime input','ranking_cost_label':'Training/evaluation target from documented baseline v2','reference_rank':'Training/evaluation rank label','is_reference_best':'Training/evaluation best-candidate label','eligible':'Candidate eligibility label; not a raw runtime feature','reason':'Evaluation reason generated from compatibility/state/reachability/SOC rules','is_correct':'Map-matching candidate label','hard_negative':'Map-matching negative difficulty marker'}
parts=['# DATA_DICTIONARY — Dataset V1.1','',warning,'']
for f in files:
    purpose,pk,fk,modules=meta[f]; full=pd.read_csv(ROOT/f)
    parts += [f'## `{f}`','',f'- **Purpose:** {purpose}',f'- **Primary key:** {pk}',f'- **Foreign keys:** {fk}',f'- **Modules:** {modules}','','| Column | Type | Unit | Nullable | Relationship / notes |','|---|---|---|---|---|']
    for c in full.columns:
        nullable='Yes' if full[c].isna().any() else 'No'; note=rel_notes.get(c,'')
        if c=='service_type' and 'demand_labels' in f: note='Target values: NONE / CHARGING / BATTERY_SWAP'
        if c=='split': note='Trip-level split: train / validation / test'
        if c=='operating_status': note='Temporal station state; OPEN/OFFLINE in V1.1'
        if c=='scenario_id': note='Scenario identifier; quantitative condition evidence in scenarios/scenario_coverage.csv'
        parts.append(f'| {c} | {full[c].dtype} | {unit(c)} | {nullable} | {note} |')
    parts.append('')
parts += ['## Supporting metadata / validation files','',
'- `config/generation_config.json`: generator seed, volume/frequency settings and V1.1 semantic thresholds.',
'- `config/ranking_baseline.json`: exact ranking candidate-pool assumptions, cost formula and penalties.',
'- `validation/data_counts.json`: record counts after patch.',
'- `validation/validation_results.json` / `.csv`: structural + semantic validation results.',
'- `validation/scenario_validation_results.json`: 21 scenario assertions and quantitative evidence.',
'- `validation/map_matching_candidate_stats.json`: positive/negative/hard-negative and split coverage.',
'- `validation/demand_distribution.json`: demand class distribution.',
'- `validation/ranking_stats.json`: ranking rows/groups/splits.',
'- `validation/pbf_integrity.json`: SHA-256 equality check against the originally uploaded raw PBFs plus the Cầu Thanh Trì warning.',
'- `map/processed/pbf_diff.csv`: explicit baseline vs patched OSM tag diff; raw PBFs remain unchanged.','']
(ROOT/'DATA_DICTIONARY.md').write_text('\n'.join(parts),encoding='utf-8')
print('updated docs')
