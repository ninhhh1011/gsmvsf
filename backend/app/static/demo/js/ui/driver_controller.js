/**
 * Driver Mode Controller for VinFast EV Recommendation Demo.
 * Clean, distraction-free Cockpit HUD for in-car use.
 *
 * Strict Rules:
 * - Real GPS observations via backend realtime pipeline (no fake movement).
 * - Exact energy context from scenarios / backend.
 * - Real PostGIS-matched road segments (honest raw GPS fallback if unmatched).
 * - GraphHopper 11 multi-leg routing for detours.
 * - Full test contract compatibility.
 */

import { TrajectoryReplayController, ReplayState } from '../replay.js';
import {
    decodePolyline,
    projectPointOnRoute,
    sliceRouteFromProgress,
    computePolylineDistanceMeters,
    simplifyTrajectoryRDP
} from '../map.js';

export {
    DriverState,
    isValidStateTransition,
    getDriverStateLabel,
    getDriverStateBadgeClass
} from '../domain/driver_state.js';

export {
    straightLineDistanceKm,
    EARTH_RADIUS_KM,
    MODEL_SPECS,
    VINFAST_MODEL_SPECS,
    registerVehicleModel,
    getVehicleModelSpec,
    calculateEstimatedRangeKm,
    calculateSocDepletion
} from '../domain/vehicle_model.js';

import { DriverState, getDriverStateLabel, getDriverStateBadgeClass } from '../domain/driver_state.js';
import {
    straightLineDistanceKm,
    MODEL_SPECS,
    VINFAST_MODEL_SPECS,
    getVehicleModelSpec,
    calculateEstimatedRangeKm,
    calculateSocDepletion
} from '../domain/vehicle_model.js';
import { isPositionOffRoute, shouldTriggerReroute } from '../domain/navigation_tracker.js';
import { isStationCompatibleWithVehicle, filterStations } from '../domain/station_evaluator.js';
import {
    renderAvailableCardHTML,
    renderOfflineCardHTML,
    renderTripCompleteCardHTML,
    renderTripAssignedCardHTML,
    renderTripActiveCardHTML,
    renderPositionStatusHTML,
    renderBatteryView,
    renderActiveCockpitView,
    renderStatusBadge,
    renderReplayControls,
    renderTripActiveEta,
    renderEnergyWarningHTML,
    renderVehicleOptions,
    renderCoordinateText,
    renderCostBreakdownHTML,
    renderPostTripBannerHTML
} from './cockpit_renderer.js';
import { renderDrawerStationsListHTML } from './drawer_renderer.js';
import { renderDriverRecommendation, renderRecommendationPanelHTML } from './driver_recommendation_renderer.js';
import { MapPicker } from './map_picker.js';
import { createCockpitBindings } from './cockpit_bindings.js';

export class DriverModeController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.options = options;
        this.bindings = options.bindings || createCockpitBindings();
        this.mapPicker = new MapPicker({
            mapController: this.map,
            onOriginSelected: async (coords) => await this.setCustomOrigin(coords),
            onDestinationSelected: async (coords) => await this.setCustomDestination(coords)
        });
        this.session = options.session || {
            session_id: crypto.randomUUID(),
            driver_id: null,
            vehicle_id: null,
            vehicle_category: null,
            trip_id: null,
            trajectory_id: null
        };

        this.generation = 1;
        this.trips = [];
        this.vehicles = [];
        this.stations = [];
        this.scenarios = [];
        this.vehicleCatalog = [];

        // State machine
        this.state = DriverState.AVAILABLE;
        this.currentTrip = null;
        this.currentVehicle = null;
        this.userSelectedVehicleModel = null;

        // Energy state
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 153.6;
        this.safetyReserveKm = 2.0;
        this.totalDistanceTravelledKm = 0.0;
        this.lastMovementPos = null;

        // Position state
        this.currentPos = null;
        this.matchedPos = null;
        this.currentObservation = null;

        // Progress & route tracking
        this.remainingTripDistanceKm = 0.0;
        this.directRouteGeometry = null;
        this.fullRouteCoords = null;
        this.lastPassedSegmentIndex = 0;
        this.offRouteConsecutiveSamples = 0;
        this.lastRerouteTimestamp = 0;

        // Recommendation & diversion route caching
        this.lastRecommendation = null;
        this.lastRecommendedStationId = null;
        this.lastDiversionLeg1 = null;
        this.lastDiversionLeg2 = null;

        // Navigation lock — khoá route khi user đã chọn trạm
        this._navigationLocked = false;
        this._selectedStationId = null;   // station_id user đã chọn

        // Proactive Station Search & Destination Picking
        this.isPickingDestination = false;
        this.currentStationsFilter = 'ALL';
        this.chargingIntent = 'EN_ROUTE'; // 'EN_ROUTE' (A -> Station -> B) | 'AT_DESTINATION' (B -> Station)
        this.customOrigin = { latitude: 20.9849, longitude: 105.7935, node_id: "ORIGIN_A" };
        this.customDestination = { latitude: 21.0285, longitude: 105.8542, node_id: "DEST_B" };
        this.postTripStation = null;
        this.postTripRoute = null;
        this.postTripRecommendation = null;
        this.postTripCandidateDetails = null;
        this._onMapPickClick = null;
        this.avoidCongestion = true;

        this._isEvaluating = false;
        this.lastEvalPos = null;
        this.lastEvalTimestamp = 0;

        // Trajectory Replay Controller
        this.replay = new TrajectoryReplayController(apiClient, mapEngine, {
            onStep: async (stepData) => await this._onReplayStep(stepData),
            onStateChange: () => this.renderTripActiveUI(),
            session: this.session
        });

        this.onStateChange = options.onStateChange || (() => {});
    }

    setCatalogs(trips, vehicles, stations, scenarios = [], vehicleCatalog = []) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
        this.scenarios = scenarios || [];
        this.vehicleCatalog = vehicleCatalog || [];
        if (!this.currentVehicle) {
            this.selectVehicleModel('VF_3');
        }
        this.bindings.setVehicleCatalog(renderVehicleOptions(this.vehicleCatalog), this.currentVehicle?.vehicle_model || 'VF_3');
    }

    async init() {
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
        this.bindGlobalControls();
        this.bindings.setVehicleSelection(this.currentVehicle?.vehicle_model || 'VF_3');
    }

    renderCurrentStateUI() {
        if (this.state === DriverState.AVAILABLE) {
            this.renderAvailableUI();
        } else if (this.state === DriverState.TRIP_ASSIGNED) {
            this.renderTripAssignedUI();
        } else if (this.state === DriverState.TRIP_ACTIVE) {
            this.renderTripActiveUI();
        } else if (this.state === DriverState.TRIP_COMPLETE) {
            this.renderTripCompleteUI();
        } else if (this.state === DriverState.OFFLINE) {
            this.renderOfflineUI();
        }
    }

    selectVehicleModel(modelKey) {
        const spec = VINFAST_MODEL_SPECS[modelKey] || VINFAST_MODEL_SPECS['VF_3'];
        const matchedVehicle = this.vehicles.find(v => v.vehicle_model === spec.vehicle_model) || {
            vehicle_id: 'V0001',
            vehicle_model: spec.vehicle_model,
            vehicle_type: spec.vehicle_type,
            usable_capacity_kwh: spec.usable_kwh,
            consumption_wh_per_km: spec.consumption_wh_km,
            charging_supported: spec.charging_supported,
            swap_supported: spec.swap_supported
        };

        this.userSelectedVehicleModel = spec.vehicle_model;
        this.currentVehicle = {
            ...matchedVehicle,
            vehicle_model: spec.vehicle_model,
            vehicle_type: spec.vehicle_type,
            usable_capacity_kwh: spec.usable_kwh,
            consumption_wh_per_km: spec.consumption_wh_km,
            charging_supported: spec.charging_supported,
            swap_supported: spec.swap_supported
        };

        this.session.vehicle_id = this.currentVehicle.vehicle_id;
        this.session.vehicle_category = this.currentVehicle.vehicle_type;

        // Recalculate range according to current SOC and new vehicle specifications
        this.updateEstimatedRange();

        // Sync dropdown UI
        this.bindings.setVehicleSelection(spec.vehicle_model);

        console.log(`[VEHICLE SWITCHED] Model: ${spec.vehicle_model} (${spec.usable_kwh} kWh, ${spec.consumption_wh_km} Wh/km), Current Range: ${this.estimatedRangeKm} km`);

        // Re-render HUD
        this.renderCurrentStateUI();

        // If stations drawer is open, refresh evaluations
        if (this.bindings.isStationsDrawerOpen()) {
            this.refreshDrawerEvaluations();
        }
    }

    updateEstimatedRange() {
        const usable = this.currentVehicle?.usable_capacity_kwh || MODEL_SPECS.VF_3.usable_capacity_kwh;
        const cons = this.currentVehicle?.consumption_wh_per_km || MODEL_SPECS.VF_3.consumption_wh_per_km;
        this.estimatedRangeKm = parseFloat(((usable * 1000.0 * (this.currentSocPct / 100.0)) / cons).toFixed(1));
    }

    setBatterySoc(newSoc, triggerEvaluation = true) {
        const val = Math.min(100, Math.max(5, parseFloat(newSoc) || 10));
        this.currentSocPct = val;
        this.updateEstimatedRange();

        this.bindings.updateBattery(renderBatteryView({ soc: this.currentSocPct, range: this.estimatedRangeKm }));

        if (triggerEvaluation && this.state === DriverState.TRIP_ACTIVE) {
            this._evaluateAtCurrentPosition().then(() => {
                this.renderTripActiveUI();
                if (this.bindings.isStationsDrawerOpen()) {
                    this.refreshDrawerEvaluations();
                }
            }).catch(err => console.warn('SOC change evaluation warning:', err));
        }
    }

    setState(newState) {
        this.state = newState;
        this.onStateChange(this.state);
        this.updateHeaderBadge();
    }

    updateHeaderBadge() {
        this.bindings.setStatusBadge(renderStatusBadge(this.state));
    }

    _getScenarioDescription(scenarioId) {
        const descriptions = {
            'NORMAL_TRIP': 'Chuyến đi thông thường',
            'NO_SERVICE_NEEDED': 'Pin đủ - Không cần sạc',
            'LOW_SOC': 'Pin thấp - Cần sạc gấp',
            'NEED_CHARGING': 'Cần sạc pin',
            'QUEUE_REALTIME_CHANGE': 'Hàng đợi biến động',
            'TRAFFIC_REALTIME_CHANGE': 'Giao thông ùn tắc',
            'STATION_STATUS_CHANGE': 'Trạm đổi trạng thái',
            'FARTHER_BUT_FASTER': 'Xa hơn nhưng nhanh hơn',
            'NEED_SWAP': 'Cần đổi pin'
        };
        return descriptions[scenarioId] || scenarioId;
    }

    // ─── Trip Assignment ────────────────────────────────────────────────

    async assignTrip(tripId) {
        this.generation++;
        const currentGen = this.generation;

        let trip = this.trips.find(t => t.trip_id === tripId);
        if (!trip) {
            const origin = this.customOrigin || { latitude: 20.9849, longitude: 105.7935, node_id: "ORIGIN_A" };
            const dest = this.customDestination || { latitude: 21.0285, longitude: 105.8542, node_id: "DEST_B" };
            trip = {
                trip_id: `TRIP_${Date.now()}`,
                driver_id: "D_USER",
                vehicle_id: this.currentVehicle?.vehicle_id || "V0001",
                scenario_id: "CUSTOM_ROUTE",
                origin: origin,
                destination: dest,
                planned_distance_m: 8500.0
            };
        }

        this.currentTrip = trip;

        if (!this.userSelectedVehicleModel) {
            const tripVehicle = this.vehicles.find(v => v.vehicle_id === trip.vehicle_id);
            if (tripVehicle) {
                this.selectVehicleModel(tripVehicle.vehicle_model);
            } else {
                this.selectVehicleModel('VF_3');
            }
        }

        // Scenario energy context matching
        const matchingScenario = this.scenarios.find(s => s.trip_id === trip.trip_id || s.id === trip.scenario_id);
        if (matchingScenario) {
            this.currentSocPct = matchingScenario.soc_pct ?? 85.0;
            this.safetyReserveKm = matchingScenario.safety_reserve_km ?? 2.0;
        } else {
            this.currentSocPct = 85.0;
            this.safetyReserveKm = 2.0;
        }
        this.updateEstimatedRange();

        // Reset tracking state
        this.fullRouteCoords = null;
        this.lastPassedSegmentIndex = 0;
        this.offRouteConsecutiveSamples = 0;
        this.lastRerouteTimestamp = 0;
        this.lastRecommendedStationId = null;
        this.lastDiversionLeg1 = null;
        this.lastDiversionLeg2 = null;

        const plannedKm = trip.planned_distance_m ? (trip.planned_distance_m / 1000) : 0.0;
        this.remainingTripDistanceKm = plannedKm;

        // Clear map and render direct endpoints
        this.map.clearAll();
        this._renderEndpointsWithDrag(trip.origin, trip.destination);

        // Sample corridor inflection waypoints via Ramer-Douglas-Peucker (250m tolerance)
        // This preserves key turnarounds while eliminating GPS sensor jitter and side-alley detours
        let viaPoints = [];
        try {
            const trajId = this._tripToTrajectory(trip.trip_id);
            const obs = await this.api.getTrajectory(trajId);
            if (obs && Array.isArray(obs) && obs.length > 5) {
                const simplified = simplifyTrajectoryRDP(obs, 250);
                if (simplified.length > 2) {
                    viaPoints = simplified.slice(1, -1).map(p => ({
                        latitude: p.latitude,
                        longitude: p.longitude
                    }));
                }
            }
        } catch (e) {
            // Trajectory unmapped or mock route, proceed without via
        }

        if (this.generation !== currentGen) return;

        const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';
        let routeResult = null;
        try {
            routeResult = await this.api.computeRoute(
                trip.origin,
                trip.destination,
                { vehicle_category: vCat },
                viaPoints
            );
        } catch (err) {
            console.warn('Corridor route computation failed, falling back to direct route:', err);
            try {
                routeResult = await this.api.computeRoute(
                    trip.origin,
                    trip.destination,
                    { vehicle_category: vCat }
                );
            } catch (directErr) {
                console.warn('Direct route computation error:', directErr);
            }
        }

        if (this.generation !== currentGen) return;

        if (routeResult?.geometry) {
            const coords = decodePolyline(routeResult.geometry);
            if (coords && coords.length > 0) {
                this.fullRouteCoords = coords;
                this.directRouteGeometry = coords;
                this.map.renderDirectRoute(coords);
                this.map.fitBoundsToActive(coords);
            } else {
                this.map.fitBoundsToActive();
            }
        } else {
            this.map.fitBoundsToActive();
        }

        if (routeResult?.distance_m) {
            this.remainingTripDistanceKm = parseFloat((routeResult.distance_m / 1000).toFixed(2));
        } else if (trip.planned_distance_m) {
            this.remainingTripDistanceKm = parseFloat((trip.planned_distance_m / 1000).toFixed(2));
        }

        this.setState(DriverState.TRIP_ASSIGNED);
        this.renderTripAssignedUI();
    }

    // ─── Start Trip ─────────────────────────────────────────────────────

    async startTrip() {
        if (!this.currentTrip) return;

        this.generation++;
        const currentGen = this.generation;

        this.session.driver_id = `driver_${Date.now().toString(36)}`;
        this.session.vehicle_id = this.currentVehicle?.vehicle_id;
        this.session.vehicle_category = this.currentVehicle?.vehicle_type;
        this.session.trip_id = this.currentTrip.trip_id;

        this.setState(DriverState.TRIP_ACTIVE);
        this.lastMovementPos = null;
        this.totalDistanceTravelledKm = 0.0;

        const trajId = this._tripToTrajectory(this.currentTrip.trip_id);
        this.session.trajectory_id = trajId || 'SIMULATED';

        if (trajId) {
            try {
                await this.replay.loadTrajectory(trajId);
            } catch (err) {
                console.warn(`Dataset trajectory ${trajId} load failed, falling back to polyline simulation:`, err);
                if (this.fullRouteCoords && this.fullRouteCoords.length > 1) {
                    await this.replay.loadFromPolyline(this.fullRouteCoords);
                }
            }
        } else if (this.fullRouteCoords && this.fullRouteCoords.length > 1) {
            await this.replay.loadFromPolyline(this.fullRouteCoords);
        }

        if (this.generation !== currentGen) return;

        // Initial recommendation & render UI
        await this._evaluateAtCurrentPosition();
        this.renderTripActiveUI();

        // Auto-step first observation
        await this.replay.step();

        if (this.generation !== currentGen) return;
        this.playTrip();
    }

    _tripToTrajectory(tripId) {
        if (!tripId) return null;
        if (tripId.startsWith('TRJ')) return tripId;
        const match = tripId.match(/^T(\d+)$/);
        if (match) {
            return `TRJ${match[1]}`;
        }
        return null;
    }

    // ─── Step Handling ──────────────────────────────────────────────────

    async _onReplayStep(stepData) {
        const { locResp, observation } = stepData || {};
        if (this.state !== DriverState.TRIP_ACTIVE) return;

        try {
            if (observation) {
                this.currentObservation = observation;
            }

            if (locResp?.matched_position) {
                this.matchedPos = {
                    latitude: locResp.matched_position.latitude,
                    longitude: locResp.matched_position.longitude,
                    road_segment_id: locResp.matched_position.road_segment_id,
                    direction: locResp.matched_position.direction,
                    confidence: locResp.matched_position.confidence
                };
                this.currentPos = {
                    latitude: locResp.matched_position.latitude,
                    longitude: locResp.matched_position.longitude
                };
            } else if (locResp?.raw_position) {
                this.currentPos = {
                    latitude: locResp.raw_position.latitude,
                    longitude: locResp.raw_position.longitude
                };
                this.matchedPos = null;
            } else if (observation) {
                this.currentPos = {
                    latitude: observation.latitude,
                    longitude: observation.longitude
                };
                this.matchedPos = null;
            }

            // Dynamic Energy & SOC depletion during movement
            if (this.lastMovementPos && this.currentPos) {
                const stepDistKm = straightLineDistanceKm(
                    this.lastMovementPos.latitude,
                    this.lastMovementPos.longitude,
                    this.currentPos.latitude,
                    this.currentPos.longitude
                );
                if (stepDistKm > 0.005) { // At least 5m
                    const usable = this.currentVehicle?.usable_capacity_kwh || MODEL_SPECS.VF_3.usable_capacity_kwh;
                    const cons = this.currentVehicle?.consumption_wh_per_km || MODEL_SPECS.VF_3.consumption_wh_per_km;
                    const energyKwh = stepDistKm * (cons / 1000.0);
                    const socDropPct = (energyKwh / usable) * 100.0;

                    this.currentSocPct = Math.max(0.0, parseFloat((this.currentSocPct - socDropPct).toFixed(2)));
                    this.updateEstimatedRange();
                    this.totalDistanceTravelledKm = (this.totalDistanceTravelledKm || 0.0) + stepDistKm;
                    this.lastMovementPos = { ...this.currentPos };
                }
            } else if (this.currentPos) {
                this.lastMovementPos = { ...this.currentPos };
            }

            // Update remaining route & distance
            const probePos = this.matchedPos || this.currentPos;
            if (this.fullRouteCoords && this.fullRouteCoords.length > 1 && probePos) {
                const progress = projectPointOnRoute(probePos, this.fullRouteCoords, this.lastPassedSegmentIndex);

                // Anti-spam off-route check (> 35m for 3 consecutive samples, with 5s cooldown)
                const OFF_ROUTE_THRESHOLD_METERS = 35.0;
                const REROUTE_COOLDOWN_MS = 5000;
                const now = Date.now();

                if (progress.distanceMeters > OFF_ROUTE_THRESHOLD_METERS) {
                    this.offRouteConsecutiveSamples++;
                    if (this.offRouteConsecutiveSamples >= 3 && (now - this.lastRerouteTimestamp) > REROUTE_COOLDOWN_MS) {
                        this.lastRerouteTimestamp = now;
                        this.offRouteConsecutiveSamples = 0;
                        await this._triggerReroute(probePos);
                    }
                } else {
                    this.offRouteConsecutiveSamples = 0;
                }

                // Route slicing: shrink route ahead of the car
                if (this.fullRouteCoords && this.fullRouteCoords.length > 1) {
                    this.lastPassedSegmentIndex = Math.max(this.lastPassedSegmentIndex, progress.segmentIndex);
                    const remainingCoords = sliceRouteFromProgress(this.fullRouteCoords, {
                        segmentIndex: this.lastPassedSegmentIndex,
                        projPoint: progress.projPoint
                    });

                    this.directRouteGeometry = remainingCoords;
                    this.map.updateDirectRoute(remainingCoords);

                    const remainingMeters = computePolylineDistanceMeters(remainingCoords);
                    this.remainingTripDistanceKm = parseFloat((remainingMeters / 1000).toFixed(2));
                }
            } else if (this.currentPos && this.currentTrip?.destination) {
                this.remainingTripDistanceKm = straightLineDistanceKm(
                    this.currentPos.latitude,
                    this.currentPos.longitude,
                    this.currentTrip.destination.latitude,
                    this.currentTrip.destination.longitude
                );
            }

            if (this.replay.isReplayComplete()) {
                this.setState(DriverState.TRIP_COMPLETE);
                this.remainingTripDistanceKm = 0.0;
                this.map.updateDirectRoute([]);
                await this._evaluateAtCurrentPosition();
                this.renderTripCompleteUI();
                return;
            }

            // Kiểm tra đã đến trạm chưa
            if (this._navigationLocked && this._selectedStationId && this.currentPos) {
                // Tính khoảng cách đến station đã chọn
                const selectedStation = this.stations.find(s => s.station_id === this._selectedStationId);
                if (selectedStation) {
                    const distKm = straightLineDistanceKm(
                        this.currentPos.latitude, this.currentPos.longitude,
                        selectedStation.latitude, selectedStation.longitude
                    );
                    if (distKm < 0.1) { // < 100m → coi như đến nơi
                        this._navigationLocked = false;
                        this._selectedStationId = null;
                    }
                }
            }

            // Periodic recommendation evaluation (every 2.5s or 50m of movement)
            const nowMs = Date.now();
            const distSinceLastEval = this.lastEvalPos ? straightLineDistanceKm(
                this.lastEvalPos.latitude, this.lastEvalPos.longitude,
                this.currentPos.latitude, this.currentPos.longitude
            ) : 999;

            if (!this.lastEvalTimestamp || (nowMs - this.lastEvalTimestamp > 2500) || (distSinceLastEval > 0.05)) {
                this.lastEvalTimestamp = nowMs;
                this.lastEvalPos = { ...this.currentPos };
                await this._evaluateAtCurrentPosition();
            }

            this.renderTripActiveUI();
        } catch (stepErr) {
            console.warn('[DriverMode] _onReplayStep error:', stepErr);
        }
    }

    async _triggerReroute(fromPos) {
        if (!fromPos || !this.currentTrip?.destination) return;
        const currentGen = this.generation;
        try {
            const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';
            const rerouteResult = await this.api.computeRoute(
                fromPos,
                this.currentTrip.destination,
                { vehicle_category: vCat }
            );
            if (this.generation !== currentGen) return;
            if (rerouteResult?.geometry) {
                const coords = decodePolyline(rerouteResult.geometry);
                if (coords && coords.length > 0) {
                    this.fullRouteCoords = coords;
                    this.lastPassedSegmentIndex = 0;
                    this.directRouteGeometry = coords;
                    this.map.updateDirectRoute(coords);
                }
            }
        } catch (err) {
            console.warn('Rerouting error:', err);
        }
    }

    // ─── Evaluation ─────────────────────────────────────────────────────

    async _evaluateAtCurrentPosition() {
        if (!this.currentVehicle || !this.currentPos || this._isEvaluating) return;

        // Vẫn kiểm tra nguy hiểm DÙ ĐANG KHOÁ
        const isDangerous = this.estimatedRangeKm < 5;
        if (isDangerous && this._navigationLocked) {
            // Hiện cảnh báo nhưng KHÔNG tự động unlock
            // User phải tự bấm "Đổi trạm"
            console.warn('[DriverMode] ⚠️ Range < 5km! User should change station.');
        }

        // Skip nếu đang khoá navigation
        if (this._navigationLocked) {
            this._isEvaluating = false;
            return;
        }

        this._isEvaluating = true;

        const currentGen = this.generation;
        const driverId = this.session.driver_id || 'UNASSIGNED';
        const timestamp = (this.currentObservation?.timestamp)
            ? this.currentObservation.timestamp
            : (this.currentTrip?.start_time || new Date().toISOString());

        const rawLat = this.currentObservation ? this.currentObservation.latitude : this.currentPos.latitude;
        const rawLng = this.currentObservation ? this.currentObservation.longitude : this.currentPos.longitude;

        // Debug: Log ETA calculation inputs
        console.group('[DRIVER MODE] ETA Debug');
        console.log('Current Position (A):', { lat: rawLat, lng: rawLng });
        console.log('Trip Destination (B):', this.currentTrip?.destination);
        console.log('Trip Origin (trip origin):', this.currentTrip?.origin);
        console.log('Vehicle:', this.currentVehicle?.vehicle_id, this.currentVehicle?.vehicle_type);
        console.log('SOC:', this.currentSocPct + '%', 'Range:', this.estimatedRangeKm + 'km');
        console.log('Remaining Trip Distance:', this.remainingTripDistanceKm + 'km');
        console.log('Observation timestamp:', timestamp);

        const payload = {
            context: {
                vehicle_id: this.currentVehicle.vehicle_id,
                driver_id: driverId,
                trip_id: this.currentTrip?.trip_id,
                timestamp: timestamp,
                current_soc_pct: parseFloat(this.currentSocPct.toFixed(1)),
                estimated_remaining_range_km: parseFloat(this.estimatedRangeKm.toFixed(1)),
                remaining_trip_distance_km: parseFloat(this.remainingTripDistanceKm.toFixed(2)),
                distance_travelled_km: parseFloat((this.totalDistanceTravelledKm || 0.0).toFixed(2)),
                safety_reserve_km: this.safetyReserveKm,
                consumption_wh_per_km: this.currentVehicle?.consumption_wh_per_km,
                raw_latitude: rawLat,
                raw_longitude: rawLng,
                road_segment_id: this.matchedPos?.road_segment_id || this.currentObservation?.road_segment_id || null
            },
            destination_latitude: this.currentTrip?.destination?.latitude,
            destination_longitude: this.currentTrip?.destination?.longitude,
            avoid_congestion: !!this.avoidCongestion,
            top_n: 5
        };
        console.log('Request payload:', JSON.stringify(payload, null, 2));

        try {
            const rec = await this.api.getRecommendation(payload);

            console.log('Recommendation Response:', {
                has_recommendation: rec?.has_recommendation,
                recommended_station: rec?.recommended_station_id,
                eta_to_station_s: rec?.ranked_candidates?.[0]?.eta_to_station_s,
                eta_to_station_min: rec?.ranked_candidates?.[0]
                    ? (rec.ranked_candidates[0].eta_to_station_s / 60).toFixed(1)
                    : null,
                eta_to_complete_min: rec?.ranked_candidates?.[0]
                    ? (rec.ranked_candidates[0].eta_to_service_complete_s / 60).toFixed(1)
                    : null
            });
            console.groupEnd();
            if (this.generation !== currentGen) return;

            this.lastRecommendation = rec;

            // Nếu đang khoá navigation → skip hoàn toàn, KHÔNG re-evaluate
            if (this._navigationLocked) {
                this._isEvaluating = false;
                return;
            }

            let leg1Result = null;
            let leg2Result = null;

            if (rec.has_recommendation && rec.ranked_candidates?.length > 0) {
                // Sổ panel chọn trạm (gọi hàm mới ở Bước 3)
                this._showRecommendationPanel(rec.ranked_candidates);

                // Vẫn vẽ route cho top 1 nhưng KHÔNG khoá
                const top = rec.ranked_candidates[0];
                const top5Candidates = (rec.ranked_candidates || []).slice(0, 5).map((c, idx) => {
                    const stMatch = this.stations?.find(s => s.station_id === c.station_id);
                    return {
                        ...c,
                        rank: c.rank ?? (idx + 1),
                        station_id: c.station_id,
                        latitude: c.latitude ?? stMatch?.latitude,
                        longitude: c.longitude ?? stMatch?.longitude,
                    };
                }).filter(c => c.latitude != null && c.longitude != null);

                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st && this.currentTrip?.destination) {
                    const stPos = { latitude: st.latitude, longitude: st.longitude };
                    try {
                        leg1Result = await this.api.computeRoute(this.currentPos, stPos, {
                            vehicle_category: this.currentVehicle.vehicle_type
                        });
                        leg2Result = await this.api.computeRoute(stPos, this.currentTrip.destination, {
                            vehicle_category: this.currentVehicle.vehicle_type
                        });
                        if (this.generation === currentGen) {
                            this.lastRecommendedStationId = top.station_id;
                            this.lastDiversionLeg1 = leg1Result;
                            this.lastDiversionLeg2 = leg2Result;
                            if (leg1Result?.geometry) {
                                this.map.renderRecommendationRoute(leg1Result.geometry, leg2Result?.geometry, top5Candidates);
                            }
                        }
                    } catch (routeErr) {
                        console.warn('Recommendation diversion route error:', routeErr);
                    }
                }
                this.map.renderStations(this.stations, top.station_id, top.service_type, null, rec.ranked_candidates);
            } else {
                this._hideRecommendationPanel();
                this.lastRecommendedStationId = null;
                this.lastDiversionLeg1 = null;
                this.lastDiversionLeg2 = null;
                this.map.clearRecommendationRoute();
                this.map.renderStations(this.stations, null, null, null, rec?.ranked_candidates || []);
            }

            if (this.options?.onStateUpdate) {
                this.options.onStateUpdate({
                    scenario: this.currentTrip,
                    vehicle: this.currentVehicle,
                    driverId: driverId,
                    origin: this.currentTrip?.origin,
                    destination: this.currentTrip?.destination,
                    driverLocation: {
                        driver_id: driverId,
                        status: this.matchedPos ? 'MATCHED' : 'RAW_GPS_FALLBACK',
                        raw_position: this.currentPos,
                        matched_position: this.matchedPos
                    },
                    recommendRequest: payload,
                    recommendResult: rec,
                    stationRoutes: { leg1: leg1Result, leg2: leg2Result }
                });
            }
        } catch (err) {
            if (this.generation !== currentGen) return;

            console.warn('Recommendation evaluation error:', err);
            this.lastRecommendation = null;

            if (err?.status === 409 || err?.isConflict) {
                this.lastRecommendedStationId = null;
                this.lastDiversionLeg1 = null;
                this.lastDiversionLeg2 = null;
                this.map.clearRecommendationRoute();
            }

            if (this.options?.onStateUpdate) {
                this.options.onStateUpdate({
                    error: err,
                    recommendRequest: payload,
                    recommendResult: null
                });
            }
        } finally {
            this._isEvaluating = false;
        }
    }

    _showRecommendationPanel(candidates) {
        if (this._navigationLocked || !candidates?.length) return;
        this.bindings.showRecommendationPanel(renderRecommendationPanelHTML(candidates, this.stations), {
            close: () => this._hideRecommendationPanel(),
            selectStation: stationId => {
                this._hideRecommendationPanel();
                this._selectStationAndNavigate(stationId);
            }
        });
    }

    _hideRecommendationPanel() { this.bindings.hideRecommendationPanel(); }

    _selectStationAndNavigate(stationId) {
        // Khoá navigation
        this._navigationLocked = true;
        this._selectedStationId = stationId;

        // Gọi navigateViaStationId với station đã chọn
        this.navigateViaStationId(stationId);
        this.renderTripActiveUI();
    }

    // ─── Controls ──────────────────────────────────────────────────────

    async stepTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        await this.replay.step();
    }

    playTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        this.replay.play();
    }

    pauseTrip() {
        this.replay.pause();
    }

    returnToAvailable() {
        this.generation++;
        this.replay.clearSession();
        this.replay.reset();
        this.map.clearAll();
        this.currentTrip = null;
        this.currentPos = null;
        this.matchedPos = null;
        this.currentObservation = null;
        this.lastRecommendation = null;
        this.directRouteGeometry = null;
        this.fullRouteCoords = null;
        this.lastPassedSegmentIndex = 0;
        this.offRouteConsecutiveSamples = 0;
        this.lastRerouteTimestamp = 0;
        this.lastRecommendedStationId = null;
        this.lastDiversionLeg1 = null;
        this.lastDiversionLeg2 = null;
        this.remainingTripDistanceKm = 0.0;

        this._navigationLocked = false;
        this._selectedStationId = null;
        this._hideRecommendationPanel();

        this.session.driver_id = null;
        this.session.vehicle_id = null;
        this.session.vehicle_category = null;
        this.session.trip_id = null;
        this.session.trajectory_id = null;

        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
    }

    goOffline() {
        this.setState(DriverState.OFFLINE);
        this.renderOfflineUI();
    }

    goOnline() {
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
    }

    cancelTrip() {
        this._navigationLocked = false;
        this._selectedStationId = null;
        this._hideRecommendationPanel();
        this.returnToAvailable();
    }

    unlockNavigation() {
        if (!this._navigationLocked) return;
        this._navigationLocked = false;
        this._selectedStationId = null;
        // Ẩn panel nếu đang mở
        this._hideRecommendationPanel();
        // Re-trigger evaluate
        this.lastEvalTimestamp = 0; // force re-evaluate
        this._evaluateAtCurrentPosition().catch(() => {});
        this._onReplayStep({}).catch(() => {});
        this.renderTripActiveUI();
    }

    async navigateViaStation() {
        if (!this.lastRecommendation?.has_recommendation || !this.lastRecommendation.ranked_candidates?.length) return;
        const top = this.lastRecommendation.ranked_candidates[0];
        this._hideRecommendationPanel();
        this._selectStationAndNavigate(top.station_id);
    }

    async navigateViaStationId(stationId) {
        const st = this.stations.find(s => s.station_id === stationId);
        if (!st) return;

        this._navigationLocked = true;
        this._selectedStationId = stationId;
        this._hideRecommendationPanel();
        this.closeStationsDrawer();

        const currentPos = this.currentPos || (this.currentTrip?.origin ? {
            latitude: this.currentTrip.origin.latitude,
            longitude: this.currentTrip.origin.longitude
        } : { latitude: 21.1038023, longitude: 106.0023809 });

        const stationPos = { latitude: st.latitude, longitude: st.longitude };
        const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';

        this.bindings.setNavigationButtonState('Đang dẫn đường...', true);

        try {
            if (this.currentTrip?.destination) {
                // Route via station: Leg 1 (Vehicle -> Station) + Leg 2 (Station -> Destination)
                const leg1 = await this.api.computeRoute(currentPos, stationPos, { vehicle_category: vCat });
                const leg2 = await this.api.computeRoute(stationPos, this.currentTrip.destination, { vehicle_category: vCat });

                if (leg1?.geometry) {
                    this.lastRecommendedStationId = st.station_id;
                    this.lastDiversionLeg1 = leg1;
                    const top5Candidates = (this.lastRecommendation?.ranked_candidates || []).slice(0, 5).map((c, idx) => {
                        const stMatch = this.stations?.find(s => s.station_id === c.station_id);
                        return {
                            ...c,
                            rank: c.rank ?? (idx + 1),
                            station_id: c.station_id,
                            latitude: c.latitude ?? stMatch?.latitude,
                            longitude: c.longitude ?? stMatch?.longitude,
                        };
                    }).filter(c => c.latitude != null && c.longitude != null);
                    this.map.renderRecommendationRoute(leg1.geometry, leg2?.geometry, top5Candidates);
                    this.map.fitBoundsToActive();

                    // Combine Leg 1 and Leg 2 for full diversion driving
                    const coords1 = decodePolyline(leg1.geometry);
                    const coords2 = leg2?.geometry ? decodePolyline(leg2.geometry) : [];
                    const combined = [...coords1, ...coords2];
                    this.fullRouteCoords = combined;
                    this.directRouteGeometry = combined;
                    this.lastPassedSegmentIndex = 0;

                    const totalDistM = (leg1.distance_m || 0) + (leg2?.distance_m || 0);
                    this.remainingTripDistanceKm = parseFloat((totalDistM / 1000).toFixed(2));

                    // Load combined diversion into replay so vehicle drives via station!
                    if (this.state === DriverState.TRIP_ACTIVE) {
                        await this.replay.loadFromPolyline(combined);
                    }
                }
            } else {
                // Direct route to station (free drive)
                const route = await this.api.computeRoute(currentPos, stationPos, { vehicle_category: vCat });
                if (route?.geometry) {
                    const coords = decodePolyline(route.geometry);
                    this.fullRouteCoords = coords;
                    this.directRouteGeometry = coords;
                    this.map.clearAll();
                    this.map.renderTripEndpoints(currentPos, stationPos);
                    this.map.renderDirectRoute(coords);
                    this.map.fitBoundsToActive(coords);
                    this.currentTrip = {
                        trip_id: `NAVI_${st.station_id}`,
                        origin: currentPos,
                        destination: stationPos,
                        planned_distance_m: route.distance_m
                    };
                    this.remainingTripDistanceKm = parseFloat((route.distance_m / 1000).toFixed(2));
                    if (this.state === DriverState.AVAILABLE) {
                        this.setState(DriverState.TRIP_ASSIGNED);
                        this.renderTripAssignedUI();
                    }
                }
            }

            // Highlight station marker on map
            this.map.renderStations(this.stations, st.station_id, st.service_type || 'FAST_CHARGING', null, this.lastRecommendation?.ranked_candidates);

            if (navBtn) {
                navBtn.textContent = '✓ Đã chọn tuyến ghé trạm';
                navBtn.style.background = '#10b981';
                navBtn.style.color = '#ffffff';
                navBtn.disabled = false;
            }
        } catch (err) {
            console.warn('Navigation to station failed:', err);
            if (navBtn) {
                navBtn.textContent = 'Chỉ đường qua trạm';
                navBtn.disabled = false;
            }
        }
    }

    async setPostTripStation(stId) {
        const st = this.stations.find(s => s.station_id === stId);
        if (!st) return;

        this.postTripStation = st;
        this.closeStationsDrawer();

        const dest = this.customDestination || this.currentTrip?.destination || { latitude: 21.0150, longitude: 105.7800 };
        const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';
        const stationPos = { latitude: st.latitude, longitude: st.longitude };

        try {
            // Compute onward route from Destination B to Station
            const routeBToSt = await this.api.computeRoute(dest, stationPos, { vehicle_category: vCat });
            this.postTripRoute = routeBToSt;

            // Render direct route A -> B, plus onward connection B -> Station
            if (this.fullRouteCoords) {
                this.map.renderDirectRoute(this.fullRouteCoords);
            }
            if (routeBToSt?.geometry) {
                this.map.renderPostTripRoute(routeBToSt.geometry);
            }

            // Highlight chosen station marker
            this.map.highlightStation(st.station_id);

            // Re-render UI to show post-trip charging badge/notification
            if (this.state === DriverState.TRIP_ACTIVE) {
                this.renderTripActiveUI();
            } else if (this.state === DriverState.TRIP_ASSIGNED) {
                this.renderTripAssignedUI();
            }
        } catch (err) {
            console.warn('Failed to compute route from B to station:', err);
        }
    }

    cancelPostTripStation() {
        this.postTripStation = null;
        this.postTripRoute = null;
        this.map.layers.recommendRoute.clearLayers();
        if (this.state === DriverState.TRIP_ACTIVE) {
            this.renderTripActiveUI();
        } else if (this.state === DriverState.TRIP_ASSIGNED) {
            this.renderTripAssignedUI();
        }
    }

    // ─── Proactive Station Drawer & Map Destination Picking ─────────────

    bindGlobalControls() {
        this.bindings.bindGlobalControls({
            selectVehicle: value => this.selectVehicleModel(value),
            openStations: () => this.openStationsDrawer(),
            closeStations: () => this.closeStationsDrawer(),
            pickOrigin: () => this.startPickCustomOrigin(),
            pickDestination: () => this.startPickCustomDestination(),
            cancelPicking: () => this.cancelAllPicking(),
            changeIntent: async value => {
                this.chargingIntent = value;
                this.renderStationsDrawer(this.currentStationsFilter);
                await this.refreshDrawerEvaluations();
            },
            changeFilter: value => {
                this.currentStationsFilter = value;
                this.renderStationsDrawer(value);
            }
        });
    }

    async openStationsDrawer(filter = null) {
        if (filter) this.currentStationsFilter = filter;
        if (!this.bindings.setStationsDrawerOpen(true)) return;
        this.renderStationsDrawer(this.currentStationsFilter);
        await this.refreshDrawerEvaluations();
    }

    closeStationsDrawer() { this.bindings.setStationsDrawerOpen(false); }

    async refreshDrawerEvaluations() {
        const dest = this.customDestination || this.currentTrip?.destination || { latitude: 21.0150, longitude: 105.7800 };
        const vId = this.currentVehicle?.vehicle_id || 'V0001';
        const isAtDest = this.chargingIntent === 'AT_DESTINATION';

        let evalOrigin;
        let evalSoc = parseFloat(this.currentSocPct.toFixed(1));
        let evalRange = parseFloat(this.estimatedRangeKm.toFixed(1));
        let evalRemainingTrip = parseFloat(this.remainingTripDistanceKm.toFixed(2));
        let evalTravelled = parseFloat((this.totalDistanceTravelledKm || 0.0).toFixed(2));

        if (isAtDest) {
            evalOrigin = { latitude: dest.latitude, longitude: dest.longitude };
            const remainingTrip = Math.max(0, this.remainingTripDistanceKm || 0.0);
            const cons = this.currentVehicle?.consumption_wh_per_km || MODEL_SPECS.VF_3.consumption_wh_per_km;
            const usable = this.currentVehicle?.usable_capacity_kwh || MODEL_SPECS.VF_3.usable_capacity_kwh;
            const energyTripKwh = (remainingTrip * cons) / 1000.0;
            const deltaSoc = (energyTripKwh / usable) * 100.0;
            evalSoc = Math.max(1.0, parseFloat((this.currentSocPct - deltaSoc).toFixed(1)));
            evalRange = Math.max(1.0, parseFloat(((evalSoc / 100.0) * usable * 1000.0 / cons).toFixed(1)));
            evalRemainingTrip = 0.0;
            evalTravelled = parseFloat((evalTravelled + remainingTrip).toFixed(2));
        } else {
            evalOrigin = this.currentPos || (this.currentTrip?.origin ? {
                latitude: this.currentTrip.origin.latitude,
                longitude: this.currentTrip.origin.longitude
            } : { latitude: 21.0285, longitude: 105.8542 });
        }

        try {
            const [candRes, recRes] = await Promise.all([
                this.api.evaluateAndSearchCandidates({
                    vehicle_id: vId,
                    current_soc_pct: evalSoc,
                    estimated_remaining_range_km: evalRange,
                    remaining_trip_distance_km: evalRemainingTrip,
                    distance_travelled_km: evalTravelled,
                    safety_reserve_km: this.safetyReserveKm,
                    consumption_wh_per_km: this.currentVehicle?.consumption_wh_per_km,
                    raw_latitude: evalOrigin.latitude,
                    raw_longitude: evalOrigin.longitude,
                    destination_latitude: dest.latitude,
                    destination_longitude: dest.longitude,
                    requested_service: 'ANY',
                    eligible_only: false
                }).catch(() => null),
                this.api.getRecommendation({
                    context: {
                        vehicle_id: vId,
                        current_soc_pct: evalSoc,
                        estimated_remaining_range_km: evalRange,
                        remaining_trip_distance_km: evalRemainingTrip,
                        distance_travelled_km: evalTravelled,
                        safety_reserve_km: this.safetyReserveKm,
                        consumption_wh_per_km: this.currentVehicle?.consumption_wh_per_km,
                        raw_latitude: evalOrigin.latitude,
                        raw_longitude: evalOrigin.longitude,
                        road_segment_id: isAtDest ? null : (this.matchedPos?.road_segment_id || this.currentObservation?.road_segment_id || null),
                        timestamp: new Date().toISOString()
                    },
                    requested_service: 'ANY',
                    destination_latitude: dest.latitude,
                    destination_longitude: dest.longitude,
                    avoid_congestion: !!this.avoidCongestion,
                    top_n: 30
                }).catch(() => null)
            ]);

            if (isAtDest) {
                if (recRes && recRes.ranked_candidates) {
                    this.postTripRecommendation = recRes;
                }
                if (candRes && candRes.candidates) {
                    this.postTripCandidateDetails = candRes.candidates;
                }
            } else {
                if (recRes && recRes.ranked_candidates) {
                    this.lastRecommendation = recRes;
                }
                if (candRes && candRes.candidates) {
                    this.stationCandidateDetails = candRes.candidates;
                }
            }

            this.renderStationsDrawer(this.currentStationsFilter);
        } catch (e) {
            console.warn('Failed to refresh drawer evaluations:', e);
        }
    }

    renderStationsDrawer(filter = 'ALL') {
        const currentPos = this.currentPos || (this.currentTrip?.origin ? {
            latitude: this.currentTrip.origin.latitude,
            longitude: this.currentTrip.origin.longitude
        } : { latitude: 21.1038023, longitude: 106.0023809 });

        const dest = this.customDestination || this.currentTrip?.destination || { latitude: 21.0150, longitude: 105.7800 };
        const directDistKm = straightLineDistanceKm(currentPos.latitude, currentPos.longitude, dest.latitude, dest.longitude);

        // Calculate straight line distance for fallback
        const stationsWithDist = this.stations.map(st => {
            const distMeters = straightLineDistanceKm(
                currentPos.latitude, currentPos.longitude,
                st.latitude, st.longitude
            ) * 1000;
            return { ...st, distMeters, distKm: (distMeters / 1000).toFixed(1) };
        });

        // Apply filter
        let filtered = stationsWithDist;
        if (filter === 'FAST_DC') {
            filtered = stationsWithDist.filter(s => s.station_type !== 'SWAP' && s.service_type !== 'BATTERY_SWAP');
        } else if (filter === 'SWAP') {
            filtered = stationsWithDist.filter(s => s.station_type === 'SWAP' || s.station_type === 'CHARGING_SWAP' || s.service_type === 'BATTERY_SWAP');
        }

        const isAtDest = this.chargingIntent === 'AT_DESTINATION';
        const activeRec = isAtDest 
            ? (this.postTripRecommendation || this.lastRecommendation) 
            : this.lastRecommendation;
        const activeCand = isAtDest 
            ? (this.postTripCandidateDetails || this.stationCandidateDetails) 
            : this.stationCandidateDetails;

        // Top recommendation ID for current active intent
        const topRecId = activeRec?.has_recommendation && activeRec.ranked_candidates?.length > 0
            ? activeRec.ranked_candidates[0].station_id
            : null;

        // Sort stations based on active intent
        if (isAtDest) {
            // AT_DESTINATION: Sort by backend post-trip rank if available, otherwise by distance to B
            filtered.sort((a, b) => {
                if (a.station_id === topRecId) return -1;
                if (b.station_id === topRecId) return 1;

                const rankA = activeRec?.ranked_candidates?.find(c => c.station_id === a.station_id)?.rank ?? 999;
                const rankB = activeRec?.ranked_candidates?.find(c => c.station_id === b.station_id)?.rank ?? 999;
                if (rankA !== rankB) return rankA - rankB;

                const distA = straightLineDistanceKm(dest.latitude, dest.longitude, a.latitude, a.longitude);
                const distB = straightLineDistanceKm(dest.latitude, dest.longitude, b.latitude, b.longitude);
                return distA - distB;
            });
        } else {
            // EN_ROUTE: Top recommendation first, then by rank if available, then by distance from vehicle
            filtered.sort((a, b) => {
                if (a.station_id === topRecId) return -1;
                if (b.station_id === topRecId) return 1;

                const rankA = activeRec?.ranked_candidates?.find(c => c.station_id === a.station_id)?.rank ?? 999;
                const rankB = activeRec?.ranked_candidates?.find(c => c.station_id === b.station_id)?.rank ?? 999;
                if (rankA !== rankB) return rankA - rankB;

                return a.distMeters - b.distMeters;
            });
        }

        const html = renderDrawerStationsListHTML(filtered, {
            topRecId,
            isAtDest,
            activeRec,
            activeCand,
            dest,
            directDistKm,
            postTripStationId: this.postTripStation?.station_id,
            remainingTripDistanceKm: this.remainingTripDistanceKm
        });
        this.bindings.renderDrawer(html, filtered.length, {
            navigate: data => this.navigateViaStationId(data.stationId),
            setPostTrip: data => this.setPostTripStation(data.stationId),
            zoom: data => this.map.map.flyTo([parseFloat(data.lat), parseFloat(data.lng)], 16)
        });
    }

    _renderEndpointsWithDrag(origin, dest) {
        this.map.renderTripEndpoints(origin, dest, {
            draggable: true,
            onOriginDragEnd: async (newOrig) => {
                await this.setCustomOrigin(newOrig);
            },
            onDestinationDragEnd: async (newDest) => {
                await this.setCustomDestination(newDest);
            }
        });
    }

    startPickCustomOrigin() {
        this.mapPicker.setMapController(this.map);
        this.mapPicker.startPickOrigin();
    }

    cancelPickCustomOrigin() {
        this.mapPicker.cancelPickOrigin();
    }

    startPickCustomDestination() {
        this.mapPicker.setMapController(this.map);
        this.mapPicker.startPickDestination();
    }

    cancelPickCustomDestination() {
        this.mapPicker.cancelPickDestination();
    }

    cancelAllPicking() {
        this.mapPicker.cancelAll();
    }

    async setCustomOrigin(orig) {
        if (!orig) return;
        this.customOrigin = orig;
        this.currentPos = { latitude: orig.latitude, longitude: orig.longitude };
        this.matchedPos = null;

        const dest = this.customDestination || { latitude: 21.0285, longitude: 105.8542 };

        this.bindings.setOriginCoordinates(renderCoordinateText(orig));

        await this._updateCustomRoute(orig, dest);
    }

    async setCustomDestination(dest) {
        if (!dest) return;
        this.customDestination = dest;

        const origin = this.customOrigin || this.currentPos || { latitude: 20.9849, longitude: 105.7935 };

        this.bindings.setDestinationCoordinates(renderCoordinateText(dest));

        await this._updateCustomRoute(origin, dest);
    }

    async _updateCustomRoute(origin, dest) {
        const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';
        try {
            const routeResult = await this.api.computeRoute(origin, dest, { vehicle_category: vCat });
            if (routeResult?.geometry) {
                const coords = decodePolyline(routeResult.geometry);
                this.fullRouteCoords = coords;
                this.directRouteGeometry = coords;
                this.map.clearAll();
                this._renderEndpointsWithDrag(origin, dest);
                this.map.renderDirectRoute(coords);
                this.map.fitBoundsToActive(coords);
                this.map.renderStations(this.stations);

                const plannedKm = routeResult.distance_m ? parseFloat((routeResult.distance_m / 1000).toFixed(2)) : 5.0;
                this.remainingTripDistanceKm = plannedKm;

                this.currentTrip = {
                    trip_id: 'CUSTOM_TRIP',
                    origin,
                    destination: dest,
                    planned_distance_m: routeResult.distance_m
                };

                if (this.state === DriverState.AVAILABLE || this.state === DriverState.TRIP_ASSIGNED) {
                    this.setState(DriverState.TRIP_ASSIGNED);
                    this.renderTripAssignedUI();
                } else if (this.state === DriverState.TRIP_ACTIVE) {
                    await this._evaluateAtCurrentPosition();
                    this.renderTripActiveUI();
                }
            }
        } catch (err) {
            console.warn('Failed to compute route for custom endpoints:', err);
            this.map.clearAll();
            this._renderEndpointsWithDrag(origin, dest);
            this.map.renderStations(this.stations);
            this.map.fitBoundsToActive([
                [origin.latitude, origin.longitude],
                [dest.latitude, dest.longitude]
            ]);
            this.bindings.showRouteUnavailable('GraphHopper chưa tìm thấy đường xe chạy kết nối điểm này. Vui lòng chọn vị trí gần đường giao thông hơn.');
        }
    }

    // ─── UI Renderers ───────────────────────────────────────────────────

    renderAvailableUI() {
        this.bindings.renderAvailable(renderAvailableCardHTML(this.customOrigin, this.customDestination), {
            accept: () => this.assignTrip(), pickOrigin: () => this.startPickCustomOrigin(),
            pickDestination: () => this.startPickCustomDestination(), goOffline: () => this.goOffline()
        });
    }

    renderOfflineUI() { this.bindings.renderOffline(renderOfflineCardHTML(), { goOnline: () => this.goOnline() }); }

    renderTripAssignedUI() {
        this.bindings.renderAssigned(renderTripAssignedCardHTML(this), {
            start: () => this.startTrip(), pickOrigin: () => this.startPickCustomOrigin(),
            pickDestination: () => this.startPickCustomDestination(), cancel: () => this.cancelTrip(),
            setSoc: (value, evaluate) => this.setBatterySoc(value, evaluate)
        });
    }

    renderTripActiveUI() {
        const etaMin = renderTripActiveEta(this.lastRecommendation, this.remainingTripDistanceKm);
        const warningBanner = renderEnergyWarningHTML(this.lastRecommendation?.energy_context);
        const recSnippet = renderDriverRecommendation(this.lastRecommendation);
        const posStatus = renderPositionStatusHTML(this.matchedPos, this.currentPos);
        const progress = this.replay.getProgressText?.() || '';
        const replayControls = renderReplayControls({ isPlaying: this.replay.isPlaying, currentIndex: this.replay.currentIndex });
        const postTripSnippet = renderPostTripBannerHTML(this.postTripStation, this.postTripRoute);
        const callbacks = {
            play: () => { this.playTrip(); this.renderTripActiveUI(); }, pause: () => { this.pauseTrip(); this.renderTripActiveUI(); },
            step: () => this.stepTrip(), unlockNavigation: () => this.unlockNavigation(), navigateViaStation: () => this.navigateViaStation(),
            switchToDestination: () => { this.chargingIntent = 'AT_DESTINATION'; this.bindings.setActiveIntent('AT_DESTINATION'); this.openStationsDrawer(); },
            cancelPostTrip: () => this.cancelPostTripStation(),
            viewCostBreakdown: () => { if (this.lastRecommendation?.ranked_candidates?.length) this.openCostBreakdownModal(this.lastRecommendation.ranked_candidates[0]); },
            completeTrip: () => { this.setState(DriverState.TRIP_COMPLETE); this.renderTripCompleteUI(); },
            setSoc: (value, evaluate) => this.setBatterySoc(value, evaluate)
        };
        this.bindings.renderActive(renderTripActiveCardHTML(this, { warningBanner, etaMin, posStatus, progress, recSnippet, postTripSnippet, replayControls }), {
            distance: this.remainingTripDistanceKm, eta: etaMin, soc: this.currentSocPct, range: this.estimatedRangeKm,
            view: renderActiveCockpitView({ distance: this.remainingTripDistanceKm, eta: etaMin, soc: this.currentSocPct, range: this.estimatedRangeKm }),
            posStatus, progress, warning: warningBanner, recommendation: recSnippet, postTrip: postTripSnippet,
            ...replayControls, navigationLocked: this._navigationLocked
        }, callbacks);
    }

    openCostBreakdownModal(candidate) {
        if (!candidate) return;
        if (this.bindings.openCostBreakdown(renderCostBreakdownHTML(candidate))) {
            const close = () => this.closeCostBreakdownModal();
            this.bindings.bindCostModalClose(close);
        }
    }

    closeCostBreakdownModal() { this.bindings.closeCostBreakdown(); }

    renderTripCompleteUI() {
        this._navigationLocked = false;
        this._selectedStationId = null;
        this._hideRecommendationPanel();
        this.bindings.renderComplete(renderTripCompleteCardHTML(this.lastRecommendation, this.postTripStation), {
            startPostTrip: async () => {
                const station = this.postTripStation;
                this.postTripStation = null;
                this.postTripRoute = null;
                await this.navigateViaStationId(station.station_id);
            },
            backAvailable: () => this.returnToAvailable()
        });
    }

}
