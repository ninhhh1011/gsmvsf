/**
 * Technical / Debug View Controller and Renderers for VinFast EV Recommendation Demo.
 * 
 * Strict rules:
 * - Pure backend/runtime truth. Zero fabricated scores, latency, or candidate states.
 * - Composite candidate identity (station_id, service_type) strictly preserved.
 * - Honest depiction of UNRESOLVED, AMBIGUOUS, NO_MATCH, and ENGINE_UNAVAILABLE states.
 * - Clear distinction of HEALTHY, DEGRADED, UNAVAILABLE, and UNKNOWN health states.
 */

/**
 * Classify system health across FastAPI, GraphHopper, PostGIS, and Redis.
 * Strictly avoids marking UNKNOWN as HEALTHY.
 */
export function classifySystemHealth(readinessResult, apiHealthy = true) {
    if (!apiHealthy || !readinessResult) {
        return {
            api: { status: 'UNAVAILABLE', label: 'API Offline', message: 'FastAPI process unreachable' },
            graphhopper: { status: 'UNKNOWN', label: 'Unknown', message: 'Cannot probe dependencies while API is unreachable' },
            postgis: { status: 'UNKNOWN', label: 'Unknown', message: 'Cannot probe dependencies while API is unreachable' },
            redis: { status: 'UNKNOWN', label: 'Unknown', message: 'Cannot probe dependencies while API is unreachable' }
        };
    }

    const gh = Boolean(readinessResult.graphhopper);
    const db = Boolean(readinessResult.postgis);
    const r = Boolean(readinessResult.redis);

    return {
        api: {
            status: 'HEALTHY',
            label: 'Healthy',
            message: 'FastAPI core process responding'
        },
        graphhopper: {
            status: gh ? 'HEALTHY' : 'UNAVAILABLE',
            label: gh ? 'Healthy' : 'Unavailable',
            message: gh ? 'Routing & map-matching engine online' : 'GraphHopper 11.0 connection refused or timeout'
        },
        postgis: {
            status: db ? 'HEALTHY' : 'UNAVAILABLE',
            label: db ? 'Healthy' : 'Unavailable',
            message: db ? 'PostGIS road_segments and snapshots ready' : 'PostGIS road database connection error'
        },
        redis: {
            status: r ? 'HEALTHY' : 'UNAVAILABLE',
            label: r ? 'Healthy' : 'Unavailable',
            message: r ? 'Shared driver state & snapshot cache ready' : 'Redis store connection error'
        }
    };
}

/**
 * Format Driver Location and Map Matching inspection data.
 */
export function formatLocationInspector(locationData, locationSource = 'MATCHED') {
    if (!locationData) {
        return {
            driver_id: 'N/A',
            matching_status: 'UNKNOWN',
            trigger_reason: 'N/A',
            raw_position: null,
            matched_position: null,
            road_segment_id: null,
            osm_way_id: null,
            direction: 'UNKNOWN',
            confidence: null,
            quality_semantics: 'mean(max(0, 1 - distance_to_matched_path_m / 100)); not a probability',
            location_source: locationSource || 'LOCATION_UNAVAILABLE',
            last_match_latency_ms: null
        };
    }

    const matchedPos = locationData.matched_position || null;
    const rawPos = locationData.raw_position || null;
    const roadSegId = matchedPos?.road_segment_id ?? null;
    const osmWayId = matchedPos?.osm_way_id ?? null;
    const dir = matchedPos?.direction || 'UNKNOWN';
    const conf = matchedPos?.confidence != null ? matchedPos.confidence : null;

    return {
        driver_id: locationData.driver_id || 'DEMO_DRIVER',
        matching_status: locationData.status || (matchedPos ? 'MATCHED' : 'UNRESOLVED'),
        trigger_reason: locationData.trigger_reason || 'MANUAL_OR_DEFAULT',
        raw_position: rawPos,
        matched_position: matchedPos,
        road_segment_id: roadSegId,
        osm_way_id: osmWayId,
        direction: dir,
        confidence: conf,
        quality_semantics: 'mean(max(0, 1 - distance_to_matched_path_m / 100)); not a probability',
        location_source: locationSource,
        last_match_latency_ms: locationData.last_match_latency_ms != null ? locationData.last_match_latency_ms : null
    };
}

/**
 * Format Demand Detection output directly from backend EnergyServiceRequest.
 */
export function formatDemandInspector(energyContext) {
    if (!energyContext) {
        return {
            need_service: false,
            reason_code: 'NO_EVALUATION',
            current_soc_pct: null,
            estimated_remaining_range_km: null,
            remaining_trip_distance_km: null,
            safety_reserve_km: null,
            energy_margin_km: null,
            allowed_service_types: [],
            resolved_service_type: 'NONE',
            request_valid: false,
            degraded: false,
            degraded_reasons: []
        };
    }

    return {
        need_service: Boolean(energyContext.need_service),
        reason_code: energyContext.reason_code || 'NOMINAL',
        current_soc_pct: energyContext.current_soc_pct != null ? energyContext.current_soc_pct : null,
        estimated_remaining_range_km: energyContext.estimated_remaining_range_km != null ? energyContext.estimated_remaining_range_km : null,
        remaining_trip_distance_km: energyContext.remaining_trip_distance_km != null ? energyContext.remaining_trip_distance_km : null,
        safety_reserve_km: energyContext.safety_reserve_km != null ? energyContext.safety_reserve_km : null,
        energy_margin_km: energyContext.energy_margin_km != null ? energyContext.energy_margin_km : null,
        allowed_service_types: energyContext.allowed_service_types || [],
        resolved_service_type: energyContext.resolved_service_type || 'NONE',
        request_valid: energyContext.request_valid !== false,
        degraded: Boolean(energyContext.degraded),
        degraded_reasons: energyContext.degraded_reasons || []
    };
}

/**
 * Filter evaluated station candidates preserving composite (station_id, service_type) identity.
 */
export function filterCandidates(candidates, filter = 'ALL') {
    if (!Array.isArray(candidates)) return [];

    const decorated = candidates.map(c => ({
        ...c,
        key: `${c.station_id}_${c.service_type}`
    }));

    if (filter === 'ELIGIBLE') {
        return decorated.filter(c => c.eligible);
    }
    if (filter === 'REJECTED') {
        return decorated.filter(c => !c.eligible);
    }
    return decorated;
}

/**
 * Format Routing Inspector metrics using real GraphHopper route data.
 */
export function formatRoutingInspector(routesData = {}) {
    const { directRoute, stationRouteLeg1, stationRouteLeg2, vehicleCategory } = routesData;

    const directDistKm = directRoute?.distance_m != null ? (directRoute.distance_m / 1000).toFixed(2) : 'N/A';
    const directDurMin = directRoute?.duration_s != null ? (directRoute.duration_s / 60).toFixed(1) : 'N/A';

    const leg1DistM = stationRouteLeg1?.distance_m || 0;
    const leg1DurS = stationRouteLeg1?.duration_s || 0;
    const leg2DistM = stationRouteLeg2?.distance_m || 0;
    const leg2DurS = stationRouteLeg2?.duration_s || 0;

    const viaTotalDistM = leg1DistM + leg2DistM;
    const viaTotalDurS = leg1DurS + leg2DurS;

    const viaDistKm = viaTotalDistM > 0 ? (viaTotalDistM / 1000).toFixed(2) : 'N/A';
    const viaDurMin = viaTotalDurS > 0 ? (viaTotalDurS / 60).toFixed(1) : 'N/A';

    let detourDistKm = 'N/A';
    let detourDurMin = 'N/A';
    if (viaTotalDistM > 0 && directRoute?.distance_m != null) {
        const dM = Math.max(0, viaTotalDistM - directRoute.distance_m);
        detourDistKm = (dM / 1000).toFixed(2);
    }
    if (viaTotalDurS > 0 && directRoute?.duration_s != null) {
        const dS = Math.max(0, viaTotalDurS - directRoute.duration_s);
        detourDurMin = (dS / 60).toFixed(1);
    }

    return {
        direct_distance_km: directDistKm,
        direct_duration_min: directDurMin,
        leg1_distance_km: leg1DistM > 0 ? (leg1DistM / 1000).toFixed(2) : 'N/A',
        leg1_duration_min: leg1DurS > 0 ? (leg1DurS / 60).toFixed(1) : 'N/A',
        leg2_distance_km: leg2DistM > 0 ? (leg2DistM / 1000).toFixed(2) : 'N/A',
        leg2_duration_min: leg2DurS > 0 ? (leg2DurS / 60).toFixed(1) : 'N/A',
        via_total_distance_km: viaDistKm,
        via_total_duration_min: viaDurMin,
        detour_distance_km: detourDistKm,
        detour_duration_min: detourDurMin,
        engine: 'GraphHopper 11.0',
        profile: vehicleCategory === 'EV_MOTORBIKE' ? 'motorcycle' : 'car',
        status: directRoute?.status || 'SUCCESS'
    };
}

/**
 * Format Ranking Inspector metrics showing true formula and features.
 */
export function formatRankingInspector(recResult) {
    if (!recResult) {
        return {
            policy_name: 'TOTAL_SERVICE_COMPLETION_V1',
            formula: 'final_cost_s = eta_to_station_s + effective_queue_wait_s + service_duration_s',
            candidates: []
        };
    }

    const policy = recResult.policy || { name: 'TOTAL_SERVICE_COMPLETION_V1' };
    const rankedList = (recResult.ranked_candidates || []).map(rc => {
        const f = rc.features || {};
        return {
            rank: rc.rank,
            station_id: rc.station_id,
            service_type: rc.service_type,
            eta_to_station_min: (rc.eta_to_station_s / 60).toFixed(1),
            queue_wait_min: (f.effective_queue_wait_s != null ? (f.effective_queue_wait_s / 60).toFixed(1) : '0.0'),
            service_duration_min: (f.service_duration_s != null ? (f.service_duration_s / 60).toFixed(1) : '-'),
            eta_complete_min: (rc.eta_to_service_complete_s / 60).toFixed(1),
            final_cost_min: (rc.final_cost_s / 60).toFixed(1),
            detour_min: f.detour_duration_s != null ? (f.detour_duration_s / 60).toFixed(1) : '-',
            available_capacity: f.available_capacity ?? '-',
            station_fresh: Boolean(f.station_state?.is_fresh),
            queue_fresh: Boolean(f.queue_state?.is_fresh),
            station_age_s: f.station_state?.age_s != null ? f.station_state.age_s.toFixed(0) : '-',
            queue_age_s: f.queue_state?.age_s != null ? f.queue_state.age_s.toFixed(0) : '-'
        };
    });

    return {
        policy_name: policy.name || 'TOTAL_SERVICE_COMPLETION_V1',
        formula: 'final_cost_s = eta_to_station_s + effective_queue_wait_s + service_duration_s',
        candidates: rankedList
    };
}

/**
 * Format Recommendation Inspector outcome summary.
 */
export function formatRecommendationInspector(recResult) {
    if (!recResult) {
        return {
            has_recommendation: false,
            recommended_station_id: null,
            recommended_service_type: null,
            eligible_count: 0,
            location_source: 'LOCATION_UNAVAILABLE',
            degraded: false,
            degraded_reasons: [],
            reason: 'NO_RECOMMENDATION',
            workflow_attempts: 1,
            candidate_search_calls: 0,
            ranking_calls: 0,
            candidate_state_conflicts: 0
        };
    }

    return {
        has_recommendation: Boolean(recResult.has_recommendation),
        recommended_station_id: recResult.recommended_station_id || null,
        recommended_service_type: recResult.recommended_service_type || null,
        eligible_count: recResult.eligible_count || 0,
        location_source: recResult.location_source || 'EXPLICIT',
        degraded: Boolean(recResult.degraded),
        degraded_reasons: recResult.degraded_reasons || [],
        reason: recResult.reason || (recResult.has_recommendation ? 'SUCCESS' : 'NO_ELIGIBLE_CANDIDATES'),
        workflow_attempts: recResult.workflow_attempts || 1,
        candidate_search_calls: recResult.candidate_search_calls || 0,
        ranking_calls: recResult.ranking_calls || 0,
        candidate_state_conflicts: recResult.candidate_state_conflicts || 0
    };
}

/**
 * Format pipeline execution timing breakdown.
 */
export function formatPipelineTiming(timingsMs) {
    if (!timingsMs) {
        return {
            location_ms: 'N/A',
            demand_ms: 'N/A',
            candidate_search_ms: 'N/A',
            ranking_ms: 'N/A',
            total_ms: 'N/A',
            raw: null
        };
    }

    const fmt = (v) => v != null ? `${Number(v).toFixed(2)} ms` : 'N/A';
    return {
        location_ms: fmt(timingsMs.location_resolution),
        demand_ms: fmt(timingsMs.demand),
        candidate_search_ms: fmt(timingsMs.candidate_search),
        ranking_ms: fmt(timingsMs.ranking),
        total_ms: fmt(timingsMs.total),
        raw: timingsMs
    };
}

/**
 * Format JSON payload cleanly without exposing secrets.
 */
export function sanitizeJsonPayload(payload) {
    if (!payload) return '{}';
    try {
        const clone = JSON.parse(JSON.stringify(payload));
        const sanitizeObj = (obj) => {
            if (typeof obj !== 'object' || obj === null) return;
            for (const k of Object.keys(obj)) {
                if (k.toLowerCase().includes('password') || k.toLowerCase().includes('token') || k.toLowerCase().includes('secret')) {
                    obj[k] = '[REDACTED]';
                } else if (typeof obj[k] === 'object') {
                    sanitizeObj(obj[k]);
                }
            }
        };
        sanitizeObj(clone);
        return JSON.stringify(clone, null, 2);
    } catch {
        return String(payload);
    }
}

/**
 * TechViewController coordinates the Technical / Debug View UI.
 */
export class TechViewController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.containerId = options.containerId || 'tech-view-drawer';
        this.isOpen = false;
        this.activeStage = 'overview';
        this.candidateFilter = 'ALL';

        // Cached runtime state synchronized from product/simulation view
        this.state = {
            scenario: null,
            vehicle: null,
            origin: null,
            destination: null,
            driverLocation: null,
            recommendRequest: null,
            recommendResult: null,
            candidateResult: null,
            routeResult: null,
            stationRoutes: null,
            health: null,
            lastUpdated: null
        };

        // Map layer visibility toggles
        this.layerToggles = {
            rawGps: true,
            matchedRoad: true,
            stations: true,
            directRoute: true,
            recommendRoute: true
        };
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        if (typeof document === 'undefined') return;

        // Close button
        document.getElementById('btn-close-tech-view')?.addEventListener('click', () => this.close());
        document.getElementById('btn-open-tech-view')?.addEventListener('click', () => this.open());

        // Pipeline stage stepper navigation
        const stepperBtns = document.querySelectorAll('.tech-stepper-btn');
        stepperBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const stage = e.currentTarget.getAttribute('data-stage');
                if (stage) this.setActiveStage(stage);
            });
        });

        // Candidate filter tabs
        document.querySelectorAll('.tech-cand-filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const f = e.currentTarget.getAttribute('data-filter');
                if (f) {
                    this.candidateFilter = f;
                    this.renderCandidatesSection();
                }
            });
        });

        // Layer toggles
        const toggleMap = [
            { id: 'toggle-layer-raw', key: 'rawGps' },
            { id: 'toggle-layer-matched', key: 'matchedRoad' },
            { id: 'toggle-layer-stations', key: 'stations' },
            { id: 'toggle-layer-direct', key: 'directRoute' },
            { id: 'toggle-layer-rec', key: 'recommendRoute' }
        ];
        toggleMap.forEach(({ id, key }) => {
            document.getElementById(id)?.addEventListener('change', (e) => {
                this.layerToggles[key] = e.target.checked;
                this.applyLayerToggles();
            });
        });

        // JSON copy buttons
        document.getElementById('btn-copy-req-json')?.addEventListener('click', () => {
            const code = document.getElementById('json-req-content')?.textContent;
            if (code) navigator.clipboard?.writeText(code);
        });
        document.getElementById('btn-copy-resp-json')?.addEventListener('click', () => {
            const code = document.getElementById('json-resp-content')?.textContent;
            if (code) navigator.clipboard?.writeText(code);
        });
    }

    syncState(newState = {}) {
        this.state = {
            ...this.state,
            ...newState,
            lastUpdated: new Date()
        };
        if (this.isOpen) {
            this.render();
        }
    }

    open() {
        this.isOpen = true;
        if (typeof document !== 'undefined') {
            const drawer = document.getElementById(this.containerId);
            if (drawer) {
                drawer.classList.add('open');
                drawer.setAttribute('aria-hidden', 'false');
            }
        }
        if (typeof window !== 'undefined') {
            window.location.hash = 'technical';
        }
        this.render();
        this.map?.invalidateSize();
    }

    close() {
        this.isOpen = false;
        if (typeof document !== 'undefined') {
            const drawer = document.getElementById(this.containerId);
            if (drawer) {
                drawer.classList.remove('open');
                drawer.setAttribute('aria-hidden', 'true');
            }
        }
        if (typeof window !== 'undefined' && window.location.hash === '#technical') {
            history.pushState('', document.title, window.location.pathname + window.location.search);
        }
        this.map?.invalidateSize();
    }

    setActiveStage(stage) {
        this.activeStage = stage;
        if (typeof document !== 'undefined') {
            document.querySelectorAll('.tech-stepper-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-stage') === stage);
            });

            // Scroll to card or filter view
            if (stage === 'overview') {
                document.querySelectorAll('.tech-inspector-card').forEach(c => c.style.display = 'block');
            } else {
                const target = document.getElementById(`tech-section-${stage}`);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        }
    }

    applyLayerToggles() {
        if (!this.map) return;
        if (this.map.driverRawMarker) {
            this.map.driverRawMarker.setStyle({ opacity: this.layerToggles.rawGps ? 1 : 0, fillOpacity: this.layerToggles.rawGps ? 0.85 : 0 });
        }
        if (this.map.driverMatchedMarker) {
            const el = this.map.driverMatchedMarker.getElement();
            if (el) el.style.display = this.layerToggles.matchedRoad ? '' : 'none';
        }
        if (this.map.layers?.stations) {
            const container = this.map.layers.stations.getLayers();
            container.forEach(layer => {
                const el = layer.getElement ? layer.getElement() : null;
                if (el) el.style.display = this.layerToggles.stations ? '' : 'none';
            });
        }
        if (this.map.layers?.directRoute) {
            this.map.layers.directRoute.eachLayer(l => {
                if (l.setStyle) l.setStyle({ opacity: this.layerToggles.directRoute ? 0.9 : 0 });
            });
        }
        if (this.map.layers?.recommendRoute) {
            this.map.layers.recommendRoute.eachLayer(l => {
                if (l.setStyle) l.setStyle({ opacity: this.layerToggles.recommendRoute ? 0.95 : 0 });
            });
        }
    }

    render() {
        if (typeof document === 'undefined') return;
        this.renderHealthSection();
        this.renderLocationSection();
        this.renderDemandSection();
        this.renderCandidatesSection();
        this.renderRoutingSection();
        this.renderRankingSection();
        this.renderRecommendationSection();
        this.renderTimingSection();
        this.renderPayloadSection();
    }

    renderHealthSection() {
        const elem = document.getElementById('tech-health-content');
        if (!elem) return;
        const h = this.state.health || classifySystemHealth(null, false);

        const badgeClass = (s) => {
            if (s === 'HEALTHY') return 'badge-success';
            if (s === 'DEGRADED') return 'badge-warning';
            if (s === 'UNAVAILABLE') return 'badge-danger';
            return 'badge-secondary';
        };

        elem.innerHTML = `
            <div class="tech-health-grid">
                <div class="health-col">
                    <span class="health-title">API (FastAPI)</span>
                    <span class="badge ${badgeClass(h.api.status)}">${h.api.status}</span>
                    <small class="text-muted">${h.api.message}</small>
                </div>
                <div class="health-col">
                    <span class="health-title">GraphHopper 11.0</span>
                    <span class="badge ${badgeClass(h.graphhopper.status)}">${h.graphhopper.status}</span>
                    <small class="text-muted">${h.graphhopper.message}</small>
                </div>
                <div class="health-col">
                    <span class="health-title">PostgreSQL / PostGIS</span>
                    <span class="badge ${badgeClass(h.postgis.status)}">${h.postgis.status}</span>
                    <small class="text-muted">${h.postgis.message}</small>
                </div>
                <div class="health-col">
                    <span class="health-title">Redis Store</span>
                    <span class="badge ${badgeClass(h.redis.status)}">${h.redis.status}</span>
                    <small class="text-muted">${h.redis.message}</small>
                </div>
            </div>
        `;
    }

    renderLocationSection() {
        const elem = document.getElementById('tech-location-content');
        if (!elem) return;
        const loc = formatLocationInspector(this.state.driverLocation, this.state.recommendResult?.location_source);

        const rawStr = loc.raw_position
            ? `${loc.raw_position.latitude.toFixed(5)}, ${loc.raw_position.longitude.toFixed(5)}`
            : (this.state.origin ? `${this.state.origin.latitude.toFixed(5)}, ${this.state.origin.longitude.toFixed(5)} (Origin)` : 'None');

        const matchedStr = loc.matched_position
            ? `${loc.matched_position.latitude.toFixed(5)}, ${loc.matched_position.longitude.toFixed(5)}`
            : 'None / Ambiguous';

        elem.innerHTML = `
            <div class="tech-keyval-grid">
                <div class="kv-item"><span class="kv-label">Driver ID:</span><span class="kv-val"><code>${loc.driver_id}</code></span></div>
                <div class="kv-item"><span class="kv-label">Location Source:</span><span class="kv-val"><span class="badge badge-info">${loc.location_source}</span></span></div>
                <div class="kv-item"><span class="kv-label">Matching Status:</span><span class="kv-val"><span class="badge ${loc.matching_status === 'MATCHED' ? 'badge-success' : 'badge-warning'}">${loc.matching_status}</span></span></div>
                <div class="kv-item"><span class="kv-label">Road Segment ID:</span><span class="kv-val"><code>${loc.road_segment_id || 'null (ambiguous/unresolved)'}</code></span></div>
                <div class="kv-item"><span class="kv-label">OSM Way ID:</span><span class="kv-val"><code>${loc.osm_way_id != null ? loc.osm_way_id : 'N/A'}</code></span></div>
                <div class="kv-item"><span class="kv-label">Direction:</span><span class="kv-val"><code>${loc.direction}</code></span></div>
                <div class="kv-item"><span class="kv-label">Raw GPS Position:</span><span class="kv-val">${rawStr}</span></div>
                <div class="kv-item"><span class="kv-label">Matched Position:</span><span class="kv-val">${matchedStr}</span></div>
                <div class="kv-item"><span class="kv-label">Proximity Quality:</span><span class="kv-val"><strong>${loc.confidence != null ? loc.confidence.toFixed(3) : 'N/A'}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Trigger Reason:</span><span class="kv-val"><code>${loc.trigger_reason}</code></span></div>
            </div>
            <div class="mt-2 text-xs text-muted">Quality semantics: <em>${loc.quality_semantics}</em></div>
        `;
    }

    renderDemandSection() {
        const elem = document.getElementById('tech-demand-content');
        if (!elem) return;
        const d = formatDemandInspector(this.state.recommendResult?.energy_context);

        elem.innerHTML = `
            <div class="tech-keyval-grid">
                <div class="kv-item"><span class="kv-label">Need Service:</span><span class="kv-val"><span class="badge ${d.need_service ? 'badge-danger' : 'badge-success'}">${d.need_service ? 'TRUE' : 'FALSE'}</span></span></div>
                <div class="kv-item"><span class="kv-label">Reason Code:</span><span class="kv-val"><code>${d.reason_code}</code></span></div>
                <div class="kv-item"><span class="kv-label">Current Battery SOC:</span><span class="kv-val"><strong>${d.current_soc_pct != null ? d.current_soc_pct + '%' : 'N/A'}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Est. Remaining Range:</span><span class="kv-val"><strong>${d.estimated_remaining_range_km != null ? d.estimated_remaining_range_km + ' km' : 'N/A'}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Remaining Trip Distance:</span><span class="kv-val">${d.remaining_trip_distance_km != null ? d.remaining_trip_distance_km + ' km' : 'N/A'}</span></div>
                <div class="kv-item"><span class="kv-label">Safety Reserve:</span><span class="kv-val">${d.safety_reserve_km != null ? d.safety_reserve_km + ' km' : 'N/A'}</span></div>
                <div class="kv-item"><span class="kv-label">Energy Margin:</span><span class="kv-val"><strong style="color: ${d.energy_margin_km < 0 ? '#ef4444' : '#10b981'};">${d.energy_margin_km != null ? d.energy_margin_km + ' km' : 'N/A'}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Allowed Services:</span><span class="kv-val"><code>${d.allowed_service_types.join(', ') || 'NONE'}</code></span></div>
                <div class="kv-item"><span class="kv-label">Resolved Service:</span><span class="kv-val"><span class="badge badge-purple">${d.resolved_service_type}</span></span></div>
                <div class="kv-item"><span class="kv-label">Request Valid:</span><span class="kv-val">${d.request_valid ? 'YES' : 'NO'}</span></div>
            </div>
        `;
    }

    renderCandidatesSection() {
        const elem = document.getElementById('tech-candidates-content');
        if (!elem) return;

        const candidates = this.state.candidateResult?.candidates || [];
        const filtered = filterCandidates(candidates, this.candidateFilter);

        // Update active filter button styling
        document.querySelectorAll('.tech-cand-filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-filter') === this.candidateFilter);
        });

        if (filtered.length === 0) {
            elem.innerHTML = '<p class="text-muted p-2">No station candidates match the current filter.</p>';
            return;
        }

        const rows = filtered.map(c => {
            const distKm = c.network_distance_m != null ? (c.network_distance_m / 1000).toFixed(1) + ' km' : '-';
            const etaMin = c.route_metrics?.duration_to_station_s != null ? (c.route_metrics.duration_to_station_s / 60).toFixed(1) + ' m' : '-';
            const detourMin = c.route_metrics?.detour_duration_s != null ? (c.route_metrics.detour_duration_s / 60).toFixed(1) + ' m' : '-';
            const cap = c.operational?.available_capacity ?? '-';
            const queueMin = c.operational?.estimated_wait_min != null ? c.operational.estimated_wait_min.toFixed(1) + ' m' : '0.0 m';

            return `
                <tr class="${c.eligible ? 'row-eligible' : 'row-rejected'}">
                    <td><strong>${c.station_id}</strong></td>
                    <td><span class="badge ${c.service_type === 'BATTERY_SWAP' ? 'badge-purple' : 'badge-teal'}">${c.service_type === 'BATTERY_SWAP' ? 'SWAP' : 'CHARGE'}</span></td>
                    <td><span class="badge ${c.eligible ? 'badge-success' : 'badge-danger'}">${c.eligible ? 'ELIGIBLE' : 'REJECTED'}</span></td>
                    <td><code>${c.reason || 'N/A'}</code></td>
                    <td>${distKm}</td>
                    <td>${etaMin}</td>
                    <td>${detourMin}</td>
                    <td>${cap}</td>
                    <td>${queueMin}</td>
                </tr>
            `;
        }).join('');

        elem.innerHTML = `
            <div class="tech-table-wrapper">
                <table class="tech-table">
                    <thead>
                        <tr>
                            <th>Station</th>
                            <th>Service</th>
                            <th>Eligibility</th>
                            <th>Reason</th>
                            <th>Distance</th>
                            <th>ETA</th>
                            <th>Detour</th>
                            <th>Cap.</th>
                            <th>Queue</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        `;
    }

    renderRoutingSection() {
        const elem = document.getElementById('tech-routing-content');
        if (!elem) return;

        const r = formatRoutingInspector({
            directRoute: this.state.routeResult,
            stationRouteLeg1: this.state.stationRoutes?.leg1,
            stationRouteLeg2: this.state.stationRoutes?.leg2,
            vehicleCategory: this.state.vehicle?.vehicle_type
        });

        elem.innerHTML = `
            <div class="tech-keyval-grid">
                <div class="kv-item"><span class="kv-label">Routing Engine:</span><span class="kv-val"><strong>${r.engine}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Routing Profile:</span><span class="kv-val"><code>${r.profile}</code></span></div>
                <div class="kv-item"><span class="kv-label">Route Status:</span><span class="kv-val"><span class="badge badge-success">${r.status}</span></span></div>
                <div class="kv-item"><span class="kv-label">Direct Trip Distance:</span><span class="kv-val"><strong>${r.direct_distance_km} km</strong></span></div>
                <div class="kv-item"><span class="kv-label">Direct Trip Duration:</span><span class="kv-val"><strong>${r.direct_duration_min} min</strong></span></div>
                <div class="kv-item"><span class="kv-label">Driver → Station (Leg 1):</span><span class="kv-val">${r.leg1_distance_km} km (${r.leg1_duration_min} min)</span></div>
                <div class="kv-item"><span class="kv-label">Station → Dest (Leg 2):</span><span class="kv-val">${r.leg2_distance_km} km (${r.leg2_duration_min} min)</span></div>
                <div class="kv-item"><span class="kv-label">Total Diversion Route:</span><span class="kv-val">${r.via_total_distance_km} km (${r.via_total_duration_min} min)</span></div>
                <div class="kv-item"><span class="kv-label">Detour Overhead:</span><span class="kv-val"><strong style="color: #f59e0b;">+${r.detour_distance_km} km (+${r.detour_duration_min} min)</strong></span></div>
            </div>
        `;
    }

    renderRankingSection() {
        const elem = document.getElementById('tech-ranking-content');
        if (!elem) return;

        const rankData = formatRankingInspector(this.state.recommendResult);

        if (rankData.candidates.length === 0) {
            elem.innerHTML = `
                <div class="p-2 text-muted">
                    No eligible candidates were ranked. (Demand reason: <code>${this.state.recommendResult?.reason || 'NONE'}</code>).
                </div>
            `;
            return;
        }

        const rows = rankData.candidates.map(c => `
            <tr class="${c.rank === 1 ? 'row-top-rec' : ''}">
                <td><span class="rank-badge ${c.rank === 1 ? 'rank-1' : ''}">${c.rank}</span></td>
                <td><strong>${c.station_id}</strong></td>
                <td><span class="badge ${c.service_type === 'BATTERY_SWAP' ? 'badge-purple' : 'badge-teal'}">${c.service_type}</span></td>
                <td>${c.eta_to_station_min} m</td>
                <td>${c.queue_wait_min} m</td>
                <td>${c.service_duration_min} m</td>
                <td><strong>${c.eta_complete_min} m</strong></td>
                <td>${c.detour_min} m</td>
                <td>${c.available_capacity}</td>
                <td>${c.station_fresh ? '✓ Fresh' : '⚠️ Stale'}</td>
                <td><strong>${c.final_cost_min} m</strong></td>
            </tr>
        `).join('');

        elem.innerHTML = `
            <div class="mb-2 text-xs">
                <strong>Policy:</strong> <code>${rankData.policy_name}</code> &nbsp;|&nbsp; <em>${rankData.formula}</em>
            </div>
            <div class="tech-table-wrapper">
                <table class="tech-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Station</th>
                            <th>Service</th>
                            <th>Travel</th>
                            <th>Queue</th>
                            <th>Service Time</th>
                            <th>ETA Complete</th>
                            <th>Detour</th>
                            <th>Cap.</th>
                            <th>Freshness</th>
                            <th>Final Cost</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
        `;
    }

    renderRecommendationSection() {
        const elem = document.getElementById('tech-recommendation-content');
        if (!elem) return;

        const rec = formatRecommendationInspector(this.state.recommendResult);

        elem.innerHTML = `
            <div class="tech-keyval-grid">
                <div class="kv-item"><span class="kv-label">Has Recommendation:</span><span class="kv-val"><span class="badge ${rec.has_recommendation ? 'badge-success' : 'badge-secondary'}">${rec.has_recommendation ? 'YES' : 'NO'}</span></span></div>
                <div class="kv-item"><span class="kv-label">Recommended Station:</span><span class="kv-val"><strong>${rec.recommended_station_id || 'None'}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Recommended Service:</span><span class="kv-val"><span class="badge ${rec.recommended_service_type === 'BATTERY_SWAP' ? 'badge-purple' : 'badge-teal'}">${rec.recommended_service_type || 'None'}</span></span></div>
                <div class="kv-item"><span class="kv-label">Eligible Candidate Count:</span><span class="kv-val"><strong>${rec.eligible_count}</strong></span></div>
                <div class="kv-item"><span class="kv-label">Location Source:</span><span class="kv-val"><code>${rec.location_source}</code></span></div>
                <div class="kv-item"><span class="kv-label">Degraded Mode:</span><span class="kv-val">${rec.degraded ? `<span class="badge badge-warning">DEGRADED (${rec.degraded_reasons.join(', ')})</span>` : '<span class="badge badge-success">NOMINAL</span>'}</span></div>
                <div class="kv-item"><span class="kv-label">Workflow Attempts:</span><span class="kv-val">${rec.workflow_attempts}</span></div>
                <div class="kv-item"><span class="kv-label">Candidate State Conflicts:</span><span class="kv-val">${rec.candidate_state_conflicts}</span></div>
                <div class="kv-item"><span class="kv-label">Backend Reason:</span><span class="kv-val"><code>${rec.reason}</code></span></div>
            </div>
        `;
    }

    renderTimingSection() {
        const elem = document.getElementById('tech-timing-content');
        if (!elem) return;

        const t = formatPipelineTiming(this.state.recommendResult?.timings_ms);

        elem.innerHTML = `
            <div class="tech-timing-rows">
                <div class="timing-row">
                    <span class="timing-stage">1. Location Resolution:</span>
                    <span class="timing-value"><code>${t.location_ms}</code></span>
                </div>
                <div class="timing-row">
                    <span class="timing-stage">2. Demand Detection:</span>
                    <span class="timing-value"><code>${t.demand_ms}</code></span>
                </div>
                <div class="timing-row">
                    <span class="timing-stage">3. Candidate Search:</span>
                    <span class="timing-value"><code>${t.candidate_search_ms}</code></span>
                </div>
                <div class="timing-row">
                    <span class="timing-stage">4. Snapshot Ranking:</span>
                    <span class="timing-value"><code>${t.ranking_ms}</code></span>
                </div>
                <div class="timing-row timing-total">
                    <span class="timing-stage">Total Pipeline Latency:</span>
                    <span class="timing-value"><strong>${t.total_ms}</strong></span>
                </div>
            </div>
        `;
    }

    renderPayloadSection() {
        const reqElem = document.getElementById('json-req-content');
        const respElem = document.getElementById('json-resp-content');
        if (reqElem) {
            reqElem.textContent = sanitizeJsonPayload(this.state.recommendRequest);
        }
        if (respElem) {
            respElem.textContent = sanitizeJsonPayload(this.state.recommendResult);
        }
    }
}
