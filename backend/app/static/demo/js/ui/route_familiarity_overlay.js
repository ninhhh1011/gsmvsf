const DEFAULT_RESOLUTION = 9;
const DEFAULT_MAX_CELLS = 500;
const DEFAULT_BATCH_SIZE = 50;
const scheduleFrame = callback => globalThis.requestAnimationFrame
    ? globalThis.requestAnimationFrame(callback) : setTimeout(callback, 0);
const cancelScheduledFrame = frame => globalThis.cancelAnimationFrame
    ? globalThis.cancelAnimationFrame(frame) : clearTimeout(frame);

export class RouteFamiliarityOverlay {
    constructor({ map, leaflet, h3, toggle, countElement, supportElement, maxCells = DEFAULT_MAX_CELLS,
        batchSize = DEFAULT_BATCH_SIZE, requestFrame = scheduleFrame,
        cancelFrame = cancelScheduledFrame, stations = [], resolution = DEFAULT_RESOLUTION }) {
        this.map = map;
        this.L = leaflet;
        this.h3 = h3;
        this.toggle = toggle;
        this.countElement = countElement;
        this.supportElement = supportElement;
        this.maxCells = maxCells;
        this.batchSize = batchSize;
        this.requestFrame = requestFrame;
        this.cancelFrame = cancelFrame;
        this.stations = Array.isArray(stations) ? stations : [];
        this.resolution = resolution || DEFAULT_RESOLUTION;
        this.sharedCellsSet = new Set();
        this.cellMetadata = new Map();
        this.layer = leaflet.layerGroup().addTo(map);
        this.active = true;
        this.enabled = false;
        this.route = { resolution: null, route_cells: [] };
        this.frame = null;
        this.polygons = [];
        this.rendered = 0;
        this.onMoveEnd = () => this.render();
        map.on('moveend', this.onMoveEnd);
        toggle?.addEventListener('change', () => this.setEnabled(toggle.checked));
        this.setCount('Route cells hidden');
    }

    setStations(stations) {
        this.stations = Array.isArray(stations) ? stations : [];
        if (this.route?.route_cells?.length > 0) {
            this._computeCellMetadata(this.route.route_cells, this.stations, this.sharedCellsSet);
            if (this.enabled) this.render();
        }
    }

    setRoute(route) {
        this.route = route && typeof route === 'object' ? route : { resolution: null, route_cells: [] };
        const res = this.route.resolution || this.resolution;
        const hasCells = Array.isArray(this.route.route_cells) &&
            this.route.route_cells.some(cell => this.isResolutionCell(cell, res));
        if (this.toggle) this.toggle.disabled = !hasCells || !this.active;
        if (!hasCells) this.setEnabled(false);
        const personal = Number.isInteger(this.route.personal_trip_count) ? this.route.personal_trip_count : null;
        const communityDrivers = Number.isInteger(this.route.community_driver_count) ? this.route.community_driver_count : null;
        const communityTrips = Number.isInteger(this.route.community_trip_count) ? this.route.community_trip_count : null;
        if (this.supportElement) {
            const personalLabel = personal === null ? 'unavailable' : `${personal} trips`;
            const communityLabel = communityDrivers === null || communityTrips === null
                ? 'suppressed/unavailable' : `${communityDrivers} drivers, ${communityTrips} trips`;
            this.supportElement.textContent = `Personal support: ${personalLabel} · Community support: ${communityLabel}`;
        }
        if (hasCells) {
            this._computeCellMetadata(this.route.route_cells, this.stations, this.sharedCellsSet);
        }
        this.render();
    }

    isResolutionCell(cell, resolution = this.resolution) {
        try {
            return typeof cell === 'string' && this.h3.isValidCell(cell) &&
                this.h3.getResolution(cell) === resolution;
        } catch {
            return false;
        }
    }

    isResolution11Cell(cell) {
        return this.isResolutionCell(cell, 11);
    }

    setEnabled(enabled) {
        this.enabled = Boolean(enabled) && this.active;
        if (this.toggle) this.toggle.checked = this.enabled;
        this.render();
    }

    setActive(active) {
        this.active = Boolean(active);
        if (!this.active) this.setEnabled(false);
        this.setRoute(this.route);
    }

    setCount(text) {
        if (this.countElement) this.countElement.textContent = text;
    }

    cancelRender() {
        if (this.frame !== null) this.cancelFrame(this.frame);
        this.frame = null;
        this.polygons = [];
        this.rendered = 0;
        this.layer.clearLayers();
    }

    render() {
        this.cancelRender();
        if (!this.active || !this.enabled) {
            this.setCount('Route cells hidden');
            this.updateLegend(false);
            return;
        }
        const res = this.route?.resolution || this.resolution;
        if (!res || !Array.isArray(this.route?.route_cells)) {
            this.setCount('Route cells unavailable');
            this.updateLegend(false);
            return;
        }

        const bounds = this.map.getBounds();
        const west = bounds.getWest();
        const east = bounds.getEast();
        const south = bounds.getSouth();
        const north = bounds.getNorth();
        const visible = [];
        for (const cell of this.route.route_cells) {
            if (!this.isResolutionCell(cell, res)) continue;
            let boundary;
            try {
                boundary = this.h3.cellToBoundary(cell);
            } catch {
                continue;
            }
            if (!Array.isArray(boundary) || boundary.length < 3 || boundary.some(point =>
                !Array.isArray(point) || point.length < 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1]))) continue;
            const lats = boundary.map(point => point[0]);
            const lngs = boundary.map(point => point[1]);
            if (Math.max(...lats) < south || Math.min(...lats) > north ||
                Math.max(...lngs) < west || Math.min(...lngs) > east) continue;
            visible.push({ cell, boundary: boundary.map(([lat, lng]) => [lat, lng]) });
        }

        const capped = visible.slice(0, this.maxCells);
        this.polygons = capped.map(item => {
            const cell = item.cell;
            const coords = item.boundary;
            const meta = this.cellMetadata.get(cell) || this._getDefaultMeta(cell);
            const poly = this.L.polygon(coords, {
                color: meta.color,
                fillColor: meta.fillColor,
                fillOpacity: 0.45,
                weight: 1.5,
                interactive: true
            });
            if (typeof poly.bindPopup === 'function') {
                poly.bindPopup(this._createPopupContent(cell, meta));
            }
            return poly;
        });
        this.setCount(`Showing ${capped.length} of ${visible.length} route cells (H3-${res})`);
        this.updateLegend(true, capped.length);
        this.renderBatch();
    }

    renderBatch() {
        const end = Math.min(this.rendered + this.batchSize, this.polygons.length);
        for (; this.rendered < end; this.rendered++) this.layer.addLayer(this.polygons[this.rendered]);
        if (this.rendered < this.polygons.length) {
            this.frame = this.requestFrame(() => {
                this.frame = null;
                this.renderBatch();
            });
        }
    }

    /**
     * Render H3 cells computed from geometry with station coverage or shared route analysis.
     * @param {string[]} cells - Array of H3 cell IDs
     * @param {Array|null} [sharedOrStations] - Optional shared cell IDs or stations
     */
    renderFromCells(cells, sharedOrStations = null) {
        if (!this.active || !Array.isArray(cells) || cells.length === 0) {
            this.clear();
            return;
        }

        let detRes = this.resolution;
        try {
            if (cells[0] && typeof this.h3?.getResolution === 'function') {
                detRes = this.h3.getResolution(cells[0]) || this.resolution;
            }
        } catch {
            detRes = this.resolution;
        }

        this.route = {
            resolution: detRes,
            route_cells: cells
        };

        if (Array.isArray(sharedOrStations)) {
            if (sharedOrStations.length > 0 && typeof sharedOrStations[0] === 'string') {
                this.sharedCellsSet = new Set(sharedOrStations);
            } else if (sharedOrStations.length > 0 && typeof sharedOrStations[0] === 'object') {
                this.stations = sharedOrStations;
                this.sharedCellsSet = new Set();
            } else {
                this.sharedCellsSet = new Set();
            }
        } else {
            this.sharedCellsSet = new Set();
        }

        this._computeCellMetadata(cells, this.stations, this.sharedCellsSet);
        this.enabled = true;
        if (this.toggle) this.toggle.checked = true;
        this.render();
    }

    /**
     * Clear the H3 overlay.
     */
    clear() {
        this.route = { resolution: null, route_cells: [] };
        this.sharedCellsSet.clear();
        this.cellMetadata.clear();
        this.cancelRender();
        this.setCount('Route cells hidden');
        this.updateLegend(false);
    }

    /**
     * Compute H3 cells from route geometry coordinates.
     * Samples along route segments scaled by resolution.
     * @param {Array<[number, number]>|null} geometryCoords - Array of [lat, lng] pairs
     * @param {number} resolution - H3 resolution (defaults to overlay's current resolution)
     * @returns {string[]} Array of H3 cell IDs
     */
    computeH3CellsFromGeometry(geometryCoords, resolution = this.resolution) {
        if (!geometryCoords || !Array.isArray(geometryCoords) || geometryCoords.length < 2) {
            return [];
        }
        const cells = new Set();
        const stepM = resolution <= 8 ? 60 : (resolution === 9 ? 35 : 20);

        for (let i = 0; i < geometryCoords.length - 1; i++) {
            const [lat1, lng1] = geometryCoords[i];
            const [lat2, lng2] = geometryCoords[i + 1];

            if (!Number.isFinite(lat1) || !Number.isFinite(lng1) ||
                !Number.isFinite(lat2) || !Number.isFinite(lng2)) {
                continue;
            }

            const segDist = this._approxDistMeters(lat1, lng1, lat2, lng2);
            const numSamples = Math.max(1, Math.ceil(segDist / stepM));

            for (let s = 0; s <= numSamples; s++) {
                const t = s / numSamples;
                const lat = lat1 + (lat2 - lat1) * t;
                const lng = lng1 + (lng2 - lng1) * t;

                try {
                    const cell = this.h3.latLngToCell(lat, lng, resolution);
                    if (cell) cells.add(cell);
                } catch {
                    // Skip invalid cells
                }

                if (cells.size >= this.maxCells) break;
            }
            if (cells.size >= this.maxCells) break;
        }

        return Array.from(cells);
    }

    setResolution(resolution) {
        this.resolution = resolution;
        if (this.route && Array.isArray(this.route.route_cells) && this.route.route_cells.length > 0) {
            this.route.resolution = resolution;
        }
    }

    _approxDistMeters(lat1, lng1, lat2, lng2) {
        const R = 6371000;
        const φ1 = lat1 * Math.PI / 180;
        const φ2 = lat2 * Math.PI / 180;
        const Δφ = (lat2 - lat1) * Math.PI / 180;
        const Δλ = (lng2 - lng1) * Math.PI / 180;
        const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
            Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    _computeCellMetadata(cells, stations = this.stations, sharedCellsSet = this.sharedCellsSet) {
        this.cellMetadata.clear();
        const activeStations = Array.isArray(stations) && stations.length > 0
            ? stations.filter(s => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
            : [];
        const hasComparison = sharedCellsSet && sharedCellsSet.size > 0;

        for (const cell of cells) {
            let centerLat = null;
            let centerLng = null;
            try {
                if (typeof this.h3.cellToLatLng === 'function') {
                    const center = this.h3.cellToLatLng(cell);
                    if (Array.isArray(center) && center.length >= 2) {
                        centerLat = center[0];
                        centerLng = center[1];
                    }
                }
            } catch {
                // fallback
            }

            if (centerLat === null) {
                try {
                    const boundary = this.h3.cellToBoundary(cell);
                    if (Array.isArray(boundary) && boundary.length > 0) {
                        centerLat = boundary.reduce((acc, p) => acc + p[0], 0) / boundary.length;
                        centerLng = boundary.reduce((acc, p) => acc + p[1], 0) / boundary.length;
                    }
                } catch {
                    centerLat = 0;
                    centerLng = 0;
                }
            }

            let nearestStation = null;
            let minDistKm = Infinity;

            for (const st of activeStations) {
                const distM = this._approxDistMeters(centerLat, centerLng, st.latitude, st.longitude);
                const distKm = distM / 1000;
                if (distKm < minDistKm) {
                    minDistKm = distKm;
                    nearestStation = st;
                }
            }

            let tier = 'SAFE';
            let color = '#10b981'; // Green: Safe (< 3km)
            let fillColor = '#34d399';
            let label = 'Vùng an toàn sạc (< 3km)';

            if (hasComparison) {
                if (sharedCellsSet.has(cell)) {
                    tier = 'SHARED';
                    color = '#10b981'; // Green/Emerald: Confirmed shared corridor
                    fillColor = '#34d399';
                    label = 'Hành lang trùng khớp (Shared)';
                } else {
                    tier = 'DIVERGENT';
                    color = '#f59e0b'; // Amber: Divergent / specific to one route
                    fillColor = '#fbbf24';
                    label = 'Đoạn phân kỳ / Khác biệt (Divergent)';
                }
            } else {
                if (minDistKm > 6.0) {
                    tier = 'ALERT';
                    color = '#f43f5e'; // Red: Desert (> 6km)
                    fillColor = '#fb7185';
                    label = 'Vùng trũng sạc (> 6km)';
                } else if (minDistKm > 3.0) {
                    tier = 'CAUTION';
                    color = '#f59e0b'; // Amber: Buffer (3-6km)
                    fillColor = '#fbbf24';
                    label = 'Vùng đệm (3 - 6km)';
                }
            }

            this.cellMetadata.set(cell, {
                cell,
                tier,
                color,
                fillColor,
                label,
                minDistKm: Number.isFinite(minDistKm) ? minDistKm : null,
                nearestStation
            });
        }
    }

    _getDefaultMeta(cell) {
        return {
            cell,
            tier: 'SAFE',
            color: '#10b981',
            fillColor: '#34d399',
            label: 'Hành lang di chuyển EV',
            minDistKm: null,
            nearestStation: null
        };
    }

    _createPopupContent(cell, meta) {
        const distStr = meta.minDistKm !== null ? `${meta.minDistKm.toFixed(2)} km` : 'Chưa có dữ liệu trạm';
        const stName = meta.nearestStation ? (meta.nearestStation.name || meta.nearestStation.station_id) : 'Không có trạm gần';
        const serviceType = meta.nearestStation?.service_type === 'BATTERY_SWAP' ? 'Đổi pin' : 'Sạc nhanh DC';
        const resLabel = this.resolution || 9;

        return `
            <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 12px; line-height: 1.45; min-width: 190px; color: #0f172a;">
                <div style="font-weight: 700; color: ${meta.color}; display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px;">
                    <span>⬡ H3-${resLabel} Index</span>
                    <code style="background: #f1f5f9; padding: 1px 4px; border-radius: 3px; font-size: 10px; color: #334155;">${cell}</code>
                </div>
                <div style="margin-bottom: 4px;">
                    <span style="color: #64748b; font-size: 11px;">Trạng thái:</span>
                    <span style="color: ${meta.color}; font-weight: 600; font-size: 11px; margin-left: 4px;">${meta.label}</span>
                </div>
                <div style="margin-bottom: 3px;">
                    <span style="color: #64748b; font-size: 11px;">Trạm gần nhất:</span>
                    <strong style="font-size: 11px; margin-left: 4px; color: #1e293b;">${stName}</strong>
                </div>
                <div style="margin-bottom: 3px;">
                    <span style="color: #64748b; font-size: 11px;">Loại cổng:</span>
                    <span style="font-size: 11px; margin-left: 4px; color: #0284c7;">⚡ ${serviceType}</span>
                </div>
                <div>
                    <span style="color: #64748b; font-size: 11px;">Khoảng cách trạm:</span>
                    <span style="font-size: 11px; font-weight: 600; margin-left: 4px; color: #0f172a;">${distStr}</span>
                </div>
            </div>
        `;
    }

    updateLegend(show, count = 0) {
        if (typeof document === 'undefined') return;
        const legend = document.getElementById('h3-corridor-legend');
        const badge = document.getElementById('h3-cells-count-badge');
        if (legend) {
            legend.style.display = show ? 'inline-flex' : 'none';
        }
        if (badge && show) {
            badge.textContent = `${count} ô`;
        }
    }

    destroy() {
        this.cancelRender();
        this.map.off('moveend', this.onMoveEnd);
        this.map.removeLayer(this.layer);
    }
}
