/**
 * Main Application Coordinator for VinFast Green Mobility EV Recommendation Demo.
 */

import { ApiClient } from './api.js';
import { DemoMap } from './map.js';
import { DriverModeController } from './driver_mode.js';
import { SimModeController } from './sim_mode.js';
import { TrajectoryReplayController } from './replay.js';

class DemoApp {
    constructor() {
        this.api = new ApiClient();
        this.map = null;
        this.driverMode = null;
        this.simMode = null;
        this.replay = null;

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

        // Initialize Controllers
        this.driverMode = new DriverModeController(this.api, this.map);
        this.driverMode.setCatalogs(this.trips, this.vehicles, this.stations);
        await this.driverMode.init();

        this.simMode = new SimModeController(this.api, this.map);
        this.simMode.setCatalogs(this.scenarios, this.vehicles, this.stations);
        this.simMode.init();

        this.replay = new TrajectoryReplayController(this.api, this.map, {
            onStep: (stepData) => {
                // When replay makes a match, optional hook
            }
        });
        this.replay.init();

        // Bind Mode Switcher
        this.bindModeSwitcher();

        // Start Health Monitor
        this.checkBackendHealth();
        setInterval(() => this.checkBackendHealth(), 15000);
    }

    async loadCatalogs() {
        try {
            const [stResp, vResp, scResp, trResp] = await Promise.all([
                fetch('./static/data/stations.json').then(r => r.json()),
                fetch('./static/data/vehicles.json').then(r => r.json()),
                fetch('./static/data/scenarios.json').then(r => r.json()),
                fetch('./static/data/trips.json').then(r => r.json())
            ]);

            this.stations = stResp || [];
            this.vehicles = vResp || [];
            this.scenarios = scResp || [];
            this.trips = trResp || [];
        } catch (err) {
            console.error('Failed to load catalogs:', err);
        }
    }

    bindModeSwitcher() {
        const btnDriver = document.getElementById('tab-driver-mode');
        const btnSim = document.getElementById('tab-sim-mode');
        const driverView = document.getElementById('driver-view-container');
        const simView = document.getElementById('sim-view-container');

        btnDriver?.addEventListener('click', () => {
            this.currentMode = 'driver';
            btnDriver.classList.add('active');
            btnSim.classList.remove('active');
            driverView.style.display = 'block';
            simView.style.display = 'none';
            this.map.invalidateSize();
        });

        btnSim?.addEventListener('click', () => {
            this.currentMode = 'sim';
            btnSim.classList.add('active');
            btnDriver.classList.remove('active');
            driverView.style.display = 'none';
            simView.style.display = 'block';
            this.map.invalidateSize();
        });
    }

    async checkBackendHealth() {
        const ghPill = document.getElementById('health-pill-gh');
        const dbPill = document.getElementById('health-pill-db');
        const apiPill = document.getElementById('health-pill-api');

        try {
            const readiness = await this.api.getReadiness();
            if (readiness.status === 'ready') {
                if (apiPill) { apiPill.className = 'pill-dot green'; apiPill.title = 'FastAPI: Online'; }
                if (ghPill) { ghPill.className = 'pill-dot green'; ghPill.title = 'GraphHopper: Healthy'; }
                if (dbPill) { dbPill.className = 'pill-dot green'; dbPill.title = 'PostGIS: Populated'; }
            } else {
                if (ghPill) ghPill.className = readiness.graphhopper ? 'pill-dot green' : 'pill-dot red';
                if (dbPill) dbPill.className = readiness.postgis ? 'pill-dot green' : 'pill-dot red';
            }
        } catch (err) {
            if (apiPill) apiPill.className = 'pill-dot red';
            if (ghPill) ghPill.className = 'pill-dot gray';
            if (dbPill) dbPill.className = 'pill-dot gray';
        }
    }
}

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new DemoApp();
    window.app.init();
});
