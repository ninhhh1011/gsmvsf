/**
 * Trajectory Replay Controller for VinFast EV Recommendation Demo.
 * 
 * Strict rules:
 * - Request-driven sequential async state machine; no setInterval overlap.
 * - Single in-flight step at any time.
 * - Generation tracking prevents stale responses after pause/reset/switch.
 * - Progress index only increments after confirmed backend acceptance and evaluation.
 * - Timestamp is strictly historical observation timestamp in replay.
 */

export const ReplayState = {
    IDLE: 'IDLE',
    LOADING: 'LOADING',
    READY: 'READY',
    PLAYING: 'PLAYING',
    PAUSED: 'PAUSED',
    ERROR: 'ERROR',
    COMPLETE: 'COMPLETE'
};

function getElem(id) {
    if (typeof document === 'undefined') return null;
    return document.getElementById(id);
}

export class TrajectoryReplayController {
    constructor(apiClient, mapEngine, options = {}) {
        this.api = apiClient;
        this.map = mapEngine;
        this.options = options;

        // Shared session context
        this.session = options.session || {
            session_id: crypto.randomUUID(),
            driver_id: null,
            vehicle_id: null,
            vehicle_category: null,
            trip_id: null,
            trajectory_id: null
        };

        // State Machine
        this.state = ReplayState.IDLE;
        this.generation = 1;
        this.isStepInProgress = false;
        this.stepTimer = null;

        // Progress
        this.observations = [];
        this.currentIndex = 0;
        this.speedMultiplier = 5; // default 5x

        // Callbacks
        this.onStep = options.onStep || (async () => {});
        this.onStateChange = options.onStateChange || (() => {});
    }

    /** Get current driver ID from shared session */
    get driverId() {
        return this.session.driver_id || `replay_${Date.now().toString(36)}`;
    }

    /** Legacy compatibility getter for isPlaying */
    get isPlaying() {
        return this.state === ReplayState.PLAYING;
    }

    init() {
        this.bindEvents();
        this.updateControlsUI();
    }

    setState(newState) {
        this.state = newState;
        this.updateControlsUI();
        this.onStateChange(this.state);
    }

    bindEvents() {
        if (typeof document === 'undefined') return;

        getElem('btn-load-trajectory')?.addEventListener('click', () => {
            const trjId = getElem('select-trajectory')?.value || 'TRJ0001';
            this.loadTrajectory(trjId);
        });

        getElem('btn-replay-play')?.addEventListener('click', () => this.play());
        getElem('btn-replay-pause')?.addEventListener('click', () => this.pause());
        getElem('btn-replay-step')?.addEventListener('click', () => this.step());
        getElem('btn-replay-reset')?.addEventListener('click', () => this.reset());

        getElem('select-replay-speed')?.addEventListener('change', (e) => {
            this.speedMultiplier = parseInt(e.target.value, 10) || 1;
        });
    }

    async loadTrajectory(trajectoryId) {
        // Cancel active loop and increment generation
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }
        this.generation++;
        const currentGen = this.generation;

        this.setState(ReplayState.LOADING);
        this.currentIndex = 0;
        this.observations = [];

        const statusElem = getElem('replay-status');
        if (statusElem) statusElem.textContent = `Loading ${trajectoryId}...`;

        try {
            const obs = await this.api.getTrajectory(trajectoryId);
            if (this.generation !== currentGen) return;

            this.observations = obs || [];
            this.setState(ReplayState.READY);
            this.updateProgressUI();

            if (statusElem) {
                statusElem.textContent = `Loaded ${this.observations.length} observations (${trajectoryId})`;
            }

            // Plot all points faintly on map
            const coords = this.observations.map(o => [o.latitude, o.longitude]);
            if (coords.length > 0 && this.map?.layers?.markers) {
                this.map.layers.markers.clearLayers();
                L.polyline(coords, {
                    color: '#94a3b8',
                    weight: 2,
                    opacity: 0.5,
                    dashArray: '4, 4'
                }).addTo(this.map.layers.markers);
                this.map.fitBoundsToActive(coords.map(c => L.latLng(c[0], c[1])));
            }
        } catch (err) {
            if (this.generation !== currentGen) return;
            console.error('Failed to load trajectory:', err);
            this.setState(ReplayState.ERROR);
            if (statusElem) statusElem.textContent = `Error: ${err.message}`;
        }
    }

    /**
     * Executes a single sequential replay step.
     * Guarantees max 1 in-flight step.
     * Progress index advances strictly after ingestion and onStep evaluation complete.
     */
    async step(isAutoStep = false) {
        if (this.isStepInProgress) {
            return false;
        }

        if (this.currentIndex >= this.observations.length) {
            this.setState(ReplayState.COMPLETE);
            const statusElem = getElem('replay-status');
            if (statusElem) statusElem.textContent = 'Trajectory Replay Complete';
            return false;
        }

        this.isStepInProgress = true;
        const currentGen = this.generation;
        const targetIndex = this.currentIndex;
        const obs = this.observations[targetIndex];

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

            // Ingest to Week 1 / realtime endpoint
            const locResp = await this.api.ingestDriverLocation(this.driverId, observationPayload);

            // Stale response guard (reset or pause or switch happened while in flight)
            if (this.generation !== currentGen) {
                return false;
            }

            // Update map with real response
            const rawPos = { latitude: obs.latitude, longitude: obs.longitude };
            const matchedPos = locResp.matched_position ? {
                latitude: locResp.matched_position.latitude,
                longitude: locResp.matched_position.longitude,
                road_segment_id: locResp.matched_position.road_segment_id,
                osm_way_id: locResp.matched_position.osm_way_id,
                direction: locResp.matched_position.direction,
                confidence: locResp.matched_position.confidence
            } : null;

            this.map.renderDriver(rawPos, matchedPos, obs.heading_deg);

            const statusElem = getElem('replay-status');
            if (statusElem) {
                statusElem.innerHTML = `
                    State: <b>${locResp.status}</b> · Trigger: <code>${locResp.trigger_reason || 'NONE'}</code> · Matches: <b>${locResp.total_match_calls}</b>
                `;
            }

            // Downstream handler (DriverModeController recommendation evaluation)
            if (this.onStep) {
                await this.onStep({
                    observation: obs,
                    locResp,
                    currentIndex: targetIndex + 1,
                    generation: currentGen
                });
            }

            // Stale check again after onStep await
            if (this.generation !== currentGen) {
                return false;
            }

            // Confirmed progress
            this.currentIndex = targetIndex + 1;
            this.updateProgressUI();

            if (this.currentIndex >= this.observations.length) {
                this.setState(ReplayState.COMPLETE);
                if (statusElem) statusElem.textContent = 'Trajectory Replay Complete';
            }

            return true;
        } catch (err) {
            if (this.generation !== currentGen) return false;
            console.error('Replay step error:', err);
            this.setState(ReplayState.ERROR);
            const statusElem = getElem('replay-status');
            if (statusElem) statusElem.textContent = `Step error: ${err.message}`;
            return false;
        } finally {
            this.isStepInProgress = false;
        }
    }

    play() {
        if (this.state === ReplayState.PLAYING) return;

        // If at end, wrap to start
        if (this.currentIndex >= this.observations.length) {
            this.currentIndex = 0;
            this.updateProgressUI();
        }

        this.setState(ReplayState.PLAYING);
        this._runPlaybackLoop();
    }

    async _runPlaybackLoop() {
        const loopGen = this.generation;

        while (this.state === ReplayState.PLAYING && this.generation === loopGen) {
            if (this.currentIndex >= this.observations.length) {
                this.setState(ReplayState.COMPLETE);
                break;
            }

            const stepSucceeded = await this.step(true);

            if (!stepSucceeded || this.state !== ReplayState.PLAYING || this.generation !== loopGen) {
                break;
            }

            // Delay before scheduling next step
            const baseDelayMs = 500;
            const delay = Math.max(30, Math.round(baseDelayMs / this.speedMultiplier));
            await new Promise(resolve => {
                this.stepTimer = setTimeout(resolve, delay);
            });
            this.stepTimer = null;
        }
    }

    pause() {
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }
        if (this.state === ReplayState.PLAYING) {
            this.setState(ReplayState.PAUSED);
        }
    }

    reset() {
        // Invalidate generation immediately
        this.generation++;
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }
        this.isStepInProgress = false;
        this.currentIndex = 0;

        // Reset backend realtime state
        this.api.resetDriverLocation(this.driverId).catch(() => {});

        // Clear map markers
        if (this.map?.layers?.driver?.clearLayers) {
            this.map.layers.driver.clearLayers();
        }
        if (this.map?.driverRawMarker) {
            this.map.driverRawMarker.remove?.();
            this.map.driverRawMarker = null;
        }
        if (this.map?.driverMatchedMarker) {
            this.map.driverMatchedMarker.remove?.();
            this.map.driverMatchedMarker = null;
        }

        this.setState(ReplayState.READY);
        this.updateProgressUI();

        const statusElem = getElem('replay-status');
        if (statusElem) statusElem.textContent = 'Replay Ready';
    }

    /** Clear session context */
    clearSession() {
        this.api.resetDriverLocation(this.session.driver_id).catch(() => {});
    }

    isReplayComplete() {
        return this.observations.length > 0 && this.currentIndex >= this.observations.length;
    }

    getProgressText() {
        if (this.observations.length === 0) return 'No trajectory loaded';
        return `${this.currentIndex} / ${this.observations.length} obs`;
    }

    getCurrentRawPosition() {
        if (this.currentIndex > 0 && this.currentIndex <= this.observations.length) {
            const obs = this.observations[this.currentIndex - 1];
            return { latitude: obs.latitude, longitude: obs.longitude };
        }
        return null;
    }

    updateProgressUI() {
        const progressElem = getElem('replay-progress');
        if (progressElem) {
            progressElem.textContent = `${this.currentIndex} / ${this.observations.length}`;
        }
    }

    updateControlsUI() {
        if (typeof document === 'undefined') return;

        const isPlaying = this.state === ReplayState.PLAYING;
        const isLoading = this.state === ReplayState.LOADING;

        const playBtns = [
            getElem('btn-replay-play'),
            getElem('btn-driver-replay-play')
        ];
        const pauseBtns = [
            getElem('btn-replay-pause'),
            getElem('btn-driver-replay-pause')
        ];
        const stepBtns = [
            getElem('btn-replay-step'),
            getElem('btn-driver-replay-step')
        ];

        playBtns.forEach(btn => {
            if (btn) btn.disabled = isPlaying || isLoading;
        });
        pauseBtns.forEach(btn => {
            if (btn) btn.disabled = !isPlaying || isLoading;
        });
        stepBtns.forEach(btn => {
            if (btn) btn.disabled = isPlaying || isLoading;
        });
    }
}
