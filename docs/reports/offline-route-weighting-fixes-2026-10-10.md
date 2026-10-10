# Offline route comparison and weighting corrections

Date: 2026-10-10. Implementation branch: `fix/offline-route-weighting`. Base: `cd13150`. No deployment, runtime feature activation, destructive migration or Dataset edit was performed.

Plan: [implementation plan](../superpowers/plans/2026-10-10-offline-route-weighting-fixes.md). Contract: [design/spec](../superpowers/specs/2026-10-10-offline-route-weighting-fixes.md). Architecture decision: ADR-022 in [DECISIONS](../DECISIONS.md).

## What changed

- Corrected ordered corridor comparison with finite segment projection, neighboring H3 cells, one-use actual progress and bounded shared distance. Removed the three-index backward tolerance. A global 10 m sampling grid reduces dependence on vertex density. Resolution 9 is the default comparison metric; stored Resolution 11 is a separate lookup index.
- Fixed canonical Driver/API request and response names, units, shared-cell metadata and zero-match display. Offline proposal and evaluation time stay frozen; observed full GPS is explicitly labelled observed rather than ground truth. Replay progress does not change comparison extent. Trip/model/SOC changes invalidate pending results, including failed responses.
- Added nullable history geometry/start columns through additive idempotent schema DDL. Trusted retries can fill missing evidence without replacing known data. Legacy cell-only rows stay intact and cannot provide geometric ranking evidence. Queries exclude completion at or after request time; start-time Vietnam windows condition scoring. Seven-day default/30-day choice remain bounded.
- Connected the geometric matcher to existing familiarity ranking. Personal similarity contributes only the capped 0–30 second cost penalty. A workflow regression verifies that geometry history changes the selected station while preserving physical ETA and eligibility/409 behavior. Community stays explanation-only with five-driver suppression. Anonymous comparison never queries private history.
- Backend power-step estimates instantaneous power and interval energy used by replay SOC. Catalog loading retains nullable physical parameters and per-field provenance. Stationary auxiliary load and regenerative energy are supported; unavailable models stay unavailable, never silently VF3. Removed duplicated frontend power physics.
- Bound original vertices, distance, individual samples, query expansion, comparison work and 50,000 total prepared pieces per batch. Consume sample budget before allocation. Run CPU matching outside the request event loop; reuse prepared geometry/results only inside one batch.
- Replaced tests importing intentionally deleted Simulation/Tech code with Driver-only checks; removed unrelated unused imports that prevented lint. Fixed a pre-existing frontend test interval leak so the ordinary Node suite exits without forced termination.

## Verification on this working tree

| Check | Result |
|---|---|
| `python -B -m pytest backend/tests -q -p no:cacheprovider --basetemp=runtime/offline-route-fixes/pytest-final` | 561 passed, 12 skipped |
| `node --test tests/frontend/*.mjs` | 196 passed, 0 failed |
| `ruff check backend` | PASS |
| `git diff --check` | PASS |
| `python -B scripts/validate_frozen_dataset.py` | 152 PASS / 0 FAIL; 22/22 scenario assertions |
| SHA-256 before/after final verification | All 63 canonical Dataset files identical, including both PBFs |
| Driver serializer → real FastAPI response → Driver banner | PASS, canonical fields and meters-to-km conversion |
| Actual GraphHopper adapter | SUCCESS, 1,870.495 m route, 26 geometry vertices |
| Real PostgreSQL disposable database | Migration twice, legacy evidence upgrade, idempotency, conflicting geometry 409, equal-time completion excluded, five-driver community support PASS |
| New API in-process HTTP/ASGI + real PostgreSQL | Unsigned history 401; signed comparison 200, 100% self overlap; stationary power-step depletes energy |

Raw evidence: `runtime/offline-route-fixes/backend-tests.txt`, `frontend-tests.txt`, `validator.txt`, `dataset-integrity.json`, and `live-verification.json`. The PostgreSQL verification database was UUID-named and dropped in cleanup. The application database was not migrated or written by this check. GraphHopper was actually called; no engine mock fallback.

Regression cases include 80 m proposed/2 m actual, repeated traversal, 4 m offset across a cell boundary, opposite headings, sparse/dense vertices, work exhaustion, long two-vertex history expansion, wrapped longitude, causal history and start-time windows, protected history, immutable offline extent/time, supported and unavailable catalog boot, stationary auxiliary use, regen, and stale successful/failed UI requests.

Independent task review found five frontend lifecycle/catalog issues; all were fixed with red-to-green regressions. Final review found stale rejected energy responses, wrapped-longitude interpolation and batch sample allocation; all were reproduced and fixed. Existing routing, energy and ranking tests ran in the full suite. Twelve backend skips remain the suite's explicit environment/integration skips, not hidden failures.

## Limits and activation

The running API containers remain feature-off. Code integration is verified, but activating familiarity still requires explicit additive migration and the existing trusted exact-driver signing/ingestion boundary. Secrets are not exposed in frontend JS. No container rebuild/restart was performed.

The 10 m chord approximation and 45 m / 60 degree corridor thresholds are project assumptions; nearby streets can share a corridor under this definition. Observed GPS is noisy and not automatically map-matched by offline comparison. No new route-quality SLA or calibrated corridor accuracy is claimed.

Physics coefficients besides cited maximum-power evidence remain assumptions. Interval energy assumes linear speed change; regen acceptance is bounded by a project estimate. Remaining range still uses labelled catalog consumption. No real vehicle calibration or hardware power measurement was performed.

No full live browser QA was performed. HTTP schema/UI serializer checks and renderer/lifecycle regressions passed; deployment smoke testing should follow activation. Historical freeze reports remain historical and are not reused as evidence for these changes.
