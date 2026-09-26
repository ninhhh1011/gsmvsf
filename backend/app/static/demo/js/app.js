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

        // Shared session context across all controllers
        this.session = {
            session_id: crypto.randomUUID(),
            driver_id: null,
            vehicle_id: null,
            vehicle_category: null,
            trip_id: null,
            trajectory_id: null
        };

        // Catalogs
        this.stations = [];
        this.vehicles = [];
        this.scenarios = [];
        this.trips = [];
    }

    async init() {
        try {
            // Initialize Map
            this.map = new DemoMap('map');

            // Load static JSON catalogs (throws on failure)
            await this.loadCatalogs();

            // Initial station plot
            this.map.renderStations(this.stations);

            // Technical View Controller (Phase 4)
            this.techView = new TechViewController(this.api, this.map);
            this.techView.init();
            window.techView = this.techView;

            // Initialize Controllers with state sync callback to Technical View
            // Debounce rapid updates from fast replay steps to prevent UI jank
            let syncDebounceTimer = null;
            const onStateUpdate = (data) => {
                clearTimeout(syncDebounceTimer);
                syncDebounceTimer = setTimeout(() => {
                    this.techView.syncState(data);
                }, 50); // 50ms debounce for rapid replay steps
            };

            this.driverMode = new DriverModeController(this.api, this.map, {
                onStateUpdate,
                session: this.session
            });
            this.driverMode.setCatalogs(this.trips, this.vehicles, this.stations, this.scenarios);
            await this.driverMode.init();
            window.driverMode = this.driverMode;

            this.simMode = new SimModeController(this.api, this.map, { onStateUpdate });
            this.simMode.setCatalogs(this.scenarios, this.vehicles, this.stations);
            this.simMode.init();

            // Link app.replay to driverMode.replay to maintain single replay instance
            this.replay = this.driverMode.replay;
            this.replay.init();

            // Bind Scenario Panel Toggle
            this.bindScenarioPanel();

            // Check if URL specifies Technical View or debug mode
            const isDebug = window.location.search.includes('debug=true');
            const isTechRoute = window.location.hash === '#technical' || window.location.pathname.includes('/demo/technical');

            const techBtn = document.getElementById('btn-open-tech-view');
            const simToggleBtn = document.getElementById('btn-toggle-sim-panel');
            const statusPills = document.getElementById('header-status-pills');
            const pipeline = document.getElementById('pipeline-indicator');

            if (isDebug || isTechRoute) {
                if (techBtn) techBtn.style.display = 'inline-flex';
                if (simToggleBtn) simToggleBtn.style.display = 'inline-flex';
                if (statusPills) statusPills.style.display = 'flex';
                if (pipeline) pipeline.style.display = 'flex';
            } else {
                if (techBtn) techBtn.style.display = 'none';
                if (simToggleBtn) simToggleBtn.style.display = 'none';
                if (statusPills) statusPills.style.display = 'none';
                if (pipeline) pipeline.style.display = 'none';
            }

            if (isTechRoute) {
                this.techView.open();
            }

            window.addEventListener('hashchange', () => {
                if (window.location.hash === '#technical') {
                    if (techBtn) techBtn.style.display = 'inline-flex';
                    if (simToggleBtn) simToggleBtn.style.display = 'inline-flex';
                    if (statusPills) statusPills.style.display = 'flex';
                    if (pipeline) pipeline.style.display = 'flex';
                    this.techView.open();
                } else if (this.techView.isOpen) {
                    this.techView.close();
                }
            });

            // Start Health Monitor
            await this.checkBackendHealth();
            setInterval(() => this.checkBackendHealth(), 15000);
        } catch (err) {
            console.error('Bootstrap failed:', err);
            this.showBootstrapError(`Initialization failed: ${err.message}`);
            throw err;
        }
    }

    async loadCatalogs() {
        const results = await Promise.allSettled([
            fetch('/demo/static/data/stations.json').then(r => r.json()),
            fetch('/demo/static/data/vehicles.json').then(r => r.json()),
            fetch('/demo/static/data/scenarios.json').then(r => r.json()),
            fetch('/demo/static/data/trips.json').then(r => r.json())
        ]);

        const [stResult, vResult, scResult, trResult] = results;

        // Check each catalog and report failures
        const errors = [];
        if (stResult.status === 'fulfilled') {
            this.stations = stResult.value || [];
            console.log('[App] Loaded stations:', this.stations.length, 'stations');
        } else {
            errors.push(`Stations: ${stResult.reason?.message || 'load failed'}`);
            this.stations = [];
        }
        if (vResult.status === 'fulfilled') {
            this.vehicles = vResult.value || [];
        } else {
            errors.push(`Vehicles: ${vResult.reason?.message || 'load failed'}`);
            this.vehicles = [];
        }
        if (scResult.status === 'fulfilled') {
            this.scenarios = scResult.value || [];
        } else {
            errors.push(`Scenarios: ${scResult.reason?.message || 'load failed'}`);
            this.scenarios = [];
        }
        if (trResult.status === 'fulfilled') {
            this.trips = trResult.value || [];
        } else {
            errors.push(`Trips: ${trResult.reason?.message || 'load failed'}`);
            this.trips = [];
        }

        if (errors.length > 0) {
            const msg = `Catalog load failed: ${errors.join('; ')}`;
            console.error(msg);
            this.showBootstrapError(msg);
            throw new Error(msg);
        }
    }

    showBootstrapError(message) {
        const existing = document.getElementById('bootstrap-error');
        if (existing) return;
        const errDiv = document.createElement('div');
        errDiv.id = 'bootstrap-error';
        errDiv.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#ef4444;color:white;padding:12px 20px;z-index:9999;font-family:sans-serif;font-size:14px;';
        errDiv.innerHTML = `<strong>Bootstrap Error:</strong> ${message}`;
        document.body.prepend(errDiv);
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

            if (time > 0 && time === maxTime) {
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
