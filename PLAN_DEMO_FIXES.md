# Demo UI Fixes Plan

## Context
User reported 4 issues with the local demo:
1. **Tiếng Anh linh tinh** - UI has hardcoded English text; needs Vietnamese translation and cleanup
2. **Trạm không hiển thị** - Stations not showing on map in Driver Mode
3. **Map matching không chuẩn** - Map matching returning incorrect results
4. **ETA tính từ A thay vì B** - ETA displayed incorrectly (to station vs remaining trip)

## Phase 1: Root Cause Analysis (Complete)

### Issue 1: Tiếng Anh / Text Cleanup
**Files affected:** `driver_mode.js`, `components.js`, `index.html`, `style.css`

All UI text is hardcoded in English. Need to:
- Replace English text with Vietnamese equivalents
- Clean up any placeholder/garbage text
- Ensure consistent terminology

### Issue 2: Stations Not Displaying
**Files affected:** `driver_mode.js`, `map.js`, `app.js`

Root cause analysis:
- `this.stations` passed to `setCatalogs()` must be populated
- `renderStations()` must be called with valid station data
- Check if `replay.js` `step()` properly triggers `_onReplayStep()` callback

**Investigation needed:**
- Verify `this.stations` is populated from `loadCatalogs()`
- Verify `renderStations()` called in `_onReplayStep()` at line 410
- Check if `map.renderStations()` signature matches expected parameters

### Issue 3: Map Matching
**Files affected:** `replay.js`, `state.py`, GraphHopper adapter

Need to verify:
- GraphHopper map matching is functioning correctly
- Raw GPS fallback is working when matching fails
- Debug logs show actual matching results

### Issue 4: ETA Calculation
**Files affected:** `driver_mode.js`

The ETA displayed is `eta_to_station_s / 60` from backend response.
- Backend calculates from driver's current position (passed in request)
- Must verify frontend sends correct `currentPos` to backend

**Code path:** `_onReplayStep()` → updates `this.currentPos` → `_evaluateAtCurrentPosition()` sends request → backend returns `eta_to_station_s`

## Proposed Fixes

### Fix 1: Vietnamese UI Text
Replace all English strings in:
- `driver_mode.js` - UI text in render methods
- `components.js` - Banner text, labels
- `index.html` - Static HTML text (pipeline steps, labels)

### Fix 2: Station Display Debug
Add console logging to verify:
- `this.stations` array length after loadCatalogs()
- `renderStations()` call parameters
- Map layer group status

### Fix 3: Position Update Verification
In `_onReplayStep()`:
- Log `locResp.matched_position` and `locResp.raw_position`
- Verify `this.currentPos` is updated before calling `_evaluateAtCurrentPosition()`

### Fix 4: ETA Source Verification
Verify `eta_to_station_s` in backend response matches expected route:
- Driver position → Station (not origin → Station)

## Critical Files to Modify

1. `backend/app/static/demo/js/driver_mode.js`
   - Replace English text with Vietnamese
   - Add debug logging for position/ETA

2. `backend/app/static/demo/js/components.js`
   - Replace English text with Vietnamese

3. `backend/app/static/demo/index.html`
   - Replace static English text with Vietnamese

## Verification Steps

1. Run backend: `cd backend && uvicorn app.main:app --reload`
2. Open demo: http://localhost:8000/demo
3. Select trip T0004 (NEED_CHARGING scenario - has active recommendation)
4. Start trip and step through observations
5. Verify:
   - [ ] Vietnamese text displays correctly
   - [ ] Stations visible on map
   - [ ] ETA updates with each step
   - [ ] Map matching status shows in Tech View
