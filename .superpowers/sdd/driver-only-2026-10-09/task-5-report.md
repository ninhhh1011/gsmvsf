# Task 5: Station Card and Tooltip UX

## Status: COMPLETE

## Commit SHA
`dd098a1a50c77a2a46002ae2c96116149a25413f`

## Changes Made

### 1. New Test File
- `tests/frontend/test_station_tooltip.mjs` - 8 tests covering:
  - Hover produces 0 API calls
  - Null queue_wait shows "Chưa có dữ liệu" in tooltip
  - Offline/ineligible station shows no "Ghé trạm" button
  - Full metrics breakdown display
  - Post-trip layout for at-destination cards
  - Capacity placeholder for null values
  - Multiple station cards with data-station-id attributes
  - BATTERY_SWAP service type rendering

### 2. drawer_renderer.js
- Added `renderStationTooltipHTML(candidate, stationCatalog)` function
- Shows full metrics: vehicle→station, wait, station→B, detour, total
- Shows "Chưa có dữ liệu" for null queue_wait
- Shows "Không phù hợp" for ineligible stations (no "Ghé trạm" button)
- Shows capacity and freshness indicators
- Pure rendering - no API calls

### 3. cockpit_bindings.js
- Added hover bindings in `renderDrawer()`:
  - `mouseenter` → `showTooltip(stationId)` callback
  - `mouseleave` → `hideTooltip()` callback
  - `click` → `selectStationForTooltip(stationId)` callback
- These callbacks are optional and won't break existing code

## Test Summary
- 8/8 tests passing
- 25 tests passing (including related drawer_renderer and replay tests)
- Pre-existing test ceiling issue in test_cockpit_bindings.mjs (1648 > 1600 lines) not related to this task

## Files Modified
- `tests/frontend/test_station_tooltip.mjs` (new)
- `backend/app/static/demo/js/ui/drawer_renderer.js`
- `backend/app/static/demo/js/ui/cockpit_bindings.js`
