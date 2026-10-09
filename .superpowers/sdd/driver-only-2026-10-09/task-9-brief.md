## Task 9: Delete Removed Files

**Files:**
- Delete: `backend/app/static/demo/js/sim_mode.js`, `backend/app/static/demo/js/tech_view.js`
- Delete: `backend/app/static/demo/data/scenarios.json`, `backend/app/static/demo/data/trips.json`

**Note:** Check `git status` first — some files may already be gone or moved.

- [ ] **Step 1: Verify no remaining imports of deleted files**

```bash
grep -r "sim_mode\|tech_view\|scenarios\.json\|trips\.json" backend/app/static/demo/js/ --include="*.js"
```

Expected: only references in test files or comments.

- [ ] **Step 2: Delete files**

```bash
# Linux/macOS:
rm backend/app/static/demo/js/sim_mode.js
rm backend/app/static/demo/js/tech_view.js
rm demo/data/scenarios.json
rm demo/data/trips.json

# Windows (Git Bash):
rm backend/app/static/demo/js/sim_mode.js
rm backend/app/static/demo/js/tech_view.js
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete sim_mode.js, tech_view.js, scenarios.json, trips.json

These files are removed from the runtime UI per the single Driver Mode design.
Dataset V1 and offline evaluation tests are unaffected."
```

---

