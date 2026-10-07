/**
 * Cockpit UI HTML Template Renderers.
 * Pure rendering functions returning HTML strings, completely decoupled from map or API calls.
 */

import { renderEnergyWarningBanner, renderRecommendationCard, renderCostBreakdown } from '../components.js';
import { escapeHtml } from '../domain/route-display.js';

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
