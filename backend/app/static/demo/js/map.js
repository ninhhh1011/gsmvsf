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

        // Crisp, modern CartoDB Positron / OSM tiles
        this.layers.baseTiles = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
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

    /**
     * Render direct trip route from origin to destination using real GraphHopper polyline.
     */
    renderDirectRoute(encodedGeometry) {
        this.layers.directRoute.clearLayers();
        if (!encodedGeometry) return;

        const coords = decodePolyline(encodedGeometry);
        if (coords.length === 0) return;

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
    renderStations(stations, recommendedId = null, recommendedService = null, onSelect = null) {
        this.layers.stations.clearLayers();
        this.stationMarkers.clear();

        stations.forEach(st => {
            const isRecommended = st.station_id === recommendedId;
            const isEligible = st.eligible !== false;
            const isSwap = (isRecommended && recommendedService === 'BATTERY_SWAP') || st.station_type === 'SWAP' || (st.service_type === 'BATTERY_SWAP');

            let markerHtml = '';
            let iconSize = [24, 24];
            let anchor = [12, 12];

            if (isRecommended) {
                iconSize = [36, 36];
                anchor = [18, 18];
                const badgeColor = isSwap ? '#8b5cf6' : '#10b981';
                markerHtml = `
                    <div class="station-marker-rec" style="border-color: ${badgeColor};">
                        <div class="rec-badge" style="background: ${badgeColor};">
                            ${isSwap ? 'SWAP' : 'CHARGE'}
                        </div>
                        <span class="station-code">${st.station_id}</span>
                    </div>
                `;
            } else if (isEligible) {
                const color = isSwap ? '#8b5cf6' : '#0d9488';
                markerHtml = `
                    <div class="station-marker-eligible" style="border-color: ${color};">
                        <div class="station-dot" style="background: ${color};"></div>
                    </div>
                `;
            } else {
                markerHtml = `
                    <div class="station-marker-ineligible" title="${st.reason || 'Ineligible'}">
                        <div class="station-dot-gray"></div>
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
                zIndexOffset: isRecommended ? 1000 : (isEligible ? 500 : 100)
            });

            const popupContent = `
                <div class="station-popup">
                    <div class="station-header">
                        <strong>${st.station_id}</strong>
                        <span class="status-pill ${isRecommended ? 'pill-rec' : (isEligible ? 'pill-eligible' : 'pill-ineligible')}">
                            ${isRecommended ? 'RECOMMENDED' : (isEligible ? 'ELIGIBLE' : (st.reason || 'INELIGIBLE'))}
                        </span>
                    </div>
                    <div class="station-body" style="font-size: 11px; margin-top: 4px;">
                        <div>Type: <b>${st.station_type || st.service_type || 'N/A'}</b></div>
                        <div>Slots: <b>${st.total_slots || (st.charging_slots + st.swap_slots) || 'N/A'}</b> (Charge: ${st.charging_slots ?? '-'}, Swap: ${st.swap_slots ?? '-'})</div>
                        ${st.queue_wait_min !== undefined ? `<div>Queue wait: <b>${st.queue_wait_min.toFixed(1)} min</b></div>` : ''}
                        ${st.final_cost_s !== undefined ? `<div>Est. Completion: <b>${(st.final_cost_s / 60).toFixed(1)} min</b></div>` : ''}
                    </div>
                </div>
            `;

            marker.bindPopup(popupContent);
            if (onSelect) {
                marker.on('click', () => onSelect(st));
            }

            marker.addTo(this.layers.stations);
            this.stationMarkers.set(st.station_id, marker);

            if (isRecommended) {
                this.recommendedStationMarker = marker;
            }
        });
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
}
