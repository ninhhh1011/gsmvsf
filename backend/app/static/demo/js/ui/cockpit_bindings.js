/** Browser boundary for the driver cockpit: DOM lookup and event translation. */
export function createCockpitBindings(root = globalThis.document) {
    const get = id => root?.getElementById(id);
    const listen = (id, type, callback, options) => get(id)?.addEventListener(type, callback, options);
    const each = (selector, callback) => root?.querySelectorAll(selector).forEach(callback);
    let analysisState;
    let assignedSlider;

    function bindStateButtons(bindings) {
        for (const [id, callback] of Object.entries(bindings)) listen(id, 'click', callback);
    }

    function updateAnalysisView(view) {
        if (!view) return;
        for (const [id, text] of [['hud-val-max-motor', view.maxMotorText], ['hud-val-instant-power', view.powerText], ['hud-vehicle-model', view.vehicleText], ['val-trip-range', view.rangeText]]) { const el = get(id); if (el) el.textContent = text; }
    }

    function bindActiveControls(callbacks) {
        bindStateButtons({
            'btn-driver-replay-play': callbacks.play,
            'btn-driver-replay-pause': callbacks.pause,
            'btn-driver-replay-step': callbacks.step,
            'btn-change-station': callbacks.unlockNavigation,
            'btn-nav-station': callbacks.navigateViaStation,
            'btn-switch-post-trip-modal': callbacks.switchToDestination,
            'btn-cancel-post-trip': callbacks.cancelPostTrip,
            'btn-view-cost-breakdown': callbacks.viewCostBreakdown,
            'btn-complete-trip': callbacks.completeTrip,
            'btn-driver-stations': callbacks.openStations
        });
        const slider = get('slider-cockpit-soc');
        slider?.addEventListener('input', event => callbacks.setSoc(parseFloat(event.target.value), false));
        slider?.addEventListener('change', event => callbacks.setSoc(parseFloat(event.target.value), true));
        each('.btn-quick-soc', btn => btn.addEventListener('click', event => callbacks.setSoc(parseFloat(event.currentTarget.dataset.soc), true)));
        each('.btn-quick-speed', btn => btn.addEventListener('click', event => callbacks.setSpeed?.(parseInt(event.currentTarget.dataset.speed, 10))));
        const speedSelect = get('select-replay-speed');
        if (speedSelect) speedSelect.addEventListener('change', event => callbacks.setSpeed?.(parseInt(event.target.value, 10)));
    }

    return {
        setVehicleCatalog(options, selected) {
            const select = get('cockpit-vehicle-select');
            if (!select) return;
            select.replaceChildren(...options.map(({ id, label }) => {
                const option = root.createElement('option');
                option.value = id;
                option.textContent = label;
                return option;
            }));
            select.value = selected;
        },
        setVehicleSelection(value) { const select = get('cockpit-vehicle-select'); if (select) select.value = value; },
        bindGlobalControls(callbacks) {
            listen('btn-driver-sheet-toggle', 'click', event => {
                const button = event.currentTarget;
                const expanded = get('driver-view-container')?.classList.toggle('is-expanded');
                button.setAttribute('aria-expanded', String(!!expanded));
                button.textContent = expanded ? button.dataset.expandedLabel : button.dataset.collapsedLabel;
            });
            listen('cockpit-vehicle-select', 'change', event => callbacks.selectVehicle(event.target.value));
            bindStateButtons({
                'btn-open-stations-drawer': callbacks.openStations,
                'btn-close-stations-drawer': callbacks.closeStations,
                'btn-pick-custom-origin': event => { event.stopPropagation(); event.preventDefault(); callbacks.pickOrigin(); },
                'btn-clear-custom-dest': callbacks.clearDestination,
                'btn-pick-custom-dest': event => { event.stopPropagation(); event.preventDefault(); callbacks.pickDestination(); },
                'btn-cancel-pick': event => { event.stopPropagation(); callbacks.cancelPicking(); },
                'btn-cancel-pick-dest': event => { event.stopPropagation(); callbacks.cancelPicking(); }
            });
            const intentTabs = [...root.querySelectorAll('.charging-intent-selector .intent-tab')];
            intentTabs.forEach(tab => tab.addEventListener('click', event => {
                const value = event.currentTarget.dataset.intent || 'EN_ROUTE';
                intentTabs.forEach(item => item.classList.remove('active'));
                event.currentTarget.classList.add('active');
                callbacks.changeIntent(value);
            }));
            const filterTabs = [...root.querySelectorAll('.drawer-filters .filter-tab')];
            filterTabs.forEach(tab => tab.addEventListener('click', event => {
                filterTabs.forEach(item => item.classList.remove('active'));
                event.currentTarget.classList.add('active');
                callbacks.changeFilter(event.currentTarget.dataset.filter || 'ALL');
            }));
        },
        setStatusBadge(view) {
            const badge = get('driver-status-badge');
            if (badge) {
                badge.textContent = view.label;
                const stateLabel = root.createElement('span');
                stateLabel.className = 'sr-only';
                stateLabel.textContent = view.accessibleState;
                badge.appendChild(stateLabel);
                badge.className = view.className;
            }
        },
        updateBattery(view) {
            for (const id of ['label-soc-slider-val', 'label-assigned-soc-val']) {
                const el = get(id); if (el) { el.textContent = view.labelText; el.style.color = view.labelColor; }
            }
            const soc = get('val-trip-soc'); if (soc) { soc.textContent = view.socText; soc.className = view.socClass; }
            const tripRange = get('val-trip-range'); if (tripRange) tripRange.textContent = view.rangeText;
            const assignedSoc = get('val-assigned-soc'); if (assignedSoc) assignedSoc.textContent = view.socText;
            const bar = get('battery-bar-fill'); if (bar) { bar.style.width = view.batteryWidth; bar.className = view.batteryClass; }
            for (const id of ['slider-cockpit-soc', 'slider-assigned-soc']) { const slider = get(id); if (slider && root.activeElement !== slider) slider.value = view.sliderValue; }
        },
        isStationsDrawerOpen() { const drawer = get('stations-drawer'); return !!drawer && drawer.style.display !== 'none'; },
        setStationsDrawerOpen(open) { const drawer = get('stations-drawer'); if (drawer) drawer.style.display = open ? 'flex' : 'none'; root?.body?.classList?.toggle('station-drawer-open', open); return !!drawer; },
        renderAnalysis(html, stateKey, view) { const slot = get('driver-analysis-content'); if (!slot) return; if (analysisState !== stateKey) { slot.innerHTML = html; analysisState = stateKey; } updateAnalysisView(view); },
        setOriginCoordinates(text) { const el = get('text-origin-coords'); if (el) el.textContent = text; },
        setDestinationCoordinates(text) { const el = get('text-dest-coords'); if (el) el.textContent = text; },
        setNavigationButtonState(text, disabled) { const button = get('btn-nav-station'); if (button) { button.textContent = text; button.disabled = disabled; } },
        setAfterDestinationEnabled(enabled, hasDestination = enabled) {
            const tab = get('tab-intent-dest'); if (tab) { tab.disabled = !enabled; tab.title = enabled ? '' : 'Cần một điểm B chưa đi qua để dùng lựa chọn này'; }
            const clear = get('btn-clear-custom-dest'); if (clear) { clear.style.display = hasDestination ? '' : 'none'; clear.disabled = !hasDestination; }
            const label = get('station-enroute-label'); if (label) label.textContent = enabled ? 'Ghé sạc giữa đường' : 'Tìm trạm từ vị trí A';
            const path = get('station-enroute-path'); if (path) path.textContent = enabled ? 'A ➔ Trạm ➔ B' : 'A ➔ Trạm';
        },
        setActiveIntent(value) { each('.charging-intent-selector .intent-tab', tab => tab.classList.toggle('active', tab.dataset.intent === value)); },
        showRouteUnavailable(message) { root?.defaultView?.alert(message); },
        renderAvailable(html, callbacks) {
            const container = get('driver-panel-content'); if (!container) return false;
            container.innerHTML = html;
            bindStateButtons({ 'btn-accept-trip': callbacks.accept, 'btn-pick-origin-map': event => { event.stopPropagation(); callbacks.pickOrigin(); }, 'btn-pick-dest-map': event => { event.stopPropagation(); callbacks.pickDestination(); }, 'btn-go-offline': callbacks.goOffline });
            return true;
        },
        renderOffline(html, callbacks) { const container = get('driver-panel-content'); if (!container) return false; container.innerHTML = html; listen('btn-go-online', 'click', callbacks.goOnline); return true; },
        renderAssigned(html, callbacks) {
            const container = get('driver-panel-content'); if (!container) return false;
            container.innerHTML = html;
            bindStateButtons({ 'btn-start-driving': callbacks.start, 'btn-assigned-pick-origin': event => { event.stopPropagation(); callbacks.pickOrigin(); }, 'btn-assigned-pick-dest': event => { event.stopPropagation(); callbacks.pickDestination(); }, 'btn-cancel-trip': callbacks.cancel });
            const slider = get('slider-assigned-soc');
            if (slider && slider !== assignedSlider) {
                slider.addEventListener('input', event => callbacks.setSoc(parseFloat(event.target.value), false));
                slider.addEventListener('change', event => callbacks.setSoc(parseFloat(event.target.value), false));
                each('.btn-preset-assigned-soc', btn => btn.addEventListener('click', event => callbacks.setSoc(parseFloat(event.currentTarget.dataset.soc), false)));
                assignedSlider = slider;
            }
            return true;
        },
        renderActive(html, state, callbacks) {
            const container = get('driver-panel-content'); if (!container) return false;
            const existing = container.querySelector('#driver-active-hud');
            if (!existing) { container.innerHTML = html; bindActiveControls(callbacks); }
            else {
                const view = state.view;
                const dist = get('val-remaining-dist'); if (dist) dist.innerHTML = view.distanceMarkup;
                const eta = get('val-trip-eta'); if (eta) eta.innerHTML = view.etaMarkup;
                const soc = get('val-trip-soc'); if (soc) { soc.textContent = view.socText; soc.className = view.socClass; }
                const range = get('val-trip-range'); if (range) range.innerHTML = view.rangeMarkup;
                updateAnalysisView(view);
                each('.btn-quick-speed', button => { button.classList.toggle('btn-primary', Number(button.dataset.speed) === state.speedMultiplier); button.classList.toggle('btn-outline', Number(button.dataset.speed) !== state.speedMultiplier); });
                const bar = get('battery-bar-fill'); if (bar) { bar.style.width = view.batteryWidth; bar.className = view.batteryClass; }
                const label = get('label-soc-slider-val'); if (label) { label.textContent = view.labelText; label.style.color = view.labelColor; }
                const slider = get('slider-cockpit-soc'); if (slider && root.activeElement !== slider) slider.value = view.sliderValue;
                const pos = get('hud-pos-status'); if (pos) pos.innerHTML = state.posStatus;
                const progress = get('hud-progress-status'); if (progress) progress.textContent = state.progress;
                const warning = get('hud-warning-container'); if (warning) warning.innerHTML = state.warning;
                const rec = get('hud-rec-container'); if (rec) { rec.innerHTML = state.recommendation; bindStateButtons({ 'btn-nav-station': callbacks.navigateViaStation, 'btn-switch-post-trip-modal': callbacks.switchToDestination, 'btn-view-cost-breakdown': callbacks.viewCostBreakdown }); }
                const postTrip = get('hud-post-trip-container'); if (postTrip) { postTrip.innerHTML = state.postTrip; listen('btn-cancel-post-trip', 'click', callbacks.cancelPostTrip); }
                const play = get('btn-driver-replay-play'); if (play) { play.innerHTML = state.playText; play.className = state.playClass; }
                const pause = get('btn-driver-replay-pause'); if (pause) pause.className = state.pauseClass;
                const change = get('btn-change-station'); if (change) change.style.display = state.navigationLocked ? 'block' : 'none';
            }
            return true;
        },
        renderComplete(html, callbacks) {
            const container = get('driver-panel-content'); if (!container) return false;
            container.innerHTML = html;
            bindStateButtons({ 'btn-start-post-trip-nav': callbacks.startPostTrip, 'btn-back-available': callbacks.backAvailable });
            return true;
        },
        renderDrawer(html, count, callbacks) {
            const list = get('stations-drawer-list'); if (!list) return;
            const countEl = get('drawer-station-count'); if (countEl) countEl.textContent = `${count} trạm trong danh sách`;
            const othersOpen = list.querySelector?.('.drawer-other-stations')?.open;
            const scrollTop = list.scrollTop;
            const focused = root.activeElement;
            const focusStationId = focused?.closest?.('.station-drawer-card')?.dataset.stationId;
            const focusClass = focused?.className;
            list.innerHTML = html;
            const others = list.querySelector?.('.drawer-other-stations');
            if (others) others.open = !!othersOpen;
            list.scrollTop = scrollTop;
            if (focusStationId) [...list.querySelectorAll('button')].find(button => button.closest('.station-drawer-card')?.dataset.stationId === focusStationId && button.className === focusClass)?.focus();
            for (const [selector, callback] of [['.btn-nav-drawer-station', callbacks.navigate], ['.btn-nav-post-trip-station', callbacks.setPostTrip], ['.btn-zoom-station', callbacks.zoom]]) {
                list.querySelectorAll(selector).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); callback(event.currentTarget.dataset); }));
            }
            // Tooltip hover/click bindings - 0 API calls on hover
            each('.station-drawer-card[data-station-id]', card => {
                card.addEventListener('mouseenter', event => {
                    if (callbacks.showTooltip) callbacks.showTooltip(event.currentTarget.dataset.stationId);
                });
                card.addEventListener('mouseleave', () => {
                    if (callbacks.hideTooltip) callbacks.hideTooltip();
                });
                card.addEventListener('click', event => {
                    if (callbacks.selectStationForTooltip) callbacks.selectStationForTooltip(event.currentTarget.dataset.stationId);
                });
            });
        },
        openCostBreakdown(html) { const modal = get('cost-breakdown-modal'), body = get('cost-modal-body'); if (!modal || !body) return false; body.innerHTML = html; modal.style.display = 'flex'; return true; },
        bindCostModalClose(callback) { listen('btn-close-cost-modal', 'click', callback, { once: true }); listen('cost-modal-backdrop', 'click', callback, { once: true }); },
        closeCostBreakdown() { const modal = get('cost-breakdown-modal'); if (modal) modal.style.display = 'none'; },
        bindH3Toggle(onToggle) {
            listen('toggle-route-familiarity', 'change', onToggle);
        },
        getH3Toggle() {
            return get('toggle-route-familiarity');
        },
        getH3CountElement() {
            return get('route-familiarity-count');
        },
        getH3SupportElement() {
            return get('route-familiarity-support');
        },
        setH3Checked(checked) {
            const el = get('toggle-route-familiarity');
            if (el) el.checked = Boolean(checked);
        },
        showH3Toast(message) {
            let toast = get('h3-notification-toast');
            if (!toast && root?.body) {
                toast = root.createElement('div');
                toast.id = 'h3-notification-toast';
                toast.className = 'h3-notification-toast';
                root.body.appendChild(toast);
            }
            if (toast) {
                toast.textContent = message;
                toast.classList.add('show');
                setTimeout(() => toast?.classList.remove('show'), 3000);
            }
        },
        bindH3ResCycle(onCycle) {
            listen('btn-h3-res-badge', 'click', onCycle);
        },
        getH3ResBadge() {
            return get('btn-h3-res-badge');
        },
        setH3ResBadgeText(text) {
            const el = get('btn-h3-res-badge');
            if (el) el.textContent = text;
        },
        setH3ResBadgeVisible(visible) {
            const el = get('btn-h3-res-badge');
            if (el) el.style.display = visible ? 'inline-flex' : 'none';
        },
        updateH3ComparisonBanner({ visible, proposedText, actualText, sharedDistText, cellCountText }) {
            const banner = get('h3-comparison-banner');
            if (!banner) return;
            banner.style.display = visible ? 'inline-flex' : 'none';
            if (visible) {
                const propEl = get('h3-pct-proposed-badge');
                if (propEl && proposedText != null) propEl.textContent = proposedText;
                const actEl = get('h3-pct-actual-badge');
                if (actEl && actualText != null) actEl.textContent = actualText;
                const distEl = get('h3-shared-dist-badge');
                if (distEl && sharedDistText != null) distEl.textContent = sharedDistText;
                const countEl = get('h3-cells-count-badge');
                if (countEl && cellCountText != null) countEl.textContent = cellCountText;
            }
        },
        updateInstantaneousPower(powerText) {
            const el = get('hud-val-instant-power');
            if (el && powerText != null) el.textContent = powerText;
        }
    };
}
