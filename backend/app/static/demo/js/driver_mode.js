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

import {
    classifyEnergyWarning,
    renderEnergyWarningBanner,
    renderRecommendationCard,
    renderCostBreakdown
} from './components.js';
import { TrajectoryReplayController, ReplayState } from './replay.js';
import {
    decodePolyline,
    projectPointOnRoute,
    sliceRouteFromProgress,
    computePolylineDistanceMeters,
    simplifyTrajectoryRDP
} from './map.js';

export const DriverState = {
    OFFLINE: 'OFFLINE',
    AVAILABLE: 'AVAILABLE',
    TRIP_ASSIGNED: 'TRIP_ASSIGNED',
    TO_PICKUP: 'TO_PICKUP',
    ON_TRIP: 'ON_TRIP',
    TRIP_ACTIVE: 'TRIP_ACTIVE',
    TRIP_COMPLETE: 'TRIP_COMPLETE'
};

export const VINFAST_MODEL_SPECS = {
    'VF_3': { vehicle_model: 'VF_3', display_name: 'VF 3', vehicle_type: 'EV_CAR', usable_kwh: 17.15, consumption_wh_km: 95.0, charging_supported: true, swap_supported: false },
    'VF_5': { vehicle_model: 'VF_5', display_name: 'VF 5', vehicle_type: 'EV_CAR', usable_kwh: 34.25, consumption_wh_km: 125.0, charging_supported: true, swap_supported: false },
    'HERIO_GREEN': { vehicle_model: 'HERIO_GREEN', display_name: 'Herio Green', vehicle_type: 'EV_CAR', usable_kwh: 34.25, consumption_wh_km: 125.0, charging_supported: true, swap_supported: false },
    'VF_6': { vehicle_model: 'VF_6', display_name: 'VF 6', vehicle_type: 'EV_CAR', usable_kwh: 54.83, consumption_wh_km: 145.0, charging_supported: true, swap_supported: false },
    'VF_7_ECO': { vehicle_model: 'VF_7_ECO', display_name: 'VF 7 Eco', vehicle_type: 'EV_CAR', usable_kwh: 54.83, consumption_wh_km: 155.0, charging_supported: true, swap_supported: false },
    'VF_7_PLUS': { vehicle_model: 'VF_7_PLUS', display_name: 'VF 7 Plus', vehicle_type: 'EV_CAR', usable_kwh: 69.28, consumption_wh_km: 170.0, charging_supported: true, swap_supported: false },
    'VF_8': { vehicle_model: 'VF_8', display_name: 'VF 8', vehicle_type: 'EV_CAR', usable_kwh: 80.68, consumption_wh_km: 195.0, charging_supported: true, swap_supported: false },
    'VF_9': { vehicle_model: 'VF_9', display_name: 'VF 9', vehicle_type: 'EV_CAR', usable_kwh: 113.16, consumption_wh_km: 235.0, charging_supported: true, swap_supported: false },
    'VF_E34': { vehicle_model: 'VF_E34', display_name: 'VF e34', vehicle_type: 'EV_CAR', usable_kwh: 38.55, consumption_wh_km: 135.0, charging_supported: true, swap_supported: false },
    'NERIO_GREEN': { vehicle_model: 'NERIO_GREEN', display_name: 'Nerio Green', vehicle_type: 'EV_CAR', usable_kwh: 38.55, consumption_wh_km: 135.0, charging_supported: true, swap_supported: false },
    'EVO200': { vehicle_model: 'EVO200', display_name: 'Evo200 [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 40.0, charging_supported: true, swap_supported: false },
    'EVO200_LITE': { vehicle_model: 'EVO200_LITE', display_name: 'Evo200 Lite [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 40.0, charging_supported: true, swap_supported: false },
    'FELIZ_S': { vehicle_model: 'FELIZ_S', display_name: 'Feliz S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 42.0, charging_supported: true, swap_supported: false },
    'KLARA_S_2022': { vehicle_model: 'KLARA_S_2022', display_name: 'Klara S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 45.0, charging_supported: true, swap_supported: false },
    'VENTO_S': { vehicle_model: 'VENTO_S', display_name: 'Vento S [Xe máy]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 3.22, consumption_wh_km: 45.0, charging_supported: true, swap_supported: false },
    'EVO': { vehicle_model: 'EVO', display_name: 'Evo [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 2.76, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true },
    'EVO_LITE': { vehicle_model: 'EVO_LITE', display_name: 'Evo Lite [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 1.38, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true },
    'FELIZ_II': { vehicle_model: 'FELIZ_II', display_name: 'Feliz II [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 2.76, consumption_wh_km: 40.0, charging_supported: true, swap_supported: true },
    'VIPER': { vehicle_model: 'VIPER', display_name: 'Viper [Xe máy đổi pin]', vehicle_type: 'EV_MOTORBIKE', usable_kwh: 1.38, consumption_wh_km: 38.0, charging_supported: true, swap_supported: true }
};

const EARTH_RADIUS_KM = 6371.0;

function toRad(deg) {
    return deg * Math.PI / 180;
}

export function straightLineDistanceKm(lat1, lng1, lat2, lng2) {
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
        + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2))
        * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return EARTH_RADIUS_KM * c;
}

export class DriverModeController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.options = options;
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
        window.driverMode = this;
    }

    setCatalogs(trips, vehicles, stations, scenarios = []) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
        this.scenarios = scenarios || [];
        if (!this.currentVehicle) {
            this.selectVehicleModel('VF_3');
        }
    }

    async init() {
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
        this.bindGlobalControls();
        const select = document.getElementById('cockpit-vehicle-select');
        if (select) {
            select.value = this.currentVehicle?.vehicle_model || 'VF_3';
        }
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
        const select = document.getElementById('cockpit-vehicle-select');
        if (select && select.value !== spec.vehicle_model) {
            select.value = spec.vehicle_model;
        }

        console.log(`[VEHICLE SWITCHED] Model: ${spec.vehicle_model} (${spec.usable_kwh} kWh, ${spec.consumption_wh_km} Wh/km), Current Range: ${this.estimatedRangeKm} km`);

        // Re-render HUD
        this.renderCurrentStateUI();

        // If stations drawer is open, refresh evaluations
        const drawer = document.getElementById('stations-drawer');
        if (drawer && drawer.style.display !== 'none') {
            this.refreshDrawerEvaluations();
        }
    }

    updateEstimatedRange() {
        const usable = this.currentVehicle?.usable_capacity_kwh || 17.15;
        const cons = this.currentVehicle?.consumption_wh_per_km || 95.0;
        this.estimatedRangeKm = parseFloat(((usable * 1000.0 * (this.currentSocPct / 100.0)) / cons).toFixed(1));
    }

    setBatterySoc(newSoc, triggerEvaluation = true) {
        const val = Math.min(100, Math.max(5, parseFloat(newSoc) || 10));
        this.currentSocPct = val;
        this.updateEstimatedRange();

        // Sync display elements in DOM
        if (typeof document !== 'undefined') {
            const socDisplay = document.getElementById('label-soc-slider-val');
            if (socDisplay) {
                socDisplay.textContent = `${this.currentSocPct.toFixed(0)}% (${this.estimatedRangeKm.toFixed(0)} km)`;
                socDisplay.style.color = this.currentSocPct < 20 ? '#ef4444' : (this.currentSocPct < 30 ? '#f59e0b' : '#10b981');
            }
            const assignedDisplay = document.getElementById('label-assigned-soc-val');
            if (assignedDisplay) {
                assignedDisplay.textContent = `${this.currentSocPct.toFixed(0)}% (${this.estimatedRangeKm.toFixed(0)} km)`;
                assignedDisplay.style.color = this.currentSocPct < 20 ? '#ef4444' : (this.currentSocPct < 30 ? '#f59e0b' : '#10b981');
            }
            const valTripSoc = document.getElementById('val-trip-soc');
            if (valTripSoc) {
                valTripSoc.textContent = `${this.currentSocPct.toFixed(0)}%`;
                valTripSoc.className = `stat-value ${this.currentSocPct < 20 ? 'text-danger' : ''}`;
            }
            const valTripRange = document.getElementById('val-trip-range');
            if (valTripRange) {
                valTripRange.textContent = `${this.estimatedRangeKm.toFixed(0)} km`;
            }
            const valAssignedSoc = document.getElementById('val-assigned-soc');
            if (valAssignedSoc) {
                valAssignedSoc.textContent = `${this.currentSocPct.toFixed(0)}%`;
            }
            const barFill = document.getElementById('battery-bar-fill');
            if (barFill) {
                barFill.style.width = `${Math.max(5, this.currentSocPct)}%`;
                barFill.className = `battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}`;
            }
            const slider = document.getElementById('slider-cockpit-soc');
            if (slider && document.activeElement !== slider) {
                slider.value = Math.round(this.currentSocPct);
            }
            const assignedSlider = document.getElementById('slider-assigned-soc');
            if (assignedSlider && document.activeElement !== assignedSlider) {
                assignedSlider.value = Math.round(this.currentSocPct);
            }
        }

        if (triggerEvaluation && this.state === DriverState.TRIP_ACTIVE) {
            this._evaluateAtCurrentPosition().then(() => {
                this.renderTripActiveUI();
                if (document.getElementById('stations-drawer')?.style.display !== 'none') {
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
        const badge = document.getElementById('driver-status-badge');
        if (!badge) return;

        const labels = {
            'AVAILABLE': 'SẴN SÀNG',
            'TRIP_ASSIGNED': 'ĐÃ NHẬN CHUYẾN',
            'TRIP_ACTIVE': 'ĐANG DI CHUYỂN',
            'TRIP_COMPLETE': 'HOÀN THÀNH',
            'OFFLINE': 'NGOẠI TUYẾN'
        };
        const vnLabel = labels[this.state] || this.state;

        badge.innerHTML = `${vnLabel} <span class="sr-only">${this.state}</span>`;
        badge.className = `status-badge badge-${this.state.toLowerCase()}`;
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
                    const usable = this.currentVehicle?.usable_capacity_kwh || 17.15;
                    const cons = this.currentVehicle?.consumption_wh_per_km || 95.0;
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
        if (this._navigationLocked || !candidates || candidates.length === 0) return;

        // Nếu đã có panel rồi → update, không tạo mới
        let panel = document.getElementById('recommendation-panel');

        if (!panel) {
            // Tạo panel mới
            panel = document.createElement('div');
            panel.id = 'recommendation-panel';
            panel.innerHTML = `
                <div class="rec-panel-header" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid #eee; background: #f8fafc; font-weight: 600; font-size: 13px; color: #0f172a;">
                    <span>🔌 Tìm thấy trạm sạc gần đó</span>
                    <button id="rec-panel-close" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 12px; line-height: 1; cursor: pointer; border: 1px solid #cbd5e1; border-radius: 6px; background: transparent; color: #64748b;">✕</button>
                </div>
                <div id="rec-panel-list" class="rec-panel-list" style="max-height: 360px; overflow-y: auto;"></div>
                <div class="rec-panel-footer" style="padding: 8px 14px; background: #f8fafc; border-top: 1px solid #eee; font-size: 11px; color: #64748b; text-align: center;">
                    <small>Chọn trạm để bắt đầu điều hướng</small>
                </div>
            `;
            // Style panel
            panel.style.cssText = `
                position: fixed; top: 80px; right: 20px; z-index: 1000;
                width: 320px; background: white; border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.15);
                font-family: sans-serif; overflow: hidden;
            `;
            document.body.appendChild(panel);

            // Bind close button
            document.getElementById('rec-panel-close').onclick = () => this._hideRecommendationPanel();
        }

        // Render danh sách candidates
        const list = document.getElementById('rec-panel-list');
        if (!list) return;

        list.innerHTML = candidates.map((c, idx) => {
            const st = this.stations.find(s => s.station_id === c.station_id);
            const rankColors = { 1: '#f59e0b', 2: '#3b82f6', 3: '#10b981', 4: '#8b5cf6', 5: '#6b7280' };
            const color = rankColors[idx + 1] || '#6b7280';
            const etaMin = c.eta_to_station_s ? (c.eta_to_station_s / 60).toFixed(1) : '?';
            const etaService = c.eta_to_service_complete_s ? (c.eta_to_service_complete_s / 60).toFixed(0) : '?';
            const scoreText = c.score != null ? (c.score * 100).toFixed(0) + '%' : '—';
            return `
                <div class="rec-candidate-item" data-station-id="${c.station_id}" style="
                    display: flex; align-items: center; gap: 10px;
                    padding: 10px 12px; cursor: pointer;
                    border-bottom: 1px solid #eee;
                    ${idx === 0 ? 'background: #fffbeb;' : 'background: white;'}
                ">
                    <div style="
                        width: 28px; height: 28px; border-radius: 50%;
                        background: ${color}; color: white;
                        display: flex; align-items: center; justify-content: center;
                        font-weight: bold; font-size: 14px; flex-shrink: 0;
                        border: 2px solid white; box-shadow: 0 1px 3px rgba(0,0,0,0.2);
                    ">${idx + 1}</div>
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 600; font-size: 13px; color: #1e293b; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${st?.name || c.station_id}</div>
                        <div style="font-size: 11px; color: #64748b;">
                            ETA ${etaMin} phút · Sạc ${etaService} phút
                        </div>
                    </div>
                    <div style="
                        background: ${idx === 0 ? '#f59e0b' : '#e5e7eb'};
                        color: ${idx === 0 ? 'white' : '#475569'};
                        padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600;
                    ">${scoreText}</div>
                </div>
            `;
        }).join('');

        // Bind click vào từng item
        list.querySelectorAll('.rec-candidate-item').forEach(item => {
            item.onmouseenter = () => {
                item.style.filter = 'brightness(0.95)';
            };
            item.onmouseleave = () => {
                item.style.filter = 'none';
            };
            item.onclick = () => {
                const stationId = item.dataset.stationId;
                this._hideRecommendationPanel();
                this._selectStationAndNavigate(stationId);
            };
        });
    }

    _hideRecommendationPanel() {
        const panel = document.getElementById('recommendation-panel');
        if (panel) {
            panel.remove();
        }
    }

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

        const navBtn = document.getElementById('btn-nav-station');
        if (navBtn) {
            navBtn.textContent = 'Đang dẫn đường...';
            navBtn.disabled = true;
        }

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
        const vehicleSelect = document.getElementById('cockpit-vehicle-select');
        if (vehicleSelect) {
            vehicleSelect.addEventListener('change', (e) => {
                this.selectVehicleModel(e.target.value);
            });
        }

        // Traffic delay calculation is enabled by default in backend recommendation pipeline

        document.getElementById('btn-open-stations-drawer')?.addEventListener('click', () => {
            this.openStationsDrawer();
        });

        document.getElementById('btn-close-stations-drawer')?.addEventListener('click', () => {
            this.closeStationsDrawer();
        });

        document.getElementById('btn-pick-custom-origin')?.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            this.startPickCustomOrigin();
        });

        document.getElementById('btn-pick-custom-dest')?.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            this.startPickCustomDestination();
        });

        document.getElementById('btn-cancel-pick')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.cancelAllPicking();
        });

        document.getElementById('btn-cancel-pick-dest')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.cancelAllPicking();
        });

        // Charging intent selector (En-route vs Post-Trip)
        const intentTabs = document.querySelectorAll('.charging-intent-selector .intent-tab');
        intentTabs.forEach(tab => {
            tab.addEventListener('click', async (e) => {
                const btn = e.currentTarget;
                intentTabs.forEach(t => t.classList.remove('active'));
                btn.classList.add('active');
                this.chargingIntent = btn.dataset.intent || 'EN_ROUTE';
                this.renderStationsDrawer(this.currentStationsFilter);
                await this.refreshDrawerEvaluations();
            });
        });

        // Filter tabs in stations drawer
        const filterTabs = document.querySelectorAll('.drawer-filters .filter-tab');
        filterTabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                filterTabs.forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                const filter = e.target.dataset.filter || 'ALL';
                this.currentStationsFilter = filter;
                this.renderStationsDrawer(filter);
            });
        });
    }

    async openStationsDrawer(filter = null) {
        const drawer = document.getElementById('stations-drawer');
        if (!drawer) return;
        if (filter) this.currentStationsFilter = filter;
        drawer.style.display = 'flex';
        this.renderStationsDrawer(this.currentStationsFilter);
        await this.refreshDrawerEvaluations();
    }

    closeStationsDrawer() {
        const drawer = document.getElementById('stations-drawer');
        if (drawer) drawer.style.display = 'none';
    }

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
            const cons = this.currentVehicle?.consumption_wh_per_km || 95.0;
            const usable = this.currentVehicle?.usable_capacity_kwh || 17.15;
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
        const listContainer = document.getElementById('stations-drawer-list');
        const countSpan = document.getElementById('drawer-station-count');
        if (!listContainer) return;

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

        if (countSpan) {
            countSpan.textContent = `${filtered.length} trạm khả dụng`;
        }

        if (filtered.length === 0) {
            listContainer.innerHTML = `<div class="text-center text-muted p-4">Không tìm thấy trạm phù hợp với bộ lọc.</div>`;
            return;
        }

        listContainer.innerHTML = filtered.map(st => {
            const isRec = st.station_id === topRecId;
            const isSwap = st.station_type === 'SWAP' || st.service_type === 'BATTERY_SWAP';
            const typeBadge = isSwap
                ? `<span class="badge badge-purple">🔋 Đổi pin</span>`
                : `<span class="badge badge-teal">⚡ Sạc nhanh DC</span>`;

            const totalSlots = st.total_slots || (st.charging_slots + st.swap_slots) || 'Đang mở';

            const ranked = activeRec?.ranked_candidates?.find(c => c.station_id === st.station_id);
            const cand = activeCand?.find(c => c.station_id === st.station_id);

            const fallbackLeg2Dist = straightLineDistanceKm(st.latitude, st.longitude, dest.latitude, dest.longitude);
            const fallbackLeg2Min = Math.max(1, Math.round(fallbackLeg2Dist * 2.2));
            const fallbackDetourKm = Math.max(0, parseFloat(st.distKm) + fallbackLeg2Dist - directDistKm).toFixed(1);
            const fallbackDetourMin = Math.max(0, Math.round(fallbackDetourKm * 2.2));

            let leg1Dist = st.distKm;
            let leg1Min = Math.round(parseFloat(st.distKm) * 2.2);
            let leg2Dist = '—';
            let leg2Min = '—';
            let detourKm = '—';
            let detourMin = '—';
            let waitMin = 0;
            let serviceMin = isSwap ? 5 : 20;
            let totalEtaMin = '—';
            let slots = totalSlots;
            let statusBadge = '';

            let bToStationDist = fallbackLeg2Dist.toFixed(1);
            let bToStationMin = fallbackLeg2Min;

            if (isAtDest) {
                // When evaluated from B, distance_to_station_m is the direct B -> Station leg!
                if (ranked) {
                    const d = ranked.features?.distance_to_station_m || ranked.distance_vehicle_to_station_m;
                    if (d) bToStationDist = (d / 1000).toFixed(1);
                    if (ranked.eta_to_station_s) bToStationMin = Math.round(ranked.eta_to_station_s / 60);
                } else if (cand?.route_metrics?.distance_to_station_m) {
                    bToStationDist = (cand.route_metrics.distance_to_station_m / 1000).toFixed(1);
                    if (cand.route_metrics.duration_to_station_s) {
                        bToStationMin = Math.round(cand.route_metrics.duration_to_station_s / 60);
                    }
                }
            }

            if (ranked) {
                const d1 = ranked.features?.distance_to_station_m || ranked.distance_vehicle_to_station_m;
                if (d1) {
                    leg1Dist = (d1 / 1000).toFixed(1);
                }
                if (ranked.eta_to_station_s) {
                    leg1Min = Math.round(ranked.eta_to_station_s / 60);
                }
                const d2 = ranked.features?.distance_station_to_dest_m || ranked.distance_station_to_dest_m;
                if (d2) {
                    leg2Dist = (d2 / 1000).toFixed(1);
                }
                const t2 = ranked.features?.duration_station_to_dest_s || ranked.duration_station_to_dest_s;
                if (t2) {
                    leg2Min = Math.round(t2 / 60);
                }
                const detD = ranked.features?.detour_distance_m !== undefined ? ranked.features.detour_distance_m : ranked.detour_distance_m;
                if (detD !== undefined) {
                    detourKm = (detD / 1000).toFixed(1);
                }
                const detT = ranked.features?.detour_duration_s !== undefined ? ranked.features.detour_duration_s : ranked.detour_duration_s;
                if (detT !== undefined) {
                    detourMin = Math.round(detT / 60);
                }
                if (ranked.features?.observed_queue_wait_s !== undefined) {
                    waitMin = Math.round(ranked.features.observed_queue_wait_s / 60);
                } else if (ranked.queue_wait_s !== undefined) {
                    waitMin = Math.round(ranked.queue_wait_s / 60);
                }
                if (ranked.features?.service_duration_s !== undefined) {
                    serviceMin = Math.round(ranked.features.service_duration_s / 60);
                } else if (ranked.service_duration_s !== undefined) {
                    serviceMin = Math.round(ranked.service_duration_s / 60);
                }
                if (ranked.eta_to_destination_via_station_s !== undefined) {
                    totalEtaMin = Math.round(ranked.eta_to_destination_via_station_s / 60);
                } else if (leg2Min !== '—') {
                    totalEtaMin = leg1Min + waitMin + serviceMin + parseInt(leg2Min);
                }
                slots = ranked.available_slots ?? (cand?.operational?.available_service_slots ?? totalSlots);
                statusBadge = isRec 
                    ? `<span class="badge-rec-hero">⭐ ĐỀ XUẤT TỐI ƯU ${isAtDest ? 'TẠI ĐIỂM ĐẾN (B)' : ''}</span>`
                    : `<span class="badge badge-teal">Hạng #${ranked.rank}</span>`;
            } else if (cand) {
                const rm = cand.route_metrics;
                if (rm?.distance_to_station_m) leg1Dist = (rm.distance_to_station_m / 1000).toFixed(1);
                if (rm?.duration_to_station_s) leg1Min = Math.round(rm.duration_to_station_s / 60);
                if (rm?.distance_station_to_dest_m) leg2Dist = (rm.distance_station_to_dest_m / 1000).toFixed(1);
                if (rm?.duration_station_to_dest_s) leg2Min = Math.round(rm.duration_station_to_dest_s / 60);
                if (rm?.detour_distance_m !== undefined) detourKm = (rm.detour_distance_m / 1000).toFixed(1);
                if (rm?.detour_duration_s !== undefined) detourMin = Math.round(rm.detour_duration_s / 60);
                waitMin = Math.round(cand.operational?.estimated_wait_min || 0);
                serviceMin = Math.round(cand.operational?.service_time_min || (isSwap ? 5 : 20));
                if (rm?.via_total_duration_s) {
                    totalEtaMin = Math.round((rm.via_total_duration_s + (waitMin + serviceMin) * 60) / 60);
                } else if (leg2Dist !== '—') {
                    totalEtaMin = leg1Min + waitMin + serviceMin + parseInt(leg2Min);
                }
                slots = cand.operational?.available_service_slots ?? totalSlots;
                if (!cand.eligible && cand.reason) {
                    statusBadge = `<span class="badge badge-danger" style="font-size:10px;">${cand.reason}</span>`;
                }
            }

            // Fallback for Leg 2 and Detour if still missing
            if (leg2Dist === '—') {
                leg2Dist = fallbackLeg2Dist.toFixed(1);
                leg2Min = fallbackLeg2Min;
                detourKm = fallbackDetourKm;
                detourMin = fallbackDetourMin;
                totalEtaMin = leg1Min + waitMin + serviceMin + fallbackLeg2Min;
            }

            const isSelectedPostTrip = this.postTripStation?.station_id === st.station_id;
            const trafficAdjSec = ranked?.features?.traffic_adjustment_s || 0;
            const trafficAdjMin = trafficAdjSec > 0 ? (trafficAdjSec / 60).toFixed(1) : '0.0';
            const baseTravelSec = ranked?.features?.base_travel_duration_s;
            const baseTravelMin = baseTravelSec ? (baseTravelSec / 60).toFixed(1) : leg1Min;

            let cardContent = '';
            if (isAtDest) {
                const directDriveMin = Math.round((this.remainingTripDistanceKm || 5) * 2);
                const totalPostTripMin = directDriveMin + bToStationMin + waitMin + serviceMin;

                cardContent = `
                    <div class="station-cost-grid">
                        <div class="cost-grid-item" style="grid-column: span 2; background: rgba(13, 148, 136, 0.08); border: 1px solid #0d9488;">
                            <span class="cost-grid-label" style="color: #0d9488; font-weight:700;">🏁 Cự ly từ Điểm đến (B) ➔ Trạm</span>
                            <span class="cost-grid-val" style="color: #0f172a; font-size:15px; font-weight:800;">
                                ${bToStationDist} km <small style="color:#0d9488;">(${bToStationMin} phút di chuyển sau khi tới B${parseFloat(trafficAdjMin) > 0 ? ` · +${trafficAdjMin}p tắc` : ''})</small>
                            </span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">🚗 Chuyến chính (A ➔ B thẳng)</span>
                            <span class="cost-grid-val">${(this.remainingTripDistanceKm || 5).toFixed(1)} km <small>(${directDriveMin} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">⚡ Tại trạm (Chờ + Sạc)</span>
                            <span class="cost-grid-val">${waitMin > 0 ? `⏳ ${waitMin}p chờ` : '✓ 0p chờ'} · ${serviceMin}p sạc <small>(${slots} cổng)</small></span>
                        </div>
                    </div>

                    <div class="station-cost-summary">
                        <span class="total-eta">⏱ Tổng thời gian (Tới B + Đến trạm + Sạc): <strong>${totalPostTripMin} phút</strong></span>
                        <span class="cost-score" style="color:#0d9488; font-weight:700;">✓ Đi thẳng trả khách trước</span>
                    </div>
                    <div style="font-size: 11px; color: #475569; padding: 4px 8px; background: rgba(13, 148, 136, 0.06); border: 1px solid rgba(13, 148, 136, 0.2); border-radius: 4px; margin-top: 4px;">
                        📊 <strong>Chi tiết chi phí (Cost):</strong> ${directDriveMin}p tới B + ${bToStationMin}p tới trạm + ${waitMin > 0 ? `<span style="color:#dc2626; font-weight:700;">${waitMin}p chờ</span>` : '<span style="color:#059669; font-weight:600;">0p chờ (trống)</span>'} + ${serviceMin}p sạc
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                        <button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">
                            Xem vị trí
                        </button>
                        <button class="btn btn-primary btn-sm btn-nav-post-trip-station" data-station-id="${st.station_id}" style="background:${isSelectedPostTrip ? '#059669' : '#0f172a'}; border-color:${isSelectedPostTrip ? '#059669' : '#0f172a'};">
                            ${isSelectedPostTrip ? '✓ Đang chọn sạc sau khi tới B' : '🏁 Đến B rồi sạc tại đây'}
                        </button>
                    </div>
                `;
            } else {
                cardContent = `
                    <div class="station-cost-grid">
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">🚗 Chặng 1 (Xe ➔ Trạm)</span>
                            <span class="cost-grid-val">${leg1Dist} km <small>(${baseTravelMin}p lái${parseFloat(trafficAdjMin) > 0 ? ` · +${trafficAdjMin}p tắc` : ' · thoáng'})</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">⚡ Tại trạm (Chờ + Sạc)</span>
                            <span class="cost-grid-val">${waitMin > 0 ? `⏳ <strong style="color:#dc2626;">${waitMin}p chờ</strong>` : '✓ <strong>0p chờ</strong>'} · ${serviceMin}p sạc <small>(${slots} cổng)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">🏁 Chặng 2 (Trạm ➔ B)</span>
                            <span class="cost-grid-val">${leg2Dist} km <small>(${leg2Min} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label">🔄 Lệch lộ trình (Detour)</span>
                            <span class="cost-grid-val" style="color:#d97706;">+${detourKm} km <small>(+${detourMin} phút)</small></span>
                        </div>
                    </div>

                    <div class="station-cost-summary">
                        <span class="total-eta">⏱ Tổng chuyến đi: <strong>${totalEtaMin} phút</strong></span>
                        ${ranked?.score ? `<span class="cost-score">Cost Score: <strong>${ranked.score.toFixed(3)}</strong></span>` : ''}
                    </div>
                    <div style="font-size: 11px; color: #475569; padding: 4px 8px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; margin-top: 4px;">
                        📊 <strong>Chi tiết chi phí (Cost):</strong> ${baseTravelMin}p lái xe + ${parseFloat(trafficAdjMin) > 0 ? `<span style="color:#d97706; font-weight:700;">+${trafficAdjMin}p tắc đường</span>` : '<span style="color:#059669; font-weight:600;">0p tắc</span>'} + ${waitMin > 0 ? `<span style="color:#dc2626; font-weight:700;">+${waitMin}p chờ</span>` : '<span style="color:#059669; font-weight:600;">0p chờ (trống)</span>'} + ${serviceMin}p sạc
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                        <button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">
                            Xem vị trí
                        </button>
                        <button class="btn btn-primary btn-sm btn-nav-drawer-station" data-station-id="${st.station_id}">
                            🔀 Dẫn đường ghé trạm
                        </button>
                    </div>
                `;
            }

            return `
                <div class="station-drawer-card ${isRec ? 'is-recommended' : ''}" data-station-id="${st.station_id}">
                    <div class="station-card-top">
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span class="station-card-name">Trạm ${st.station_id}</span>
                                ${statusBadge}
                            </div>
                            <div style="font-size:12px; color:#64748b; margin-top:2px;">
                                ${st.name || `Trạm năng lượng ${st.station_id}`}
                            </div>
                        </div>
                        ${typeBadge}
                    </div>

                    ${cardContent}
                </div>
            `;
        }).join('');

        // Bind clicks on cards
        listContainer.querySelectorAll('.btn-nav-drawer-station').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const stId = btn.dataset.stationId;
                this.navigateViaStationId(stId);
            });
        });

        listContainer.querySelectorAll('.btn-nav-post-trip-station').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const stId = btn.dataset.stationId;
                await this.setPostTripStation(stId);
            });
        });

        listContainer.querySelectorAll('.btn-zoom-station').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const lat = parseFloat(btn.dataset.lat);
                const lng = parseFloat(btn.dataset.lng);
                this.map.map.flyTo([lat, lng], 16);
            });
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
        if (!this.map?.map) return;
        this.cancelPickCustomDestination();
        this.isPickingOrigin = true;

        const banner = document.getElementById('map-picker-banner');
        const textSpan = document.getElementById('map-picker-banner-text');
        if (textSpan) textSpan.textContent = '📍 Chạm vào vị trí bất kỳ trên bản đồ để đặt ĐIỂM XUẤT PHÁT (A)';
        if (banner) banner.style.display = 'flex';

        const mapContainer = this.map.map.getContainer();
        mapContainer.classList.add('map-picking-active');
        document.getElementById('btn-pick-custom-origin')?.classList.add('active');
        document.getElementById('btn-pick-origin-map')?.classList.add('active');
        document.getElementById('btn-assigned-pick-origin')?.classList.add('active');

        if (this._onMapPickClick) {
            this.map.map.off('click', this._onMapPickClick);
        }

        this._onMapPickClick = async (e) => {
            const { lat, lng } = e.latlng;
            this.cancelPickCustomOrigin();
            await this.setCustomOrigin({ latitude: lat, longitude: lng });
        };

        setTimeout(() => {
            if (this.isPickingOrigin && this.map?.map) {
                this.map.map.once('click', this._onMapPickClick);
            }
        }, 50);
    }

    cancelPickCustomOrigin() {
        this.isPickingOrigin = false;
        const banner = document.getElementById('map-picker-banner');
        if (banner) banner.style.display = 'none';

        const mapContainer = this.map?.map?.getContainer();
        if (mapContainer) mapContainer.classList.remove('map-picking-active');
        document.getElementById('btn-pick-custom-origin')?.classList.remove('active');
        document.getElementById('btn-pick-origin-map')?.classList.remove('active');
        document.getElementById('btn-assigned-pick-origin')?.classList.remove('active');

        if (this._onMapPickClick && this.map?.map) {
            this.map.map.off('click', this._onMapPickClick);
            this._onMapPickClick = null;
        }
    }

    startPickCustomDestination() {
        if (!this.map?.map) return;
        this.cancelPickCustomOrigin();
        this.isPickingDestination = true;

        const banner = document.getElementById('map-picker-banner');
        const textSpan = document.getElementById('map-picker-banner-text');
        if (textSpan) textSpan.textContent = '🏁 Chạm vào vị trí bất kỳ trên bản đồ để đặt ĐIỂM ĐẾN (B)';
        if (banner) banner.style.display = 'flex';

        const mapContainer = this.map.map.getContainer();
        mapContainer.classList.add('map-picking-active');
        document.getElementById('btn-pick-custom-dest')?.classList.add('active');
        document.getElementById('btn-pick-dest-map')?.classList.add('active');
        document.getElementById('btn-assigned-pick-dest')?.classList.add('active');

        if (this._onMapPickClick) {
            this.map.map.off('click', this._onMapPickClick);
        }

        this._onMapPickClick = async (e) => {
            const { lat, lng } = e.latlng;
            this.cancelPickCustomDestination();
            await this.setCustomDestination({ latitude: lat, longitude: lng });
        };

        setTimeout(() => {
            if (this.isPickingDestination && this.map?.map) {
                this.map.map.once('click', this._onMapPickClick);
            }
        }, 50);
    }

    cancelPickCustomDestination() {
        this.isPickingDestination = false;
        const banner = document.getElementById('map-picker-banner');
        if (banner) banner.style.display = 'none';

        const mapContainer = this.map?.map?.getContainer();
        if (mapContainer) mapContainer.classList.remove('map-picking-active');
        document.getElementById('btn-pick-custom-dest')?.classList.remove('active');
        document.getElementById('btn-pick-dest-map')?.classList.remove('active');
        document.getElementById('btn-assigned-pick-dest')?.classList.remove('active');

        if (this._onMapPickClick && this.map?.map) {
            this.map.map.off('click', this._onMapPickClick);
            this._onMapPickClick = null;
        }
    }

    cancelAllPicking() {
        this.cancelPickCustomOrigin();
        this.cancelPickCustomDestination();
    }

    async setCustomOrigin(orig) {
        if (!orig) return;
        this.customOrigin = orig;
        this.currentPos = { latitude: orig.latitude, longitude: orig.longitude };
        this.matchedPos = null;

        const dest = this.customDestination || { latitude: 21.0285, longitude: 105.8542 };

        const origEl = document.getElementById('text-origin-coords');
        if (origEl) origEl.textContent = `${orig.latitude.toFixed(4)}, ${orig.longitude.toFixed(4)}`;

        await this._updateCustomRoute(orig, dest);
    }

    async setCustomDestination(dest) {
        if (!dest) return;
        this.customDestination = dest;

        const origin = this.customOrigin || this.currentPos || { latitude: 20.9849, longitude: 105.7935 };

        const destEl = document.getElementById('text-dest-coords');
        if (destEl) destEl.textContent = `${dest.latitude.toFixed(4)}, ${dest.longitude.toFixed(4)}`;

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
            alert('GraphHopper chưa tìm thấy đường xe chạy kết nối điểm này. Vui lòng chọn vị trí gần đường giao thông hơn.');
        }
    }

    // ─── UI Renderers ───────────────────────────────────────────────────

    renderAvailableUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const origLat = (this.customOrigin?.latitude || 20.9849).toFixed(4);
        const origLng = (this.customOrigin?.longitude || 105.7935).toFixed(4);
        const destLat = (this.customDestination?.latitude || 21.0285).toFixed(4);
        const destLng = (this.customDestination?.longitude || 105.8542).toFixed(4);

        container.innerHTML = `
            <div class="driver-available-card">
                <div class="card-status-indicator">
                    <span class="pulse-dot green"></span>
                    <h3>Sẵn sàng bắt đầu hành trình</h3>
                </div>
                <p class="text-muted" style="margin-top: 4px; font-size: 13px;">
                    Dẫn đường thông minh & phân tích lộ trình thói quen. Thiết lập điểm xuất phát và điểm đến:
                </p>

                <div class="endpoints-box mt-3" style="background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 13px; margin-bottom: 8px;">
                        <span style="color: #10b981; font-weight: 600;">📍 Điểm A (Xuất phát):</span>
                        <span id="text-origin-coords" class="text-muted" style="font-size: 12px; font-family: monospace;">${origLat}, ${origLng}</span>
                    </div>
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 13px;">
                        <span style="color: #ef4444; font-weight: 600;">🏁 Điểm B (Điểm đến):</span>
                        <span id="text-dest-coords" class="text-muted" style="font-size: 12px; font-family: monospace;">${destLat}, ${destLng}</span>
                    </div>
                </div>

                <div class="driver-actions mt-3">
                    <div style="display: flex; gap: 8px; margin-bottom: 10px;">
                        <button id="btn-pick-origin-map" class="btn btn-outline flex-1" style="font-size: 13px;">
                            📍 Đổi điểm đi (A)
                        </button>
                        <button id="btn-pick-dest-map" class="btn btn-outline flex-1" style="font-size: 13px;">
                            🏁 Đổi điểm đến (B)
                        </button>
                    </div>
                    <button id="btn-accept-trip" class="btn btn-primary btn-lg btn-block">
                        🚀 Tạo lộ trình & Bắt đầu
                    </button>
                    <button id="btn-go-offline" class="btn btn-outline btn-sm mt-2">
                        Chuyển ngoại tuyến
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-accept-trip')?.addEventListener('click', () => {
            this.assignTrip();
        });

        document.getElementById('btn-pick-origin-map')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.startPickCustomOrigin();
        });

        document.getElementById('btn-pick-dest-map')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.startPickCustomDestination();
        });

        document.getElementById('btn-go-offline')?.addEventListener('click', () => this.goOffline());
    }

    renderOfflineUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-available-card text-center">
                <span class="pulse-dot gray"></span>
                <h3>Tài xế đang ngoại tuyến</h3>
                <p class="text-muted">Bật trực tuyến để nhận phân phối chuyến đi.</p>
                <button id="btn-go-online" class="btn btn-primary btn-lg mt-3">
                    Bật trực tuyến
                </button>
            </div>
        `;

        document.getElementById('btn-go-online')?.addEventListener('click', () => this.goOnline());
    }

    renderTripAssignedUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-nav-hud">
                <div class="hud-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span class="badge badge-info">
                        ĐÃ NHẬN CHUYẾN
                        <span class="sr-only">TRIP_ASSIGNED TRIP ASSIGNED</span>
                    </span>
                    <h3 style="margin: 0; font-size: 18px;">${this.currentTrip?.trip_id}</h3>
                </div>

                <div class="hud-details" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
                    <div class="stat-box">
                        <span class="stat-label">Phương tiện</span>
                        <strong class="stat-value" style="font-size: 14px;">${this.currentVehicle?.vehicle_model || 'VF 3'}</strong>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">Cự ly dự kiến</span>
                        <strong class="stat-value" style="font-size: 14px;">${(this.currentTrip?.planned_distance_m / 1000).toFixed(1)} km</strong>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">Dung lượng Pin</span>
                        <strong id="val-assigned-soc" class="stat-value" style="font-size: 14px;">${this.currentSocPct.toFixed(0)}%</strong>
                    </div>
                </div>

                <!-- Interactive Battery SOC Adjuster -->
                <div class="cockpit-soc-control" style="margin-bottom: 14px; padding: 10px 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase;">
                            🔋 Tùy chỉnh mức Pin ban đầu (SOC)
                        </span>
                        <span id="label-assigned-soc-val" style="font-size: 12px; font-weight: 700; color: ${this.currentSocPct < 20 ? '#ef4444' : (this.currentSocPct < 30 ? '#f59e0b' : '#10b981')};">
                            ${this.currentSocPct.toFixed(0)}% (${this.estimatedRangeKm.toFixed(0)} km)
                        </span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="range" id="slider-assigned-soc" min="5" max="100" step="1" value="${Math.round(this.currentSocPct)}"
                               style="flex: 1; accent-color: #0d9488; cursor: pointer; height: 6px;">
                        <div style="display: flex; gap: 4px;">
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="12" style="padding: 2px 6px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">12%</button>
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="22" style="padding: 2px 6px; font-size: 11px; color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">22%</button>
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="85" style="padding: 2px 6px; font-size: 11px; color: #10b981; border-color: rgba(16, 185, 129, 0.5);">85%</button>
                        </div>
                    </div>
                </div>

                <div class="driver-actions">
                    <button id="btn-start-driving" class="btn btn-success btn-lg btn-block">
                        ▶ Bắt đầu lái xe
                    </button>
                    <div style="display: flex; gap: 8px; margin-top: 8px;">
                        <button id="btn-assigned-pick-origin" class="btn btn-outline flex-1" style="font-size: 13px;">
                            📍 Đổi điểm xuất phát (A)
                        </button>
                        <button id="btn-assigned-pick-dest" class="btn btn-outline flex-1" style="font-size: 13px;">
                            🏁 Đổi điểm đến (B)
                        </button>
                    </div>
                    <button id="btn-cancel-trip" class="btn btn-outline btn-sm mt-2">
                        Hủy nhận chuyến
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-start-driving')?.addEventListener('click', () => this.startTrip());
        document.getElementById('btn-assigned-pick-origin')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.startPickCustomOrigin();
        });
        document.getElementById('btn-assigned-pick-dest')?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.startPickCustomDestination();
        });
        document.getElementById('btn-cancel-trip')?.addEventListener('click', () => this.cancelTrip());

        const sliderAssigned = document.getElementById('slider-assigned-soc');
        sliderAssigned?.addEventListener('input', (e) => {
            this.setBatterySoc(parseFloat(e.target.value), false);
        });
        sliderAssigned?.addEventListener('change', (e) => {
            this.setBatterySoc(parseFloat(e.target.value), false);
        });
        document.querySelectorAll('.btn-preset-assigned-soc').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const s = parseFloat(e.target.dataset.soc);
                this.setBatterySoc(s, false);
            });
        });
    }

    renderTripActiveUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        let etaMin = '—';
        if (this.lastRecommendation?.ranked_candidates?.length > 0) {
            const top = this.lastRecommendation.ranked_candidates[0];
            etaMin = (top.eta_to_station_s / 60).toFixed(0);
        } else if (this.remainingTripDistanceKm > 0) {
            etaMin = Math.round(this.remainingTripDistanceKm * 2).toString();
        }

        const warningBanner = renderEnergyWarningBanner(this.lastRecommendation?.energy_context);

        let recSnippet = '';
        if (this.lastRecommendation?.has_recommendation && this.lastRecommendation.ranked_candidates?.length > 0) {
            const top = this.lastRecommendation.ranked_candidates[0];
            const isSwap = top.service_type === 'BATTERY_SWAP';
            const detourKm = top.features?.detour_distance_m != null
                ? (top.features.detour_distance_m / 1000).toFixed(1)
                : '0.5';
            const detourMin = top.features?.detour_duration_s != null
                ? (top.features.detour_duration_s / 60).toFixed(0)
                : '2';
            const etaStationMin = (top.eta_to_station_s / 60).toFixed(0);
            const serviceMin = top.features?.service_duration_s != null
                ? (top.features.service_duration_s / 60).toFixed(0)
                : '15';
            const completionMin = top.eta_to_service_complete_s != null
                ? (top.eta_to_service_complete_s / 60).toFixed(0)
                : Math.round(top.final_cost_s / 60).toString();
            const etaTotalMin = top.eta_to_destination_via_station_s != null
                ? (top.eta_to_destination_via_station_s / 60).toFixed(0)
                : (top.features?.duration_station_to_dest_s != null
                    ? Math.round((top.eta_to_service_complete_s + top.features.duration_station_to_dest_s) / 60).toString()
                    : completionMin);
            const cap = top.features?.available_capacity;
            const capText = cap != null ? ` · ${cap} vị trí còn trống` : '';

            const leg1D = top.distance_vehicle_to_station_m ? (top.distance_vehicle_to_station_m / 1000).toFixed(1) : '1.9';
            const leg2D = top.features?.distance_station_to_dest_m != null
                ? (top.features.distance_station_to_dest_m / 1000).toFixed(1)
                : (top.distance_station_to_dest_m ? (top.distance_station_to_dest_m / 1000).toFixed(1) : '—');
            const leg2T = top.features?.duration_station_to_dest_s != null
                ? Math.round(top.features.duration_station_to_dest_s / 60)
                : (top.duration_station_to_dest_s ? Math.round(top.duration_station_to_dest_s / 60) : '—');
            const waitT = top.queue_wait_s != null ? Math.round(top.queue_wait_s / 60) : 0;
            const costVal = top.score != null ? top.score.toFixed(3) : (top.final_cost_s ? (top.final_cost_s / 60).toFixed(1) : '—');

            recSnippet = `
                <div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}" style="margin-top: 12px; padding: 12px; background: rgba(13, 148, 136, 0.1); border: 1px solid rgba(13, 148, 136, 0.3); border-radius: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong>Trạm ${top.station_id}</strong> — ${isSwap ? 'Đổi pin nhanh' : 'Sạc pin'}
                            <span class="sr-only">${top.station_id} ${isSwap ? 'Battery Swap' : 'Charging'}</span>
                            <div class="text-sm" style="margin-top: 4px; color: #cbd5e1; font-size: 12px; line-height: 1.5;">
                                🚗 Đến trạm: <strong>${etaStationMin}p</strong> · Sạc/đổi: <strong>${serviceMin}p</strong> · Về đích: <strong>${etaTotalMin}p</strong>
                            </div>
                        </div>
                        <span class="badge ${isSwap ? 'badge-purple' : 'badge-teal'}">
                            Đề xuất tối ưu
                            <span class="sr-only">Recommended</span>
                        </span>
                    </div>

                    <!-- Bảng thông số tính toán Cost trực quan -->
                    <div class="station-cost-grid mt-2" style="background: rgba(15, 23, 42, 0.5); border: 1px solid rgba(51, 65, 85, 0.7);">
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🚗 Chặng 1 (Xe ➔ Trạm)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${leg1D} km <small style="color:#cbd5e1;">(${etaStationMin} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">⚡ Tại trạm (Chờ + Sạc)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${waitT}p chờ · ${serviceMin}p sạc${capText}</span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🏁 Chặng 2 (Trạm ➔ B)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${leg2D} km <small style="color:#cbd5e1;">(${leg2T} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🔄 Lệch lộ trình (Detour)</span>
                            <span class="cost-grid-val" style="color: #f59e0b;">+${detourKm} km <span class="sr-only">detour</span><small style="color:#fcd34d;">(+${detourMin} phút)</small></span>
                        </div>
                    </div>

                    <div class="station-cost-summary mt-2" style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5);">
                        <span class="total-eta" style="color: #38bdf8;">⏱ Tổng thời gian chuyến đi: <strong>${etaTotalMin} phút</strong></span>
                        <span class="cost-score" style="color: #e2e8f0;">Điểm Cost: <strong>${costVal}</strong></span>
                    </div>

                    <div class="d-flex gap-2 mt-2" style="display: flex; gap: 8px; margin-top: 10px;">
                        <button id="btn-nav-station" class="btn btn-accent btn-sm flex-1" style="flex: 1.1;">
                            🔀 Ghé sạc ngay
                            <span class="sr-only">Navigate Via Station</span>
                        </button>
                        <button id="btn-switch-post-trip-modal" class="btn btn-primary btn-sm flex-1" style="flex: 1.1; background: #0f172a; border-color: #334155;">
                            🏁 Đến B rồi sạc
                        </button>
                        <button id="btn-view-cost-breakdown" class="btn btn-outline btn-sm" style="padding: 4px 8px; font-size: 12px;">
                            📊
                        </button>
                    </div>
                </div>
            `;
        }

        const posStatus = this.matchedPos
            ? `<span class="text-success">Khớp đường: ${this.matchedPos.road_segment_id || 'đã khớp'} <span class="sr-only">Road: ${this.matchedPos.road_segment_id || 'matched'}</span></span>`
            : (this.currentPos
                ? `<span class="text-warning">GPS trực tiếp (${this.currentPos.latitude.toFixed(4)}, ${this.currentPos.longitude.toFixed(4)}) <span class="sr-only">Raw GPS</span></span>`
                : '<span class="text-muted">Đang định vị...</span>');

        const progress = this.replay.getProgressText?.() || '';
        const isPlaying = this.replay.isPlaying;
        const playBtnText = isPlaying ? '▶ Đang chạy...' : (this.replay.currentIndex > 0 ? '▶ Tiếp tục' : '▶ Bắt đầu');
        const playBtnClass = isPlaying ? 'btn btn-outline btn-sm flex-1' : 'btn btn-primary btn-sm flex-1';
        const pauseBtnClass = isPlaying ? 'btn btn-primary btn-sm flex-1' : 'btn btn-outline btn-sm flex-1';

        const postTripSnippet = this.postTripStation ? `
            <div class="post-trip-banner" style="background: rgba(15, 23, 42, 0.85); border: 1px solid #0d9488; border-radius: 10px; padding: 12px 14px; margin-top: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; color: #2dd4bf; font-size: 13px; display: flex; align-items: center; gap: 6px;">
                        <span>🏁</span> ĐÃ ĐẶT SẠC SAU KHI TỚI B
                    </span>
                    <button id="btn-cancel-post-trip" class="btn btn-outline btn-xs" style="color: #94a3b8; border-color: #475569; padding: 2px 6px;">✕ Hủy</button>
                </div>
                <div style="font-size: 12px; color: #e2e8f0; margin-top: 6px;">
                    Xe đang chạy thẳng đến điểm B. Sau khi trả khách sẽ tiếp tục di chuyển đến <strong>Trạm ${this.postTripStation.station_id}</strong> (${this.postTripRoute?.distance_m ? (this.postTripRoute.distance_m / 1000).toFixed(1) : '1.5'} km).
                </div>
            </div>
        ` : '';

        // If active HUD already mounted in DOM, perform fast in-place property updates to prevent losing slider focus
        const existingHud = container.querySelector('#driver-active-hud');
        if (existingHud) {
            const elemDist = document.getElementById('val-remaining-dist');
            if (elemDist) elemDist.innerHTML = `${this.remainingTripDistanceKm.toFixed(1)} <small>km</small>`;
            const elemEta = document.getElementById('val-trip-eta');
            if (elemEta) elemEta.innerHTML = `${etaMin} <small>phút</small><span class="sr-only">min</span>`;
            const elemSoc = document.getElementById('val-trip-soc');
            if (elemSoc) {
                elemSoc.textContent = `${this.currentSocPct.toFixed(0)}%`;
                elemSoc.className = `stat-value ${this.currentSocPct < 20 ? 'text-danger' : ''}`;
            }
            const elemRange = document.getElementById('val-trip-range');
            if (elemRange) elemRange.innerHTML = `${this.estimatedRangeKm.toFixed(0)} <small>km</small>`;
            const barFill = document.getElementById('battery-bar-fill');
            if (barFill) {
                barFill.style.width = `${Math.max(5, this.currentSocPct)}%`;
                barFill.className = `battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}`;
            }
            const labelSocSlider = document.getElementById('label-soc-slider-val');
            if (labelSocSlider) {
                labelSocSlider.textContent = `${this.currentSocPct.toFixed(0)}% (${this.estimatedRangeKm.toFixed(0)} km)`;
                labelSocSlider.style.color = this.currentSocPct < 20 ? '#ef4444' : (this.currentSocPct < 30 ? '#f59e0b' : '#10b981');
            }
            const slider = document.getElementById('slider-cockpit-soc');
            if (slider && document.activeElement !== slider) {
                slider.value = Math.round(this.currentSocPct);
            }
            const posElem = document.getElementById('hud-pos-status');
            if (posElem) posElem.innerHTML = posStatus;
            const progElem = document.getElementById('hud-progress-status');
            if (progElem) progElem.textContent = progress;

            const warnContainer = document.getElementById('hud-warning-container');
            if (warnContainer) warnContainer.innerHTML = warningBanner;

            const recContainer = document.getElementById('hud-rec-container');
            if (recContainer) {
                recContainer.innerHTML = recSnippet;
                document.getElementById('btn-nav-station')?.addEventListener('click', () => this.navigateViaStation());
                document.getElementById('btn-switch-post-trip-modal')?.addEventListener('click', () => {
                    this.chargingIntent = 'AT_DESTINATION';
                    document.querySelectorAll('.charging-intent-selector .intent-tab').forEach(t => {
                        t.classList.toggle('active', t.dataset.intent === 'AT_DESTINATION');
                    });
                    this.openStationsDrawer();
                });
                document.getElementById('btn-view-cost-breakdown')?.addEventListener('click', () => {
                    if (this.lastRecommendation?.ranked_candidates?.length > 0) {
                        this.openCostBreakdownModal(this.lastRecommendation.ranked_candidates[0]);
                    }
                });
            }

            const postTripContainer = document.getElementById('hud-post-trip-container');
            if (postTripContainer) {
                postTripContainer.innerHTML = postTripSnippet;
                document.getElementById('btn-cancel-post-trip')?.addEventListener('click', () => this.cancelPostTripStation());
            }

            const btnPlay = document.getElementById('btn-driver-replay-play');
            if (btnPlay) {
                btnPlay.innerHTML = playBtnText;
                btnPlay.className = playBtnClass;
            }
            const btnPause = document.getElementById('btn-driver-replay-pause');
            if (btnPause) {
                btnPause.className = pauseBtnClass;
            }
            const changeStationBtn = document.getElementById('btn-change-station');
            if (changeStationBtn) {
                changeStationBtn.style.display = this._navigationLocked ? 'block' : 'none';
            }
            return;
        }

        // Full initial render
        container.innerHTML = `
            <div class="driver-nav-hud" id="driver-active-hud" data-hud-state="TRIP_ACTIVE">
                <div id="hud-warning-container">
                    ${warningBanner}
                </div>

                <div class="nav-metrics-card">
                    <div class="nav-destination" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div>
                            <span class="text-sm text-muted" style="font-size: 11px; text-transform: uppercase;">Điểm đến</span>
                            <div class="dest-name" style="font-weight: 700; font-size: 16px;">
                                Điểm trả khách
                                <span class="sr-only">Passenger Drop-off (Trả khách)</span>
                            </div>
                        </div>
                        <span class="badge badge-teal">Đang di chuyển</span>
                    </div>

                    <div class="nav-stats-grid" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
                        <div class="stat-box">
                            <span class="stat-label">Cự ly còn lại</span>
                            <span class="stat-value" id="val-remaining-dist">${this.remainingTripDistanceKm.toFixed(1)} <small>km</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">ETA</span>
                            <span class="stat-value" id="val-trip-eta">${etaMin} <small>phút</small><span class="sr-only">min</span></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Pin (SOC)</span>
                            <span class="stat-value ${this.currentSocPct < 20 ? 'text-danger' : ''}" id="val-trip-soc">${this.currentSocPct.toFixed(0)}%</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Tầm xa</span>
                            <span class="stat-value" id="val-trip-range">${this.estimatedRangeKm.toFixed(0)} <small>km</small></span>
                        </div>
                    </div>

                    <div class="battery-bar-container" style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div id="battery-bar-fill" class="battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}"
                             style="width: ${Math.max(5, this.currentSocPct)}%; height: 100%;"></div>
                    </div>

                    <!-- Interactive Battery SOC Adjuster -->
                    <div class="cockpit-soc-control" style="margin-top: 10px; padding: 8px 10px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase;">
                                🔋 Điều chỉnh mức Pin (SOC)
                            </span>
                            <span id="label-soc-slider-val" style="font-size: 12px; font-weight: 700; color: ${this.currentSocPct < 20 ? '#ef4444' : (this.currentSocPct < 30 ? '#f59e0b' : '#10b981')};">
                                ${this.currentSocPct.toFixed(0)}% (${this.estimatedRangeKm.toFixed(0)} km)
                            </span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <input type="range" id="slider-cockpit-soc" min="5" max="100" step="1" value="${Math.round(this.currentSocPct)}"
                                   style="flex: 1; accent-color: #0d9488; cursor: pointer; height: 6px;">
                            <div class="quick-soc-presets" style="display: flex; gap: 4px;">
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="12" title="Mức pin nguy cấp (< 15%)"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">12%</button>
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="22" title="Mức pin khuyến cáo (< 30%)"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">22%</button>
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="85" title="Mức pin an toàn"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #10b981; border-color: rgba(16, 185, 129, 0.5);">85%</button>
                            </div>
                        </div>
                    </div>

                    <div class="text-xs text-muted mt-2" style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span id="hud-pos-status">${posStatus}</span>
                        <span id="hud-progress-status">${progress}</span>
                    </div>
                </div>

                <div id="hud-rec-container">
                    ${recSnippet}
                </div>

                <div id="hud-post-trip-container">
                    ${postTripSnippet}
                </div>

                <div class="driver-controls mt-3">
                    <div class="replay-controls d-flex gap-2 mb-2" style="display: flex; gap: 8px;">
                        <button id="btn-driver-replay-play" class="${playBtnClass}">${playBtnText}</button>
                        <button id="btn-driver-replay-pause" class="${pauseBtnClass}">⏸ Tạm dừng</button>
                        <button id="btn-driver-replay-step" class="btn btn-outline btn-sm flex-1">⏭ Từng bước</button>
                    </div>
                    <button id="btn-change-station" class="btn btn-sm btn-outline-secondary" style="margin-top: 6px; width: 100%; display: ${this._navigationLocked ? 'block' : 'none'};"
                        onclick="driverMode.unlockNavigation()">
                        🔄 Đổi trạm sạc khác
                    </button>
                    <button id="btn-complete-trip" class="btn btn-outline btn-sm btn-block">
                        ✓ Hoàn thành chuyến đi
                    </button>
                </div>
            </div>
        `;

        // Bind interactive controls
        document.getElementById('btn-driver-replay-play')?.addEventListener('click', () => {
            this.playTrip();
            this.renderTripActiveUI();
        });
        document.getElementById('btn-driver-replay-pause')?.addEventListener('click', () => {
            this.pauseTrip();
            this.renderTripActiveUI();
        });
        document.getElementById('btn-driver-replay-step')?.addEventListener('click', () => this.stepTrip());
        document.getElementById('btn-change-station')?.addEventListener('click', () => {
            this.unlockNavigation();
        });
        document.getElementById('btn-nav-station')?.addEventListener('click', () => this.navigateViaStation());
        document.getElementById('btn-switch-post-trip-modal')?.addEventListener('click', () => {
            this.chargingIntent = 'AT_DESTINATION';
            document.querySelectorAll('.charging-intent-selector .intent-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.intent === 'AT_DESTINATION');
            });
            this.openStationsDrawer();
        });
        document.getElementById('btn-cancel-post-trip')?.addEventListener('click', () => {
            this.cancelPostTripStation();
        });
        document.getElementById('btn-view-cost-breakdown')?.addEventListener('click', () => {
            if (this.lastRecommendation?.ranked_candidates?.length > 0) {
                this.openCostBreakdownModal(this.lastRecommendation.ranked_candidates[0]);
            }
        });
        document.getElementById('btn-complete-trip')?.addEventListener('click', () => {
            this.setState(DriverState.TRIP_COMPLETE);
            this.renderTripCompleteUI();
        });

        const slider = document.getElementById('slider-cockpit-soc');
        slider?.addEventListener('input', (e) => {
            this.setBatterySoc(parseFloat(e.target.value), false);
        });
        slider?.addEventListener('change', (e) => {
            this.setBatterySoc(parseFloat(e.target.value), true);
        });
        document.querySelectorAll('.btn-quick-soc').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const s = parseFloat(e.target.dataset.soc);
                this.setBatterySoc(s, true);
            });
        });
    }

    openCostBreakdownModal(candidate) {
        const modal = document.getElementById('cost-breakdown-modal');
        const body = document.getElementById('cost-modal-body');
        if (!modal || !body || !candidate) return;

        body.innerHTML = renderCostBreakdown(candidate);
        modal.style.display = 'flex';

        const closeModal = () => {
            modal.style.display = 'none';
        };
        document.getElementById('btn-close-cost-modal')?.addEventListener('click', closeModal, { once: true });
        document.getElementById('cost-modal-backdrop')?.addEventListener('click', closeModal, { once: true });
    }

    closeCostBreakdownModal() {
        const modal = document.getElementById('cost-breakdown-modal');
        if (modal) modal.style.display = 'none';
    }

    renderTripCompleteUI() {
        this._navigationLocked = false;
        this._selectedStationId = null;
        this._hideRecommendationPanel();

        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const warningBanner = renderEnergyWarningBanner(this.lastRecommendation?.energy_context);
        const recCard = renderRecommendationCard(this.lastRecommendation);

        container.innerHTML = `
            <div class="driver-nav-hud">
                <div class="completion-header text-center" style="text-align: center; margin-bottom: 16px;">
                    <span class="check-icon" style="display: inline-block; width: 44px; height: 44px; line-height: 44px; background: rgba(16, 185, 129, 0.2); color: #10b981; border-radius: 50%; font-size: 22px; font-weight: bold; margin-bottom: 8px;">✓</span>
                    <h3>Chuyến đi hoàn tất</h3>
                    <p class="text-muted" style="font-size: 13px;">Hành khách đã xuống xe an toàn.</p>
                </div>

                ${warningBanner}

                ${this.postTripStation ? `
                    <div style="background: rgba(13, 148, 136, 0.12); border: 1px solid #0d9488; border-radius: 10px; padding: 14px; margin-top: 12px; margin-bottom: 12px;">
                        <div style="font-weight: 700; color: #0d9488; font-size: 14px;">⚡ BƯỚC TIẾP THEO: ĐI SẠC PIN</div>
                        <p style="font-size: 13px; color: #cbd5e1; margin: 4px 0 10px 0;">
                            Bạn đã chọn sạc tại <strong>Trạm ${this.postTripStation.station_id}</strong> (${this.postTripStation.name || ''}) sau khi trả khách.
                        </p>
                        <button id="btn-start-post-trip-nav" class="btn btn-success btn-lg btn-block">
                            ⚡ Dẫn đường tới Trạm ${this.postTripStation.station_id} ngay
                        </button>
                    </div>
                ` : ''}

                <div class="mt-3">
                    ${recCard}
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-back-available" class="btn btn-primary btn-lg btn-block">
                        Sẵn sàng chuyến tiếp theo
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-start-post-trip-nav')?.addEventListener('click', async () => {
            const st = this.postTripStation;
            this.postTripStation = null;
            this.postTripRoute = null;
            await this.navigateViaStationId(st.station_id);
        });
        document.getElementById('btn-back-available')?.addEventListener('click', () => this.returnToAvailable());
    }
}
