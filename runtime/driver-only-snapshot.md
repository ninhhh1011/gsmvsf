# Driver-only Implementation Baseline Snapshot

**Date:** 2026-10-09
**Branch:** main (ef4699a)

## Baseline State

### Git state
```
HEAD: ef4699a — docs: add driver-only architectural design spec
Uncommitted changes on disk:
  M backend/Dockerfile
  M backend/app/static/demo/js/api.js
  M backend/app/static/demo/js/replay.js
  M backend/app/static/demo/js/ui/cockpit_bindings.js
  M backend/app/static/demo/js/ui/cockpit_renderer.js
  M backend/app/static/demo/js/ui/driver_controller.js
  M backend/pyproject.toml
```

### Existing test files
- tests/frontend/test_replay_state_machine.mjs
- tests/frontend/test_mode_isolation.mjs
- tests/frontend/test_driver_playback_probe.mjs
- tests/frontend/test_cockpit_bindings.mjs
- tests/frontend/test_cockpit_renderer.mjs
- tests/frontend/test_drawer_renderer.mjs
- tests/frontend/test_driver_recommendation_renderer.mjs
- tests/frontend/test_route_familiarity_overlay.mjs
- tests/frontend/test_vehicle_catalog.mjs
- tests/frontend/test_vehicle_model.mjs
- tests/frontend/test_domain.mjs
- tests/frontend/test_navigation_tracker.mjs
- tests/frontend/test_station_evaluator.mjs
- tests/frontend/test_tech_view.mjs
- tests/frontend/test_tech_view_scenarios.mjs
- tests/frontend/test_demo_frontend.mjs
- tests/frontend/test_driver_state.mjs

### Files to delete (planned)
- backend/app/static/demo/js/sim_mode.js
- backend/app/static/demo/js/tech_view.js
- demo/data/scenarios.json
- demo/data/trips.json

### Known pending changes (not committed)
- backend/Dockerfile: 7 line changes
- backend/app/static/demo/js/api.js: 8 line changes
- backend/app/static/demo/js/replay.js: 132 line changes (pending fixes per investigation)
- backend/app/static/demo/js/ui/cockpit_bindings.js: 1 line change
- backend/app/static/demo/js/ui/cockpit_renderer.js: 8 line changes
- backend/app/static/demo/js/ui/driver_controller.js: 51 line changes
- backend/pyproject.toml: 3 line changes

### Design spec
- docs/superpowers/specs/2026-10-08-driver-only-design.md (committed ef4699a)

### Implementation plan
- docs/superpowers/plans/2026-10-09-driver-only-implementation.md
