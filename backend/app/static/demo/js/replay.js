/**
 * Trajectory Replay Controller for VinFast EV Recommendation Demo.
 * 
 * Replays real Dataset V1 GPS observations via /api/v1/drivers/{id}/location.
 * Strict rule: Request-driven client replay; no backend streaming or websocket.
 */

export class TrajectoryReplayController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;

        this.driverId = `replay_${Date.now().toString(36)}`;
        this.observations = [];
        this.currentIndex = 0;
        this.isPlaying = false;
        this.intervalId = null;
        this.speedMultiplier = 5; // default 5x

        this.onStep = options.onStep || (() => {});
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
            // Ingest to Week 1 endpoint
            const locResp = await this.api.ingestDriverLocation(this.driverId, {
                latitude: obs.latitude,
                longitude: obs.longitude,
                timestamp: obs.timestamp,
                speed_kmh: obs.speed_kmh,
                heading_deg: obs.heading_deg
            });

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
}
