# REQUIREMENT_DATA_MATRIX — Dataset V1.2

| Requirement | Runtime / source data | Features / columns | Training / labels | Evaluation / semantic evidence |
|---|---|---|---|---|
| Project-wide linked operational data | drivers, vehicles, trips, road network, trajectories, GPS, SOC, stations, temporal state | stable IDs, timestamps, road refs, compatibility refs | labels remain separate from runtime input | 163/163 validations PASS; 21/21 scenarios PASS |
| Week 1 — Map Matching | `road_nodes`, `road_segments`, `true_trajectories`, `gps_observations` | geometry, direction, heading, GPS accuracy, projected candidate distance, heading difference | `map_matching_labels`, `is_correct`, `hard_negative` | 5,029 selected observations; positive + negative guaranteed; 2,619 hard negatives |
| Week 2 — Demand Detection | vehicles, trips, SOC history | SOC, remaining range/trip, reserve, consumption, safe SOC, service capability | 1,200 demand labels: NONE 352 / CHARGING 448 / BATTERY_SWAP 400 | NEED_SWAP vehicle capability + BATTERY_SWAP assertions; trip-safe splits |
| Week 3 — Candidate Search | stations + service-specific station status + service-specific queue + road graph + demand output | compatibility, network reachability, station status, service capacity, service queue, SOC feasibility | `candidate_labels`: eligible + reason | eligibility recomputed independently; ranking/recommendation may only consume `eligible=true` |
| Week 3 — Charging capacity | station_status + station master | `available_charging_slots`, `occupied_charging_slots`, `charging_slots` | none | CHARGING capacity = available charging slots; mixed-station bounds validated |
| Week 3 — Swap capacity | station_status + station master | `available_swap_slots`, `occupied_swap_slots`, `available_swap_batteries`, `swap_slots` | none | BATTERY_SWAP capacity = min(swap slots available, batteries available); both bounds validated |
| Week 3 — Service time / queue | queue + station status | charging/swap service time, queue length, active service count, wait | none | CHARGING uses 18 min; BATTERY_SWAP uses 6 min; wait formula independently validated |
| Week 3 — Routing reference | existing road graph + event position + station access + destination | driver→station, station→destination, direct distance/ETA | evaluation/reference only | no road/PBF regeneration and no runtime route result hardcoding |
| Week 4 — Ranking | **eligible Candidate Search output only** + route/traffic/queue/service state | detour, traffic ETA, service-specific wait/time/capacity, SOC feasibility | `ranking_cost_label`, `reference_rank`, `is_reference_best` | 630 variable-size groups / 3727 rows; max 8; only eligible stations |
| Week 4 — Recommendation | eligible count + ranking reference | `has_recommendation`, reference station | `recommendation_labels` evaluation-only | iff eligible_count>0; reference station must be eligible; 218 events have no eligible station |
| Week 5 — Realtime | replay + service-specific station/queue/traffic state | GPS_UPDATE, SOC_UPDATE, STATION_STATUS_UPDATE, QUEUE_UPDATE, TRAFFIC_UPDATE | no recommendation label as runtime input | service-specific payloads + before/after scenario checks |
| Week 5 — Scenario evaluation | scenario coverage + source tables | quantitative thresholds/evidence | none | FARTHER_BUT_FASTER >=500 m farther and >=10 min faster; all 21 conditions PASS |
| Week 6 — Reproducibility | config + patch generators + counts + validators | deterministic thresholds and documented baseline | none | 163 checks, PBF byte integrity, human map warning retained |

## Candidate-to-ranking contract
`All Stations → Candidate Search → eligible == true → nearest/top-N eligible (N<=8) → Ranking`.

- 0 eligible: `has_recommendation=false`, no ranking group.
- 1 eligible: recommendation must return it; group can remain for evaluation but `is_ltr_group=false`.
- >=2 eligible: eligible candidates are ranked; `is_ltr_group=true`.

## Map routing caveat
**MAP WARNING — HUMAN CONFIRMATION REQUIRED:** `hanoi-patched.osm.pbf` changes OSM way `881947000` (Cầu Thanh Trì) from `motorcar=designated` to `motorcar=no`. Dataset V1.2 does not decide whether that edit is correct. Both PBFs remain unchanged; human confirmation is required before routing-map freeze.

## Scope boundary
No FastAPI, database, OSRM server, Docker application stack, Kafka, Redis, frontend, microservices or production infrastructure is created.
