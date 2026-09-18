# REQUIREMENT_DATA_MATRIX — Dataset V1.3.1

| Requirement | Runtime / source data | Features / columns | Training / labels | Evaluation / semantic evidence |
|---|---|---|---|---|
| Project-wide linked operational data | drivers, vehicles, trips, road network, trajectories, GPS, SOC, stations, temporal state | stable IDs, timestamps, road refs, compatibility refs | labels remain separate from runtime input | 152/152 validations PASS; 21/21 scenarios PASS |
| Week 1 — Map Matching | `road_nodes`, `road_segments`, `true_trajectories`, `gps_observations` | geometry, direction, heading, GPS accuracy, projected candidate distance, heading difference | `map_matching_labels`, `is_correct`, `hard_negative` | 5,029 selected observations; positive + negative guaranteed; 2,619 hard negatives |
| Week 2 — Demand Detection | vehicles, trips, SOC history, `vehicle_model_catalog` | SOC, remaining range/trip, reserve, consumption, safe SOC, service capability | Canonical ML: `demand_need_service_features.csv` (1,200 rows) & `demand_need_service_labels.csv` (1,200 rows; 848 positive, 352 negative, 70.7% pos); `demand_labels.csv` (3,824 rows) | AUTO_DETECTED swap-capable bike does NOT force swap (resolved_service_type=NULL); DRIVER_REQUEST(ANY) does NOT force charge; model-level capability (40 cars, 13 charge-only bikes, 7 swap bikes); NONE is not an energy service type; trip-safe splits (no leakage) |
| Week 3 — Candidate Search | stations + service-specific station status + service-specific queue + road graph + demand output | compatibility, network reachability, station status, service capacity, service queue, SOC feasibility | `candidate_labels`: eligible + reason (31,440 rows: 7,474 eligible, 23,966 ineligible) | Eligibility recomputed independently per service type; ranking/recommendation may only consume `eligible=true`; unresolved events evaluate both CHARGING + BATTERY_SWAP candidates |
| Week 3 — Charging capacity | station_status + station master | `available_charging_slots`, `occupied_charging_slots`, `charging_slots` | none | CHARGING capacity = available charging slots; mixed-station bounds validated |
| Week 3 — Swap capacity | station_status + station master | `available_swap_slots`, `occupied_swap_slots`, `available_swap_batteries`, `swap_slots` | none | BATTERY_SWAP capacity = min(swap slots available, batteries available); both bounds validated |
| Week 3 — Service time / queue | queue + station status | charging/swap service time, queue length, active service count, wait | none | CHARGING uses 18 min; BATTERY_SWAP uses 6 min; wait formula independently validated |
| Week 3 — Routing reference | existing road graph + event position + station access + destination | driver→station, station→destination, direct distance/ETA | evaluation/reference only | no road/PBF regeneration and no runtime route result hardcoding |
| Week 4 — Ranking | **eligible Candidate Search output only** + route/traffic/queue/service state | detour, traffic ETA, service-specific wait/time/capacity, SOC feasibility | `ranking_cost_label`, `reference_rank`, `is_reference_best` | 553 variable-size groups / 3,439 rows (all eligible only); max 8; 478 LTR groups (size >= 2) |
| Week 4 — Recommendation | eligible count + ranking reference | `has_recommendation`, reference station | `recommendation_labels` evaluation-only (848 rows: 553 has_rec=true, 295 has_rec=false) | iff eligible_count>0; reference station must be eligible; unsupported requests and AUTO need_service=false have no recommendation |
| Week 5 — Realtime | replay + service-specific station/queue/traffic state | GPS_UPDATE, SOC_UPDATE, STATION_STATUS_UPDATE, QUEUE_UPDATE, TRAFFIC_UPDATE | no recommendation label as runtime input | service-specific payloads + before/after scenario checks |
| Week 5 — Scenario evaluation | scenario coverage + source tables | quantitative thresholds/evidence | none | FARTHER_BUT_FASTER (DE001858) >=500 m farther and >=10 min faster; NEED_ENERGY_BOTH_ALLOWED; all 21 conditions PASS |
| Week 6 — Reproducibility | config + patch generators + counts + validators | deterministic thresholds and documented baseline | none | 152 checks, PBF byte integrity, human map warning retained |

## Candidate-to-ranking contract
`All Stations → Candidate Search → eligible == true → nearest/top-N eligible (N<=8) → Ranking`.

- 0 eligible: `has_recommendation=false`, no ranking group.
- 1 eligible: recommendation must return it; group can remain for evaluation but `is_ltr_group=false`.
- >=2 eligible: eligible candidates are ranked; `is_ltr_group=true`.

## Training Data Contract (V1.3.1)
- **Canonical ML Training:** `training/demand_need_service_features.csv` and `training/demand_need_service_labels.csv` contain ONLY AUTO_DETECTED events (1,200 samples: 848 positive / 352 negative). Zero DRIVER_REQUEST contamination. No label leakage inside features. Split by trip (105 train / 22 val / 23 test, 0 overlap).
- **Legacy Reference:** `training/demand_features.csv` is SUPERSEDED / DERIVED REFERENCE (NOT CANONICAL ML TRAINING INPUT). Contains both AUTO_DETECTED and DRIVER_REQUEST events with embedded labels.
- **Service Request Contract:** `labels/energy_service_requests.csv` provides the full request contract for downstream Candidate Search.

## Map routing caveat
**MAP STATUS — APPROVED:** `hanoi-patched.osm.pbf` is the primary OSRM map. Contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì). `hanoi-baseline.osm.pbf` is reference.

## Scope boundary
No FastAPI, database, OSRM server, Docker application stack, Kafka, Redis, frontend, microservices or production infrastructure is created.
