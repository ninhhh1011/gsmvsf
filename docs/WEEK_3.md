# WEEK 3: CANDIDATE SEARCH & ENGINE-INDEPENDENT ROUTING

**Project:** VinFast EV Charging & Battery-Swap Recommendation System  
**Milestone:** Week 3 Complete  
**Deliverables:** Candidate Search Pipeline, Engine-Independent Routing Domain, OSRM Routing Adapter, Multi-Leg Route & Detour Calculations, Deterministic Candidate Eligibility, REST API (`/api/v1/candidate-search`), Dataset V1.3.1 Evaluation Replay.

---

## 1. Official Week 3 Scope & Objectives

Week 3 consumes the normalized `EnergyServiceRequest` produced by Week 2 Demand Detection and answers:
1. Which station/service alternatives are physically compatible with the vehicle?
2. Which stations are operational and have capacity to serve the vehicle?
3. Which stations are reachable with the driver's current energy state?
4. What is the route from driver → station?
5. What is the route from station → destination?
6. What are the key routing metrics:
   - Base ETA / route duration
   - Network distance
   - Via-route distance and duration
   - Detour distance and detour duration
7. Return a clean, evaluated candidate set for Week 4 Ranking.

### Strict Architectural Boundaries
- **Week 3 does NOT decide**: "Which candidate is the final best station?"
- **No Ranking Leakage**: No ranking weights, no ranking scores, no recommendations.
- **Strict Ordering**: ALL STATIONS → EXPAND SERVICE ALTERNATIVES → FULL ELIGIBILITY → ELIGIBLE CANDIDATES. Never filter top-N by Euclidean distance prior to eligibility evaluation.
- **Labels are Evaluation-Only**: `dataset_v1/labels/candidate_labels.csv` is strictly used for testing and offline evaluation. Runtime logic derives decisions dynamically.

---

## 2. System Architecture & Boundaries

Aligned with the mentor directive:
> *"custom route nhiều nhất, dynamic nhất có thể, không gò bó vào việc dễ triển khai, phải nhìn bao quát"*

```
                    Week 2: Demand Detection
                               │ (EnergyServiceRequest)
                               ▼
               ┌───────────────────────────────┐
               │    CandidateSearchService     │
               └───────────────┬───────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       ▼                       ▼                       ▼
┌──────────────┐      ┌─────────────────┐     ┌─────────────────┐
│StationCatalog│      │EligibilityEngine│     │Routing Domain   │
│(30 stations) │      │(Deterministic   │     │(RouteRequest,   │
│              │      │ Precedence)     │     │ RouteResult)    │
└──────────────┘      └─────────────────┘     └────────┬────────┘
                                                       │
                                                       ▼
                                            ┌─────────────────────┐
                                            │<<RoutingEngine>>    │
                                            │Protocol             │
                                            └──────────┬──────────┘
                                                       │
                                         ┌─────────────┴─────────────┐
                                         ▼                           ▼
                              ┌────────────────────┐      ┌────────────────────┐
                              │ OSRMRoutingAdapter │      │ MockRoutingAdapter │
                              │ (/route/v1/driving)│      │ (In-memory/offline)│
                              └────────────────────┘      └────────────────────┘
```

---

## 3. Candidate Identity & Multi-Service Expansion

### 3.1 Candidate Identity
Candidate identity is strictly represented as the composite tuple:
$$\text{Candidate Identity} = (\text{station\_id}, \text{service\_type})$$

This ensures that multi-service physical stations (e.g. S005, S010, S020, S025 which provide both `CHARGING` and `BATTERY_SWAP`) produce **two distinct candidate alternatives** for swap-capable vehicles.

### 3.2 Service Expansion
- **Car**: Only `CHARGING` is evaluated → yields 30 candidate alternatives across all 30 stations.
- **Charge-Only Motorcycle**: Only `CHARGING` is evaluated → yields 30 candidate alternatives.
- **Swap-Capable Motorcycle (AUTO Unresolved)**: Evaluates BOTH `CHARGING` and `BATTERY_SWAP` → yields 60 candidate alternatives (30 charging + 30 swap).
- **Driver Request (ANY)**: Evaluates all allowed service types for the vehicle without forcing premature resolution.

---

## 4. Candidate Eligibility & Deterministic Precedence

Eligibility is evaluated using the exact deterministic chain frozen in Dataset V1.3.1:

```
Routing Reachability (np.isfinite(dist))
  ├── False ──► UNREACHABLE
  └── True
        ▼
Physical & Connector Compatibility
  ├── False ──► INCOMPATIBLE
  └── True
        ▼
Operational Status (status == 'OPEN')
  ├── False ──► OFFLINE
  └── True
        ▼
Swap Battery Inventory (service == BATTERY_SWAP and slots > 0 and batt <= 0)
  ├── True ──► NO_SWAP_BATTERY
  └── False
        ▼
Capacity (capacity <= 0)
  ├── True ──► FULL
  └── False
        ▼
Queue Wait Time (estimated_wait_min > 90.0 min)
  ├── True ──► EXCESSIVE_QUEUE
  └── False
        ▼
Energy Feasibility to Station (dist_km + 0.5 <= remaining_range_km)
  ├── False ──► INSUFFICIENT_SOC_TO_REACH
  └── True ──► ELIGIBLE
```

---

## 5. Multi-Leg Routing & Detour Calculations

### 5.1 Route Legs
For each candidate station and destination:
- **Leg 1 (Driver → Station)**: $D_{1}$, $T_{1}$
- **Leg 2 (Station → Destination)**: $D_{2}$, $T_{2}$
- **Direct Route (Driver → Destination)**: $D_{\text{direct}}$, $T_{\text{direct}}$ (computed once per request and cached)

### 5.2 Derived Metrics
$$\text{Via Total Distance} = D_{\text{via}} = D_{1} + D_{2}$$
$$\text{Via Total Duration} = T_{\text{via}} = T_{1} + T_{2}$$
$$\text{Detour Distance} = \Delta D = \max(0.0, D_{\text{via}} - D_{\text{direct}})$$
$$\text{Detour Duration} = \Delta T = \max(0.0, T_{\text{via}} - T_{\text{direct}})$$
$$\text{Base ETA to Station} = T_{1}$$

### 5.3 Missing Destination Fallback
When destination coordinates are not provided:
- Leg 1 is computed normally.
- Leg 2 and direct route are skipped.
- Destination distance, direct distance, and detour metrics are returned as `None`.
- Station candidates are evaluated on reachable and energy feasibility without error.

---

## 6. Energy Feasibility to Station

Candidate Search evaluates whether the vehicle can physically reach the station on current battery state:
$$\text{soc\_feasible} = \left(\frac{\text{network\_distance\_m}}{1000.0} + 0.5 \le \text{estimated\_remaining\_range\_km}\right)$$
- Always uses road network distance, never straight-line Euclidean distance as proof.
- Uses canonical 0.5 km safety reserve buffer.

---

## 7. Performance Baseline

Measured using 100 end-to-end candidate search executions evaluating all 30 stations and 60 service alternatives:

| Metric | Measured Value |
|---|---|
| End-to-End Latency (Min) | 61.19 ms |
| End-to-End Latency (Median) | 86.38 ms |
| End-to-End Latency (Mean) | 157.43 ms |
| End-to-End Latency (P90) | 156.14 ms |
| End-to-End Latency (P95) | 285.43 ms |
| Route Calls per Search | 61 (1 direct route + 30 driver→station + 30 station→dest) |
| Throughput | 11.6 searches / second |

---

## 8. Dataset V1.3.1 Replay Evaluation

Runtime candidate eligibility was evaluated against all 31,440 canonical rows in `dataset_v1/labels/candidate_labels.csv`:

```
==================================================
DATASET V1.3.1 REPLAY EVALUATION REPORT
==================================================
Total Rows Evaluated: 31440
Eligible/Ineligible Agreement: 31440/31440 (100.0%)
Reason Code Agreement: 31440/31440 (100.0%)
Confusion Matrix: TP=7474, TN=23966, FP=0, FN=0
  CHARGING: Total=25440, Eligible Agreement=100.0%, Reason Agreement=100.0%
  BATTERY_SWAP: Total=6000, Eligible Agreement=100.0%, Reason Agreement=100.0%
```

---

## 9. Week 4 Handoff Contract

Candidate Search produces `CandidateSearchResult` containing a list of `EvaluatedCandidate` records. Each candidate provides Week 4 Ranking with:
- `station_id`: Unique station identifier
- `service_type`: `CHARGING` or `BATTERY_SWAP`
- `eligible`: Boolean flag (`True` if all eligibility criteria met)
- `reason`: Explainable reason code (`ELIGIBLE`, `OFFLINE`, `FULL`, `INCOMPATIBLE`, `INSUFFICIENT_SOC_TO_REACH`, etc.)
- `station_latitude`, `station_longitude`: Geographic position
- `network_distance_m`: True road distance to station
- `soc_feasible`: Boolean reachability proof
- `operational`:
  - `operating_status`: Operational state (`OPEN`, `OFFLINE`)
  - `available_service_slots`: Available bays
  - `available_swap_batteries`: Charged swap batteries
  - `available_capacity`: Usable capacity
  - `queue_length`: Waiting vehicles
  - `estimated_wait_min`: Estimated queue wait time
  - `service_time_min`: Nominal service duration
- `route_metrics`:
  - `distance_to_station_m`: Route distance to station
  - `duration_to_station_s`: Base ETA to station
  - `distance_station_to_dest_m`: Leg 2 distance
  - `via_total_distance_m`: Total trip distance via station
  - `detour_distance_m`: Added distance over direct route
  - `detour_duration_s`: Added travel time over direct route

**Week 4 Ranking Boundary**: Week 4 will filter `[c for c in result.candidates if c.eligible]` and apply multi-criteria scoring (travel time + queue wait + service time + detour + battery availability) to produce the final recommendation.
