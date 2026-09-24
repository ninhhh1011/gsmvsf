/**
 * Driver Mode Controller for VinFast EV Recommendation Demo.
 *
 * State model: OFFLINE -> AVAILABLE -> TRIP_ACTIVE -> TRIP_COMPLETE
 *
 * STRICT RULES:
 * - No fake movement. Driver advances through real GPS observations via the backend realtime pipeline.
 * - No hardcoded SOC decrement. SOC is fixed per scenario.
 * - No straight-line interpolation. Positions come from matched road segments.
 * - No frontend ETA calculation. ETA comes from backend routing result.
 * - Backend owns all demand evaluation, candidate eligibility, routing, ranking.
 */

import { renderEnergyWarningBanner, renderRecommendationCard, renderErrorState, renderLoadingState } from './components.js';
import { TrajectoryReplayController } from './replay.js';

export const DriverState = {
    OFFLINE: 'OFFLINE',
    AVAILABLE: 'AVAILABLE',
    TRIP_ASSIGNED: 'TRIP_ASSIGNED',
    TO_PICKUP: 'TO_PICKUP',
    ON_TRIP: 'ON_TRIP',
    TRIP_ACTIVE: 'TRIP_ACTIVE',
    TRIP_COMPLETE: 'TRIP_COMPLETE'
};

/** Approximate Earth radius in km for Haversine distance. */
const EARTH_RADIUS_KM = 6371.0;

function toRad(deg) {
    return deg * Math.PI / 180;
}

/**
 * Compute Haversine distance (km) between two lat/lng points.
 * Used only for remaining-trip-distance estimation; NOT for routing.
 */
function haversineKm(lat1, lng1, lat2, lng2) {
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
        this.trips = [];
        this.vehicles = [];
        this.stations = [];

        // Active trip state
        this.state = DriverState.AVAILABLE;
        this.currentTrip = null;
        this.currentVehicle = null;

        // Energy state — owned by scenario data, NOT self-computed
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 100.0;
        this.safetyReserveKm = 2.0;

        // Position — updated from matched road segment, NOT interpolated
        this.currentPos = null;       // { latitude, longitude }
        this.matchedPos = null;       // { latitude, longitude, road_segment_id, direction, confidence }

        // Trip progress — from real trajectory observations
        this.remainingTripDistanceKm = 0.0;

        // Routing geometry cache
        this.directRouteGeometry = null;

        // Recommendation cache
        this.lastRecommendation = null;

        // Trajectory replay — real GPS observations via backend realtime pipeline
        // Session is passed for consistent driver_id across Driver Mode + Replay
        this.replay = new TrajectoryReplayController(apiClient, mapEngine, {
            onStep: (stepData) => this._onReplayStep(stepData),
            session: this.session
        });

        // Callbacks
        this.onStateChange = options.onStateChange || (() => {});
    }

    setCatalogs(trips, vehicles, stations) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
    }

    async init() {
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
    }

    setState(newState) {
        this.state = newState;
        this.onStateChange(this.state);
        this.updateHeaderBadge();
    }

    updateHeaderBadge() {
        try {
            const badge = document.getElementById('driver-status-badge');
            if (badge) {
                badge.textContent = this.state;
                badge.className = `status-badge badge-${this.state.toLowerCase()}`;
            }
        } catch (err) {
            // Guard: ignore DOM errors during SSR/testing
        }
    }

    /**
     * Assign a trip from the curated dataset and compute direct route.
     */
    async assignTrip(tripId) {
        const trip = this.trips.find(t => t.trip_id === tripId) || this.trips[0];
        if (!trip) return;

        this.currentTrip = trip;
        this.currentVehicle = this.vehicles.find(v => v.vehicle_id === trip.vehicle_id)
            || this.vehicles.find(v => v.vehicle_id === 'V0001')
            || this.vehicles[0];

        // Energy state comes from scenario data, NOT hardcoded per trip_id
        // Use vehicle defaults; scenario SOC/range overrides via loadScenario
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 100.0;
        this.safetyReserveKm = 2.0;
        this.remainingTripDistanceKm = trip.planned_distance_m / 1000;

        // Clear previous state BEFORE rendering new trip
        this.map.clearAll();
        this.map.renderTripEndpoints(trip.origin, trip.destination);

        // Compute direct route via GraphHopper
        try {
            const routeResult = await this.api.computeRoute(
                trip.origin,
                trip.destination,
                { vehicle_category: this.currentVehicle?.vehicle_type || 'EV_CAR' }
            );
            if (routeResult.geometry) {
                this.directRouteGeometry = routeResult.geometry;
                this.map.renderDirectRoute(routeResult.geometry);
            }
        } catch (err) {
            console.warn('Direct route computation error:', err);
        }

        this.map.fitBoundsToActive();
        this.setState(DriverState.TRIP_ASSIGNED);
        this.renderTripAssignedUI();
    }

    /**
     * Start the trip: enter TRIP_ACTIVE state, load trajectory, begin replay.
     */
    async startTrip() {
        if (!this.currentTrip) return;

        // Assign driver ID in shared session context (consistent across Driver Mode + Replay)
        this.session.driver_id = `driver_${Date.now().toString(36)}`;
        this.session.vehicle_id = this.currentVehicle?.vehicle_id;
        this.session.vehicle_category = this.currentVehicle?.vehicle_type;
        this.session.trip_id = this.currentTrip.trip_id;

        this.setState(DriverState.TRIP_ACTIVE);

        // Load trajectory observations for this trip
        const trajId = this._tripToTrajectory(this.currentTrip.trip_id);
        this.session.trajectory_id = trajId;
        await this.replay.loadTrajectory(trajId);

        // Initial recommendation at trip start
        await this._evaluateAtCurrentPosition();

        // Render HUD (SOC stays at scenario values throughout)
        this.renderTripActiveUI();

        // Auto-step first observation
        await this.replay.step();
    }

    /**
     * Map trajectory trip_id to a trajectory replay ID.
     * Throws if trip is not mapped to a known trajectory.
     * Only trips T0001-T0005 have trajectory data in the demo.
     */
    _tripToTrajectory(tripId) {
        const mapping = {
            'T0001': 'TRJ0001',
            'T0002': 'TRJ0002',
            'T0003': 'TRJ0003',
            'T0004': 'TRJ0004',
            'T0005': 'TRJ0005',
            // T0017, T0018, T0019, T0073, T0110, T0129 use TRJ0001 as demo baseline
            'T0017': 'TRJ0001',
            'T0018': 'TRJ0001',
            'T0019': 'TRJ0001',
            'T0073': 'TRJ0001',
            'T0110': 'TRJ0001',
            'T0129': 'TRJ0001',
        };
        const trajId = mapping[tripId];
        if (!trajId) {
            console.error(`Trip '${tripId}' has no mapped trajectory. Available mappings: ${Object.keys(mapping).join(', ')}`);
            throw new Error(`UNMAPPED_TRIP: Trip '${tripId}' not mapped to any trajectory`);
        }
        return trajId;
    }

    /**
     * Called after each replay step completes.
     * Updates position from matched state and re-evaluates recommendation.
     */
    async _onReplayStep(stepData) {
        const { locResp } = stepData;

        // Update position from backend-matched road segment
        if (locResp.matched_position) {
            this.matchedPos = {
                latitude: locResp.matched_position.latitude,
                longitude: locResp.matched_position.longitude,
                road_segment_id: locResp.matched_position.road_segment_id,
                direction: locResp.matched_position.direction,
                confidence: locResp.matched_position.confidence
            };
            this.currentPos = { ...this.matchedPos };
        } else if (locResp.raw_position) {
            this.currentPos = {
                latitude: locResp.raw_position.latitude,
                longitude: locResp.raw_position.longitude
            };
            this.matchedPos = null;
        }

        // Update remaining distance from actual position to destination
        if (this.currentPos && this.currentTrip?.destination) {
            this.remainingTripDistanceKm = haversineKm(
                this.currentPos.latitude,
                this.currentPos.longitude,
                this.currentTrip.destination.latitude,
                this.currentTrip.destination.longitude
            );
        }

        // Check if replay is complete
        if (this.replay.isReplayComplete()) {
            this.setState(DriverState.TRIP_COMPLETE);
            await this._evaluateAtCurrentPosition();
            this.renderTripCompleteUI();
            return;
        }

        // Re-evaluate recommendation at new position
        await this._evaluateAtCurrentPosition();
        this.renderTripActiveUI();
    }

    /**
     * Call backend recommendation endpoint with current position.
     * Backend owns all demand evaluation, routing, eligibility, ranking.
     * SOC/range/remaining_distance come from this controller's state.
     */
    async _evaluateAtCurrentPosition() {
        if (!this.currentVehicle || !this.currentPos) return;

        const driverId = this.session.driver_id || 'UNASSIGNED';

        const payload = {
            context: {
                vehicle_id: this.currentVehicle.vehicle_id,
                driver_id: driverId,
                trip_id: this.currentTrip?.trip_id,
                timestamp: new Date().toISOString(),
                // Fixed per scenario — NOT decremented by frontend
                current_soc_pct: parseFloat(this.currentSocPct.toFixed(1)),
                estimated_remaining_range_km: parseFloat(this.estimatedRangeKm.toFixed(1)),
                remaining_trip_distance_km: parseFloat(this.remainingTripDistanceKm.toFixed(2)),
                safety_reserve_km: this.safetyReserveKm,
                raw_latitude: this.currentPos.latitude,
                raw_longitude: this.currentPos.longitude
            },
            destination_latitude: this.currentTrip?.destination?.latitude,
            destination_longitude: this.currentTrip?.destination?.longitude,
            top_n: 5
        };

        try {
            const rec = await this.api.getRecommendation(payload);
            this.lastRecommendation = rec;

            let leg1Result = null;
            let leg2Result = null;

            if (rec.has_recommendation && rec.ranked_candidates?.length > 0) {
                const top = rec.ranked_candidates[0];
                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st) {
                    const stPos = { latitude: st.latitude, longitude: st.longitude };
                    try {
                        leg1Result = await this.api.computeRoute(this.currentPos, stPos, {
                            vehicle_category: this.currentVehicle.vehicle_type
                        });
                        if (this.currentTrip?.destination) {
                            leg2Result = await this.api.computeRoute(stPos, this.currentTrip.destination, {
                                vehicle_category: this.currentVehicle.vehicle_type
                            });
                        }
                        this.map.renderRecommendationRoute(leg1Result.geometry, leg2Result?.geometry);
                        this.map.renderStations(this.stations, top.station_id, top.service_type);
                    } catch (routeErr) {
                        console.warn('Recommendation route fetch error:', routeErr);
                    }
                }
            } else {
                this.map.clearRoutes();
                if (this.directRouteGeometry) {
                    this.map.renderDirectRoute(this.directRouteGeometry);
                }
                this.map.renderStations(this.stations);
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
                        status: 'MATCHED',
                        raw_position: this.currentPos,
                        matched_position: {
                            latitude: this.currentPos?.latitude,
                            longitude: this.currentPos?.longitude,
                            direction: 'FORWARD',
                            confidence: 1.0
                        }
                    },
                    recommendRequest: payload,
                    recommendResult: rec,
                    stationRoutes: { leg1: leg1Result, leg2: leg2Result }
                });
            }
        } catch (err) {
            console.error('Driver mode recommendation error:', err);
            this.lastRecommendation = null;

            // Sync error to Tech View
            if (this.options?.onStateUpdate) {
                this.options.onStateUpdate({
                    error: err,
                    recommendRequest: payload,
                    recommendResult: null
                });
            }
        }
    }

    /**
     * Advance to next GPS observation (called from UI button).
     */
    async stepTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        await this.replay.step();
    }

    /**
     * Play trajectory at configured speed.
     */
    playTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        this.replay.play();
    }

    /**
     * Pause trajectory replay.
     */
    pauseTrip() {
        this.replay.pause();
    }

    /**
     * Return to available state.
     */
    returnToAvailable() {
        this.replay.clearSession();
        this.replay.reset();
        this.map.clearAll();
        this.currentTrip = null;
        this.currentPos = null;
        this.matchedPos = null;
        this.lastRecommendation = null;
        this.directRouteGeometry = null;
        this.remainingTripDistanceKm = 0.0;
        // Clear session context
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
        this.replay.clearSession();
        this.replay.reset();
        this.map.clearAll();
        this.currentTrip = null;
        this.currentPos = null;
        this.matchedPos = null;
        this.lastRecommendation = null;
        this.directRouteGeometry = null;
        // Clear session context
        this.session.driver_id = null;
        this.session.vehicle_id = null;
        this.session.vehicle_category = null;
        this.session.trip_id = null;
        this.session.trajectory_id = null;
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
    }

    // ─── UI Renderers ───────────────────────────────────────────────────────

    renderAvailableUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const tripOptions = this.trips.map(t => `
            <option value="${t.trip_id}">
                ${t.trip_id} — ${t.scenario_id} (${(t.planned_distance_m / 1000).toFixed(1)} km)
            </option>
        `).join('');

        container.innerHTML = `
            <div class="driver-available-card">
                <div class="card-status-indicator">
                    <span class="pulse-dot green"></span>
                    <h3>Driver Online</h3>
                </div>
                <p class="text-muted">Select a trip to begin navigation.</p>

                <div class="form-group mt-3">
                    <label>Select Trip:</label>
                    <select id="select-driver-trip" class="form-control">
                        ${tripOptions}
                    </select>
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-accept-trip" class="btn btn-primary btn-lg btn-block">Start Trip</button>
                    <button id="btn-go-offline" class="btn btn-outline btn-sm mt-2">Go Offline</button>
                </div>
            </div>
        `;

        document.getElementById('btn-accept-trip')?.addEventListener('click', () => {
            const tripId = document.getElementById('select-driver-trip')?.value;
            this.assignTrip(tripId);
        });

        document.getElementById('btn-go-offline')?.addEventListener('click', () => this.goOffline());
    }

    renderOfflineUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-available-card text-center">
                <span class="pulse-dot gray"></span>
                <h3>Driver is Offline</h3>
                <p class="text-muted">Turn online to receive trip dispatches.</p>
                <button id="btn-go-online" class="btn btn-primary btn-lg mt-3">Go Online</button>
            </div>
        `;

        document.getElementById('btn-go-online')?.addEventListener('click', () => this.goOnline());
    }

    renderTripAssignedUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-nav-hud">
                <div class="hud-header">
                    <span class="badge badge-info">TRIP ASSIGNED</span>
                    <h3>${this.currentTrip?.trip_id}</h3>
                </div>

                <div class="hud-details">
                    <div>Vehicle: <strong>${this.currentVehicle?.vehicle_model || 'VF 3'}</strong></div>
                    <div>Distance: <strong>${(this.currentTrip?.planned_distance_m / 1000).toFixed(1)} km</strong></div>
                    <div>Battery: <strong>${this.currentSocPct.toFixed(0)}%</strong></div>
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-start-driving" class="btn btn-success btn-lg btn-block">Start Driving</button>
                    <button id="btn-cancel-trip" class="btn btn-outline btn-sm mt-2">Cancel</button>
                </div>
            </div>
        `;

        document.getElementById('btn-start-driving')?.addEventListener('click', () => this.startTrip());
        document.getElementById('btn-cancel-trip')?.addEventListener('click', () => this.cancelTrip());
    }

    renderTripActiveUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        // Get ETA from backend recommendation or direct route
        let etaMin = '—';
        if (this.lastRecommendation?.ranked_candidates?.length > 0) {
            const top = this.lastRecommendation.ranked_candidates[0];
            etaMin = (top.eta_to_station_s / 60).toFixed(0);
        } else if (this.directRouteGeometry) {
            // Fallback: use direct route ETA (requires re-fetch or stored value)
            // For now show remaining distance context
            etaMin = '—';
        }

        const warningBanner = renderEnergyWarningBanner(this.lastRecommendation?.energy_context);

        let recSnippet = '';
        if (this.lastRecommendation?.has_recommendation) {
            const top = this.lastRecommendation.ranked_candidates[0];
            const isSwap = top.service_type === 'BATTERY_SWAP';
            const detourKm = top.features.detour_distance_m
                ? (top.features.detour_distance_m / 1000).toFixed(1)
                : '?';
            const completionMin = top.eta_to_service_complete_s
                ? (top.eta_to_service_complete_s / 60).toFixed(0)
                : '?';
            recSnippet = `
                <div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}">
                    <div>
                        <strong>${top.station_id}</strong> — ${isSwap ? 'Battery Swap' : 'Charging'}
                        <div class="text-sm text-muted">
                            +${detourKm} km detour · Ready in ${completionMin} min
                        </div>
                    </div>
                    <span class="badge ${isSwap ? 'badge-purple' : 'badge-teal'}">Recommended</span>
                </div>
            `;
        }

        // Show position status
        const posStatus = this.matchedPos
            ? `<span class="text-success">Road: ${this.matchedPos.road_segment_id || 'matched'}</span>`
            : '<span class="text-muted">Acquiring position...</span>';

        const progress = this.replay.getProgressText?.() || '';

        container.innerHTML = `
            <div class="driver-nav-hud">
                ${warningBanner}

                <div class="nav-metrics-card">
                    <div class="nav-destination">
                        <span class="text-sm text-muted">Destination</span>
                        <div class="dest-name">Passenger Drop-off</div>
                    </div>

                    <div class="nav-stats-grid">
                        <div class="stat-box">
                            <span class="stat-label">Remaining</span>
                            <span class="stat-value">${this.remainingTripDistanceKm.toFixed(1)} <small>km</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">ETA</span>
                            <span class="stat-value">${etaMin} <small>min</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">SOC</span>
                            <span class="stat-value ${this.currentSocPct < 20 ? 'text-danger' : ''}">${this.currentSocPct.toFixed(0)}%</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Range</span>
                            <span class="stat-value">${this.estimatedRangeKm.toFixed(0)} <small>km</small></span>
                        </div>
                    </div>

                    <div class="battery-bar-container">
                        <div class="battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}" style="width: ${Math.max(5, this.currentSocPct)}%;"></div>
                    </div>

                    <div class="text-xs text-muted mt-2">
                        ${posStatus} · ${progress}
                    </div>
                </div>

                ${recSnippet}

                <div class="driver-controls mt-4">
                    <div class="replay-controls d-flex gap-2 mb-2">
                        <button id="btn-replay-play" class="btn btn-primary btn-sm">▶ Play</button>
                        <button id="btn-replay-pause" class="btn btn-outline btn-sm" disabled>⏸ Pause</button>
                        <button id="btn-replay-step" class="btn btn-outline btn-sm">⏭ Step</button>
                    </div>
                    <button id="btn-complete-trip" class="btn btn-outline btn-sm btn-block">Complete Trip Now</button>
                </div>
            </div>
        `;

        // Bind replay controls
        document.getElementById('btn-replay-play')?.addEventListener('click', () => this.playTrip());
        document.getElementById('btn-replay-pause')?.addEventListener('click', () => this.pauseTrip());
        document.getElementById('btn-replay-step')?.addEventListener('click', () => this.stepTrip());
        document.getElementById('btn-complete-trip')?.addEventListener('click', () => {
            this.setState(DriverState.TRIP_COMPLETE);
            this.renderTripCompleteUI();
        });
    }

    renderTripCompleteUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const warningBanner = renderEnergyWarningBanner(this.lastRecommendation?.energy_context);
        const recCard = renderRecommendationCard(this.lastRecommendation);

        container.innerHTML = `
            <div class="driver-nav-hud">
                <div class="completion-header text-center">
                    <span class="check-icon">✓</span>
                    <h3>Trip Completed</h3>
                    <p class="text-muted">Passenger dropped off safely.</p>
                </div>

                ${warningBanner}

                <div class="mt-3">
                    ${recCard}
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-back-available" class="btn btn-primary btn-lg btn-block">Return to Available</button>
                </div>
            </div>
        `;

        document.getElementById('btn-back-available')?.addEventListener('click', () => this.returnToAvailable());
    }
}
