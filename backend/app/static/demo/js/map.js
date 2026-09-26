/**
 * Map and Geometry Engine for VinFast EV Recommendation Demo.
 * Uses Leaflet 1.9.4 and real GraphHopper route geometries.
 * 
 * Strict rule: No fake straight lines labeled as routes!
 */

export function decodePolyline(str, precision = 5) {
    if (!str || typeof str !== 'string') return [];
    let index = 0, lat = 0, lng = 0, coordinates = [];
    let shift = 0, result = 0, byte = null, factor = Math.pow(10, precision);

    while (index < str.length) {
        byte = null;
        shift = 0;
        result = 0;
        do {
            byte = str.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        let dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lat += dlat;

        shift = 0;
        result = 0;
        do {
            byte = str.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        let dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lng += dlng;

        coordinates.push([lat / factor, lng / factor]);
    }
    return coordinates;
}

export function haversineDistanceMeters(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function computePolylineDistanceMeters(coords) {
    if (!coords || coords.length < 2) return 0;
    let dist = 0;
    for (let i = 0; i < coords.length - 1; i++) {
        dist += haversineDistanceMeters(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]);
    }
    return dist;
}

export function projectPointOnSegment(pLat, pLon, aLat, aLon, bLat, bLon) {
    const cosLat = Math.cos(aLat * Math.PI / 180);
    const x = (pLon - aLon) * cosLat;
    const y = pLat - aLat;
    const dx = (bLon - aLon) * cosLat;
    const dy = bLat - aLat;
    const lenSq = dx * dx + dy * dy;
    if (lenSq === 0) {
        return { lat: aLat, lon: aLon, t: 0, distMeters: haversineDistanceMeters(pLat, pLon, aLat, aLon) };
    }
    const t = Math.max(0, Math.min(1, (x * dx + y * dy) / lenSq));
    const projLat = aLat + t * (bLat - aLat);
    const projLon = aLon + t * (bLon - aLon);
    return { lat: projLat, lon: projLon, t, distMeters: haversineDistanceMeters(pLat, pLon, projLat, projLon) };
}

export function projectPointOnRoute(point, routeCoords, startIndex = 0) {
    if (!routeCoords || routeCoords.length < 2) {
        return { segmentIndex: 0, projPoint: point ? [point.latitude ?? point[0], point.longitude ?? point[1]] : [0, 0], distanceMeters: 0 };
    }
    const pLat = point.latitude ?? point[0];
    const pLon = point.longitude ?? point[1];
    let bestDist = Infinity;
    let bestSegment = startIndex;
    let bestProj = routeCoords[startIndex];

    // Search window from startIndex forward to avoid O(N) over entire route on each step
    const searchStart = Math.max(0, startIndex);
    const searchEnd = Math.min(routeCoords.length - 1, searchStart + 40);
    for (let i = searchStart; i < searchEnd; i++) {
        const a = routeCoords[i];
        const b = routeCoords[i + 1];
        const proj = projectPointOnSegment(pLat, pLon, a[0], a[1], b[0], b[1]);
        if (proj.distMeters < bestDist) {
            bestDist = proj.distMeters;
            bestSegment = i;
            bestProj = [proj.lat, proj.lon];
        }
    }
    return { segmentIndex: bestSegment, projPoint: bestProj, distanceMeters: bestDist };
}

export function sliceRouteFromProgress(routeCoords, progress) {
    if (!routeCoords || routeCoords.length < 2) return [];
    if (!progress || progress.segmentIndex == null) return routeCoords;
    const { segmentIndex, projPoint } = progress;
    if (segmentIndex >= routeCoords.length - 1) {
        return [routeCoords[routeCoords.length - 1]];
    }
    return [projPoint, ...routeCoords.slice(segmentIndex + 1)];
}

export function simplifyTrajectoryRDP(points, epsilonMeters = 250) {
    if (!points || points.length < 3) return points || [];

    function pointLineDistance(pt, lineStart, lineEnd) {
        const lat = pt.latitude ?? pt[0];
        const lon = pt.longitude ?? pt[1];
        const aLat = lineStart.latitude ?? lineStart[0];
        const aLon = lineStart.longitude ?? lineStart[1];
        const bLat = lineEnd.latitude ?? lineEnd[0];
        const bLon = lineEnd.longitude ?? lineEnd[1];

        const cosLat = Math.cos(aLat * Math.PI / 180);
        const dx = (bLon - aLon) * cosLat * 111320;
        const dy = (bLat - aLat) * 111320;
        const lenSq = dx * dx + dy * dy;
        if (lenSq === 0) {
            return Math.hypot((lon - aLon) * cosLat * 111320, (lat - aLat) * 111320);
        }

        const px = (lon - aLon) * cosLat * 111320;
        const py = (lat - aLat) * 111320;
        const t = Math.max(0, Math.min(1, (px * dx + py * dy) / lenSq));
        const projX = t * dx;
        const projY = t * dy;
        return Math.hypot(px - projX, py - projY);
    }

    function rdp(pts) {
        if (pts.length < 3) return pts;
        let dmax = 0;
        let index = 0;
        for (let i = 1; i < pts.length - 1; i++) {
            const d = pointLineDistance(pts[i], pts[0], pts[pts.length - 1]);
            if (d > dmax) {
                index = i;
                dmax = d;
            }
        }
        if (dmax > epsilonMeters) {
            const rec1 = rdp(pts.slice(0, index + 1));
            const rec2 = rdp(pts.slice(index));
            return [...rec1.slice(0, -1), ...rec2];
        } else {
            return [pts[0], pts[pts.length - 1]];
        }
    }

    return rdp(points);
}

export class DemoMap {
    constructor(elementId, options = {}) {
        this.elementId = elementId;
        this.map = null;

        // Layer groups
        this.layers = {
            baseTiles: null,
            directRoute: null,
            recommendRoute: null,
            stations: null,
            driver: null,
            markers: null
        };

        // State markers
        this.driverRawMarker = null;
        this.driverMatchedMarker = null;
        this.originMarker = null;
        this.destinationMarker = null;
        this.recommendedStationMarker = null;
        this.stationMarkers = new Map();

        this.init(options);
    }

    init(options) {
        const center = options.center || [21.0285, 105.8542]; // Hanoi center
        const zoom = options.zoom || 13;

        this.map = L.map(this.elementId, {
            zoomControl: false,
            attributionControl: true
        }).setView(center, zoom);

        L.control.zoom({ position: 'bottomright' }).addTo(this.map);

        // Standard OpenStreetMap tiles (no API key required)
        this.layers.baseTiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(this.map);

        this.layers.directRoute = L.layerGroup().addTo(this.map);
        this.layers.recommendRoute = L.layerGroup().addTo(this.map);
        this.layers.stations = L.layerGroup().addTo(this.map);
        this.layers.driver = L.layerGroup().addTo(this.map);
        this.layers.markers = L.layerGroup().addTo(this.map);
    }

    invalidateSize() {
        if (this.map) {
            setTimeout(() => this.map.invalidateSize(), 50);
        }
    }

    onMapClick(callback) {
        if (this.map) {
            this.map.on('click', (e) => {
                callback({ latitude: e.latlng.lat, longitude: e.latlng.lng });
            });
        }
    }

    clearRoutes() {
        this.layers.directRoute.clearLayers();
        this.layers.recommendRoute.clearLayers();
    }

    clearRecommendationRoute() {
        this.layers.recommendRoute.clearLayers();
    }

    clearAll() {
        this.clearRoutes();
        this.layers.stations.clearLayers();
        this.layers.driver.clearLayers();
        this.layers.markers.clearLayers();
        this.stationMarkers.clear();
        this.driverRawMarker = null;
        this.driverMatchedMarker = null;
        this.originMarker = null;
        this.destinationMarker = null;
        this.recommendedStationMarker = null;
    }

    renderDirectRoute(geometry) {
        this.layers.directRoute.clearLayers();
        if (!geometry) return;

        let coords = [];
        if (Array.isArray(geometry)) {
            if (geometry.length > 0 && typeof geometry[0] === 'object' && 'latitude' in geometry[0]) {
                coords = geometry.map(p => [p.latitude, p.longitude]);
            } else {
                coords = geometry;
            }
        } else {
            coords = decodePolyline(geometry);
        }
        if (!coords || coords.length === 0) return;

        // Outer glow
        L.polyline(coords, {
            color: '#3b82f6',
            weight: 7,
            opacity: 0.4
        }).addTo(this.layers.directRoute);

        // Core path
        const line = L.polyline(coords, {
            color: '#1d4ed8',
            weight: 4,
            opacity: 0.9,
            lineJoin: 'round'
        }).addTo(this.layers.directRoute);

        return line;
    }

    /**
     * Efficiently update active direct route geometry (e.g. slicing behind driver).
     * If polylines exist, updates their latlngs directly without layer flickering.
     */
    updateDirectRoute(geometry) {
        if (!geometry) {
            this.layers.directRoute.clearLayers();
            return;
        }

        let coords = [];
        if (Array.isArray(geometry)) {
            if (geometry.length > 0 && typeof geometry[0] === 'object' && 'latitude' in geometry[0]) {
                coords = geometry.map(p => [p.latitude, p.longitude]);
            } else {
                coords = geometry;
            }
        } else {
            coords = decodePolyline(geometry);
        }

        if (!coords || coords.length === 0) {
            this.layers.directRoute.clearLayers();
            return;
        }

        const layers = this.layers.directRoute.getLayers();
        if (layers.length >= 2) {
            layers[0].setLatLngs(coords);
            layers[1].setLatLngs(coords);
        } else {
            this.renderDirectRoute(coords);
        }
    }

    /**
     * Render recommended diversion routes:
     * Leg 1: Driver -> Station
     * Leg 2: Station -> Destination (if available)
     */
    renderRecommendationRoute(leg1Geometry, leg2Geometry = null) {
        this.layers.recommendRoute.clearLayers();

        const boundsCoords = [];

        if (leg1Geometry) {
            const coords1 = decodePolyline(leg1Geometry);
            if (coords1.length > 0) {
                boundsCoords.push(...coords1);
                // Outer glow
                L.polyline(coords1, {
                    color: '#f59e0b',
                    weight: 8,
                    opacity: 0.4
                }).addTo(this.layers.recommendRoute);

                // Core path to station
                L.polyline(coords1, {
                    color: '#d97706',
                    weight: 5,
                    opacity: 0.95,
                    lineCap: 'round',
                    dashArray: '8, 4'
                }).addTo(this.layers.recommendRoute);
            }
        }

        if (leg2Geometry) {
            const coords2 = decodePolyline(leg2Geometry);
            if (coords2.length > 0) {
                boundsCoords.push(...coords2);
                L.polyline(coords2, {
                    color: '#10b981',
                    weight: 4,
                    opacity: 0.8,
                    dashArray: '6, 6'
                }).addTo(this.layers.recommendRoute);
            }
        }

        return boundsCoords;
    }

    /**
     * Render driver location: raw GPS point and matched road position.
     */
    renderDriver(rawPos, matchedPos = null, heading = null) {
        // Raw GPS marker (amber dot with subtle accuracy circle)
        if (rawPos && rawPos.latitude && rawPos.longitude) {
            const latLng = [rawPos.latitude, rawPos.longitude];
            if (!this.driverRawMarker) {
                this.driverRawMarker = L.circleMarker(latLng, {
                    radius: 6,
                    fillColor: '#f59e0b',
                    color: '#b45309',
                    weight: 2,
                    fillOpacity: 0.85
                }).addTo(this.layers.driver);
                this.driverRawMarker.bindPopup('<b>Raw GPS Observation</b>');
            } else {
                this.driverRawMarker.setLatLng(latLng);
            }
        }

        // Matched road marker (green pulsing ring with car icon)
        if (matchedPos && matchedPos.latitude && matchedPos.longitude) {
            const latLng = [matchedPos.latitude, matchedPos.longitude];
            const iconHtml = `
                <div class="driver-marker-pulse">
                    <div class="driver-pin" style="transform: rotate(${heading || 0}deg)">
                        <svg viewBox="0 0 24 24" width="22" height="22" fill="#059669">
                            <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
                        </svg>
                    </div>
                </div>
            `;
            const customIcon = L.divIcon({
                className: 'driver-icon-container',
                html: iconHtml,
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });

            if (!this.driverMatchedMarker) {
                this.driverMatchedMarker = L.marker(latLng, { icon: customIcon }).addTo(this.layers.driver);
                this.driverMatchedMarker.bindPopup(`
                    <div style="font-size:12px;">
                        <strong>Matched Road Position</strong><br>
                        Road Segment: <code>${matchedPos.road_segment_id || 'N/A'}</code><br>
                        Direction: ${matchedPos.direction || 'N/A'}<br>
                        Quality: ${(matchedPos.confidence || 0).toFixed(3)}
                    </div>
                `);
            } else {
                this.driverMatchedMarker.setLatLng(latLng);
                this.driverMatchedMarker.setIcon(customIcon);
            }
        }
    }

    /**
     * Render Trip endpoints (Origin and Destination).
     */
    renderTripEndpoints(origin, destination) {
        if (this.originMarker) this.layers.markers.removeLayer(this.originMarker);
        if (this.destinationMarker) this.layers.markers.removeLayer(this.destinationMarker);

        if (origin && origin.latitude && origin.longitude) {
            const originIcon = L.divIcon({
                className: 'endpoint-icon origin-icon',
                html: `<div class="origin-pin">A</div>`,
                iconSize: [26, 26],
                iconAnchor: [13, 13]
            });
            this.originMarker = L.marker([origin.latitude, origin.longitude], { icon: originIcon })
                .bindPopup(`<strong>Trip Origin</strong><br>${origin.latitude.toFixed(5)}, ${origin.longitude.toFixed(5)}`)
                .addTo(this.layers.markers);
        }

        if (destination && destination.latitude && destination.longitude) {
            const destIcon = L.divIcon({
                className: 'endpoint-icon dest-icon',
                html: `<div class="dest-pin">B</div>`,
                iconSize: [26, 26],
                iconAnchor: [13, 13]
            });
            this.destinationMarker = L.marker([destination.latitude, destination.longitude], { icon: destIcon })
                .bindPopup(`<strong>Trip Destination</strong><br>${destination.latitude.toFixed(5)}, ${destination.longitude.toFixed(5)}`)
                .addTo(this.layers.markers);
        }
    }

    /**
     * Render Station markers across Hanoi.
     * Differentiates Recommended station, Eligible stations, and Ineligible stations.
     */
    renderStations(stations, recommendedId = null, recommendedService = null, onSelect = null, liveCandidates = null) {
        if (!stations || stations.length === 0) {
            console.warn('[Map] No stations to render');
            return;
        }

        this.layers.stations.clearLayers();
        this.stationMarkers.clear();

        // Build lookup map for live evaluated candidates if provided
        const liveMap = new Map();
        if (Array.isArray(liveCandidates)) {
            liveCandidates.forEach(c => {
                if (c && c.station_id) {
                    liveMap.set(c.station_id, c);
                }
            });
        }

        stations.forEach(st => {
            const isRecommended = st.station_id === recommendedId;
            const liveCandidate = liveMap.get(st.station_id);

            // Categorize station truthfully:
            // 1. RECOMMENDED: Chosen top recommendation
            // 2. ELIGIBLE: Confirmed in live snapshot with available slots
            // 3. INELIGIBLE: Evaluated in candidate search but rejected
            // 4. UNKNOWN: Static station with no live operational snapshot at current timestamp
            let statusCategory = 'UNKNOWN';
            if (isRecommended) {
                statusCategory = 'RECOMMENDED';
            } else if (liveCandidate) {
                statusCategory = liveCandidate.eligible !== false ? 'ELIGIBLE' : 'INELIGIBLE';
            } else if (st.eligible === true) {
                statusCategory = 'ELIGIBLE';
            } else if (st.eligible === false) {
                statusCategory = 'INELIGIBLE';
            } else {
                statusCategory = 'UNKNOWN';
            }

            const isSwap = (isRecommended && recommendedService === 'BATTERY_SWAP') ||
                (liveCandidate?.service_type === 'BATTERY_SWAP') ||
                st.station_type === 'SWAP' ||
                st.service_type === 'BATTERY_SWAP';

            let markerHtml = '';
            let iconSize = [20, 20];
            let anchor = [10, 10];

            if (statusCategory === 'RECOMMENDED') {
                iconSize = [38, 38];
                anchor = [19, 19];
                const badgeColor = isSwap ? '#8b5cf6' : '#10b981';
                markerHtml = `
                    <div class="station-marker-rec" style="border-color: ${badgeColor};">
                        <div class="rec-badge" style="background: ${badgeColor};">
                            ${isSwap ? 'ĐỔI PIN' : 'SẠC PIN'}
                        </div>
                        <span class="station-code">${st.station_id}</span>
                    </div>
                `;
            } else if (statusCategory === 'ELIGIBLE') {
                const color = isSwap ? '#8b5cf6' : '#0d9488';
                markerHtml = `
                    <div class="station-marker-eligible" style="border-color: ${color};" title="Đang mở (Có dữ liệu vận hành)">
                        <div class="station-dot" style="background: ${color};"></div>
                    </div>
                `;
            } else if (statusCategory === 'INELIGIBLE') {
                markerHtml = `
                    <div class="station-marker-ineligible" title="${liveCandidate?.reason || st.reason || 'Không đủ điều kiện'}">
                        <div class="station-dot-gray"></div>
                    </div>
                `;
            } else {
                markerHtml = `
                    <div class="station-marker-unknown" title="Chưa có dữ liệu vận hành thời gian thực">
                        <div class="station-dot-unknown"></div>
                    </div>
                `;
            }

            const icon = L.divIcon({
                className: 'custom-station-icon',
                html: markerHtml,
                iconSize: iconSize,
                iconAnchor: anchor
            });

            const marker = L.marker([st.latitude, st.longitude], {
                icon: icon,
                zIndexOffset: statusCategory === 'RECOMMENDED' ? 1000 : (statusCategory === 'ELIGIBLE' ? 500 : (statusCategory === 'INELIGIBLE' ? 200 : 100))
            });

            // Vietnamese popup labels & truthful operational metadata
            let statusPillText = 'CHƯA CÓ DỮ LIỆU';
            let statusPillClass = 'pill-unknown';
            if (statusCategory === 'RECOMMENDED') {
                statusPillText = 'ĐƯỢC ĐỀ XUẤT';
                statusPillClass = 'pill-rec';
            } else if (statusCategory === 'ELIGIBLE') {
                statusPillText = 'ĐANG MỞ';
                statusPillClass = 'pill-eligible';
            } else if (statusCategory === 'INELIGIBLE') {
                statusPillText = liveCandidate?.reason || st.reason || 'KHÔNG PHÙ HỢP';
                statusPillClass = 'pill-ineligible';
            }

            const typeLabel = (st.station_type === 'SWAP' || st.service_type === 'BATTERY_SWAP' || isSwap)
                ? 'Đổi pin'
                : ((st.station_type === 'CHARGING_SWAP') ? 'Sạc & Đổi pin' : 'Sạc pin');

            // Format slots/capacity
            let slotInfo = '';
            if (statusCategory === 'UNKNOWN') {
                slotInfo = `<div>Vị trí thiết kế: <b>${st.total_slots || (st.charging_slots + st.swap_slots) || 'N/A'}</b> (Hạ tầng vật lý)</div>
                            <div style="color: #94a3b8; font-style: italic; margin-top: 4px; line-height: 1.3;">⚠️ Chưa có dữ liệu snapshot thời gian thực. Không tự động coi là đang mở.</div>`;
            } else {
                const availCap = liveCandidate?.features?.available_capacity ?? liveCandidate?.operational?.available_capacity ?? st.available_capacity;
                const queueWait = liveCandidate?.features?.effective_queue_wait_s != null
                    ? (liveCandidate.features.effective_queue_wait_s / 60).toFixed(1)
                    : (liveCandidate?.operational?.estimated_wait_min != null ? liveCandidate.operational.estimated_wait_min.toFixed(1) : null);
                const compTime = liveCandidate?.final_cost_s != null ? (liveCandidate.final_cost_s / 60).toFixed(1) : null;

                slotInfo = `
                    <div>Vị trí còn trống: <b>${availCap != null ? availCap : 'Có dữ liệu'}</b></div>
                    ${queueWait != null ? `<div>Thời gian chờ: <b>${queueWait} phút</b></div>` : ''}
                    ${compTime != null ? `<div>Tổng thời gian hoàn tất: <b>${compTime} phút</b></div>` : ''}
                `;
            }

            const popupContent = `
                <div class="station-popup">
                    <div class="station-header" style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                        <strong>Trạm ${st.station_id}</strong>
                        <span class="status-pill ${statusPillClass}">
                            ${statusPillText}
                        </span>
                    </div>
                    <div class="station-body" style="font-size: 11px; margin-top: 6px;">
                        <div>Loại trạm: <b>${typeLabel}</b></div>
                        ${slotInfo}
                    </div>
                    <button class="btn btn-primary btn-xs btn-block mt-2 btn-popup-nav" onclick="window.driverMode?.navigateViaStationId('${st.station_id}')">
                        📍 Dẫn đường tới trạm này
                    </button>
                </div>
            `;

            marker.bindPopup(popupContent);
            if (onSelect) {
                marker.on('click', () => onSelect(st));
            }

            try {
                marker.addTo(this.layers.stations);
                this.stationMarkers.set(st.station_id, marker);
            } catch (err) {
                console.error('[Map] Error adding station marker:', st.station_id, err);
            }

            if (isRecommended) {
                this.recommendedStationMarker = marker;
            }
        });

        console.log('[Map] renderStations complete, markers created:', this.stationMarkers.size);
    }

    /**
     * Auto-fit bounds around all active routes, driver, and destination.
     */
    fitBoundsToActive(extraPoints = []) {
        const points = [...extraPoints];

        if (this.driverMatchedMarker) {
            points.push(this.driverMatchedMarker.getLatLng());
        } else if (this.driverRawMarker) {
            points.push(this.driverRawMarker.getLatLng());
        }

        if (this.destinationMarker) {
            points.push(this.destinationMarker.getLatLng());
        }

        if (this.recommendedStationMarker) {
            points.push(this.recommendedStationMarker.getLatLng());
        }

        if (points.length > 0) {
            const bounds = L.latLngBounds(points);
            this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
        }
    }

    /**
     * Change cursor on map container (e.g. crosshair during destination picking).
     */
    setMapCursor(cursorStyle = '') {
        if (this.map && this.map.getContainer()) {
            this.map.getContainer().style.cursor = cursorStyle;
        }
    }
}
