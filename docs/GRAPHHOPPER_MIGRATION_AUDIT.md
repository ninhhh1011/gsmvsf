# GraphHopper migration repository audit

Audit date: 2026-09-21. Repository verified as `E:/build6week`.
Baseline: `master`, `a2f43a3`; historical tags `week1-map-matching-complete`
and `week2-demand-detection-complete` remain unchanged.

## Phase 0 / task GH-00

Result: PASS. Required scope, acceptance, data, architecture, decisions, routing
strategy, Week 1 freeze/audit, and Week 2/3 plans and reports reviewed.
Actual code takes precedence over historical implementation claims.

- Existing uncommitted dual-engine draft: 11 modified tracked files, new
  GraphHopper adapters/tests/config/models, `PLAN.md`, and `.claude/memory/`.
  Preserved in the working tree. An inherited concurrent audit claimed an external
  backup; this continuation did not create or rely on it. All continuation writes
  are confined to the repository.
- The complete pre-deletion text inventory is `GRAPHHOPPER_OSRM_INVENTORY.md`:
  583 occurrences, A=182, B=9, C=25, D=41, E=325, F=1.
- Active adapters: `services/routing/osrm_routing_adapter.py` and
  `services/map_matching/osrm_adapter.py`. The latter also owns shared result
  types imported by the new protocol and GraphHopper adapter: these must move.
- Engine branches: candidate API, map-match API, realtime API. Candidate service
  additionally constructs OSRM by default. Readiness probes OSRM directly.
- Settings: OSRM URL/data path and two engine selectors. Infrastructure:
  root Compose (there is no backend Compose), Makefile and `.env.example`.
- Tools: smoke tests, realtime benchmark and Week 3 smoke fallback. Week 3
  benchmark uses a mock; its documented timing is not a real-engine baseline.
- Docker currently runs API, PostGIS, OSRM and a floating GraphHopper
  `12.0-SNAPSHOT`; its cache cannot serve as the pinned migration baseline.
- Generated `runtime/osrm/*.osrm*` may remain ignored locally. Its checked-in
  profile and workflow references must be removed. GraphHopper cache must be ignored.
- Existing GraphHopper draft assumes JSON map matching and fabricated equal
  routing legs; neither is accepted evidence of a correct upstream API.

## Boundaries and integrity

Week 1: keep DriverStateStore, hybrid 10s/50m trigger, 30s/50-point window,
warm-up, stationary suppression, 60s gap reset and stale-observation policy.
Replace engine plumbing and return actual matched positions/segment resolution.
Historical quality is PARTIAL: 247/250 matched, 36.0% directed segment accuracy,
46.2% direction accuracy, position mean 4.65m / median 3.91m / P95 11.84m /
maximum 20.21m. Historical sample and aggregation limitations must be reported.

Week 2: preserve AUTO, DRIVER_REQUEST, ANY, capability and energy semantics.
Week 3: preserve station/service identity, expansion, eligibility precedence,
network reachability, SOC buffer and multi-leg arithmetic. No Week 4 work.

Dataset V1.3.1 is frozen. All 63 source files were SHA-256 inventoried in the
repository-local `runtime/migration/dataset-before.json`. Patched PBF SHA-256:
`0d3a66b2fb03019fd9d7877115c1ed9efbb736a83c5ac6f6e5440d71ddcfff60`.
Labels remain evaluation-only. Validation must not leave generated changes in
the frozen directory. No dataset file has been changed by this audit.

## Exit gate

- [x] Repository and inherited edits understood and backed up.
- [x] Active dependencies inventoried before deletion.
- [x] Existing GraphHopper draft identified.
- [x] Week 1/2/3 scope and dataset freeze understood.
- [x] Working tree safe to continue without discarding inherited work.

The mentor's explicit sole-GraphHopper instruction supersedes the old
dual-engine `PLAN.md` and historical engine decision gates. No engine-choice
question remains open.
