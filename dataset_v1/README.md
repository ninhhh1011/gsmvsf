# Dataset V1.2 — Driver Charging / Battery Swap Recommendation

This workspace is an in-place semantic patch of Dataset V1. No road-network rebuild and no application/backend setup was performed. It contains source data, generated operational data, labels, training/evaluation references, deterministic replay, generators and validation only.

## Map source status
- Raw PBFs remain byte-for-byte unchanged: `map/raw/hanoi-baseline.osm.pbf` and `map/raw/hanoi-patched.osm.pbf`.
- Current processed road representation derives from the patched working source.
- PBF integrity against the originally uploaded inputs: **PASS**.

**MAP STATUS — APPROVED:** `hanoi-patched.osm.pbf` is the primary OSRM map. Contains motorcar=no for OSM way 881947000 (Cầu Thanh Trì). `hanoi-baseline.osm.pbf` is reference.

## Patch V1.2 summary
- Ranking now consumes Candidate Search output: `All stations → candidate eligibility → eligible=true → optional nearest top-N eligible (max 8) → ranking`.
- A service event with 0 eligible stations has no recommendation; 1 eligible station returns that station; 2+ eligible stations are ranked. One-candidate groups remain evaluation/reference groups but are not LTR groups.
- CHARGING/SWAP state is service-specific. Mixed stations maintain independent charging and swap slot occupancy/capacity.
- BATTERY_SWAP capacity is `min(available_swap_slots, available_swap_batteries)`; CHARGING capacity is `available_charging_slots`.
- Service times are service-specific: CHARGING **18 min**, BATTERY_SWAP **6 min**. Queue wait uses the corresponding service queue and service time.
- `FARTHER_BUT_FASTER` now requires at least **500 m** additional network distance and at least **10 min** lower total ETA.
- Full independent validation: **163 PASS / 0 FAIL**; scenarios: **21/21 PASS**.

## Preserved V1.1 guarantees
- Demand samples: **1,200** = NONE 352 / CHARGING 448 / BATTERY_SWAP 400.
- NEED_SWAP uses swap-capable vehicles and BATTERY_SWAP labels.
- Trip-level train/validation/test split remains intact.
- Map-matching selected observations: **5,029**, every group has a positive and at least one negative; hard negatives preserved.
- Road network and both raw PBFs unchanged.

## Candidate / recommendation statistics
- Service decision events: **848**.
- Events with >=1 eligible station: **630**.
- Events with no eligible station: **218**.
- Exactly one eligible station: **83**.
- Two or more eligible stations: **547**.
- Recommendation labels: **848**, with recommendation=true for **630** and false for **218**.

## Ranking groups
Ranking has **630 groups / 3,727 rows**. Group sizes are variable and capped at 8:

| Group size | Events |
|---:|---:|
| 1 | 83 |
| 2 | 28 |
| 3 | 50 |
| 4 | 57 |
| 5 | 16 |
| 6 | 17 |
| 7 | 4 |
| 8 | 375 |

LTR-eligible groups (size >=2): **547**. Single-candidate evaluation groups: **83**.

The documented reference cost in `config/ranking_baseline.json` is:

`traffic_adjusted_eta_min + queue_wait_min + service_time_min + 0.25*detour_time_min + 0.002*detour_distance_m - 0.35*min(available_capacity,6)`

`labels/recommendation_labels.csv` and ranking reference labels are evaluation/training artifacts only and are not runtime inputs.

## Service-specific station state
`stations/station_status.csv.gz` contains:
- `available_charging_slots`, `occupied_charging_slots`
- `available_swap_slots`, `occupied_swap_slots`
- `available_swap_batteries`
- `charging_service_time_min`, `swap_service_time_min`

Invariants:
- `available_charging_slots + occupied_charging_slots <= charging_slots`
- `available_swap_slots + occupied_swap_slots <= swap_slots`
- CHARGING available capacity = `available_charging_slots`
- BATTERY_SWAP available capacity = `min(available_swap_slots, available_swap_batteries)`

`queue/queue_status.csv.gz` contains independent charging/swap queue lengths, active service counts, service times and estimated waits.

## FARTHER_BUT_FASTER evidence
Validated event `DE000580` / trip `T0073`: S028 is **542.9 m farther** by network distance than S026, while its total ETA is **13.472 min lower** (53.339 vs 66.811 min). Required meaningful margin: >=10 min.

## Key counts
| Dataset | Records |
|---|---:|
| road_nodes | 339,441 |
| road_segments | 701,407 |
| drivers | 60 |
| vehicles | 60 |
| trips | 150 |
| true_trajectory_points | 68,664 |
| gps_observations | 65,847 |
| soc_history | 68,664 |
| stations | 30 |
| station_status | 3,270 |
| queue_status | 3,270 |
| traffic_snapshots | 883,597 |
| realtime_events | 109,193 |
| map_matching_candidates | 27,042 |
| map_matching_selected_observations | 5,029 |
| demand_labels | 1,200 |
| candidate_labels | 36,000 |
| ranking_reference | 3,727 |
| ranking_event_groups | 630 |
| recommendation_labels | 848 |
| scenario_rows | 21 |


## Patch / validation workflow
For the current V1 workspace, the semantic patch sequence is:
1. `generators/05_patch_candidate_service_semantics.py`
2. `generators/05b_preserve_near_tie_scenario.py`
3. `generators/05c_sync_near_tie_state.py`
4. `validation/validate_dataset.py`

These are patch scripts over existing Dataset V1 artifacts. They do not download OSM, rebuild the road network, or set up an application project.
