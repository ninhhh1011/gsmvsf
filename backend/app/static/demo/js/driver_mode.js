/**
 * Driver Mode Controller - Clean Driver-First UI
 * Minimal, distraction-free interface for in-car use
 */

import { renderEnergyWarningBanner, renderRecommendationCard } from './components.js';
import { TrajectoryReplayController } from './replay.js';

// State machine
export const DriverState = {
    OFFLINE: 'OFFLINE',
    AVAILABLE: 'AVAILABLE',
    TRIP_ASSIGNED: 'TRIP_ASSIGNED',
    TO_PICKUP: 'TO_PICKUP',
    ON_TRIP: 'ON_TRIP',
    TRIP_ACTIVE: 'TRIP_ACTIVE',
    TRIP_COMPLETE: 'TRIP_COMPLETE'
};

function toRad(deg) {
    return deg * Math.PI / 180;
}

export function straightLineDistanceKm(lat1, lng1, lat2, lng2) {
    const R = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLng = toRad(lng2 - lng1);
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
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
        this.state = DriverState.AVAILABLE;
        this.currentTrip = null;
        this.currentVehicle = null;
        this.mode = 'REPLAY';

        // Energy state
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 100.0;
        this.safetyReserveKm = 2.0;

        // Position
        this.currentPos = null;
        this.matchedPos = null;
        this.currentObservation = null;

        // Trip progress
        this.remainingTripDistanceKm = 0.0;
        this.lastKnownRoadDistanceKm = 0.0;

        // Recommendation cache
        this.lastRecommendation = null;

        // Trajectory replay
        this.replay = new TrajectoryReplayController(apiClient, mapEngine, {
            onStep: async (stepData) => await this._onReplayStep(stepData),
            session: this.session
        });

        this.onStateChange = options.onStateChange || (() => {});
        this.selectedTripId = null;
    }

    setCatalogs(trips, vehicles, stations, scenarios = []) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
        this.scenarios = scenarios || [];
    }

    async init() {
        this.renderTripSelect();
    }

    setState(newState) {
        this.state = newState;
        this.onStateChange(this.state);
        this.updateHeaderStatus();
    }

    updateHeaderStatus() {
        const statusText = document.getElementById('status-text');
        if (!statusText) return;

        const statusMap = {
            [DriverState.OFFLINE]: 'Ngoại tuyến',
            [DriverState.AVAILABLE]: 'Trực tuyến',
            [DriverState.TRIP_ASSIGNED]: 'Chuyến đi',
            [DriverState.TRIP_ACTIVE]: 'Đang lái',
            [DriverState.TRIP_COMPLETE]: 'Hoàn thành'
        };
        statusText.textContent = statusMap[this.state] || 'Trực tuyến';
    }

    // ─── Trip Selection ────────────────────────────────────────────────

    renderTripSelect() {
        const hud = document.getElementById('driver-hud');
        const select = document.getElementById('trip-select');
        const tripList = document.getElementById('trip-list');
        const startBtn = document.getElementById('btn-start-trip');

        if (hud) hud.classList.add('hidden');
        if (select) select.classList.remove('hidden');

        // Populate trip list
        if (tripList && this.trips.length > 0) {
            tripList.innerHTML = this.trips.map(trip => {
                const desc = this._getScenarioDescription(trip.scenario_id);
                const distance = (trip.planned_distance_m / 1000).toFixed(1);
                return `
                    <div class="trip-item ${this.selectedTripId === trip.trip_id ? 'selected' : ''}"
                         data-trip-id="${trip.trip_id}">
                        <div class="trip-item-header">
                            <span class="trip-item-id">${trip.trip_id}</span>
                            <span class="trip-item-distance">${distance} km</span>
                        </div>
                        <div class="trip-item-desc">${desc}</div>
                    </div>
                `;
            }).join('');

            // Click handlers
            tripList.querySelectorAll('.trip-item').forEach(item => {
                item.addEventListener('click', () => {
                    this.selectedTripId = item.dataset.tripId;
                    tripList.querySelectorAll('.trip-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    startBtn.disabled = false;
                });
            });
        }

        // Start button handler
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                if (this.selectedTripId) {
                    this.assignTrip(this.selectedTripId);
                }
            });
            startBtn.disabled = !this.selectedTripId;
        }
    }

    _getScenarioDescription(scenarioId) {
        const descriptions = {
            'NORMAL_TRIP': 'Chuyến đi thường',
            'NO_SERVICE_NEEDED': 'Không cần dịch vụ',
            'LOW_SOC': 'Pin thấp',
            'NEED_CHARGING': 'Cần sạc pin',
            'QUEUE_REALTIME_CHANGE': 'Hàng đợi thay đổi',
            'TRAFFIC_REALTIME_CHANGE': 'Kẹt xe',
            'STATION_STATUS_CHANGE': 'Trạm thay đổi',
            'FARTHER_BUT_FASTER': 'Xa hơn nhưng nhanh hơn',
            'NEED_SWAP': 'Cần đổi pin'
        };
        return descriptions[scenarioId] || scenarioId;
    }

    // ─── Trip Assignment ────────────────────────────────────────────────

    async assignTrip(tripId) {
        this.generation++;
        const currentGen = this.generation;

        const trip = this.trips.find(t => t.trip_id === tripId);
        if (!trip) return;

        this.currentTrip = trip;
        this.currentVehicle = this.vehicles.find(v => v.vehicle_id === trip.vehicle_id)
            || this.vehicles[0];

        // Source energy from scenario
        const matchingScenario = this.scenarios.find(s => s.trip_id === trip.trip_id || s.id === trip.scenario_id);
        if (matchingScenario) {
            this.currentSocPct = matchingScenario.soc_pct ?? 85.0;
            this.estimatedRangeKm = matchingScenario.estimated_range_km ?? 100.0;
            this.safetyReserveKm = matchingScenario.safety_reserve_km ?? 2.0;
        }

        const plannedKm = trip.planned_distance_m ? (trip.planned_distance_m / 1000) : 0.0;
        this.remainingTripDistanceKm = plannedKm;
        this.lastKnownRoadDistanceKm = plannedKm;

        // Clear map and show route
        this.map.clearAll();
        this.map.renderTripEndpoints(trip.origin, trip.destination);

        // Compute direct route
        try {
            const routeResult = await this.api.computeRoute(
                trip.origin,
                trip.destination,
                { vehicle_category: this.currentVehicle?.vehicle_type || 'EV_CAR' }
            );
            if (this.generation !== currentGen) return;
            if (routeResult.geometry) {
                this.map.renderDirectRoute(routeResult.geometry);
            }
            if (routeResult.distance_m) {
                this.remainingTripDistanceKm = parseFloat((routeResult.distance_m / 1000).toFixed(2));
            }
        } catch (err) {
            console.warn('Route error:', err);
        }

        this.map.fitBoundsToActive();
        this.setState(DriverState.TRIP_ASSIGNED);
        this.renderTripActiveUI();
    }

    // ─── Trip Active ────────────────────────────────────────────────────

    async startTrip() {
        if (!this.currentTrip) return;

        this.generation++;
        const currentGen = this.generation;

        this.session.driver_id = `driver_${Date.now().toString(36)}`;
        this.session.vehicle_id = this.currentVehicle?.vehicle_id;
        this.session.vehicle_category = this.currentVehicle?.vehicle_type;
        this.session.trip_id = this.currentTrip.trip_id;
        this.mode = 'REPLAY';

        this.setState(DriverState.TRIP_ACTIVE);

        const trajId = this._tripToTrajectory(this.currentTrip.trip_id);
        this.session.trajectory_id = trajId;
        await this.replay.loadTrajectory(trajId);

        if (this.generation !== currentGen) return;

        this.renderTripActiveUI();
        await this.replay.step();
    }

    _tripToTrajectory(tripId) {
        const mapping = {
            'T0001': 'TRJ0001', 'T0002': 'TRJ0002', 'T0003': 'TRJ0003',
            'T0004': 'TRJ0004', 'T0005': 'TRJ0005', 'T0017': 'TRJ0001',
            'T0018': 'TRJ0001', 'T0019': 'TRJ0001', 'T0073': 'TRJ0001',
            'T0110': 'TRJ0001', 'T0129': 'TRJ0001',
        };
        const trajId = mapping[tripId];
        if (!trajId) {
            throw new Error(`UNMAPPED_TRIP: Trip '${tripId}' not mapped`);
        }
        return trajId;
    }

    // ─── Replay Step Handler ───────────────────────────────────────────

    async _onReplayStep(stepData) {
        const { locResp, observation } = stepData;
        if (this.state !== DriverState.TRIP_ACTIVE) return;

        this.currentObservation = observation;

        // Update position
        if (locResp.matched_position) {
            this.matchedPos = {
                latitude: locResp.matched_position.latitude,
                longitude: locResp.matched_position.longitude,
                road_segment_id: locResp.matched_position.road_segment_id
            };
            this.currentPos = {
                latitude: locResp.matched_position.latitude,
                longitude: locResp.matched_position.longitude
            };
        } else if (locResp.raw_position) {
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

        // Update remaining distance
        if (this.currentPos && this.currentTrip?.destination) {
            try {
                const legRoute = await this.api.computeRoute(
                    this.currentPos,
                    this.currentTrip.destination,
                    { vehicle_category: this.currentVehicle?.vehicle_type || 'EV_CAR' }
                );
                if (legRoute?.distance_m != null) {
                    this.remainingTripDistanceKm = parseFloat((legRoute.distance_m / 1000).toFixed(2));
                }
            } catch {
                // Keep last known
            }
        }

        // Re-evaluate recommendation
        await this._evaluateAtCurrentPosition();
        this.updateHUDDisplay();
    }

    async _evaluateAtCurrentPosition() {
        if (!this.currentVehicle || !this.currentPos) return;

        const currentGen = this.generation;
        const driverId = this.session.driver_id || 'UNASSIGNED';
        const timestamp = (this.mode === 'REPLAY' && this.currentObservation?.timestamp)
            ? this.currentObservation.timestamp
            : (this.currentTrip?.start_time || new Date().toISOString());

        const rawLat = this.currentObservation ? this.currentObservation.latitude : this.currentPos.latitude;
        const rawLng = this.currentObservation ? this.currentObservation.longitude : this.currentPos.longitude;

        const payload = {
            context: {
                vehicle_id: this.currentVehicle.vehicle_id,
                driver_id: driverId,
                trip_id: this.currentTrip?.trip_id,
                timestamp: timestamp,
                current_soc_pct: parseFloat(this.currentSocPct.toFixed(1)),
                estimated_remaining_range_km: parseFloat(this.estimatedRangeKm.toFixed(1)),
                remaining_trip_distance_km: parseFloat(this.remainingTripDistanceKm.toFixed(2)),
                safety_reserve_km: this.safetyReserveKm,
                raw_latitude: rawLat,
                raw_longitude: rawLng
            },
            destination_latitude: this.currentTrip?.destination?.latitude,
            destination_longitude: this.currentTrip?.destination?.longitude,
            top_n: 5
        };

        try {
            const rec = await this.api.getRecommendation(payload);
            if (this.generation !== currentGen) return;

            this.lastRecommendation = rec;

            // Render station on map if recommendation exists
            if (rec.has_recommendation && rec.ranked_candidates?.length > 0) {
                const top = rec.ranked_candidates[0];
                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st) {
                    this.map.renderStations(this.stations, top.station_id, top.service_type);
                }
            } else {
                this.map.renderStations(this.stations);
            }
        } catch (err) {
            if (this.generation !== currentGen) return;
            console.warn('Recommendation error:', err);
            this.lastRecommendation = null;
        }
    }

    // ─── HUD Rendering ─────────────────────────────────────────────────

    renderTripActiveUI() {
        const hud = document.getElementById('driver-hud');
        const select = document.getElementById('trip-select');

        if (hud) hud.classList.remove('hidden');
        if (select) select.classList.add('hidden');

        // Bind controls
        document.getElementById('btn-pause')?.addEventListener('click', () => this.pauseTrip());
        document.getElementById('btn-complete')?.addEventListener('click', () => this.completeTrip());

        this.updateHUDDisplay();
    }

    updateHUDDisplay() {
        // Destination
        const destName = document.getElementById('dest-name');
        if (destName) {
            destName.textContent = 'Trả khách';
        }

        // ETA
        const etaValue = document.getElementById('eta-value');
        if (etaValue) {
            let etaMin = '--';
            if (this.lastRecommendation?.ranked_candidates?.length > 0) {
                const top = this.lastRecommendation.ranked_candidates[0];
                etaMin = Math.round(top.eta_to_station_s / 60).toString();
            }
            etaValue.innerHTML = `${etaMin}<span class="unit">phút</span>`;
        }

        // Distance
        const distanceValue = document.getElementById('distance-value');
        if (distanceValue) {
            distanceValue.innerHTML = `${this.remainingTripDistanceKm.toFixed(1)}<span class="unit">km</span>`;
        }

        // Battery
        const batteryValue = document.getElementById('battery-value');
        if (batteryValue) {
            batteryValue.innerHTML = `${this.currentSocPct.toFixed(0)}<span class="unit">%</span>`;
        }

        // Battery bar
        const batteryBar = document.getElementById('battery-bar');
        if (batteryBar) {
            batteryBar.style.width = `${Math.max(5, this.currentSocPct)}%`;
            batteryBar.className = 'battery-fill';
            if (this.currentSocPct < 15) {
                batteryBar.classList.add('critical');
            } else if (this.currentSocPct < 30) {
                batteryBar.classList.add('warning');
            }
        }

        // Range
        const rangeValue = document.getElementById('range-value');
        if (rangeValue) {
            rangeValue.textContent = `${this.estimatedRangeKm.toFixed(0)} km`;
        }

        // Battery status
        const batteryStatus = document.getElementById('battery-status');
        if (batteryStatus && this.lastRecommendation?.energy_context) {
            const { need_service, reason_code } = this.lastRecommendation.energy_context;
            if (need_service && reason_code === 'DESTINATION_NOT_REACHABLE') {
                batteryStatus.textContent = '⚠️ Không đủ pin!';
                batteryStatus.style.color = '#ff3b30';
            } else if (need_service) {
                batteryStatus.textContent = '⚠️ Pin thấp';
                batteryStatus.style.color = '#ff9500';
            } else {
                batteryStatus.textContent = 'Bình thường';
                batteryStatus.style.color = 'rgba(255,255,255,0.5)';
            }
        } else if (batteryStatus) {
            batteryStatus.textContent = 'Bình thường';
            batteryStatus.style.color = 'rgba(255,255,255,0.5)';
        }

        // Station alert
        const stationAlert = document.getElementById('station-alert');
        if (stationAlert) {
            if (this.lastRecommendation?.has_recommendation && this.lastRecommendation.ranked_candidates?.length > 0) {
                stationAlert.classList.remove('hidden');
                const top = this.lastRecommendation.ranked_candidates[0];
                const isSwap = top.service_type === 'BATTERY_SWAP';
                document.getElementById('station-name').textContent = `Trạm ${top.station_id}`;
                document.getElementById('station-detail').textContent =
                    `Cách bạn ${Math.round(top.eta_to_station_s / 60)} phút • ${isSwap ? 'Đổi pin' : 'Sạc pin'}`;
            } else {
                stationAlert.classList.add('hidden');
            }
        }

        // Progress
        const progressText = document.getElementById('progress-text');
        const progressFill = document.getElementById('progress-fill');
        if (progressText && progressFill) {
            const total = this.replay.observations?.length || 0;
            const current = this.replay.currentIndex || 0;
            progressText.textContent = `${current}/${total}`;
            progressFill.style.width = total > 0 ? `${(current / total) * 100}%` : '0%';
        }
    }

    // ─── Controls ──────────────────────────────────────────────────────

    pauseTrip() {
        this.replay.pause();
        const btn = document.getElementById('btn-pause');
        if (btn) {
            btn.textContent = '▶ Tiếp tục';
            btn.onclick = () => this.resumeTrip();
        }
    }

    resumeTrip() {
        this.replay.play();
        const btn = document.getElementById('btn-pause');
        if (btn) {
            btn.textContent = '⏸ Dừng';
            btn.onclick = () => this.pauseTrip();
        }
    }

    completeTrip() {
        this.setState(DriverState.TRIP_COMPLETE);
        this.showTripComplete();
    }

    showTripComplete() {
        const hud = document.getElementById('driver-hud');
        if (hud) hud.classList.add('hidden');

        // Show completion message
        const select = document.getElementById('trip-select');
        if (select) {
            select.classList.remove('hidden');
            select.innerHTML = `
                <div class="trip-select-icon" style="background: linear-gradient(135deg, rgba(0,255,136,0.2), rgba(0,217,255,0.1));">✓</div>
                <h2 class="trip-select-title">Hoàn thành chuyến!</h2>
                <p class="trip-select-desc">Đã trả khách an toàn.</p>
                ${this.lastRecommendation?.has_recommendation ? `
                    <div class="station-alert" style="margin-top: 20px;">
                        <div class="station-alert-icon">⚡</div>
                        <div class="station-alert-info">
                            <div class="station-alert-title">Khuyến nghị sạc pin</div>
                            <div class="station-alert-detail">Trạm ${this.lastRecommendation.ranked_candidates[0].station_id} - ${Math.round(this.lastRecommendation.ranked_candidates[0].eta_to_station_s / 60)} phút</div>
                        </div>
                    </div>
                ` : ''}
                <button class="start-trip-btn" onclick="window.app.driverMode.returnToAvailable()">
                    Chuyến tiếp theo
                </button>
            `;
        }
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
        this.remainingTripDistanceKm = 0.0;
        this.selectedTripId = null;

        this.session.driver_id = null;
        this.session.vehicle_id = null;
        this.session.vehicle_category = null;
        this.session.trip_id = null;
        this.session.trajectory_id = null;

        this.setState(DriverState.AVAILABLE);
        this.renderTripSelect();
    }

    // ─── Legacy methods for compatibility ──────────────────────────────

    stepTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        this.replay.step();
    }

    playTrip() {
        if (this.state !== DriverState.TRIP_ACTIVE) return;
        this.replay.play();
    }

    pauseTripLegacy() {
        this.replay.pause();
    }

    goOffline() {
        this.setState(DriverState.OFFLINE);
    }

    goOnline() {
        this.setState(DriverState.AVAILABLE);
    }

    cancelTrip() {
        this.returnToAvailable();
    }
}
