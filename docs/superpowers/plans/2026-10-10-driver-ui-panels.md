# Driver UI panels and metric clarity

User authorized four changes: integrate Top-5 into the station drawer, collapse/expand mobile panel while preserving map/actions, prioritize road distance/correct-target ETA/SOC with analysis tools folded away, improve color/contrast. No historical trip picker.

## Design and boundaries

- Existing station drawer is the sole station chooser. No automatic Top-5 popup. Backend ranked order is retained; Top-5 appears above remaining catalog stations in the same drawer. Opening/closing the drawer does not select a station or trigger duplicate recommendation requests.
- Mobile cockpit starts compact with primary route metrics and actions. A semantic expand/collapse button controls additional content and analysis. Mobile drawer is a bottom sheet; while open, cockpit cannot obscure its controls. Desktop retains separate non-overlapping cockpit and drawer.
- Native `details/summary` holds H3, coordinates, road identity, replay controls and simulation SOC controls. Open state remains stable across replay updates. Primary display has road distance, ETA to the current trip destination and SOC. Route-derived travel ETA is explicitly estimated and excludes queue/service stops; service-completion estimates remain named in the station drawer.
- Valid remaining road geometry takes precedence over straight-line fallback. Cache real GraphHopper duration/distance whenever current route changes, and estimate remaining travel time from route progress. Do not use ETA to an unselected recommended station as ETA to passenger destination.
- Preserve backend eligibility/ranking/physics, causal history, authentication and Dataset V1. No new dependencies, streaming, infrastructure, or runtime feature activation.

## Tasks

1. Write regressions for road-vs-straight-line distance, ETA source, no auto popup/drawer refresh, Top-5 ordering, analysis state and capability display updates. Observe failures before fixing.
2. Static/CSS task owns `index.html`/`style.css`: one analysis details with `driver-analysis-content` slot, move existing H3 IDs inside it, add `btn-driver-sheet-toggle` controlling `driver-panel-content`, retain global A/B/station toolbar, accessible responsive panel layout and unified light tokens. Keep cost modal valid.
3. JS task owns controller, bindings and renderers: remove popup creation, update drawer in place when already open, group Top-5, render analysis into its stable slot, use prepared metric/power views, preserve focus/details state, primary station chooser button, fix road fallback and cache engine route timing at every route-change caller. Use existing marker rendering for post-trip station choice; do not call nonexistent highlight API.
4. Run full frontend/backend suites and lint. Run real browser checks for no overlay obstruction, compact mobile map exposure, native analysis toggle/state persistence, current-model power, correct road distance and ETA, H3 cycling, station filtering/navigation/cost modal. Record screenshots and an independent review; fix material findings.

## Interface checklist

| Boundary | Contract |
|---|---|
| Static HTML / bindings | `btn-driver-sheet-toggle`, `driver-analysis-tools` details, `driver-analysis-content`; existing H3 and vehicle IDs preserved |
| Controller / renderers | currentRouteTiming `{distance_m,duration_s}`, road remaining distance, prepared analysis view; no DOM in controller |
| Renderer / bindings | primary HUD IDs stay; analysis markup is replaced only on driver-state transitions, values updated incrementally |
| Ranking / drawer | existing ranked_candidates order and station/service identities; no browser ranking |

Scope decisions: no dataset selection UI, no backend changes, no model calibration. Keep the snapshot/ranking and 30-second familiarity contracts unchanged. Work on `fix/driver-ui-panels`; preserve other untracked browser evidence/generator scripts.

## Execution evidence

All four UI tasks implemented. Frontend 205 PASS; backend 561 PASS / 12 skipped; Ruff PASS. Independent source review findings fixed and covered by focused regressions. Real-browser results and screenshots: runtime/driver-ui-panels/. See docs/reports/driver-ui-panels-2026-10-10.md for metric assumptions and limits.
