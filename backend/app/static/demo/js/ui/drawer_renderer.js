/**
 * Drawer Renderer module for Driver Mode.
 * Generates HTML markup for station drawer cards, list views, and badges.
 * Pure rendering functions - decoupled from DOM mutation and network calls.
 */

import { escapeHtml, formatDistanceKm, formatDuration } from '../domain/route-display.js';

/**
 * Render a single station card for the drawer list.
 * @param {Object} st - Station object.
 * @param {Object} options - Rendering options.
 * @returns {string} HTML string.
 */
export function renderDrawerStationCard(st, options = {}) {
    const { isRec = false, isAtDest = false, activeRec = null, activeCand = null, dest = null } = options;
    const filteredService = options.serviceFilter === 'SWAP' ? 'BATTERY_SWAP' : options.serviceFilter === 'FAST_DC' ? 'CHARGING' : null;
    const requestedService = filteredService || st.service_type;
    const ranked = options.rankedCandidate && (!requestedService || options.rankedCandidate.service_type === requestedService) ? options.rankedCandidate : activeRec?.ranked_candidates?.find(c => c.station_id === st.station_id && (!requestedService || c.service_type === requestedService));
    const service = ranked?.service_type || requestedService;
    const cand = activeCand?.find(c => c.station_id === st.station_id && (!service || c.service_type === service));
    const features = ranked?.features || {};
    const metrics = cand?.route_metrics || {};
    const minutes = value => value != null && Number.isFinite(value) ? Math.round(value / 60) : '—';
    const km = value => value != null && Number.isFinite(value) ? (value / 1000).toFixed(1) : '—';
    const totalTravel = ranked?.eta_to_station_s ?? metrics.duration_to_station_s;
    const travel = isAtDest && totalTravel != null && features.prior_travel_duration_s != null ? totalTravel - features.prior_travel_duration_s : totalTravel;
    const totalDistance = features.distance_to_station_m ?? metrics.distance_to_station_m;
    const stationDistance = isAtDest && totalDistance != null && features.prior_travel_distance_m != null ? totalDistance - features.prior_travel_distance_m : totalDistance;
    const wait = features.effective_queue_wait_s ?? ranked?.queue_wait_s;
    const duration = features.service_duration_s ?? ranked?.service_duration_s;
    const total = ranked?.total_completion_time_s ?? ranked?.eta_to_destination_via_station_s ?? ranked?.service_completion_time_s;
    const queueAssumed = features.observed_queue_wait_s == null && wait != null;
    const eligible = !!ranked && ranked.eligible !== false && cand?.eligible !== false && st.station_state !== 'offline';
    const swap = service === 'BATTERY_SWAP' || st.station_type === 'SWAP';
    const serviceLabel = swap ? 'Đổi pin' : 'Sạc';
    const hasDestination = !!dest || features.duration_station_to_dest_s != null;
    const familiar = ranked?.familiarity;
    const percentage = value => value != null ? `${Math.round(value * 100)}%` : 'Chưa đủ dữ liệu';
    return `<div class="station-drawer-card ${isRec ? 'is-recommended' : ''}" data-station-id="${escapeHtml(st.station_id)}">
        <div class="station-card-top"><div><span class="station-card-name">Trạm ${escapeHtml(st.station_id)}</span>
        ${isRec ? '<span class="badge-rec-hero">⭐ ĐỀ XUẤT TỐI ƯU</span>' : ranked ? `<span class="badge badge-teal">Hạng #${ranked.rank}</span>` : ''}
        <div>${escapeHtml(st.name || st.station_id)}</div></div><span class="badge badge-teal">${serviceLabel}</span></div>
        <div class="station-cost-grid">
          <div class="cost-grid-item"><span class="cost-grid-label">${isAtDest ? 'Cự ly từ Điểm đến (B) ➔ Trạm' : 'Chặng 1 (Xe ➔ Trạm)'}</span><span class="cost-grid-val">${km(stationDistance)} km <small>(${minutes(travel)} phút)</small></span></div>
          <div class="cost-grid-item"><span class="cost-grid-label">Tại trạm (Chờ + ${serviceLabel})</span><span class="cost-grid-val">${minutes(wait)}p chờ${queueAssumed ? ' (ước tính)' : ''} · ${minutes(duration)}p ${serviceLabel.toLowerCase()} <small>(${features.available_capacity ?? '—'} cổng)</small></span></div>
          ${isAtDest ? `<div class="cost-grid-item"><span class="cost-grid-label">Chuyến chính (A ➔ B thẳng)</span><span class="cost-grid-val">${minutes(features.prior_travel_duration_s)} phút</span></div>` : hasDestination ? `<div class="cost-grid-item"><span class="cost-grid-label">Chặng 2 (Trạm ➔ B)</span><span class="cost-grid-val">${km(features.distance_station_to_dest_m ?? metrics.distance_station_to_dest_m)} km <small>(${minutes(features.duration_station_to_dest_s ?? metrics.duration_station_to_dest_s)} phút)</small></span></div><div class="cost-grid-item"><span class="cost-grid-label">Lệch lộ trình (Detour)</span><span class="cost-grid-val">${km(features.detour_distance_m ?? metrics.detour_distance_m)} km</span></div>` : ''}
        </div>
        <div class="station-cost-summary"><span class="total-eta">Tổng thời gian hoàn thành: <strong>${minutes(total)} phút</strong></span>
        ${ranked?.ranking_score != null || ranked?.score != null ? `<span class="cost-score">Điểm xếp hạng 80/10/10: <strong>${(ranked.ranking_score ?? ranked.score).toFixed(3)}</strong></span>` : ''}</div>
        ${familiar ? `<details><summary>Độ quen và mức phổ biến</summary><p>Cá nhân: ${percentage(familiar.personal_adherence)} · Cộng đồng: ${percentage(familiar.community_adherence)}<br/>${familiar.personal_trip_count ?? 0} chuyến cá nhân · ${familiar.community_driver_count ?? 0} tài xế cùng hành lang</p></details>` : ''}
        ${cand?.eligible === false ? `<div class="badge badge-danger">${escapeHtml(cand.reason || 'Không phù hợp')}</div>` : ''}
        <div class="driver-primary-actions"><button class="btn btn-outline btn-xs btn-zoom-station" data-lat="${st.latitude}" data-lng="${st.longitude}">Xem vị trí</button>
        ${eligible ? `<button class="btn btn-primary btn-sm ${isAtDest ? 'btn-nav-post-trip-station' : 'btn-nav-drawer-station'}" data-station-id="${escapeHtml(st.station_id)}" data-service-type="${escapeHtml(service || '')}">${isAtDest ? 'Đến B rồi ghé trạm' : 'Dẫn đường ghé trạm'}</button>` : '<span>Chưa có phương án phù hợp</span>'}</div>
    </div>`;
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
    const byId = new Map(stations.map(st => [st.station_id, st]));
    const seen = new Set();
    const pairs = [...(options.activeRec?.ranked_candidates || [])].sort((a,b) => a.rank - b.rank).filter(pair => { const key = `${pair.station_id}:${pair.service_type}`; if (seen.has(key)) return false; seen.add(key); return true; }).filter(pair => byId.has(pair.station_id) &&
        (options.serviceFilter !== 'FAST_DC' || pair.service_type === 'CHARGING') &&
        (options.serviceFilter !== 'SWAP' || pair.service_type === 'BATTERY_SWAP')).sort((a,b) => a.rank - b.rank);
    const topIds = [...new Set(pairs.map(pair => pair.station_id))].slice(0,5);
    const card = pair => renderDrawerStationCard({ ...byId.get(pair.station_id), service_type: pair.service_type }, {
        ...options, rankedCandidate: pair, isRec: pair.rank === 1,
        isSelectedPostTrip: options.postTripStationId === pair.station_id
    });
    const top = pairs.filter(pair => topIds.includes(pair.station_id));
    const remainingPairs = pairs.filter(pair => !topIds.includes(pair.station_id));
    const unranked = stations.filter(st => !pairs.some(pair => pair.station_id === st.station_id));
    const remaining = remainingPairs.map(card).join('') + unranked.map(st => renderDrawerStationCard(st, options)).join('');
    if (!top.length) return remaining;
    return `<section class="drawer-top-five" aria-label="Top-5 đề xuất"><h3>Top-5 đề xuất (${topIds.length} trạm)</h3>${top.map(card).join('')}</section>
        ${remaining ? `<details class="drawer-other-stations"><summary>Các trạm khác (${new Set([...remainingPairs,...unranked].map(item => item.station_id)).size})</summary>${remaining}</details>` : ''}`;

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
