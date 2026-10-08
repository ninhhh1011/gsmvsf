/**
 * Drawer Renderer module for Driver Mode.
 * Generates HTML markup for station drawer cards, list views, and badges.
 * Pure rendering functions - decoupled from DOM mutation and network calls.
 */

import { straightLineDistanceKm } from '../domain/vehicle_model.js';
import { escapeHtml, formatDistanceKm, formatDuration } from '../domain/route-display.js';

/**
 * Render a single station card for the drawer list.
 * @param {Object} st - Station object.
 * @param {Object} options - Rendering options.
 * @returns {string} HTML string.
 */
export function renderDrawerStationCard(st, options = {}) {
    const {
        isRec = false,
        isAtDest = false,
        activeRec = null,
        activeCand = null,
        dest = { latitude: 21.0285, longitude: 105.8542 },
        directDistKm = 5.0,
        isSelectedPostTrip = false,
        remainingTripDistanceKm = 5.0,
    } = options;

    const isSwap = st.station_type === 'SWAP' || st.service_type === 'BATTERY_SWAP';
    const typeBadge = isSwap
        ? `<span class="badge badge-purple">🔋 Đổi pin</span>`
        : `<span class="badge badge-teal">⚡ Sạc nhanh DC</span>`;

    const totalSlots = st.total_slots || (st.charging_slots + st.swap_slots) || 'Đang mở';

    const ranked = activeRec?.ranked_candidates?.find(c => c.station_id === st.station_id);
    const cand = activeCand?.find(c => c.station_id === st.station_id);

    const fallbackLeg2Dist = straightLineDistanceKm(st.latitude, st.longitude, dest.latitude, dest.longitude);
    const fallbackLeg2Min = Math.max(1, Math.round(fallbackLeg2Dist * 2.2));
    const fallbackDetourKm = Math.max(0, parseFloat(st.distKm || '0') + fallbackLeg2Dist - directDistKm).toFixed(1);
    const fallbackDetourMin = Math.max(0, Math.round(fallbackDetourKm * 2.2));

    let leg1Dist = st.distKm || '—';
    let leg1Min = Math.round(parseFloat(st.distKm || '0') * 2.2);
    let leg2Dist = '—';
    let leg2Min = '—';
    let detourKm = '—';
    let detourMin = '—';
    let waitMin = 0;
    let serviceMin = isSwap ? 5 : 20;
    let totalEtaMin = '—';
    let slots = totalSlots;
    let statusBadge = '';

    let bToStationDist = fallbackLeg2Dist.toFixed(1);
    let bToStationMin = fallbackLeg2Min;

    if (isAtDest) {
        if (ranked) {
            const d = ranked.features?.distance_to_station_m || ranked.distance_vehicle_to_station_m;
            if (d) bToStationDist = (d / 1000).toFixed(1);
            if (ranked.eta_to_station_s) bToStationMin = Math.round(ranked.eta_to_station_s / 60);
        } else if (cand?.route_metrics?.distance_to_station_m) {
            bToStationDist = (cand.route_metrics.distance_to_station_m / 1000).toFixed(1);
            if (cand.route_metrics.duration_to_station_s) {
                bToStationMin = Math.round(cand.route_metrics.duration_to_station_s / 60);
            }
        }
    }

    if (ranked) {
        const d1 = ranked.features?.distance_to_station_m || ranked.distance_vehicle_to_station_m;
        if (d1) leg1Dist = (d1 / 1000).toFixed(1);
        if (ranked.eta_to_station_s) leg1Min = Math.round(ranked.eta_to_station_s / 60);
        const d2 = ranked.features?.distance_station_to_dest_m || ranked.distance_station_to_dest_m;
        if (d2) leg2Dist = (d2 / 1000).toFixed(1);
        const t2 = ranked.features?.duration_station_to_dest_s || ranked.duration_station_to_dest_s;
        if (t2) leg2Min = Math.round(t2 / 60);
        const detD = ranked.features?.detour_distance_m !== undefined ? ranked.features.detour_distance_m : ranked.detour_distance_m;
        if (detD !== undefined) detourKm = (detD / 1000).toFixed(1);
        const detT = ranked.features?.detour_duration_s !== undefined ? ranked.features.detour_duration_s : ranked.detour_duration_s;
        if (detT !== undefined) detourMin = Math.round(detT / 60);

        if (ranked.features?.observed_queue_wait_s !== undefined) {
            waitMin = Math.round(ranked.features.observed_queue_wait_s / 60);
        } else if (ranked.queue_wait_s !== undefined) {
            waitMin = Math.round(ranked.queue_wait_s / 60);
        }
        if (ranked.features?.service_duration_s !== undefined) {
            serviceMin = Math.round(ranked.features.service_duration_s / 60);
        } else if (ranked.service_duration_s !== undefined) {
            serviceMin = Math.round(ranked.service_duration_s / 60);
        }
        if (ranked.eta_to_destination_via_station_s !== undefined) {
            totalEtaMin = Math.round(ranked.eta_to_destination_via_station_s / 60);
        } else if (leg2Min !== '—') {
            totalEtaMin = leg1Min + waitMin + serviceMin + parseInt(leg2Min, 10);
        }
        slots = ranked.available_slots ?? (cand?.operational?.available_service_slots ?? totalSlots);
        statusBadge = isRec 
            ? `<span class="badge-rec-hero">⭐ ĐỀ XUẤT TỐI ƯU ${isAtDest ? 'TẠI ĐIỂM ĐẾN (B)' : ''}</span>`
            : `<span class="badge badge-teal">Hạng #${ranked.rank}</span>`;
    } else if (cand) {
        const rm = cand.route_metrics;
        if (rm?.distance_to_station_m) leg1Dist = (rm.distance_to_station_m / 1000).toFixed(1);
        if (rm?.duration_to_station_s) leg1Min = Math.round(rm.duration_to_station_s / 60);
        if (rm?.distance_station_to_dest_m) leg2Dist = (rm.distance_station_to_dest_m / 1000).toFixed(1);
        if (rm?.duration_station_to_dest_s) leg2Min = Math.round(rm.duration_station_to_dest_s / 60);
        if (rm?.detour_distance_m !== undefined) detourKm = (rm.detour_distance_m / 1000).toFixed(1);
        if (rm?.detour_duration_s !== undefined) detourMin = Math.round(rm.detour_duration_s / 60);
        waitMin = Math.round(cand.operational?.estimated_wait_min || 0);
        serviceMin = Math.round(cand.operational?.service_time_min || (isSwap ? 5 : 20));
        if (rm?.via_total_duration_s) {
            totalEtaMin = Math.round((rm.via_total_duration_s + (waitMin + serviceMin) * 60) / 60);
        } else if (leg2Dist !== '—') {
            totalEtaMin = leg1Min + waitMin + serviceMin + parseInt(leg2Min, 10);
        }
        slots = cand.operational?.available_service_slots ?? totalSlots;
        if (!cand.eligible && cand.reason) {
            statusBadge = `<span class="badge badge-danger" style="font-size:10px;">${escapeHtml(cand.reason)}</span>`;
        }
    }

    if (leg2Dist === '—') {
        leg2Dist = fallbackLeg2Dist.toFixed(1);
        leg2Min = fallbackLeg2Min;
        detourKm = fallbackDetourKm;
        detourMin = fallbackDetourMin;
        totalEtaMin = leg1Min + waitMin + serviceMin + fallbackLeg2Min;
    }

    const trafficAdjSec = ranked?.features?.traffic_adjustment_s || 0;
    const trafficAdjMin = trafficAdjSec > 0 ? (trafficAdjSec / 60).toFixed(1) : '0.0';
    const baseTravelSec = ranked?.features?.base_travel_duration_s;
    const baseTravelMin = baseTravelSec ? (baseTravelSec / 60).toFixed(1) : leg1Min;

    let cardContent = '';
    if (isAtDest) {
        const directDriveMin = Math.round((remainingTripDistanceKm || 5) * 2);
        const totalPostTripMin = directDriveMin + bToStationMin + waitMin + serviceMin;

        cardContent = `
            <div class="station-cost-grid">
                <div class="cost-grid-item" style="grid-column: span 2; background: rgba(13, 148, 136, 0.08); border: 1px solid #0d9488;">
                    <span class="cost-grid-label" style="color: #0d9488; font-weight:700;">🏁 Cự ly từ Điểm đến (B) ➔ Trạm</span>
                    <span class="cost-grid-val" style="color: #0f172a; font-size:15px; font-weight:800;">
                        ${bToStationDist} km <small style="color:#0d9488;">(${bToStationMin} phút di chuyển sau khi tới B${parseFloat(trafficAdjMin) > 0 ? ` · +${trafficAdjMin}p tắc` : ''})</small>
                    </span>
                </div>
                <div class="cost-grid-item">
                    <span class="cost-grid-label">🚗 Chuyến chính (A ➔ B thẳng)</span>
                    <span class="cost-grid-val">${(remainingTripDistanceKm || 5).toFixed(1)} km <small>(${directDriveMin} phút)</small></span>
                </div>
                <div class="cost-grid-item">
                    <span class="cost-grid-label">⚡ Tại trạm (Chờ + Sạc)</span>
                    <span class="cost-grid-val">${waitMin > 0 ? `⏳ ${waitMin}p chờ` : '✓ 0p chờ'} · ${serviceMin}p sạc <small>(${slots} cổng)</small></span>
                </div>
            </div>

            <div class="station-cost-summary">
                <span class="total-eta">⏱ Tổng thời gian (Tới B + Đến trạm + Sạc): <strong>${totalPostTripMin} phút</strong></span>
                <span class="cost-score" style="color:#0d9488; font-weight:700;">✓ Đi thẳng trả khách trước</span>
            </div>
            <div style="font-size: 11px; color: #475569; padding: 4px 8px; background: rgba(13, 148, 136, 0.06); border: 1px solid rgba(13, 148, 136, 0.2); border-radius: 4px; margin-top: 4px;">
                📊 <strong>Chi tiết chi phí (Cost):</strong> ${directDriveMin}p tới B + ${bToStationMin}p tới trạm + ${waitMin > 0 ? `<span style="color:#dc2626; font-weight:700;">${waitMin}p chờ</span>` : '<span style="color:#059669; font-weight:600;">0p chờ (trống)</span>'} + ${serviceMin}p sạc
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                <button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">
                    Xem vị trí
                </button>
                <button class="btn btn-primary btn-sm btn-nav-post-trip-station" data-station-id="${escapeHtml(st.station_id)}" style="background:${isSelectedPostTrip ? '#059669' : '#0f172a'}; border-color:${isSelectedPostTrip ? '#059669' : '#0f172a'};">
                    ${isSelectedPostTrip ? '✓ Đang chọn sạc sau khi tới B' : '🏁 Đến B rồi sạc tại đây'}
                </button>
            </div>
        `;
    } else {
        cardContent = `
            <div class="station-cost-grid">
                <div class="cost-grid-item">
                    <span class="cost-grid-label">🚗 Chặng 1 (Xe ➔ Trạm)</span>
                    <span class="cost-grid-val">${leg1Dist} km <small>(${baseTravelMin}p lái${parseFloat(trafficAdjMin) > 0 ? ` · +${trafficAdjMin}p tắc` : ' · thoáng'})</small></span>
                </div>
                <div class="cost-grid-item">
                    <span class="cost-grid-label">⚡ Tại trạm (Chờ + Sạc)</span>
                    <span class="cost-grid-val">${waitMin > 0 ? `⏳ <strong style="color:#dc2626;">${waitMin}p chờ</strong>` : '✓ <strong>0p chờ</strong>'} · ${serviceMin}p sạc <small>(${slots} cổng)</small></span>
                </div>
                <div class="cost-grid-item">
                    <span class="cost-grid-label">🏁 Chặng 2 (Trạm ➔ B)</span>
                    <span class="cost-grid-val">${leg2Dist} km <small>(${leg2Min} phút)</small></span>
                </div>
                <div class="cost-grid-item">
                    <span class="cost-grid-label">🔄 Lệch lộ trình (Detour)</span>
                    <span class="cost-grid-val" style="color:#d97706;">+${detourKm} km <small>(+${detourMin} phút)</small></span>
                </div>
            </div>

            <div class="station-cost-summary">
                <span class="total-eta">⏱ Tổng chuyến đi: <strong>${totalEtaMin} phút</strong></span>
                ${ranked?.score ? `<span class="cost-score">Cost Score: <strong>${ranked.score.toFixed(3)}</strong></span>` : ''}
            </div>
            <div style="font-size: 11px; color: #475569; padding: 4px 8px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; margin-top: 4px;">
                📊 <strong>Chi tiết chi phí (Cost):</strong> ${baseTravelMin}p lái xe + ${parseFloat(trafficAdjMin) > 0 ? `<span style="color:#d97706; font-weight:700;">+${trafficAdjMin}p tắc đường</span>` : '<span style="color:#059669; font-weight:600;">0p tắc</span>'} + ${waitMin > 0 ? `<span style="color:#dc2626; font-weight:700;">+${waitMin}p chờ</span>` : '<span style="color:#059669; font-weight:600;">0p chờ (trống)</span>'} + ${serviceMin}p sạc
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                <button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">
                    Xem vị trí
                </button>
                ${ranked?.eligible !== false ? `<button class="btn btn-primary btn-sm btn-nav-drawer-station" data-station-id="${escapeHtml(st.station_id)}">🔀 Dẫn đường ghé trạm</button>` : ''}
            </div>
        `;
    }

    return `
        <div class="station-drawer-card ${isRec ? 'is-recommended' : ''}" data-station-id="${escapeHtml(st.station_id)}">
            <div class="station-card-top">
                <div>
                    <div style="display:flex; align-items:center; gap:6px;">
                        <span class="station-card-name">Trạm ${escapeHtml(st.station_id)}</span>
                        ${statusBadge}
                    </div>
                    <div style="font-size:12px; color:#64748b; margin-top:2px;">
                        ${escapeHtml(st.name || `Trạm năng lượng ${st.station_id}`)}
                    </div>
                </div>
                ${typeBadge}
            </div>

            ${cardContent}
        </div>
    `;
}

/**
 * Render the full stations drawer list HTML.
 * @param {Array} stations - Filtered stations array.
 * @param {Object} options - Options passed to card renderer.
 * @returns {string} HTML markup.
 */
export function renderDrawerStationsListHTML(stations = [], options = {}) {
    if (!stations || stations.length === 0) {
        return `<div class="text-center text-muted p-4">Không tìm thấy trạm phù hợp với bộ lọc.</div>`;
    }
    return stations.map(st => {
        const isRec = st.station_id === options.topRecId;
        const isSelectedPostTrip = options.postTripStationId === st.station_id;
        return renderDrawerStationCard(st, {
            ...options,
            isRec,
            isSelectedPostTrip
        });
    }).join('');
}

/**
 * Render a station tooltip showing full metrics.
 * Pure rendering - no API calls on hover.
 * @param {Object} candidate - Station candidate with features.
 * @param {Array} stationCatalog - Station catalog for name lookup.
 * @returns {string} HTML string for tooltip.
 */
export function renderStationTooltipHTML(candidate, stationCatalog = []) {
    const station = stationCatalog.find(s => s.station_id === candidate.station_id);
    const feats = candidate.features || {};

    const wait = feats.effective_queue_wait_s !== null && feats.effective_queue_wait_s !== undefined
        ? formatDuration(feats.effective_queue_wait_s)
        : 'Chưa có dữ liệu';

    const capacity = feats.available_capacity !== null && feats.available_capacity !== undefined
        ? feats.available_capacity
        : '—';

    const distToStationKm = feats.distance_to_station_m != null
        ? formatDistanceKm(feats.distance_to_station_m / 1000)
        : '—';
    const etaToStation = feats.eta_to_station_s != null
        ? formatDuration(feats.eta_to_station_s)
        : '—';
    const distStationToDest = feats.distance_station_to_dest_m != null
        ? formatDistanceKm(feats.distance_station_to_dest_m / 1000)
        : '—';
    const durStationToDest = feats.duration_station_to_dest_s != null
        ? formatDuration(feats.duration_station_to_dest_s)
        : '—';
    const detourDist = feats.detour_distance_m != null
        ? formatDistanceKm(feats.detour_distance_m / 1000)
        : '—';
    const totalEta = candidate.eta_to_destination_via_station_s != null
        ? formatDuration(candidate.eta_to_destination_via_station_s)
        : '—';

    const serviceLabel = candidate.service_type === 'BATTERY_SWAP' ? 'Đổi pin' : 'Sạc';
    const serviceDur = feats.service_duration_s != null
        ? formatDuration(feats.service_duration_s)
        : '—';

    const freshClass = candidate.freshness?.station === 'STALE' || feats.station_state?.freshness === 'STALE'
        ? 'tooltip-freshness-stale'
        : 'tooltip-freshness-fresh';

    return `
        <div class="station-tooltip" data-station-id="${escapeHtml(candidate.station_id)}">
            <div class="tooltip-header">
                #${candidate.rank} ${escapeHtml(station?.name || candidate.station_id)}
                <span class="service-badge">${serviceLabel}</span>
            </div>
            <div class="tooltip-metrics">
                <div>Xe → trạm: ${distToStationKm} · ${etaToStation}</div>
                <div>Chờ: ${wait} · ${serviceLabel}: ${serviceDur}</div>
                <div>Trạm → B: ${distStationToDest} · ${durStationToDest}</div>
                <div>Đi vòng: +${detourDist}</div>
                <div class="tooltip-total">Tổng: ${totalEta}</div>
                <div>Trống: ${capacity} vị trí</div>
            </div>
            <div class="${freshClass}">
                ${candidate.freshness?.station === 'STALE' || feats.station_state?.freshness === 'STALE'
                    ? '⚠️ Dữ liệu cũ'
                    : '✓ Dữ liệu tươi'}
            </div>
            ${candidate.eligible
                ? '<button class="btn-ghe-tram">Ghé trạm này</button>'
                : '<div class="tooltip-ineligible">Không phù hợp</div>'}
        </div>
    `;
}
