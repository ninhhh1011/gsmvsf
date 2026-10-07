/** Browser boundary for the driver cockpit: DOM lookup, rendering, and event translation. */
export function createCockpitBindings(root = globalThis.document) {
    const get = id => root?.getElementById(id);
    const listen = (id, type, callback, options) => get(id)?.addEventListener(type, callback, options);
    const each = (selector, callback) => root?.querySelectorAll(selector).forEach(callback);

    function bindStateButtons(bindings) {
        for (const [id, callback] of Object.entries(bindings)) listen(id, 'click', callback);
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
            'btn-complete-trip': callbacks.completeTrip
        });
        const slider = get('slider-cockpit-soc');
        slider?.addEventListener('input', event => callbacks.setSoc(parseFloat(event.target.value), false));
        slider?.addEventListener('change', event => callbacks.setSoc(parseFloat(event.target.value), true));
        each('.btn-quick-soc', btn => btn.addEventListener('click', event => callbacks.setSoc(parseFloat(event.currentTarget.dataset.soc), true)));
    }

    return {
        setVehicleCatalog(vehicles, selected) {
            const select = get('cockpit-vehicle-select');
            if (!select) return;
            select.replaceChildren(...vehicles.map(vehicle => {
                const option = root.createElement('option');
                option.value = vehicle.id;
                option.textContent = `${vehicle.name} (${vehicle.battery_kwh.toFixed(1)} kWh)`;
                return option;
            }));
            select.value = selected;
        },
        setVehicleSelection(value) { const select = get('cockpit-vehicle-select'); if (select) select.value = value; },
        bindGlobalControls(callbacks) {
            listen('cockpit-vehicle-select', 'change', event => callbacks.selectVehicle(event.target.value));
            bindStateButtons({
                'btn-open-stations-drawer': callbacks.openStations,
                'btn-close-stations-drawer': callbacks.closeStations,
                'btn-pick-custom-origin': event => { event.stopPropagation(); event.preventDefault(); callbacks.pickOrigin(); },
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
        setStatusBadge(state, label) {
            const badge = get('driver-status-badge');
            if (badge) {
                badge.textContent = label;
                const stateLabel = root.createElement('span');
                stateLabel.className = 'sr-only';
                stateLabel.textContent = state;
                badge.appendChild(stateLabel);
                badge.className = `status-badge badge-${state.toLowerCase()}`;
            }
        },
        updateBattery(state) {
            const percent = state.soc.toFixed(0), range = state.range.toFixed(0), color = state.soc < 20 ? '#ef4444' : state.soc < 30 ? '#f59e0b' : '#10b981';
            for (const id of ['label-soc-slider-val', 'label-assigned-soc-val']) {
                const el = get(id); if (el) { el.textContent = `${percent}% (${range} km)`; el.style.color = color; }
            }
            const soc = get('val-trip-soc'); if (soc) { soc.textContent = `${percent}%`; soc.className = `stat-value ${state.soc < 20 ? 'text-danger' : ''}`; }
            const tripRange = get('val-trip-range'); if (tripRange) tripRange.textContent = `${range} km`;
            const assignedSoc = get('val-assigned-soc'); if (assignedSoc) assignedSoc.textContent = `${percent}%`;
            const bar = get('battery-bar-fill'); if (bar) { bar.style.width = `${Math.max(5, state.soc)}%`; bar.className = `battery-bar-fill ${state.soc < 20 ? 'bg-danger' : state.soc < 30 ? 'bg-warning' : 'bg-success'}`; }
            for (const id of ['slider-cockpit-soc', 'slider-assigned-soc']) { const slider = get(id); if (slider && root.activeElement !== slider) slider.value = Math.round(state.soc); }
        },
        isStationsDrawerOpen() { const drawer = get('stations-drawer'); return !!drawer && drawer.style.display !== 'none'; },
        setStationsDrawerOpen(open) { const drawer = get('stations-drawer'); if (drawer) drawer.style.display = open ? 'flex' : 'none'; return !!drawer; },
        setOriginCoordinates(coords) { const el = get('text-origin-coords'); if (el) el.textContent = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`; },
        setDestinationCoordinates(coords) { const el = get('text-dest-coords'); if (el) el.textContent = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`; },
        setNavigationButtonState(text, disabled) { const button = get('btn-nav-station'); if (button) { button.textContent = text; button.disabled = disabled; } },
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
            slider?.addEventListener('input', event => callbacks.setSoc(parseFloat(event.target.value), false));
            slider?.addEventListener('change', event => callbacks.setSoc(parseFloat(event.target.value), false));
            each('.btn-preset-assigned-soc', btn => btn.addEventListener('click', event => callbacks.setSoc(parseFloat(event.currentTarget.dataset.soc), false)));
            return true;
        },
        renderActive(html, state, callbacks) {
            const container = get('driver-panel-content'); if (!container) return false;
            const existing = container.querySelector('#driver-active-hud');
            if (!existing) { container.innerHTML = html; bindActiveControls(callbacks); }
            else {
                const dist = get('val-remaining-dist'); if (dist) dist.innerHTML = `${state.distance.toFixed(1)} <small>km</small>`;
                const eta = get('val-trip-eta'); if (eta) eta.innerHTML = `${state.eta} <small>phút</small><span class="sr-only">min</span>`;
                const soc = get('val-trip-soc'); if (soc) { soc.textContent = `${state.soc.toFixed(0)}%`; soc.className = `stat-value ${state.soc < 20 ? 'text-danger' : ''}`; }
                const range = get('val-trip-range'); if (range) range.innerHTML = `${state.range.toFixed(0)} <small>km</small>`;
                const bar = get('battery-bar-fill'); if (bar) { bar.style.width = `${Math.max(5, state.soc)}%`; bar.className = `battery-bar-fill ${state.soc < 20 ? 'bg-danger' : state.soc < 30 ? 'bg-warning' : 'bg-success'}`; }
                const label = get('label-soc-slider-val'); if (label) { label.textContent = `${state.soc.toFixed(0)}% (${state.range.toFixed(0)} km)`; label.style.color = state.soc < 20 ? '#ef4444' : state.soc < 30 ? '#f59e0b' : '#10b981'; }
                const slider = get('slider-cockpit-soc'); if (slider && root.activeElement !== slider) slider.value = Math.round(state.soc);
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
            const countEl = get('drawer-station-count'); if (countEl) countEl.textContent = `${count} trạm khả dụng`;
            list.innerHTML = html;
            for (const [selector, callback] of [['.btn-nav-drawer-station', callbacks.navigate], ['.btn-nav-post-trip-station', callbacks.setPostTrip], ['.btn-zoom-station', callbacks.zoom]]) {
                list.querySelectorAll(selector).forEach(button => button.addEventListener('click', event => { event.stopPropagation(); callback(event.currentTarget.dataset); }));
            }
        },
        openCostBreakdown(html) { const modal = get('cost-breakdown-modal'), body = get('cost-modal-body'); if (!modal || !body) return false; body.innerHTML = html; modal.style.display = 'flex'; return true; },
        bindCostModalClose(callback) { listen('btn-close-cost-modal', 'click', callback, { once: true }); listen('cost-modal-backdrop', 'click', callback, { once: true }); },
        closeCostBreakdown() { const modal = get('cost-breakdown-modal'); if (modal) modal.style.display = 'none'; },
        showRecommendationPanel(html, callbacks) {
            if (!root?.body) return;
            let panel = get('recommendation-panel');
            if (panel) panel.outerHTML = html;
            else root.body.insertAdjacentHTML('beforeend', html);
            panel = get('recommendation-panel');
            get('rec-panel-close')?.addEventListener('click', callbacks.close);
            panel?.querySelectorAll('.rec-candidate-item').forEach(item => {
                item.addEventListener('click', event => callbacks.selectStation(event.currentTarget.dataset.stationId));
            });
        },
        hideRecommendationPanel() { get('recommendation-panel')?.remove(); }
    };
}
