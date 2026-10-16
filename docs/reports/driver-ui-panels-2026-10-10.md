# Driver UI panels — verification, 2026-10-10

## Implemented scope

- One station drawer: unique Top-5 stations follow backend order; remaining stations use a native disclosure. Removed the auto-open recommendation popup and duplicate detailed chooser from the cockpit.
- Mobile cockpit starts compact and expands through an accessible toggle. Drawer is a bottom sheet with a fixed header and scrolling list; cockpit yields while it is open. Desktop keeps cockpit and drawer on opposite sides of the full map.
- Main HUD prioritizes destination, remaining road distance, estimated driving ETA and SOC. Coordinates, range/power, road identity, SOC simulation, replay speed/step and H3 live in native analysis details. Its open state and focused controls survive replay updates. Model/power display updates on vehicle changes.
- Light surfaces, clearer text/status colors, visible keyboard focus and 44px touch controls. Cost modal has a readable light surface and viewport-bounded scrolling.

## Correctness fixes discovered while integrating

The road distance was overwritten by a straight-line calculation; it now uses remaining geometry, including selected diversions. New routes cache their engine distance/duration. The ETA no longer uses time to an unselected recommended station. Rerouting reprojects progress onto the new road, rather than applying an old segment index. Missing road geometry uses a labelled straight-line fallback; missing timing stays unavailable.

Station selection after arrival uses the existing map marker contract instead of the nonexistent highlightStation method. Drawer refresh preserves the expanded remaining-catalog section, scrolling and focused station action. Persistent SOC controls bind once instead of accumulating handlers.

## Verification

- Frontend: 205 tests PASS. Regressions cover road bend vs diagonal, selected diversions, reroute timing/projection, backend ordering/deduplication, drawer state, analysis persistence, model values, sheet semantics and persistent SOC listeners.
- Backend: 561 PASS / 12 skipped; demo static-serving tests 3 PASS. No backend production code changed.
- Ruff: PASS; diff whitespace check: PASS.
- Independent source review reproduced two integration defects, both fixed; final focused review: 16 tests PASS, no remaining blocker in this change.
- Real browser testing uses installed Playwright Chromium against local frontend, FastAPI, GraphHopper, PostgreSQL and Redis. The configured computer-use browser was unavailable. Screenshots and executable verification are in `runtime/driver-ui-panels/`; final results are in `browser-results.json`: **39/39 PASS**, no page errors on desktop (1440×900) and mobile (390×844). Checks cover compact/expanded views, current-model power, analysis persistence, H3 cycling, backend Top-5 order, catalog disclosure persistence, filtering, station navigation/unlock, manual after-arrival selection/cancellation, cost modal, completion/reset. After-arrival selection does not assume backend recommendations must be nonempty.

## Limits

Driving ETA is a proportional estimate from the active engine route duration, not a traffic-updated per-segment forecast; station queue/service time is separate. The zero-distance after-arrival fallback is fixed, and its driving-to-B term uses active-route ETA. Existing non-ranked station cards retain approximate station-leg fallback metrics; this change does not certify them as engine-derived. Physical energy calibration and route-familiarity feature activation are outside this UI scope. Dataset V1 and pre-existing evidence/generator scripts were not edited.
