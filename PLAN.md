# Plan: Consolidate Documentation + Production-Ready Demo UI

## Context

Week 1-6 complete nhưng:
1. **44 docs files** — 20+ WEEK_*.md, evidence phân tán
2. **Demo UI** — mang tính "báo cáo" hơn là UX thực tế  
3. **Week 1→6 progression** không rõ trong UI

Backend đã solid (347 tests, real routing, no mocks). Cần cải thiện presentation.

---

## PHASE 1: Documentation Consolidation

### 1.1 New consolidated files

| File | Content |
|------|---------|
| `docs/PROGRESS.md` | Week 1→6 timeline với key achievements, mỗi week 1 section |
| `docs/TEST_RESULTS.md` | All test evidence inline (152 validator, 368 backend, 18 frontend, 8 scenarios) |
| `docs/ARCHITECTURE.md` | Current state + system diagram |

### 1.2 Files to DELETE (consolidation)

```
docs/WEEK_1.md, WEEK_1_*.md (6 files)
docs/WEEK_2*.md (2 files)  
docs/WEEK_3*.md (2 files)
docs/WEEK_4*.md (2 files)
docs/WEEK_5*.md (4 files)
docs/WEEK_6*.md (2 files)
docs/FINAL_*.md (4 files)
docs/PHASE_*.md (2 files)
docs/GRAPHHOPPER_*.md (7 files) → gộp thành 1
```

### 1.3 Files to KEEP (unchanged)

- `docs/PROJECT_SCOPE.md`
- `docs/ACCEPTANCE_CRITERIA.md`
- `docs/DATA_CONTRACT.md`
- `docs/DECISIONS.md`
- `docs/PRODUCIONIZATION_RUNBOOK.md`

---

## PHASE 2: Demo UI Redesign

### 2.1 Clear separation

**Before:**
- Tab 1: Driver Mode
- Tab 2: Explore Scenarios
- Button: Technical View

**After:**
- Primary: Driver Mode (full screen, distraction-free)
- Secondary: Scenario Explorer (collapsible panel, không phải tab)
- Tech View: Modal overlay (triggered by button)

### 2.2 Driver Mode UX improvements

| Current | Proposed |
|---------|----------|
| Status badge only | Trip progress indicator |
| Energy banner (amber/red) | Toast notifications + banner |
| Static demo data | Real API calls với loading states |
| No error UX | Proper 409/422/503 error handling UI |

### 2.3 Week Pipeline indicator

Visual badge trong UI hiển thị:
```
W1: Location → W2: Demand → W3: Candidates → W4: Ranking → W5: API
```

Current active step highlighted.

---

## PHASE 3: Implementation order

1. **Documentation** (2-3 hours)
   - Write `docs/PROGRESS.md`
   - Write `docs/TEST_RESULTS.md`
   - Rewrite `docs/ARCHITECTURE.md`
   - Delete old files

2. **UI** (4-6 hours)
   - Restructure `index.html` - remove tab, add collapsible panel
   - Update `driver_mode.js` - better error states, loading UX
   - Update `app.js` - mode management
   - Add pipeline indicator component

3. **Verification** (1 hour)
   - Run full test suite
   - Verify demo scenarios
   - Check no broken links

---

## Critical Files

| File | Change |
|-------|--------|
| `docs/PROGRESS.md` | NEW |
| `docs/TEST_RESULTS.md` | NEW |
| `docs/ARCHITECTURE.md` | REWRITE |
| `docs/index.html` (delete list) | DELETE 20+ files |
| `backend/app/static/demo/index.html` | Restructure |
| `backend/app/static/demo/js/driver_mode.js` | UX polish |
| `backend/app/static/demo/js/app.js` | Mode management |

---

## Verification

```bash
# Must pass before commit
python -B -m pytest backend/tests -q
node --test tests/frontend/*.mjs
python scripts/validate_frozen_dataset.py
python scripts/verify_demo_scenarios.py
```

---

## Open Questions

1. **Demo hay Production UI?** — Demo mode vẫn cần cho presentation?
2. **GraphHopper migration docs** — Gộp 7 files thành 1 hay xóa hết (đã historical)?
