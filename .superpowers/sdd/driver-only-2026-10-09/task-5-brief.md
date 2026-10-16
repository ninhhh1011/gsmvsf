## Task 5: Station Card and Tooltip UX

**Files:**
- Create: `tests/frontend/test_station_tooltip.mjs`
- Modify: `backend/app/static/demo/js/ui/drawer_renderer.js`, `backend/app/static/demo/js/ui/cockpit_renderer.js`, `backend/app/static/demo/js/map.js`

**Interfaces:**
- Consumes: `_top5Result` candidates
- Produces: `renderStationCardHTML(candidate, mode: 'list'|'tooltip')` and `renderStationTooltipHTML(candidate)`

**Tests to write:**

- [ ] **Step 1: Test — hover generates 0 API calls**

```javascript
it('hovering over station card produces 0 API calls', async () => {
    // Setup: controller with 5 candidates
    // Action: simulate 100 hover events on station elements
    // Assert: api call count === 0, SOC unchanged, selectedStationId unchanged
});
```

- [ ] **Step 2: Test — offline station has no "Ghé trạm" button**

```javascript
it('offline station card disables the select button', async () => {
    // Setup: candidate with station_state === 'offline'
    // Action: render card
    // Assert: no "Ghé trạm" button, tooltip shows station offline status
});
```

- [ ] **Step 3: Test — null queue_wait displays "Chưa có dữ liệu"**

```javascript
it('null effective_queue_wait_s displays placeholder, not 0', async () => {
    // Setup: candidate with queue_wait null
    // Action: render card
    // Assert: text contains "Chưa có dữ liệu", not "0 phút"
});
```

- [ ] **Step 4: Implement tooltip rendering**

```javascript
// drawer_renderer.js
export function renderStationTooltipHTML(candidate, stationCatalog) {
    const station = stationCatalog.find(s => s.station_id === candidate.station_id);
    const wait = candidate.features.effective_queue_wait_s !== null
        ? formatDuration(candidate.features.effective_queue_wait_s)
        : 'Chưa có dữ liệu';
    const capacity = candidate.features.available_capacity !== null
        ? candidate.features.available_capacity
        : '—';

    return `
        <div class="station-tooltip" data-station-id="${candidate.station_id}">
            <div class="tooltip-header">
                #${candidate.rank} ${station?.name || candidate.station_id}
                <span class="service-badge">${formatServiceType(candidate.service_type)}</span>
            </div>
            <div class="tooltip-metrics">
                <div>Xe → trạm: ${formatDistance(candidate.features.distance_to_station_m)} · ${formatDuration(candidate.features.eta_to_station_s)}</div>
                <div>Chờ: ${wait} · ${formatServiceType(candidate.service_type)}: ${formatDuration(candidate.features.service_duration_s)}</div>
                <div>Trạm → B: ${formatDistance(candidate.features.distance_station_to_dest_m)} · ${formatDuration(candidate.features.duration_station_to_dest_s)}</div>
                <div>Đi vòng: +${formatDistance(candidate.features.detour_distance_m)}</div>
                <div class="tooltip-total">Tổng: ${formatDuration(candidate.eta_to_destination_via_station_s)}</div>
                <div>Trống: ${capacity} vị trí</div>
            </div>
            <div class="tooltip-freshness">${renderFreshness(candidate.freshness)}</div>
            ${candidate.eligible ? '<button class="btn-ghe-tram">Ghé trạm này</button>' : '<div class="tooltip-ineligible">Không phù hợp</div>'}
        </div>
    `;
}
```

- [ ] **Step 5: Bind tooltip to hover/click in cockpit_bindings.js**

```javascript
// In setStationsDrawer():
each('.station-card[data-station-id]', card => {
    card.addEventListener('mouseenter', event => callbacks.showTooltip(event.currentTarget.dataset.stationId));
    card.addEventListener('mouseleave', () => callbacks.hideTooltip());
    card.addEventListener('click', event => callbacks.selectStationForTooltip(event.currentTarget.dataset.stationId));
});
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_station_tooltip.mjs
```

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_station_tooltip.mjs backend/app/static/demo/js/ui/drawer_renderer.js backend/app/static/demo/js/ui/cockpit_renderer.js backend/app/static/demo/js/ui/cockpit_bindings.js backend/app/static/demo/js/map.js
git commit -m "feat(ui): add station tooltip with full metrics, no API calls on hover"
```

---

