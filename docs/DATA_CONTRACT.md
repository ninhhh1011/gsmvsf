# DATA_CONTRACT

## Paired guidance-departure evidence (2026-10-14)

The authorized H3 extension stores paired evidence separately in the configured
`realtime.route_deviation_trips` or `synthetic.route_deviation_trips` namespace.
Trusted producers submit driver/trip identity, aware start/completion times,
ordered guidance versions (`effective_at`, coordinates), and strictly ordered
timestamped observations. Raw evidence is immutable; matching retries may refresh
derived analysis after detector corrections. Conflicting evidence is HTTP 409.
Legacy paths cannot prove a departure and are not backfilled with today's routes.

Only completed trips available at query time contribute. Individual reached,
departure and uncertainty timestamps also obey the seven-day event window.
Per cell, a trip counts once in the reached denominator/departure numerator; all
confirmed events count separately. Uncertain no-event trip/cell contributions are
excluded rather than reported as zero. This denominator measures sampled guided
corridor exposure, not all planned trips or all GPS points. The last unambiguous
guided position preceding confirmation approximates the departure origin, not a
verified junction or a driver's motivation. Synthetic offline truth never enters
runtime analysis. See the [contract](superpowers/specs/2026-10-14-h3-departure-statistics.md).

## Approved synthetic journey extension (2026-10-12)

Dataset V1 remains immutable. Optional generated journey histories live in PostgreSQL `synthetic.route_familiarity_routes`; production history defaults to `realtime.route_familiarity_routes`. Namespace selection is server configuration, never a client-supplied SQL identifier. The fixed public example identity is exposed only with enabled synthetic history.

Seed manifests contain batch identity, seed, exact observation time, real GraphHopper route templates and provenance. Behavioral inputs produce route choices; separate `evaluation_truth.json` records those inputs for evaluation and is never runtime prediction input. Immutable ingestion retries preserve trip geometry/time. Load drivers use virtual copies of canonical vehicle specifications and independent synthetic IDs; no canonical fleet or trajectories are patched.

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

These are frozen Dataset V1 semantics and historical baselines. Under customer-approved ADR-026, the current runtime replaces flat charging time with predicted energy-based service duration. The canonical snapshots and labels remain unchanged and are not rewritten to match the new runtime.

- CHARGING service time: 18 minutes
- BATTERY_SWAP service time: 6 minutes
- CHARGING capacity: available_charging_slots
- BATTERY_SWAP capacity: min(available_swap_slots, available_swap_batteries)
- FARTHER_BUT_FASTER threshold: ≥500 m farther AND ≥10 min lower total ETA

## Predicted replenishment contract (2026-10-13)

`EvaluatedCandidate.replenishment`, ranking `features.replenishment` and station-plan `replenishment` expose model status/reason, arrival/departure/destination kWh and SOC, added kWh, effective installed capacity, consumption, reserve, nominal charging power bound, efficiency/taper/setup, service seconds and provenance. Destination energy is null when the station is the final goal. Explicit valid remaining kWh is authoritative over rounded SOC; missing range is derived from that energy and retained consumption. Explicit range keeps its source. Capacity comes from canonical capability and installed modules, not a client override. Nonfinite/out-of-capacity evidence is unavailable.

The customer chose sufficient energy for B plus reserve, 80% for a station-only goal and 90% for swap. The published VF 3 limit is 24 kW; representative charging powers and broad class assumptions are documented separately. Calculated charging service time replaces the flat whole-service time, rather than adding it as setup. Swap service time still follows the operational snapshot. Queue is separate and counted once.

These fields predict a future service plan. They are not accepted GPS/SOC telemetry, charging completion evidence or calibrated charging curves. Live SOC is never raised just because a driver passes the station. After-B planning evidence consumes the prefix once without reporting the projected B SOC as the current live SOC.

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

## Legacy H3 footprint extension (2026-10-14)

Legacy completed histories contribute gray `HISTORY_ONLY` cells, with
`history_trip_count` and null departure metrics. Convert saved resolution-11 index
centres to the requested resolution, counting each trip once per cell. Time means
`COMPLETED_TRIP_COHORT`, because legacy point times are unavailable. Paired observed
cell timestamps obey the event window, independently of guided exposure. Overlapping
legacy/paired identities are excluded from legacy only once paired completion is
available. Visits never enlarge the guided denominator. No raw identity is exposed.
The new GraphHopper synthetic batch is separate from Dataset V1 and ranking history;
its offline maneuver declarations are never prediction inputs.

## Approved trip-inspection and coverage extension (2026-10-14)

`POST /routing/inspect-guided-trip` accepts bounded caller-supplied GuidedTrip
without history lookup or persistence. Confirmed ON_ROUTE/OFF_ROUTE runs reuse the
analyzer. UNKNOWN includes pending runs, ambiguity and continuity/version breaks;
never draw across those breaks. Unknown time includes missing head/tail; unobserved
jump distances are withheld. Two frozen initial-guidance coverage percentages are
separate from active-guidance intervals. Incomplete GPS/boundaries, zero observed
movement or comparison work limits withhold percentages rather than invalidate
otherwise usable interval evidence.

Gated synthetic examples sanitize identities and require enabled familiarity,
public_synthetic_sample and a synthetic repository. No realtime history reader.
Offline coverage reports are fixed synthetic summaries. Candidate-reference
coverage uses road class/access, deduplicated physical geometry, 12 m proximity to
continuous seven-day paired GPS and EPSG:32648 lengths. Entire roads are bucketed
by approximate geodesic midpoint into H3-5 regions, not clipped at borders or
assigned districts. Complete motorcar permissions are unavailable; eligible-road
coverage stays null. Legacy signatures and offline labels never supply coverage.
