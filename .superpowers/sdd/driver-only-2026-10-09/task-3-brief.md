## Task 3: Navigation Revision Guards

**Files:**
- Create: `tests/frontend/test_navigation_revision.mjs`
- Modify: `backend/app/static/demo/js/driver_controller.js`

**Interfaces:**
- Consumes: `_navigationRevision`, `_recommendationRevision`, `_routeRevision`
- Produces: Tests that stale async responses are discarded

**Tests to write:**

- [ ] **Step 1: Test — select NEW while OLD evaluation pending leg-2**

```javascript
it('selecting NEW station while OLD evaluation pending does not overwrite with OLD response', async () => {
    // Setup: mock API, pending recommend for station A
    // Action: user selects station B (NEW), OLD response arrives
    // Assert: selectedStationId === B (NEW), not A (OLD)
});
```

- [ ] **Step 2: Test — rapid B changes commit only final revision**

```javascript
it('rapid destination changes commit only the final revision', async () => {
    // Setup: mock API with 100ms delay per response
    // Action: change B → B' → B'' in rapid succession (50ms apart)
    // Assert: final route matches B'', not B' or B
});
```

- [ ] **Step 3: Implement revision guards in driver_controller.js**

Read existing code for revision patterns. Add checks in:
- `_onRecommendationResponse()` — check `_recommendationRevision` matches
- `_onRouteResponse()` — check `_routeRevision` matches
- `_onNavigation()` — check `_navigationRevision` matches

- [ ] **Step 4: Run tests**

```bash
node --test tests/frontend/test_navigation_revision.mjs
```

- [ ] **Step 5: Commit**

```bash
git add tests/frontend/test_navigation_revision.mjs backend/app/static/demo/js/driver_controller.js
git commit -m "test+fix: add navigation revision guards to prevent stale response overwrites"
```

---

