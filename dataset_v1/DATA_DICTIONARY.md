# DATA_DICTIONARY â€” Dataset V1.2

**MAP STATUS â€” APPROVED:** `hanoi-patched.osm.pbf` is the primary OSRM map. Contains motorcar=no for OSM way 881947000 (Cáº§u Thanh TrÃ¬). `hanoi-baseline.osm.pbf` is reference.

## V1.2 semantic contracts

- Ranking consumes only `candidate_labels.eligible == true`.
- Ranking group size is variable 1..8 after eligibility filtering.
- Recommendation exists iff at least one eligible station exists.
- Mixed charging/swap stations maintain independent capacity and queue/service-time state.
- FARTHER_BUT_FASTER uses thresholds: >=500 m farther and >=10 min lower total ETA.
- Current independent validation: **163 PASS / 0 FAIL**.

## `map/processed/road_nodes.csv.gz`

- **Purpose:** Topological road nodes
- **Primary key:** node_id
- **Foreign keys:** None
- **Modules:** Map matching, routing, station access

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| node_id | object |  | No |  |
| latitude | float64 | degrees WGS84 | No |  |
| longitude | float64 | degrees WGS84 | No |  |

## `map/processed/road_segments.csv.gz`

- **Purpose:** Directed road segments split between consecutive OSM geometry vertices
- **Primary key:** segment_id
- **Foreign keys:** from_node_id, to_node_id
- **Modules:** Map matching, routing, traffic, station access

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| segment_id | object |  | No | References road_segments.segment_id |
| from_node_id | object |  | No | References road_nodes.node_id |
| to_node_id | object |  | No | References road_nodes.node_id |
| travel_direction | object |  | No |  |
| base_segment_id | object |  | No |  |
| osm_way_id | int64 |  | No |  |
| geometry | object | WKT EPSG:4326 | No |  |
| length_m | float64 | m | No |  |
| road_type | object |  | No |  |
| road_name | object |  | Yes |  |
| oneway | bool |  | No |  |
| maxspeed_kmh | float64 | km/h | No |  |
| lanes | float64 |  | Yes |  |
| bridge | object |  | No |  |
| tunnel | object |  | No |  |
| access | object |  | No |  |

## `drivers/drivers.csv`

- **Purpose:** Driver population without real PII
- **Primary key:** driver_id
- **Foreign keys:** None
- **Modules:** Trip ownership

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| driver_id | object |  | No | References drivers.driver_id |
| status | object |  | No |  |
| operating_shift | object |  | No |  |

## `vehicles/vehicles.csv`

- **Purpose:** Vehicle, battery and service compatibility profile
- **Primary key:** vehicle_id
- **Foreign keys:** driver_id
- **Modules:** Demand, compatibility, ranking

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| vehicle_id | object |  | No | References vehicles.vehicle_id |
| driver_id | object |  | No | References drivers.driver_id |
| vehicle_type | object |  | No |  |
| battery_capacity_kwh | float64 | kWh | No |  |
| usable_capacity_kwh | float64 | kWh | No |  |
| consumption_wh_per_km | int64 | Wh/km | No |  |
| minimum_safe_soc_pct | int64 | % | No |  |
| charging_supported | bool |  | No |  |
| swap_supported | bool |  | No |  |
| connector_type | object |  | No |  |
| battery_type | object |  | No |  |

## `trips/trips.csv`

- **Purpose:** Trips tied to network origin/destination, vehicle and scenario
- **Primary key:** trip_id
- **Foreign keys:** driver_id, vehicle_id, origin_node_id, destination_node_id
- **Modules:** All pipeline modules

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| trip_id | object |  | No | References trips.trip_id |
| driver_id | object |  | No | References drivers.driver_id |
| vehicle_id | object |  | No | References vehicles.vehicle_id |
| origin_node_id | object |  | No | References road_nodes.node_id |
| destination_node_id | object |  | No | References road_nodes.node_id |
| start_time | object |  | No |  |
| end_time | object |  | No |  |
| planned_network_distance_m | float64 | m | No |  |
| scenario_id | object |  | No | Scenario identifier; quantitative condition evidence in scenarios/scenario_coverage.csv |

## `trajectories/true_trajectories.csv.gz`

- **Purpose:** Ground-truth road-network trajectory
- **Primary key:** trajectory_id + point_index
- **Foreign keys:** trip_id, true_segment_id
- **Modules:** Map-matching truth, scenario validation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| trajectory_id | object |  | No |  |
| trip_id | object |  | No | References trips.trip_id |
| point_index | int64 |  | No |  |
| timestamp | object | ISO 8601 | No |  |
| true_latitude | float64 | degrees WGS84 | No |  |
| true_longitude | float64 | degrees WGS84 | No |  |
| true_segment_id | object |  | No | References road_segments.segment_id |
| speed_kmh | float64 | km/h | No |  |
| heading_deg | float64 | degrees | No |  |
| travel_direction | object |  | No |  |

## `gps/gps_observations.csv.gz`

- **Purpose:** Noisy/missing GPS observations derived from true trajectory
- **Primary key:** observation_id
- **Foreign keys:** trajectory_id, trip_id
- **Modules:** Map-matching runtime input, replay

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| observation_id | object |  | No |  |
| trajectory_id | object |  | No |  |
| trip_id | object |  | No | References trips.trip_id |
| timestamp | object | ISO 8601 | No |  |
| latitude | float64 | degrees WGS84 | No |  |
| longitude | float64 | degrees WGS84 | No |  |
| speed_kmh | float64 | km/h | No |  |
| heading_deg | float64 | degrees | No |  |
| accuracy_m | float64 | m | No |  |

## `battery/soc_history.csv.gz`

- **Purpose:** Physically recomputed SOC, energy and estimated range history
- **Primary key:** vehicle_id + trip_id + timestamp
- **Foreign keys:** vehicle_id, trip_id
- **Modules:** Demand runtime input, replay

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| vehicle_id | object |  | No | References vehicles.vehicle_id |
| trip_id | object |  | No | References trips.trip_id |
| timestamp | object | ISO 8601 | No |  |
| soc_pct | float64 | % | No |  |
| distance_travelled_km | float64 | km | No |  |
| energy_consumed_kwh | float64 | kWh | No |  |
| estimated_remaining_range_km | float64 | km | No |  |

## `stations/stations.csv`

- **Purpose:** Charging/swap station master located at road access nodes
- **Primary key:** station_id
- **Foreign keys:** access_node_id
- **Modules:** Candidate search, ranking

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| station_id | object |  | No | References stations.station_id |
| access_node_id | object |  | No | References road_nodes.node_id |
| latitude | float64 | degrees WGS84 | No |  |
| longitude | float64 | degrees WGS84 | No |  |
| access_latitude | float64 | degrees WGS84 | No |  |
| access_longitude | float64 | degrees WGS84 | No |  |
| station_type | object |  | No |  |
| connector_type | object |  | No |  |
| battery_type | object |  | Yes |  |
| supported_vehicle_type | object |  | No |  |
| total_slots | int64 |  | No |  |
| charging_slots | int64 |  | No |  |
| swap_slots | int64 |  | No |  |

## `stations/station_status.csv.gz`

- **Purpose:** Temporal operating state plus service-specific charging/swap capacity and service time
- **Primary key:** station_id + timestamp
- **Foreign keys:** station_id â†’ stations.station_id
- **Modules:** Candidate search, ranking, realtime replay

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| station_id | object |  | No | References stations.station_id |
| timestamp | object | ISO 8601 | No | State timestamp |
| operating_status | object |  | No | OPEN/OFFLINE |
| available_charging_slots | int64 | slots | No | CHARGING available capacity |
| occupied_charging_slots | int64 | slots | No | Together with available <= stations.charging_slots |
| available_swap_slots | int64 | slots | No | Swap bay/slot availability |
| occupied_swap_slots | int64 | slots | No | Together with available <= stations.swap_slots |
| available_swap_batteries | int64 | batteries | No | Swap inventory constraint |
| charging_service_time_min | float64 | min | No | 18 for stations offering charging; 0 when charging unavailable |
| swap_service_time_min | float64 | min | No | 6 for stations offering swap; 0 when swap unavailable |

For BATTERY_SWAP, usable capacity is `min(available_swap_slots, available_swap_batteries)`.

## `queue/queue_status.csv.gz`

- **Purpose:** Independent charging and battery-swap queue/service/wait state
- **Primary key:** station_id + timestamp
- **Foreign keys:** station_id â†’ stations.station_id
- **Modules:** Candidate search, ranking, realtime replay

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| station_id | object |  | No | References stations.station_id |
| timestamp | object | ISO 8601 | No | State timestamp |
| charging_queue_length | int64 | vehicles | No | Charging queue only |
| charging_active_service_count | int64 | services | No | Active charging services |
| charging_service_time_min | float64 | min | No | Service-specific time; 18 when offered |
| charging_estimated_wait_min | float64 | min | No | queue_length Ã— service_time / active_service_count when active > 0 |
| swap_queue_length | int64 | vehicles | No | Swap queue only |
| swap_active_service_count | int64 | services | No | Active swap services |
| swap_service_time_min | float64 | min | No | Service-specific time; 6 when offered |
| swap_estimated_wait_min | float64 | min | No | queue_length Ã— service_time / active_service_count when active > 0 |

## `traffic/traffic_snapshots.csv.gz`

- **Purpose:** Temporal traffic speed and delay on road segments
- **Primary key:** segment_id + timestamp
- **Foreign keys:** segment_id
- **Modules:** Routing/ranking/realtime

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| segment_id | object |  | No | References road_segments.segment_id |
| timestamp | object | ISO 8601 | No |  |
| traffic_level | object |  | No |  |
| free_flow_speed_kmh | float64 | km/h | No |  |
| current_speed_kmh | float64 | km/h | No |  |
| delay_factor | float64 |  | No |  |

## `realtime/events.csv.gz`

- **Purpose:** Chronological event stream for deterministic replay
- **Primary key:** event_id
- **Foreign keys:** entity_id references trip/station/segment by event type
- **Modules:** Week 5 replay

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Decision/ranking event identifier; join to demand label/feature by event_id |
| timestamp | object | ISO 8601 | No |  |
| event_type | object |  | No |  |
| entity_id | object |  | No |  |
| payload_json | object | JSON | No |  |

## `labels/map_matching_labels.csv.gz`

- **Purpose:** Ground-truth segment/direction per GPS observation
- **Primary key:** observation_id
- **Foreign keys:** observation_id, true_segment_id
- **Modules:** Map-matching training/evaluation label

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| observation_id | object |  | No |  |
| true_segment_id | object |  | No | References road_segments.segment_id |
| true_latitude | float64 | degrees WGS84 | No |  |
| true_longitude | float64 | degrees WGS84 | No |  |
| true_direction | object |  | No |  |

## `training/map_matching_candidates.csv.gz`

- **Purpose:** Selected candidate segments for map-matching training/evaluation
- **Primary key:** observation_id + candidate_segment_id
- **Foreign keys:** observation_id, candidate_segment_id
- **Modules:** Map-matching training/evaluation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| observation_id | object |  | No |  |
| candidate_segment_id | object |  | No | References road_segments.segment_id |
| distance_to_segment_m | float64 | m | No |  |
| projected_lat | float64 | degrees WGS84 | No |  |
| projected_lon | float64 | degrees WGS84 | No |  |
| heading_difference_deg | float64 | degrees | No |  |
| is_correct | bool |  | No | Map-matching candidate label |
| hard_negative | bool |  | No | Map-matching negative difficulty marker |

## `training/map_matching_candidates_with_split.csv.gz`

- **Purpose:** Map-matching candidates with trip-safe train/validation/test assignment
- **Primary key:** observation_id + candidate_segment_id
- **Foreign keys:** observation_id, candidate_segment_id, trip_id
- **Modules:** Map-matching training/evaluation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| observation_id | object |  | No |  |
| candidate_segment_id | object |  | No | References road_segments.segment_id |
| distance_to_segment_m | float64 | m | No |  |
| projected_lat | float64 | degrees WGS84 | No |  |
| projected_lon | float64 | degrees WGS84 | No |  |
| heading_difference_deg | float64 | degrees | No |  |
| is_correct | bool |  | No | Map-matching candidate label |
| hard_negative | bool |  | No | Map-matching negative difficulty marker |
| trip_id | object |  | No | References trips.trip_id |
| split | object |  | No | Trip-level split: train / validation / test |

## `labels/demand_labels.csv`

- **Purpose:** Service-demand target labels at multiple trip decision snapshots
- **Primary key:** event_id
- **Foreign keys:** trip_id
- **Modules:** Demand training/evaluation label

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Decision/ranking event identifier; join to demand label/feature by event_id |
| trip_id | object |  | No | References trips.trip_id |
| timestamp | object | ISO 8601 | No |  |
| need_service | bool |  | No |  |
| service_type | object |  | Yes | Target energy service values: CHARGING / BATTERY_SWAP (or ANY for unconstrained DRIVER_REQUEST; NULL for need_service=False or unresolved AUTO; note: NONE is not an energy service type) |
| reason_code | object |  | No |  |

## `training/demand_features.csv`

- **Purpose:** Leakage-safe demand features at multiple trip decision snapshots
- **Primary key:** event_id
- **Foreign keys:** trip_id
- **Modules:** Demand training/evaluation features

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Decision/ranking event identifier; join to demand label/feature by event_id |
| trip_id | object |  | No | References trips.trip_id |
| timestamp | object | ISO 8601 | No |  |
| snapshot_index | int64 |  | No |  |
| trip_progress_pct | float64 | % | No |  |
| soc_pct | float64 | % | No |  |
| estimated_remaining_range_km | float64 | km | No |  |
| remaining_trip_distance_km | float64 | km | No |  |
| reserve_buffer_km | float64 | km | No |  |
| consumption_wh_per_km | float64 | Wh/km | No |  |
| minimum_safe_soc_pct | float64 | % | No |  |
| charging_supported | bool |  | No |  |
| swap_supported | bool |  | No |  |
| connector_type | object |  | No |  |
| battery_type | object |  | No |  |
| split | object |  | No | Trip-level split: train / validation / test |

## `labels/candidate_labels.csv`

- **Purpose:** Full Candidate Search evaluation output for every service decision event Ã— station
- **Primary key:** event_id + station_id
- **Foreign keys:** event_id â†’ demand_labels.event_id; station_id â†’ stations.station_id
- **Modules:** Candidate Search evaluation; source contract for ranking

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Service decision event |
| station_id | object |  | No | Candidate station |
| service_type | object |  | No | NONE / CHARGING / BATTERY_SWAP |
| eligible | bool |  | No | Only `true` rows may enter ranking |
| reason | object |  | No | ELIGIBLE / INCOMPATIBLE / OFFLINE / FULL / UNREACHABLE / INSUFFICIENT_SOC_TO_REACH / NO_SERVICE_NEEDED / NO_SWAP_BATTERY / EXCESSIVE_QUEUE |
| network_distance_m | float64 | m | Yes | Network reachability/reference distance |
| soc_feasible | bool |  | No | Range feasibility to station with configured buffer |
| operating_status | object |  | No | State at `state_timestamp` |
| available_service_slots | int64 | slots | No | Charging slots for CHARGING; swap slots for BATTERY_SWAP |
| available_swap_batteries | int64 | batteries | No | Relevant for BATTERY_SWAP; 0 for CHARGING |
| available_capacity | int64 | slots/services | No | CHARGING=available charging slots; SWAP=min(available swap slots,batteries) |
| queue_length | int64 | vehicles | No | Queue for the requested service |
| estimated_wait_min | float64 | min | No | Wait for the requested service |
| service_time_min | float64 | min | No | Requested station service time; unsupported service may be 0 and reason INCOMPATIBLE |
| state_timestamp | object | ISO 8601 | No | Temporal state used for eligibility |

## `training/ranking_reference.csv`

- **Purpose:** Eligible-only grouped station-ranking training/evaluation reference
- **Primary key:** event_id + station_id
- **Foreign keys:** event_id, trip_id, station_id; every row must join to candidate_labels with eligible=true
- **Modules:** Week 4 ranking training/evaluation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Service decision event |
| trip_id | object |  | No | References trips.trip_id |
| station_id | object |  | No | Must be eligible in Candidate Search |
| service_type | object |  | No | CHARGING / BATTERY_SWAP |
| split | object |  | No | Trip-level train / validation / test |
| eligible_candidate_count | int64 | stations | No | Count before top-N cap |
| ranking_group_size | int64 | stations | No | `min(eligible_candidate_count, 8)`; variable 1..8 |
| is_ltr_group | bool |  | No | True only when group size >=2 |
| candidate_eligible | bool |  | No | Always true by contract |
| driver_to_station_distance_m | float64 | m | No | Network reference |
| driver_to_station_eta_min | float64 | min | No | Network reference |
| station_to_destination_distance_m | float64 | m | No | Network reference |
| station_to_destination_eta_min | float64 | min | No | Network reference |
| direct_driver_to_destination_distance_m | float64 | m | No | Direct-route reference |
| direct_driver_to_destination_eta_min | float64 | min | No | Direct-route reference |
| detour_distance_m | float64 | m | No | Via-station extra distance |
| detour_time_min | float64 | min | No | Via-station extra time |
| traffic_delay_factor_driver_leg | float64 | factor | No | Traffic adjustment |
| traffic_delay_factor_station_leg | float64 | factor | No | Traffic adjustment |
| traffic_adjusted_eta_min | float64 | min | No | Traffic-adjusted travel ETA |
| queue_wait_min | float64 | min | No | Service-specific queue wait |
| service_time_min | float64 | min | No | CHARGING=18; BATTERY_SWAP=6 |
| total_eta_min | float64 | min | No | traffic ETA + queue wait + service time |
| available_capacity | int64 | services | No | Service-specific usable capacity |
| operating_status | object |  | No | Eligible rows are OPEN |
| soc_feasible | bool |  | No | Eligible rows are feasible |
| ranking_cost_label | float64 | score | No | Baseline v3 documented in config/ranking_baseline.json |
| reference_rank | int64 | rank | No | 1=lowest documented baseline cost |
| is_reference_best | bool |  | No | True only for rank 1 |

## `labels/recommendation_labels.csv`

- **Purpose:** Evaluation-only recommendation reference for every service decision event; never runtime input
- **Primary key:** event_id
- **Foreign keys:** event_id; reference_station_id when present
- **Modules:** Recommendation evaluation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| event_id | object |  | No | Service decision event |
| eligible_candidate_count | int64 | stations | No | Recomputed from Candidate Search |
| has_recommendation | bool |  | No | True iff eligible_candidate_count > 0 |
| reference_station_id | object |  | Yes | Must be eligible; null when no eligible station |
| label_method | object |  | No | Documented eligible-only ranking baseline or NO_ELIGIBLE_STATION |

## `training/trip_splits.csv`

- **Purpose:** Leakage-safe split assignment at trip granularity
- **Primary key:** trip_id
- **Foreign keys:** trip_id
- **Modules:** All training tasks

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| trip_id | object |  | No | References trips.trip_id |
| split | object |  | No | Trip-level split: train / validation / test |

## `scenarios/scenario_coverage.csv`

- **Purpose:** Quantitative scenario evidence and validator result
- **Primary key:** scenario_id
- **Foreign keys:** example_trip_id, example_event_id, evidence entities
- **Modules:** Cross-module semantic evaluation

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| scenario_id | object |  | No | Scenario identifier; quantitative condition evidence in scenarios/scenario_coverage.csv |
| trip_count | int64 |  | No |  |
| example_trip_id | object |  | No |  |
| example_event_id | object |  | No |  |
| validator_status | object |  | No |  |
| primary_metric | object |  | No |  |
| primary_value | float64 |  | No |  |
| operator | object |  | No |  |
| threshold | float64 |  | No |  |
| secondary_metric | object |  | Yes |  |
| secondary_value | object |  | Yes |  |
| evidence_entity_a | object |  | Yes |  |
| evidence_entity_b | object |  | Yes |  |
| evidence_timestamp | object |  | Yes |  |
| before_timestamp | object | ISO 8601 | Yes |  |
| after_timestamp | object | ISO 8601 | Yes |  |
| evidence_note | object |  | Yes |  |

## Supporting metadata / validation files

- `config/generation_config.json`: generator seed, volume/frequency settings and V1.1 semantic thresholds.
- `config/ranking_baseline.json`: exact ranking candidate-pool assumptions, cost formula and penalties.
- `validation/data_counts.json`: record counts after patch.
- `validation/validation_results.json` / `.csv`: structural + semantic validation results.
- `validation/scenario_validation_results.json`: 21 scenario assertions and quantitative evidence.
- `validation/map_matching_candidate_stats.json`: positive/negative/hard-negative and split coverage.
- `validation/demand_distribution.json`: demand class distribution.
- `validation/ranking_stats.json`: ranking rows/groups/splits.
- `validation/pbf_integrity.json`: SHA-256 equality check against the originally uploaded raw PBFs plus the Cáº§u Thanh TrÃ¬ warning.
- `map/processed/pbf_diff.csv`: explicit baseline vs patched OSM tag diff; raw PBFs remain unchanged.


## `vehicles/vehicle_model_catalog.csv`

- **Purpose:** Canonical VinFast vehicle model capability reference
- **Primary key:** vehicle_model
- **Modules:** Demand, compatibility, candidate search

| Column | Type | Unit | Nullable | Relationship / notes |
|---|---|---|---|---|
| vehicle_model | object |  | No | VinFast model name (project-internal, not official branding) |
| vehicle_category | object |  | No | EV_CAR or EV_MOTORBIKE |
| battery_architecture | object |  | No | FIXED_TRACTION_PACK / FIXED_OR_INTEGRATED_LFP / REMOVABLE_SWAP_MODULE |
| battery_capacity_kwh | float64 | kWh | No | Nominal battery capacity; null for REMOVABLE_SWAP_MODULE models |
| battery_module_capacity_kwh | float64 | kWh | Yes | For swap-capable models; null otherwise |
| max_battery_modules | int64 |  | Yes | For swap-capable models; null otherwise |
| charging_supported | bool |  | No |  |
| swap_supported | bool |  | No |  |
| public_swap_compatible | bool |  | No | True only for EVO, EVO_LITE, FELIZ_II, VIPER |
| charging_interface_class | object |  | No | CCS2_TYPE2 for cars; VINFAST_MOTORCYCLE_CHARGING for motorcycles |
| swap_battery_family | object |  | Yes | VINFAST_SWAP_LFP_1_5_KWH for swap-capable models; null otherwise |
| capability_source_class | object |  | No | VINFAST_OFFICIAL_BATTERY_SPEC for official data; PROJECT_SIMULATION_ASSUMPTION for synthetic fields |

**Note:** charging_interface_class and swap_battery_family are project-internal normalized names.
They do NOT reflect official VinFast product terminology.

## `vehicles/vehicles.csv` — V1.3 additions

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| vehicle_model | object |  | No | References vehicle_model_catalog.vehicle_model |
| battery_architecture | object |  | No | From catalog |
| battery_module_capacity_kwh | float64 | kWh | Yes | For swap-capable motorcycles |
| max_battery_modules | int64 |  | Yes | For swap-capable motorcycles |
| installed_battery_modules | int64 |  | Yes | For swap-capable motorcycles; 1 or 2 |
| public_swap_compatible | bool |  | No | True only for EVO/EVO_LITE/FELIZ_II/VIPER |
| charging_interface_class | object |  | No | CCS2_TYPE2 or VINFAST_MOTORCYCLE_CHARGING |
| swap_battery_family | object |  | Yes | VINFAST_SWAP_LFP_1_5_KWH for swap-capable models |

## `labels/demand_labels.csv` — V1.3 additions

| Column | Type | Unit | Nullable | Notes |
|---|---|---|---|---|
| request_source | object |  | No | AUTO_DETECTED or DRIVER_REQUEST |
| requested_service_type | object |  | No | CHARGING / BATTERY_SWAP / ANY |
| allowed_service_types | object |  | No | Semicolon-separated list of supported services |
| request_valid | bool |  | Yes | True/False for DRIVER_REQUEST; null for AUTO_DETECTED |
| current_soc_pct | float64 | % | No |  |
| estimated_remaining_range_km | float64 | km | No |  |
| remaining_trip_distance_km | float64 | km | No |  |
| safety_reserve_km | float64 | km | No |  |
| vehicle_model | object |  | No | From vehicles |
| vehicle_category | object |  | No | EV_CAR or EV_MOTORBIKE |
| public_swap_compatible | bool |  | No |  |
| installed_battery_modules | int64 |  | Yes | For swap-capable motorcycles |

**service_type semantics (V1.3):**
- AUTO_DETECTED rows: service_type is the auto-detected needed service
- DRIVER_REQUEST rows: service_type is the explicitly requested service

## `labels/energy_service_requests.csv`

- **Purpose:** Week 3 Candidate Search data contract
- **Primary key:** event_id
- **Modules:** Week 3 Candidate Search, Week 4 Ranking

Same columns as `demand_labels.csv` with additional vehicle identifiers.

## `training/demand_need_service_features.csv`

- **Purpose:** Task A training features — binary need_service prediction
- **Primary key:** event_id
- **Modules:** Demand training

Features: soc_pct, estimated_remaining_range_km, remaining_trip_distance_km,
safety_reserve_km, consumption_wh_per_km, minimum_safe_soc_pct,
battery_capacity_kwh, usable_capacity_kwh, charging_supported, swap_supported,
vehicle_category, vehicle_model, trip_progress_pct.

## `training/demand_need_service_labels.csv`

- **Purpose:** Task A training labels — binary need_service
- **Primary key:** event_id

Columns: event_id, trip_id, split, need_service.

## `labels/candidate_labels.csv` — V1.3 additions

**Reason vocabulary (V1.3):** ELIGIBLE / INCOMPATIBLE / UNSUPPORTED_SERVICE / OFFLINE /
FULL / UNREACHABLE / INSUFFICIENT_SOC_TO_REACH / NO_SERVICE_NEEDED / NO_SWAP_BATTERY / EXCESSIVE_QUEUE

**service_type per row:** Each row represents ONE service type at ONE station.
A swap-capable vehicle may have multiple rows for the same (event_id, station_id) pair,
one per service type it supports.
