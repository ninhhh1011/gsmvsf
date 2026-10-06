# Graph Report - build6week  (2026-10-06)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 2977 nodes · 7899 edges · 105 communities (70 shown, 35 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 890 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `8b9ecb8e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Energy Demand Detection
- Driver Trace State
- Ranking Recommendation APIs
- Driver State Manager
- Route History H3 Index
- Candidate Service Expansion
- Map Matching Models
- Station Compatibility Checks
- Snapshot Cache Services
- Route Family Clustering
- Map Matching Benchmark
- Ranking Context Features
- Route Data Import
- Candidate Eligibility
- Historical Familiarity
- Road Network Simulation
- Driver Mode Controller
- Service Semantic Patches
- Familiarity Integration
- Map Matching API
- Station State Ingestion
- Driver State Snapshots
- App Config Lifecycle
- State Ingestion Service
- Demand Energy Step API
- Demo Recommendation Workflow
- Location Ingestion
- Ranking Service Features
- Routing Benchmark Filters
- Route Family Management
- Routing Domain Models
- Redis Driver State
- Candidate Search API
- GPS Data Processing
- Routing Engine
- Tech View Controller
- Shared State Tests
- UI Components Renderer
- Week 5 Replay Tests
- Week 5 Benchmark Tests
- Bayesian Familiarity
- Historical Route Search
- Week 4 Evaluation Tests
- GraphHopper Adapter
- Family Clustering Tests
- Demo Spec Tests
- Leaflet Map Library
- Week 5 Eval Tests
- Prometheus Metrics
- Habitual Routes API
- Time Recency Weighting
- Demand Evaluation API
- Trajectory Replay Controller
- Position Multi-Leg Routing
- API Client
- Demo Map Controller
- H3 Corridor Generation
- Route History Importer
- Routing Engine Contract
- Snapshot Repository
- Load Testing
- Simulation Mode Controller
- Health Check Endpoints
- Driver State Store
- H3 Integration Tests
- Dataset Validation Suite
- H3 Signature Tests
- Demand API Tests
- Rate Limit Middleware
- Minified Utility JS
- GraphHopper Eval
- Architecture Diagrams
- Test Fixtures Mocks
- Minified Utility JS
- Minified Utility JS
- Security Checklist
- Minified Utility JS
- Congestion Routing Tests
- Demand ML Evaluation
- Synthetic Route Generation
- Minified Utility JS
- Health Endpoint Tests
- Familiarity Config Tests
- Canonical Validator
- Minified Utility JS
- Minified Utility JS
- Structured Logging
- Demo Package
- Energy Range Tests
- Car Rules Tests
- EV Recommendations

## God Nodes (most connected - your core abstractions)
1. `ServiceType` - 143 edges
2. `ReasonCode` - 79 edges
3. `DemandContext` - 65 edges
4. `EnergyServiceRequest` - 65 edges
5. `DriverTraceState` - 62 edges
6. `RequestSource` - 60 edges
7. `DriverModeController` - 57 edges
8. `StateError` - 53 edges
9. `RequestedServiceType` - 51 edges
10. `GraphHopperRoutingAdapter` - 47 edges

## Surprising Connections (you probably didn't know these)
- `performance()` --uses--> `RecommendationResult`  [INFERRED]
  scripts/verify_week4.py → backend/app/services/ranking/models.py
- `evaluate()` --uses--> `MapMatchingNoMatchError`  [INFERRED]
  scripts/evaluate_graphhopper_matching.py → backend/app/services/map_matching/engine.py
- `predict()` --uses--> `DemandContext`  [INFERRED]
  scripts/evaluate_week4.py → backend/app/services/demand/models.py
- `dataset_cases()` --uses--> `RequestedServiceType`  [INFERRED]
  scripts/verify_graphhopper.py → backend/app/services/demand/models.py
- `failures()` --uses--> `StateError`  [INFERRED]
  scripts/verify_week4.py → backend/app/services/snapshots/models.py

## Import Cycles
- None detected.

## Communities (105 total, 35 thin omitted)

### Community 0 - "Energy Demand Detection"
Cohesion: 0.03
Nodes (25): AutoDemandDetector, SafetyReservePolicy, get_capability_resolver(), reset_capability_resolver(), VehicleCapabilityResolver, DriverRequestProcessor, NeedServiceDecision, VehicleCapability (+17 more)

### Community 1 - "Driver Trace State"
Cohesion: 0.03
Nodes (15): canonical_payload_hash(), DriverTraceState, ensure_utc(), GPSObservation, haversine_distance(), make_naive(), DistanceTrigger, get_default_policy() (+7 more)

### Community 2 - "Ranking Recommendation APIs"
Cohesion: 0.03
Nodes (48): authorize_ingestion(), recommend(), RecommendationTelemetry, RecommendRequest, search_for_ranking(), DemandContext, RequestedServiceType, VehicleCategory (+40 more)

### Community 3 - "Driver State Manager"
Cohesion: 0.04
Nodes (30): DriverStateError, DriverStateManager, reset_driver_state_manager(), set_driver_state_manager(), snapshot_to_trace_state(), trace_state_to_snapshot(), DriverStateRepository, get_driver_state_repository() (+22 more)

### Community 4 - "Route History H3 Index"
Cohesion: 0.04
Nodes (11): Direction, RouteH3Index, RouteInvertedIndex, test_inverted_index(), HistoricalRoute, H3Signature, H3SignatureGenerator, H3Transition (+3 more)

### Community 5 - "Candidate Service Expansion"
Cohesion: 0.08
Nodes (36): determine_evaluable_services(), expand_candidate_pairs(), CandidateSearchRequest, EnergyServiceRequest, ReasonCode, RequestSource, test_car_expansion(), test_driver_request_any_expansion() (+28 more)

### Community 6 - "Map Matching Models"
Cohesion: 0.06
Nodes (17): GPSObservation, MapMatchRequest, MapMatchResponse, MatchedObservation, ResolutionStatus, ResolutionStatus, RouteConstrainedSegmentResolver, SegmentInfo (+9 more)

### Community 7 - "Station Compatibility Checks"
Cohesion: 0.06
Nodes (20): check_station_service_compatibility(), check_energy_feasibility_to_station(), floor_iso_timestamp(), _parse_tokens(), StationCatalog, StationRecord, stations(), test_car_compatibility() (+12 more)

### Community 8 - "Snapshot Cache Services"
Cohesion: 0.09
Nodes (31): get_ingestion(), get_workflow(), trigger_simulation_tick(), SnapshotCache, test_traffic_probe_uses_canonical_identity_and_consistent_speeds(), test_verification_statistics_and_source_request(), rows(), dynamic_demo() (+23 more)

### Community 9 - "Route Family Clustering"
Cohesion: 0.06
Nodes (12): test_route_family_cluster(), DivergencePoint, RejoinPoint, RoadLevelSimilarity, RouteSegments, SegmentInfo, SimilarityResult, test_road_similarity() (+4 more)

### Community 10 - "Map Matching Benchmark"
Cohesion: 0.07
Nodes (18): latency_summary(), run_benchmark(), main(), GPSObservation, load_all_trajectory_ids(), load_trajectory(), main(), replay_trajectory() (+10 more)

### Community 11 - "Ranking Context Features"
Cohesion: 0.08
Nodes (22): rank(), RankRequest, get_logger(), invalid_evidence(), CandidateRankingFeatures, CandidateSearchEvidence, CandidateStateChanged, ChangedCandidate (+14 more)

### Community 12 - "Route Data Import"
Cohesion: 0.06
Nodes (8): get_route_repository(), build_route_record(), import_routes(), load_trajectories(), main(), HistoricalRouteRecord, RouteFamilyRecord, RouteHistoryRepository

### Community 13 - "Candidate Eligibility"
Cohesion: 0.08
Nodes (26): evaluate_candidate_eligibility(), CandidateEligibilityReason, StationOperationalSnapshot, StationServiceCandidate, DriverRequestDecision, ServiceType, test_charge_only_motorcycle_resolves_to_charging(), test_low_soc_short_trip() (+18 more)

### Community 14 - "Historical Familiarity"
Cohesion: 0.07
Nodes (9): FamiliarityConfig, FamiliarityPenalty, FamiliaritySource, HistoricalFamiliarity, test_familiarity(), TestBayesianComparison, TestFamiliarityCostApplication, TestFamiliarityPenalty (+1 more)

### Community 15 - "Road Network Simulation"
Cohesion: 0.06
Nodes (26): blob_decode(), fields(), hav(), heading(), pbf_stats(), read_varint(), sha256(), add() (+18 more)

### Community 17 - "Service Semantic Patches"
Cohesion: 0.06
Nodes (25): add(), compatible(), floor_iso(), service_slots(), set_service_state(), tokens(), add(), auto_detect_service() (+17 more)

### Community 18 - "Familiarity Integration"
Cohesion: 0.08
Nodes (11): get_history_service(), HistoricalEvidence, HistoricalFamiliarityService, HistoryStatus, RouteHistoryConfig, TestFamiliarityBounds, TestIntegrationWithRanking, TestScaleProperties (+3 more)

### Community 19 - "Map Matching API"
Cohesion: 0.10
Nodes (19): get_map_matching_adapter(), get_map_matching_service(), get_segment_resolver(), map_match(), MapMatchingEngine, MapMatchingEngineError, MapMatchingEngineUnavailableError, MapMatchingInvalidRequestError (+11 more)

### Community 20 - "Station State Ingestion"
Cohesion: 0.06
Nodes (15): ingest_queue(), ingest_snapshot(), ingest_station(), ingest_traffic(), QueueSnapshot, SnapshotBase, StationStateSnapshot, RealtimeSimulator (+7 more)

### Community 21 - "Driver State Snapshots"
Cohesion: 0.06
Nodes (11): DriverTraceStateSnapshot, GPSObservation, InMemoryDriverStateRepository, MatchedState, test_gps_observation_roundtrip(), test_in_memory_repository_delete(), test_in_memory_repository_health(), test_in_memory_repository_list_drivers() (+3 more)

### Community 22 - "App Config Lifecycle"
Cohesion: 0.06
Nodes (13): Settings, lifespan(), app(), client(), dataset_path(), test_settings_defaults(), test_settings_validate_paths(), test_adapters_share_and_close_lifespan_client() (+5 more)

### Community 23 - "State Ingestion Service"
Cohesion: 0.11
Nodes (26): IngestionService, reject(), StateError, SnapshotResolver, repository(), station(), test_batch_conflict_rolls_back_and_id_collision(), test_candidate_search_evidence_is_immutable() (+18 more)

### Community 24 - "Demand Energy Step API"
Cohesion: 0.06
Nodes (20): calculate_energy_step(), DriverIntentApiRequest, EnergyStepRequest, EnergyStepResponse, evaluate_demand(), get_model_capability(), get_vehicle_capability(), list_vehicle_models() (+12 more)

### Community 25 - "Demo Recommendation Workflow"
Cohesion: 0.07
Nodes (19): create_app(), routing_error_handler(), RecommendationWorkflow, SnapshotCatalogView, test_demo_catalogs(), test_demo_page_serving(), test_demo_static_assets(), test_recommendation_consumes_selected_vehicle_and_dynamic_soc() (+11 more)

### Community 26 - "Location Ingestion"
Cohesion: 0.08
Nodes (18): _add_observation_with_cas(), _call_map_match(), get_driver_location(), get_trajectory_observations(), ingest_location(), list_drivers(), LocationIngestionRequest, LocationResponse (+10 more)

### Community 27 - "Ranking Service Features"
Cohesion: 0.21
Nodes (30): build_features(), catalog_digest(), operational_snapshot(), RankingPolicy, rank_features(), RankingService, candidate(), evidence() (+22 more)

### Community 28 - "Routing Benchmark Filters"
Cohesion: 0.08
Nodes (8): BenchmarkResult, main(), run_benchmark(), FilterResult, HardFilters, RouteMetadata, test_filters_and_weights(), TestHardFilters

### Community 29 - "Route Family Management"
Cohesion: 0.07
Nodes (4): RouteFamily, RouteFamilyCluster, RouteFamilyMember, TestRouteFamily

### Community 30 - "Routing Domain Models"
Cohesion: 0.11
Nodes (13): OptimizationObjective, RouteLeg, RouteRequest, RouteStatus, _haversine_meters(), MockRoutingAdapter, test_mock_adapter_implements_protocol(), test_mock_adapter_route_calculation() (+5 more)

### Community 31 - "Redis Driver State"
Cohesion: 0.09
Nodes (9): RedisDriverStateRepository, test_health_check_local(), test_health_check_redis_healthy(), test_health_check_redis_unhealthy(), test_local_manager_allows_local_operations(), test_production_manager_requires_redis(), test_production_manager_save_requires_redis(), test_production_manager_with_healthy_redis() (+1 more)

### Community 32 - "Candidate Search API"
Cohesion: 0.11
Nodes (15): evaluate_and_search(), get_candidate_service(), _routing_http_error(), search_candidates(), CandidateSearchResult, EvaluatedCandidate, CandidateSearchService, RoutingInvalidRequestError (+7 more)

### Community 33 - "GPS Data Processing"
Cohesion: 0.10
Nodes (15): build_normalized_df(), compute_sampling_stats(), haversine_m(), haversine_m_batch(), haversine_mv(), is_row_start(), load_and_validate(), main() (+7 more)

### Community 34 - "Routing Engine"
Cohesion: 0.10
Nodes (14): route(), CandidateRouteMetrics, raise_for_routing_failure(), RouteNotFoundError, RoutingEngineError, RoutingEngineUnavailableError, RoutingTimeoutError, RouteConstraints (+6 more)

### Community 35 - "Tech View Controller"
Cohesion: 0.15
Nodes (10): classifySystemHealth(), filterCandidates(), formatDemandInspector(), formatLocationInspector(), formatPipelineTiming(), formatRankingInspector(), formatRecommendationInspector(), formatRoutingInspector() (+2 more)

### Community 36 - "Shared State Tests"
Cohesion: 0.09
Nodes (14): api_available(), redis_available(), skip_if_no_api(), skip_if_no_redis(), test_concurrent_writes(), test_dedup_retention_boundary(), test_no_duplicate_observation_counting(), test_post_instance_a_get_instance_b() (+6 more)

### Community 37 - "UI Components Renderer"
Cohesion: 0.14
Nodes (21): ApiError, classifyEnergyWarning(), renderCandidateTable(), renderConflictAlert(), renderCostBreakdown(), renderEnergyWarningBanner(), renderPipelineLatency(), renderRecommendationCard() (+13 more)

### Community 38 - "Week 5 Replay Tests"
Cohesion: 0.12
Nodes (15): test_client_normalizes_only_equivalent_rounded_north_heading(), test_failure_counters_separate_second_conflict_graphhopper_and_database(), test_future_state_is_rejected(), test_representative_schedule_uses_source_events_and_causal_gps(), test_snapshot_advance_never_preloads_future_and_does_not_repeat_rows(), test_source_snapshot_lookup_accepts_nanosecond_decision_time(), assert_causal_result(), CausalSnapshots (+7 more)

### Community 39 - "Week 5 Benchmark Tests"
Cohesion: 0.12
Nodes (13): test_benchmark_counts_errors_and_stage_distributions(), test_benchmark_minimums(), main(), request(), measure_workload(), measured(), validate_counts(), generate_markdown_report() (+5 more)

### Community 41 - "Historical Route Search"
Cohesion: 0.08
Nodes (5): HistoricalRouteSearch, RouteFamily, RouteSearchResult, SimilarRouteResult, test_historical_route_search()

### Community 42 - "Week 4 Evaluation Tests"
Cohesion: 0.11
Nodes (17): test_common_pool_comparison_preserves_service_identity_and_pair_denominator(), test_full_pool_miss_can_be_common_pool_match(), test_report_counts_empty_and_missing_reference_without_fabricating_accuracy(), test_source_contexts_match_frozen_event_schedule_and_causal_gps(), main(), __init__(), baseline_orders(), compare_order() (+9 more)

### Community 43 - "GraphHopper Adapter"
Cohesion: 0.17
Nodes (14): _failure(), GraphHopperRoutingAdapter, _metric(), DynamicRoutingContext, VehicleRoutingProfile, request(), test_http_failure_classification(), test_malformed_success_is_engine_error() (+6 more)

### Community 45 - "Demo Spec Tests"
Cohesion: 0.07
Nodes (24): { test, expect }, author, bugs, url, description, devDependencies, @playwright/test, directories (+16 more)

### Community 46 - "Leaflet Map Library"
Cohesion: 0.08
Nodes (6): a(), Ci(), l(), me(), x(), ze()

### Community 47 - "Week 5 Eval Tests"
Cohesion: 0.14
Nodes (10): test_complete_offline_evaluation_uses_canonical_reference_locations(), test_prediction_hash_and_label_audit_are_required(), test_unfinished_inference_fails_before_any_label_access(), add(), floor_iso(), hav_m(), sha256(), completed_predictions() (+2 more)

### Community 48 - "Prometheus Metrics"
Cohesion: 0.08
Nodes (10): metrics(), metrics_endpoint(), observe_candidate_search(), observe_recommendation(), observe_route_call(), record_candidate_conflict(), record_db_fallback(), record_dependency_error() (+2 more)

### Community 49 - "Habitual Routes API"
Cohesion: 0.10
Nodes (12): compare_routes(), ComparisonResult, DriverHabitualResponse, ErrorResponse, get_driver_habitual(), get_history_status(), h3_lookup(), HistoryStatusResponse (+4 more)

### Community 50 - "Time Recency Weighting"
Cohesion: 0.11
Nodes (3): TimeRecencyWeight, WeightedScore, TestTimeRecencyWeight

### Community 51 - "Demand Evaluation API"
Cohesion: 0.14
Nodes (14): EvaluateAndSearchApiRequest, evaluate_driver_demand_with_realtime_state(), EvaluateDemandApiRequest, CurrentLocation, resolve_current_location(), utc(), valid_coordinates(), test_candidate_current_state_uses_existing_fields() (+6 more)

### Community 52 - "Trajectory Replay Controller"
Cohesion: 0.19
Nodes (4): approxDistMeters(), getElem(), ReplayState, TrajectoryReplayController

### Community 53 - "Position Multi-Leg Routing"
Cohesion: 0.17
Nodes (11): Position, MultiLegRouteCalculator, test_concurrent_station_metrics_produces_correct_results(), test_concurrent_with_semaphore_limits(), slow_route(), test_dependency_errors_are_never_unreachable(), test_multi_leg_exact_formulas_and_driver_repositioning(), test_multi_leg_missing_destination() (+3 more)

### Community 56 - "H3 Corridor Generation"
Cohesion: 0.13
Nodes (8): coords_to_h3_res11(), haversine_distance_m(), interpolate_points(), jitter_coord(), main(), query_graphhopper_route(), table_exists(), run_migration()

### Community 58 - "Routing Engine Contract"
Cohesion: 0.13
Nodes (6): RoutingEngine, test_api_candidate_search_eligible_only(), test_api_candidate_search_post(), test_api_evaluate_and_search(), test_graphhopper_adapter_satisfies_protocol(), test_graphhopper_routing_adapter_route()

### Community 62 - "Health Check Endpoints"
Cohesion: 0.17
Nodes (6): _database_ready(), dependencies_ready(), health(), ready(), _redis_ready(), test_readiness_requires_dependencies()

### Community 64 - "H3 Integration Tests"
Cohesion: 0.13
Nodes (5): MockLogger, test_bayesian_penalty_integration(), test_h3_overlap_calculation(), test_h3_signature_generation(), test_sequential_overlap()

### Community 65 - "Dataset Validation Suite"
Cohesion: 0.15
Nodes (4): compatible(), floor_iso(), get_station_queue(), tokens()

### Community 67 - "Demand API Tests"
Cohesion: 0.19
Nodes (6): app(), clean_state(), test_driver_request_car_battery_swap_rejected(), test_driver_request_swap_bike_any(), test_evaluate_auto_demand_swap_bike_unresolved(), test_get_vehicle_capability()

### Community 69 - "Minified Utility JS"
Cohesion: 0.24
Nodes (12): F(), G(), h(), j(), k(), ke(), ne(), e() (+4 more)

### Community 70 - "GraphHopper Eval"
Cohesion: 0.29
Nodes (7): distance_m(), distribution(), evaluate(), percentile(), rows(), score(), self_check()

### Community 71 - "Architecture Diagrams"
Cohesion: 0.51
Nodes (6): draw_arrow(), draw_box(), generate_architecture_diagram(), generate_avoidance_diagram(), generate_core_engine_diagram(), generate_data_flow_diagram()

### Community 72 - "Test Fixtures Mocks"
Cohesion: 0.33
Nodes (5): set_candidate_service(), setup_mock_service(), test_api_dependency_failures_are_explicit(), test_invalid_candidate_coordinates_are_client_error(), test_route_endpoint_domain_contract()

### Community 73 - "Minified Utility JS"
Cohesion: 0.22
Nodes (9): Ae(), be(), De(), ei(), Ie(), ii(), p(), pe() (+1 more)

### Community 74 - "Minified Utility JS"
Cohesion: 0.25
Nodes (9): at(), d(), ht(), i(), Li(), Mi(), v(), W() (+1 more)

### Community 75 - "Security Checklist"
Cohesion: 0.22
Nodes (3): run_security_checklist(), SecurityCheck, SecurityChecklist

### Community 76 - "Minified Utility JS"
Cohesion: 0.25
Nodes (8): bi(), c(), e(), hi(), Pi(), Qe(), Ti(), u()

### Community 77 - "Congestion Routing Tests"
Cohesion: 0.36
Nodes (3): sample_request(), test_live_congestion_avoidance_detour(), test_route_with_avoid_areas_constructs_custom_model()

### Community 79 - "Synthetic Route Generation"
Cohesion: 0.29
Nodes (3): generate_random_coords(), generate_route_geometry(), generate_synthetic_routes()

### Community 80 - "Minified Utility JS"
Cohesion: 0.29
Nodes (7): Jt(), Le(), O(), Qt(), Re(), $t(), te()

### Community 85 - "Minified Utility JS"
Cohesion: 0.60
Nodes (5): m(), ve(), xe(), ye(), z()

### Community 87 - "Minified Utility JS"
Cohesion: 0.67
Nodes (4): Je(), ni(), oi(), si()

## Knowledge Gaps
- **22 isolated node(s):** `ev-recommendation`, `VINFAST_MODEL_SPECS`, `SimulationModeController`, `{ test, expect }`, `author` (+17 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1169 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ServiceType` connect `Candidate Eligibility` to `Candidate Search API`, `Energy Demand Detection`, `Ranking Recommendation APIs`, `Energy Range Tests`, `Demand API Tests`, `Candidate Service Expansion`, `Driver State Manager`, `Station Compatibility Checks`, `Car Rules Tests`, `Ranking Context Features`, `Demand Energy Step API`, `Ranking Service Features`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Are the 103 inferred relationships involving `ServiceType` (e.g. with `check_station_service_compatibility()` and `evaluate_candidate_eligibility()`) actually correct?**
  _`ServiceType` has 103 INFERRED edges - model-reasoned connections that need verification._
- **What connects `ev-recommendation`, `VINFAST_MODEL_SPECS`, `SimulationModeController` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Energy Demand Detection` be split into smaller, more focused modules?**
  _Cohesion score 0.029117774880486745 - nodes in this community are weakly interconnected._
- **Why does `DriverTraceState` connect `Driver Trace State` to `Driver State Manager`, `Driver State Snapshots`, `Location Ingestion`, `Driver State Store`, `Redis Driver State`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 60 inferred relationships involving `ReasonCode` (e.g. with `AutoDemandDetector` and `DriverRequestDecision`) actually correct?**
  _`ReasonCode` has 60 INFERRED edges - model-reasoned connections that need verification._
- **Should `Driver Trace State` be split into smaller, more focused modules?**
  _Cohesion score 0.031289506953223765 - nodes in this community are weakly interconnected._