import { escapeHtml } from '../domain/route-display.js';

export function renderDriverRecommendation(recResult) {
    if (!recResult?.has_recommendation || !recResult.ranked_candidates?.length) return '';
    const top = recResult.ranked_candidates[0];
    const isSwap = top.service_type === 'BATTERY_SWAP';
    const capacity = top.features?.available_capacity;
    return `<div class="on-trip-rec-alert ${isSwap ? 'border-swap' : 'border-charge'}">
        <strong>Đề xuất: Trạm ${escapeHtml(top.station_id)}</strong> · ${isSwap ? 'Đổi pin' : 'Sạc pin'}
        ${capacity != null ? `<span> · ${escapeHtml(String(capacity))} vị trí còn trống</span>` : ''}
        <p class="text-muted">${top.estimate_unavailable ? 'Ước tính pin và tổng thời gian chưa khả dụng; cần xác nhận lại phương án với pin hiện tại.' : 'Xem Top-5 và chọn phương án ghé trạm trong danh sách trạm.'}</p>
        <button id="btn-view-cost-breakdown" class="btn btn-outline btn-sm">Xem chi tiết chi phí</button>
    </div>`;
}
