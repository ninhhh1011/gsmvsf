/**
 * Main Application Coordinator for VinFast Green Mobility EV Recommendation Demo.
 */

import { ApiClient } from './api.js';
import { DemoMap } from './map.js';
import { DriverModeController } from './driver_mode.js';
import { SimModeController } from './sim_mode.js';
import { TrajectoryReplayController } from './replay.js';
import { TechViewController, classifySystemHealth } from './tech_view.js';

class DemoApp {
    constructor() {
        this.api = new ApiClient();
        this.map = null;
        this.driverMode = null;
        this.simMode = null;
        this.replay = null;
        this.techView = null;

        this.currentMode = 'driver'; // 'driver' | 'sim'

        // Catalogs
        this.stations = [];
        this.vehicles = [];
        this.scenarios = [];
        this.trips = [];
    }

    async init() {
        // Initialize Map
        this.map = new DemoMap('map');

        // Load static JSON catalogs
        await this.loadCatalogs();

        // Initial station plot
        this.map.renderStations(this.stations);

        // Technical View Controller (Phase 4)
        this.techView = new TechViewController(this.api, this.map);
        this.techView.init();
        window.techView = this.techView;

        // Initialize Controllers with state sync callback to Technical View
        const onStateUpdate = (data) => this.techView.syncState(data);

        this.driverMode = new DriverModeController(this.api, this.map, { onStateUpdate });
        this.driverMode.setCatalogs(this.trips, this.vehicles, this.stations);
        await this.driverMode.init();

        this.simMode = new SimModeController(this.api, this.map, { onStateUpdate });
        this.simMode.setCatalogs(this.scenarios, this.vehicles, this.stations);
        this.simMode.init();

        this.replay = new TrajectoryReplayController(this.api, this.map, {
            onStep: (stepData) => {
                if (stepData?.observation) {
                    this.techView.syncState({
                        driverLocation: {
                            driver_id: this.replay.driverId || 'REPLAY_DRIVER',
                            status: stepData.status || 'MATCHED',
                            trigger_reason: 'REPLAY_STEP',
                            raw_position: {
                                latitude: stepData.observation.latitude,
                                longitude: stepData.observation.longitude,
                                speed_kmh: stepData.observation.speed_kmh,
                                heading_deg: stepData.observation.heading_deg,
                                accuracy_m: stepData.observation.accuracy_m
                            },
                            matched_position: stepData.matched ? {
                                latitude: stepData.matched.latitude,
                                longitude: stepData.matched.longitude,
                                road_segment_id: stepData.matched.road_segment_id,
                                osm_way_id: stepData.matched.osm_way_id,
                                direction: stepData.matched.direction,
                                confidence: stepData.matched.confidence
                            } : null,
                            last_match_latency_ms: stepData.latency_ms
                        }
                    });
                }
            }
        });
        this.replay.init();

        // Bind Scenario Panel Toggle
        this.bindScenarioPanel();

        // Check if URL specifies Technical View
        if (window.location.hash === '#technical' || window.location.pathname.includes('/demo/technical')) {
            this.techView.open();
        }

        window.addEventListener('hashchange', () => {
            if (window.location.hash === '#technical') {
                this.techView.open();
            } else if (this.techView.isOpen) {
                this.techView.close();
            }
        });

        // Start Health Monitor
        await this.checkBackendHealth();
        setInterval(() => this.checkBackendHealth(), 15000);
    }

    async loadCatalogs() {
        try {
            const [stResp, vResp, scResp, trResp] = await Promise.all([
                fetch('/demo/static/data/stations.json').then(r => r.json()),
                fetch('/demo/static/data/vehicles.json').then(r => r.json()),
                fetch('/demo/static/data/scenarios.json').then(r => r.json()),
                fetch('/demo/static/data/trips.json').then(r => r.json())
            ]);

            this.stations = stResp || [];
            this.vehicles = vResp || [];
            this.scenarios = scResp || [];
            this.trips = trResp || [];
        } catch (err) {
            console.error('Failed to load catalogs:', err);
        }
    }

    /**
     * Toggle collapsible Scenario Explorer panel.
     * Driver Mode is always visible; Scenario Explorer is a collapsible panel below.
     */
    bindScenarioPanel() {
        const btnToggle = document.getElementById('btn-toggle-sim-panel');
        const btnCollapse = document.getElementById('btn-collapse-sim-panel');
        const simPanel = document.getElementById('sim-view-container');

        if (!btnToggle || !simPanel) return;

        // Open panel
        btnToggle?.addEventListener('click', () => {
            simPanel.style.display = 'block';
            btnToggle.style.display = 'none';
            this.map?.invalidateSize();
        });

        // Collapse panel
        btnCollapse?.addEventListener('click', () => {
            simPanel.style.display = 'none';
            btnToggle.style.display = 'inline-block';
            this.map?.invalidateSize();
        });
    }

    /**
     * Update the Week Pipeline indicator based on recommendation timings.
     * Active step is determined by the longest timing; completed steps are grayed.
     */
    updatePipelineIndicator(timingsMs) {
        const indicator = document.getElementById('pipeline-indicator');
        if (!indicator || !timingsMs) return;

        const steps = indicator.querySelectorAll('.pipeline-step');
        const timings = {
            1: timingsMs.location_resolution || 0,
            2: timingsMs.demand || 0,
            3: timingsMs.candidate_search || 0,
            4: timingsMs.ranking || 0,
            5: timingsMs.total || 0
        };

        const maxTime = Math.max(...Object.values(timings));

        steps.forEach(step => {
            const week = parseInt(step.dataset.week);
            const time = timings[week] || 0;

            // Reset classes
            step.classList.remove('active', 'completed');

            if (week === 5) {
                // W5 is always "current" when there's timing data
                step.classList.add('active');
            } else if (time > 0 && time === maxTime) {
                step.classList.add('active');
            } else if (time > 0) {
                step.classList.add('completed');
            }
        });
    }

    async checkBackendHealth() {
        const ghPill = document.getElementById('health-pill-gh');
        const dbPill = document.getElementById('health-pill-db');
        const apiPill = document.getElementById('health-pill-api');
        const redisPill = document.getElementById('health-pill-redis');

        let readiness = null;
        let apiHealthy = false;

        try {
            readiness = await this.api.getReadiness();
            apiHealthy = true;

            if (readiness.status === 'ready') {
                if (apiPill) { apiPill.className = 'pill-dot green'; apiPill.title = 'FastAPI: Online'; }
                if (ghPill) { ghPill.className = 'pill-dot green'; ghPill.title = 'GraphHopper: Healthy'; }
                if (dbPill) { dbPill.className = 'pill-dot green'; dbPill.title = 'PostGIS: Populated'; }
                if (redisPill) { redisPill.className = 'pill-dot green'; redisPill.title = 'Redis: Connected'; }
            } else {
                if (apiPill) { apiPill.className = 'pill-dot green'; apiPill.title = 'FastAPI: Online'; }
                if (ghPill) ghPill.className = readiness.graphhopper ? 'pill-dot green' : 'pill-dot red';
                if (dbPill) dbPill.className = readiness.postgis ? 'pill-dot green' : 'pill-dot red';
                if (redisPill) redisPill.className = readiness.redis ? 'pill-dot green' : 'pill-dot red';
            }
        } catch (err) {
            if (err?.detail && typeof err.detail === 'object') {
                // Backend 503 returned detailed dependency failure
                apiHealthy = true;
                readiness = err.detail;
                if (apiPill) apiPill.className = 'pill-dot green';
                if (ghPill) ghPill.className = readiness.graphhopper ? 'pill-dot green' : 'pill-dot red';
                if (dbPill) dbPill.className = readiness.postgis ? 'pill-dot green' : 'pill-dot red';
                if (redisPill) redisPill.className = readiness.redis ? 'pill-dot green' : 'pill-dot red';
            } else {
                // Complete API outage
                apiHealthy = false;
                if (apiPill) apiPill.className = 'pill-dot red';
                if (ghPill) ghPill.className = 'pill-dot gray';
                if (dbPill) dbPill.className = 'pill-dot gray';
                if (redisPill) redisPill.className = 'pill-dot gray';
            }
        }

        const classified = classifySystemHealth(readiness, apiHealthy);
        this.techView?.syncState({ health: classified });
    }
}

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DemoApp();
    window.app.init();
});
