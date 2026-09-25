/**
 * Simulation Mode Controller for VinFast EV Recommendation Demo.
 * 
 * Strict rule: Simulation controls supply inputs.
 * Backend owns all demand evaluation, candidate search, routing, and ranking.
 */

import { renderPipelineLatency, renderCandidateTable, renderRecommendationCard, renderEnergyWarningBanner, renderConflictAlert } from './components.js';

export class SimModeController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.options = options;
        this.scenarios = [];
        this.vehicles = [];
        this.stations = [];

        this.pickingMode = null; // 'origin' | 'destination' | null
        this.activeScenario = null;

        // Current inputs
        this.origin = { latitude: 21.0285, longitude: 105.8542 };
        this.destination = { latitude: 21.0150, longitude: 105.7800 };
        this.vehicleId = 'V0001';
        this.socPct = 15.0;
        this.estimatedRangeKm = 25.0;
        this.remainingTripDistanceKm = 8.0;
        this.safetyReserveKm = 2.0;
        this.timestamp = '2026-09-01T07:00:00Z';
        this.serviceIntent = 'AUTO';

        // Simulation output cache
        this.lastRecommendation = null;
        this.lastCandidateResult = null;
        this.generation = 1;
    }

    setCatalogs(scenarios, vehicles, stations) {
        this.scenarios = scenarios || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
    }

    init() {
        this.bindEvents();
        this.renderScenarioQuickSelect();
        this.renderVehicleSelect();

        // Bind map click handler for coordinate picking
        this.map.onMapClick((coords) => {
            if (this.pickingMode === 'origin') {
                this.setOrigin(coords);
                this.setPickingMode(null);
            } else if (this.pickingMode === 'destination') {
                this.setDestination(coords);
                this.setPickingMode(null);
            }
        });
    }

    setPickingMode(mode) {
        this.pickingMode = mode;
        const infoBar = document.getElementById('map-picking-indicator');
        const mapElem = document.getElementById('map');

        if (mode) {
            infoBar.style.display = 'block';
            infoBar.textContent = `Click on the map to choose ${mode.toUpperCase()} position...`;
            mapElem.style.cursor = 'crosshair';
        } else {
            infoBar.style.display = 'none';
            mapElem.style.cursor = '';
        }
    }

    setOrigin(coords) {
        this.origin = coords;
        document.getElementById('sim-origin-lat').value = coords.latitude.toFixed(6);
        document.getElementById('sim-origin-lng').value = coords.longitude.toFixed(6);
        this.map.renderTripEndpoints(this.origin, this.destination);
    }

    setDestination(coords) {
        this.destination = coords;
        document.getElementById('sim-dest-lat').value = coords.latitude.toFixed(6);
        document.getElementById('sim-dest-lng').value = coords.longitude.toFixed(6);
        this.map.renderTripEndpoints(this.origin, this.destination);
    }

    bindEvents() {
        // Run simulation button
        document.getElementById('btn-run-sim')?.addEventListener('click', () => this.runSimulation());

        // Coordinate picker buttons
        document.getElementById('btn-pick-origin')?.addEventListener('click', () => this.setPickingMode('origin'));
        document.getElementById('btn-pick-dest')?.addEventListener('click', () => this.setPickingMode('destination'));

        // Input change listeners
        document.getElementById('sim-origin-lat')?.addEventListener('change', (e) => {
            this.origin.latitude = parseFloat(e.target.value);
            this.map.renderTripEndpoints(this.origin, this.destination);
        });
        document.getElementById('sim-origin-lng')?.addEventListener('change', (e) => {
            this.origin.longitude = parseFloat(e.target.value);
            this.map.renderTripEndpoints(this.origin, this.destination);
        });
        document.getElementById('sim-dest-lat')?.addEventListener('change', (e) => {
            this.destination.latitude = parseFloat(e.target.value);
            this.map.renderTripEndpoints(this.origin, this.destination);
        });
        document.getElementById('sim-dest-lng')?.addEventListener('change', (e) => {
            this.destination.longitude = parseFloat(e.target.value);
            this.map.renderTripEndpoints(this.origin, this.destination);
        });

        // SOC slider sync
        const socSlider = document.getElementById('sim-soc-slider');
        const socDisplay = document.getElementById('sim-soc-val');
        socSlider?.addEventListener('input', (e) => {
            this.socPct = parseFloat(e.target.value);
            if (socDisplay) socDisplay.textContent = `${this.socPct.toFixed(0)}%`;
            this.recalculateEstimatedRange();
        });

        // Vehicle selector
        document.getElementById('sim-vehicle-select')?.addEventListener('change', (e) => {
            this.vehicleId = e.target.value;
            this.recalculateEstimatedRange();
        });

        // Service selector
        document.getElementById('sim-service-intent')?.addEventListener('change', (e) => {
            this.serviceIntent = e.target.value;
        });

        // Timestamp input
        document.getElementById('sim-timestamp')?.addEventListener('change', (e) => {
            this.timestamp = e.target.value;
        });
    }

    recalculateEstimatedRange() {
        const vehicle = this.vehicles.find(v => v.vehicle_id === this.vehicleId);
        if (vehicle && vehicle.usable_capacity_kwh && vehicle.consumption_wh_per_km) {
            const wh = vehicle.usable_capacity_kwh * 1000 * (this.socPct / 100);
            this.estimatedRangeKm = Math.round((wh / vehicle.consumption_wh_per_km) * 10) / 10;
        }
        const rangeDisplay = document.getElementById('sim-est-range-val');
        if (rangeDisplay) rangeDisplay.textContent = `${this.estimatedRangeKm.toFixed(1)} km`;
    }

    renderScenarioQuickSelect() {
        const container = document.getElementById('sim-scenarios-container');
        if (!container) return;

        container.innerHTML = this.scenarios.map(sc => `
            <button class="scenario-pill-btn" data-scenario-id="${sc.id}">
                <span class="pill-tag tag-${sc.tag.toLowerCase()}">${sc.tag}</span>
                <span class="pill-title">${sc.title}</span>
            </button>
        `).join('');

        container.querySelectorAll('.scenario-pill-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const scId = btn.getAttribute('data-scenario-id');
                this.loadScenario(scId);
            });
        });
    }

    renderVehicleSelect() {
        const select = document.getElementById('sim-vehicle-select');
        if (!select) return;

        // Group unique vehicle models
        select.innerHTML = this.vehicles.slice(0, 15).map(v => `
            <option value="${v.vehicle_id}">
                ${v.vehicle_model} (${v.vehicle_type === 'EV_CAR' ? 'Car' : 'Motorbike'}, Usable: ${v.usable_capacity_kwh || '-'} kWh)
            </option>
        `).join('');
    }

    loadScenario(scenarioId) {
        this.generation++;
        const sc = this.scenarios.find(s => s.id === scenarioId);
        if (!sc) return;

        this.activeScenario = sc;

        // Populate fields
        if (sc.origin) this.setOrigin(sc.origin);
        if (sc.destination) this.setDestination(sc.destination);
        if (sc.vehicle_id) {
            this.vehicleId = sc.vehicle_id;
            const vehSelect = document.getElementById('sim-vehicle-select');
            if (vehSelect) vehSelect.value = sc.vehicle_id;
        }
        if (sc.soc_pct != null) {
            this.socPct = sc.soc_pct;
            const socSlider = document.getElementById('sim-soc-slider');
            const socDisplay = document.getElementById('sim-soc-val');
            if (socSlider) socSlider.value = sc.soc_pct;
            if (socDisplay) socDisplay.textContent = `${sc.soc_pct.toFixed(0)}%`;
        }
        if (sc.estimated_range_km != null) this.estimatedRangeKm = sc.estimated_range_km;
        if (sc.remaining_trip_distance_km != null) this.remainingTripDistanceKm = sc.remaining_trip_distance_km;
        if (sc.safety_reserve_km != null) this.safetyReserveKm = sc.safety_reserve_km;
        if (sc.timestamp) {
            this.timestamp = sc.timestamp;
            const tsInput = document.getElementById('sim-timestamp');
            if (tsInput) tsInput.value = sc.timestamp;
        }
        if (sc.requested_service) {
            this.serviceIntent = sc.requested_service;
            const svcSelect = document.getElementById('sim-service-intent');
            if (svcSelect) svcSelect.value = sc.requested_service;
        }

        this.recalculateEstimatedRange();

        // Highlight scenario description card
        const descElem = document.getElementById('sim-scenario-desc');
        if (descElem) {
            descElem.innerHTML = `
                <div class="active-scenario-banner">
                    <strong>${sc.title}</strong>
                    <p>${sc.description}</p>
                    ${sc.timestamp_t1 && sc.timestamp_t2 ? `
                        <div class="scenario-timeline mt-2">
                            <span>Step 1: <button id="btn-sc-step1" class="btn btn-xs btn-outline">Time T1 (${sc.timestamp_t1.substring(11, 16)})</button></span>
                            <span>Step 2: <button id="btn-sc-step2" class="btn btn-xs btn-outline">Time T2 (${sc.timestamp_t2.substring(11, 16)})</button></span>
                        </div>
                    ` : ''}
                </div>
            `;

            document.getElementById('btn-sc-step1')?.addEventListener('click', () => {
                this.timestamp = sc.timestamp_t1;
                document.getElementById('sim-timestamp').value = sc.timestamp_t1;
                this.runSimulation();
            });

            document.getElementById('btn-sc-step2')?.addEventListener('click', () => {
                this.timestamp = sc.timestamp_t2;
                document.getElementById('sim-timestamp').value = sc.timestamp_t2;
                this.runSimulation();
            });
        }

        // Run simulation immediately for smooth demo
        this.runSimulation();
    }

    async runSimulation() {
        this.generation++;
        const currentGen = this.generation;

        const btn = document.getElementById('btn-run-sim');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Finding Best Station...';
        }

        const vehicle = this.vehicles.find(v => v.vehicle_id === this.vehicleId) || this.vehicles[0];

        // Format requested service
        let reqService = null;
        if (this.serviceIntent && this.serviceIntent !== 'AUTO') {
            reqService = this.serviceIntent;
        }

        const basePayload = {
            vehicle_id: this.vehicleId,
            timestamp: this.timestamp || new Date().toISOString(),
            current_soc_pct: parseFloat(this.socPct.toFixed(1)),
            estimated_remaining_range_km: parseFloat(this.estimatedRangeKm.toFixed(1)),
            remaining_trip_distance_km: parseFloat(this.remainingTripDistanceKm.toFixed(1)),
            safety_reserve_km: this.safetyReserveKm,
            raw_latitude: this.origin.latitude,
            raw_longitude: this.origin.longitude,
            destination_latitude: this.destination.latitude,
            destination_longitude: this.destination.longitude
        };

        const recommendPayload = {
            context: {
                vehicle_id: basePayload.vehicle_id,
                timestamp: basePayload.timestamp,
                current_soc_pct: basePayload.current_soc_pct,
                estimated_remaining_range_km: basePayload.estimated_remaining_range_km,
                remaining_trip_distance_km: basePayload.remaining_trip_distance_km,
                safety_reserve_km: basePayload.safety_reserve_km,
                raw_latitude: basePayload.raw_latitude,
                raw_longitude: basePayload.raw_longitude
            },
            requested_service: reqService,
            destination_latitude: basePayload.destination_latitude,
            destination_longitude: basePayload.destination_longitude,
            top_n: 10
        };

        const candidatePayload = {
            ...basePayload,
            eligible_only: false
        };

        try {
            // Run Candidate Search and Ranking in parallel
            const [candResult, recResult, routeResult] = await Promise.all([
                this.api.evaluateAndSearchCandidates(candidatePayload).catch(err => ({ error: err })),
                this.api.getRecommendation(recommendPayload).catch(err => ({ error: err })),
                this.api.computeRoute(this.origin, this.destination, {
                    vehicle_category: vehicle.vehicle_type
                }).catch(() => null)
            ]);

            if (this.generation !== currentGen) return;

            this.lastCandidateResult = candResult;
            this.lastRecommendation = recResult;

            // Handle 409 Conflict if returned
            if (recResult?.error && recResult.error.isConflict) {
                this.renderConflictState(recResult.error);
                return;
            }

            // Render Output Panels
            this.renderOutputPanels(recResult, candResult);

            // Update Map with real routes and candidates
            this.map.clearAll();
            this.map.renderTripEndpoints(this.origin, this.destination);

            if (routeResult?.geometry) {
                this.map.renderDirectRoute(routeResult.geometry);
            }

            const candidatesList = candResult.candidates || [];
            const recStationId = recResult?.has_recommendation ? recResult.recommended_station_id : null;
            const recService = recResult?.has_recommendation ? recResult.recommended_service_type : null;

            // Render station dots on map
            this.map.renderStations(this.stations.map(st => {
                const found = candidatesList.find(c => c.station_id === st.station_id);
                return {
                    ...st,
                    eligible: found ? found.eligible : false,
                    reason: found ? found.reason : null
                };
            }), recStationId, recService);

            let leg1Result = null;
            let leg2Result = null;

            // Render diversion route to recommended station
            if (recResult?.has_recommendation && recResult.ranked_candidates?.length > 0) {
                const top = recResult.ranked_candidates[0];
                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st) {
                    const stPos = { latitude: st.latitude, longitude: st.longitude };
                    try {
                        leg1Result = await this.api.computeRoute(this.origin, stPos, {
                            vehicle_category: vehicle.vehicle_type
                        });
                        leg2Result = await this.api.computeRoute(stPos, this.destination, {
                            vehicle_category: vehicle.vehicle_type
                        });
                        if (this.generation !== currentGen) return;
                        this.map.renderRecommendationRoute(leg1Result.geometry, leg2Result?.geometry);
                    } catch (routeErr) {
                        console.warn('Diversion route error:', routeErr);
                    }
                }
            }

            if (this.options?.onStateUpdate) {
                this.options.onStateUpdate({
                    scenario: this.activeScenario,
                    vehicle: vehicle,
                    origin: this.origin,
                    destination: this.destination,
                    driverLocation: {
                        driver_id: 'SIM_DRIVER',
                        status: 'INPUT_COORDINATES',
                        trigger_reason: 'SIMULATION_ORIGIN',
                        raw_position: this.origin,
                        matched_position: null,
                        direction: 'UNKNOWN',
                        confidence: null,
                        location_source: recResult?.location_source || 'EXPLICIT_COORDINATES'
                    },
                    recommendRequest: recommendPayload,
                    recommendResult: recResult,
                    candidateResult: candResult,
                    routeResult: routeResult,
                    stationRoutes: { leg1: leg1Result, leg2: leg2Result }
                });
            }

            this.map.fitBoundsToActive();

        } catch (err) {
            if (this.generation !== currentGen) return;
            console.error('Simulation execution failed:', err);
            this.map.clearRoutes();
            this.lastRecommendation = null;
            this.renderErrorState(err);
        } finally {
            if (btn && this.generation === currentGen) {
                btn.disabled = false;
                btn.textContent = 'FIND BEST STATION';
            }
        }
    }

    renderOutputPanels(recResult, candResult) {
        // Pipeline latency
        const pipelineContainer = document.getElementById('sim-pipeline-container');
        if (pipelineContainer) {
            pipelineContainer.innerHTML = renderPipelineLatency(recResult?.timings_ms);
        }

        // Energy warning banner
        const bannerContainer = document.getElementById('sim-warning-container');
        if (bannerContainer) {
            bannerContainer.innerHTML = renderEnergyWarningBanner(recResult?.energy_context);
        }

        // Recommendation card
        const recContainer = document.getElementById('sim-recommendation-container');
        if (recContainer) {
            recContainer.innerHTML = renderRecommendationCard(recResult);
        }

        // Demand detail panel
        const demandContainer = document.getElementById('sim-demand-detail-container');
        if (demandContainer && recResult?.energy_context) {
            const ctx = recResult.energy_context;
            demandContainer.innerHTML = `
                <div class="demand-card">
                    <h4>Demand Detection</h4>
                    <div class="demand-grid">
                        <div>Need Service: <strong>${ctx.need_service ? 'YES' : 'NO'}</strong></div>
                        <div>Reason Code: <code>${ctx.reason_code}</code></div>
                        <div>Current SOC: <strong>${ctx.current_soc_pct}%</strong></div>
                        <div>Est. Range: <strong>${ctx.estimated_remaining_range_km ?? '-'} km</strong></div>
                        <div>Remaining Trip: <strong>${ctx.remaining_trip_distance_km ?? '-'} km</strong></div>
                        <div>Safety Reserve: <strong>${ctx.safety_reserve_km ?? '-'} km</strong></div>
                        <div>Energy Margin: <strong>${ctx.energy_margin_km ?? '-'} km</strong></div>
                        <div>Allowed Services: <strong>${(ctx.allowed_service_types || []).join(', ')}</strong></div>
                        <div>Resolved Service: <strong>${ctx.resolved_service_type || 'NONE (EVALUATES ALL)'}</strong></div>
                    </div>
                </div>
            `;
        }

        // Candidate Table
        const candidateContainer = document.getElementById('sim-candidates-container');
        if (candidateContainer) {
            candidateContainer.innerHTML = renderCandidateTable(
                candResult?.candidates || [],
                recResult?.ranked_candidates || []
            );
        }
    }

    renderConflictState(conflictError) {
        const recContainer = document.getElementById('sim-recommendation-container');
        if (recContainer) {
            recContainer.innerHTML = renderConflictAlert(conflictError.detail, () => this.runSimulation());
            document.getElementById('btn-refresh-conflict')?.addEventListener('click', () => this.runSimulation());
        }
    }

    renderErrorState(err) {
        const recContainer = document.getElementById('sim-recommendation-container');
        if (recContainer) {
            recContainer.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <h4>Backend Error (${err.status || '500'})</h4>
                    <p>${err.message}</p>
                    <small>Code: <code>${err.code || 'UNKNOWN'}</code></small>
                </div>
            `;
        }
    }
}
