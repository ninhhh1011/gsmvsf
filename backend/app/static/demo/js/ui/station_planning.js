import { DriverState } from '../domain/driver_state.js';
import { renderDrawerStationsListHTML } from './drawer_renderer.js';
import { decodePolyline } from '../map.js';

export function planningRequest(controller) {
    const origin = controller.planningOrigin;
    if (!origin || !controller.currentVehicle) return null;
    const destination = controller.navigationStages?.passengerPassed ? null : controller.passengerDestination;
    return {
        context: {
            vehicle_id: controller.currentVehicle.vehicle_id,
            driver_id: controller.api.driverIdentity?.driver_id || controller.session.driver_id || undefined,
            current_soc_pct: controller.currentSocPct,
            estimated_remaining_range_km: controller.estimatedRangeKm,
            remaining_trip_distance_km: destination ? controller.remainingTripDistanceKm : 0,
            distance_travelled_km: controller.totalDistanceTravelledKm || 0,
            safety_reserve_km: controller.safetyReserveKm,
            consumption_wh_per_km: controller.currentVehicle.consumption_wh_per_km,
            raw_latitude: origin.latitude, raw_longitude: origin.longitude,
            timestamp: new Date().toISOString()
        },
        requested_service: 'ANY',
        destination_latitude: destination?.latitude ?? null,
        destination_longitude: destination?.longitude ?? null,
        avoid_congestion: !!controller.avoidCongestion,
        top_n: 30
    };
}

export async function selectStationPlan(stationId, serviceType = null, mode = 'BEFORE_DESTINATION', refresh = false) {
    const station = this.stations.find(item => item.station_id === stationId);
    const recommendation = mode === 'AFTER_DESTINATION' ? this.postTripRecommendation : this.lastRecommendation;
    const pair = recommendation?.ranked_candidates?.find(item => item.station_id === stationId && (!serviceType || item.service_type === serviceType)) || (station ? { service_type: serviceType || station.service_type || (station.station_type === 'SWAP' ? 'BATTERY_SWAP' : 'CHARGING') } : null);
    if (!station || !pair || (mode === 'AFTER_DESTINATION' && !this.passengerDestination)) return false;
    const payload = planningRequest(this);
    if (!payload) return false;
    const generation = this.generation, powerRevision = this._powerRevision;
    const revision = ++this.routeRevision;
    this.bindings.setNavigationButtonState('Đang kiểm tra trạm...', true);
    try {
        const effectiveMode = this.navigationStages?.passengerPassed ? 'BEFORE_DESTINATION' : mode;
        const plan = await this.api.getStationPlan({ ...payload, station_id: stationId, service_type: pair.service_type, plan_mode: effectiveMode });
        if (this.generation !== generation || this.routeRevision !== revision || this._powerRevision !== powerRevision) return false;
        if (plan.station_id !== stationId || plan.service_type !== pair.service_type || !plan.route) throw new Error('Kế hoạch trạm không hợp lệ');
        const coords = typeof plan.route.geometry === 'string' ? decodePolyline(plan.route.geometry) : plan.route.geometry?.map(([lng, lat]) => [lat, lng]);
        if (!coords?.length) throw new Error('Chưa có hình học tuyến đường');
        const origin = this.planningOrigin;
        const passengerDestination = this.passengerDestination;
        const target = payload.destination_latitude != null && effectiveMode !== 'AFTER_DESTINATION' ? this.passengerDestination : { latitude: station.latitude, longitude: station.longitude };
        this.selectedStationPlan = plan;
        if (!refresh && !this.navigationStages?.passengerPassed) this.navigationStages = { originalMode: mode, passengerPassed: false, stationPassed: false };
        else this.navigationStages ??= { originalMode: mode, passengerPassed: false, stationPassed: false };
        this._navigationLocked = true; this._selectedStationId = stationId;
        this.stationNavigationTarget = { latitude: station.latitude, longitude: station.longitude };
        this.lastRecommendedStationId = stationId;
        this.fullRouteCoords = coords; this.directRouteGeometry = coords; this.currentRouteTiming = plan.route;
        this.remainingTripDistanceKm = plan.route.distance_m / 1000;
        this.lastPassedSegmentIndex = 0; this._clearH3OnRouteChange();
        this.currentTrip = { ...(this.currentTrip || {}), trip_id: this.currentTrip?.trip_id || `NAVI_${stationId}`,
            origin, destination: target, passenger_destination: passengerDestination, goal_role: plan.goal_role || (passengerDestination && mode !== 'AFTER_DESTINATION' ? 'PASSENGER_DESTINATION' : 'STATION'), planned_distance_m: plan.route.distance_m };
        if (mode === 'AFTER_DESTINATION') { this.postTripStation = station; this.postTripRoute = plan.route; }
        this.map.clearAll(); this.map.renderTripEndpoints(origin, target); this.map.renderDirectRoute(coords);
        this.map.renderStations(this.stations, stationId, pair.service_type, null, recommendation?.ranked_candidates);
        this.map.fitBoundsToActive(coords);
        this.closeStationsDrawer();
        if (!refresh) await this.replay.loadFromPolyline(coords);
        if (this.generation !== generation || this.routeRevision !== revision) return false;
        if (this.state === DriverState.AVAILABLE) this.setState(DriverState.TRIP_ASSIGNED);
        if (this.state === DriverState.TRIP_ACTIVE) this.renderTripActiveUI(); else this.renderTripAssignedUI();
        return true;
    } catch (error) {
        if (this.generation === generation && this.routeRevision === revision && this._powerRevision === powerRevision) {
            this.bindings.showRouteUnavailable?.(`Không thể chọn trạm: ${error.message}`);
            this.bindings.setNavigationButtonState('Chọn trạm', false);
        }
        return false;
    }
}

export async function refreshStationPlans() {
    const request = planningRequest(this);
    if (!request) { this.renderStationsDrawer(); this.bindings.showRouteUnavailable?.('Chọn điểm A trên bản đồ để tìm trạm.'); return; }
    const generation = this.generation, power = this._powerRevision, route = this.routeRevision;
    const revision = ++this._drawerRevision;
    const after = this.chargingIntent === 'AT_DESTINATION' && !this.navigationStages?.passengerPassed;
    if (after && !this.passengerDestination) return;
    this.bindings.setAfterDestinationEnabled?.(!!this.passengerDestination && !this.navigationStages?.passengerPassed, !!this.passengerDestination);
    if (after) { this.postTripRecommendation = null; this.postTripCandidateDetails = null; }
    else { this.lastRecommendation = null; this.stationCandidateDetails = null; }
    this.renderStationsDrawer();
    try {
        const recommendation = await this.api.getRecommendation({ ...request, plan_mode: after ? 'AFTER_DESTINATION' : 'BEFORE_DESTINATION' });
        if (this.generation !== generation || this._powerRevision !== power || this.routeRevision !== route || this._drawerRevision !== revision) return;
        if (after) { this.postTripRecommendation = recommendation; this.postTripCandidateDetails = recommendation.candidate_details || null; }
        else { this.lastRecommendation = recommendation; this.stationCandidateDetails = recommendation.candidate_details || null; }
        this.renderStationsDrawer();
    } catch (error) {
        if (this.generation === generation && this._powerRevision === power && this.routeRevision === route && this._drawerRevision === revision) {
            this.renderStationsDrawer(); this.bindings.showRouteUnavailable?.(`Không thể đánh giá trạm: ${error.message}`);
        }
    }
}

export function renderStationPlans(filter = 'ALL') {
    const after = this.chargingIntent === 'AT_DESTINATION' && !!this.passengerDestination && !this.navigationStages?.passengerPassed;
    const activeRec = after ? this.postTripRecommendation : this.lastRecommendation;
    const activeCand = after ? this.postTripCandidateDetails : this.stationCandidateDetails;
    let stations = this.stations;
    if (filter === 'FAST_DC') stations = stations.filter(item => item.station_type === 'CHARGING_SWAP' || (item.station_type !== 'SWAP' && item.service_type !== 'BATTERY_SWAP'));
    if (filter === 'SWAP') stations = stations.filter(item => item.station_type === 'SWAP' || item.station_type === 'CHARGING_SWAP' || item.service_type === 'BATTERY_SWAP');
    const ranks = new Map();
    for (const item of activeRec?.ranked_candidates || []) ranks.set(item.station_id, Math.min(ranks.get(item.station_id) ?? Infinity, item.rank));
    stations = [...stations].sort((a,b) => (ranks.get(a.station_id) ?? Infinity) - (ranks.get(b.station_id) ?? Infinity));
    const html = renderDrawerStationsListHTML(stations, { activeRec, activeCand, serviceFilter: filter, isAtDest: after, dest: this.passengerDestination,
        topRecId: activeRec?.ranked_candidates?.[0]?.station_id, postTripStationId: this.postTripStation?.station_id });
    this.bindings.renderDrawer(html, stations.length, {
        navigate: data => this.navigateViaStationId(data.stationId, data.serviceType),
        setPostTrip: data => this.setPostTripStation(data.stationId, data.serviceType),
        zoom: data => this.map.map.flyTo([Number(data.lat), Number(data.lng)],16)
    });
}

export function recordWaypointProgress(controller, progress) {
    if (!controller.selectedStationPlan || !progress || progress.distanceMeters > 35 || (controller.navigationStages?.originalMode === 'BEFORE_DESTINATION' && controller.navigationStages.stationPassed)) return;
    const coords = controller.fullRouteCoords;
    let passedIndex = controller.lastPassedSegmentIndex;
    const endpoint = coords?.[passedIndex + 1];
    if (endpoint && progress.projPoint && Math.abs(endpoint[0] - progress.projPoint[0]) < 1e-7 && Math.abs(endpoint[1] - progress.projPoint[1]) < 1e-7) passedIndex++;
    controller.navigationStages ??= { originalMode: controller.selectedStationPlan.plan_mode, passengerPassed: false, stationPassed: false };
    for (const waypoint of controller.selectedStationPlan.waypoints || []) {
        if (passedIndex >= waypoint.geometry_index) {
            if (waypoint.role === 'PASSENGER_DESTINATION') controller.navigationStages.passengerPassed = true;
            if (waypoint.role === 'STATION') controller.navigationStages.stationPassed = true;
        }
    }
}
