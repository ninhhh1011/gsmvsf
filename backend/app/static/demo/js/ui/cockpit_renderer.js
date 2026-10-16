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
    const distance = state.distance.toFixed(1);
    const eta = escapeHtml(state.eta);
    const range = state.range.toFixed(0);
    return {
        ...renderBatteryView(state),
        distanceMarkup: `${distance} <small>km</small>`,
        etaMarkup: `${eta} <small>phút</small><span class="sr-only">min</span>`,
        rangeMarkup: `${range} <small>km</small>`,
        maxMotorText: `${state.maxMotorPowerKw ?? '—'} kW`,
        powerText: Number.isFinite(state.currentInstantPowerKw) ? `${state.currentInstantPowerKw.toFixed(1)} kW (ước tính)${state.powerStatus === 'KINEMATICS_EXCEED_CAPABILITY' ? ' (vượt khả năng)' : ''}` : '— (không khả dụng)',
        vehicleText: state.vehicleModel || '—'
    };
}

export function renderTripActiveEta(routeTiming, remainingDistanceKm) {
    if (routeTiming?.distance_m === 0 && routeTiming?.duration_s === 0 && remainingDistanceKm === 0) return '0';
    if (!Number.isFinite(routeTiming?.distance_m) || routeTiming.distance_m <= 0 || !Number.isFinite(routeTiming.duration_s) || routeTiming.duration_s < 0 || !Number.isFinite(remainingDistanceKm)) return '—';
    return String(Math.round(Math.max(0, Math.min(1, remainingDistanceKm * 1000 / routeTiming.distance_m)) * routeTiming.duration_s / 60));
}

export function renderStatusBadge(state) {
    const labels = {
        AVAILABLE: 'SẴN SÀNG',
        TRIP_ASSIGNED: '\u0110\u00c3 NH\u1eacN CHUY\u1ebeN',
        TRIP_ACTIVE: '\u0110ANG DI CHUY\u1ec2N',
        TRIP_COMPLETE: 'HO\u00c0N TH\u00c0NH',
        OFFLINE: 'NGO\u1ea0I TUY\u1ebeN'
    };
    return { label: labels[state] || state, accessibleState: state, className: `status-badge badge-${state.toLowerCase()}` };
}

export function renderReplayControls({ isPlaying, currentIndex }) {
    return {
        playText: isPlaying ? '\u25b6 \u0110ang ch\u1ea1y...' : (currentIndex > 0 ? '\u25b6 Ti\u1ebfp t\u1ee5c' : '\u25b6 B\u1eaft \u0111\u1ea7u'),
        playClass: isPlaying ? 'btn btn-outline btn-sm flex-1' : 'btn btn-primary btn-sm flex-1',
        pauseClass: isPlaying ? 'btn btn-primary btn-sm flex-1' : 'btn btn-outline btn-sm flex-1'
    };
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
export function renderAvailableCardHTML(origin = null, destination = null) {
    return `<div class="driver-available-card driver-summary">
        <h3>Sẵn sàng bắt đầu hành trình</h3>
        <p class="text-muted">Chọn điểm A để tìm trạm; thêm B nếu có điểm trả khách.</p>
        <div class="driver-primary-actions"><button id="btn-accept-trip" class="btn btn-primary btn-block">${destination ? 'Tạo lộ trình & Bắt đầu' : 'Tìm trạm từ A'}</button></div>
        <button id="btn-go-offline" class="btn btn-outline driver-expanded-only">Chuyển ngoại tuyến</button>
    </div>`;
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
export function renderTripCompleteCardHTML(lastRecommendation, postTripStation, goalRole) {
    const warningBanner = renderEnergyWarningBanner(lastRecommendation?.energy_context);
    const recCard = renderRecommendationCard(lastRecommendation);

    return `
        <div class="driver-nav-hud">
            <div class="completion-header text-center" style="text-align: center; margin-bottom: 16px;">
                <span class="check-icon" style="display: inline-block; width: 44px; height: 44px; line-height: 44px; background: rgba(16, 185, 129, 0.2); color: #10b981; border-radius: 50%; font-size: 22px; font-weight: bold; margin-bottom: 8px;">✓</span>
                <h3>${goalRole === 'STATION' ? 'Đã đến trạm' : 'Chuyến đi hoàn tất'}</h3>
                <p class="text-muted" style="font-size: 13px;">${goalRole === 'STATION' ? 'Bạn đã tới trạm đã chọn. Thời gian chờ và dịch vụ là ước tính.' : 'Hành khách đã xuống xe an toàn.'}</p>
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
    return `<div class="driver-nav-hud driver-summary">
        <h3>Đã nhận chuyến <span class="sr-only">TRIP_ASSIGNED TRIP ASSIGNED</span></h3>
        <div class="nav-stats-grid">
            <div class="stat-box"><span class="stat-label">Cự ly đường</span><strong class="stat-value">${((controller.currentTrip?.planned_distance_m || 0) / 1000).toFixed(1)} km</strong></div>
            <div class="stat-box"><span class="stat-label">ETA tới ${controller.currentTrip?.goal_role === 'STATION' ? 'trạm' : 'B'} (ước tính)</span><strong class="stat-value">${renderTripActiveEta(controller.currentRouteTiming, (controller.currentTrip?.planned_distance_m || 0) / 1000)} phút</strong></div>
            <div class="stat-box"><span class="stat-label">Pin (SOC)</span><strong id="val-assigned-soc" class="stat-value">${controller.currentSocPct.toFixed(0)}%</strong></div>
        </div>
        <div class="driver-primary-actions"><button id="btn-start-driving" class="btn btn-success btn-block">▶ Bắt đầu lái xe</button></div>
        <button id="btn-cancel-trip" class="btn btn-outline driver-expanded-only">Hủy nhận chuyến</button>
    </div>`;
}

export function renderDriverAnalysisHTML(controller, {posStatus = '', progress = ''} = {}) {
    const active = controller.state === 'TRIP_ACTIVE';
    const assigned = controller.state === 'TRIP_ASSIGNED';
    const battery = renderBatteryView({soc: controller.currentSocPct, range: controller.estimatedRangeKm});
    const view = renderActiveCockpitView({distance: controller.remainingTripDistanceKm || 0, eta: '—', soc: controller.currentSocPct, range: controller.estimatedRangeKm, maxMotorPowerKw: controller.maxMotorPowerKw, currentInstantPowerKw: controller.instantaneousPowerKw, vehicleModel: controller.currentVehicle?.vehicle_model, powerStatus: controller.powerStatus});
    const origin = controller.customOrigin || controller.currentTrip?.origin;
    const destination = controller.passengerDestination ?? controller.customDestination ?? (controller.currentTrip?.goal_role === 'STATION' ? null : controller.currentTrip?.destination);
    return `<div class="analysis-coordinates">
        <span>Điểm A: <span id="text-origin-coords">${origin ? renderCoordinateText(origin) : '—'}</span></span>
        <span>Điểm B: <span id="text-dest-coords">${destination ? renderCoordinateText(destination) : '—'}</span></span>
    </div><div class="analysis-grid">
        <span>Xe: <strong id="hud-vehicle-model">${escapeHtml(view.vehicleText)}</strong></span>
        <span>Tầm xa: <strong id="val-trip-range">${view.rangeMarkup}</strong></span>
        <span>Động cơ (Max): <strong id="hud-val-max-motor">${escapeHtml(view.maxMotorText)}</strong></span>
        <span>Công suất: <strong id="hud-val-instant-power">${escapeHtml(view.powerText)}</strong></span>
        <span id="hud-pos-status">${posStatus}</span><span id="hud-progress-status">${escapeHtml(progress)}</span>
    </div>
    ${(active || assigned) ? `<div class="cockpit-soc-control analysis-controls"><label for="${assigned ? 'slider-assigned-soc' : 'slider-cockpit-soc'}">SOC mô phỏng <span id="${assigned ? 'label-assigned-soc-val' : 'label-soc-slider-val'}">${battery.labelText}</span></label>
        <input type="range" id="${assigned ? 'slider-assigned-soc' : 'slider-cockpit-soc'}" min="5" max="100" step="1" value="${battery.sliderValue}">
        <div>${[12,22,85].map(soc => `<button type="button" class="btn btn-outline btn-sm ${assigned ? 'btn-preset-assigned-soc' : 'btn-quick-soc'}" data-soc="${soc}">${soc}%</button>`).join('')}</div></div>` : ''}
    ${active ? `<div class="analysis-controls"><span>Tốc độ replay:</span>${[1,5,10].map(speed => `<button type="button" class="btn btn-sm ${(controller.replay?.speedMultiplier || 5) === speed ? 'btn-primary' : 'btn-outline'} btn-quick-speed" data-speed="${speed}">${speed}x</button>`).join('')}
        <button id="btn-driver-replay-step" class="btn btn-outline btn-sm">⏭ Từng bước</button></div>` : ''}`;
}

export function renderTripActiveCardHTML(controller, {warningBanner, etaMin, recSnippet, postTripSnippet, replayControls}) {
    const battery = renderBatteryView({soc: controller.currentSocPct, range: controller.estimatedRangeKm});
    const destination = controller.currentTrip?.goal_role === 'STATION' ? 'Trạm đã chọn' : 'Điểm trả khách';
    return `<div class="driver-nav-hud driver-summary" id="driver-active-hud" data-hud-state="TRIP_ACTIVE">
        <div id="hud-warning-container">${warningBanner}</div>
        <div class="nav-metrics-card"><div class="nav-destination"><span class="stat-label">Điểm đến</span><strong class="dest-name">${destination}<span class="sr-only">${controller.currentTrip?.goal_role === 'STATION' ? 'Selected station' : 'Passenger Drop-off (Trả khách)'}</span></strong></div>
            <div class="nav-stats-grid">
                <div class="stat-box"><span class="stat-label">${controller.fullRouteCoords?.length >= 2 ? 'Cự ly đường còn lại' : 'Cự ly thẳng (ước tính)'}</span><span class="stat-value" id="val-remaining-dist">${controller.remainingTripDistanceKm.toFixed(1)} <small>km</small></span></div>
                <div class="stat-box"><span class="stat-label">ETA lái xe (ước tính)</span><span class="stat-value" id="val-trip-eta">${escapeHtml(etaMin)} <small>phút</small><span class="sr-only">min</span></span></div>
                <div class="stat-box"><span class="stat-label">Pin (SOC)</span><span class="${battery.socClass}" id="val-trip-soc">${battery.socText}</span></div>
            </div><div class="battery-bar-container"><div id="battery-bar-fill" class="${battery.batteryClass}" style="width:${battery.batteryWidth};height:100%"></div></div>
        </div>
        <div class="driver-primary-actions"><button id="btn-driver-stations" class="btn btn-primary btn-block">Chọn trạm sạc</button>
            <div class="replay-controls"><button id="btn-driver-replay-play" class="${replayControls.playClass}">${replayControls.playText}</button><button id="btn-driver-replay-pause" class="${replayControls.pauseClass}">⏸ Tạm dừng</button></div>
            <button id="btn-change-station" class="btn btn-outline btn-block" style="display:${controller._navigationLocked ? 'block' : 'none'}">Đổi trạm sạc khác</button>
        </div>
        <div id="hud-post-trip-container">${postTripSnippet}</div>
        <div id="hud-rec-container" class="driver-expanded-only">${recSnippet}</div>
        <button id="btn-complete-trip" class="btn btn-outline btn-block driver-expanded-only">✓ Hoàn thành chuyến đi</button>
    </div>`;
}
