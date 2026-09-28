# Demo UI Bug Fixes Plan

**Date:** 2026-09-26  
**Status:** Ready for Implementation  
**Priority:** High

## Context

Four issues identified during demo testing:

1. **Điểm A (Origin) không chọn được** — Map picker for origin position is broken
2. **ETA hiển thị sai** — User perceives ETA calculation as wrong
3. **Route T00001 chết cứng** — Route doesn't update when car moves
4. **Cost breakdown không hiển thị** — Ranking cost components not visible

---

## Fix 1: Origin Picker Broken

### Root Cause
- HTML line 106: `id="map-picker-banner"`
- JS line 64: `document.getElementById('map-picking-indicator')` ← **Wrong ID**
- Banner text hardcoded for destination only, no dynamic text per mode

### Files to Modify
- `backend/app/static/demo/js/sim_mode.js` (lines 62-75)

### Change
```javascript
// BEFORE
const infoBar = document.getElementById('map-picking-indicator');

// AFTER  
const infoBar = document.getElementById('map-picker-banner');
// Dynamic text based on mode
const label = mode === 'origin' ? 'điểm bắt đầu' : 'điểm đến';
infoBar.querySelector('span').textContent = `📍 Chạm vào bản đồ để chọn ${label}`;
```

---

## Fix 2: Route T00001 Freezing

### Root Cause
- `projectPointOnRoute()` in `map.js` limits search window to 40 points ahead
- When car moves past this window, projection finds wrong segment or distance = 0
- `sliceRouteFromProgress()` then produces empty/invalid remaining route

### Files to Modify
- `backend/app/static/demo/js/map.js` (lines 83-96)

### Change
```javascript
// BEFORE - search window limited to 40 points
const searchEnd = Math.min(routeCoords.length - 1, searchStart + 40);

// AFTER - expand to 100 points AND ensure we don't go backward
const searchEnd = Math.min(routeCoords.length - 1, searchStart + 100);
```

### Additional Safety
- Add guard in `sliceRouteFromProgress()` for edge cases:
```javascript
if (segmentIndex >= routeCoords.length - 1) {
    return [routeCoords[routeCoords.length - 1]]; // Keep final point only
}
```

---

## Fix 3: Add Cost Breakdown Panel

### Root Cause
- Current `renderRecommendationCard()` shows top-level metrics
- Missing detailed cost component breakdown for transparency/debugging

### Files to Modify
- `backend/app/static/demo/js/components.js` (after line 178)

### Add New Function
```javascript
export function renderCostBreakdown(topCandidate) {
    const f = topCandidate.features;
    if (!f) return '';
    
    return `
        <div class="cost-breakdown-card">
            <div class="cost-header">Chi tiết tính toán</div>
            <div class="cost-row">
                <span>Thời gian di chuyển (cơ bản):</span>
                <span>${(f.base_travel_duration_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row">
                <span>Điều chỉnh giao thông:</span>
                <span>${(f.traffic_adjustment_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row">
                <span>Thời gian di chuyển (điều chỉnh):</span>
                <span>${(f.adjusted_travel_duration_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row">
                <span>Thời gian chờ (thực tế):</span>
                <span>${(f.effective_queue_wait_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row">
                <span>Thời gian dịch vụ:</span>
                <span>${(f.service_duration_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row total">
                <span>Tổng thời gian hoàn tất:</span>
                <span>${(topCandidate.eta_to_service_complete_s / 60).toFixed(1)} phút</span>
            </div>
            <div class="cost-row">
                <span>Khoảng cách đến trạm:</span>
                <span>${(f.distance_to_station_m / 1000).toFixed(1)} km</span>
            </div>
            <div class="cost-row">
                <span>Lệch lộ trình:</span>
                <span>+${(f.detour_distance_m / 1000).toFixed(1)} km</span>
            </div>
            <div class="cost-row">
                <span>Vị trí còn trống:</span>
                <span>${f.available_capacity ?? 'N/A'}</span>
            </div>
            ${f.traffic_state?.snapshot ? `
            <div class="cost-row muted">
                <span>Phương pháp traffic:</span>
                <span>${f.traffic_method || 'N/A'}</span>
            </div>
            ` : ''}
        </div>
    `;
}
```

### Integrate into `renderRecommendationCard()`
Add expandable section after line 178 (detour-bar):
```javascript
// Add expandable cost breakdown
<div class="mt-2">
    <details class="cost-details">
        <summary>🔧 Chi tiết tính toán</summary>
        ${renderCostBreakdown(topCandidate)}
    </details>
</div>
```

### Add CSS (in style.css)
```css
.cost-breakdown-card {
    background: rgba(0,0,0,0.1);
    border-radius: 8px;
    padding: 12px;
    font-size: 12px;
}
.cost-row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.cost-row:last-child { border-bottom: none; }
.cost-row.total { 
    font-weight: 700; 
    color: var(--brand-green);
    border-top: 2px solid currentColor;
    margin-top: 4px;
    padding-top: 8px;
}
.cost-row.muted { color: #94a3b8; font-style: italic; }
.cost-details summary { 
    cursor: pointer; 
    color: #94a3b8;
    font-size: 12px;
}
```

---

## Fix 4: ETA Clarification (Investigation)

### Investigation Required
User complaint "ETA tính B→Trạm không tính A→Trạm" may be:
1. Misunderstanding of what ETA shows
2. Actual calculation bug
3. Display issue

### Current Behavior
- `_evaluateAtCurrentPosition()` sends `raw_latitude/raw_longitude` (current car position)
- Backend calculates ETA from this position to station
- `eta_to_station_s` is displayed correctly

### Action
Add logging to verify backend receives correct coordinates:
```javascript
console.log('[DriverMode] Evaluating at:', rawLat, rawLng, 'Timestamp:', timestamp);
```

If ETA is genuinely wrong, investigate backend `multi_leg.py` distance calculation.

---

## Implementation Order

1. **Fix 1** (Origin picker) — Simple ID fix, ~5 min
2. **Fix 2** (Route freezing) — Search window expansion, ~5 min
3. **Fix 3** (Cost breakdown) — New UI component, ~15 min
4. **Fix 4** (ETA investigation) — Add logging, verify behavior

---

## Verification

1. Open demo at `http://127.0.0.1:8000/demo/technical`
2. Test Origin picker — should show correct banner text
3. Select trip T0001 and start driving — route should slice correctly
4. Check recommendation card — cost breakdown section should be expandable
5. Monitor console for ETA calculation logs
