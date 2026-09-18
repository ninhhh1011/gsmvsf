# Routing Strategy

**Purpose:** Define the project-level routing domain model, engine strategy, and Week alignment for the full 6-week project.

**Status:** PLANNED — not yet implemented. Week 1 is frozen with OSRM-coupled map matching.

---

## 1. MENTOR DIRECTION

> "để có thể custom route nhiều nhất, dynamic nhất có thể,
> k gò bó vào việc dễ triển khai, phải nhìn bao quát"

**Interpretation:**
- Do NOT design around the easiest implementation
- Do NOT design around one routing engine's API
- Routing, candidate selection, recommendation, vehicle capability, and dynamic conditions must remain configurable and extensible
- Goal: **FLEXIBLE DOMAIN DESIGN + DYNAMIC ROUTING INPUTS + ENGINE INDEPENDENCE + MEASURABLE DECISIONS**

**NOT the goal:**
- MORE TECHNOLOGY
- Pre-implementing all engines
- Over-engineering

---

## 2. ROUTING VS RECOMMENDATION SEPARATION

This is the most critical architectural boundary.

```
Candidate Search
        ↓
Route Calculation (ROUTING)
        ↓
Route Metrics (geometry, distance, base ETA)
        ↓
Dynamic Service Metrics (queue, capacity, traffic) (RECOMMENDATION)
        ↓
Ranking / Recommendation
```

### What Routing Answers

- How can the driver reach this station?
- How long does it take? (base ETA)
- How far is it? (distance)
- What is the detour compared to going directly?

### What Recommendation Answers

- Which station should the driver choose?
- Based on: ETA + traffic-adjusted ETA + queue + capacity + service time + energy feasibility

### Boundary Rule

> **Recommendation logic must NOT depend directly on OSRM HTTP API. Use domain RouteResult.**

---

## 3. DOMAIN ROUTING MODEL

### 3.1 RouteRequest

```
RouteRequest
├── origin: Position (lat, lon)
├── destination: Position (lat, lon)
├── via: list[Position]  (optional intermediate stops)
├── vehicle_profile: VehicleRoutingProfile
├── service_context: ServiceContext  (enum: CHARGING | BATTERY_SWAP)
├── constraints: RouteConstraints
├── optimization_objective: OptimizationObjective
├── dynamic_context: DynamicRoutingContext  (inputs that affect route, not recommendation)
└── metadata: RouteMetadata
```

**Note on via routing:** The model supports multiple via points for future requirements (e.g., driver → station A → station B → destination). Week 3 initially uses origin → destination and origin → station.

### 3.2 Position

```
Position
├── latitude: float
├── longitude: float
└── node_id: Optional[str]  (road node ID for precision)
```

### 3.3 VehicleRoutingProfile

```
VehicleRoutingProfile
├── vehicle_id: str
├── vehicle_model: str  (e.g., "VF6", "VF8", "VinFast VF3")
├── vehicle_category: VehicleCategory  (enum: COMPACT | SEDAN | SUV | VAN)
├── battery_capacity_kwh: float
├── current_soc_percent: float
├── energy_consumption_kwh_per_km: float
├── service_capabilities: set[ServiceType]  (CHARGING, BATTERY_SWAP, or both)
├── max_charging_power_kw: Optional[float]
├── road_access_restrictions: set[RoadRestriction]  (enum values)
└── routing_profile_hint: Optional[str]  (engine-specific profile hint: "car", "ev", etc.)
```

**Design principle:** The profile captures vehicle reality, not engine reality. If a vehicle cannot use a road, that is a constraint. If an engine does not support that constraint natively, the routing adapter translates.

### 3.4 RouteConstraints

```
RouteConstraints
├── avoid_segments: set[str]  (OSM way IDs or segment IDs)
├── avoid_road_classes: set[RoadClass]  (enum: MOTORWAY, TRUNK, RESIDENTIAL, etc.)
├── max_detour_meters: Optional[float]
├── max_route_distance_m: Optional[float]
├── required_service_type: ServiceType  (station must support this)
├── station_compatibility: StationCompatibility  (which stations this vehicle can use)
├── exclude_temporarily_unavailable: bool  (exclude roads with temporary restrictions)
└── custom: dict[str, Any]  (engine-specific, parsed by adapter)
```

**Note:** Week 3 uses a minimal subset. This contract allows extension without breaking existing consumers.

### 3.5 OptimizationObjective

```
OptimizationObjective
├── primary: ObjectiveType
│   ├── MIN_TRAVEL_TIME      (default — fastest route)
│   ├── MIN_DISTANCE         (shortest path)
│   ├── MIN_DETOUR           (minimize detour from direct)
│   ├── MIN_GENERALIZED_COST (multi-factor: time + energy + tolls)
│   └── CUSTOM: str          (engine-specific named objective)
├── weights: Optional[ObjectiveWeights]
│   ├── time_weight: float
│   ├── distance_weight: float
│   └── energy_weight: float
└── traffic_aware: bool  (if engine supports real-time traffic)
```

**Design principle:** OSRM defaults to MIN_TRAVEL_TIME (shortest by time). The explicit enum makes this configurable. Recommendation ranking can also use these objectives without reverse-engineering OSRM flags.

### 3.6 DynamicRoutingContext

This captures data that **may affect the road path** (not recommendation ranking).

```
DynamicRoutingContext
├── timestamp: datetime
├── traffic_state: Optional[TrafficState]
│   ├── level: TrafficLevel  (enum: FREE, MODERATE, HEAVY, BLOCKED)
│   ├── delay_factor: float  (multiplier on base ETA)
│   └── affected_segments: set[str]
├── road_incidents: list[RoadIncident]
│   ├── segment_id: str
│   ├── incident_type: IncidentType  (enum: CLOSED, ONEWAY, CONSTRUCTION)
│   └── estimated_clear_time: Optional[datetime]
└── engine_config_overrides: Optional[EngineConfigOverrides]
    └── custom_cost_function: Optional[str]  (for engines that support it)
```

**Critical distinction:**

| Data | Effects ROUTE PATH? | Effects RANKING? |
|------|---------------------|------------------|
| traffic_state | YES (traffic-aware ETA) | YES (traffic-adjusted recommendation) |
| queue_status | NO (station internal) | YES (ranking score) |
| station_capacity | NO | YES (ranking score) |
| current_SOC | NO (pre-routing filter) | YES (energy feasibility) |
| road_incidents | YES (if engine supports) | INDIRECTLY (via route) |

### 3.7 RouteResult

```
RouteResult
├── status: RouteStatus  (enum: SUCCESS, NO_ROUTE, UNREACHABLE, ERROR)
├── geometry: Optional[str]  (polyline encoded)
├── distance_meters: float
├── duration_seconds: float
├── traffic_adjusted_duration_seconds: Optional[float]
├── legs: list[RouteLeg]
│   ├── from_position: Position
│   ├── to_position: Position
│   ├── distance_meters: float
│   ├── duration_seconds: float
│   └── geometry: Optional[str]
├── via_points: list[Position]  (intermediate stops reached)
├── detour_from_direct: Optional[DetourMetrics]
│   ├── direct_distance_m: float
│   ├── route_distance_m: float
│   ├── detour_distance_m: float
│   └── detour_ratio: float  (route/direct)
├── road_segment_ids: list[str]  (for downstream compatibility)
├── engine_metadata: EngineMetadata
│   ├── engine: str  ("osrm", "valhalla", "graphhopper")
│   ├── profile: str  ("driving", "car", etc.)
│   └── raw_response_id: Optional[str]
└── error_message: Optional[str]
```

---

## 4. ROUTING ENGINE ABSTRACTION

### 4.1 RoutingEngine Interface (Conceptual)

```python
class RoutingEngine(Protocol):
    """Project-level routing engine contract."""

    async def route(self, request: RouteRequest) -> RouteResult:
        """Compute a route from origin to destination."""
        ...

    async def route_via(
        self,
        origin: Position,
        waypoints: list[Position],
        destination: Position,
        request: RouteRequest,
    ) -> RouteResult:
        """Compute a route with intermediate stops."""
        ...

    async def matrix(
        self,
        sources: list[Position],
        destinations: list[Position],
        profile: VehicleRoutingProfile,
    ) -> MatrixResult:
        """Compute distance/duration matrix for multiple points."""
        ...

    async def map_match(
        self,
        coordinates: list[Position],
        profile: VehicleRoutingProfile,
    ) -> MapMatchResult:
        """Match GPS coordinates to road network."""
        ...
```

**Note:** Map Matching and Routing MAY use separate adapters. They share the Position type but serve different purposes. Week 1's `OsrmMapMatchingAdapter` remains as-is.

### 4.2 Adapter Pattern

```
Domain Layer
    │
    ▼
RoutingService  (uses RouteRequest, returns RouteResult)
    │
    ▼
RoutingEngineAdapter  (e.g., OsrmRoutingAdapter, ValhallaRoutingAdapter)
    │
    ▼
Engine HTTP API  (OSRM, Valhalla, GraphHopper)
```

**Principle:** Domain logic depends on project contracts, NOT on OSRM HTTP API.

---

## 5. ENGINE CAPABILITY MATRIX

| Capability | OSRM | GraphHopper | Valhalla |
|------------|------|-------------|----------|
| Basic routing | ✅ | ✅ | ✅ |
| Route with via | ✅ | ✅ | ✅ |
| Distance matrix | ✅ | ✅ | ✅ |
| Map Matching | ✅ | ✅ | ✅ |
| Vehicle profiles | limited (car, bike, foot) | extended | custom profiles |
| Custom costing | ❌ (profile rebuild) | ✅ (custom models) | ✅ (JSON costing) |
| Dynamic cost | ❌ | limited | ✅ |
| Avoid roads | ✅ (flags) | ✅ | ✅ |
| Traffic support | ❌ (no live traffic) | ✅ (optional) | ✅ (optional) |
| Multi-modal | limited | limited | limited |
| Runtime flexibility | low (rebuild needed) | medium | high |
| Performance/TPS | high | medium | medium |
| Operational complexity | low | medium | medium |
| Docker support | ✅ | ✅ | ✅ |

**Legend:**
- ✅ = Supported natively
- ⚠️ = Partial / needs research
- ❌ = Not supported
- NEEDS BENCHMARK = Capability not verified in this project

**Benchmark requirements before engine switch:**
- Route latency at p50, p95, p99
- Matrix latency for 30×30 (station × candidate)
- Map matching accuracy comparison
- Custom constraint support verification

---

## 6. ENGINE DECISION GATE

OSRM remains the initial engine. Consider alternatives when:

1. **Week 3 benchmark shows a specific OSRM limitation:**
   - Required route constraint cannot be expressed (e.g., vehicle-specific access)
   - Custom costing required and OSRM profile rebuild is too slow

2. **Dynamic requirements emerge:**
   - Real-time traffic cost propagation needed
   - Per-vehicle custom routing profiles at runtime

3. **Hard Week 3/4 use cases fail:**
   - EV range constraint routing (battery-aware path)
   - Multi-stop optimization (driver → station → station → destination)

4. **Evidence-based decision:**
   - Another engine materially improves requirement coverage
   - Benchmark data shows >20% improvement in relevant metric

**Do NOT switch because:**
- Another engine has more features on paper
- Vendor marketing suggests better performance
- Week 1/2 were difficult with OSRM

---

## 7. WEEK ALIGNMENT

### Week 2: Demand Detection

**Input:** Driver state from Week 1 + vehicle profile

```
EnergyServiceRequest
├── driver_id: str
├── driver_state: DriverState
│   ├── raw_position: Position
│   ├── matched_position: Optional[Position]
│   ├── road_segment_id: Optional[str]
│   └── direction: Optional[str]
├── vehicle_profile: VehicleRoutingProfile
├── request_source: RequestSource  (enum: REALTIME | REPLAY | BATCH)
├── allowed_service_types: set[ServiceType]
├── requested_service_type: Optional[ServiceType]  (if driver specified)
├── current_location: Position
├── destination: Optional[Position]
├── trip_context: Optional[TripContext]
│   ├── trip_id: Optional[str]
│   └── estimated_remaining_distance_m: Optional[float]
└── energy_state: EnergyState
    ├── current_soc_percent: float
    ├── estimated_range_km: float
    └── last_update_timestamp: datetime
```

**Routing boundary:** Week 2 does NOT call routing directly. It produces `EnergyServiceRequest` for Week 3.

### Week 3: Candidate Search + Routing

```
EnergyServiceRequest
        ↓
Candidate Search
        ↓
eligible station-service pairs
(station_id, service_type)
        ↓
For each candidate:
  RouteRequest(origin → station)
  RouteRequest(station → destination)
        ↓
RoutingEngine
        ↓
RouteResult
        ↓
route metrics:
  - ETA to station
  - distance to station
  - detour distance
  - ETA to destination
```

**Key concept:** Candidate entity is `(station_id, service_type)` not just `station_id`. One physical station may support multiple energy services.

### Week 4: Recommendation Ranking

Ranking consumes **generic features**, not routing engine fields:

```
RankingFeatures
├── route_eta_seconds: float  (from RouteResult.duration_seconds)
├── route_distance_meters: float  (from RouteResult.distance_meters)
├── detour_distance_meters: float  (from RouteResult.detour_from_direct)
├── traffic_adjusted_eta_seconds: Optional[float]
├── queue_length: int
├── available_capacity: int
├── service_time_seconds: float  (18 min for CHARGING, 6 min for BATTERY_SWAP)
├── energy_feasibility: bool  (can vehicle reach and leave station?)
├── waiting_time_seconds: Optional[float]  (estimated)
└── total_station_time_seconds: float  (queue_wait + service_time)
```

**RankingPolicy** (configurable):

```
RankingPolicy
├── weights: dict[FeatureName, float]
├── score_formula: ScoreFormula  (enum: WEIGHTED_SUM, LOGISTIC, ML_MODEL)
└── fallback_policy: FallbackPolicy  (what if all scores are tied/zero)
```

**Do NOT:** Hardcode weights in domain logic. Make them configurable via policy.

### Week 5: Realtime Dynamic Updates

```
Events that may invalidate recommendation:
├── GPS change → new origin → re-route
├── SOC change → energy feasibility check
├── traffic change → traffic-adjusted ETA update
├── queue change → ranking score update
├── station status change → capacity/availability update

Optimization (later implementation):
├── Invalidation check before full recomputation
├── Partial route update (OSRM supports via points)
└── Cache routes by (origin, destination, timestamp_bucket)
```

**Note:** Not every event requires full recomputation. Later implementation may add smart invalidation.

### Week 6: Performance Benchmarking

```
Performance targets (to be measured):
├── Route call latency: p50 < X ms, p95 < Y ms
├── Matrix call latency: p50 < X ms, p95 < Y ms
├── Candidate count per request: expected range
├── Cache hit rate: target > 60%
├── Concurrent drivers: target > 1000
└── Total recommendation latency: p95 < 500 ms

Benchmark targets:
├── Route calls: ~N per recommendation (origin→station, station→destination)
├── Matrix calls: N×M per candidate search (if used)
├── Engine latency: isolate OSRM vs business logic
└── Parallel request capacity: concurrent driver load
```

---

## 8. CURRENT OSRM ROLE

### Week 1 (Frozen)

- Map Matching: `POST /api/v1/map-match`, `POST /api/v1/drivers/{id}/location`
- Adapter: `OsrmMapMatchingAdapter`
- Direct OSRM HTTP API usage in business logic: ✅ contained in adapter

### Week 2 (Planned)

- No routing changes
- Demand Detection produces `EnergyServiceRequest`

### Week 3 (Planned)

- RoutingService introduced
- `OsrmRoutingAdapter` implements `RoutingEngine` interface
- Candidate routing uses domain `RouteRequest` → `RouteResult`
- Original OSRM map matching adapter remains unchanged

### Week 4+ (Planned)

- Recommendation ranking uses `RouteResult` fields
- Engine can be replaced without changing ranking logic
- Benchmark gates engine decision (see Section 6)

---

## 9. FILES UPDATED BY THIS DOCUMENT

This document defines planned architecture. It does NOT modify working code.

**Updated files:**
- `docs/ROUTING_STRATEGY.md` — new (this file)
- `docs/ARCHITECTURE.md` — updated with routing domain layer
- `docs/DECISIONS.md` — ADR-008 added for engine-independent routing
- `AGENTS.md` — routing architecture rule added

---

## 10. REVISION HISTORY

| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | Initial | Mentor direction: flexible dynamic routing |
