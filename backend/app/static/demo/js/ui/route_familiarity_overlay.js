const RESOLUTION = 11;
const DEFAULT_MAX_CELLS = 500;
const DEFAULT_BATCH_SIZE = 50;
const scheduleFrame = callback => globalThis.requestAnimationFrame
    ? globalThis.requestAnimationFrame(callback) : setTimeout(callback, 0);
const cancelScheduledFrame = frame => globalThis.cancelAnimationFrame
    ? globalThis.cancelAnimationFrame(frame) : clearTimeout(frame);

export class RouteFamiliarityOverlay {
    constructor({ map, leaflet, h3, toggle, countElement, supportElement, maxCells = DEFAULT_MAX_CELLS,
        batchSize = DEFAULT_BATCH_SIZE, requestFrame = scheduleFrame,
        cancelFrame = cancelScheduledFrame }) {
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
        this.layer = leaflet.layerGroup().addTo(map);
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

    setRoute(route) {
        this.route = route && typeof route === 'object' ? route : { resolution: null, route_cells: [] };
        const hasCells = this.route.resolution === RESOLUTION && Array.isArray(this.route.route_cells) &&
            this.route.route_cells.some(cell => this.isResolution11Cell(cell));
        if (this.toggle) this.toggle.disabled = !hasCells;
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
        this.render();
    }

    isResolution11Cell(cell) {
        try {
            return typeof cell === 'string' && this.h3.isValidCell(cell) &&
                this.h3.getResolution(cell) === RESOLUTION;
        } catch {
            return false;
        }
    }

    setEnabled(enabled) {
        this.enabled = Boolean(enabled);
        if (this.toggle) this.toggle.checked = this.enabled;
        this.render();
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
        if (!this.enabled) {
            this.setCount('Route cells hidden');
            return;
        }
        if (this.route?.resolution !== RESOLUTION || !Array.isArray(this.route.route_cells)) {
            this.setCount('Resolution 11 route cells unavailable');
            return;
        }

        const bounds = this.map.getBounds();
        const west = bounds.getWest();
        const east = bounds.getEast();
        const south = bounds.getSouth();
        const north = bounds.getNorth();
        const visible = [];
        for (const cell of this.route.route_cells) {
            if (!this.isResolution11Cell(cell)) continue;
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
            visible.push(boundary.map(([lat, lng]) => [lat, lng]));
        }

        const capped = visible.slice(0, this.maxCells);
        this.polygons = capped.map(coords => this.L.polygon(coords, {
            color: '#7c3aed', fillColor: '#a78bfa', fillOpacity: 0.35, weight: 1,
            interactive: false
        }));
        this.setCount(`Showing ${capped.length} of ${visible.length} route cells (H3-11)`);
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

    destroy() {
        this.cancelRender();
        this.map.off('moveend', this.onMoveEnd);
        this.map.removeLayer(this.layer);
    }
}
