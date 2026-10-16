## Task 4: Merge Recommendation Data Flow

**Files:**
- Create: `tests/frontend/test_top5_result_sharing.mjs`
- Modify: `backend/app/static/demo/js/driver_mode.js`, `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: `api.recommend(A, B, vehicle, soc, top_n=5, requested_service)`
- Produces: `this._top5Result` — shared by list renderer, map markers, tooltip

**Tests to write:**

- [ ] **Step 1: Test — "Tìm đường" always calls recommend, even with sufficient SOC**

```javascript
it('findRoute calls recommend even when SOC >= 50%', async () => {
    // Setup: soc = 80%
    // Action: call findRoute()
    // Assert: api.recommend was called with top_n=5
});
```

- [ ] **Step 2: Test — top 1 is NOT auto-selected after recommend**

```javascript
it('recommend response does not auto-select top 1 station', async () => {
    // Setup: mock recommend returns 3 candidates
    // Action: findRoute()
    // Assert: selectedStationId === null, no "Ghé trạm này" committed
});
```

- [ ] **Step 3: Test — 0/1/5 results handled without fake data**

```javascript
it('recommend with 0 results shows empty state, not fake candidates', async () => {
    // Setup: mock recommend returns empty array
    // Action: findRoute()
    // Assert: top5Result.candidates.length === 0, no fallback data
});
```

- [ ] **Step 4: Test — station with 2 services renders as one card with both services**

```javascript
it('station with BATTERY_SWAP and CHARGING renders as one composite card', async () => {
    // Setup: mock candidate with both service types
    // Action: render station card
    // Assert: one card, both services shown, rank not duplicated
});
```

- [ ] **Step 5: Implement `_top5Result` sharing**

In `DriverModeController`:
```javascript
// Add property
this._top5Result = null;
this._top5Revision = 0;

// In _onRecommendResponse():
if (responseRevision !== this._top5Revision) return;
this._top5Result = result;
this._notifyTop5Updated(result);

// map.js receives result via callback
this.map.updateStationMarkers(this._top5Result.candidates);
```

- [ ] **Step 6: Implement auto-refresh timer**

```javascript
// In init():
this._recommendRefreshInterval = options.recommendRefreshInterval ?? 30000;
this._recommendTimer = null;

startRecommendRefresh() {
    this.stopRecommendRefresh();
    this._recommendTimer = setInterval(
        () => this._refreshRecommendation(),
        this._recommendRefreshInterval
    );
}

stopRecommendRefresh() {
    if (this._recommendTimer) { clearInterval(this._recommendTimer); this._recommendTimer = null; }
}
```

- [ ] **Step 7: Run tests**

```bash
node --test tests/frontend/test_top5_result_sharing.mjs
```

- [ ] **Step 8: Commit**

```bash
git add tests/frontend/test_top5_result_sharing.mjs
git commit -m "test: add Top 5 result sharing and auto-refresh regression tests"
```

```bash
git add backend/app/static/demo/js/driver_mode.js backend/app/static/demo/js/driver_controller.js
git commit -m "feat(driver): add _top5Result sharing, auto-refresh, explicit service request"
```

---

