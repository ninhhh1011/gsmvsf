/**
 * UI Component Renderers for VinFast EV Recommendation Demo.
 *
 * Strict rule: All energy warnings and recommendation decisions reflect backend truth.
 * No recalculation of scores or energy thresholds.
 */

import { ApiError } from './api.js';

export function classifyEnergyWarning(energyContext) {
    if (!energyContext) {
        return {
            level: 'SAFE',
            title: 'Trạng thái năng lượng: An toàn',
            testToken: 'SAFE',
            message: 'Dữ liệu pin bình thường.',
            reasonCode: 'NOMINAL'
        };
    }

    const { need_service, reason_code, estimated_remaining_range_km, remaining_trip_distance_km, energy_margin_km } = energyContext;

    if (!need_service || reason_code === 'SUFFICIENT_SOC_RANGE') {
        return {
            level: 'SAFE',
            title: 'Trạng thái năng lượng: An toàn',
            testToken: 'SAFE',
            message: 'Tầm xa ước tính đủ cho chuyến đi hiện tại và mức dự phòng an toàn.',
            reasonCode: reason_code || 'SUFFICIENT_SOC_RANGE'
        };
    }

    // Critical: Vehicle cannot reach destination
    if (
        reason_code === 'DESTINATION_NOT_REACHABLE' ||
        (estimated_remaining_range_km != null && remaining_trip_distance_km != null && estimated_remaining_range_km < remaining_trip_distance_km)
    ) {
        return {
            level: 'CRITICAL',
            title: 'Năng lượng nguy cấp',
            testToken: 'ENERGY CRITICAL',
            message: 'Tầm xa không đủ để đến đích. Cần ghé trạm sạc hoặc đổi pin ngay lập tức.',
            reasonCode: reason_code || 'DESTINATION_NOT_REACHABLE'
        };
    }

    // Advisory: Destination reachable, but insufficient post-destination reserve
    return {
        level: 'ADVISORY',
        title: 'Dự phòng năng lượng thấp',
        testToken: 'Energy Reserve Low',
        message: 'Bạn có thể hoàn tất chuyến đi hiện tại. Khuyến nghị ghé trạm bổ sung năng lượng sau khi trả khách.',
        reasonCode: reason_code || 'INSUFFICIENT_POST_DESTINATION_RESERVE'
    };
}

export function renderEnergyWarningBanner(energyContext) {
    const warning = classifyEnergyWarning(energyContext);
    const badgeClass = warning.level.toLowerCase();

    const reasonLabels = {
        'NOMINAL': 'Bình thường',
        'SUFFICIENT_SOC_RANGE': 'Pin đủ',
        'DESTINATION_NOT_REACHABLE': 'Không đủ pin đến đích',
        'LOW_SOC_AND_INSUFFICIENT_RANGE': 'Pin thấp không đủ đến đích',
        'LOW_SOC': 'Mức pin thấp',
        'INSUFFICIENT_POST_DESTINATION_RESERVE': 'Dự phòng thấp'
    };
    const friendlyReason = reasonLabels[warning.reasonCode] || warning.reasonCode;

    let iconSvg = '';
    if (warning.level === 'SAFE') {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
            </svg>
        `;
    } else if (warning.level === 'ADVISORY') {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
        `;
    } else {
        iconSvg = `
            <svg class="warning-icon" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
            </svg>
        `;
    }

    return `
        <div class="energy-warning-banner banner-${badgeClass}" role="alert">
            <div class="banner-icon">${iconSvg}</div>
            <div class="banner-content">
                <div class="banner-title">
                    ${warning.title}
                    <span class="sr-only">${warning.testToken || warning.title}</span>
                    <span class="badge-code">
                        ${friendlyReason}
                        <span class="sr-only">${warning.reasonCode}</span>
                    </span>
                </div>
                <div class="banner-desc">${warning.message}</div>
            </div>
        </div>
    `;
}

export function renderRecommendationCard(recResult, onSelectStation = null) {
    if (!recResult || !recResult.has_recommendation) {
        return `
            <div class="recommendation-card empty-card">
                <div class="card-header">
                    <h4>Không cần dịch vụ / Không có trạm phù hợp <span class="sr-only">No Service Needed / No Eligible Stations</span></h4>
                </div>
                <div class="card-body">
                    <p class="muted-text">
                        ${recResult?.reason || 'Pin hiện tại đủ cho hành trình hoặc không có trạm khả dụng.'}
                    </p>
                </div>
            </div>
        `;
    }

    const topCandidate = recResult.ranked_candidates[0];
    const stId = recResult.recommended_station_id || topCandidate?.station_id;
    const sType = recResult.recommended_service_type || topCandidate?.service_type;
    const isSwap = sType === 'BATTERY_SWAP';

    const etaStationMin = (topCandidate.eta_to_station_s / 60).toFixed(1);
    const etaStartMin = (topCandidate.eta_to_service_start_s / 60).toFixed(1);
    const etaCompleteMin = (topCandidate.eta_to_service_complete_s / 60).toFixed(1);
    const detourMin = topCandidate.features.detour_duration_s != null ? (topCandidate.features.detour_duration_s / 60).toFixed(1) : '0.0';
    const detourDistKm = topCandidate.features.detour_distance_m != null ? (topCandidate.features.detour_distance_m / 1000).toFixed(1) : '0.0';
    const queueWaitMin = (topCandidate.features.effective_queue_wait_s / 60).toFixed(1);
    const serviceMin = (topCandidate.features.service_duration_s / 60).toFixed(1);

    const isDegraded = recResult.degraded;
    const degradedBadges = (recResult.degraded_reasons || []).map(r => `<span class="badge badge-warning">${r}</span>`).join(' ');

    const stationFresh = topCandidate.features.station_state?.freshness || 'FRESH';
    const queueFresh = topCandidate.features.queue_state?.freshness || 'FRESH';

    return `
        <div class="recommendation-card ${isSwap ? 'card-swap' : 'card-charging'}">
            <div class="card-header">
                <div class="rec-title-wrap">
                    <span class="rec-badge-label">TRẠM ĐỀ XUẤT <span class="sr-only">Recommended ${isSwap ? 'Battery Swap' : 'Charging'}</span></span>
                    <h3 class="station-id">${stId}</h3>
                </div>
                <span class="service-type-pill ${isSwap ? 'pill-swap' : 'pill-charging'}">
                    ${isSwap ? '⚡ ĐỔI PIN' : '🔌 SẠC PIN'}
                </span>
            </div>

            <div class="card-grid">
                <div class="metric-item">
                    <span class="metric-label">Đến trạm</span>
                    <span class="metric-val highlight">${etaStationMin} <small>phút</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Chờ hàng đợi</span>
                    <span class="metric-val">${queueWaitMin} <small>phút</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Thời gian dịch vụ</span>
                    <span class="metric-val">${serviceMin} <small>phút</small></span>
                </div>
                <div class="metric-item">
                    <span class="metric-label">Tổng thời gian hoàn tất</span>
                    <span class="metric-val highlight-green">${etaCompleteMin} <small>phút</small></span>
                </div>
            </div>

            <div class="detour-bar">
                <span>Lệch lộ trình: <strong>+${detourDistKm} km</strong> (+${detourMin} phút)<span class="sr-only">+${detourDistKm} km detour</span></span>
                <span>Vị trí còn trống: <strong>${topCandidate.features.available_capacity} vị trí</strong></span>
            </div>
            ${topCandidate.features?.traffic_adjustment_s > 30 ? `
            <div style="background: rgba(245, 158, 11, 0.1); border-left: 3px solid #f59e0b; padding: 6px 10px; border-radius: 4px; font-size: 12px; color: #b45309; margin-top: 6px; display: flex; align-items: center; gap: 6px;">
                <span>🚦 Đã tự động tính trễ do tắc đường: <strong>+${(topCandidate.features.traffic_adjustment_s / 60).toFixed(1)} phút</strong> (đã cộng vào tổng chi phí)</span>
            </div>` : ''}

            ${isDegraded ? `<div class="degraded-notice">⚠️ Dữ liệu suy giảm: ${degradedBadges}</div>` : ''}

            <div class="card-explanation">
                <div class="exp-title">Tại sao đề xuất này?</div>
                <div class="exp-body">
                    Được chọn để giảm thiểu tổng thời gian hoàn tất: đến trạm (${etaStationMin} phút) + thời gian chờ (${queueWaitMin} phút) + thời gian dịch vụ (${serviceMin} phút) = <strong>${etaCompleteMin} phút để hoàn tất</strong>.
                </div>
            </div>

            <div class="mt-2">
                <details class="cost-details">
                    <summary>🔧 Chi tiết tính toán</summary>
                    ${renderCostBreakdown(topCandidate)}
                </details>
            </div>
        </div>
    `;
}

export function renderCostBreakdown(topCandidate) {
    const f = topCandidate?.features;
    if (!f) return '<p class="muted-text">Không có dữ liệu chi tiết.</p>';

    const baseTravel = f.base_travel_duration_s != null ? (f.base_travel_duration_s / 60).toFixed(1) : 'N/A';
    const trafficAdj = f.traffic_adjustment_s != null ? (f.traffic_adjustment_s / 60).toFixed(1) : '0.0';
    const adjTravel = f.adjusted_travel_duration_s != null ? (f.adjusted_travel_duration_s / 60).toFixed(1) : 'N/A';
    const queueWait = f.effective_queue_wait_s != null ? (f.effective_queue_wait_s / 60).toFixed(1) : '0.0';
    const serviceDur = f.service_duration_s != null ? (f.service_duration_s / 60).toFixed(1) : 'N/A';
    const distToStation = f.distance_to_station_m != null ? (f.distance_to_station_m / 1000).toFixed(1) : 'N/A';
    
    // Leg 2 and Via Total
    const leg2Dist = f.distance_station_to_dest_m != null ? (f.distance_station_to_dest_m / 1000).toFixed(1) : '-';
    const leg2Dur = f.duration_station_to_dest_s != null ? (f.duration_station_to_dest_s / 60).toFixed(1) : '-';
    const viaDist = f.via_total_distance_m != null ? (f.via_total_distance_m / 1000).toFixed(1) : '-';
    const viaDur = f.via_total_duration_s != null ? (f.via_total_duration_s / 60).toFixed(1) : '-';

    const detourDist = f.detour_distance_m != null ? (f.detour_distance_m / 1000).toFixed(1) : '0.0';
    const detourDur = f.detour_duration_s != null ? (f.detour_duration_s / 60).toFixed(1) : '0.0';
    const cap = f.available_capacity ?? 'N/A';
    const trafficMethod = f.traffic_method || 'N/A';
    const queueAssumption = f.queue_assumption || '';

    const etaComplete = topCandidate.eta_to_service_complete_s != null ? (topCandidate.eta_to_service_complete_s / 60).toFixed(1) : 'N/A';
    const etaDest = topCandidate.eta_to_destination_via_station_s != null 
        ? (topCandidate.eta_to_destination_via_station_s / 60).toFixed(1)
        : (f.duration_station_to_dest_s != null ? ((topCandidate.eta_to_service_complete_s + f.duration_station_to_dest_s) / 60).toFixed(1) : etaComplete);

    return `
        <div class="cost-breakdown-card">
            <!-- Chặng 1: A -> Trạm -->
            <div class="cost-section">
                <div class="cost-section-title">🚗 Chặng 1: Xe (A) ➔ Trạm sạc</div>
                <div class="cost-row">
                    <span>Khoảng cách đến trạm:</span>
                    <span><strong>${distToStation} km</strong></span>
                </div>
                <div class="cost-row">
                    <span>Thời gian lái xe cơ bản:</span>
                    <span>${baseTravel} phút</span>
                </div>
                <div class="cost-row">
                    <span>Độ trễ kẹt xe:</span>
                    <span style="color: #f59e0b;">+${trafficAdj} phút</span>
                </div>
                <div class="cost-row highlight">
                    <span>Thời gian đến trạm (ETA Trạm):</span>
                    <span style="color: #38bdf8;">${adjTravel} phút</span>
                </div>
            </div>

            <!-- Tại trạm: Chờ + Dịch vụ -->
            <div class="cost-section">
                <div class="cost-section-title">⚡ Tại trạm: Hàng đợi & Dịch vụ</div>
                <div class="cost-row">
                    <span>Thời gian chờ hàng đợi:</span>
                    <span>${queueWait} phút${queueAssumption ? ` (${queueAssumption})` : ''}</span>
                </div>
                <div class="cost-row">
                    <span>Thời gian sạc / đổi pin:</span>
                    <span>${serviceDur} phút</span>
                </div>
                <div class="cost-row">
                    <span>Cổng / Vị trí còn trống:</span>
                    <span style="color: #10b981;"><strong>${cap} vị trí</strong></span>
                </div>
                <div class="cost-row highlight">
                    <span>Tổng thời gian nạp xong tại trạm:</span>
                    <span style="color: #38bdf8;">${etaComplete} phút</span>
                </div>
            </div>

            <!-- Chặng 2: Trạm -> Đích B -->
            <div class="cost-section">
                <div class="cost-section-title">🏁 Chặng 2: Trạm sạc ➔ Điểm đến (B)</div>
                <div class="cost-row">
                    <span>Khoảng cách trạm về đích:</span>
                    <span>${leg2Dist} km</span>
                </div>
                <div class="cost-row highlight">
                    <span>Thời gian chạy tiếp về đích:</span>
                    <span>${leg2Dur} phút</span>
                </div>
            </div>

            <!-- Tổng hợp lộ trình & Độ lệch -->
            <div class="cost-section">
                <div class="cost-section-title">📐 So sánh lộ trình & Độ lệch (Detour)</div>
                <div class="cost-row">
                    <span>Tổng quãng đường qua trạm:</span>
                    <span>${viaDist} km (lái xe ~${viaDur} phút)</span>
                </div>
                <div class="cost-row">
                    <span>Lệch lộ trình (Detour overhead):</span>
                    <span style="color: #f59e0b;"><strong>+${detourDist} km (+${detourDur} phút)</strong></span>
                </div>
            </div>

            <!-- Tổng kết Final Cost -->
            <div class="cost-section" style="background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.3);">
                <div class="cost-section-title" style="color: #10b981;">⏱ Tổng thời gian chuyến đi (A ➔ Trạm ➔ B)</div>
                <div class="cost-row total">
                    <span>Dự kiến đến đích (bao gồm sạc):</span>
                    <span style="font-size: 16px;"><strong>${etaDest} phút</strong></span>
                </div>
                <div class="cost-row muted" style="margin-top: 4px;">
                    <span>Công thức xếp hạng:</span>
                    <span><code>final_cost_s = travel + queue + service</code> (${(topCandidate.final_cost_s / 60).toFixed(1)}p)</span>
                </div>
            </div>

            <!-- Trạng thái nguồn dữ liệu -->
            <div class="cost-section">
                <div class="cost-section-title">📡 Trạng thái dữ liệu thời gian thực</div>
                <div class="cost-row muted">
                    <span>Phương pháp tính traffic:</span>
                    <span>${trafficMethod}</span>
                </div>
                <div class="cost-row muted">
                    <span>Độ tươi trạng thái trạm:</span>
                    <span>${f.station_state?.freshness || 'N/A'}</span>
                </div>
                <div class="cost-row muted">
                    <span>Độ tươi trạng thái hàng đợi:</span>
                    <span>${f.queue_state?.freshness || 'N/A'}</span>
                </div>
            </div>
        </div>
    `;
}

export function renderPipelineLatency(timingsMs) {
    if (!timingsMs) return '';

    const loc = timingsMs.location_resolution || 0;
    const dem = timingsMs.demand || 0;
    const cand = timingsMs.candidate_search || 0;
    const rank = timingsMs.ranking || 0;
    const total = timingsMs.total || (loc + dem + cand + rank);

    const pct = (val) => Math.max(2, Math.min(100, (val / total) * 100)).toFixed(1);

    return `
        <div class="pipeline-card">
            <div class="pipeline-header">
                <h4>Chi tiết đề xuất</h4>
                <span class="total-latency">${total.toFixed(1)} ms</span>
            </div>

            <div class="pipeline-progress-bar">
                <div class="bar-seg seg-w1" style="width: ${pct(loc)}%;" title="Vị trí: ${loc.toFixed(2)} ms"></div>
                <div class="bar-seg seg-w2" style="width: ${pct(dem)}%;" title="Nhu cầu: ${dem.toFixed(2)} ms"></div>
                <div class="bar-seg seg-w3" style="width: ${pct(cand)}%;" title="Tìm trạm: ${cand.toFixed(1)} ms"></div>
                <div class="bar-seg seg-w4" style="width: ${pct(rank)}%;" title="Xếp hạng: ${rank.toFixed(1)} ms"></div>
            </div>

            <div class="pipeline-legend">
                <div class="legend-item"><span class="dot dot-w1"></span> Vị trí: <b>${loc.toFixed(2)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w2"></span> Nhu cầu: <b>${dem.toFixed(2)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w3"></span> Tìm trạm: <b>${cand.toFixed(1)} ms</b></div>
                <div class="legend-item"><span class="dot dot-w4"></span> Xếp hạng: <b>${rank.toFixed(1)} ms</b></div>
            </div>
        </div>
    `;
}

export function renderCandidateTable(candidates, rankedCandidates = []) {
    if (!candidates || candidates.length === 0) {
        return '<p class="muted-text">Không có trạm nào được đánh giá.</p>';
    }

    const rankMap = new Map();
    rankedCandidates.forEach(rc => {
        rankMap.set(`${rc.station_id}_${rc.service_type}`, rc);
    });

    const eligible = candidates.filter(c => c.eligible);
    const ineligible = candidates.filter(c => !c.eligible);

    const renderRow = (c, isEligible) => {
        const key = `${c.station_id}_${c.service_type}`;
        const ranked = rankMap.get(key);
        const rankNum = ranked ? ranked.rank : (isEligible ? '-' : 'N/A');
        const isTop = rankNum === 1;

        let travelText = '-';
        if (c.route_metrics?.duration_to_station_s != null) {
            travelText = `${(c.route_metrics.duration_to_station_s / 60).toFixed(1)} phút`;
        } else if (c.network_distance_m != null) {
            travelText = `${(c.network_distance_m / 1000).toFixed(1)} km`;
        }

        const queueText = c.operational?.estimated_wait_min != null ? `${c.operational.estimated_wait_min.toFixed(1)} phút` : '0.0 phút';
        const detourText = c.route_metrics?.detour_duration_s != null ? `${(c.route_metrics.detour_duration_s / 60).toFixed(1)} phút` : '-';
        const costText = ranked ? `${(ranked.final_cost_s / 60).toFixed(1)} phút` : '-';
        const capText = c.operational?.available_capacity != null ? `${c.operational.available_capacity}` : '-';

        return `
            <tr class="${isTop ? 'row-top-rec' : ''} ${!isEligible ? 'row-ineligible' : ''}">
                <td><span class="rank-badge ${isTop ? 'rank-1' : ''}">${rankNum}</span></td>
                <td><strong>${c.station_id}</strong></td>
                <td><span class="badge ${c.service_type === 'BATTERY_SWAP' ? 'badge-purple' : 'badge-teal'}">${c.service_type === 'BATTERY_SWAP' ? 'ĐỔI PIN' : 'SẠC PIN'}</span></td>
                <td>${isEligible ? `<span class="badge badge-success">PHÙ HỢP</span>` : `<span class="badge badge-danger">${c.reason || 'KHÔNG PHÙ HỢP'}</span>`}</td>
                <td>${travelText}</td>
                <td>${queueText}</td>
                <td>${detourText}</td>
                <td>${capText}</td>
                <td><strong>${costText}</strong></td>
            </tr>
        `;
    };

    return `
        <div class="candidate-tables-wrapper">
            <div class="table-section">
                <div class="section-title">Trạm phù hợp (${eligible.length})</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Hạng</th>
                            <th>Trạm</th>
                            <th>Dịch vụ</th>
                            <th>Trạng thái</th>
                            <th>Di chuyển</th>
                            <th>Thời gian chờ</th>
                            <th>Chênh lệch</th>
                            <th>Vị trí còn trống</th>
                            <th>Tổng thời gian hoàn tất</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${eligible.map(c => renderRow(c, true)).join('')}
                    </tbody>
                </table>
            </div>

            <div class="table-section mt-4">
                <div class="section-title">Trạm không phù hợp (${ineligible.length})</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>-</th>
                            <th>Trạm</th>
                            <th>Dịch vụ</th>
                            <th>Lý do</th>
                            <th>Khoảng cách</th>
                            <th>Thời gian chờ</th>
                            <th>-</th>
                            <th>Vị trí còn trống</th>
                            <th>-</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${ineligible.map(c => renderRow(c, false)).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

export function renderConflictAlert(conflictDetail, onRefresh) {
    return `
        <div class="conflict-alert-card" role="alert">
            <div class="conflict-header">
                <span class="conflict-badge">409 TRẠNG THÁI THAY ĐỔI</span>
                <h4>Trạm không còn khả dụng</h4>
            </div>
            <p>
                Một hoặc nhiều trạm thay đổi trạng thái hoạt động trong quá trình xử lý đề xuất.
                Hệ thống xếp hạng đã từ chối dữ liệu cũ.
            </p>
            <div class="conflict-actions">
                <button id="btn-refresh-conflict" class="btn btn-primary btn-sm">Làm mới đề xuất</button>
            </div>
        </div>
    `;
}

/**
 * Render error state for HTTP errors (409, 422, 503, etc.)
 */
export function renderErrorState(error, onRetry = null) {
    if (!error) return '';

    const isApiError = error instanceof ApiError;
    const status = isApiError ? error.status : 0;
    const message = isApiError ? error.message : (error.message || 'Unknown error');
    const code = isApiError ? error.code : null;

    // Determine error class and title
    let errorClass = '';
    let errorTitle = '';
    let errorCode = '';
    let errorMessage = '';

    if (status === 409) {
        errorClass = 'error-409';
        errorTitle = 'Trạm không còn khả dụng';
        errorCode = '409 Xung đột';
        errorMessage = 'Trạm thay đổi trong quá trình xử lý. Dữ liệu cũ đã bị từ chối.';
    } else if (status === 422) {
        errorClass = 'error-422';
        errorTitle = 'Yêu cầu không hợp lệ';
        errorCode = '422 Không xử lý được';
        errorMessage = code === 'LOCATION_UNAVAILABLE'
            ? 'Không thể xác định vị trí từ GPS hoặc map matching.'
            : (message || 'Yêu cầu chứa tham số không hợp lệ hoặc thiếu.');
    } else if (status === 503) {
        errorClass = 'error-503';
        errorTitle = 'Dịch vụ không khả dụng';
        errorCode = '503 Không khả dụng';
        errorMessage = code === 'DRIVER_STATE_UNAVAILABLE'
            ? 'Dịch vụ trạng thái tài xế tạm thời không khả dụng. Vui lòng thử lại.'
            : 'Phụ thuộc cần thiết (GraphHopper, PostgreSQL, hoặc Redis) không khả dụng.';
    } else if (status === 504) {
        errorClass = 'error-503';
        errorTitle = 'Hết thời gian chờ';
        errorCode = '504 Timeout';
        errorMessage = 'Định tuyến không phản hồi kịp thời. Vui lòng thử lại.';
    } else if (status === 0 || !isApiError) {
        errorClass = 'error-503';
        errorTitle = 'Lỗi kết nối';
        errorCode = 'NETWORK';
        errorMessage = 'Không thể kết nối đến máy chủ backend.';
    } else {
        errorClass = 'error-503';
        errorTitle = `Lỗi ${status}`;
        errorCode = `${status}`;
        errorMessage = message;
    }

    return `
        <div class="error-state ${errorClass}" role="alert">
            <div class="error-state-header">
                <span class="error-state-code">${errorCode}</span>
                <span class="error-state-title">${errorTitle}</span>
            </div>
            <div class="error-state-message">${errorMessage}</div>
            ${onRetry ? `
                <div class="error-state-actions">
                    <button class="btn btn-primary btn-sm" data-action="retry">Thử lại</button>
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * Render loading state
 */
export function renderLoadingState(message = 'Đang tải...') {
    return `
        <div class="loading-state">
            <div class="loading-spinner"></div>
            <span>${message}</span>
        </div>
    `;
}
