## Task 8: Clean app.js Bootstrap

**Files:**
- Modify: `backend/app/static/demo/js/app.js`
- Create: `tests/frontend/test_scenario_removal.mjs`

**Interfaces:**
- Consumes: `fetch('/demo/static/data/scenarios.json')`
- Produces: App boots and initializes without scenarios.json

**Tests to write:**

- [ ] **Step 1: Test — app boots when scenarios.json returns 404**

```javascript
it('app boots successfully when scenarios.json is unavailable', async () => {
    // Setup: mock fetch for scenarios.json to reject
    // Action: new DemoApp().init()
    // Assert: no bootstrap error thrown, driverMode initialized
});
```

- [ ] **Step 2: Test — app does not instantiate SimModeController**

```javascript
it('app does not create SimModeController instance', async () => {
    // Setup: full app init
    // Assert: app.simMode === undefined
});
```

- [ ] **Step 3: Modify app.js — remove SimModeController and scenarios bootstrap**

```javascript
// REMOVE from imports:
import { SimModeController } from './sim_mode.js';

// REMOVE from constructor:
this.simMode = null;

// REMOVE from init():
// SimModeController initialization block (lines ~57-70)

// MODIFY loadCatalogs():
// scenarios and trips: if fetch fails, log warning and continue with empty array
// DO NOT throw — degrade gracefully
```

- [ ] **Step 4: Remove mode tab HTML from index.html**

Search for `id="tab-driver"`, `id="tab-sim"`, `id="tab-debug"` in index.html. Remove sim and debug tab containers.

- [ ] **Step 5: Run tests**

```bash
node --test tests/frontend/test_scenario_removal.mjs
npm test 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add tests/frontend/test_scenario_removal.mjs backend/app/static/demo/js/app.js
git commit -m "refactor(app): remove SimModeController and graceful scenario degradation"
```

---

