/**
 * Trajectory Replay Controller for VinFast EV Recommendation Demo.
 * 
 * Replays real GPS observations via the backend realtime endpoint.
 * Strict rule: Request-driven client replay; no backend streaming or websocket.
 */

export class TrajectoryReplayController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.options = options;

        // Use shared session context for driver_id (set by DriverModeController.startTrip)
        this.session = options.session || {
            session_id: crypto.randomUUID(),
            driver_id: null,
            vehicle_id: null,
            vehicle_category: null,
            trip_id: null,
            trajectory_id: null
        };

        this.observations = [];
        this.currentIndex = 0;
        this.isPlaying = false;
        this.intervalId = null;
        this.speedMultiplier = 5; // default 5x

        this.onStep = options.onStep || (() => {});
    }

    /** Get current driver ID from shared session */
    get driverId() {
        return this.session.driver_id || `replay_${Date.now().toString(36)}`;
    }

    init() {
        this.bindEvents();
    }

    bindEvents() {
        document.getElementById('btn-load-trajectory')?.addEventListener('click', () => {
            const trjId = document.getElementById('select-trajectory')?.value || 'TRJ0001';
            this.loadTrajectory(trjId);
        });

        document.getElementById('btn-replay-play')?.addEventListener('click', () => this.play());
        document.getElementById('btn-replay-pause')?.addEventListener('click', () => this.pause());
        document.getElementById('btn-replay-step')?.addEventListener('click', () => this.step());
        document.getElementById('btn-replay-reset')?.addEventListener('click', () => this.reset());

        document.getElementById('select-replay-speed')?.addEventListener('change', (e) => {
            this.speedMultiplier = parseInt(e.target.value, 10) || 1;
            if (this.isPlaying) {
                this.pause();
                this.play();
            }
        });
    }

    async loadTrajectory(trajectoryId) {
        this.reset();
        const statusElem = document.getElementById('replay-status');
        if (statusElem) statusElem.textContent = `Loading ${trajectoryId}...`;

        try {
            this.observations = await this.api.getTrajectory(trajectoryId);
            if (statusElem) statusElem.textContent = `Loaded ${this.observations.length} observations`;

            const progressElem = document.getElementById('replay-progress');
            if (progressElem) progressElem.textContent = `0 / ${this.observations.length}`;

            // Plot all points faintly on map
            const coords = this.observations.map(o => [o.latitude, o.longitude]);
            if (coords.length > 0) {
                L.polyline(coords, {
                    color: '#94a3b8',
                    weight: 2,
                    opacity: 0.5,
                    dashArray: '4, 4'
                }).addTo(this.map.layers.markers);
                this.map.fitBoundsToActive(coords.map(c => L.latLng(c[0], c[1])));
            }
        } catch (err) {
            console.error('Failed to load trajectory:', err);
            if (statusElem) statusElem.textContent = `Error: ${err.message}`;
        }
    }

    async step() {
        // Guard: don't queue steps during autoplay (prevents race condition)
        if (this.isPlaying) return;

        if (this.currentIndex >= this.observations.length) {
            this.pause();
            const statusElem = document.getElementById('replay-status');
            if (statusElem) statusElem.textContent = 'Trajectory Replay Complete';
            return;
        }

        const obs = this.observations[this.currentIndex];
        this.currentIndex++;

        const progressElem = document.getElementById('replay-progress');
        if (progressElem) {
            progressElem.textContent = `${this.currentIndex} / ${this.observations.length}`;
        }

        try {
            // Build observation payload with vehicle metadata from session
            const observationPayload = {
                latitude: obs.latitude,
                longitude: obs.longitude,
                timestamp: obs.timestamp,
                speed_kmh: obs.speed_kmh,
                heading_deg: obs.heading_deg,
                vehicle_id: this.session.vehicle_id,
                vehicle_category: this.session.vehicle_category
            };

            // Ingest to Week 1 endpoint
            const locResp = await this.api.ingestDriverLocation(this.driverId, observationPayload);

            // Update map
            const rawPos = { latitude: obs.latitude, longitude: obs.longitude };
            const matchedPos = locResp.matched_position ? {
                latitude: locResp.matched_position.latitude,
                longitude: locResp.matched_position.longitude,
                road_segment_id: locResp.matched_position.road_segment_id,
                direction: locResp.matched_position.direction,
                confidence: locResp.matched_position.confidence
            } : null;

            this.map.renderDriver(rawPos, matchedPos, obs.heading_deg);

            const statusElem = document.getElementById('replay-status');
            if (statusElem) {
                statusElem.innerHTML = `
                    State: <b>${locResp.status}</b> · Trigger: <code>${locResp.trigger_reason || 'NONE'}</code> · Matches: <b>${locResp.total_match_calls}</b>
                `;
            }

            this.onStep({ obs, locResp, currentIndex: this.currentIndex });
        } catch (err) {
            console.warn('Replay step error:', err);
        }
    }

    play() {
        if (this.isPlaying) return;
        this.isPlaying = true;

        const baseIntervalMs = 500;
        const interval = Math.max(20, Math.round(baseIntervalMs / this.speedMultiplier));

        this.intervalId = setInterval(() => this.step(), interval);

        const playBtn = document.getElementById('btn-replay-play');
        const pauseBtn = document.getElementById('btn-replay-pause');
        if (playBtn) playBtn.disabled = true;
        if (pauseBtn) pauseBtn.disabled = false;
    }

    pause() {
        this.isPlaying = false;
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }

        const playBtn = document.getElementById('btn-replay-play');
        const pauseBtn = document.getElementById('btn-replay-pause');
        if (playBtn) playBtn.disabled = false;
        if (pauseBtn) pauseBtn.disabled = true;
    }

    reset() {
        this.pause();
        this.currentIndex = 0;
        this.api.resetDriverLocation(this.driverId).catch(() => {});
        this.map.layers.driver.clearLayers();
        this.map.layers.markers.clearLayers();

        const progressElem = document.getElementById('replay-progress');
        if (progressElem) progressElem.textContent = `0 / ${this.observations.length}`;
        const statusElem = document.getElementById('replay-status');
        if (statusElem) statusElem.textContent = 'Replay Ready';
    }

    /** Clear session context (called by DriverModeController on reset/cancel). */
    clearSession() {
        // Reset driver location on backend
        this.api.resetDriverLocation(this.session.driver_id).catch(() => {});
    }

    /** Returns true when all observations have been replayed. */
    isReplayComplete() {
        return this.observations.length > 0 && this.currentIndex >= this.observations.length;
    }

    /** Returns a human-readable progress string. */
    getProgressText() {
        if (this.observations.length === 0) return 'No trajectory loaded';
        return `${this.currentIndex} / ${this.observations.length} obs`;
    }

    /** Returns the current raw position (from last observation) without re-fetching. */
    getCurrentRawPosition() {
        if (this.currentIndex > 0 && this.currentIndex <= this.observations.length) {
            const obs = this.observations[this.currentIndex - 1];
            return { latitude: obs.latitude, longitude: obs.longitude };
        }
        return null;
    }
}
