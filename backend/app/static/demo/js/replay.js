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

function approxDistMeters(lat1, lon1, lat2, lon2) {
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const midLat = ((lat1 + lat2) / 2) * Math.PI / 180;
    const x = dLon * Math.cos(midLat) * 6371000;
    const y = dLat * 6371000;
    return Math.sqrt(x * x + y * y);
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
        this.playbackToken = 0;
        this._cancelSleep = null;
        this.lastAcceptedTimestampMs = 0;
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

    _sleep(ms, token) {
        return new Promise(resolve => {
            let timerId = null;
            const cleanup = () => {
                if (timerId) clearTimeout(timerId);
                if (this._cancelSleep === cancelFn) this._cancelSleep = null;
            };
            const cancelFn = () => {
                cleanup();
                resolve(false);
            };
            this._cancelSleep = cancelFn;
            timerId = setTimeout(() => {
                cleanup();
                resolve(this.playbackToken === token);
            }, ms);
        });
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

        // Capture playing state BEFORE incrementing generation
        const wasPlaying = this.state === ReplayState.PLAYING;
        const resumeAfterLoad = wasPlaying;

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

            // Auto-resume playback if was playing before
            if (resumeAfterLoad) {
                this.play();
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
     * Generate synthetic trajectory observations along route polyline coordinates.
     * Allows simulated driving on ANY route (custom origin/destination, detour routes, etc.)
     * @param {Array<Array<number>>|Array<{latitude: number, longitude: number}>} coordinates
     * @param {number} speedKmh - average vehicle speed (default 35 km/h)
     */
    async loadFromPolyline(coordinates, speedKmh = 35) {
        if (!coordinates || coordinates.length < 2) {
            console.warn('[Replay] Invalid coordinates for polyline simulation');
            return;
        }

        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }

        // Capture playing state BEFORE incrementing generation
        const wasPlaying = this.state === ReplayState.PLAYING;
        const resumeAfterLoad = wasPlaying;

        this.generation++;
        const currentGen = this.generation;

        this.setState(ReplayState.LOADING);
        this.currentIndex = 0;
        this.observations = [];

        // Normalize coordinates to [{lat, lng}, ...]
        const points = coordinates.map(c => {
            if (Array.isArray(c)) return { lat: c[0], lng: c[1] };
            return { lat: c.latitude ?? c.lat, lng: c.longitude ?? c.lng };
        });

        // Step distance along route: vehicle travels at speedKmh
        const speedMs = speedKmh / 3.6;
        const multiplier = Math.max(1, Math.min(10, this.speedMultiplier || 1));
        const intervalSec = 1.5 * multiplier;
        const stepDistMeters = Math.max(12, speedMs * intervalSec);

        // Calculate total route distance first to place baseTime safely in the past
        let totalDistMeters = 0;
        for (let i = 0; i < points.length - 1; i++) {
            totalDistMeters += approxDistMeters(points[i].lat, points[i].lng, points[i + 1].lat, points[i + 1].lng);
        }
        const totalEstimatedSteps = Math.max(points.length, Math.ceil(totalDistMeters / stepDistMeters) + 10);
        const totalDurationMs = totalEstimatedSteps * intervalSec * 1000;
        let baseTime;
        if (this.lastAcceptedTimestampMs > 0) {
            baseTime = this.lastAcceptedTimestampMs + 1000;
        } else {
            baseTime = Date.now() - totalDurationMs - 120000;
        }

        const syntheticObs = [];
        let obsIndex = 0;

        for (let i = 0; i < points.length - 1; i++) {
            const p1 = points[i];
            const p2 = points[i + 1];

            const dLat = (p2.lat - p1.lat) * Math.PI / 180;
            const dLng = (p2.lng - p1.lng) * Math.PI / 180;
            const midLat = ((p1.lat + p2.lat) / 2) * Math.PI / 180;
            const x = dLng * Math.cos(midLat) * 6371000;
            const y = dLat * 6371000;
            const segDist = Math.sqrt(x * x + y * y);

            const yH = Math.sin(dLng) * Math.cos(p2.lat * Math.PI / 180);
            const xH = Math.cos(p1.lat * Math.PI / 180) * Math.sin(p2.lat * Math.PI / 180) -
                       Math.sin(p1.lat * Math.PI / 180) * Math.cos(p2.lat * Math.PI / 180) * Math.cos(dLng);
            let headingDeg = (Math.atan2(yH, xH) * 180 / Math.PI + 360) % 360;

            const numSubSteps = Math.max(1, Math.round(segDist / stepDistMeters));
            for (let s = 0; s < numSubSteps; s++) {
                const fraction = s / numSubSteps;
                const curLat = p1.lat + (p2.lat - p1.lat) * fraction;
                const curLng = p1.lng + (p2.lng - p1.lng) * fraction;
                const timestamp = new Date(baseTime + obsIndex * intervalSec * 1000).toISOString();

                syntheticObs.push({
                    observation_id: `SIM_${obsIndex}`,
                    latitude: curLat,
                    longitude: curLng,
                    timestamp,
                    speed_kmh: speedKmh,
                    heading_deg: headingDeg
                });
                obsIndex++;
            }
        }

        const lastP = points[points.length - 1];
        syntheticObs.push({
            observation_id: `SIM_${obsIndex}`,
            latitude: lastP.lat,
            longitude: lastP.lng,
            timestamp: new Date(baseTime + obsIndex * intervalSec * 1000).toISOString(),
            speed_kmh: 0,
            heading_deg: syntheticObs[syntheticObs.length - 1]?.heading_deg || 0
        });

        if (this.generation !== currentGen) return;

        this.observations = syntheticObs;
        this.setState(ReplayState.READY);
        this.updateProgressUI();

        const statusElem = getElem('replay-status');
        if (statusElem) {
            statusElem.textContent = `Lộ trình mô phỏng: ${this.observations.length} điểm quan sát`;
        }

        // Auto-resume playback if was playing before (seamless route change)
        if (resumeAfterLoad) {
            this.play();
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
            let obsTimestamp = obs.timestamp;
            const nowMs = Date.now();
            // Critical safeguard: never send a timestamp in the future to backend realtime ingestion
            if (!obsTimestamp || new Date(obsTimestamp).getTime() > nowMs) {
                obsTimestamp = new Date(nowMs).toISOString();
            }

            const observationPayload = {
                latitude: obs.latitude,
                longitude: obs.longitude,
                timestamp: obsTimestamp,
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

            // Reject stale observation status (data integrity guard)
            if (locResp.status === 'STALE_OBSERVATION') {
                const staleErr = new Error('STALE_OBSERVATION: Timestamp rejected by backend realtime tracker');
                staleErr.isStale = true;
                throw staleErr;
            }

            // Record monotonic accepted timestamp
            this.lastAcceptedTimestampMs = new Date(obsTimestamp).getTime();

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
            const isLastObservation = (targetIndex + 1 >= this.observations.length);
            if (this.onStep) {
                try {
                    await this.onStep({
                        observation: obs,
                        locResp,
                        currentIndex: targetIndex + 1,
                        isComplete: isLastObservation,
                        generation: currentGen
                    });
                } catch (stepErr) {
                    console.warn('[Replay] Downstream onStep warning:', stepErr);
                }
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
            if (isAutoStep) {
                // Let playback loop manage transient backoff and retry budget
                throw err;
            }
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
        const token = ++this.playbackToken;
        this._runPlaybackLoop(token);
    }

    async _runPlaybackLoop(token) {
        const loopGen = this.generation;
        let consecutiveRetries = 0;

        while (this.state === ReplayState.PLAYING && this.generation === loopGen && this.playbackToken === token) {
            if (this.currentIndex >= this.observations.length) {
                this.setState(ReplayState.COMPLETE);
                break;
            }

            try {
                await this.step(true);
                consecutiveRetries = 0; // Reset retries on success
            } catch (err) {
                if (this.state !== ReplayState.PLAYING || this.generation !== loopGen || this.playbackToken !== token) {
                    break;
                }

                const isTransient = err.isRateLimited || err.isEngineUnavailable || err.status === 429 ||
                                    err.status === 503 || err.status === 504 || err.code === 'NETWORK_ERROR' ||
                                    err.code === 'TIMEOUT' || (err.status >= 500 && err.status < 600);

                if (isTransient && consecutiveRetries < 3) {
                    consecutiveRetries++;
                    const cooldownMs = (err.retryAfter ? (err.retryAfter * 1000) : null) ||
                                       Math.min(10000, 1500 * Math.pow(2, consecutiveRetries - 1));
                    console.warn(`[Replay] Transient error (${err.message}) at index ${this.currentIndex}. Retrying ${consecutiveRetries}/3 in ${cooldownMs}ms...`);
                    const ok = await this._sleep(cooldownMs, token);
                    if (!ok) break;
                    continue;
                } else {
                    // Non-transient or exhausted retry budget
                    console.error(`[Replay] Step error (${err.message}). Retries exhausted or non-retriable.`);
                    this.setState(ReplayState.ERROR);
                    const statusElem = getElem('replay-status');
                    if (statusElem) statusElem.textContent = `Error: ${err.message}`;
                    break;
                }
            }

            if (this.state !== ReplayState.PLAYING || this.generation !== loopGen || this.playbackToken !== token) {
                break;
            }

            // Normal pacing between steps:
            // High multiplier (>= 10, e.g. tests): fast floor for automated tests.
            // Fast simulation (5x - 9x): 800ms delay (~75 req/min total, safely within 100 req/min quota).
            // Moderate simulation (2x - 4x): 1000ms delay (~60 req/min).
            // Realtime (< 2x): 1200ms delay (~50 req/min).
            const delay = this.speedMultiplier >= 10
                ? Math.max(30, Math.round(500 / this.speedMultiplier))
                : (this.speedMultiplier >= 5 ? 800 : (this.speedMultiplier >= 2 ? 1000 : 1200));
            const ok = await this._sleep(delay, token);
            if (!ok) break;
        }
    }

    setSpeedMultiplier(multiplier) {
        this.speedMultiplier = Math.max(1, parseInt(multiplier, 10) || 1);
    }

    pause() {
        this.playbackToken++;
        if (this._cancelSleep) {
            this._cancelSleep();
        }
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }
        if (this.state === ReplayState.PLAYING) {
            this.setState(ReplayState.PAUSED);
        }
    }

    reset() {
        // Invalidate generation and playback token immediately
        this.generation++;
        this.playbackToken++;
        if (this._cancelSleep) {
            this._cancelSleep();
        }
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
            this.stepTimer = null;
        }
        this.isStepInProgress = false;
        this.currentIndex = 0;
        this.lastAcceptedTimestampMs = 0;

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
        if (this.observations.length === 0) return 'Chưa tải lộ trình';
        return `${this.currentIndex} / ${this.observations.length} điểm GPS`;
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
