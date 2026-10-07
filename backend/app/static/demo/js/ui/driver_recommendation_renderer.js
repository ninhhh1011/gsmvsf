import { escapeHtml } from '../domain/route-display.js';

export function renderDriverRecommendation(recResult) {
    if (!recResult?.has_recommendation || !recResult.ranked_candidates?.length) return '';
    const top = recResult.ranked_candidates[0];
    const isSwap = top.service_type === 'BATTERY_SWAP';
    const detourKm = top.features?.detour_distance_m != null
        ? (top.features.detour_distance_m / 1000).toFixed(1)
        : '0.5';
    const detourMin = top.features?.detour_duration_s != null
        ? (top.features.detour_duration_s / 60).toFixed(0)
        : '2';
    const etaStationMin = (top.eta_to_station_s / 60).toFixed(0);
    const serviceMin = top.features?.service_duration_s != null
        ? (top.features.service_duration_s / 60).toFixed(0)
        : '15';
    const completionMin = top.eta_to_service_complete_s != null
        ? (top.eta_to_service_complete_s / 60).toFixed(0)
        : Math.round(top.final_cost_s / 60).toString();
    const etaTotalMin = top.eta_to_destination_via_station_s != null
        ? (top.eta_to_destination_via_station_s / 60).toFixed(0)
        : (top.features?.duration_station_to_dest_s != null
            ? Math.round((top.eta_to_service_complete_s + top.features.duration_station_to_dest_s) / 60).toString()
            : completionMin);
    const cap = top.features?.available_capacity;
    const capValue = typeof cap === 'number' && Number.isFinite(cap)
        ? String(cap)
        : (cap == null ? '' : escapeHtml(String(cap)));
    const capText = cap != null ? ` · ${capValue} vị trí còn trống` : '';

    const leg1D = top.distance_vehicle_to_station_m ? (top.distance_vehicle_to_station_m / 1000).toFixed(1) : '1.9';
    const leg2D = top.features?.distance_station_to_dest_m != null
        ? (top.features.distance_station_to_dest_m / 1000).toFixed(1)
        : (top.distance_station_to_dest_m ? (top.distance_station_to_dest_m / 1000).toFixed(1) : '—');
    const leg2T = top.features?.duration_station_to_dest_s != null
        ? Math.round(top.features.duration_station_to_dest_s / 60)
        : (top.duration_station_to_dest_s ? Math.round(top.duration_station_to_dest_s / 60) : '—');
    const waitT = top.queue_wait_s != null ? Math.round(top.queue_wait_s / 60) : 0;
    const costVal = top.score != null ? top.score.toFixed(3) : (top.final_cost_s ? (top.final_cost_s / 60).toFixed(1) : '—');

    return `
                <div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}" style="margin-top: 12px; padding: 12px; background: rgba(13, 148, 136, 0.1); border: 1px solid rgba(13, 148, 136, 0.3); border-radius: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <strong>Trạm ${escapeHtml(top.station_id)}</strong> — ${isSwap ? 'Đổi pin nhanh' : 'Sạc pin'}
                            <span class="sr-only">${escapeHtml(top.station_id)} ${isSwap ? 'Battery Swap' : 'Charging'}</span>
                            <div class="text-sm" style="margin-top: 4px; color: #cbd5e1; font-size: 12px; line-height: 1.5;">
                                🚗 Đến trạm: <strong>${etaStationMin}p</strong> · Sạc/đổi: <strong>${serviceMin}p</strong> · Về đích: <strong>${etaTotalMin}p</strong>
                            </div>
                        </div>
                        <span class="badge ${isSwap ? 'badge-purple' : 'badge-teal'}">
                            Đề xuất tối ưu
                            <span class="sr-only">Recommended</span>
                        </span>
                    </div>

                    <!-- Bảng thông số tính toán Cost trực quan -->
                    <div class="station-cost-grid mt-2" style="background: rgba(15, 23, 42, 0.5); border: 1px solid rgba(51, 65, 85, 0.7);">
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🚗 Chặng 1 (Xe ➔ Trạm)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${leg1D} km <small style="color:#cbd5e1;">(${etaStationMin} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">⚡ Tại trạm (Chờ + Sạc)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${waitT}p chờ · ${serviceMin}p sạc${capText}</span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🏁 Chặng 2 (Trạm ➔ B)</span>
                            <span class="cost-grid-val" style="color: #f8fafc;">${leg2D} km <small style="color:#cbd5e1;">(${leg2T} phút)</small></span>
                        </div>
                        <div class="cost-grid-item">
                            <span class="cost-grid-label" style="color: #94a3b8;">🔄 Lệch lộ trình (Detour)</span>
                            <span class="cost-grid-val" style="color: #f59e0b;">+${detourKm} km <span class="sr-only">detour</span><small style="color:#fcd34d;">(+${detourMin} phút)</small></span>
                        </div>
                    </div>

                    <div class="station-cost-summary mt-2" style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5);">
                        <span class="total-eta" style="color: #38bdf8;">⏱ Tổng thời gian chuyến đi: <strong>${etaTotalMin} phút</strong></span>
                        <span class="cost-score" style="color: #e2e8f0;">Điểm Cost: <strong>${costVal}</strong></span>
                    </div>

                    <div class="d-flex gap-2 mt-2" style="display: flex; gap: 8px; margin-top: 10px;">
                        <button id="btn-nav-station" class="btn btn-accent btn-sm flex-1" style="flex: 1.1;">
                            🔀 Ghé sạc ngay
                            <span class="sr-only">Navigate Via Station</span>
                        </button>
                        <button id="btn-switch-post-trip-modal" class="btn btn-primary btn-sm flex-1" style="flex: 1.1; background: #0f172a; border-color: #334155;">
                            🏁 Đến B rồi sạc
                        </button>
                        <button id="btn-view-cost-breakdown" class="btn btn-outline btn-sm" style="padding: 4px 8px; font-size: 12px;">
                            📊
                        </button>
                    </div>
                </div>
            `;
}
