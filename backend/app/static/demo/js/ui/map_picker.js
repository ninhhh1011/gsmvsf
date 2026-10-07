/**
 * Map Picker module for Driver Mode.
 * Encapsulates interactive coordinate selection on Leaflet maps (Origin / Destination).
 */

export class MapPicker {
    /**
     * @param {Object} options
     * @param {Object} options.mapController - Map controller instance with .map Leaflet instance
     * @param {Function} options.onOriginSelected - Callback(coords: {latitude, longitude})
     * @param {Function} options.onDestinationSelected - Callback(coords: {latitude, longitude})
     */
    constructor(options = {}) {
        this.mapController = options.mapController;
        this.onOriginSelected = options.onOriginSelected;
        this.onDestinationSelected = options.onDestinationSelected;

        this.isPickingOrigin = false;
        this.isPickingDestination = false;
        this._onClickHandler = null;
    }

    setMapController(controller) {
        this.mapController = controller;
    }

    startPickOrigin() {
        if (!this.mapController?.map) return;
        this.cancelPickDestination();
        this.isPickingOrigin = true;

        this._updateBanner('📍 Chạm vào vị trí bất kỳ trên bản đồ để đặt ĐIỂM XUẤT PHÁT (A)', true);
        this._setContainerActive(true);
        this._setOriginButtonsActive(true);

        this._unbindClickListener();

        this._onClickHandler = async (e) => {
            const { lat, lng } = e.latlng;
            this.cancelPickOrigin();
            if (this.onOriginSelected) {
                await this.onOriginSelected({ latitude: lat, longitude: lng });
            }
        };

        setTimeout(() => {
            if (this.isPickingOrigin && this.mapController?.map) {
                this.mapController.map.once('click', this._onClickHandler);
            }
        }, 50);
    }

    cancelPickOrigin() {
        this.isPickingOrigin = false;
        this._updateBanner('', false);
        this._setContainerActive(false);
        this._setOriginButtonsActive(false);
        this._unbindClickListener();
    }

    startPickDestination() {
        if (!this.mapController?.map) return;
        this.cancelPickOrigin();
        this.isPickingDestination = true;

        this._updateBanner('🏁 Chạm vào vị trí bất kỳ trên bản đồ để đặt ĐIỂM ĐẾN (B)', true);
        this._setContainerActive(true);
        this._setDestButtonsActive(true);

        this._unbindClickListener();

        this._onClickHandler = async (e) => {
            const { lat, lng } = e.latlng;
            this.cancelPickDestination();
            if (this.onDestinationSelected) {
                await this.onDestinationSelected({ latitude: lat, longitude: lng });
            }
        };

        setTimeout(() => {
            if (this.isPickingDestination && this.mapController?.map) {
                this.mapController.map.once('click', this._onClickHandler);
            }
        }, 50);
    }

    cancelPickDestination() {
        this.isPickingDestination = false;
        this._updateBanner('', false);
        this._setContainerActive(false);
        this._setDestButtonsActive(false);
        this._unbindClickListener();
    }

    cancelAll() {
        this.cancelPickOrigin();
        this.cancelPickDestination();
    }

    _unbindClickListener() {
        if (this._onClickHandler && this.mapController?.map) {
            this.mapController.map.off('click', this._onClickHandler);
            this._onClickHandler = null;
        }
    }

    _updateBanner(text, visible) {
        if (typeof document === 'undefined') return;
        const banner = document.getElementById('map-picker-banner');
        const textSpan = document.getElementById('map-picker-banner-text');
        if (textSpan && text) textSpan.textContent = text;
        if (banner) banner.style.display = visible ? 'flex' : 'none';
    }

    _setContainerActive(active) {
        if (typeof document === 'undefined') return;
        const mapContainer = this.mapController?.map?.getContainer?.();
        if (mapContainer) {
            mapContainer.classList.toggle('map-picking-active', active);
        }
    }

    _setOriginButtonsActive(active) {
        if (typeof document === 'undefined') return;
        const ids = ['btn-pick-custom-origin', 'btn-pick-origin-map', 'btn-assigned-pick-origin'];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('active', active);
        }
    }

    _setDestButtonsActive(active) {
        if (typeof document === 'undefined') return;
        const ids = ['btn-pick-custom-dest', 'btn-pick-dest-map', 'btn-assigned-pick-dest'];
        for (const id of ids) {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('active', active);
        }
    }
}
