/**
 * Driver Mode Controller for VinFast EV Recommendation Demo.
 * 
 * Minimal demo state model:
 * OFFLINE -> AVAILABLE -> TRIP_ASSIGNED -> TO_PICKUP -> ON_TRIP -> TRIP_COMPLETE
 * 
 * Strict rule: No multiple active passenger trips.
 * Driver mode prioritizes driving safety and reduces visual clutter.
 */

import { renderEnergyWarningBanner, renderRecommendationCard } from './components.js';

export const DriverState = {
    OFFLINE: 'OFFLINE',
    AVAILABLE: 'AVAILABLE',
    TRIP_ASSIGNED: 'TRIP_ASSIGNED',
    TO_PICKUP: 'TO_PICKUP',
    ON_TRIP: 'ON_TRIP',
    TRIP_COMPLETE: 'TRIP_COMPLETE'
};

export class DriverModeController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.trips = [];
        this.vehicles = [];
        this.stations = [];

        // Active State
        this.state = DriverState.AVAILABLE;
        this.currentTrip = null;
        this.currentVehicle = null;
        this.currentDriverId = 'D0001';
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 100.0;
        this.remainingTripDistanceKm = 0.0;
        this.safetyReserveKm = 2.0;
        this.currentPos = { latitude: 21.0285, longitude: 105.8542 };
        this.matchedPos = null;

        // Trip step progress (0.0 to 1.0)
        this.progress = 0.0;

        // Cached recommendation result
        this.lastRecommendation = null;
        this.directRouteGeometry = null;
        this.recRouteGeometry = null;

        // Callbacks
        this.onStateChange = options.onStateChange || (() => {});
    }

    setCatalogs(trips, vehicles, stations) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];

        if (this.vehicles.length > 0) {
            this.currentVehicle = this.vehicles.find(v => v.vehicle_id === 'V0001') || this.vehicles[0];
        }
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
        const badge = document.getElementById('driver-status-badge');
        if (badge) {
            badge.textContent = this.state;
            badge.className = `status-badge badge-${this.state.toLowerCase()}`;
        }
    }

    /**
     * Start a demo trip from curated dataset trips.
     */
    async assignTrip(tripId) {
        const trip = this.trips.find(t => t.trip_id === tripId) || this.trips[0];
        if (!trip) return;

        this.currentTrip = trip;
        this.currentDriverId = trip.driver_id || 'D0001';
        this.currentVehicle = this.vehicles.find(v => v.vehicle_id === trip.vehicle_id) || this.currentVehicle;

        // Initialize coordinates
        this.currentPos = { ...trip.origin };
        this.remainingTripDistanceKm = trip.planned_distance_m / 1000;
        this.progress = 0.0;

        // Set realistic starting SOC depending on scenario
        if (trip.trip_id === 'T0003') {
            this.currentSocPct = 20.0;
            this.estimatedRangeKm = 12.0;
        } else if (trip.trip_id === 'T0004') {
            this.currentSocPct = 14.0;
            this.estimatedRangeKm = 18.0;
        } else if (trip.trip_id === 'T0110') {
            this.currentSocPct = 12.0;
            this.estimatedRangeKm = 14.0;
        } else {
            this.currentSocPct = 80.0;
            this.estimatedRangeKm = 95.0;
        }

        this.setState(DriverState.TRIP_ASSIGNED);
        this.renderAssignedUI();

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

        this.map.renderTripEndpoints(trip.origin, trip.destination);
        this.map.renderDriver(this.currentPos, this.currentPos, 0);
        this.map.fitBoundsToActive();
    }

    async startTrip() {
        this.setState(DriverState.ON_TRIP);
        await this.evaluateDriverEnergyAndRecommendation();
        this.renderOnTripUI();
    }

    /**
     * Advance along the active trip (simulates vehicle moving toward destination).
     */
    async stepProgress() {
        if (this.state !== DriverState.ON_TRIP || !this.currentTrip) return;

        this.progress += 0.25; // 4 steps to completion
        if (this.progress >= 1.0) {
            this.progress = 1.0;
            this.remainingTripDistanceKm = 0.0;
            this.currentPos = { ...this.currentTrip.destination };
            this.setState(DriverState.TRIP_COMPLETE);
            await this.evaluateDriverEnergyAndRecommendation();
            this.renderTripCompleteUI();
            return;
        }

        // Interpolate position
        const orig = this.currentTrip.origin;
        const dest = this.currentTrip.destination;
        this.currentPos = {
            latitude: orig.latitude + (dest.latitude - orig.latitude) * this.progress,
            longitude: orig.longitude + (dest.longitude - orig.longitude) * this.progress
        };

        const totalDist = this.currentTrip.planned_distance_m / 1000;
        this.remainingTripDistanceKm = Math.max(0.1, totalDist * (1 - this.progress));

        // Consume battery proportionally
        const consumedRange = (totalDist * 0.25);
        this.estimatedRangeKm = Math.max(1.0, this.estimatedRangeKm - consumedRange);
        this.currentSocPct = Math.max(3.0, this.currentSocPct - 4.5);

        // Update map
        this.map.renderDriver(this.currentPos, this.currentPos);

        // Call backend to re-evaluate demand and recommendation
        await this.evaluateDriverEnergyAndRecommendation();
        this.renderOnTripUI();
    }

    /**
     * Call backend recommendation orchestration endpoint.
     */
    async evaluateDriverEnergyAndRecommendation() {
        if (!this.currentVehicle || !this.currentPos) return;

        const payload = {
            context: {
                vehicle_id: this.currentVehicle.vehicle_id,
                driver_id: this.currentDriverId,
                trip_id: this.currentTrip?.trip_id,
                timestamp: new Date().toISOString(),
                current_soc_pct: parseFloat(this.currentSocPct.toFixed(1)),
                estimated_remaining_range_km: parseFloat(this.estimatedRangeKm.toFixed(1)),
                remaining_trip_distance_km: parseFloat(this.remainingTripDistanceKm.toFixed(1)),
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

            // If recommendation exists, draw route to station
            if (rec.has_recommendation && rec.ranked_candidates?.length > 0) {
                const top = rec.ranked_candidates[0];
                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st) {
                    const stPos = { latitude: st.latitude, longitude: st.longitude };
                    try {
                        const leg1 = await this.api.computeRoute(this.currentPos, stPos, {
                            vehicle_category: this.currentVehicle.vehicle_type
                        });
                        let leg2 = null;
                        if (this.currentTrip?.destination) {
                            leg2 = await this.api.computeRoute(stPos, this.currentTrip.destination, {
                                vehicle_category: this.currentVehicle.vehicle_type
                            });
                        }
                        this.map.renderRecommendationRoute(leg1.geometry, leg2?.geometry);
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
        } catch (err) {
            console.error('Driver mode recommendation error:', err);
            this.lastRecommendation = null;
        }
    }

    renderAvailableUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const tripOptions = this.trips.map(t => `
            <option value="${t.trip_id}">
                ${t.trip_id} - ${t.scenario_id} (${(t.planned_distance_m / 1000).toFixed(1)} km)
            </option>
        `).join('');

        container.innerHTML = `
            <div class="driver-available-card">
                <div class="card-status-indicator">
                    <span class="pulse-dot green"></span>
                    <h3>Driver Online — Available for Trips</h3>
                </div>
                <p class="text-muted">Vehicle is idle. Select an assigned trip to begin route navigation.</p>
                
                <div class="form-group mt-3">
                    <label>Select Assigned Trip (Dataset V1):</label>
                    <select id="select-driver-trip" class="form-control">
                        ${tripOptions}
                    </select>
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-accept-trip" class="btn btn-primary btn-lg btn-block">Accept & Start Route</button>
                    <button id="btn-go-offline" class="btn btn-outline btn-sm mt-2">Go Offline</button>
                </div>
            </div>
        `;

        document.getElementById('btn-accept-trip')?.addEventListener('click', () => {
            const tripId = document.getElementById('select-driver-trip')?.value;
            this.assignTrip(tripId);
        });

        document.getElementById('btn-go-offline')?.addEventListener('click', () => {
            this.setState(DriverState.OFFLINE);
            this.renderOfflineUI();
        });
    }

    renderOfflineUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-available-card text-center">
                <span class="pulse-dot gray"></span>
                <h3>Driver is Offline</h3>
                <p class="text-muted">Turn online to receive passenger trip dispatches.</p>
                <button id="btn-go-online" class="btn btn-primary btn-lg mt-3">Go Online</button>
            </div>
        `;

        document.getElementById('btn-go-online')?.addEventListener('click', () => {
            this.setState(DriverState.AVAILABLE);
            this.renderAvailableUI();
        });
    }

    renderAssignedUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        container.innerHTML = `
            <div class="driver-nav-hud">
                <div class="hud-header">
                    <span class="badge badge-info">TRIP ASSIGNED</span>
                    <h3>Trip ${this.currentTrip?.trip_id}</h3>
                </div>

                <div class="hud-details">
                    <div>Vehicle: <strong>${this.currentVehicle?.vehicle_model || 'VF_3'}</strong></div>
                    <div>Distance: <strong>${(this.currentTrip?.planned_distance_m / 1000).toFixed(1)} km</strong></div>
                    <div>Battery: <strong>${this.currentSocPct.toFixed(0)}%</strong> (~${this.estimatedRangeKm.toFixed(0)} km)</div>
                </div>

                <div class="hud-actions mt-4">
                    <button id="btn-start-driving" class="btn btn-success btn-lg btn-block">Start Passenger Trip</button>
                    <button id="btn-cancel-trip" class="btn btn-outline btn-sm mt-2">Cancel Assignment</button>
                </div>
            </div>
        `;

        document.getElementById('btn-start-driving')?.addEventListener('click', () => this.startTrip());
        document.getElementById('btn-cancel-trip')?.addEventListener('click', () => {
            this.map.clearAll();
            this.setState(DriverState.AVAILABLE);
            this.renderAvailableUI();
        });
    }

    renderOnTripUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const warningBanner = renderEnergyWarningBanner(this.lastRecommendation?.energy_context);
        const etaMin = (this.remainingTripDistanceKm * 2.1).toFixed(0); // ~30 km/h approx

        // In ON_TRIP mode: uncluttered view. Candidate table collapsed/hidden.
        let recSnippet = '';
        if (this.lastRecommendation?.has_recommendation) {
            const top = this.lastRecommendation.ranked_candidates[0];
            const isSwap = top.service_type === 'BATTERY_SWAP';
            recSnippet = `
                <div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}">
                    <div class="d-flex justify-between items-center">
                        <div>
                            <strong>Recommended Stop: ${top.station_id}</strong> (${isSwap ? 'BATTERY SWAP' : 'CHARGING'})
                            <div class="text-sm text-muted">+${(top.features.detour_distance_m / 1000).toFixed(1)} km detour · ${(top.eta_to_service_complete_s / 60).toFixed(1)}m completion</div>
                        </div>
                        <span class="badge ${isSwap ? 'badge-purple' : 'badge-teal'}">Active Rec</span>
                    </div>
                </div>
            `;
        }

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
                            <span class="stat-label">Est. ETA</span>
                            <span class="stat-value">${etaMin} <small>min</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">SOC</span>
                            <span class="stat-value ${this.currentSocPct < 20 ? 'text-danger' : 'text-success'}">${this.currentSocPct.toFixed(0)}%</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Range</span>
                            <span class="stat-value">${this.estimatedRangeKm.toFixed(0)} <small>km</small></span>
                        </div>
                    </div>

                    <div class="battery-bar-container">
                        <div class="battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}" style="width: ${Math.max(5, this.currentSocPct)}%;"></div>
                    </div>
                </div>

                ${recSnippet}

                <div class="driver-controls mt-4">
                    <button id="btn-step-trip" class="btn btn-primary btn-block">Simulate Next GPS Step (+25%)</button>
                    <button id="btn-force-complete" class="btn btn-outline btn-sm mt-2">Complete Trip Now</button>
                </div>
            </div>
        `;

        document.getElementById('btn-step-trip')?.addEventListener('click', () => this.stepProgress());
        document.getElementById('btn-force-complete')?.addEventListener('click', () => {
            this.progress = 1.0;
            this.remainingTripDistanceKm = 0.0;
            this.currentPos = { ...this.currentTrip.destination };
            this.setState(DriverState.TRIP_COMPLETE);
            this.evaluateDriverEnergyAndRecommendation().then(() => this.renderTripCompleteUI());
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
                    <h3>Trip Completed!</h3>
                    <p class="text-muted">Passenger has been safely dropped off at destination.</p>
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

        document.getElementById('btn-back-available')?.addEventListener('click', () => {
            this.map.clearAll();
            this.setState(DriverState.AVAILABLE);
            this.renderAvailableUI();
        });
    }
}
