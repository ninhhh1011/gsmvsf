/**
 * Main Application Coordinator for VinFast Green Mobility EV Recommendation Demo.
 */

import { ApiClient } from './api.js';
import { DemoMap } from './map.js';
import { DriverModeController } from './driver_mode.js';
import { TrajectoryReplayController } from './replay.js';
import { fetchVehicleCatalog } from './domain/vehicle-catalog.js';
import { FALLBACK_MODEL_SPECS } from './domain/vehicle_model.js';

class DemoApp {
    constructor() {
        this.api = new ApiClient();
        this.map = null;
        this.driverMode = null;
        this.replay = null;

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

            // Initialize Driver Mode Controller
            this.driverMode = new DriverModeController(this.api, this.map, {
                session: this.session
            });
            this.driverMode.setCatalogs(this.trips, this.vehicles, this.stations, this.scenarios, this.vehicleCatalog);
            await this.driverMode.init();
            window.driverMode = this.driverMode;

            // Link app.replay to driverMode.replay to maintain single replay instance
            this.replay = this.driverMode.replay;
            this.replay.init();

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
        try {
            this.vehicleCatalog = await fetchVehicleCatalog();
        } catch (error) {
            console.warn('[App] Vehicle catalog API unavailable; using fallback model specifications:', error);
            this.vehicleCatalog = Object.values(FALLBACK_MODEL_SPECS).map(spec => ({
                id: spec.vehicle_model,
                name: spec.display_name,
                battery_kwh: spec.usable_kwh,
                efficiency_kwh_per_km: spec.consumption_wh_km / 1000,
                vehicle_type: spec.vehicle_type,
                supported_services: [
                    ...(spec.charging_supported ? ['charging'] : []),
                    ...(spec.swap_supported ? ['battery_swap'] : [])
                ]
            }));
        }

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
            const specs = new Map(this.vehicleCatalog.map(item => [item.id, item]));
            this.vehicles = (vResult.value || []).map(vehicle => {
                const spec = specs.get(vehicle.vehicle_model);
                return spec ? {
                    ...vehicle,
                    vehicle_type: spec.vehicle_type,
                    usable_capacity_kwh: spec.battery_kwh,
                    consumption_wh_per_km: spec.efficiency_kwh_per_km * 1000,
                    charging_supported: spec.supported_services.includes('charging'),
                    swap_supported: spec.supported_services.includes('battery_swap')
                } : vehicle;
            });
        } else {
            errors.push(`Vehicles: ${vResult.reason?.message || 'load failed'}`);
            this.vehicles = [];
        }
        if (scResult.status === 'fulfilled') {
            this.scenarios = scResult.value || [];
        } else {
            console.warn(`[App] Scenarios unavailable: ${scResult.reason?.message || 'load failed'} — continuing without scenarios`);
            this.scenarios = [];
        }
        if (trResult.status === 'fulfilled') {
            this.trips = trResult.value || [];
        } else {
            console.warn(`[App] Trips unavailable: ${trResult.reason?.message || 'load failed'} — continuing without trips`);
            this.trips = [];
        }

        // Only throw if stations (critical) or vehicles fail; scenarios/trips degrade gracefully
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

        const banner = document.getElementById('backend-offline-banner');
        if (banner) {
            banner.style.display = apiHealthy ? 'none' : 'block';
        }
    }
}

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DemoApp();
    window.app.init();
});
