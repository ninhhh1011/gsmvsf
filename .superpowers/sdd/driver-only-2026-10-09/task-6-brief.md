## Task 6: H3 Display-Only Layer

**Files:**
- Create: `tests/frontend/test_h3_display.mjs`
- Modify: `backend/app/static/demo/js/ui/route_familiarity_overlay.js`, `backend/app/static/demo/js/driver_mode.js`

**Interfaces:**
- Consumes: route geometry `[lat, lng][]` from `driver_mode._currentRoute`
- Produces: H3-11 cells rendered as overlay

**Tests to write:**

- [ ] **Step 1: Test — H3 toggle produces 0 API calls**

```javascript
it('H3 toggle does not call any API endpoint', async () => {
    // Setup: controller with active route
    // Action: toggle H3 on → wait 100ms → toggle H3 off
    // Assert: no api.* calls made during toggle
});
```

- [ ] **Step 2: Test — H3 toggle does not change selected station**

```javascript
it('H3 toggle does not modify selectedStationId', async () => {
    // Action: toggle H3
    // Assert: selectedStationId unchanged
});
```

- [ ] **Step 3: Test — route change clears old H3 cells**

```javascript
it('changing route removes previous H3 overlay', async () => {
    // Setup: H3 overlay visible with 50 cells
    // Action: change destination → new route
    // Assert: old cells removed, new cells added
});
```

- [ ] **Step 4: Implement H3 cell computation from geometry**

In `route_familiarity_overlay.js`, add method:

```javascript
computeH3CellsFromGeometry(geometryCoords, resolution = 11) {
    if (!geometryCoords || geometryCoords.length < 2) return [];
    const cells = new Set();
    // Sample along route segments every ~100m
    for (let i = 0; i < geometryCoords.length - 1; i++) {
        const [lat1, lng1] = geometryCoords[i];
        const [lat2, lng2] = geometryCoords[i + 1];
        const segDist = approxDistMeters(lat1, lng1, lat2, lng2);
        const numSamples = Math.max(1, Math.ceil(segDist / 100));
        for (let s = 0; s <= numSamples; s++) {
            const t = s / numSamples;
            const lat = lat1 + (lat2 - lat1) * t;
            const lng = lng1 + (lng2 - lng1) * t;
            const cell = h3.latLngToCell(lat, lng, resolution);
            cells.add(cell);
            if (cells.size >= 500) break; // cap per spec
        }
        if (cells.size >= 500) break;
    }
    return Array.from(cells);
}
```

- [ ] **Step 5: Bind H3 toggle in driver_mode.js**

```javascript
// In init():
this._h3Overlay = new RouteFamiliarityOverlay({ /* ... */ });
this._h3Enabled = false;

// In onToggleH3():
this._h3Enabled = !this._h3Enabled;
if (this._h3Enabled) {
    const cells = this._h3Overlay.computeH3CellsFromGeometry(this._currentRoute?.geometry);
    this._h3Overlay.render(cells);
} else {
    this._h3Overlay.clear();
}
```

- [ ] **Step 6: Run tests**

```bash
node --test tests/frontend/test_h3_display.mjs
```

- [ ] **Step 7: Commit**

```bash
git add tests/frontend/test_h3_display.mjs backend/app/static/demo/js/ui/route_familiarity_overlay.js backend/app/static/demo/js/driver_mode.js
git commit -m "feat(ui): add H3 display-only overlay from route geometry"
```

---

