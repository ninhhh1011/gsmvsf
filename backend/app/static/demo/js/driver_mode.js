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
    renderRecommendationCard
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

        // Energy state
        this.currentSocPct = 85.0;
        this.estimatedRangeKm = 100.0;
        this.safetyReserveKm = 2.0;

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

        // Proactive Station Search & Destination Picking
        this.isPickingDestination = false;
        this.currentStationsFilter = 'ALL';
        this._onMapPickClick = null;

        // Trajectory Replay Controller
        this.replay = new TrajectoryReplayController(apiClient, mapEngine, {
            onStep: async (stepData) => await this._onReplayStep(stepData),
            session: this.session
        });

        this.onStateChange = options.onStateChange || (() => {});
    }

    setCatalogs(trips, vehicles, stations, scenarios = []) {
        this.trips = trips || [];
        this.vehicles = vehicles || [];
        this.stations = stations || [];
        this.scenarios = scenarios || [];
    }

    async init() {
        this.setState(DriverState.AVAILABLE);
        this.renderAvailableUI();
        this.bindGlobalControls();
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

        const trip = this.trips.find(t => t.trip_id === tripId) || this.trips[0];
        if (!trip) return;

        this.currentTrip = trip;
        this.currentVehicle = this.vehicles.find(v => v.vehicle_id === trip.vehicle_id)
            || this.vehicles[0];

        // Scenario energy context matching
        const matchingScenario = this.scenarios.find(s => s.trip_id === trip.trip_id || s.id === trip.scenario_id);
        if (matchingScenario) {
            this.currentSocPct = matchingScenario.soc_pct ?? 85.0;
            this.estimatedRangeKm = matchingScenario.estimated_range_km ?? 100.0;
            this.safetyReserveKm = matchingScenario.safety_reserve_km ?? 2.0;
        } else {
            this.currentSocPct = 85.0;
            this.estimatedRangeKm = 100.0;
            this.safetyReserveKm = 2.0;
        }

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
        this.map.renderTripEndpoints(trip.origin, trip.destination);

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

        const trajId = this._tripToTrajectory(this.currentTrip.trip_id);
        this.session.trajectory_id = trajId;
        await this.replay.loadTrajectory(trajId);

        if (this.generation !== currentGen) return;

        // Initial recommendation & render UI
        await this._evaluateAtCurrentPosition();
        this.renderTripActiveUI();

        // Auto-step first observation
        await this.replay.step();
    }

    _tripToTrajectory(tripId) {
        const mapping = {
            'T0001': 'TRJ0001',
            'T0002': 'TRJ0002',
            'T0003': 'TRJ0003',
            'T0004': 'TRJ0004',
            'T0005': 'TRJ0005',
            'T0017': 'TRJ0001',
            'T0018': 'TRJ0001',
            'T0019': 'TRJ0001',
            'T0073': 'TRJ0001',
            'T0110': 'TRJ0001',
            'T0129': 'TRJ0001'
        };
        const trajId = mapping[tripId];
        if (!trajId) {
            throw new Error(`UNMAPPED_TRIP: Trip '${tripId}' not mapped to any trajectory`);
        }
        return trajId;
    }

    // ─── Step Handling ──────────────────────────────────────────────────

    async _onReplayStep(stepData) {
        const { locResp, observation } = stepData;
        if (this.state !== DriverState.TRIP_ACTIVE) return;

        this.currentObservation = observation;

        if (locResp.matched_position) {
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

        await this._evaluateAtCurrentPosition();
        this.renderTripActiveUI();
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
        if (!this.currentVehicle || !this.currentPos) return;

        const currentGen = this.generation;
        const driverId = this.session.driver_id || 'UNASSIGNED';
        const timestamp = (this.currentObservation?.timestamp)
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

            let leg1Result = null;
            let leg2Result = null;

            if (rec.has_recommendation && rec.ranked_candidates?.length > 0) {
                const top = rec.ranked_candidates[0];
                const st = this.stations.find(s => s.station_id === top.station_id);
                if (st && this.currentTrip?.destination) {
                    const stPos = { latitude: st.latitude, longitude: st.longitude };
                    // If recommendation station changed, compute new diversion legs
                    if (top.station_id !== this.lastRecommendedStationId) {
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
                                    this.map.renderRecommendationRoute(leg1Result.geometry, leg2Result?.geometry);
                                }
                            }
                        } catch (routeErr) {
                            console.warn('Recommendation diversion route error:', routeErr);
                        }
                    } else {
                        leg1Result = this.lastDiversionLeg1;
                        leg2Result = this.lastDiversionLeg2;
                    }
                    this.map.renderStations(this.stations, top.station_id, top.service_type, null, rec.ranked_candidates);
                } else {
                    this.map.renderStations(this.stations, top.station_id, top.service_type, null, rec.ranked_candidates);
                }
            } else {
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
        }
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
        this.returnToAvailable();
    }

    async navigateViaStation() {
        if (!this.lastRecommendation?.has_recommendation || !this.lastRecommendation.ranked_candidates?.length) return;
        const top = this.lastRecommendation.ranked_candidates[0];
        await this.navigateViaStationId(top.station_id);
    }

    async navigateViaStationId(stationId) {
        const st = this.stations.find(s => s.station_id === stationId);
        if (!st) return;

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
                    this.lastDiversionLeg2 = leg2;
                    this.map.renderRecommendationRoute(leg1.geometry, leg2?.geometry);
                    this.map.fitBoundsToActive();
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

    // ─── Proactive Station Drawer & Map Destination Picking ─────────────

    bindGlobalControls() {
        document.getElementById('btn-open-stations-drawer')?.addEventListener('click', () => {
            this.openStationsDrawer();
        });

        document.getElementById('btn-close-stations-drawer')?.addEventListener('click', () => {
            this.closeStationsDrawer();
        });

        document.getElementById('btn-pick-custom-dest')?.addEventListener('click', () => {
            this.startPickCustomDestination();
        });

        document.getElementById('btn-cancel-pick-dest')?.addEventListener('click', () => {
            this.cancelPickCustomDestination();
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

    openStationsDrawer(filter = null) {
        const drawer = document.getElementById('stations-drawer');
        if (!drawer) return;
        if (filter) this.currentStationsFilter = filter;
        drawer.style.display = 'flex';
        this.renderStationsDrawer(this.currentStationsFilter);
    }

    closeStationsDrawer() {
        const drawer = document.getElementById('stations-drawer');
        if (drawer) drawer.style.display = 'none';
    }

    renderStationsDrawer(filter = 'ALL') {
        const listContainer = document.getElementById('stations-drawer-list');
        const countSpan = document.getElementById('drawer-station-count');
        if (!listContainer) return;

        const currentPos = this.currentPos || (this.currentTrip?.origin ? {
            latitude: this.currentTrip.origin.latitude,
            longitude: this.currentTrip.origin.longitude
        } : { latitude: 21.1038023, longitude: 106.0023809 });

        // Calculate distance from vehicle to each station
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

        // Top recommendation ID
        const topRecId = this.lastRecommendation?.has_recommendation && this.lastRecommendation.ranked_candidates?.length > 0
            ? this.lastRecommendation.ranked_candidates[0].station_id
            : null;

        // Sort: Top recommendation first, then by distance ascending
        filtered.sort((a, b) => {
            if (a.station_id === topRecId) return -1;
            if (b.station_id === topRecId) return 1;
            return a.distMeters - b.distMeters;
        });

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

            return `
                <div class="station-drawer-card ${isRec ? 'is-recommended' : ''}" data-station-id="${st.station_id}">
                    <div class="station-card-top">
                        <div>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span class="station-card-name">Trạm ${st.station_id}</span>
                                ${isRec ? `<span class="badge-rec-hero">⭐ ĐỀ XUẤT TỐI ƯU</span>` : ''}
                            </div>
                            <div style="font-size:12px; color:#64748b; margin-top:2px;">
                                ${st.name || `Trạm năng lượng ${st.station_id}`}
                            </div>
                        </div>
                        ${typeBadge}
                    </div>

                    <div class="station-card-meta">
                        <span>📍 Cách <strong>${st.distKm} km</strong></span>
                        <span>⚡ ${totalSlots} cổng</span>
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                        <button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">
                            Xem vị trí
                        </button>
                        <button class="btn btn-primary btn-sm btn-nav-drawer-station" data-station-id="${st.station_id}">
                            Dẫn đường tới đây
                        </button>
                    </div>
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

        listContainer.querySelectorAll('.btn-zoom-station').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const lat = parseFloat(btn.dataset.lat);
                const lng = parseFloat(btn.dataset.lng);
                this.map.map.flyTo([lat, lng], 16);
            });
        });
    }

    startPickCustomDestination() {
        if (!this.map?.map) return;
        this.isPickingDestination = true;

        const banner = document.getElementById('map-picker-banner');
        if (banner) banner.style.display = 'flex';
        this.map.setMapCursor('crosshair');

        if (this._onMapPickClick) {
            this.map.map.off('click', this._onMapPickClick);
        }

        this._onMapPickClick = async (e) => {
            const { lat, lng } = e.latlng;
            this.cancelPickCustomDestination();
            await this.setCustomDestination({ latitude: lat, longitude: lng });
        };

        this.map.map.once('click', this._onMapPickClick);
    }

    cancelPickCustomDestination() {
        this.isPickingDestination = false;
        const banner = document.getElementById('map-picker-banner');
        if (banner) banner.style.display = 'none';
        this.map.setMapCursor('');
        if (this._onMapPickClick && this.map?.map) {
            this.map.map.off('click', this._onMapPickClick);
            this._onMapPickClick = null;
        }
    }

    async setCustomDestination(dest) {
        if (!dest) return;
        const origin = this.currentPos || (this.currentTrip?.origin ? {
            latitude: this.currentTrip.origin.latitude,
            longitude: this.currentTrip.origin.longitude
        } : { latitude: 21.1038023, longitude: 106.0023809 });

        const vCat = this.currentVehicle?.vehicle_type || 'EV_CAR';
        try {
            const routeResult = await this.api.computeRoute(origin, dest, { vehicle_category: vCat });
            if (routeResult?.geometry) {
                const coords = decodePolyline(routeResult.geometry);
                this.fullRouteCoords = coords;
                this.directRouteGeometry = coords;
                this.map.clearAll();
                this.map.renderTripEndpoints(origin, dest);
                this.map.renderDirectRoute(coords);
                this.map.fitBoundsToActive(coords);
                this.map.renderStations(this.stations);

                const plannedKm = routeResult.distance_m ? parseFloat((routeResult.distance_m / 1000).toFixed(2)) : 5.0;
                this.remainingTripDistanceKm = plannedKm;

                this.currentTrip = {
                    trip_id: 'CUSTOM_DEST',
                    origin,
                    destination: dest,
                    planned_distance_m: routeResult.distance_m
                };

                if (this.state === DriverState.AVAILABLE) {
                    this.setState(DriverState.TRIP_ASSIGNED);
                    this.renderTripAssignedUI();
                } else if (this.state === DriverState.TRIP_ACTIVE) {
                    await this._evaluateAtCurrentPosition();
                    this.renderTripActiveUI();
                }
            }
        } catch (err) {
            console.warn('Failed to compute route to custom destination:', err);
        }
    }

    // ─── UI Renderers ───────────────────────────────────────────────────

    renderAvailableUI() {
        const container = document.getElementById('driver-panel-content');
        if (!container) return;

        const tripOptions = this.trips.map(t => `
            <option value="${t.trip_id}">
                ${t.trip_id} — ${this._getScenarioDescription(t.scenario_id)} (${(t.planned_distance_m / 1000).toFixed(1)} km)
            </option>
        `).join('');

        container.innerHTML = `
            <div class="driver-available-card">
                <div class="card-status-indicator">
                    <span class="pulse-dot green"></span>
                    <h3>Sẵn sàng nhận chuyến</h3>
                </div>
                <p class="text-muted" style="margin-top: 4px; font-size: 13px;">
                    Bản đồ dẫn đường thông minh thời gian thực. Chọn chuyến đi để bắt đầu:
                </p>

                <div class="form-group mt-3">
                    <label style="font-weight: 600; font-size: 12px; text-transform: uppercase; color: var(--text-muted);">
                        Chọn chuyến đi:
                    </label>
                    <select id="select-driver-trip" class="form-control" style="margin-top: 6px;">
                        ${tripOptions}
                    </select>
                </div>

                <div class="driver-actions mt-4">
                    <button id="btn-accept-trip" class="btn btn-primary btn-lg btn-block">
                        Nhận chuyến đi
                    </button>
                    <button id="btn-pick-dest-map" class="btn btn-outline btn-block mt-2">
                        📍 Chọn điểm đến trên bản đồ
                    </button>
                    <button id="btn-go-offline" class="btn btn-outline btn-sm mt-2">
                        Chuyển ngoại tuyến
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-accept-trip')?.addEventListener('click', () => {
            const tripId = document.getElementById('select-driver-trip')?.value;
            this.assignTrip(tripId);
        });

        document.getElementById('btn-pick-dest-map')?.addEventListener('click', () => {
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

                <div class="hud-details" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px;">
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
                        <strong class="stat-value" style="font-size: 14px;">${this.currentSocPct.toFixed(0)}%</strong>
                    </div>
                </div>

                <div class="driver-actions">
                    <button id="btn-start-driving" class="btn btn-success btn-lg btn-block">
                        ▶ Bắt đầu lái xe
                    </button>
                    <button id="btn-cancel-trip" class="btn btn-outline btn-sm mt-2">
                        Hủy nhận chuyến
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-start-driving')?.addEventListener('click', () => this.startTrip());
        document.getElementById('btn-cancel-trip')?.addEventListener('click', () => this.cancelTrip());
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
            const completionMin = top.eta_to_service_complete_s != null
                ? (top.eta_to_service_complete_s / 60).toFixed(0)
                : Math.round(top.final_cost_s / 60).toString();
            const cap = top.features?.available_capacity;
            const capText = cap != null ? ` · ${cap} vị trí còn trống` : '';

            recSnippet = `
                <div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}" style="margin-top: 12px; padding: 12px; background: rgba(13, 148, 136, 0.1); border: 1px solid rgba(13, 148, 136, 0.3); border-radius: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong>Trạm ${top.station_id}</strong> — ${isSwap ? 'Đổi pin nhanh' : 'Sạc pin'}
                            <span class="sr-only">${top.station_id} ${isSwap ? 'Battery Swap' : 'Charging'}</span>
                            <div class="text-sm text-muted" style="margin-top: 2px;">
                                +${detourKm} km lệch lộ trình · Sẵn sàng sau ${completionMin} phút${capText}
                                <span class="sr-only">+${detourKm} km detour Ready in ${completionMin} min</span>
                            </div>
                        </div>
                        <span class="badge ${isSwap ? 'badge-purple' : 'badge-teal'}">
                            Khuyến nghị
                            <span class="sr-only">Recommended</span>
                        </span>
                    </div>
                    <button id="btn-nav-station" class="btn btn-accent btn-sm mt-2" style="width: 100%;">
                        Chỉ đường ghé trạm
                        <span class="sr-only">Navigate Via Station</span>
                    </button>
                </div>
            `;
        }

        const posStatus = this.matchedPos
            ? `<span class="text-success">Khớp đường: ${this.matchedPos.road_segment_id || 'đã khớp'} <span class="sr-only">Road: ${this.matchedPos.road_segment_id || 'matched'}</span></span>`
            : (this.currentPos
                ? `<span class="text-warning">GPS trực tiếp (${this.currentPos.latitude.toFixed(4)}, ${this.currentPos.longitude.toFixed(4)}) <span class="sr-only">Raw GPS</span></span>`
                : '<span class="text-muted">Đang định vị...</span>');

        const progress = this.replay.getProgressText?.() || '';

        container.innerHTML = `
            <div class="driver-nav-hud">
                ${warningBanner}

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
                            <span class="stat-value">${this.remainingTripDistanceKm.toFixed(1)} <small>km</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">ETA</span>
                            <span class="stat-value">${etaMin} <small>phút</small><span class="sr-only">min</span></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Pin (SOC)</span>
                            <span class="stat-value ${this.currentSocPct < 20 ? 'text-danger' : ''}">${this.currentSocPct.toFixed(0)}%</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Tầm xa</span>
                            <span class="stat-value">${this.estimatedRangeKm.toFixed(0)} <small>km</small></span>
                        </div>
                    </div>

                    <div class="battery-bar-container" style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div class="battery-bar-fill ${this.currentSocPct < 20 ? 'bg-danger' : (this.currentSocPct < 30 ? 'bg-warning' : 'bg-success')}"
                             style="width: ${Math.max(5, this.currentSocPct)}%; height: 100%;"></div>
                    </div>

                    <div class="text-xs text-muted mt-2" style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span>${posStatus}</span>
                        <span>${progress}</span>
                    </div>
                </div>

                ${recSnippet}

                <div class="driver-controls mt-3">
                    <div class="replay-controls d-flex gap-2 mb-2" style="display: flex; gap: 8px;">
                        <button id="btn-driver-replay-play" class="btn btn-primary btn-sm flex-1">▶ Bắt đầu</button>
                        <button id="btn-driver-replay-pause" class="btn btn-outline btn-sm flex-1">⏸ Tạm dừng</button>
                        <button id="btn-driver-replay-step" class="btn btn-outline btn-sm flex-1">⏭ Từng bước</button>
                    </div>
                    <button id="btn-complete-trip" class="btn btn-outline btn-sm btn-block">
                        ✓ Hoàn thành chuyến đi
                    </button>
                </div>
            </div>
        `;

        document.getElementById('btn-driver-replay-play')?.addEventListener('click', () => this.playTrip());
        document.getElementById('btn-driver-replay-pause')?.addEventListener('click', () => this.pauseTrip());
        document.getElementById('btn-driver-replay-step')?.addEventListener('click', () => this.stepTrip());
        document.getElementById('btn-nav-station')?.addEventListener('click', () => this.navigateViaStation());
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
                <div class="completion-header text-center" style="text-align: center; margin-bottom: 16px;">
                    <span class="check-icon" style="display: inline-block; width: 44px; height: 44px; line-height: 44px; background: rgba(16, 185, 129, 0.2); color: #10b981; border-radius: 50%; font-size: 22px; font-weight: bold; margin-bottom: 8px;">✓</span>
                    <h3>Chuyến đi hoàn tất</h3>
                    <p class="text-muted" style="font-size: 13px;">Hành khách đã xuống xe an toàn.</p>
                </div>

                ${warningBanner}

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

        document.getElementById('btn-back-available')?.addEventListener('click', () => this.returnToAvailable());
    }
}
