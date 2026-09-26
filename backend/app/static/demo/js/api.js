/**
 * Centralized API Client for VinFast Green Mobility EV Recommendation Demo.
 * 
 * Strict rule: NO BUSINESS LOGIC IN FRONTEND.
 * All ranking, routing, demand evaluation, and candidate eligibility remain in the backend.
 */

export class ApiError extends Error {
    constructor(message, status, code = null, detail = null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
        this.detail = detail;
        this.isConflict = status === 409;
        this.isEngineUnavailable = status === 503;
        this.isLocationUnavailable = code === 'LOCATION_UNAVAILABLE';
    }
}

export class ApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl.replace(/\/+$/, '');
        this.defaultTimeoutMs = 15000;
    }

    async _request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const timeoutMs = options.timeout || this.defaultTimeoutMs;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        const config = {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            }
        };

        try {
            const response = await fetch(url, config);
            clearTimeout(timeoutId);

            let data = null;
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                let code = null;
                let message = `HTTP ${response.status}`;
                let detail = data;

                if (data && typeof data === 'object') {
                    if (data.code) code = data.code;
                    if (data.detail) {
                        if (typeof data.detail === 'string') {
                            message = data.detail;
                        } else if (data.detail.code) {
                            code = data.detail.code;
                            message = data.detail.message || message;
                        } else if (Array.isArray(data.detail) && data.detail[0]?.msg) {
                            message = data.detail.map(d => `${d.loc?.join('.')}: ${d.msg}`).join('; ');
                        }
                    }
                    if (data.message) message = data.message;
                }

                throw new ApiError(message, response.status, code, detail);
            }

            return data;
        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === 'AbortError') {
                throw new ApiError(`Request timed out after ${timeoutMs}ms`, 504, 'TIMEOUT');
            }
            if (err instanceof ApiError) {
                throw err;
            }
            throw new ApiError(err.message || 'Network error', 0, 'NETWORK_ERROR');
        }
    }

    /**
     * Liveness check
     */
    async getHealth() {
        return this._request('/health');
    }

    /**
     * Readiness check across GraphHopper, PostGIS road segments, etc.
     */
    async getReadiness() {
        return this._request('/ready');
    }

    /**
     * Recommendation API: demand detection, candidate search, and ranking.
     */
    async getRecommendation(recommendRequest) {
        return this._request('/api/v1/recommend', {
            method: 'POST',
            body: JSON.stringify(recommendRequest)
        });
    }

    /**
     * Evaluates demand and searches all 30 candidate stations (eligible and ineligible).
     * Used exclusively in Simulation / Debug mode to inspect candidate details.
     */
    async evaluateAndSearchCandidates(payload) {
        return this._request('/api/v1/candidate-search/evaluate', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    /**
     * Evaluates vehicle telemetry to determine auto-detected demand.
     */
    async evaluateDemand(payload) {
        return this._request('/api/v1/demand/evaluate', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    /**
     * Computes a road-network route and returns encoded polyline geometry.
     */
    async computeRoute(origin, destination, profile = { vehicle_category: 'EV_CAR' }, via = []) {
        const payload = {
            origin: { latitude: origin.latitude, longitude: origin.longitude },
            destination: { latitude: destination.latitude, longitude: destination.longitude },
            profile
        };
        if (via && via.length > 0) {
            payload.via = via.map(p => ({ latitude: p.latitude, longitude: p.longitude }));
        }
        return this._request('/api/v1/route', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }

    /**
     * Ingest single GPS observation for a driver (Week 1 realtime state).
     */
    async ingestDriverLocation(driverId, observation) {
        return this._request(`/api/v1/drivers/${driverId}/location`, {
            method: 'POST',
            body: JSON.stringify(observation)
        });
    }

    /**
     * Get current location and matched state for a driver.
     */
    async getDriverLocation(driverId) {
        return this._request(`/api/v1/drivers/${driverId}/location`);
    }

    /**
     * Reset driver's realtime state.
     */
    async resetDriverLocation(driverId) {
        return this._request(`/api/v1/drivers/${driverId}/location`, {
            method: 'DELETE'
        });
    }

    /**
     * Load trajectory observations for replay.
     */
    async getTrajectory(trajectoryId) {
        return this._request(`/api/v1/debug/trajectories/${trajectoryId}`);
    }

    /**
     * Fetch vehicle capability.
     */
    async getVehicleCapability(vehicleId) {
        return this._request(`/api/v1/vehicles/${vehicleId}/capability`);
    }
}
