## Task 7: Transfer Synthetic GPS Init to Driver

**Files:**
- Modify: `backend/app/static/demo/js/driver_mode.js`, `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: GraphHopper route geometry from `api.route()`
- Produces: `replay.loadFromPolyline(geometry)` called on route selection

**Context (from sim_mode.js `runSimulation`):**

Sim currently generates synthetic GPS in `runSimulation()`. This logic moves to `driver_mode.js`.

- [ ] **Step 1: In driver_mode.js, call replay.loadFromPolyline() after route calculation**

```javascript
async _onRouteCalculated(geometry) {
    // geometry: [{lat, lng}, ...] from GraphHopper
    this._currentRoute = { geometry };
    this._routeRevision++;

    // Load synthetic GPS for replay
    if (this.replay) {
        await this.replay.loadFromPolyline(geometry, this._vehicleSpeedKmh ?? 35);
    }

    // Update map
    this.map.renderRoute(geometry);
}
```

- [ ] **Step 2: Bind Play/Pause/Speed controls**

The existing `cockpit_bindings.js` already has `btn-driver-replay-play`, `btn-driver-replay-pause`, `select-replay-speed`. Ensure these call `this.replay.play()`, `this.replay.pause()`, `this.replay.setSpeedMultiplier()`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/static/demo/js/driver_mode.js backend/app/static/demo/js/driver_controller.js
git commit -m "feat(driver): integrate synthetic GPS from GraphHopper geometry into replay"
```

---

