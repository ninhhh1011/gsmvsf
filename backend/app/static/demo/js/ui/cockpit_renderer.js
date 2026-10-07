/**
 * Cockpit UI HTML Template Renderers.
 * Pure rendering functions returning HTML strings, completely decoupled from map or API calls.
 */

import { renderEnergyWarningBanner, renderRecommendationCard, renderCostBreakdown } from '../components.js';
import { escapeHtml } from '../domain/route-display.js';

export function renderBatteryView({ soc, range }) {
    const percent = soc.toFixed(0);
    const rangeKm = range.toFixed(0);
    const critical = soc < 20;
    const warning = soc < 30;
    const color = critical ? '#ef4444' : warning ? '#f59e0b' : '#10b981';
    return {
        labelText: `${percent}% (${rangeKm} km)`, labelColor: color,
        socText: `${percent}%`, socClass: `stat-value ${critical ? 'text-danger' : ''}`,
        rangeText: `${rangeKm} km`, batteryWidth: `${Math.max(5, soc)}%`,
        batteryClass: `battery-bar-fill ${critical ? 'bg-danger' : warning ? 'bg-warning' : 'bg-success'}`,
        sliderValue: String(Math.round(soc))
    };
}

export function renderActiveCockpitView(state) {
    return {
        ...renderBatteryView(state),
        distanceText: `${state.distance.toFixed(1)} km`,
        etaText: `${state.eta} phút`
    };
}

export function renderTripActiveEta(recommendation, remainingDistanceKm) {
    if (recommendation?.ranked_candidates?.length > 0) {
        return (recommendation.ranked_candidates[0].eta_to_station_s / 60).toFixed(0);
    }
    return remainingDistanceKm > 0 ? Math.round(remainingDistanceKm * 2).toString() : '—';
}

export function renderStatusBadge(state, label) {
    return { label, accessibleState: state, className: `status-badge badge-${state.toLowerCase()}` };
}

export function renderVehicleOptions(vehicles) {
    return vehicles.map(({ id, name, battery_kwh }) => ({ id, label: `${name} (${battery_kwh.toFixed(1)} kWh)` }));
}

export function renderCoordinateText(coords) {
    return `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`;
}

export function renderCostBreakdownHTML(candidate) {
    return renderCostBreakdown(candidate);
}

export function renderEnergyWarningHTML(context) {
    return renderEnergyWarningBanner(context);
}

/**
 * Render Available HUD card.
 */
export function renderAvailableCardHTML(origCoords, destCoords) {
    const origLat = (origCoords?.latitude || 20.9849).toFixed(4);
    const origLng = (origCoords?.longitude || 105.7935).toFixed(4);
    const destLat = (destCoords?.latitude || 21.0285).toFixed(4);
    const destLng = (destCoords?.longitude || 105.8542).toFixed(4);

    return `
        <div class="driver-available-card">
            <div class="card-status-indicator">
                <span class="pulse-dot green"></span>
                <h3>Sẵn sàng bắt đầu hành trình</h3>
            </div>
            <p class="text-muted" style="margin-top: 4px; font-size: 13px;">
                Dẫn đường thông minh & phân tích lộ trình thói quen. Thiết lập điểm xuất phát và điểm đến:
            </p>

            <div class="endpoints-box mt-3" style="background: rgba(255,255,255,0.04); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px;">
                <div style="display: flex; align-items: center; justify-content: space-between; font-size: 13px; margin-bottom: 8px;">
                    <span style="color: #10b981; font-weight: 600;">📍 Điểm A (Xuất phát):</span>
                    <span id="text-origin-coords" class="text-muted" style="font-size: 12px; font-family: monospace;">${origLat}, ${origLng}</span>
                </div>
                <div style="display: flex; align-items: center; justify-content: space-between; font-size: 13px;">
                    <span style="color: #ef4444; font-weight: 600;">🏁 Điểm B (Điểm đến):</span>
                    <span id="text-dest-coords" class="text-muted" style="font-size: 12px; font-family: monospace;">${destLat}, ${destLng}</span>
                </div>
            </div>

            <div class="driver-actions mt-3">
                <div style="display: flex; gap: 8px; margin-bottom: 10px;">
                    <button id="btn-pick-origin-map" class="btn btn-outline flex-1" style="font-size: 13px;">
                        📍 Đổi điểm đi (A)
                    </button>
                    <button id="btn-pick-dest-map" class="btn btn-outline flex-1" style="font-size: 13px;">
                        🏁 Đổi điểm đến (B)
                    </button>
                </div>
                <button id="btn-accept-trip" class="btn btn-primary btn-lg btn-block">
                    🚀 Tạo lộ trình & Bắt đầu
                </button>
                <button id="btn-go-offline" class="btn btn-outline btn-sm mt-2">
                    Chuyển ngoại tuyến
                </button>
            </div>
        </div>
    `;
}

/**
 * Render Offline HUD card.
 */
export function renderOfflineCardHTML() {
    return `
        <div class="driver-available-card text-center">
            <span class="pulse-dot gray"></span>
            <h3>Tài xế đang ngoại tuyến</h3>
            <p class="text-muted">Bật trực tuyến để nhận phân phối chuyến đi.</p>
            <button id="btn-go-online" class="btn btn-primary btn-lg mt-3">
                Bật trực tuyến
            </button>
        </div>
    `;
}

export function renderPositionStatusHTML(matchedPos, currentPos) {
    if (matchedPos) {
        const roadId = escapeHtml(matchedPos.road_segment_id || 'đã khớp');
        return `<span class="text-success">Khớp đường: ${roadId} <span class="sr-only">Road: ${roadId}</span></span>`;
    }
    if (currentPos) {
        const format = value => Number.isFinite(Number(value)) ? Number(value).toFixed(4) : escapeHtml(String(value));
        return `<span class="text-warning">GPS trực tiếp (${format(currentPos.latitude)}, ${format(currentPos.longitude)}) <span class="sr-only">Raw GPS</span></span>`;
    }
    return '<span class="text-muted">Đang định vị...</span>';
}

export function renderPostTripBannerHTML(station, route) {
    if (!station) return '';
    const distance = Number(route?.distance_m);
    const distanceKm = Number.isFinite(distance) && distance ? (distance / 1000).toFixed(1) : '1.5';
    return `
        <div class="post-trip-banner" style="background: rgba(15, 23, 42, 0.85); border: 1px solid #0d9488; border-radius: 10px; padding: 12px 14px; margin-top: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; color: #2dd4bf; font-size: 13px; display: flex; align-items: center; gap: 6px;">🏁 ĐÃ ĐẶT SẠC SAU KHI TỚI B</span>
                <button id="btn-cancel-post-trip" class="btn btn-outline btn-xs" style="color: #94a3b8; border-color: #475569; padding: 2px 6px;">✕ Hủy</button>
            </div>
            <div style="font-size: 12px; color: #e2e8f0; margin-top: 6px;">Xe đang chạy thẳng đến điểm B. Sau khi trả khách sẽ tiếp tục di chuyển đến <strong>Trạm ${escapeHtml(station.station_id)}</strong> (${distanceKm} km).</div>
        </div>`;
}

/**
 * Render Trip Complete HUD card.
 */
export function renderTripCompleteCardHTML(lastRecommendation, postTripStation) {
    const warningBanner = renderEnergyWarningBanner(lastRecommendation?.energy_context);
    const recCard = renderRecommendationCard(lastRecommendation);

    return `
        <div class="driver-nav-hud">
            <div class="completion-header text-center" style="text-align: center; margin-bottom: 16px;">
                <span class="check-icon" style="display: inline-block; width: 44px; height: 44px; line-height: 44px; background: rgba(16, 185, 129, 0.2); color: #10b981; border-radius: 50%; font-size: 22px; font-weight: bold; margin-bottom: 8px;">✓</span>
                <h3>Chuyến đi hoàn tất</h3>
                <p class="text-muted" style="font-size: 13px;">Hành khách đã xuống xe an toàn.</p>
            </div>

            ${warningBanner}

            ${postTripStation ? `
                <div style="background: rgba(13, 148, 136, 0.12); border: 1px solid #0d9488; border-radius: 10px; padding: 14px; margin-top: 12px; margin-bottom: 12px;">
                    <div style="font-weight: 700; color: #0d9488; font-size: 14px;">⚡ BƯỚC TIẾP THEO: ĐI SẠC PIN</div>
                    <p style="font-size: 13px; color: #cbd5e1; margin: 4px 0 10px 0;">
                        Bạn đã chọn sạc tại <strong>Trạm ${escapeHtml(postTripStation.station_id)}</strong> (${escapeHtml(postTripStation.name || '')}) sau khi trả khách.
                    </p>
                    <button id="btn-start-post-trip-nav" class="btn btn-success btn-lg btn-block">
                        ⚡ Dẫn đường tới Trạm ${escapeHtml(postTripStation.station_id)} ngay
                    </button>
                </div>
            ` : ''}

            <div class="mt-3">
                ${recCard}
            </div>

            <div class="driver-actions mt-4">
                <button id="btn-back-available" class="btn btn-primary btn-lg btn-block">
                    Sẵn sàng chuyến tiếp theo
                </button>
            </div>
        </div>
    `;
}


export function renderTripAssignedCardHTML(controller) {
    const battery = renderBatteryView({ soc: controller.currentSocPct, range: controller.estimatedRangeKm });
    return `
            <div class="driver-nav-hud">
                <div class="hud-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span class="badge badge-info">
                        ĐÃ NHẬN CHUYẾN
                        <span class="sr-only">TRIP_ASSIGNED TRIP ASSIGNED</span>
                    </span>
                    <h3 style="margin: 0; font-size: 18px;">${escapeHtml(controller.currentTrip?.trip_id || '')}</h3>
                </div>

                <div class="hud-details" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px;">
                    <div class="stat-box">
                        <span class="stat-label">Phương tiện</span>
                        <strong class="stat-value" style="font-size: 14px;">${escapeHtml(controller.currentVehicle?.vehicle_model || 'VF 3')}</strong>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">Cự ly dự kiến</span>
                        <strong class="stat-value" style="font-size: 14px;">${(controller.currentTrip?.planned_distance_m / 1000).toFixed(1)} km</strong>
                    </div>
                    <div class="stat-box">
                        <span class="stat-label">Dung lượng Pin</span>
                        <strong id="val-assigned-soc" class="stat-value" style="font-size: 14px;">${controller.currentSocPct.toFixed(0)}%</strong>
                    </div>
                </div>

                <!-- Interactive Battery SOC Adjuster -->
                <div class="cockpit-soc-control" style="margin-bottom: 14px; padding: 10px 12px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase;">
                            🔋 Tùy chỉnh mức Pin ban đầu (SOC)
                        </span>
                        <span id="label-assigned-soc-val" style="font-size: 12px; font-weight: 700; color: ${battery.labelColor};">
                            ${battery.labelText}
                        </span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <input type="range" id="slider-assigned-soc" min="5" max="100" step="1" value="${battery.sliderValue}"
                               style="flex: 1; accent-color: #0d9488; cursor: pointer; height: 6px;">
                        <div style="display: flex; gap: 4px;">
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="12" style="padding: 2px 6px; font-size: 11px; color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">12%</button>
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="22" style="padding: 2px 6px; font-size: 11px; color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">22%</button>
                            <button type="button" class="btn btn-outline btn-xs btn-preset-assigned-soc" data-soc="85" style="padding: 2px 6px; font-size: 11px; color: #10b981; border-color: rgba(16, 185, 129, 0.5);">85%</button>
                        </div>
                    </div>
                </div>

                <div class="driver-actions">
                    <button id="btn-start-driving" class="btn btn-success btn-lg btn-block">
                        ▶ Bắt đầu lái xe
                    </button>
                    <div style="display: flex; gap: 8px; margin-top: 8px;">
                        <button id="btn-assigned-pick-origin" class="btn btn-outline flex-1" style="font-size: 13px;">
                            📍 Đổi điểm xuất phát (A)
                        </button>
                        <button id="btn-assigned-pick-dest" class="btn btn-outline flex-1" style="font-size: 13px;">
                            🏁 Đổi điểm đến (B)
                        </button>
                    </div>
                    <button id="btn-cancel-trip" class="btn btn-outline btn-sm mt-2">
                        Hủy nhận chuyến
                    </button>
                </div>
            </div>
        `;
}

export function renderTripActiveCardHTML(controller, { warningBanner, etaMin, posStatus, progress, recSnippet, postTripSnippet, playBtnClass, playBtnText, pauseBtnClass }) {
    const battery = renderBatteryView({ soc: controller.currentSocPct, range: controller.estimatedRangeKm });
    return `
            <div class="driver-nav-hud" id="driver-active-hud" data-hud-state="TRIP_ACTIVE">
                <div id="hud-warning-container">
                    ${warningBanner}
                </div>

                <div class="nav-metrics-card">
                    <div class="nav-destination" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div>
                            <span class="text-sm text-muted" style="font-size: 11px; text-transform: uppercase;">Điểm đến</span>
                            <div class="dest-name" style="font-weight: 700; font-size: 16px;">
                                Điểm trả khách
                                <span class="sr-only">Passenger Drop-off (Trả khách)</span>
                            </div>
                        </div>
                        <span class="badge badge-teal">Đang di chuyển</span>
                    </div>

                    <div class="nav-stats-grid" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px;">
                        <div class="stat-box">
                            <span class="stat-label">Cự ly còn lại</span>
                            <span class="stat-value" id="val-remaining-dist">${controller.remainingTripDistanceKm.toFixed(1)} <small>km</small></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">ETA</span>
                            <span class="stat-value" id="val-trip-eta">${etaMin} <small>phút</small><span class="sr-only">min</span></span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Pin (SOC)</span>
                            <span class="${battery.socClass}" id="val-trip-soc">${battery.socText}</span>
                        </div>
                        <div class="stat-box">
                            <span class="stat-label">Tầm xa</span>
                            <span class="stat-value" id="val-trip-range">${controller.estimatedRangeKm.toFixed(0)} <small>km</small></span>
                        </div>
                    </div>

                    <div class="battery-bar-container" style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden;">
                        <div id="battery-bar-fill" class="${battery.batteryClass}"
                             style="width: ${battery.batteryWidth}; height: 100%;"></div>
                    </div>

                    <!-- Interactive Battery SOC Adjuster -->
                    <div class="cockpit-soc-control" style="margin-top: 10px; padding: 8px 10px; background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(51, 65, 85, 0.7); border-radius: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase;">
                                🔋 Điều chỉnh mức Pin (SOC)
                            </span>
                            <span id="label-soc-slider-val" style="font-size: 12px; font-weight: 700; color: ${battery.labelColor};">
                                ${battery.labelText}
                            </span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <input type="range" id="slider-cockpit-soc" min="5" max="100" step="1" value="${battery.sliderValue}"
                                   style="flex: 1; accent-color: #0d9488; cursor: pointer; height: 6px;">
                            <div class="quick-soc-presets" style="display: flex; gap: 4px;">
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="12" title="Mức pin nguy cấp (< 15%)"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #ef4444; border-color: rgba(239, 68, 68, 0.5);">12%</button>
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="22" title="Mức pin khuyến cáo (< 30%)"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #f59e0b; border-color: rgba(245, 158, 11, 0.5);">22%</button>
                                <button type="button" class="btn btn-outline btn-xs btn-quick-soc" data-soc="85" title="Mức pin an toàn"
                                        style="padding: 2px 6px; font-size: 11px; font-weight: 600; color: #10b981; border-color: rgba(16, 185, 129, 0.5);">85%</button>
                            </div>
                        </div>
                    </div>

                    <div class="text-xs text-muted mt-2" style="display: flex; justify-content: space-between; font-size: 11px;">
                        <span id="hud-pos-status">${posStatus}</span>
                        <span id="hud-progress-status">${progress}</span>
                    </div>
                </div>

                <div id="hud-rec-container">
                    ${recSnippet}
                </div>

                <div id="hud-post-trip-container">
                    ${postTripSnippet}
                </div>

                <div class="driver-controls mt-3">
                    <div class="replay-controls d-flex gap-2 mb-2" style="display: flex; gap: 8px;">
                        <button id="btn-driver-replay-play" class="${playBtnClass}">${playBtnText}</button>
                        <button id="btn-driver-replay-pause" class="${pauseBtnClass}">⏸ Tạm dừng</button>
                        <button id="btn-driver-replay-step" class="btn btn-outline btn-sm flex-1">⏭ Từng bước</button>
                    </div>
                    <button id="btn-change-station" class="btn btn-sm btn-outline-secondary" style="margin-top: 6px; width: 100%; display: ${controller._navigationLocked ? 'block' : 'none'};">
                        🔄 Đổi trạm sạc khác
                    </button>
                    <button id="btn-complete-trip" class="btn btn-outline btn-sm btn-block">
                        ✓ Hoàn thành chuyến đi
                    </button>
                </div>
            </div>
        `;
}
